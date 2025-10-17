# AgentEx VM Setup & Deployment Guide

This guide covers the complete process for setting up and deploying AgentEx to Azure VMs for alpha testing.

## Prerequisites

- Azure CLI installed and configured (`az login`)
- SSH keys set up for Azure VMs
- Docker and Node.js installed locally (for package creation)
- Access to the AgentEx source repository

## VM Setup Scripts

The `vmsetup/` directory contains all the scripts needed for VM management:

- **`run-init-vm.sh`** - VM initialization orchestrator (uploads and runs init-vm.sh remotely)
- **`init-vm.sh`** - VM initialization script (installs Docker, Python 3.12, Node.js, etc.)
- **`deploy-to-vm.sh`** - Deployment orchestrator (uploads and runs deploy.sh remotely)
- **`deploy.sh`** - Deployment script (extracts tarball, installs AgentEx, starts services)
- **`create-vm-package.sh`** - Creates deployment tarball from source code
- **`cloud-init.yml`** - Initial VM setup (runs during VM creation)

## Quick Start

```bash
# 1. Create VM
az vm create --resource-group agentex-test-rg --name agentex-base-dc-vm --image Ubuntu2204 --size Standard_D2s_v3 --admin-username agentex --generate-ssh-keys --custom-data cloud-init.yml

# 2. Get VM IP (from output above or query)
VM_IP=$(az vm show -d -g agentex-test-rg -n agentex-base-dc-vm --query publicIps -o tsv)

# 3. Initialize VM
./run-init-vm.sh $VM_IP

# 4. Create deployment package
./create-vm-package.sh ~/src/agentex  # or use AGENTEX_HOME env var

# 5. Deploy to VM
./vmsetup/deploy-to-vm.sh $VM_IP agentex-alpha-YYYYMMDD-HHMMSS.tar.gz
```

## Detailed Setup Process

### 1. VM Creation

Create a new Ubuntu 22.04 VM with the provided cloud-init configuration:

```bash
az vm create \
  --resource-group agentex-test-rg \
  --name agentex-base-dc-vm \
  --image Ubuntu2204 \
  --size Standard_D2s_v3 \
  --admin-username agentex \
  --generate-ssh-keys \
  --custom-data cloud-init.yml
```

**Important notes:**
- `--custom-data cloud-init.yml` runs initial VM setup (installs Docker, creates user, etc.)
- `--generate-ssh-keys` creates SSH keys if they don't exist
- VM size `Standard_D2s_v3` provides 2 vCPUs and 8GB RAM (suitable for development)

Alternative VM sizes:
- `Standard_B2ms` - 2 vCPUs, 8GB RAM (burstable, cost-effective)
- `Standard_D4s_v3` - 4 vCPUs, 16GB RAM (for heavier workloads)

### 2. VM Initialization

After VM creation, get the public IP and initialize the VM:

```bash
# Get VM IP address
VM_IP=$(az vm show -d -g agentex-test-rg -n agentex-base-dc-vm --query publicIps -o tsv)
echo "VM IP: $VM_IP"

# Run VM initialization orchestrator
./vmsetup/run-init-vm.sh $VM_IP
```

The `run-init-vm.sh` orchestrator:
- Tests SSH connectivity to the VM
- Uploads `init-vm.sh` script to VM
- Runs VM initialization remotely (installs Docker, Python 3.12, Node.js, etc.)
- Cleans up temporary files
- Verifies installation completed successfully

### 3. Package Creation

Create a deployment package containing the AgentEx source code:

```bash
# Option 1: Specify AgentEx directory as argument
./create-vm-package.sh ~/src/agentex

# Option 2: Use environment variable
export AGENTEX_HOME=~/src/agentex
./create-vm-package.sh

# Option 3: Run from AgentEx root (legacy)
cd ~/src/agentex
./create-vm-package.sh
```

This creates a timestamped tarball: `agentex-alpha-YYYYMMDD-HHMMSS.tar.gz`

**Package contents:**
- `agentex/` - Server code with docker-compose.yml
- `agentex-py/` - Python SDK and CLI tools
- `agentex-web/` - Frontend application
- `tutorials/` - Tutorial examples
- `README.md` - Basic deployment instructions

### 4. Deployment

Deploy the package to your VM:

```bash
./vmsetup/deploy-to-vm.sh $VM_IP agentex-alpha-YYYYMMDD-HHMMSS.tar.gz
```

This script:
1. Uploads tarball and deployment script to VM
2. Runs deployment (extracts, installs dependencies, starts services)
3. Configures Python environment with AgentEx CLI
4. Starts frontend service
5. Provides access instructions with SSH port forwarding

### 5. Accessing Services

After deployment, access services via SSH port forwarding:

```bash
# Forward all ports
ssh -L 3000:localhost:3000 -L 5003:localhost:5003 -L 8080:localhost:8080 agentex@$VM_IP

# Then access:
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:5003  
# - Temporal UI: http://localhost:8080
```

## VM Management Commands

Once connected to the VM, use these aliases:

```bash
# Service management
agentex-status       # Check all service status
agentex-logs         # Follow service logs
agentex-restart      # Restart all services
agentex-stop         # Stop all services
agentex-start        # Start all services

# Development
agentex-env          # Activate Python environment
cd ~/tutorials       # Access tutorial examples
```

## Troubleshooting

### VM Creation Issues

**SSH key problems:**
```bash
# Generate new SSH key if needed
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa

# Verify connection
ssh -v agentex@$VM_IP
```

**Cloud-init failures:**
```bash
# Check cloud-init logs on VM
ssh agentex@$VM_IP "sudo cat /var/log/cloud-init-output.log"
```

### Deployment Issues

**Package creation fails:**
- Ensure you have Node.js and npm installed
- Check that the AgentEx directory structure is complete
- Verify file permissions in the source directory

**Deployment fails:**
```bash
# Check deployment logs
ssh agentex@$VM_IP "sudo journalctl -u agentex --since '1 hour ago'"

# Manually run deployment script
ssh agentex@$VM_IP
sudo /opt/agentex/deploy.sh ~/agentex-alpha-*.tar.gz
```

**Services not starting:**
```bash
# Check Docker status
ssh agentex@$VM_IP "docker ps -a"

# Check infrastructure services
ssh agentex@$VM_IP "cd /opt/agentex/agentex && docker-compose logs"

# Restart services
ssh agentex@$VM_IP "agentex-restart"
```

### Connectivity Issues

**Port forwarding not working:**
- Ensure services are running on the VM
- Check firewall rules: `ssh agentex@$VM_IP "sudo ufw status"`
- Verify services are bound to correct interfaces

**Frontend 502/504 errors:**
- Check if frontend process is running: `ssh agentex@$VM_IP "pgrep -f 'next dev'"`
- Check frontend logs: `ssh agentex@$VM_IP "tail -f /opt/agentex/logs/frontend.log"`

## File Structure on VM

After successful deployment:

```
/opt/agentex/
├── agentex/              # Server code + docker-compose.yml
├── agentex-py/           # Python SDK
├── agentex-web/          # Frontend code
├── venv/                 # Python 3.12 virtual environment
├── logs/                 # Service logs
├── start-frontend-npm.sh # Frontend startup script
├── manage-infrastructure.sh # Infrastructure management
└── README-ALPHA.md       # User guide

/home/agentex/
├── tutorials/            # Tutorial examples
└── .bashrc               # Configured with agentex aliases
```

## Multiple VM Management

For managing multiple VMs:

```bash
# Create multiple VMs
for i in {1..3}; do
  az vm create \
    --resource-group agentex-test-rg \
    --name agentex-vm-$i \
    --image Ubuntu2204 \
    --size Standard_D2s_v3 \
    --admin-username agentex \
    --generate-ssh-keys \
    --custom-data cloud-init.yml
done

# Deploy to all VMs
for vm in agentex-vm-{1..3}; do
  VM_IP=$(az vm show -d -g agentex-test-rg -n $vm --query publicIps -o tsv)
  ./deploy-to-vm.sh $VM_IP agentex-alpha-latest.tar.gz
done
```

## Cleanup

```bash
# Stop and remove VM
az vm delete --resource-group agentex-test-rg --name agentex-base-dc-vm --yes

# Clean up resource group (if no longer needed)
az group delete --name agentex-test-rg --yes
```

## Security Considerations

- VMs use SSH key authentication (no passwords)
- Services run in Docker containers with limited privileges
- Only necessary ports are exposed via SSH tunneling
- Regular system updates via cloud-init

## Next Steps

1. **Automated Testing**: Add health checks and automated testing post-deployment
2. **Scaling**: Consider VM scale sets for multiple test environments
3. **Monitoring**: Add Azure Monitor integration for VM and service metrics
4. **Backup**: Implement automated snapshots for VM state preservation 