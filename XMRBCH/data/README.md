Runtime data lives here and is never committed:

- `db.sqlite3`               swap database (contains BCH deposit private keys!)
- `xmr_wallet`, `xmr_wallet.keys`  Monero wallet (the default XMR_WALLET_FILE)
- `transactions_log.jsonl`   JSON Lines log of every swap event
- `secret_key`               Django secret key (auto-generated)
- `staticfiles/`             collected static files
- `monero-wallet-rpc.log`

Back this folder up. Losing it loses access to funds.
