import os

# XMRTo.Cash - Application Configuration
# Prefer setting values via environment variables.


def _env_bool(name, default):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    val = os.environ.get(name)
    if val is None:
        return default
    return int(val)


def _env_float(name, default):
    val = os.environ.get(name)
    if val is None:
        return default
    return float(val)

# ── Network ──────────────────────────────────────────────────────────────────
# Set True for testing (no real money), False for mainnet (REAL MONEY)
TESTNET = _env_bool("TESTNET", True)

# ── BCH Operational Wallet ───────────────────────────────────────────────────
# YOUR BCH wallet used to PAY users who send you XMR.
# Run: python manage.py generate_wallets   to create one.
BCH_OPERATIONAL_WIF = os.environ.get("BCH_OPERATIONAL_WIF", "")

# ── Monero Wallet RPC ────────────────────────────────────────────────────────
# Run monero-wallet-rpc before starting the app. See start_xmr_wallet.sh
XMR_RPC_HOST = os.environ.get("XMR_RPC_HOST", "127.0.0.1")
XMR_RPC_PORT = _env_int("XMR_RPC_PORT", 18083)
XMR_RPC_USER = os.environ.get("XMR_RPC_USER", "")   # Leave empty if no auth configured
XMR_RPC_PASS = os.environ.get("XMR_RPC_PASS", "")   # Leave empty if no auth configured

# ── Exchange Settings ─────────────────────────────────────────────────────────
FEE_PERCENT = _env_float("FEE_PERCENT", 5.0)           # Service fee: user receives spot rate minus this %
MIN_BCH = _env_float("MIN_BCH", 0.001)                 # Minimum BCH swap amount
MIN_XMR = _env_float("MIN_XMR", 0.01)                  # Minimum XMR swap amount
SWAP_EXPIRY_HOURS = _env_int("SWAP_EXPIRY_HOURS", 24)  # Swaps expire after this many hours with no deposit

# ── Transaction Log ───────────────────────────────────────────────────────────
# Human-readable JSON log of all swaps (path relative to manage.py)
TRANSACTION_LOG_FILE = os.environ.get("TRANSACTION_LOG_FILE", "transactions_log.json")

# ── Deposit Monitor ───────────────────────────────────────────────────────────
MONITOR_INTERVAL_SECONDS = _env_int("MONITOR_INTERVAL_SECONDS", 30)   # How often to check for new deposits
# Minimum confirmations before processing (0 = unconfirmed, 1+ = confirmed)
BCH_MIN_CONFIRMATIONS = _env_int("BCH_MIN_CONFIRMATIONS", 1)
XMR_MIN_CONFIRMATIONS = _env_int("XMR_MIN_CONFIRMATIONS", 10)
