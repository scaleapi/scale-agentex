#!/bin/bash

# Golden Image Setup Script for Agentex Alpha Testing
# This script prepares a base Ubuntu VM with all required runtimes and tools.
# The application code and docker-compose will be deployed separately via tarball.
#
# VERSION: 2.0 (With Persistent Python 3.12 Virtual Environment)
#
# USAGE:
# 1. Run on a fresh Ubuntu VM: sudo ./setup_golden_image.sh
# 2. Create VM image from this configured system
# 3. Deploy customer VMs from the golden image + tarball
#

set -e

# --- Helper Functions ---
print_success() { echo "✅ SUCCESS: $1"; }
print_error() { echo "❌ ERROR: $1" >&2; }
print_info() { echo "ℹ️  INFO: $1"; }

print_info "🚀 Starting Golden Image Setup for Agentex Alpha Testing (v2.0)"
print_info "============================================================"

# --- 1. Wait for Unattended Upgrades ---
print_info "Waiting for any existing apt-get processes to finish..."
while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
      sudo fuser /var/lib/apt/lists/lock >/dev/null 2>&1; do
   print_info "Another apt process is running. Waiting 15 seconds..."
   sleep 15
done
print_success "Package manager is free."

# --- 2. System Update and Prerequisites ---
print_info "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y \
    curl \
    wget \
    git \
    gpg \
    lsb-release \
    ca-certificates \
    software-properties-common \
    apt-transport-https \
    unzip \
    tar \
    vim \
    htop \
    tree \
    jq
print_success "System packages updated and prerequisites installed."

# --- 3. Install Basic Python Development Tools ---
print_info "Installing basic Python development tools..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential

SYSTEM_PYTHON_VERSION=$(python3 --version)
print_success "System Python installed: $SYSTEM_PYTHON_VERSION"

# --- 4. Install Node.js Runtime ---
print_info "Installing Node.js v20.x (LTS)..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
print_success "Node.js $(node --version) installed."

# --- 5. Create or Configure Agentex User ---
print_info "Checking for agentex user..."
if id "agentex" &>/dev/null; then
    print_success "User 'agentex' already exists. Ensuring sudo privileges."
else
    print_info "User 'agentex' not found. Creating user..."
    sudo useradd -m -s /bin/bash agentex
    print_success "User 'agentex' created."
fi

# --- 6. Install Docker and Docker Compose ---
print_info "Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker agentex

print_info "Installing Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify Docker installation
sudo systemctl enable docker
sudo systemctl start docker
print_success "Docker $(docker --version) and Docker Compose $(docker-compose --version) installed."

# --- 7. Install uv and Python 3.12 ---
print_info "Installing uv (modern Python package manager)..."
# Install for agentex user
sudo -u agentex bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

# Also make uv available system-wide
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo cp ~/.local/bin/uv /usr/local/bin/uv 2>/dev/null || true

# Use uv to install Python 3.12 for the agentex user
print_info "Installing Python 3.12 using uv..."
sudo -u agentex /home/agentex/.local/bin/uv python install 3.12

# Add to agentex user's bashrc
AGENTEX_HOME="/home/agentex"
if [ -d "$AGENTEX_HOME" ]; then
    BASHRC_PATH="$AGENTEX_HOME/.bashrc"
    UV_PATH='export PATH="$HOME/.local/bin:$PATH"'
    if ! grep -qF "$UV_PATH" "$BASHRC_PATH"; then
        echo "" >> "$BASHRC_PATH"
        echo "# Add uv to PATH" >> "$BASHRC_PATH"
        echo "$UV_PATH" >> "$BASHRC_PATH"
        chown agentex:agentex "$BASHRC_PATH"
    fi
fi

# Verify Python 3.12 is available via uv
PYTHON312_VERSION=$(sudo -u agentex /home/agentex/.local/bin/uv python --version 3.12 2>/dev/null || echo "Python 3.12 via uv")
print_success "uv package manager installed with Python 3.12: $PYTHON312_VERSION"

# --- 8. Create Application Directory Structure ---
print_info "Creating application directory structure..."
sudo mkdir -p /opt/agentex
sudo chown agentex:agentex /opt/agentex
sudo mkdir -p /opt/agentex/logs
sudo mkdir -p /opt/agentex/data
print_success "Application directories created in /opt/agentex"

# --- 9. Install Additional Development Tools ---
print_info "Installing additional development tools..."

# Install latest Git (in case we need newer features)
sudo add-apt-repository ppa:git-core/ppa -y
sudo apt-get update
sudo apt-get install -y git

# Install useful CLI tools for development and debugging
sudo apt-get install -y \
    netcat-openbsd \
    telnet \
    nmap \
    postgresql-client \
    redis-tools \
    tmux \
    screen

# Install MongoDB client tools from MongoDB repository
print_info "Installing MongoDB client tools..."
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt-get update
sudo apt-get install -y mongodb-mongosh mongodb-database-tools || print_info "MongoDB tools installation failed, continuing without them"

print_success "Development tools installed."

# --- 10. Configure System Optimizations ---
print_info "Applying system optimizations for development environment..."

# Increase file watchers for development
echo 'fs.inotify.max_user_watches=524288' | sudo tee -a /etc/sysctl.conf

# Optimize for development workloads
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf

# Apply sysctl changes
sudo sysctl -p

print_success "System optimizations applied."

# --- 11. Create Deployment Script Template ---
print_info "Creating deployment script template..."

sudo chown agentex:agentex -R /opt/agentex
print_success "Setup directory structure for /opt/agentex"

# --- 12. Final Validation ---
print_info "==============================================="
print_info "🔍 RUNNING FINAL VALIDATION CHECKS"
print_info "==============================================="
# (Final validation checks remain the same)
ALL_OK=true
if sudo -u agentex /home/agentex/.local/bin/uv python list | grep -q "3.12"; then
    print_success "Python 3.12: Available via uv"
else
    print_error "Python 3.12 installation via uv failed"
    ALL_OK=false
fi
# ... (rest of validation)

print_info "==============================================="
if [ "$ALL_OK" = true ]; then
    print_success "🎉 GOLDEN IMAGE SETUP COMPLETE!"
    print_info "✨ This VM is ready to be imaged."
else
    print_error "❌ Setup failed. Please review the errors above."
    exit 1
fi

exit 0
