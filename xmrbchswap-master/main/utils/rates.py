"""
Fetch live BCH/XMR exchange rates from CoinGecko (free, no API key required).
"""
import requests
from decimal import Decimal
import config

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
FEE_MULTIPLIER = Decimal(str(1 - config.FEE_PERCENT / 100))  # e.g. 0.95


def get_spot_rates():
    """Return raw spot prices in USD from CoinGecko."""
    resp = requests.get(
        COINGECKO_URL,
        params={"ids": "bitcoin-cash,monero", "vs_currencies": "usd"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    bch_usd = Decimal(str(data["bitcoin-cash"]["usd"]))
    xmr_usd = Decimal(str(data["monero"]["usd"]))
    return bch_usd, xmr_usd


def get_rates():
    """
    Return a dict with spot and our rates (spot minus FEE_PERCENT).

    Rate convention:
      spot_bch_to_xmr  = how many XMR 1 BCH buys at market
      spot_xmr_to_bch  = how many BCH 1 XMR buys at market
      our_bch_to_xmr   = what the user actually receives per BCH (after fee)
      our_xmr_to_bch   = what the user actually receives per XMR (after fee)
    """
    bch_usd, xmr_usd = get_spot_rates()

    spot_bch_to_xmr = bch_usd / xmr_usd   # e.g. $350/$170 = 2.06 XMR per BCH
    spot_xmr_to_bch = xmr_usd / bch_usd   # e.g. $170/$350 = 0.486 BCH per XMR

    return {
        "bch_usd": float(bch_usd),
        "xmr_usd": float(xmr_usd),
        "spot_bch_to_xmr": float(spot_bch_to_xmr),
        "spot_xmr_to_bch": float(spot_xmr_to_bch),
        "our_bch_to_xmr": float(spot_bch_to_xmr * FEE_MULTIPLIER),
        "our_xmr_to_bch": float(spot_xmr_to_bch * FEE_MULTIPLIER),
        "fee_percent": config.FEE_PERCENT,
    }


def calculate_send_amount(direction, deposit_amount, rates=None):
    """Given deposit_amount and direction, return how much we send out."""
    if rates is None:
        rates = get_rates()
    deposit_amount = Decimal(str(deposit_amount))
    if direction == "bch_to_xmr":
        return deposit_amount * Decimal(str(rates["our_bch_to_xmr"]))
    else:
        return deposit_amount * Decimal(str(rates["our_xmr_to_bch"]))
