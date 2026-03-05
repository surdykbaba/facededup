#!/bin/bash
set -e

echo "================================================"
echo "  FaceDedup API - AWS EC2 Server Setup"
echo "================================================"
echo ""
echo "  Run this script on a fresh Ubuntu 24.04 EC2 instance."
echo "  Instance type: t3.xlarge (Phase 1 CPU)"
echo "  or g4dn.xlarge (Phase 2 GPU)"
echo ""

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run this script as root (sudo bash aws-setup.sh)"
    exit 1
fi

echo "[1/8] Updating system..."
apt update && apt upgrade -y

echo "[2/8] Creating deploy user..."
if ! id "deployer" &>/dev/null; then
    adduser --disabled-password --gecos "" deployer
    usermod -aG sudo deployer
    echo "deployer ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deployer
    # Copy SSH keys from ubuntu/root user
    mkdir -p /home/deployer/.ssh
    if [ -f /home/ubuntu/.ssh/authorized_keys ]; then
        cp /home/ubuntu/.ssh/authorized_keys /home/deployer/.ssh/
    elif [ -f /root/.ssh/authorized_keys ]; then
        cp /root/.ssh/authorized_keys /home/deployer/.ssh/
    fi
    chown -R deployer:deployer /home/deployer/.ssh
    chmod 700 /home/deployer/.ssh
    chmod 600 /home/deployer/.ssh/authorized_keys
    echo "  Created user: deployer"
else
    echo "  User deployer already exists, skipping."
fi

echo "[3/8] Configuring firewall..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
echo "  Firewall enabled (SSH, HTTP, HTTPS)"

echo "[4/8] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker deployer
    systemctl enable docker
    echo "  Docker installed"
else
    echo "  Docker already installed, skipping."
fi

echo "[5/8] Setting up swap (4GB for ML model memory)..."
if [ ! -f /swapfile ]; then
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # Optimize swap for ML workloads
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    echo "  4GB swap created"
else
    echo "  Swap already exists, skipping."
fi

echo "[6/8] Installing certbot for SSL..."
if ! command -v certbot &>/dev/null; then
    apt install -y certbot
    echo "  Certbot installed"
else
    echo "  Certbot already installed, skipping."
fi

echo "[7/8] Checking for NVIDIA GPU..."
if lspci | grep -i nvidia &>/dev/null; then
    echo "  NVIDIA GPU detected! Installing NVIDIA Container Toolkit..."
    # Install NVIDIA drivers
    apt install -y nvidia-driver-535
    # Install NVIDIA Container Toolkit
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
        gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt update && apt install -y nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
    echo "  NVIDIA Container Toolkit installed"
    echo ""
    echo "  GPU DETECTED: Use docker-compose.gpu.yaml for deployment"
else
    echo "  No GPU detected. Using CPU mode."
    echo "  To upgrade to GPU later, switch to a g4dn.xlarge instance."
fi

echo "[8/8] Creating project directory..."
mkdir -p /home/deployer/facededup
chown deployer:deployer /home/deployer/facededup

echo ""
echo "================================================"
echo "  Server setup complete!"
echo "================================================"
echo ""
echo "  Next steps:"
echo "  1. SSH as deployer:  ssh deployer@<instance-ip>"
echo "  2. Clone your repo:  cd ~ && git clone <repo-url> facededup"
echo "  3. Get SSL cert:     sudo certbot certonly --standalone -d api.yourdomain.com"
echo "  4. Configure:        cd facededup && cp .env.example .env && nano .env"
echo "  5. Generate API key: python3 scripts/generate_api_key.py"
echo "  6. Deploy:           ./scripts/deploy.sh"
echo ""
echo "  AWS Security Group reminder:"
echo "    - Inbound: SSH (22), HTTP (80), HTTPS (443)"
echo "    - Outbound: All traffic"
echo ""
