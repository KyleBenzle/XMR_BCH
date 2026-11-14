# XMRTo.Cash — BCH ↔ XMR swap

A small, self-contained swap service. A user picks a direction, gets a one-time
deposit address, sends coins, and the service pays out the other coin at spot
price minus a fee (default 5%).

Everything lives in this one folder. Copy it to a server, run `install.sh`, and
it runs at `https://yourdomain.com/XMRBCH/`.

## Install on a VPS (Ubuntu/Debian)

```bash
# 1. Copy this folder to the server, e.g. into your site's public_html
scp -r XMRBCH user@server:/var/www/yourdomain/public_html/

# 2. On the server
cd /var/www/yourdomain/public_html/XMRBCH
sudo ./install.sh        # creates .env (testnet), venv, DB; offers to download Monero CLI
nano .env                # set domain, BCH_OPERATIONAL_WIF, XMR_WALLET_PASSWORD, ...
sudo ./install.sh        # re-run: installs + starts the 3 services
```

`install.sh` is safe to re-run. Do it after every config change or code update.

**Web server:**
- **Apache with the folder inside `public_html`:** nothing to configure. The included
  `.htaccess` forwards `/XMRBCH/*` to the app and blocks direct access to every file
  in the folder. It needs `AllowOverride All` and the modules
  `rewrite proxy proxy_http headers` (install.sh offers to enable them).
- **Folder elsewhere, or nginx:** `install.sh` prints the 3–5 lines to paste into
  your site config.

**First-time wallets:**
```bash
.venv/bin/python manage.py generate_wallets                          # BCH → put WIF in .env
./bin/monero-wallet-cli --stagenet --generate-new-wallet data/xmr_wallet   # XMR (drop --stagenet for mainnet)
```
Write down the Monero seed and keep a copy of the WIF offline. Then fund both wallets.

**Going live (mainnet):** in `.env` set `TESTNET=false`, use a *mainnet* WIF and a
*mainnet* XMR wallet, then `sudo ./install.sh`. Start with tiny amounts.

## Services

| Service          | What it does                                        |
|------------------|-----------------------------------------------------|
| `xmrbch-web`     | Website + API (gunicorn on `127.0.0.1:WEB_PORT`)    |
| `xmrbch-monitor` | Watches deposits, sends payouts, sweeps BCH         |
| `xmrbch-wallet`  | `monero-wallet-rpc`, bound to localhost only        |

```bash
sudo systemctl restart xmrbch-web xmrbch-monitor xmrbch-wallet
journalctl -u xmrbch-monitor -f          # watch swaps happen
tail -f data/transactions_log.jsonl      # permanent event log
```

Admin panel: `/XMRBCH/admin/` (create a login with `.venv/bin/python manage.py createsuperuser`).

## How a swap flows

```
pending ─▶ confirming ─▶ received ─▶ sending ─▶ complete
   └─▶ expired (late deposits within 7 days are still paid)        └─▶ failed
```

1. `POST /api/swap/init/` validates the receiving address and checks that the
   wallet can cover the payout. It then creates a deposit address: a fresh BCH key,
   or a new XMR subaddress. The order number looks like `20260221073544_md6mn9`.
2. The monitor sees the deposit (`confirming`) and waits for
   `BCH_MIN_CONFIRMATIONS` or `XMR_MIN_CONFIRMATIONS`.
3. It pays out `received × current rate × (1 − fee)`. If the wallet is short (or the
   XMR is temporarily locked), the swap waits in `received` and retries. It doesn't fail.
4. For BCH→XMR, the deposit is then swept into the operational BCH wallet, so
   BCH from XMR buyers funds payouts to BCH buyers.

The UI keeps the swap in the URL (`#swap=…`), so users can reload or bookmark it.

### Safety rules
- Status changes that move money are compare-and-swap updates, and only one
  monitor can run at a time (file lock). A swap can't be paid twice.
- If the monitor dies mid-send, that swap becomes `failed` with a note. Check the
  wallet for the outgoing transaction, then set the status back to `received` in
  admin to retry.
- `failed` swaps are never swept. Their deposits may need a manual refund.
- Leftover BCH on old deposit addresses: `.venv/bin/python manage.py sweep_deposits`
  shows a dry run. Add `--execute` to send.

## Files

```
XMRBCH/
├─ .env.example, .env        configuration (only file you edit)
├─ .htaccess                 Apache: proxy to app, hide all files
├─ install.sh                setup / update / systemd
├─ start_xmr_wallet.sh       launches monero-wallet-rpc from .env
├─ manage.py, config.py
├─ data/                     DB, wallet, logs, secret key — BACK THIS UP, never commit
├─ deploy/*.service          systemd templates (filled in by install.sh)
├─ xmrbchswap/               Django settings / urls / wsgi
└─ main/
   ├─ swaps.py               the swap state machine (monitor logic)
   ├─ views.py               API
   ├─ utils/                 bch.py, xmr.py, rates.py, logger.py
   ├─ management/commands/   monitor, sweep_deposits, generate_wallets
   ├─ templates/index.html, static/main/   frontend
   └─ tests.py
```

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
DJANGO_DEBUG=true .venv/bin/python manage.py runserver   # http://localhost:8000/XMRBCH/
```

## Security notes
- `data/db.sqlite3` contains the private keys of BCH deposit addresses, and
  `data/xmr_wallet*` is the hot wallet. Keep server access tight, and keep only a
  working float in the hot wallets.
- gunicorn and wallet-rpc listen on 127.0.0.1 only.
- Swap creation is rate-limited per IP (`SWAPS_PER_IP_PER_HOUR`).
