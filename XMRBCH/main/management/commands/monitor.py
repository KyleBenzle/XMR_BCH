"""
Deposit monitor — runs forever (as the xmrbch-monitor systemd service).

    python manage.py monitor           # loop
    python manage.py monitor --once    # single pass, then exit

All swap logic lives in main/swaps.py.
"""
import fcntl
import logging
import os
import time

from django.core.management.base import BaseCommand, CommandError

import config
from main import swaps

log = logging.getLogger("monitor")


class Command(BaseCommand):
    help = "Monitor for incoming deposits and execute swaps automatically."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one pass and exit")

    def handle(self, *args, **options):
        # Only one monitor may run at a time, or swaps could be paid twice.
        lock_path = os.path.join(config.DATA_DIR, "monitor.lock")
        self._lock = open(lock_path, "w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CommandError("Another monitor is already running.")

        network = "TESTNET/stagenet" if config.TESTNET else "MAINNET"
        log.info("=== XMRTo.Cash monitor started (%s), every %ss ===", network, config.MONITOR_INTERVAL_SECONDS)
        swaps.recover_interrupted_sends()

        while True:
            try:
                swaps.process_all()
            except Exception as e:
                log.exception("Monitor loop error: %s", e)
            if options["once"]:
                return
            time.sleep(config.MONITOR_INTERVAL_SECONDS)
