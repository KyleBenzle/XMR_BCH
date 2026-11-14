import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from main.models import Swap
from main.utils import rates as rates_util
from main.utils import bch as bch_util
from main.utils import xmr as xmr_util
from main.utils import logger as txlog
import config

BALANCE_CACHE_SECONDS = 30


def site_context(request):
    """Template variables available on every page."""
    prefix = f"/{settings.URL_PREFIX}" if settings.URL_PREFIX else ""
    return {
        "base_path": prefix,
        "fee_percent": config.FEE_PERCENT,
        "expiry_hours": config.SWAP_EXPIRY_HOURS,
        "testnet": config.TESTNET,
    }


def _client_ip(request):
    # Behind the local reverse proxy REMOTE_ADDR is 127.0.0.1; the real
    # client is the last address the proxy appended to X-Forwarded-For.
    remote = request.META.get("REMOTE_ADDR", "")
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded and remote in ("127.0.0.1", "::1"):
        return forwarded.split(",")[-1].strip()
    return remote


def _rate_limited(request):
    key = f"swaps-ip:{_client_ip(request)}"
    count = cache.get(key, 0)
    if count >= config.SWAPS_PER_IP_PER_HOUR:
        return True
    cache.set(key, count + 1, 3600)
    return False


def _balances():
    """Wallet balances, cached briefly (they require slow network calls)."""
    cached = cache.get("balances")
    if cached:
        return cached

    bch_balance = bch_util.get_operational_balance()
    xmr_balance = xmr_total = None
    if xmr_util.is_available():
        try:
            unlocked, total = xmr_util.get_balances()
            xmr_balance, xmr_total = float(unlocked), float(total)
        except Exception:
            pass

    balances = {
        "bch_balance": float(bch_balance) if bch_balance is not None else None,
        "xmr_balance": xmr_balance,
        "xmr_total_balance": xmr_total,
        "xmr_locked_balance": (
            max(0.0, xmr_total - xmr_balance)
            if xmr_total is not None and xmr_balance is not None
            else None
        ),
    }
    cache.set("balances", balances, BALANCE_CACHE_SECONDS)
    return balances


@method_decorator(csrf_exempt, name="dispatch")
class RatesView(View):
    """GET /api/rates/ — current exchange rates and wallet balances."""

    def get(self, request):
        try:
            r = rates_util.get_rates()
        except Exception as e:
            return JsonResponse({"error": f"Could not fetch rates: {e}"}, status=503)
        r.update(_balances())
        r["min_bch"] = config.MIN_BCH
        r["min_xmr"] = config.MIN_XMR
        return JsonResponse(r)


@method_decorator(csrf_exempt, name="dispatch")
class SwapInitView(View):
    """POST /api/swap/init/ — create a new swap and return deposit address."""

    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        direction = str(data.get("direction", "")).strip()
        receiving_address = str(data.get("receiving_address", "")).strip()

        try:
            deposit_amount = Decimal(str(data.get("amount", 0)))
        except InvalidOperation:
            return JsonResponse({"error": "Invalid amount"}, status=400)

        # Validate
        if direction not in ("bch_to_xmr", "xmr_to_bch"):
            return JsonResponse({"error": "direction must be bch_to_xmr or xmr_to_bch"}, status=400)
        if not receiving_address:
            return JsonResponse({"error": "receiving_address is required"}, status=400)
        if not deposit_amount.is_finite() or deposit_amount <= 0:
            return JsonResponse({"error": "amount must be greater than zero"}, status=400)

        from_cur = "BCH" if direction == "bch_to_xmr" else "XMR"
        to_cur = "XMR" if direction == "bch_to_xmr" else "BCH"
        min_amount = Decimal(str(config.MIN_BCH if direction == "bch_to_xmr" else config.MIN_XMR))
        if deposit_amount < min_amount:
            return JsonResponse({"error": f"Minimum swap is {min_amount} {from_cur}"}, status=400)

        # The XMR wallet is needed either way: to pay out XMR, or to create
        # the XMR deposit address.
        if not xmr_util.is_available():
            return JsonResponse({"error": "XMR wallet is offline. Please try again later."}, status=503)

        # Validate the user's receiving address before they send us anything
        try:
            if direction == "bch_to_xmr":
                receiving_address = xmr_util.validate_address(receiving_address)
            else:
                receiving_address = bch_util.normalize_address(receiving_address)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except Exception:
            return JsonResponse({"error": "Could not validate address. Please try again."}, status=503)

        # Get current rates
        try:
            r = rates_util.get_rates()
        except Exception as e:
            return JsonResponse({"error": f"Could not fetch rates: {e}"}, status=503)

        rate_key = "our_bch_to_xmr" if direction == "bch_to_xmr" else "our_xmr_to_bch"
        rate = Decimal(str(r[rate_key]))
        send_amount = rates_util.calculate_send_amount(direction, deposit_amount, r)

        # Make sure we can actually pay this out
        balances = _balances()
        available = balances["xmr_balance"] if direction == "bch_to_xmr" else balances["bch_balance"]
        if available is None:
            return JsonResponse({"error": f"{to_cur} wallet is offline. Please try again later."}, status=503)
        if send_amount > Decimal(str(available)):
            max_in = (Decimal(str(available)) / rate).quantize(Decimal("0.0001"), rounding="ROUND_DOWN")
            return JsonResponse(
                {"error": f"Not enough {to_cur} liquidity. Max you can send right now: {max_in} {from_cur}"},
                status=400,
            )

        if _rate_limited(request):
            return JsonResponse({"error": "Too many swaps created. Please try again later."}, status=429)

        # Generate deposit address
        deposit_private_key = ""
        xmr_subaddress_index = None
        try:
            if direction == "bch_to_xmr":
                deposit_address, deposit_private_key = bch_util.generate_address()
            else:
                deposit_address, xmr_subaddress_index = xmr_util.create_deposit_address(label="swap")
        except Exception as e:
            return JsonResponse({"error": f"Could not generate {from_cur} address: {e}"}, status=500)

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
            "order_number": swap.order_number,
            "direction": direction,
            "from_currency": swap.from_currency(),
            "to_currency": swap.to_currency(),
            "deposit_address": deposit_address,
            "deposit_amount": str(deposit_amount),
            "send_amount": str(send_amount),
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

        remaining = None
        if swap.status == "pending":
            remaining = max(0, int((swap.expires_at - timezone.now()).total_seconds()))

        return JsonResponse({
            "swap_id": str(swap.swap_id),
            "order_number": swap.order_number,
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
