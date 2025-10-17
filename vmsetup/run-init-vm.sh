#!/bin/bash

# AgentEx VM Initialization Orchestrator
# Handles complete VM initialization flow on remote VM

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Usage function
usage() {
    echo "Usage: $0 <vm-ip>"
    echo ""
    echo "Arguments:"
    echo "  vm-ip        IP address of the target VM"
    echo ""
    echo "Example:"
    echo "  $0 192.168.1.100"
    echo ""
    echo "This script will:"
    echo "  1. Test SSH connectivity to the VM"
    echo "  2. Upload init-vm.sh script to VM"
    echo "  3. Run VM initialization remotely"
    echo "  4. Clean up temporary files"
    echo "  5. Verify initialization completed successfully"
    exit 1
}

# Check for help flag
if [ "$#" -ge 1 ] && [[ "$1" =~ ^(-h|--help)$ ]]; then
    usage
fi

# Check arguments
if [ "$#" -ne 1 ]; then
    print_error "Invalid number of arguments"
    usage
fi

VM_IP="$1"
VM_USER="agentex"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Validate inputs
print_status "Validating inputs..."

# Check if init-vm.sh exists in vmsetup directory
INIT_SCRIPT="$SCRIPT_DIR/init-vm.sh"
if [ ! -f "$INIT_SCRIPT" ]; then
    print_error "Initialization script not found: $INIT_SCRIPT"
    exit 1
fi

print_success "Inputs validated"
print_status "Target VM: $VM_USER@$VM_IP"
print_status "Init script: $(basename "$INIT_SCRIPT")"

# Test SSH connectivity
print_status "Testing SSH connectivity..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "$VM_USER@$VM_IP" exit 2>/dev/null; then
    print_error "Cannot connect to $VM_USER@$VM_IP via SSH"
    print_error "Please ensure:"
    print_error "  - VM is running and accessible"
    print_error "  - SSH keys are properly configured"
    print_error "  - User 'agentex' exists on the VM"
    exit 1
fi
print_success "SSH connectivity confirmed"

# Step 1: Upload init-vm.sh script
print_status "📋 Step 1: Uploading initialization script..."
if scp "$INIT_SCRIPT" "$VM_USER@$VM_IP:~/init-vm.sh"; then
    # Make it executable
    ssh "$VM_USER@$VM_IP" "chmod +x ~/init-vm.sh"
    print_success "Initialization script uploaded and made executable"
else
    print_error "Failed to upload initialization script"
    exit 1
fi

# Step 2: Run initialization remotely
print_status "🚀 Step 2: Running VM initialization..."
print_status "This may take several minutes..."
print_warning "The VM will install Docker, Python 3.12, Node.js, and other development tools"

if ssh "$VM_USER@$VM_IP" "sudo ~/init-vm.sh"; then
    print_success "VM initialization completed successfully"
else
    print_error "VM initialization failed"
    print_error "Check the logs above for details"
    exit 1
fi

# Step 3: Clean up temporary files
print_status "🧹 Step 3: Cleaning up temporary files..."
ssh "$VM_USER@$VM_IP" "rm -f ~/init-vm.sh ~/get-docker.sh" || print_warning "Some cleanup files may not exist"
print_success "Temporary files cleaned up"

# Step 4: Verify initialization results
print_status "🔍 Step 4: Verifying initialization..."

# Check Docker installation
if ssh "$VM_USER@$VM_IP" "docker --version >/dev/null 2>&1"; then
    DOCKER_VERSION=$(ssh "$VM_USER@$VM_IP" "docker --version")
    print_success "Docker verified: $DOCKER_VERSION"
else
    print_warning "Docker verification failed"
fi

# Check Python 3.12 via uv
if ssh "$VM_USER@$VM_IP" "source ~/.bashrc && /home/agentex/.local/bin/uv python --version 3.12 >/dev/null 2>&1"; then
    print_success "Python 3.12 via uv verified"
else
    print_warning "Python 3.12 verification failed"
fi

# Check Node.js
if ssh "$VM_USER@$VM_IP" "node --version >/dev/null 2>&1"; then
    NODE_VERSION=$(ssh "$VM_USER@$VM_IP" "node --version")
    print_success "Node.js verified: $NODE_VERSION"
else
    print_warning "Node.js verification failed"
fi

# Check application directory
if ssh "$VM_USER@$VM_IP" "[ -d /opt/agentex ] && [ -O /opt/agentex ]"; then
    print_success "Application directory verified: /opt/agentex"
else
    print_warning "Application directory verification failed"
fi

# Step 5: Provide next steps
print_status "🎯 Step 5: Initialization Summary"
print_success "==============================================="
print_success "🎉 VM INITIALIZATION COMPLETED SUCCESSFULLY!"
print_success "==============================================="
print_status ""
print_status "✅ Installed components:"
print_status "  - Docker & Docker Compose"
print_status "  - Python 3.12 (via uv)"
print_status "  - Node.js v20.x LTS"
print_status "  - Development tools (git, vim, htop, etc.)"
print_status "  - Database clients (PostgreSQL, MongoDB, Redis)"
print_status ""
print_status "📁 Directory structure:"
print_status "  /opt/agentex/          # Application root"
print_status "  /opt/agentex/logs/     # Log files"
print_status "  /opt/agentex/data/     # Data directory"
print_status "  /home/agentex/         # User home directory"
print_status ""
print_status "🔗 VM Access:"
print_status "  SSH: ssh $VM_USER@$VM_IP"
print_status ""
print_status "🚀 NEXT STEPS:"
print_status "  1. Create AgentEx package: ./create-vm-package.sh ~/src/agentex"
print_status "  2. Deploy to VM: ./deploy-to-vm.sh $VM_IP agentex-alpha-YYYYMMDD-HHMMSS.tar.gz"
print_status "  3. Access services via SSH port forwarding"
print_status ""
print_success "🎊 VM is ready for AgentEx deployment!" 