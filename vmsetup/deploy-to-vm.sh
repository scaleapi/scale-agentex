#!/bin/bash

# Agentex VM Deployment Orchestrator
# Handles complete deployment flow to remote VM

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
    echo "Usage: $0 <vm-ip> <tarball-path>"
    echo ""
    echo "Arguments:"
    echo "  vm-ip        IP address of the target VM"
    echo "  tarball-path Path to the agentex tarball (created by create-vm-package.sh)"
    echo ""
    echo "Example:"
    echo "  $0 192.168.1.100 agentex-alpha-20250117-143022.tar.gz"
    echo ""
    echo "This script will:"
    echo "  1. SCP tarball to VM home directory"
    echo "  2. SCP deploy.sh script to VM"
    echo "  3. Run deployment remotely"
    echo "  4. Start frontend service"
    echo "  5. Activate Python environment"
    echo "  6. Verify services and provide access information"
    exit 1
}

# Check arguments
if [ "$#" -ne 2 ]; then
    print_error "Invalid number of arguments"
    usage
fi

VM_IP="$1"
TARBALL_PATH="$2"
VM_USER="agentex"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Validate inputs
print_status "Validating inputs..."

# Check if tarball exists
if [ ! -f "$TARBALL_PATH" ]; then
    print_error "Tarball not found: $TARBALL_PATH"
    exit 1
fi

# Get absolute path for tarball
TARBALL_PATH=$(readlink -f "$TARBALL_PATH")
TARBALL_NAME=$(basename "$TARBALL_PATH")

# Check if deploy.sh exists in vmsetup directory
DEPLOY_SCRIPT="$SCRIPT_DIR/deploy.sh"
if [ ! -f "$DEPLOY_SCRIPT" ]; then
    print_error "Deploy script not found: $DEPLOY_SCRIPT"
    exit 1
fi

print_success "Inputs validated"
print_status "Target VM: $VM_USER@$VM_IP"
print_status "Tarball: $TARBALL_NAME ($(du -h "$TARBALL_PATH" | cut -f1))"

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

# Step 1: SCP tarball to VM home directory
print_status "📦 Step 1: Uploading tarball to VM..."
if scp "$TARBALL_PATH" "$VM_USER@$VM_IP:~/$TARBALL_NAME"; then
    print_success "Tarball uploaded successfully"
else
    print_error "Failed to upload tarball"
    exit 1
fi

# Step 2: SCP deploy.sh script
print_status "📋 Step 2: Uploading deploy script..."
if scp "$DEPLOY_SCRIPT" "$VM_USER@$VM_IP:~/deploy.sh"; then
    # Make it executable
    ssh "$VM_USER@$VM_IP" "chmod +x ~/deploy.sh"
    print_success "Deploy script uploaded and made executable"
else
    print_error "Failed to upload deploy script"
    exit 1
fi

# Step 3: SCP README-ALPHA.md script to VM
print_status "📋 Step 3: Uploading README-ALPHA-TESTERS.md script..."
if scp "$SCRIPT_DIR/README-ALPHA-TESTERS.md" "$VM_USER@$VM_IP:~/README-ALPHA-TESTERS.md"; then
    print_success "README-ALPHA-TESTERS.md uploaded successfully"
else
    print_error "Failed to upload README-ALPHA-TESTERS.md"
    exit 1
fi

# Step 3: Run deployment remotely
print_status "🚀 Step 3: Running deployment on VM..."
print_status "This may take several minutes..."

if ssh "$VM_USER@$VM_IP" "sudo ~/deploy.sh ~/$TARBALL_NAME"; then
    print_success "Deployment completed successfully"
else
    print_error "Deployment failed"
    print_error "Check the logs above for details"
    exit 1
fi

# Step 4: Start frontend service
print_status "🎨 Step 4: Starting frontend service..."
if ssh "$VM_USER@$VM_IP" "cd /opt/agentex && ./start-frontend-npm.sh"; then
    print_success "Frontend service started"
else
    print_warning "Frontend startup may have issues - continuing anyway"
fi

# Step 5: Activate environment (this is more informational since it's per-session)
print_status "🐍 Step 5: Python environment setup..."
# We can't really "activate" remotely since it's per-session, but we can verify it exists
if ssh "$VM_USER@$VM_IP" "source ~/.bashrc && source /opt/agentex/venv/bin/activate && python --version"; then
    print_success "Python environment verified"
else
    print_warning "Python environment verification failed"
fi

# Step 6: Verify services status
print_status "📊 Step 6: Verifying services..."
ssh "$VM_USER@$VM_IP" "cd /opt/agentex/agentex && docker-compose ps" || print_warning "Some services may not be ready yet"

# Step 7: Check frontend accessibility
print_status "🌐 Step 7: Checking frontend accessibility..."
sleep 5  # Give frontend a moment to start
if ssh "$VM_USER@$VM_IP" "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000" | grep -q "200\|404\|500"; then
    print_success "Frontend is responding on port 3000"
else
    print_warning "Frontend may still be starting up"
fi

# Step 8: Provide access information
print_status "🎯 Step 8: Deployment Summary"
print_success "==============================================="
print_success "🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!"
print_success "==============================================="
print_status ""
print_status "🔗 Access Information:"
print_status "  SSH: ssh $VM_USER@$VM_IP"
print_status ""
print_status "🌐 Service URLs (use SSH port forwarding):"
print_status "  Frontend:    http://localhost:3000"
print_status "  Backend API: http://localhost:5003"
print_status "  Temporal UI: http://localhost:8080"
print_status ""
print_status "🔌 SSH Port Forwarding Commands:"
print_status "  ssh -L 3000:localhost:3000 -L 5003:localhost:5003 -L 8080:localhost:8080 $VM_USER@$VM_IP"
print_status ""
print_status "📋 Useful Commands on VM:"
print_status "  agentex-status       # Check service status"
print_status "  agentex-logs         # View service logs"
print_status "  agentex-restart      # Restart services"
print_status "  agentex-env          # Activate Python environment"
print_status "  cd ~/tutorials       # Access tutorials"
print_status ""
print_status "📖 Complete documentation: /opt/agentex/README-ALPHA.md"

# Step 9: Health check summary
print_status "🔍 Step 9: Running final health checks..."
print_status "Service Status Summary:"

# Get status of all services
ssh "$VM_USER@$VM_IP" "echo '--- Docker Services ---' && cd /opt/agentex/agentex && docker-compose ps && echo '' && echo '--- Frontend Process ---' && pgrep -f 'next dev' && echo 'Frontend running' || echo 'Frontend not detected'" || print_warning "Could not retrieve full status"

# Step 10: Cleanup temporary files and next steps
print_status "🧹 Step 10: Cleanup and next steps..."

# Optionally remove the tarball from VM to save space (user can decide)
print_status "💡 Optional cleanup: Remove tarball from VM to save space:"
print_status "  ssh $VM_USER@$VM_IP 'rm ~/$TARBALL_NAME'"

print_status ""
print_status "🚀 NEXT STEPS:"
print_status "  1. Set up SSH port forwarding (see commands above)"
print_status "  2. Access frontend at http://localhost:3000"
print_status "  3. Check tutorials: ssh $VM_USER@$VM_IP 'ls ~/tutorials'"
print_status "  4. For development, activate env: agentex-env"
print_status ""
print_success "🎊 Happy coding with Agentex!" 