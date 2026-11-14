"""
Swap state machine — everything the monitor does, in one place.

    pending ──deposit seen──▶ confirming ──confirmed──▶ received ──▶ sending ──▶ complete
       │                                                   │            │
       └──no deposit──▶ expired                            │            └──error──▶ failed
                         (late deposits within              └── waits here (with a note)
                          LATE_DEPOSIT_GRACE_DAYS are           if our wallet can't cover
                          still processed)                      the payout yet

Safety rules:
  * Every status change that leads to sending money is a compare-and-swap
    (UPDATE ... WHERE status=<old>), so a swap can never be paid twice.
  * A swap found in "sending" when the monitor starts was interrupted mid-send.
    We can't know if the coins went out, so it is marked "failed" for manual
    review instead of being retried.
  * After a BCH→XMR swap completes, the BCH deposit is swept into the
    operational wallet so it can fund XMR→BCH payouts.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

import config
from main.models import Swap
from main.utils import bch as bch_util
from main.utils import logger as txlog
from main.utils import rates as rates_util
from main.utils import xmr as xmr_util

log = logging.getLogger("monitor")

UNDERPAY_TOLERANCE = Decimal("0.995")   # accept deposits within 0.5% of expected
WAITING_FOR_LIQUIDITY = "Deposit received. Payout is queued and will be sent shortly."


def _transition(swap, from_status, to_status, **fields):
    """Atomically move swap from one status to another. Returns True on success."""
    fields["status"] = to_status
    updated = Swap.objects.filter(pk=swap.pk, status=from_status).update(**fields)
    if updated:
        for k, v in fields.items():
            setattr(swap, k, v)
    return bool(updated)


# ── Entry points ──────────────────────────────────────────────────────────────

def recover_interrupted_sends():
    """Call once at monitor startup."""
    for swap in Swap.objects.filter(status="sending"):
        note = ("Payout was interrupted. Operator: check the wallet for an outgoing "
                "transaction before retrying (set status back to 'received' to retry).")
        if _transition(swap, "sending", "failed", notes=note):
            txlog.log_swap_failed(swap, note)
            log.error("[%s] Found in 'sending' at startup — marked failed for manual review", swap.order_number)


def process_all():
    """One pass of the monitor loop."""
    _expire_stale()

    grace_cutoff = timezone.now() - timedelta(days=config.LATE_DEPOSIT_GRACE_DAYS)
    watch = Swap.objects.filter(status__in=["pending", "confirming"]) | Swap.objects.filter(
        status="expired", expires_at__gte=grace_cutoff
    )
    for swap in watch:
        try:
            check_deposit(swap)
        except Exception as e:
            log.exception("[%s] deposit check error: %s", swap.order_number, e)

    for swap in Swap.objects.filter(status="received"):
        try:
            pay_out(swap)
        except Exception as e:
            log.exception("[%s] payout error: %s", swap.order_number, e)

    for swap in Swap.objects.filter(direction="bch_to_xmr", status="complete", sweep_tx_hash=""):
        try:
            sweep(swap)
        except Exception as e:
            log.warning("[%s] sweep failed (will retry): %s", swap.order_number, e)


# ── Steps ─────────────────────────────────────────────────────────────────────

def _expire_stale():
    now = timezone.now()
    # A "confirming" swap that expires is still paid out once its deposit
    # confirms (see the late-deposit rule in check_deposit).
    for swap in Swap.objects.filter(status__in=["pending", "confirming"], expires_at__lt=now):
        if _transition(swap, swap.status, "expired"):
            log.info("[%s] expired", swap.order_number)


def _get_deposit(swap):
    """Return (confirmed, unconfirmed, txid) or None if the chain/wallet is unreachable."""
    if swap.direction == "bch_to_xmr":
        if not bch_util.is_current_network(swap.deposit_address):
            return None   # swap from the other network (e.g. TESTNET was switched)
        confirmed, unconfirmed, txid = bch_util.get_deposit(swap.deposit_address)
        if confirmed is None:
            return None
        return confirmed, unconfirmed, txid
    if swap.xmr_subaddress_index is None or not xmr_util.is_available():
        return None
    return xmr_util.get_deposit(swap.xmr_subaddress_index)


def check_deposit(swap):
    result = _get_deposit(swap)
    if result is None:
        return
    confirmed, unconfirmed, txid = result

    min_amount = Decimal(str(config.MIN_BCH if swap.direction == "bch_to_xmr" else config.MIN_XMR))
    full_payment = confirmed >= swap.deposit_amount_expected * UNDERPAY_TOLERANCE
    # Once a swap has expired we stop waiting for the rest of an underpayment
    # and pay out for whatever (above the minimum) actually arrived.
    late_or_partial = swap.status == "expired" and confirmed >= min_amount

    if full_payment or late_or_partial:
        if _transition(
            swap, swap.status, "received",
            deposit_amount_received=confirmed,
            deposit_tx_hash=txid or swap.deposit_tx_hash,
            deposit_received_at=timezone.now(),
            notes="",
        ):
            txlog.log_deposit_received(swap)
            log.info("[%s] deposit confirmed: %s %s", swap.order_number, confirmed, swap.from_currency())
            pay_out(swap)
        return

    seen = confirmed + unconfirmed
    if seen > 0 and swap.status == "pending":
        if _transition(swap, "pending", "confirming",
                       deposit_amount_received=seen, deposit_tx_hash=txid or ""):
            log.info("[%s] deposit seen (%s %s), waiting for confirmations",
                     swap.order_number, seen, swap.from_currency())


def pay_out(swap):
    """Send the output coin for a swap in 'received'."""
    try:
        r = rates_util.get_rates()
        send_amount = rates_util.calculate_send_amount(swap.direction, swap.deposit_amount_received, r)
    except Exception:
        # Price feed down — fall back to the rate quoted when the swap was created
        send_amount = rates_util.quantize_output(swap.direction, swap.deposit_amount_received * swap.rate)

    available = _available_output_balance(swap)
    if available is None or available < send_amount:
        if swap.notes != WAITING_FOR_LIQUIDITY:
            Swap.objects.filter(pk=swap.pk).update(notes=WAITING_FOR_LIQUIDITY)
            swap.notes = WAITING_FOR_LIQUIDITY
            log.warning("[%s] waiting for liquidity: need %s %s, available %s",
                        swap.order_number, send_amount, swap.to_currency(), available)
        return

    if not _transition(swap, "received", "sending", send_amount=send_amount, notes=""):
        return  # someone else got it first

    try:
        if swap.direction == "bch_to_xmr":
            tx_hash = xmr_util.send_xmr(swap.receiving_address, send_amount)
        else:
            tx_hash = bch_util.send_bch(swap.receiving_address, send_amount)
    except Exception as e:
        note = f"Payout failed: {e}"
        _transition(swap, "sending", "failed", notes=note)
        txlog.log_swap_failed(swap, note)
        log.error("[%s] %s", swap.order_number, note)
        return

    _transition(swap, "sending", "complete", send_tx_hash=tx_hash, completed_at=timezone.now())
    txlog.log_swap_complete(swap)
    log.info("[%s] COMPLETE — sent %s %s tx=%s", swap.order_number, send_amount, swap.to_currency(), tx_hash)

    if swap.direction == "bch_to_xmr":
        try:
            sweep(swap)
        except Exception as e:
            log.warning("[%s] sweep failed (will retry): %s", swap.order_number, e)


def _available_output_balance(swap):
    try:
        if swap.direction == "bch_to_xmr":
            return xmr_util.get_balance() if xmr_util.is_available() else None
        return bch_util.get_operational_balance()
    except Exception:
        return None


def sweep(swap):
    """Move a completed BCH→XMR deposit into the operational wallet."""
    if not swap.deposit_private_key or not config.BCH_OPERATIONAL_WIF:
        return
    if not bch_util.is_current_network(swap.deposit_address):
        return
    tx_hash = bch_util.sweep_deposit(swap.deposit_private_key)
    Swap.objects.filter(pk=swap.pk).update(sweep_tx_hash=tx_hash or "empty")
    swap.sweep_tx_hash = tx_hash or "empty"
    if tx_hash:
        txlog.log_deposit_swept(swap)
        log.info("[%s] swept deposit into operational wallet tx=%s", swap.order_number, tx_hash)
