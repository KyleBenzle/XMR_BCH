#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# XMRTo.Cash — Start Monero Wallet RPC
#
# All settings come from .env (TESTNET, XMR_WALLET_FILE, XMR_WALLET_PASSWORD,
# XMR_DAEMON_ADDRESS, XMR_RPC_PORT, XMR_RPC_USER/PASS).
# Runs as the xmrbch-wallet systemd service; you can also run it by hand.
#
# First-time wallet creation (stagenet shown; drop --stagenet for mainnet):
#   monero-wallet-cli --stagenet --generate-new-wallet data/xmr_wallet
# ─────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$(readlink -f "$0")")"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

WALLET_FILE="${XMR_WALLET_FILE:-data/xmr_wallet}"
RPC_PORT="${XMR_RPC_PORT:-18083}"

case "$(echo "${TESTNET:-true}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
        NETWORK_FLAG="--stagenet"
        DAEMON_ADDRESS="${XMR_DAEMON_ADDRESS:-stagenet.xmr-tw.org:38081}" ;;
    *)
        NETWORK_FLAG=""
        DAEMON_ADDRESS="${XMR_DAEMON_ADDRESS:-xmr-node.cakewallet.com:18081}" ;;
esac

# Only fully trust a daemon running on this machine
case "$DAEMON_ADDRESS" in
    127.0.0.1:*|localhost:*) TRUST_FLAG="--trusted-daemon" ;;
    *)                       TRUST_FLAG="--untrusted-daemon" ;;
esac

if [ -n "$XMR_RPC_USER" ]; then
    LOGIN_ARGS=(--rpc-login "$XMR_RPC_USER:$XMR_RPC_PASS")
else
    LOGIN_ARGS=(--disable-rpc-login)
fi

# Prefer a bundled binary in ./bin (install.sh can download it), else PATH
RPC_BIN="./bin/monero-wallet-rpc"
[ -x "$RPC_BIN" ] || RPC_BIN="$(command -v monero-wallet-rpc || true)"
if [ -z "$RPC_BIN" ]; then
    echo "monero-wallet-rpc not found. Run ./install.sh or install the Monero CLI tools." >&2
    exit 1
fi
if [ ! -f "$WALLET_FILE.keys" ]; then
    echo "Wallet '$WALLET_FILE' not found. Create it with:" >&2
    echo "  ${RPC_BIN%-rpc}-cli $NETWORK_FLAG --generate-new-wallet $WALLET_FILE" >&2
    exit 1
fi

echo "Monero wallet RPC: network=${NETWORK_FLAG:-mainnet} wallet=$WALLET_FILE port=$RPC_PORT daemon=$DAEMON_ADDRESS"

exec "$RPC_BIN" \
    $NETWORK_FLAG \
    --wallet-file "$WALLET_FILE" \
    --password "$XMR_WALLET_PASSWORD" \
    --rpc-bind-ip 127.0.0.1 \
    --rpc-bind-port "$RPC_PORT" \
    --daemon-address "$DAEMON_ADDRESS" \
    $TRUST_FLAG \
    --log-file data/monero-wallet-rpc.log \
    --max-log-file-size 10000000 \
    --max-log-files 3 \
    --log-level 0 \
    "${LOGIN_ARGS[@]}"
