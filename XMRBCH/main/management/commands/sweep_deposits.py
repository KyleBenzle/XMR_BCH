"""
Sweep leftover BCH from old deposit addresses into the operational wallet.

    python manage.py sweep_deposits            # dry run: show what's there
    python manage.py sweep_deposits --execute  # actually send

The monitor sweeps completed swaps automatically; this is for anything left
behind (e.g. swaps from before auto-sweep existed, or expired swaps that got
a deposit after the grace period). Failed swaps are skipped — those deposits
may need to be refunded to the user.
"""
from django.core.management.base import BaseCommand

import config
from main.models import Swap
from main.utils import bch as bch_util


class Command(BaseCommand):
    help = "Sweep BCH left on per-swap deposit addresses into the operational wallet."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", help="Send transactions (default: dry run)")
        parser.add_argument("--include-failed", action="store_true", help="Also sweep failed swaps")

    def handle(self, *args, **options):
        if not config.BCH_OPERATIONAL_WIF:
            self.stderr.write("BCH_OPERATIONAL_WIF is not set in .env")
            return
        dest = bch_util.operational_address()
        self.stdout.write(f"Operational wallet: {dest}\n")

        qs = Swap.objects.filter(direction="bch_to_xmr").exclude(deposit_private_key="")
        if not options["include_failed"]:
            qs = qs.exclude(status="failed")

        total = 0
        for swap in qs:
            confirmed, unconfirmed, _ = bch_util.get_deposit(swap.deposit_address, min_confirmations=0)
            if not confirmed:
                continue
            total += confirmed
            line = f"  {swap.order_number}  {swap.status:<10} {confirmed} BCH  {swap.deposit_address}"
            if options["execute"]:
                try:
                    tx = bch_util.sweep_deposit(swap.deposit_private_key, dest)
                    Swap.objects.filter(pk=swap.pk).update(sweep_tx_hash=tx or "empty")
                    line += f"  → swept tx={tx}"
                except Exception as e:
                    line += f"  → FAILED: {e}"
            self.stdout.write(line)

        verb = "Swept" if options["execute"] else "Found (dry run — add --execute to send)"
        self.stdout.write(f"\n{verb}: {total} BCH")
