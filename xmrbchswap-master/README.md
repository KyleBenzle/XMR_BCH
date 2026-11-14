# XMRTo.Cash (BCH ↔ XMR Swap)

A lightweight Django service for non-custodial-style BCH/XMR swaps:
- User creates a swap order in the web UI.
- Service generates a one-time deposit address.
- Background monitor detects deposit and sends payout.
- UI polls swap status until complete.

This repository is designed for local/mainnet testing first, then VPS deployment.

## Important Safety Notes

- This project handles real crypto funds on mainnet.
- Never commit secrets (`.env`, WIF keys, wallet seeds, wallet files).
- Never commit Monero wallet files (`xmr_wallet`, `xmr_wallet.keys`).
- Use small test amounts first.
- Keep hot wallet balances limited.

## Stack

- Backend: Django 4.2
- Frontend: Django template + static JS/CSS
- DB: SQLite
- BCH: `bitcash` + Blockchair API
- XMR: `monero-wallet-rpc` JSON-RPC
- Rates: CoinGecko
- Worker: Django management command (`monitor`)

## Project Structure

```text
xmrbchswap-master/
├─ main/
│  ├─ management/commands/
│  │  ├─ monitor.py            # swap execution worker
│  │  └─ generate_wallets.py   # BCH wallet generator
│  ├─ static/main/
│  │  ├─ app.js                # frontend logic
│  │  ├─ index.css             # frontend styles
│  │  ├─ BCHQR.png             # donation BCH QR
│  │  └─ XMRQR.png             # donation XMR QR
│  ├─ templates/index.html     # single-page UI
│  ├─ utils/
│  │  ├─ bch.py                # BCH helpers
│  │  ├─ xmr.py                # Monero RPC helpers
│  │  ├─ rates.py              # CoinGecko pricing
│  │  └─ logger.py             # JSON lines transaction log
│  ├─ models.py                # Swap model/state
│  └─ views.py                 # API + home view
├─ xmrbchswap/
│  ├─ settings.py
│  └─ urls.py
├─ config.py                   # app config from env vars
├─ start_xmr_wallet.sh         # starts monero-wallet-rpc
├─ SETUP.md                    # concise setup guide
└─ README.md
```

## How It Works

1. User opens `/`.
2. Frontend requests `GET /api/rates/` (price + wallet balances).
3. User submits swap (`POST /api/swap/init/`).
4. Backend creates `Swap` row and returns deposit instructions.
5. `monitor` loop checks pending swaps.
6. On valid deposit:
   - marks `received`
   - calculates payout amount
   - sends output asset
   - marks `complete` (or `failed`)
7. Frontend polls `GET /api/swap/<swap_id>/` for status updates.

## Swap States

- `pending`
- `received`
- `sending`
- `complete`
- `expired`
- `failed`

## API Endpoints

- `GET /api/rates/`
  - Returns BCH/XMR prices and wallet balances
  - Includes `xmr_locked_balance` when unlocked funds are temporarily zero

- `POST /api/swap/init/`
  - Body:
    ```json
    {
      "direction": "bch_to_xmr",
      "amount": "0.01",
      "receiving_address": "..."
    }
    ```

- `GET /api/swap/<swap_id>/`
  - Returns status, tx hashes, timestamps, amounts

## Local Setup (Quick Start)

### 1) Install dependencies

```bash
cd xmrbchswap-master
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2) Configure env

```bash
cp .env.example .env
```

Edit `.env` values for your network:
- test mode:
  - `TESTNET=true`
  - `XMR_NETWORK=stagenet`
- mainnet:
  - `TESTNET=false`
  - `XMR_NETWORK=mainnet`

Load env:
```bash
set -a
source .env
set +a
```

### 3) Generate BCH operational wallet

```bash
python3 -m django generate_wallets --settings=xmrbchswap.settings
```

Copy generated WIF into `.env`:
```env
BCH_OPERATIONAL_WIF=...
```

### 4) Create/restore Monero wallet file

Create:
```bash
monero-wallet-cli --generate-new-wallet ./xmr_wallet
```

or restore:
```bash
monero-wallet-cli --restore-deterministic-wallet --wallet-file ./xmr_wallet
```

### 5) Start Monero wallet RPC

```bash
./start_xmr_wallet.sh
```

If the configured remote node is unavailable, edit `DAEMON_ADDRESS` in `start_xmr_wallet.sh`.

### 6) Run DB migrations + app

```bash
python3 -m django migrate --settings=xmrbchswap.settings
python3 -m django runserver --settings=xmrbchswap.settings
```

### 7) Start monitor worker (separate terminal)

```bash
python3 -m django monitor --settings=xmrbchswap.settings
```

## Mainnet Checklist

- Fresh production BCH WIF and fresh production XMR seed.
- `.env` configured for `TESTNET=false`, `XMR_NETWORK=mainnet`.
- Wallet RPC stable and connected to a reachable daemon.
- BCH and XMR operational wallets funded with small float.
- Start with tiny live swap amounts.
- Keep backups of WIF/seed offline.

## Donation Section

The homepage includes a `DONATE FUNDS` section with BCH/XMR donation addresses and QR images:
- `main/static/main/BCHQR.png`
- `main/static/main/XMRQR.png`

## Logging

Events are appended to `transactions_log.json` (JSON lines):
- `swap_created`
- `deposit_received`
- `swap_complete`
- `swap_failed`

Tail logs:
```bash
tail -f transactions_log.json
```

## Testing

```bash
pytest
```

## Troubleshooting

### `python manage.py` fails

This repo runs commands via module form:
```bash
python3 -m django <command> --settings=xmrbchswap.settings
```

### `xmr_wallet.keys is opened by another wallet program`

Another Monero process holds the wallet lock. Stop other wallet processes before starting RPC.

### `Wallet initialization failed: invalid password`

`WALLET_PASSWORD` in `start_xmr_wallet.sh` does not match wallet password.

### `no connection to daemon`

Configured remote node is unreachable. Use a working daemon endpoint or local `monerod`.

### XMR max shows `0` after a payout

Funds can be temporarily locked by Monero. Check:
- `balance` (total)
- `unlocked_balance` (spendable)
- `blocks_to_unlock`

## Deployment

See:
- `deploy/DEPLOY_MAINNET.md`
- `deploy/gunicorn.service`
- `deploy/nginx.conf`
- `deploy/monitor.service`

## Publishing to GitHub (Safe)

Before push, verify no secrets are staged:

```bash
git status
git diff -- .env xmr_wallet xmr_wallet.keys monero-wallet-rpc.log monero-wallet-cli.log
```

Then push:

```bash
git add README.md .gitignore main/ xmrbchswap/ config.py start_xmr_wallet.sh requirements.txt requirements-dev.txt SETUP.md deploy/ pytest.ini
git commit -m "Docs: add detailed README and deployment-safe repo hygiene"
git push origin main
```

If you only want selected files, stage explicitly by path.
