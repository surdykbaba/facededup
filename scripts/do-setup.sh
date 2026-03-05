#!/bin/bash
set -e

# ================================================
#  FaceDedup API - Digital Ocean Droplet Setup
# ================================================
#
#  Run this ONCE on a fresh Ubuntu 24.04 droplet:
#    ssh root@<droplet-ip> 'bash -s' < scripts/do-setup.sh
#
#  Or copy it to the server and run:
#    scp scripts/do-setup.sh root@<droplet-ip>:/root/
#    ssh root@<droplet-ip> bash /root/do-setup.sh
#
#  Prerequisites:
#    - Fresh DO droplet (s-2vcpu-4gb, Ubuntu 24.04)
#    - SSH access as root
#    - Your Git repo URL (GitHub/GitLab/Bitbucket)
# ================================================

# ---- Configuration (edit these before running) ----
REPO_URL="${REPO_URL:-}"           # e.g. https://github.com/youruser/facededup.git
DOMAIN="${DOMAIN:-}"               # e.g. api.facededup.com (leave empty to skip SSL)
DEPLOY_USER="deployer"
APP_DIR="/home/${DEPLOY_USER}/facededup"
# ---------------------------------------------------

echo "================================================"
echo "  FaceDedup API - DO Droplet Setup"
echo "================================================"
echo ""

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run as root."
    exit 1
fi

# Prompt for repo URL if not set
if [ -z "$REPO_URL" ]; then
    read -rp "Git repo URL: " REPO_URL
    if [ -z "$REPO_URL" ]; then
        echo "ERROR: Repo URL is required."
        exit 1
    fi
fi

# Prompt for domain (optional)
if [ -z "$DOMAIN" ]; then
    read -rp "Domain for SSL (leave empty to skip): " DOMAIN
fi

echo ""
echo "  Repo:   $REPO_URL"
echo "  Domain: ${DOMAIN:-none (HTTP only)}"
echo "  User:   $DEPLOY_USER"
echo "  Dir:    $APP_DIR"
echo ""

# ---- 1. System update ----
echo "[1/8] Updating system..."
apt update && apt upgrade -y

# ---- 2. Create deploy user ----
echo "[2/8] Creating deploy user..."
if ! id "$DEPLOY_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
    usermod -aG sudo "$DEPLOY_USER"
    echo "${DEPLOY_USER} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${DEPLOY_USER}
    mkdir -p /home/${DEPLOY_USER}/.ssh
    # Copy SSH keys so you can SSH as deployer
    if [ -f /root/.ssh/authorized_keys ]; then
        cp /root/.ssh/authorized_keys /home/${DEPLOY_USER}/.ssh/
    fi
    chown -R ${DEPLOY_USER}:${DEPLOY_USER} /home/${DEPLOY_USER}/.ssh
    chmod 700 /home/${DEPLOY_USER}/.ssh
    chmod 600 /home/${DEPLOY_USER}/.ssh/authorized_keys 2>/dev/null || true
    echo "  Created user: $DEPLOY_USER"
else
    echo "  User $DEPLOY_USER already exists."
fi

# ---- 3. Firewall ----
echo "[3/8] Configuring firewall..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ---- 4. Install Docker ----
echo "[4/8] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "$DEPLOY_USER"
    systemctl enable docker
    echo "  Docker installed."
else
    echo "  Docker already installed."
fi

# ---- 5. Setup swap (essential for InsightFace on 4GB droplet) ----
echo "[5/8] Setting up 2GB swap..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    echo "  2GB swap created."
else
    echo "  Swap already exists."
fi

# ---- 6. Clone repo ----
echo "[6/8] Cloning repository..."
if [ ! -d "$APP_DIR" ]; then
    sudo -u "$DEPLOY_USER" git clone "$REPO_URL" "$APP_DIR"
    echo "  Cloned to $APP_DIR"
else
    echo "  $APP_DIR already exists. Pulling latest..."
    cd "$APP_DIR" && sudo -u "$DEPLOY_USER" git pull origin main
fi

# ---- 7. SSL certificate ----
if [ -n "$DOMAIN" ]; then
    echo "[7/8] Setting up SSL for $DOMAIN..."
    apt install -y certbot
    # Stop anything on port 80 temporarily
    systemctl stop nginx 2>/dev/null || true
    docker compose -f "$APP_DIR/docker-compose.prod.yaml" down 2>/dev/null || true
    certbot certonly --standalone -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email
    # Update nginx config with actual domain
    sed -i "s/yourdomain.com/$DOMAIN/g" "$APP_DIR/nginx/conf.d/api.conf"
    # Setup auto-renewal
    (crontab -l 2>/dev/null; echo "0 3 1 * * certbot renew --quiet --pre-hook 'docker compose -f $APP_DIR/docker-compose.prod.yaml stop nginx' --post-hook 'docker compose -f $APP_DIR/docker-compose.prod.yaml start nginx'") | crontab -
    echo "  SSL certificate obtained for $DOMAIN"
else
    echo "[7/8] Skipping SSL (no domain provided)."
    echo "  API will be available on HTTP port 80 only."
fi

# ---- 8. Configure .env and deploy ----
echo "[8/8] Preparing application..."
cd "$APP_DIR"

if [ ! -f .env ]; then
    sudo -u "$DEPLOY_USER" cp .env.example .env

    # Generate a random DB password
    DB_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
    sed -i "s/DB_PASSWORD=changeme/DB_PASSWORD=$DB_PASS/" .env
    sed -i "s/postgresql+asyncpg:\/\/facededup:changeme/postgresql+asyncpg:\/\/facededup:$DB_PASS/" .env

    # Generate API key
    API_KEY=$(python3 -c "import secrets; print(f'fd_{secrets.token_urlsafe(36)}')")
    sed -i "s/API_KEYS=your-api-key-here/API_KEYS=$API_KEY/" .env

    echo ""
    echo "  .env configured with:"
    echo "    DB Password: $DB_PASS"
    echo "    API Key:     $API_KEY"
    echo ""
    echo "  SAVE THESE VALUES - you won't see them again!"
    echo ""
else
    echo "  .env already exists, keeping existing config."
fi

# Fix ownership
chown -R ${DEPLOY_USER}:${DEPLOY_USER} "$APP_DIR"

# Run deploy
echo ""
echo "  Running first deployment..."
echo ""
cd "$APP_DIR"
sudo -u "$DEPLOY_USER" bash scripts/deploy.sh

echo ""
echo "================================================"
echo "  Setup complete!"
echo "================================================"
echo ""
if [ -n "$DOMAIN" ]; then
    echo "  API:    https://$DOMAIN/api/v1/health"
else
    DROPLET_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address 2>/dev/null || hostname -I | awk '{print $1}')
    echo "  API:    http://$DROPLET_IP/api/v1/health"
fi
echo "  SSH:    ssh $DEPLOY_USER@<droplet-ip>"
echo "  Logs:   cd $APP_DIR && docker compose -f docker-compose.prod.yaml logs -f api"
echo ""
echo "  Test it:"
echo "    curl -s <your-url>/api/v1/health | python3 -m json.tool"
echo ""
