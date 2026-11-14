"""
Deposit monitor — run this in a second terminal while the Django server runs.

    python manage.py monitor

Checks all pending swaps every MONITOR_INTERVAL_SECONDS seconds.
When a deposit is detected it executes the swap and updates the database.
"""
import time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from main.models import Swap
from main.utils import bch as bch_util
from main.utils import xmr as xmr_util
from main.utils import logger as txlog
import config


class Command(BaseCommand):
    help = "Monitor for incoming deposits and execute swaps automatically."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== XMRTo.Cash deposit monitor started ==="))
        self.stdout.write(f"Checking every {config.MONITOR_INTERVAL_SECONDS}s. Press Ctrl+C to stop.\n")

        while True:
            try:
                self._check_all_pending()
            except Exception as e:
                self.stderr.write(f"[ERROR] Monitor loop error: {e}")
            time.sleep(config.MONITOR_INTERVAL_SECONDS)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _check_all_pending(self):
        pending = Swap.objects.filter(status="pending")
        if pending.exists():
            self.stdout.write(f"[{timezone.now().strftime('%H:%M:%S')}] Checking {pending.count()} pending swap(s)...")

        for swap in pending:
            if swap.is_expired():
                swap.status = "expired"
                swap.save(update_fields=["status"])
                self.stdout.write(f"  [{swap.swap_id}] Expired — no deposit received.")
                continue

            if swap.direction == "bch_to_xmr":
                self._check_bch_deposit(swap)
            else:
                self._check_xmr_deposit(swap)

    # ── BCH→XMR ───────────────────────────────────────────────────────────────

    def _check_bch_deposit(self, swap):
        balance = bch_util.get_balance_by_address(swap.deposit_address)
        if balance is None:
            return  # API error, will retry next cycle

        expected = swap.deposit_amount_expected
        # Allow 0.5% underpayment tolerance
        if balance < expected * Decimal("0.995"):
            return

        self.stdout.write(
            self.style.WARNING(f"  [{swap.swap_id}] BCH deposit detected: {balance} BCH")
        )

        # Mark received
        swap.status = "received"
        swap.deposit_amount_received = balance
        swap.deposit_received_at = timezone.now()
        swap.save(update_fields=["status", "deposit_amount_received", "deposit_received_at"])
        txlog.log_deposit_received(swap)

        # Recalculate send amount based on what was actually received
        from main.utils.rates import get_rates, calculate_send_amount
        try:
            r = get_rates()
            send_amount = calculate_send_amount("bch_to_xmr", balance, r)
        except Exception:
            # Fall back to the pre-locked rate
            send_amount = balance * swap.rate

        self._send_xmr(swap, send_amount)

    def _send_xmr(self, swap, send_amount):
        swap.status = "sending"
        swap.save(update_fields=["status"])

        try:
            tx_hash = xmr_util.send_xmr(swap.receiving_address, send_amount)
            swap.status = "complete"
            swap.send_amount = send_amount
            swap.send_tx_hash = tx_hash
            swap.completed_at = timezone.now()
            swap.save(update_fields=["status", "send_amount", "send_tx_hash", "completed_at"])
            txlog.log_swap_complete(swap)
            self.stdout.write(
                self.style.SUCCESS(f"  [{swap.swap_id}] COMPLETE — sent {send_amount:.8f} XMR  tx={tx_hash}")
            )
        except Exception as e:
            swap.status = "failed"
            swap.notes = str(e)
            swap.save(update_fields=["status", "notes"])
            txlog.log_swap_failed(swap, str(e))
            self.stderr.write(f"  [{swap.swap_id}] FAILED sending XMR: {e}")

    # ── XMR→BCH ───────────────────────────────────────────────────────────────

    def _check_xmr_deposit(self, swap):
        if swap.xmr_subaddress_index is None:
            return

        if not xmr_util.is_available():
            self.stderr.write("  XMR wallet offline — skipping XMR deposit checks.")
            return

        try:
            amount, txid = xmr_util.check_incoming(
                swap.xmr_subaddress_index,
                min_amount_xmr=swap.deposit_amount_expected * Decimal("0.995"),
            )
        except Exception as e:
            self.stderr.write(f"  [{swap.swap_id}] XMR check failed: {e}")
            return

        if amount is None:
            return

        self.stdout.write(
            self.style.WARNING(f"  [{swap.swap_id}] XMR deposit detected: {amount} XMR  tx={txid}")
        )

        swap.status = "received"
        swap.deposit_amount_received = amount
        swap.deposit_tx_hash = txid or ""
        swap.deposit_received_at = timezone.now()
        swap.save(update_fields=["status", "deposit_amount_received", "deposit_tx_hash", "deposit_received_at"])
        txlog.log_deposit_received(swap)

        from main.utils.rates import get_rates, calculate_send_amount
        try:
            r = get_rates()
            send_amount = calculate_send_amount("xmr_to_bch", amount, r)
        except Exception:
            send_amount = amount * swap.rate

        self._send_bch(swap, send_amount)

    def _send_bch(self, swap, send_amount):
        swap.status = "sending"
        swap.save(update_fields=["status"])

        try:
            tx_hash = bch_util.send_bch(swap.receiving_address, send_amount)
            swap.status = "complete"
            swap.send_amount = send_amount
            swap.send_tx_hash = tx_hash
            swap.completed_at = timezone.now()
            swap.save(update_fields=["status", "send_amount", "send_tx_hash", "completed_at"])
            txlog.log_swap_complete(swap)
            self.stdout.write(
                self.style.SUCCESS(f"  [{swap.swap_id}] COMPLETE — sent {send_amount:.8f} BCH  tx={tx_hash}")
            )
        except Exception as e:
            swap.status = "failed"
            swap.notes = str(e)
            swap.save(update_fields=["status", "notes"])
            txlog.log_swap_failed(swap, str(e))
            self.stderr.write(f"  [{swap.swap_id}] FAILED sending BCH: {e}")
