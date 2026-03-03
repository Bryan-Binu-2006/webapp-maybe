#!/usr/bin/env bash
# ============================================================================
# setup.sh — EC2 deployment setup script
# ============================================================================
# Run this script on a fresh Ubuntu EC2 instance to set up everything.
#
# Usage:
#   chmod +x deploy/setup.sh
#   sudo ./deploy/setup.sh
#
# WHAT THIS SCRIPT DOES:
# 1. Installs system packages (Python, PostgreSQL, Nginx)
# 2. Creates a PostgreSQL database and user
# 3. Sets up a Python virtual environment
# 4. Installs Python dependencies
# 5. Configures Nginx
# 6. Sets up the systemd service
# 7. Starts everything
#
# SECURITY NOTES:
# - The PostgreSQL password below is a PLACEHOLDER.  Change it!
# - After running this script, edit /etc/systemd/system/certissuer.service
#   and set a real SECRET_KEY and DATABASE_URL.
# ============================================================================

set -euo pipefail

# Required for HTTPS-ready deployment.
APP_DOMAIN="${APP_DOMAIN:-}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"

# App and DB defaults (can be overridden by env vars).
APP_DIR="${APP_DIR:-/home/ubuntu/certissuer}"
APP_USER="${APP_USER:-ubuntu}"
DB_NAME="${DB_NAME:-certapp}"
DB_USER="${DB_USER:-certapp}"
DB_PASSWORD="${DB_PASSWORD:-}"
SECRET_KEY="${SECRET_KEY:-}"

# t2.micro-friendly defaults.
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_THREADS="${GUNICORN_THREADS:-2}"

if [[ -z "$APP_DOMAIN" || -z "$LETSENCRYPT_EMAIL" ]]; then
    echo "ERROR: APP_DOMAIN and LETSENCRYPT_EMAIL are required."
    echo "Example:"
    echo "  sudo APP_DOMAIN=cert.example.com LETSENCRYPT_EMAIL=ops@example.com ./deploy/setup.sh"
    exit 1
fi

if [[ -z "$DB_PASSWORD" ]]; then
    DB_PASSWORD="$(openssl rand -base64 24 | tr -d '=+/' | cut -c1-24)"
fi

if [[ -z "$SECRET_KEY" ]]; then
    SECRET_KEY="$(openssl rand -hex 32)"
fi

echo "============================================"
echo "  CertIssuer — EC2 Setup Script"
echo "============================================"

# ── 1. Update system packages ──────────────────────────────────────
echo "[1/7] Updating system packages..."
apt-get update -y
apt-get upgrade -y

# ── 2. Install required system packages ────────────────────────────
echo "[2/7] Installing system packages..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    nginx \
    certbot \
    python3-certbot-nginx \
    libpq-dev \
    fonts-dejavu-core \
    openssl

# ── 3. Set up PostgreSQL database ──────────────────────────────────
echo "[3/7] Setting up PostgreSQL..."
sudo -u postgres psql <<SQL
DO
\$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
    ELSE
        ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
    END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
    sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"
fi

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

# ── 4. Set up application directory ────────────────────────────────
echo "[4/7] Setting up application..."
if [ ! -d "$APP_DIR" ]; then
    echo "ERROR: Please clone the repository to $APP_DIR first."
    echo "  git clone <your-repo-url> $APP_DIR"
    exit 1
fi

cd "$APP_DIR"

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create storage directories
mkdir -p storage uploads
chown -R "${APP_USER}:${APP_USER}" storage uploads

# ── 5. Write secure environment file ──────────────────────────────
echo "[5/7] Writing runtime environment..."
install -d -m 750 /etc/certissuer
cat >/etc/certissuer/certissuer.env <<EOF
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
STORAGE_DIR=${APP_DIR}/storage
UPLOAD_DIR=${APP_DIR}/uploads
SESSION_LIFETIME_MINUTES=30
SESSION_COOKIE_SECURE=True
GUNICORN_WORKERS=${GUNICORN_WORKERS}
GUNICORN_THREADS=${GUNICORN_THREADS}
GUNICORN_LOG_LEVEL=info
EOF
chmod 600 /etc/certissuer/certissuer.env

# ── 6. Configure Nginx ─────────────────────────────────────────────
echo "[6/7] Configuring Nginx..."
mkdir -p /var/www/certissuer/.well-known/acme-challenge
cp deploy/nginx.conf /etc/nginx/sites-available/certissuer
sed -i "s/your-domain.com/${APP_DOMAIN}/g" /etc/nginx/sites-available/certissuer
ln -sf /etc/nginx/sites-available/certissuer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# ── 7. Set up systemd service ──────────────────────────────────────
echo "[7/7] Setting up systemd service..."
cp deploy/certissuer.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable certissuer

# Obtain/renew certificate and update nginx with redirect handling.
echo "[TLS] Requesting Let's Encrypt certificate..."
certbot --nginx \
    --non-interactive \
    --agree-tos \
    -m "${LETSENCRYPT_EMAIL}" \
    -d "${APP_DOMAIN}" \
    --redirect

echo "[APP] Starting CertIssuer..."
systemctl restart certissuer
systemctl status certissuer --no-pager || true

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "Deployment completed for domain: ${APP_DOMAIN}"
echo "Environment file: /etc/certissuer/certissuer.env"
echo "Service logs: journalctl -u certissuer -f"
echo "Nginx logs: tail -f /var/log/nginx/error.log"
echo ""
