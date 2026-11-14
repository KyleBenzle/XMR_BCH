"""
XMRTo.Cash - Application Configuration

All settings come from environment variables. On startup this file loads
`.env` from the project folder, so you never need to `source` it by hand.
Real environment variables win over values in `.env`.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")   # DB, wallet files, logs, secret key


def _load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            os.environ.setdefault(key, val)


_load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env_bool(name, default):
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    return int(val)


def _env_float(name, default):
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    return float(val)


# ── Network ──────────────────────────────────────────────────────────────────
# Set True for testing (no real money), False for mainnet (REAL MONEY)
TESTNET = _env_bool("TESTNET", True)

# ── Web ──────────────────────────────────────────────────────────────────────
# The site is served under https://yourdomain.com/<URL_PREFIX>/
# Set to empty to serve from the domain root.
URL_PREFIX = os.environ.get("URL_PREFIX", "XMRBCH").strip("/")
WEB_PORT = _env_int("WEB_PORT", 8077)     # gunicorn listens on 127.0.0.1:WEB_PORT

# ── BCH Operational Wallet ───────────────────────────────────────────────────
# YOUR BCH wallet used to PAY users who send you XMR. BCH deposits from
# BCH→XMR swaps are swept back into this wallet automatically.
# Run: python manage.py generate_wallets   to create one.
BCH_OPERATIONAL_WIF = os.environ.get("BCH_OPERATIONAL_WIF", "")

# ── Monero Wallet RPC ────────────────────────────────────────────────────────
# monero-wallet-rpc runs on the same server. See start_xmr_wallet.sh
XMR_RPC_HOST = os.environ.get("XMR_RPC_HOST", "127.0.0.1")
XMR_RPC_PORT = _env_int("XMR_RPC_PORT", 18083)
XMR_RPC_USER = os.environ.get("XMR_RPC_USER", "")   # Leave empty if no auth configured
XMR_RPC_PASS = os.environ.get("XMR_RPC_PASS", "")   # Leave empty if no auth configured

# ── Exchange Settings ─────────────────────────────────────────────────────────
FEE_PERCENT = _env_float("FEE_PERCENT", 5.0)           # Service fee: user receives spot rate minus this %
MIN_BCH = _env_float("MIN_BCH", 0.001)                 # Minimum BCH swap amount
MIN_XMR = _env_float("MIN_XMR", 0.01)                  # Minimum XMR swap amount
SWAP_EXPIRY_HOURS = _env_int("SWAP_EXPIRY_HOURS", 24)  # Swaps expire after this many hours with no deposit
# Deposits that arrive this long after a swap expired are still processed
LATE_DEPOSIT_GRACE_DAYS = _env_int("LATE_DEPOSIT_GRACE_DAYS", 7)
RATES_CACHE_SECONDS = _env_int("RATES_CACHE_SECONDS", 60)   # Avoid hammering CoinGecko
SWAPS_PER_IP_PER_HOUR = _env_int("SWAPS_PER_IP_PER_HOUR", 20)

# ── Transaction Log ───────────────────────────────────────────────────────────
# JSON Lines log of all swap events (relative paths are inside data/)
TRANSACTION_LOG_FILE = os.environ.get("TRANSACTION_LOG_FILE", "transactions_log.jsonl")

# ── Deposit Monitor ───────────────────────────────────────────────────────────
MONITOR_INTERVAL_SECONDS = _env_int("MONITOR_INTERVAL_SECONDS", 30)   # How often to check for new deposits
# Minimum confirmations before paying out (0 = unconfirmed, 1+ = confirmed)
BCH_MIN_CONFIRMATIONS = _env_int("BCH_MIN_CONFIRMATIONS", 1)
XMR_MIN_CONFIRMATIONS = _env_int("XMR_MIN_CONFIRMATIONS", 10)
