#!/bin/bash
# ============================================
# Video-Creator Server Setup Script
# ============================================
# Run this on a fresh Ubuntu 22.04 server

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

echo ""
echo "============================================"
echo "  Video-Creator Server Setup"
echo "============================================"
echo ""

# Update system
log_info "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# Install dependencies
log_info "Installing dependencies..."
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    htop \
    ncdu \
    ufw \
    fail2ban

# Install Docker
log_info "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    
    # Enable Docker service
    systemctl enable docker
    systemctl start docker
    
    log_success "Docker installed"
else
    log_info "Docker already installed"
fi

# Install Docker Compose (v2 is included with Docker now)
log_info "Verifying Docker Compose..."
docker compose version

# Create app user
log_info "Setting up app user..."
if ! id "deploy" &>/dev/null; then
    useradd -m -s /bin/bash deploy
    usermod -aG docker deploy
    log_success "User 'deploy' created and added to docker group"
else
    log_info "User 'deploy' already exists"
fi

# Create application directory
log_info "Creating application directory..."
mkdir -p /opt/video-creator
chown deploy:deploy /opt/video-creator

# Setup firewall
log_info "Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
echo "y" | ufw enable
log_success "Firewall configured"

# Setup fail2ban
log_info "Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
EOF

systemctl enable fail2ban
systemctl restart fail2ban
log_success "Fail2ban configured"

# Setup automatic security updates
log_info "Configuring automatic security updates..."
apt-get install -y unattended-upgrades
# Non-interactive enablement (safe for curl|bash usage)
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# Create swap if needed (for low memory servers)
log_info "Checking swap..."
if [ $(swapon --show | wc -l) -eq 0 ]; then
    log_info "Creating 2GB swap file..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    log_success "Swap created"
else
    log_info "Swap already exists"
fi

# Docker log rotation
log_info "Configuring Docker log rotation..."
cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker

# Print summary
echo ""
echo "============================================"
log_success "Server setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Clone your repository to /opt/video-creator:"
echo "   sudo -u deploy git clone <your-repo> /opt/video-creator"
echo ""
echo "2. Configure environment:"
echo "   cd /opt/video-creator"
echo "   cp env.prod.example .env.prod"
echo "   nano .env.prod"
echo ""
echo "3. Run deployment:"
echo "   ./deploy/deploy.sh"
echo ""
echo "Server info:"
echo "  - App user: deploy"
echo "  - App directory: /opt/video-creator"
echo "  - Firewall: enabled (ssh, http, https)"
echo "  - Fail2ban: enabled"
echo ""
echo "To switch to deploy user: sudo su - deploy"
echo ""

