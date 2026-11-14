# XMR ↔ BCH Self-Hosted Mini-Swap

I became interested in swapping Monero (XMR) and Bitcoin Cash (BCH) in 2021 through an atomic-swap bounty. Since then, the idea has evolved into a different kind of self-hosted project: a small, open mini-swap that anyone can operate with their own wallets, their own liquidity, and their own domain.

The long-term goal is a turn-key package that a user can upload to a web host, open at an address such as `https://their-domain.example/XMRtoBCH/`, and configure without giving control of the wallets to an outside exchange. During setup, the operator should eventually be able to import existing BCH and XMR wallets or generate new wallets, receive the recovery information directly, back it up, fund both sides, and begin offering swaps.

This could be run publicly, privately, or simply for convenience. An individual or small community might use an instance to buy, sell, or trade between its own BCH and XMR liquidity while retaining access to both wallets. The aim is not to reproduce a large centralized exchange. It is to make a small, understandable, self-hosted swap service that is as open and portable as practical.

> **Development warning:** this is experimental software that controls hot-wallet funds. It has not been independently audited. Use testnet/stagenet first, keep only limited liquidity online, and do not use funds you cannot afford to lose.

## What exists today

The active implementation is in [`XMRBCH/`](XMRBCH/). It is a Django web application that:

- supports BCH → XMR and XMR → BCH orders;
- displays current rates and the operator's available wallet liquidity;
- gives each order a one-time BCH deposit address or an XMR subaddress;
- monitors incoming deposits and waits for configurable confirmations;
- pays the other asset from the operator-funded wallet;
- applies a configurable fee (5% by default);
- records order state, transaction IDs, and a JSON Lines event log;
- can run below a URL prefix such as `/XMRBCH/`; and
- includes an installer and systemd service templates for a Linux VPS.

This repository also contains `xmrbchswap-master/`, an older development snapshot kept for reference. New deployment and development work should use `XMRBCH/`.

## What this project is—and is not

This is currently an **operator-run hot-wallet swap service**. The person hosting it supplies and controls the BCH and XMR liquidity. A visitor sends one asset to an order-specific address, and the service sends the other asset to the visitor's chosen address.

It is **not currently a trustless atomic swap**. It does not use an atomic-swap protocol, multisignature escrow, or a cross-chain contract. During a swap, the visitor must trust the operator and the running software to make the payout. “Self-hosted” describes the operator's control of the service and keys; it does not make a public customer's trade non-custodial.

It is also not yet a static package that works on every `public_html` account. The current version needs Python, a persistent Django/Gunicorn process, a continuously running deposit monitor, `monero-wallet-rpc`, outbound API access, and permission to configure a reverse proxy. A VPS or hosting account with shell access and background-service support is therefore required today. Making installation truly upload-and-configure is a future goal.

## How a swap works

1. The operator funds the BCH operational wallet and the XMR wallet.
2. A visitor chooses BCH → XMR or XMR → BCH, enters an amount, and supplies a receiving address.
3. The app validates the receiving address, obtains a market rate, subtracts the configured fee, and checks available payout liquidity.
4. The app creates a unique deposit address and order number.
5. The background monitor detects the deposit and waits for the configured number of confirmations.
6. The app sends the calculated output amount and publishes the order status and transaction ID.
7. BCH received in BCH → XMR orders is swept back into the operational BCH wallet after a successful payout.

```text
pending → confirming → received → sending → complete
   └─→ expired                              └─→ failed
```

Orders that arrive shortly after expiry can still be processed within the configured grace period.

## Technical overview

| Component | Current implementation |
|---|---|
| Web application | Django 4.2 + Gunicorn |
| User interface | Django template, plain JavaScript, and CSS |
| Database | SQLite |
| BCH wallet operations | `bitcash`; one-time deposit keys and an operational payout wallet |
| BCH chain data | Blockchair API |
| XMR wallet operations | `monero-wallet-rpc` JSON-RPC and subaddresses |
| Market rates | CoinGecko |
| Swap worker | Django `monitor` management command |
| Production services | systemd units for web, monitor, and XMR wallet RPC |
| Event history | JSON Lines transaction log |

The public API currently consists of:

- `GET /api/rates/` — rates, limits, and available liquidity;
- `POST /api/swap/init/` — validate and create a swap order; and
- `GET /api/swap/<swap_id>/` — retrieve the latest order state.

## Repository layout

```text
.
├── XMRBCH/                    # active implementation
│   ├── install.sh             # repeatable VPS installer
│   ├── config.py              # environment-based configuration
│   ├── main/                  # models, API, monitor, wallet helpers, UI
│   ├── xmrbchswap/            # Django settings and routing
│   ├── deploy/                # systemd service templates
│   └── data/                  # runtime secrets/data; never commit
└── xmrbchswap-master/          # legacy snapshot; reference only
```

More detailed operating documentation is available in [`XMRBCH/README.md`](XMRBCH/README.md).

## Quick start on a Linux VPS

The safest first run uses BCH testnet and Monero stagenet.

```bash
cd XMRBCH
./install.sh
nano .env
./install.sh
```

The first run creates a Python environment, installs dependencies, initializes the database, and creates `.env` from `.env.example`. Follow the printed instructions to create or restore the wallets. When installed as system services, the application runs `xmrbch-web`, `xmrbch-monitor`, and `xmrbch-wallet`.

For an Apache site whose `XMRBCH` directory is inside `public_html`, the included `.htaccess` proxies requests to the application. Apache must allow `.htaccess` overrides and enable `rewrite`, `proxy`, `proxy_http`, and `headers`. nginx and nonstandard layouts require the reverse-proxy configuration printed by the installer.

Do not switch to mainnet until both directions have been tested end to end with valueless test coins. Mainnet setup requires fresh production wallets, `TESTNET=false`, secure offline backups, and a deliberately small initial float.

## Development

```bash
cd XMRBCH
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
DJANGO_DEBUG=true .venv/bin/python manage.py runserver
```

The development site is served at `http://localhost:8000/XMRBCH/` with the default URL prefix.

## Wallets, liquidity, and donations

The operator owns the two liquidity wallets and is responsible for their security, balances, backups, accounting, and legal use. The website reports spendable liquidity so it should not accept an order that the other wallet cannot cover.

Unsolicited funds sent directly to addresses explicitly published as donation or pool-contribution addresses may be treated as contributions to that operator's pool, but this policy must be clearly disclosed on each deployed site. Do **not** assume that an accidental payment to an order address is a donation: failed, late, duplicate, or incorrect deposits need a documented refund and support policy.

Donation addresses and QR codes must be configured by each operator. No contributor should assume that addresses included in a fork belong to them.

## Security and publishing checklist

Private keys, seeds, wallet files, databases, and production logs must never be committed or placed where the web server can serve them. In particular:

- keep `.env`, `data/`, `xmr_wallet*`, `*.keys`, `db.sqlite3`, and transaction logs out of Git;
- do not publish the legacy snapshot until it has been checked for wallet files, databases, logs, and other historical secrets;
- assume every key ever committed to Git or shared with an AI/tool is compromised and move funds to a newly generated wallet;
- encrypt offline backups of both wallet recovery secrets;
- bind Gunicorn and `monero-wallet-rpc` to localhost, with RPC authentication where appropriate;
- run services as an unprivileged user and restrict filesystem permissions;
- keep only the minimum practical hot-wallet float online;
- use HTTPS and production-safe Django host, CSRF, debug, and secret-key settings;
- monitor failed orders before retrying them, because blindly retrying a payout can lose funds; and
- obtain an independent security review before offering swaps to the public.

The application depends on external node/API availability and market data. An operator must plan for stale rates, chain reorganizations, locked XMR balances, API outages, partial deposits, transaction fees, and manual recovery.

## Roadmap

- Browser-based first-run setup wizard.
- Safe import or generation of both operator wallets with an explicit backup step.
- A simpler packaged installer for more hosting environments.
- Operator-configurable branding, URL path, fees, limits, and donation addresses.
- Clearer reserve, refund, maintenance, and out-of-liquidity behavior.
- Fewer centralized API dependencies and optional self-hosted chain backends.
- Stronger secret storage, audit logs, monitoring, and backup/restore tools.
- Automated integration tests for both swap directions.
- Research toward genuinely trust-minimized or atomic BCH/XMR exchange flows.

## Contributing

Bug reports, documentation improvements, test coverage, deployment work, security review, wallet-integration improvements, and careful protocol research are welcome. Please do not include live wallet material, personal data, or real transaction secrets in issues, commits, screenshots, or test fixtures.

## Legal notice

Running a swap service may create licensing, money-transmission, sanctions, tax, consumer-protection, privacy, or other obligations depending on the operator and jurisdiction. This repository is software, not legal or financial advice. Each operator is responsible for determining whether and how they may lawfully run it.

## License

No license file is currently included. Until a license is added, copyright law reserves the usual rights and the repository should not be described as open source in the formal licensing sense. Adding an explicit license is an important next step if broad reuse and contribution are intended.
