import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

from main.models import Swap
from main.utils import rates as rates_util
from main.utils import bch as bch_util
from main.utils import xmr as xmr_util
from main.utils import logger as txlog
import config


@method_decorator(csrf_exempt, name="dispatch")
class RatesView(View):
    """GET /api/rates/ — current exchange rates and wallet balances."""

    def get(self, request):
        try:
            r = rates_util.get_rates()
        except Exception as e:
            return JsonResponse({"error": f"Could not fetch rates: {e}"}, status=503)

        # Wallet balances (shown as "max tradable")
        bch_balance = bch_util.get_operational_balance()
        xmr_balance = None
        xmr_total_balance = None
        if xmr_util.is_available():
            try:
                xmr_balance = float(xmr_util.get_balance())
            except Exception:
                pass
            try:
                xmr_total_balance = float(xmr_util.get_total_balance())
            except Exception:
                pass

        r["bch_balance"] = float(bch_balance) if bch_balance is not None else None
        r["xmr_balance"] = xmr_balance
        r["xmr_total_balance"] = xmr_total_balance
        r["xmr_locked_balance"] = (
            max(0.0, xmr_total_balance - xmr_balance)
            if xmr_total_balance is not None and xmr_balance is not None
            else None
        )
        return JsonResponse(r)


@method_decorator(csrf_exempt, name="dispatch")
class SwapInitView(View):
    """POST /api/swap/init/ — create a new swap and return deposit address."""

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        direction = data.get("direction", "").strip()
        receiving_address = data.get("receiving_address", "").strip()

        try:
            deposit_amount = Decimal(str(data.get("amount", 0)))
        except InvalidOperation:
            return JsonResponse({"error": "Invalid amount"}, status=400)

        # Validate
        if direction not in ("bch_to_xmr", "xmr_to_bch"):
            return JsonResponse({"error": "direction must be bch_to_xmr or xmr_to_bch"}, status=400)
        if not receiving_address:
            return JsonResponse({"error": "receiving_address is required"}, status=400)
        if deposit_amount <= 0:
            return JsonResponse({"error": "amount must be greater than zero"}, status=400)

        min_amount = Decimal(str(config.MIN_BCH if direction == "bch_to_xmr" else config.MIN_XMR))
        if deposit_amount < min_amount:
            currency = "BCH" if direction == "bch_to_xmr" else "XMR"
            return JsonResponse({"error": f"Minimum swap is {min_amount} {currency}"}, status=400)

        # Get current rates
        try:
            r = rates_util.get_rates()
        except Exception as e:
            return JsonResponse({"error": f"Could not fetch rates: {e}"}, status=503)

        rate_key = "our_bch_to_xmr" if direction == "bch_to_xmr" else "our_xmr_to_bch"
        rate = Decimal(str(r[rate_key]))
        send_amount = deposit_amount * rate

        # Generate deposit address
        deposit_address = ""
        deposit_private_key = ""
        xmr_subaddress_index = None

        if direction == "bch_to_xmr":
            # User sends BCH — we generate a fresh BCH address
            try:
                deposit_address, deposit_private_key = bch_util.generate_address()
            except Exception as e:
                return JsonResponse({"error": f"Could not generate BCH address: {e}"}, status=500)
        else:
            # User sends XMR — create a subaddress in our XMR wallet
            if not xmr_util.is_available():
                return JsonResponse(
                    {"error": "XMR wallet is offline. Please try again later."},
                    status=503,
                )
            try:
                deposit_address, xmr_subaddress_index = xmr_util.create_deposit_address(
                    label=f"swap-{direction}"
                )
            except Exception as e:
                return JsonResponse({"error": f"Could not generate XMR address: {e}"}, status=500)

        # Save swap
        swap = Swap(
            direction=direction,
            deposit_address=deposit_address,
            deposit_private_key=deposit_private_key,
            xmr_subaddress_index=xmr_subaddress_index,
            receiving_address=receiving_address,
            deposit_amount_expected=deposit_amount,
            send_amount=send_amount,
            rate=rate,
        )
        swap.save()
        txlog.log_swap_created(swap)

        return JsonResponse({
            "swap_id": str(swap.swap_id),
            "direction": direction,
            "from_currency": swap.from_currency(),
            "to_currency": swap.to_currency(),
            "deposit_address": deposit_address,
            "deposit_amount": str(deposit_amount),
            "send_amount": str(send_amount.quantize(Decimal("0.000000001"))),
            "rate": str(rate),
            "fee_percent": config.FEE_PERCENT,
            "expires_at": swap.expires_at.isoformat(),
            "status": swap.status,
        })


@method_decorator(csrf_exempt, name="dispatch")
class SwapStatusView(View):
    """GET /api/swap/<swap_id>/ — poll swap progress."""

    def get(self, request, swap_id):
        try:
            swap = Swap.objects.get(swap_id=swap_id)
        except Swap.DoesNotExist:
            return JsonResponse({"error": "Swap not found"}, status=404)

        # Auto-expire stale pending swaps
        if swap.is_expired():
            swap.status = "expired"
            swap.save(update_fields=["status"])

        remaining = None
        if swap.status == "pending":
            remaining = max(0, int((swap.expires_at - timezone.now()).total_seconds()))

        return JsonResponse({
            "swap_id": str(swap.swap_id),
            "direction": swap.direction,
            "from_currency": swap.from_currency(),
            "to_currency": swap.to_currency(),
            "deposit_address": swap.deposit_address,
            "receiving_address": swap.receiving_address,
            "deposit_amount_expected": str(swap.deposit_amount_expected),
            "deposit_amount_received": str(swap.deposit_amount_received) if swap.deposit_amount_received else None,
            "send_amount": str(swap.send_amount) if swap.send_amount else None,
            "rate": str(swap.rate),
            "status": swap.status,
            "deposit_tx_hash": swap.deposit_tx_hash,
            "send_tx_hash": swap.send_tx_hash,
            "created_at": swap.created_at.isoformat(),
            "expires_at": swap.expires_at.isoformat(),
            "remaining_seconds": remaining,
            "notes": swap.notes,
        })
