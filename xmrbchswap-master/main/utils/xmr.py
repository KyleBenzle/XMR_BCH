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


def get_balance():
    """Return unlocked XMR balance as Decimal."""
    result = _rpc("get_balance", {"account_index": 0})
    return Decimal(result["unlocked_balance"]) * PICONERO


def get_total_balance():
    """Return total XMR balance (locked + unlocked) as Decimal."""
    result = _rpc("get_balance", {"account_index": 0})
    return Decimal(result["balance"]) * PICONERO


def create_deposit_address(label="deposit"):
    """
    Create a new subaddress in account 0.
    Returns (address_string, subaddress_index_int).
    """
    result = _rpc("create_address", {"account_index": 0, "label": label})
    return result["address"], result["address_index"]


def check_incoming(subaddress_index, min_amount_xmr=Decimal("0")):
    """
    Check if funds arrived at a specific subaddress.
    Returns (amount_xmr, txid) or (None, None) if nothing there yet.
    Only counts transfers with enough confirmations.
    """
    result = _rpc("get_transfers", {
        "in": True,
        "account_index": 0,
        "subaddr_indices": [subaddress_index],
        "filter_by_height": False,
    })
    transfers = result.get("in", [])
    # Filter by confirmations
    confirmed = [
        t for t in transfers
        if t.get("confirmations", 0) >= config.XMR_MIN_CONFIRMATIONS
    ]
    if not confirmed:
        return None, None

    total_atomic = sum(t["amount"] for t in confirmed)
    total_xmr = Decimal(total_atomic) * PICONERO
    if total_xmr < min_amount_xmr:
        return None, None

    latest_txid = confirmed[-1]["txid"]
    return total_xmr, latest_txid


def send_xmr(to_address, amount_xmr):
    """
    Send XMR from the wallet to to_address.
    Returns tx_hash string on success, raises on failure.
    """
    amount_atomic = int(Decimal(str(amount_xmr)) / PICONERO)
    result = _rpc("transfer", {
        "destinations": [{"amount": amount_atomic, "address": to_address}],
        "account_index": 0,
        "priority": 1,  # Normal priority
        "ring_size": 16,
        "get_tx_key": True,
    })
    return result["tx_hash"]
