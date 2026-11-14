# Mainnet Deploy

## 1. Prepare app

```bash
cd /opt/xmrbchswap/xmrbchswap-master
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Edit `.env`:
- `TESTNET=false`
- `XMR_NETWORK=mainnet`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com`
- `DJANGO_SECRET_KEY=<strong-random-secret>`
- `BCH_OPERATIONAL_WIF=<mainnet-bch-wif>`

## 2. DB/static

```bash
. .venv/bin/activate
set -a && source .env && set +a
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

## 3. XMR wallet RPC (mainnet)

Create/restore wallet:

```bash
monero-wallet-cli --generate-new-wallet xmr_wallet
```

Start RPC:

```bash
set -a && source .env && set +a
./start_xmr_wallet.sh
```

Keep this running (or run it in a separate systemd service if you already have one).

## 4. Systemd services

Copy units:

```bash
sudo cp deploy/gunicorn.service /etc/systemd/system/xmrbchswap-gunicorn.service
sudo cp deploy/monitor.service /etc/systemd/system/xmrbchswap-monitor.service
```

Reload/start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xmrbchswap-gunicorn
sudo systemctl enable --now xmrbchswap-monitor
```

## 5. Nginx

Copy site config:

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/xmrbchswap
```

Edit `server_name` and paths if needed, then:

```bash
sudo ln -s /etc/nginx/sites-available/xmrbchswap /etc/nginx/sites-enabled/xmrbchswap
sudo nginx -t
sudo systemctl reload nginx
```

## 6. TLS (Let's Encrypt)

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

After TLS is active, set in `.env`:
- `DJANGO_SECURE_SSL_REDIRECT=true`
- `DJANGO_SECURE_HSTS_SECONDS=31536000`
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=true`
- `DJANGO_SECURE_HSTS_PRELOAD=true`

Then restart services:

```bash
sudo systemctl restart xmrbchswap-gunicorn xmrbchswap-monitor
```

## 7. Basic health checks

```bash
curl -I https://yourdomain.com/
curl https://yourdomain.com/api/rates/
sudo systemctl status xmrbchswap-gunicorn xmrbchswap-monitor
```
