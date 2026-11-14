#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# XMRTo.Cash installer. Safe to re-run any time (e.g. after copying new code).
#
#   ./install.sh          set up venv + database (no root needed)
#   sudo ./install.sh     ...and install/restart the three systemd services:
#                           xmrbch-web      website (gunicorn on 127.0.0.1:WEB_PORT)
#                           xmrbch-monitor  deposit watcher / payout worker
#                           xmrbch-wallet   monero-wallet-rpc
# ─────────────────────────────────────────────────────────────────────────────
set -e
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$APP_DIR"

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*"; }
ask()  { local a; read -r -p "$1 [y/N] " a </dev/tty || true; [[ "$a" =~ ^[Yy] ]]; }

IS_ROOT=0; [ "$(id -u)" = 0 ] && IS_ROOT=1
APP_USER="$(stat -c %U "$APP_DIR")"   # services run as the folder's owner
as_user() { if [ $IS_ROOT = 1 ] && [ "$APP_USER" != root ]; then sudo -u "$APP_USER" -- "$@"; else "$@"; fi; }

# ── 1. Python environment ────────────────────────────────────────────────────
command -v python3 >/dev/null || { echo "python3 is required (apt install python3 python3-venv)"; exit 1; }
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import sys' 2>/dev/null; then
    say "Creating Python virtualenv in .venv"
    rm -rf .venv
    as_user python3 -m venv .venv || { echo "Failed — try: apt install python3-venv"; exit 1; }
fi
say "Installing Python packages"
as_user .venv/bin/pip install -q --upgrade pip
as_user .venv/bin/pip install -q -r requirements.txt

# ── 2. Config ────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    as_user cp .env.example .env
    warn "Created .env from .env.example (TESTNET mode). Edit it, then re-run this script."
fi
as_user mkdir -p data
chmod 700 data; chmod 600 .env
set -a; . ./.env; set +a
WEB_PORT="${WEB_PORT:-8077}"
URL_PREFIX="${URL_PREFIX-XMRBCH}"

# Keep .htaccess pointing at the right port
sed -i "s#http://127.0.0.1:[0-9]*%{REQUEST_URI}#http://127.0.0.1:${WEB_PORT}%{REQUEST_URI}#" .htaccess
[ $IS_ROOT = 1 ] && chown "$APP_USER" .htaccess

if [ -n "$URL_PREFIX" ] && [ "$(basename "$APP_DIR")" != "$URL_PREFIX" ]; then
    warn "Folder is named '$(basename "$APP_DIR")' but URL_PREFIX=$URL_PREFIX."
    warn "If you use the public_html/.htaccess setup they must match."
fi

# ── 3. Database + static files ───────────────────────────────────────────────
say "Migrating database"
as_user .venv/bin/python manage.py migrate --noinput
as_user .venv/bin/python manage.py collectstatic --noinput -v 0

if [ -z "$BCH_OPERATIONAL_WIF" ]; then
    warn "BCH_OPERATIONAL_WIF is empty. Create one with:  .venv/bin/python manage.py generate_wallets"
fi

# ── 4. Monero CLI tools ──────────────────────────────────────────────────────
if [ ! -x bin/monero-wallet-rpc ] && ! command -v monero-wallet-rpc >/dev/null; then
    warn "monero-wallet-rpc not found."
    if ask "Download the official Monero CLI tools into ./bin?"; then
        case "$(uname -m)" in
            x86_64)  PLATFORM=linux64 ;;
            aarch64) PLATFORM=linuxarm8 ;;
            *) echo "Unsupported CPU $(uname -m); install Monero CLI manually."; exit 1 ;;
        esac
        TMP="$(mktemp -d)"
        URL="$(curl -sIL -o /dev/null -w '%{url_effective}' "https://downloads.getmonero.org/cli/$PLATFORM")"
        FILE="$(basename "$URL")"
        say "Downloading $FILE"
        curl -fL --progress-bar -o "$TMP/$FILE" "$URL"
        curl -fsSL -o "$TMP/hashes.txt" https://www.getmonero.org/downloads/hashes.txt
        EXPECTED="$(grep -E " $FILE\$" "$TMP/hashes.txt" | awk '{print $1}')"
        ACTUAL="$(sha256sum "$TMP/$FILE" | awk '{print $1}')"
        if [ -z "$EXPECTED" ] || [ "$EXPECTED" != "$ACTUAL" ]; then
            echo "SHA256 mismatch for $FILE — aborting."; rm -rf "$TMP"; exit 1
        fi
        say "Checksum OK"
        as_user mkdir -p bin
        tar -xjf "$TMP/$FILE" -C "$TMP"
        cp "$TMP"/monero-*/monero-wallet-rpc "$TMP"/monero-*/monero-wallet-cli bin/
        chown -R "$APP_USER" bin
        rm -rf "$TMP"
    fi
fi
if [ ! -f "${XMR_WALLET_FILE:-data/xmr_wallet}.keys" ]; then
    NET=""; case "$(echo "${TESTNET:-true}" | tr '[:upper:]' '[:lower:]')" in 1|true|yes|on) NET="--stagenet ";; esac
    CLI="./bin/monero-wallet-cli"; [ -x "$CLI" ] || CLI="monero-wallet-cli"
    warn "No Monero wallet yet. Create one (write down the seed!):"
    warn "  $CLI ${NET}--generate-new-wallet ${XMR_WALLET_FILE:-data/xmr_wallet}"
    warn "then put its password in .env as XMR_WALLET_PASSWORD and re-run this script."
fi

# ── 5. systemd services ──────────────────────────────────────────────────────
if [ $IS_ROOT = 1 ] && command -v systemctl >/dev/null; then
    say "Installing systemd services (running as user '$APP_USER')"
    [ "$APP_USER" = root ] && warn "Services will run as root. Better: chown the folder to a normal user and re-run."
    for unit in deploy/*.service; do
        sed -e "s#@APP_DIR@#$APP_DIR#g" -e "s#@APP_USER@#$APP_USER#g" -e "s#@WEB_PORT@#$WEB_PORT#g" \
            "$unit" > "/etc/systemd/system/$(basename "$unit")"
    done
    systemctl daemon-reload
    systemctl enable -q xmrbch-wallet xmrbch-web xmrbch-monitor
    systemctl restart xmrbch-wallet xmrbch-web xmrbch-monitor
    sleep 2
    systemctl --no-pager --lines=0 status xmrbch-wallet xmrbch-web xmrbch-monitor | grep -E "●|Active:" || true

    # Apache: make sure the modules the .htaccess needs are on
    if command -v apache2ctl >/dev/null && command -v a2enmod >/dev/null; then
        MISSING=""
        for m in rewrite proxy proxy_http headers; do
            apache2ctl -M 2>/dev/null | grep -q " ${m}_module" || MISSING="$MISSING $m"
        done
        if [ -n "$MISSING" ] && ask "Enable Apache modules:$MISSING (and reload Apache)?"; then
            a2enmod -q $MISSING && systemctl reload apache2
        fi
    fi
else
    warn "Not root: skipped systemd. To run by hand (3 terminals):"
    echo "    ./start_xmr_wallet.sh"
    echo "    .venv/bin/gunicorn -b 127.0.0.1:$WEB_PORT xmrbchswap.wsgi:application"
    echo "    .venv/bin/python manage.py monitor"
fi

# ── 6. Web server ────────────────────────────────────────────────────────────
P="/${URL_PREFIX}"
cat <<EOF

────────────────────────────────────────────────────────────────────────────
 App is listening on http://127.0.0.1:$WEB_PORT$P/

 Apache, folder inside public_html:  nothing to do — the .htaccess forwards
   requests (needs AllowOverride All + modules rewrite proxy proxy_http headers).

 Apache, folder elsewhere — add to your site's VirtualHost:
     ProxyPass        $P http://127.0.0.1:$WEB_PORT$P
     ProxyPassReverse $P http://127.0.0.1:$WEB_PORT$P
     RequestHeader set X-Forwarded-Proto "https"

 nginx — add to your server { } block:
     location $P/ {
         proxy_pass http://127.0.0.1:$WEB_PORT;
         proxy_set_header Host \$host;
         proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
         proxy_set_header X-Forwarded-Proto \$scheme;
     }

 Admin panel: https://yourdomain.com$P/admin/
   create a login with:  .venv/bin/python manage.py createsuperuser
────────────────────────────────────────────────────────────────────────────
EOF
