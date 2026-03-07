#!/bin/bash
# =============================================================================
# FaceDedup Server Setup Script
# Run this on a fresh Ubuntu 24.04 server as root or with sudo
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/surdykbaba/facededup/main/scripts/setup-server.sh | sudo bash
#   -- OR --
#   sudo bash scripts/setup-server.sh
# =============================================================================
set -euo pipefail

DEPLOY_USER="admin1"
DEPLOY_DIR="/home/${DEPLOY_USER}/facededup"
DOMAIN="face.ninauth.com"
REPO_URL="https://github.com/surdykbaba/facededup.git"

echo "=========================================="
echo "  FaceDedup Server Setup"
echo "  Server: $(hostname)"
echo "  OS:     $(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2)"
echo "  RAM:    $(free -h | awk '/^Mem:/{print $2}')"
echo "=========================================="
echo ""

# --- 1. System packages ---
echo "[1/7] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    fail2ban \
    certbot

# --- 2. Docker ---
echo "[2/7] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "  Docker installed: $(docker --version)"
else
    echo "  Docker already installed: $(docker --version)"
fi

# Add deploy user to docker group
usermod -aG docker "${DEPLOY_USER}" 2>/dev/null || true

# Docker Compose is included in modern Docker
echo "  Docker Compose: $(docker compose version 2>/dev/null || echo 'included in Docker')"

# --- 3. Firewall ---
echo "[3/7] Configuring firewall..."
ufw --force reset >/dev/null 2>&1 || true
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
echo "  Firewall configured (SSH, HTTP, HTTPS)"

# --- 4. Clone repo ---
echo "[4/7] Setting up repository..."
if [ -d "${DEPLOY_DIR}" ]; then
    echo "  Repository already exists at ${DEPLOY_DIR}"
    cd "${DEPLOY_DIR}"
    git fetch origin main
    git reset --hard origin/main
else
    git clone "${REPO_URL}" "${DEPLOY_DIR}"
    cd "${DEPLOY_DIR}"
fi
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${DEPLOY_DIR}"
echo "  Repository ready at ${DEPLOY_DIR}"

# --- 5. SSL Certificate ---
echo "[5/7] Setting up SSL certificate..."
if [ -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
    echo "  SSL certificate already exists for ${DOMAIN}"
else
    echo "  Requesting SSL certificate for ${DOMAIN}..."
    echo "  NOTE: Make sure DNS for ${DOMAIN} points to this server's IP first!"
    echo ""
    # Stop anything on port 80 temporarily
    docker compose -f docker-compose.prod.yaml down 2>/dev/null || true
    certbot certonly --standalone -d "${DOMAIN}" --non-interactive --agree-tos --email admin@ninauth.com || {
        echo ""
        echo "  WARNING: SSL certificate request failed."
        echo "  Make sure DNS for ${DOMAIN} points to this server, then run:"
        echo "    sudo certbot certonly --standalone -d ${DOMAIN}"
        echo ""
    }
fi

# Set up auto-renewal
if ! crontab -l 2>/dev/null | grep -q certbot; then
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --deploy-hook 'docker restart facededup-nginx'") | crontab -
    echo "  SSL auto-renewal cron job configured"
fi

# --- 6. Environment file ---
echo "[6/7] Setting up environment..."
if [ -f "${DEPLOY_DIR}/.env" ]; then
    echo "  .env file already exists"
else
    cp "${DEPLOY_DIR}/.env.example" "${DEPLOY_DIR}/.env"
    echo ""
    echo "  ================================================"
    echo "  IMPORTANT: Edit .env with your actual values:"
    echo "    nano ${DEPLOY_DIR}/.env"
    echo ""
    echo "  Required changes:"
    echo "    DB_PASSWORD=<strong-password>"
    echo "    API_KEYS=<your-api-key>"
    echo "    DOCS_PASSWORD=<docs-page-password>"
    echo "    DB_POOL_SIZE=20"
    echo "    DB_MAX_OVERFLOW=30"
    echo "    WORKERS=4"
    echo "  ================================================"
    echo ""
fi

# --- 7. Build & Start ---
echo "[7/7] Building and starting services..."
cd "${DEPLOY_DIR}"
sudo -u "${DEPLOY_USER}" docker compose -f docker-compose.prod.yaml build
sudo -u "${DEPLOY_USER}" docker compose -f docker-compose.prod.yaml up -d --remove-orphans

echo ""
echo "Waiting for services to start..."
for i in $(seq 1 90); do
    if curl -sf http://localhost/api/v1/health > /dev/null 2>&1; then
        echo "API is healthy!"
        break
    fi
    if [ "$i" -eq 90 ]; then
        echo "WARNING: API not healthy after 90 seconds. Check logs:"
        echo "  docker compose -f docker-compose.prod.yaml logs api"
    fi
    sleep 2
done

# Run migrations
echo "Running database migrations..."
sudo -u "${DEPLOY_USER}" docker compose -f docker-compose.prod.yaml exec -T api alembic upgrade head 2>/dev/null || {
    echo "  Migrations will run on next deploy"
}

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "  URL:       https://${DOMAIN}"
echo "  Dashboard: https://${DOMAIN}/dashboard"
echo "  Health:    https://${DOMAIN}/api/v1/health"
echo ""
echo "  Useful commands:"
echo "    cd ${DEPLOY_DIR}"
echo "    docker compose -f docker-compose.prod.yaml logs -f api"
echo "    docker compose -f docker-compose.prod.yaml ps"
echo "    docker compose -f docker-compose.prod.yaml restart"
echo ""
echo "  GitHub Secrets to update:"
echo "    DO_HOST     = $(curl -4 -sf ifconfig.me 2>/dev/null || echo '<this-server-ip>')"
echo "    DO_USER     = ${DEPLOY_USER}"
echo "    DO_PASSWORD  = <your-password>"
echo ""
