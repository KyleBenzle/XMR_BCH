import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.management.commands.monitor import Command as MonitorCommand
from main.models import Swap


class RatesApiTests(TestCase):
    @patch("main.views.xmr_util.get_balance", return_value=Decimal("4.5"))
    @patch("main.views.xmr_util.is_available", return_value=True)
    @patch("main.views.bch_util.get_operational_balance", return_value=Decimal("1.25"))
    @patch(
        "main.views.rates_util.get_rates",
        return_value={
            "bch_usd": 320.0,
            "xmr_usd": 160.0,
            "spot_bch_to_xmr": 2.0,
            "spot_xmr_to_bch": 0.5,
            "our_bch_to_xmr": 1.9,
            "our_xmr_to_bch": 0.475,
            "fee_percent": 5.0,
        },
    )
    def test_rates_view_returns_rates_and_balances(self, *_):
        resp = self.client.get(reverse("rates"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["bch_balance"], 1.25)
        self.assertEqual(data["xmr_balance"], 4.5)
        self.assertEqual(data["our_bch_to_xmr"], 1.9)


class SwapInitApiTests(TestCase):
    @patch("main.views.txlog.log_swap_created")
    @patch("main.views.bch_util.generate_address", return_value=("bchtest:abc123", "wif-123"))
    @patch(
        "main.views.rates_util.get_rates",
        return_value={
            "our_bch_to_xmr": 2.0,
            "our_xmr_to_bch": 0.5,
            "fee_percent": 5.0,
        },
    )
    def test_swap_init_bch_to_xmr_creates_swap(self, *_):
        payload = {
            "direction": "bch_to_xmr",
            "amount": "0.25",
            "receiving_address": "xmr-recv-addr",
        }
        resp = self.client.post(
            reverse("swap_init"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["direction"], "bch_to_xmr")
        self.assertEqual(data["deposit_address"], "bchtest:abc123")
        self.assertEqual(data["send_amount"], "0.500000000")
        self.assertTrue(Swap.objects.filter(swap_id=data["swap_id"]).exists())

    @patch("main.views.xmr_util.is_available", return_value=False)
    @patch(
        "main.views.rates_util.get_rates",
        return_value={
            "our_bch_to_xmr": 2.0,
            "our_xmr_to_bch": 0.5,
            "fee_percent": 5.0,
        },
    )
    def test_swap_init_xmr_to_bch_rejects_when_xmr_wallet_offline(self, *_):
        payload = {
            "direction": "xmr_to_bch",
            "amount": "0.25",
            "receiving_address": "bch-recv-addr",
        }
        resp = self.client.post(
            reverse("swap_init"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 503)
        self.assertIn("offline", resp.json()["error"].lower())


class SwapStatusApiTests(TestCase):
    def test_swap_status_auto_expires_pending_swap(self):
        swap = Swap.objects.create(
            direction="bch_to_xmr",
            deposit_address="bchtest:expired",
            deposit_private_key="wif-expired",
            receiving_address="xmr-recv",
            deposit_amount_expected=Decimal("0.1"),
            rate=Decimal("2.0"),
            send_amount=Decimal("0.2"),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        resp = self.client.get(reverse("swap_status", kwargs={"swap_id": str(swap.swap_id)}))
        self.assertEqual(resp.status_code, 200)
        swap.refresh_from_db()
        self.assertEqual(swap.status, "expired")
        self.assertEqual(resp.json()["status"], "expired")


class MonitorTests(TestCase):
    @patch("main.management.commands.monitor.txlog.log_deposit_received")
    @patch("main.management.commands.monitor.Command._send_xmr")
    @patch("main.utils.rates.calculate_send_amount", return_value=Decimal("1.9"))
    @patch(
        "main.utils.rates.get_rates",
        return_value={
            "our_bch_to_xmr": 1.9,
            "our_xmr_to_bch": 0.5,
            "fee_percent": 5.0,
        },
    )
    @patch("main.management.commands.monitor.bch_util.get_balance_by_address", return_value=Decimal("1.0"))
    def test_monitor_detects_bch_deposit_and_advances_state(self, *_):
        swap = Swap.objects.create(
            direction="bch_to_xmr",
            deposit_address="bchtest:dep1",
            deposit_private_key="wif-dep1",
            receiving_address="xmr-recv-1",
            deposit_amount_expected=Decimal("1.0"),
            rate=Decimal("1.8"),
            send_amount=Decimal("1.8"),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        cmd = MonitorCommand()
        cmd._check_bch_deposit(swap)
        swap.refresh_from_db()
        self.assertEqual(swap.status, "received")
        self.assertEqual(swap.deposit_amount_received, Decimal("1.0"))
