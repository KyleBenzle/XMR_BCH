"""
Helper to generate a fresh BCH operational wallet and print setup instructions.

    python manage.py generate_wallets
"""
from django.core.management.base import BaseCommand
from main.utils import bch as bch_util
import config


class Command(BaseCommand):
    help = "Generate a BCH operational wallet and print setup instructions."

    def handle(self, *args, **options):
        address, wif = bch_util.generate_address()

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  NEW BCH OPERATIONAL WALLET")
        self.stdout.write("=" * 60)
        self.stdout.write(f"\n  Network  : {'TESTNET' if config.TESTNET else 'MAINNET'}")
        self.stdout.write(f"  Address  : {address}")
        self.stdout.write(f"  WIF Key  : {wif}")
        self.stdout.write("\n  ACTION REQUIRED:")
        self.stdout.write("  1. Copy the WIF key above.")
        self.stdout.write("  2. Open config.py and set:")
        self.stdout.write(f"       BCH_OPERATIONAL_WIF = \"{wif}\"")
        self.stdout.write("  3. Fund this address with BCH so you can pay users.")
        self.stdout.write("\n  IMPORTANT: Keep your WIF key secret. Anyone with")
        self.stdout.write("  this key can spend the funds in this wallet.\n")
        self.stdout.write("=" * 60 + "\n")
