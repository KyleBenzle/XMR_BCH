import json
import re
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

import config
from main import swaps
from main.models import Swap
from main.utils import bch as bch_util

RATES = {
    "bch_usd": 320.0,
    "xmr_usd": 160.0,
    "spot_bch_to_xmr": 2.0,
    "spot_xmr_to_bch": 0.5,
    "our_bch_to_xmr": 1.9,
    "our_xmr_to_bch": 0.475,
    "fee_percent": 5.0,
}


class BaseTest(TestCase):
    def setUp(self):
        cache.clear()
        p = patch("main.utils.logger._append")   # don't write the real log
        p.start()
        self.addCleanup(p.stop)

    def make_swap(self, **kw):
        defaults = dict(
            direction="bch_to_xmr",
            deposit_address="bchtest:qdeposit123456",
            deposit_private_key="wif-dep",
            receiving_address="xmr-recv",
            deposit_amount_expected=Decimal("1.0"),
            rate=Decimal("1.9"),
            send_amount=Decimal("1.9"),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        defaults.update(kw)
        return Swap.objects.create(**defaults)


# ── API ───────────────────────────────────────────────────────────────────────

@patch("main.views.rates_util.get_rates", return_value=dict(RATES))
@patch("main.views.bch_util.get_operational_balance", return_value=Decimal("1.25"))
@patch("main.views.xmr_util.get_balances", return_value=(Decimal("4.5"), Decimal("5.0")))
@patch("main.views.xmr_util.is_available", return_value=True)
class ApiTests(BaseTest):
    def test_home_served_under_prefix(self, *_):
        resp = self.client.get(f"/{config.URL_PREFIX}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'window.BASE_PATH = "/{config.URL_PREFIX}"')
        self.assertContains(resp, f"/{config.URL_PREFIX}/static/main/app.js")

    def test_rates_view_returns_rates_and_balances(self, *_):
        data = self.client.get(reverse("rates")).json()
        self.assertEqual(data["bch_balance"], 1.25)
        self.assertEqual(data["xmr_balance"], 4.5)
        self.assertEqual(data["xmr_locked_balance"], 0.5)
        self.assertEqual(data["our_bch_to_xmr"], 1.9)

    def post_init(self, **payload):
        return self.client.post(reverse("swap_init"), data=json.dumps(payload),
                                content_type="application/json")

    @patch("main.views.bch_util.generate_address", return_value=("bchtest:qq0123abc456", "wif-123"))
    @patch("main.views.xmr_util.validate_address", side_effect=lambda a: a)
    def test_swap_init_bch_to_xmr_creates_swap(self, *_):
        resp = self.post_init(direction="bch_to_xmr", amount="0.25", receiving_address="xmr-addr")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["deposit_address"], "bchtest:qq0123abc456")
        self.assertEqual(Decimal(data["send_amount"]), Decimal("0.475"))
        self.assertRegex(data["order_number"], r"^\d{14}_abc456$")
        self.assertTrue(Swap.objects.filter(swap_id=data["swap_id"]).exists())

    @patch("main.views.xmr_util.validate_address", side_effect=ValueError("Invalid XMR address for this network"))
    def test_swap_init_rejects_bad_xmr_address(self, *_):
        resp = self.post_init(direction="bch_to_xmr", amount="0.25", receiving_address="nope")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid XMR address", resp.json()["error"])
        self.assertFalse(Swap.objects.exists())

    def test_swap_init_rejects_bad_bch_address(self, *_):
        resp = self.post_init(direction="xmr_to_bch", amount="0.5", receiving_address="bchtest:garbage")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("BCH address", resp.json()["error"])

    @patch("main.views.xmr_util.validate_address", side_effect=lambda a: a)
    def test_swap_init_rejects_when_liquidity_too_low(self, *_):
        # 10 BCH * 1.9 = 19 XMR > 4.5 available
        resp = self.post_init(direction="bch_to_xmr", amount="10", receiving_address="xmr-addr")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("liquidity", resp.json()["error"])

    def test_swap_init_rejects_when_xmr_wallet_offline(self, mock_avail, *_):
        mock_avail.return_value = False
        resp = self.post_init(direction="xmr_to_bch", amount="0.25", receiving_address="bchtest:x")
        self.assertEqual(resp.status_code, 503)
        self.assertIn("offline", resp.json()["error"].lower())

    @patch("main.views.bch_util.generate_address", return_value=("bchtest:qq0123abc456", "wif"))
    @patch("main.views.xmr_util.validate_address", side_effect=lambda a: a)
    def test_swap_init_rate_limited(self, *_):
        with patch.object(config, "SWAPS_PER_IP_PER_HOUR", 2):
            codes = [self.post_init(direction="bch_to_xmr", amount="0.01",
                                    receiving_address="x").status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_swap_status(self, *_):
        swap = self.make_swap()
        data = self.client.get(reverse("swap_status", kwargs={"swap_id": swap.swap_id})).json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["order_number"], swap.order_number)
        self.assertNotIn("deposit_private_key", data)


# ── Address validation ───────────────────────────────────────────────────────

class BchAddressTests(TestCase):
    MAINNET_ADDR = "bitcoincash:qqaky5tlfe4zkdnuqzgxqh056zmq2ttpvg4wmd6mn9"

    def test_mainnet_with_and_without_prefix(self):
        with patch.object(config, "TESTNET", False):
            self.assertEqual(bch_util.normalize_address(self.MAINNET_ADDR), self.MAINNET_ADDR)
            self.assertEqual(bch_util.normalize_address(self.MAINNET_ADDR.split(":")[1]), self.MAINNET_ADDR)

    def test_wrong_network_rejected(self):
        with patch.object(config, "TESTNET", True):
            with self.assertRaises(ValueError):
                bch_util.normalize_address(self.MAINNET_ADDR)

    def test_bad_checksum_rejected(self):
        with patch.object(config, "TESTNET", False):
            with self.assertRaises(ValueError):
                bch_util.normalize_address(self.MAINNET_ADDR[:-1] + "8")


# ── Monitor / state machine ──────────────────────────────────────────────────

@patch("main.swaps.rates_util.get_rates", return_value=dict(RATES))
@patch("main.swaps.xmr_util.is_available", return_value=True)
@patch("main.swaps.xmr_util.get_balance", return_value=Decimal("100"))
@patch("main.swaps.bch_util.get_operational_balance", return_value=Decimal("100"))
@patch("main.swaps.bch_util.sweep_deposit", return_value="sweeptx")
@patch("main.swaps.xmr_util.send_xmr", return_value="xmrtx")
@patch("main.swaps.bch_util.send_bch", return_value="bchtx")
class MonitorTests(BaseTest):
    def setUp(self):
        super().setUp()
        p = patch.object(config, "BCH_OPERATIONAL_WIF", "op-wif")
        p.start()
        self.addCleanup(p.stop)

    def test_unconfirmed_deposit_moves_to_confirming(self, send_bch, send_xmr, *_):
        swap = self.make_swap()
        with patch("main.swaps.bch_util.get_deposit", return_value=(Decimal(0), Decimal("1.0"), "tx1")):
            swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "confirming")
        send_xmr.assert_not_called()

    def test_confirmed_bch_deposit_pays_xmr_and_sweeps(self, send_bch, send_xmr, sweep, *_):
        swap = self.make_swap()
        with patch("main.swaps.bch_util.get_deposit", return_value=(Decimal("1.0"), Decimal(0), "tx1")):
            swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "complete")
        self.assertEqual(swap.send_amount, Decimal("1.9"))
        self.assertEqual(swap.send_tx_hash, "xmrtx")
        self.assertEqual(swap.deposit_tx_hash, "tx1")
        self.assertEqual(swap.sweep_tx_hash, "sweeptx")
        send_xmr.assert_called_once_with("xmr-recv", Decimal("1.9"))
        sweep.assert_called_once_with("wif-dep")

    def test_confirmed_xmr_deposit_pays_bch(self, send_bch, send_xmr, *_):
        swap = self.make_swap(direction="xmr_to_bch", deposit_address="8xmrsub",
                              deposit_private_key="", xmr_subaddress_index=3,
                              receiving_address="bchtest:recv", rate=Decimal("0.475"))
        with patch("main.swaps.xmr_util.get_deposit", return_value=(Decimal("1.0"), Decimal(0), "xtx")):
            swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "complete")
        send_bch.assert_called_once_with("bchtest:recv", Decimal("0.475"))
        send_xmr.assert_not_called()

    def test_underpayment_waits(self, send_bch, send_xmr, *_):
        swap = self.make_swap()
        with patch("main.swaps.bch_util.get_deposit", return_value=(Decimal("0.5"), Decimal(0), "tx1")):
            swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "confirming")
        send_xmr.assert_not_called()

    def test_late_deposit_after_expiry_is_paid(self, send_bch, send_xmr, *_):
        swap = self.make_swap(expires_at=timezone.now() - timedelta(hours=2))
        with patch("main.swaps.bch_util.get_deposit", return_value=(Decimal(0), Decimal(0), "")):
            swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "expired")

        with patch("main.swaps.bch_util.get_deposit", return_value=(Decimal("0.5"), Decimal(0), "tx1")):
            swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "complete")
        send_xmr.assert_called_once_with("xmr-recv", Decimal("0.95"))

    def test_waits_for_liquidity_instead_of_failing(self, send_bch, send_xmr, sweep, op_bal, xmr_bal, *_):
        xmr_bal.return_value = Decimal("0.1")
        swap = self.make_swap()
        with patch("main.swaps.bch_util.get_deposit", return_value=(Decimal("1.0"), Decimal(0), "tx1")):
            swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "received")
        self.assertEqual(swap.notes, swaps.WAITING_FOR_LIQUIDITY)
        send_xmr.assert_not_called()

        xmr_bal.return_value = Decimal("100")
        with patch("main.swaps.bch_util.get_deposit", return_value=(Decimal("1.0"), Decimal(0), "tx1")):
            swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "complete")
        self.assertEqual(swap.notes, "")

    def test_pay_out_never_sends_twice(self, send_bch, send_xmr, *_):
        swap = self.make_swap(status="received", deposit_amount_received=Decimal("1.0"))
        stale_copy = Swap.objects.get(pk=swap.pk)
        swaps.pay_out(swap)
        swaps.pay_out(stale_copy)   # e.g. a second worker holding an old copy
        self.assertEqual(send_xmr.call_count, 1)

    def test_send_error_marks_failed(self, send_bch, send_xmr, *_):
        send_xmr.side_effect = RuntimeError("XMR RPC error: not enough money")
        swap = self.make_swap(status="received", deposit_amount_received=Decimal("1.0"))
        swaps.pay_out(swap)
        swap.refresh_from_db()
        self.assertEqual(swap.status, "failed")
        self.assertIn("not enough money", swap.notes)

    def test_interrupted_send_is_not_retried(self, send_bch, send_xmr, *_):
        swap = self.make_swap(status="sending", deposit_amount_received=Decimal("1.0"))
        swaps.recover_interrupted_sends()
        swaps.process_all()
        swap.refresh_from_db()
        self.assertEqual(swap.status, "failed")
        send_xmr.assert_not_called()


class OrderNumberTests(BaseTest):
    def test_format(self):
        swap = self.make_swap(deposit_address="bchtest:qzzzzzXYZ789")
        self.assertTrue(re.fullmatch(r"\d{14}_XYZ789", swap.order_number))
