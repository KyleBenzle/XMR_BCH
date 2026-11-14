"""
Bitcoin Cash wallet utilities using the bitcash library.

For BCH→XMR swaps  : we generate a fresh BCH key per swap (deposit address),
                     and sweep it into the operational wallet once paid out.
For XMR→BCH swaps  : we send from the operational wallet (BCH_OPERATIONAL_WIF).
Balance checking    : bitcash's built-in Fulcrum/Chaingraph endpoints, which
                     report confirmations per UTXO.
"""
import logging
from decimal import Decimal

import config

log = logging.getLogger(__name__)

SATOSHI = Decimal("0.00000001")
_SATS_PER_BCH = Decimal(100_000_000)


def _network():
    return "testnet" if config.TESTNET else "mainnet"


def _key(wif=None):
    if config.TESTNET:
        from bitcash import PrivateKeyTestnet
        return PrivateKeyTestnet(wif) if wif else PrivateKeyTestnet()
    from bitcash import Key
    return Key(wif) if wif else Key()


def _operational_key():
    if not config.BCH_OPERATIONAL_WIF:
        raise RuntimeError("BCH_OPERATIONAL_WIF is not set in .env")
    return _key(config.BCH_OPERATIONAL_WIF)


def to_satoshi(amount_bch):
    return int((Decimal(str(amount_bch)) / SATOSHI).to_integral_value(rounding="ROUND_DOWN"))


def is_current_network(address):
    """True if a cashaddr belongs to the configured network (testnet vs mainnet)."""
    return address.startswith("bchtest:" if config.TESTNET else "bitcoincash:")


def generate_address():
    """Generate a fresh BCH key. Returns (address, wif)."""
    key = _key()
    return key.address, key.to_wif()


def normalize_address(address):
    """
    Return the canonical cashaddr for a user-supplied BCH address,
    or raise ValueError if it is invalid / for the wrong network.
    Accepts addresses with or without the "bitcoincash:" prefix.
    """
    from bitcash.cashaddress import Address

    prefix = "bchtest" if config.TESTNET else "bitcoincash"
    address = address.strip()
    if ":" not in address:
        address = f"{prefix}:{address}"
    try:
        parsed = Address.from_string(address.lower())
    except Exception:
        raise ValueError("Invalid BCH address (use the cashaddr format, e.g. bitcoincash:q...)")
    if parsed.prefix != prefix:
        raise ValueError(f"BCH address is for the wrong network (expected {prefix}:...)")
    if not parsed.version.startswith("P2PKH") and not parsed.version.startswith("P2SH"):
        raise ValueError("Unsupported BCH address type")
    return parsed.cash_address()


def get_deposit(address, min_confirmations=None):
    """
    Return (confirmed_bch, unconfirmed_bch, latest_txid) for an address.
    Only UTXOs with >= min_confirmations count as confirmed.
    Returns (None, None, None) on network error.
    """
    from bitcash.network import NetworkAPI

    if min_confirmations is None:
        min_confirmations = config.BCH_MIN_CONFIRMATIONS
    try:
        unspents = NetworkAPI.get_unspent(address, network=_network())
    except Exception as e:
        log.warning("[BCH] UTXO lookup failed for %s: %s", address, e)
        return None, None, None

    confirmed = sum(u.amount for u in unspents if u.confirmations >= min_confirmations)
    unconfirmed = sum(u.amount for u in unspents if u.confirmations < min_confirmations)
    txid = unspents[-1].txid if unspents else ""
    return Decimal(confirmed) / _SATS_PER_BCH, Decimal(unconfirmed) / _SATS_PER_BCH, txid


def operational_address():
    return _operational_key().address


def get_operational_balance():
    """Return the operational wallet BCH balance, or None if unavailable."""
    if not config.BCH_OPERATIONAL_WIF:
        return None
    try:
        return Decimal(_operational_key().get_balance("satoshi")) / _SATS_PER_BCH
    except Exception as e:
        log.warning("[BCH] Operational balance check failed: %s", e)
        return None


def send_bch(to_address, amount_bch):
    """
    Send BCH from the operational wallet to to_address.
    Returns tx_hash string on success, raises on failure.
    """
    key = _operational_key()
    sats = to_satoshi(amount_bch)
    if sats < 546:
        raise ValueError(f"Amount {amount_bch} BCH is below the dust limit")
    return key.send([(to_address, sats, "satoshi")])


def sweep_deposit(deposit_wif, to_address=None):
    """
    Send ALL BCH from a deposit address to to_address (default: the
    operational wallet). Returns tx_hash, or "" if there was nothing to sweep.
    """
    key = _key(deposit_wif)
    unspents = key.get_unspents()
    if not unspents:
        return ""
    return key.send([], leftover=to_address or operational_address(), unspents=unspents)
