"""
Monero wallet utilities via monero-wallet-rpc JSON-RPC.

The app connects directly to a running monero-wallet-rpc process.
See start_xmr_wallet.sh for how to start the wallet daemon.

Amounts: monero-wallet-rpc uses atomic units (piconero = 1e-12 XMR).
"""
import requests
from decimal import Decimal
from requests.auth import HTTPDigestAuth
import config

PICONERO = Decimal("1e-12")


def _rpc(method, params=None):
    """Make a JSON-RPC call to monero-wallet-rpc."""
    url = f"http://{config.XMR_RPC_HOST}:{config.XMR_RPC_PORT}/json_rpc"
    payload = {"jsonrpc": "2.0", "id": "0", "method": method, "params": params or {}}
    kwargs = {"json": payload, "timeout": 15}
    if config.XMR_RPC_USER:
        kwargs["auth"] = HTTPDigestAuth(config.XMR_RPC_USER, config.XMR_RPC_PASS)
    resp = requests.post(url, **kwargs)
    if resp.status_code == 401:
        raise RuntimeError("XMR RPC: authentication failed (check XMR_RPC_USER/PASS)")
    resp.raise_for_status()
    result = resp.json()
    if "error" in result:
        raise RuntimeError(f"XMR RPC error: {result['error']['message']}")
    return result["result"]


def is_available():
    """Return True if the wallet RPC is reachable."""
    try:
        _rpc("get_version")
        return True
    except Exception:
        return False


def get_balances():
    """Return (unlocked, total) XMR balance of account 0 as Decimals."""
    result = _rpc("get_balance", {"account_index": 0})
    return (
        Decimal(result["unlocked_balance"]) * PICONERO,
        Decimal(result["balance"]) * PICONERO,
    )


def get_balance():
    """Return unlocked (spendable) XMR balance as Decimal."""
    return get_balances()[0]


def validate_address(address):
    """
    Raise ValueError if address is not a valid XMR address for the wallet's
    network. Returns the address unchanged when valid.
    """
    result = _rpc("validate_address", {"address": address.strip()})
    if not result.get("valid"):
        raise ValueError("Invalid XMR address for this network")
    return address.strip()


def create_deposit_address(label="deposit"):
    """
    Create a new subaddress in account 0.
    Returns (address_string, subaddress_index_int).
    """
    result = _rpc("create_address", {"account_index": 0, "label": label})
    return result["address"], result["address_index"]


def get_deposit(subaddress_index):
    """
    Return (confirmed_xmr, unconfirmed_xmr, latest_txid) received at a
    subaddress. "Confirmed" means >= XMR_MIN_CONFIRMATIONS; mempool and
    young transfers count as unconfirmed.
    """
    result = _rpc("get_transfers", {
        "in": True,
        "pool": True,
        "account_index": 0,
        "subaddr_indices": [subaddress_index],
    })
    transfers = result.get("in", []) + result.get("pool", [])
    confirmed = unconfirmed = 0
    for t in transfers:
        if t.get("confirmations", 0) >= config.XMR_MIN_CONFIRMATIONS:
            confirmed += t["amount"]
        else:
            unconfirmed += t["amount"]
    txid = transfers[-1]["txid"] if transfers else ""
    return Decimal(confirmed) * PICONERO, Decimal(unconfirmed) * PICONERO, txid


def send_xmr(to_address, amount_xmr):
    """
    Send XMR from the wallet to to_address.
    Returns tx_hash string on success, raises on failure.
    """
    amount_atomic = int((Decimal(str(amount_xmr)) / PICONERO).to_integral_value(rounding="ROUND_DOWN"))
    if amount_atomic <= 0:
        raise ValueError(f"Amount {amount_xmr} XMR is too small to send")
    result = _rpc("transfer", {
        "destinations": [{"amount": amount_atomic, "address": to_address}],
        "account_index": 0,
        "priority": 1,  # Normal priority
        "get_tx_key": True,
    })
    return result["tx_hash"]
