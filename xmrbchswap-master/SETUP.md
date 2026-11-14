# XMRTo.Cash — Setup Guide

A simple BCH ↔ XMR swap service. Run everything locally to test before deploying.

---

## Requirements

- Python 3.8+
- `monero-wallet-rpc` binary (from the Monero CLI tools)

---

## Step 1 — Install Python Dependencies

```bash
cd xmrbchswap-master
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Step 1.5 — Configure Environment Variables

Create your local environment file from the template:

```bash
cp .env.example .env
```

Then edit `.env` and set values for your environment (especially secrets like
`DJANGO_SECRET_KEY` and `BCH_OPERATIONAL_WIF`).

Before running Django/monitor commands, load the variables in your shell:

```bash
set -a
source .env
set +a
```

---

## Step 2 — Generate Your BCH Operational Wallet

This is the wallet that holds your BCH inventory (used to pay users who send XMR).

```bash
python manage.py generate_wallets
```

Copy the printed WIF key and set it in `.env`:
```bash
# in .env
BCH_OPERATIONAL_WIF="your_wif_key_here"
```

Then fund this BCH address with some BCH (or testnet BCH if TESTNET=True).

---

## Step 3 — Set Up the Monero Wallet

### A. Download Monero CLI Tools
Go to https://www.getmonero.org/downloads/ and download the CLI tools for your OS.
Extract and make sure `monero-wallet-rpc` and `monero-wallet-cli` are in your PATH.

### B. Create a New Wallet (first time only)
```bash
# Stagenet (testing):
monero-wallet-cli --stagenet --generate-new-wallet xmr_wallet

# Mainnet (real money):
monero-wallet-cli --generate-new-wallet xmr_wallet
```
Write down the seed phrase — you will need it to recover funds.

### C. Start the Wallet RPC
```bash
./start_xmr_wallet.sh
```
Leave this running in its own terminal. It connects to a public remote node so you
don't need to sync the entire blockchain.

### D. Fund the XMR Wallet
Send some XMR (or stagenet XMR) to the wallet's primary address.
You can find your address by running:
```bash
monero-wallet-cli --stagenet --wallet-file xmr_wallet
# then type: address
```

---

## Step 4 — Configure Settings

Open `.env` and verify:
- `TESTNET=true` for testing, `false` for real money
- `BCH_OPERATIONAL_WIF` is set
- `XMR_RPC_HOST` / `XMR_RPC_PORT` match your wallet RPC settings
- `FEE_PERCENT=5.0` (adjust as desired)

---

## Step 5 — Set Up the Database

Delete any old database and run fresh migrations:
```bash
rm -f db.sqlite3
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin panel
```

---

## Step 6 — Run the Application

You need **three terminals** running simultaneously:

**Terminal 1 — XMR Wallet RPC:**
```bash
./start_xmr_wallet.sh
```

**Terminal 2 — Django Web Server:**
```bash
python manage.py runserver
```
Visit http://localhost:8000 in your browser.

**Terminal 3 — Deposit Monitor:**
```bash
python manage.py monitor
```
This checks for incoming deposits every 30 seconds and executes swaps automatically.

---

## Transaction Log

Every swap is recorded to `transactions_log.json` (JSON Lines format).
Each line is a JSON event: `swap_created`, `deposit_received`, `swap_complete`, or `swap_failed`.

View recent activity:
```bash
tail -f transactions_log.json | python -m json.tool
```

---

## Admin Panel

Visit http://localhost:8000/admin/ to view and manage all swaps in the database.

---

## Running Tests (Simple)

Run the backend tests with:

```bash
cd xmrbchswap-master
pytest
```

These tests mock external BCH/XMR/rate calls, so they are safe to run in test/dev
without moving real funds.

---

## Getting Testnet Coins

**BCH testnet:**
Search for "BCH testnet faucet" — several free faucets exist.

**XMR stagenet:**
Ask in the #monero-stagenet IRC channel or the Monero subreddit.
The stagenet community.xmr.to node may have a faucet endpoint.

---

## Switching to Mainnet

1. Set `TESTNET=false` in `.env`
2. Generate a new mainnet BCH wallet: `python manage.py generate_wallets`
3. Edit `start_xmr_wallet.sh` — comment out the stagenet lines, uncomment mainnet lines
4. Create/restore a mainnet XMR wallet
5. Fund both wallets with real BCH and XMR
6. Run everything as above

**Warning:** With TESTNET=False you are handling real money. Protect your WIF keys and
seed phrases. Never commit them to version control.
