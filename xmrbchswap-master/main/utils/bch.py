"""
Bitcoin Cash wallet utilities using the bitcash library.

For BCH→XMR swaps  : we generate a fresh BCH key per swap (deposit address).
For XMR→BCH swaps  : we send from the operational wallet configured in config.py.
Balance checking    : uses Blockchair API (reliable, free, no key needed).
"""
import requests
from decimal import Decimal
import config

# Blockchair endpoints
_BLOCKCHAIR_MAINNET = "https://api.blockchair.com/bitcoin-cash/dashboards/address/{}"
_BLOCKCHAIR_TESTNET = "https://api.blockchair.com/bitcoin-cash/testnet/dashboards/address/{}"


def _blockchair_url(address):
    if config.TESTNET:
        return _BLOCKCHAIR_TESTNET.format(address)
    return _BLOCKCHAIR_MAINNET.format(address)


def generate_address():
    """Generate a fresh BCH key. Returns (address, wif)."""
    if config.TESTNET:
        from bitcash import PrivateKeyTestnet
        key = PrivateKeyTestnet()
    else:
        from bitcash import Key
        key = Key()
    return key.address, key.to_wif()


def get_balance_by_address(address):
    """
    Check BCH balance for any address via Blockchair.
    Returns balance in BCH as Decimal, or None on error.
    """
    try:
        resp = requests.get(_blockchair_url(address), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        satoshis = data["data"][address]["address"]["balance"]
        return Decimal(satoshis) / Decimal("1e8")
    except Exception as e:
        print(f"[BCH] Balance check failed for {address}: {e}")
        return None


def get_operational_balance():
    """Return the operational wallet BCH balance, or None if not configured."""
    if not config.BCH_OPERATIONAL_WIF:
        return None
    if config.TESTNET:
        from bitcash import PrivateKeyTestnet
        key = PrivateKeyTestnet(config.BCH_OPERATIONAL_WIF)
    else:
        from bitcash import Key
        key = Key(config.BCH_OPERATIONAL_WIF)
    try:
        return Decimal(key.get_balance("bch"))
    except Exception as e:
        print(f"[BCH] Operational balance check failed: {e}")
        return None


def send_bch(to_address, amount_bch):
    """
    Send BCH from the operational wallet to to_address.
    Returns tx_hash string on success, raises on failure.
    """
    if not config.BCH_OPERATIONAL_WIF:
        raise RuntimeError("BCH_OPERATIONAL_WIF not set in config.py")
    if config.TESTNET:
        from bitcash import PrivateKeyTestnet
        key = PrivateKeyTestnet(config.BCH_OPERATIONAL_WIF)
    else:
        from bitcash import Key
        key = Key(config.BCH_OPERATIONAL_WIF)
    outputs = [(to_address, float(amount_bch), "bch")]
    tx_hash = key.send(outputs)
    return tx_hash


def sweep_deposit(deposit_wif, to_address):
    """
    Send ALL BCH from a deposit address to to_address.
    Used for BCH→XMR swaps: we collect the deposited BCH.
    Returns tx_hash string.
    """
    if config.TESTNET:
        from bitcash import PrivateKeyTestnet
        key = PrivateKeyTestnet(deposit_wif)
    else:
        from bitcash import Key
        key = Key(deposit_wif)
    # Send everything (empty outputs = send all to single address)
    tx_hash = key.send([], leftover=to_address)
    return tx_hash
