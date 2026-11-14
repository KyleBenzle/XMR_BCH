#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# XMRTo.Cash — Start Monero Wallet RPC
#
# Requirements: Download the Monero CLI tools from https://www.getmonero.org/downloads/
# and place 'monero-wallet-rpc' in your PATH or the same directory as this script.
#
# First-time setup:
#   1. Create a wallet:
#        monero-wallet-cli --stagenet --generate-new-wallet xmr_wallet
#      (remove --stagenet for mainnet — real money!)
#   2. Note down the seed phrase in a safe place.
#   3. Run this script to start the RPC daemon.
# ─────────────────────────────────────────────────────────────────────────────

WALLET_FILE="./xmr_wallet"        # Path to wallet file (no extension)
WALLET_PASSWORD="xmrPowermessage84!"                 # Wallet password (empty = no password)
RPC_PORT=18083                     # Must match XMR_RPC_PORT in config.py
XMR_NETWORK="${XMR_NETWORK:-stagenet}"  # stagenet (default) or mainnet

# ── Network selection ─────────────────────────────────────────────────────────
if [ "$XMR_NETWORK" = "mainnet" ]; then
    NETWORK_FLAG=""
    DAEMON_ADDRESS="xmr-node.cakewallet.com:18081"
else
    NETWORK_FLAG="--stagenet"
    DAEMON_ADDRESS="stagenet.community.xmr.to:38081"
fi

# ─────────────────────────────────────────────────────────────────────────────
echo "======================================"
echo " XMRTo.Cash — Monero Wallet RPC"
echo "======================================"
echo " Network : ${NETWORK_FLAG:-mainnet}"
echo " Wallet  : $WALLET_FILE"
echo " Port    : $RPC_PORT"
echo " Daemon  : $DAEMON_ADDRESS"
echo "======================================"
echo ""

monero-wallet-rpc \
    $NETWORK_FLAG \
    --wallet-file "$WALLET_FILE" \
    --password "$WALLET_PASSWORD" \
    --rpc-bind-port "$RPC_PORT" \
    --rpc-bind-ip "127.0.0.1" \
    --daemon-address "$DAEMON_ADDRESS" \
    --trusted-daemon \
    --log-level 1 \
    --disable-rpc-login
