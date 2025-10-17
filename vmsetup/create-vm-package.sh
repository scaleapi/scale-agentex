#!/bin/bash
# trigger
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PACKAGE_DIR="agentex-alpha-package"
PACKAGE_NAME="agentex-alpha-$(date +%Y%m%d-%H%M%S).tar.gz"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Usage function
usage() {
    echo "Usage: $0 [agentex-home-directory]"
    echo ""
    echo "Arguments:"
    echo "  agentex-home-directory  Path to the AgentEx source directory (optional)"
    echo ""
    echo "The script will use the AgentEx home directory in this order:"
    echo "  1. Command line argument (if provided)"
    echo "  2. AGENTEX_HOME environment variable (if set)"
    echo "  3. Current script directory (legacy behavior)"
    echo ""
    echo "Examples:"
    echo "  $0 ~/src/agentex                    # Use specific directory"
    echo "  AGENTEX_HOME=~/src/agentex $0       # Use environment variable"
    echo "  $0                                  # Use script directory (legacy)"
    exit 1
}

# Determine and validate AgentEx home directory
determine_agentex_home() {
    local agentex_home=""
    local source_type=""
    
    # Check command line argument first
    if [ "$#" -ge 1 ]; then
        agentex_home="$1"
        source_type="command line argument"
    # Check environment variable second
    elif [ -n "${AGENTEX_HOME:-}" ]; then
        agentex_home="$AGENTEX_HOME"
        source_type="AGENTEX_HOME environment variable"
    # Fall back to script directory (legacy behavior)
    else
        agentex_home="$SCRIPT_DIR"
        source_type="script directory (legacy)"
    fi
    
    # Convert to absolute path (if path exists)
    local resolved_path
    resolved_path=$(readlink -f "$agentex_home" 2>/dev/null)
    
    # If readlink failed or returned empty, use the original path for error reporting
    if [ -z "$resolved_path" ]; then
        echo "$agentex_home"
    else
        echo "$resolved_path"
    fi
}

# Validate AgentEx home directory
validate_agentex_home() {
    local agentex_home="$1"
    
    # Validate the directory exists
    if [ ! -d "$agentex_home" ]; then
        print_error "AgentEx home directory does not exist: $agentex_home"
        return 1
    fi
    
    # Validate required subdirectories exist
    local missing_dirs=()
    for required_dir in agentex agentex-py agentex-web; do
        if [ ! -d "$agentex_home/$required_dir" ]; then
            missing_dirs+=("$required_dir")
        fi
    done
    
    if [ ${#missing_dirs[@]} -ne 0 ]; then
        print_error "AgentEx home directory is missing required subdirectories: ${missing_dirs[*]}"
        print_error "Expected directory structure:"
        print_error "  $agentex_home/"
        print_error "  ├── agentex/          # Server code"
        print_error "  ├── agentex-py/       # Python SDK"
        print_error "  └── agentex-web/      # Frontend code"
        return 1
    fi
    
    return 0
}

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

# Cleanup function
cleanup() {
    if [ -d "$SCRIPT_DIR/$PACKAGE_DIR" ]; then
        print_status "Cleaning up temporary directory..."
        rm -rf "$SCRIPT_DIR/$PACKAGE_DIR"
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Check dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    local missing_deps=()
    
    # Check for Node.js and npm (needed for frontend build)
    if ! command -v node &> /dev/null; then
        missing_deps+=("node")
    fi
    
    if ! command -v npm &> /dev/null; then
        missing_deps+=("npm")
    fi
    
    # Check for rsync (needed for selective copying)
    if ! command -v rsync &> /dev/null; then
        missing_deps+=("rsync")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        print_status "Please install them first. For Ubuntu/Debian:"
        print_status "  sudo apt update && sudo apt install -y ${missing_deps[*]}"
        exit 1
    fi
    
    print_success "All dependencies found"
}

# No frontend build needed - deploy.sh handles development setup

# Create package directory structure to match deploy.sh expectations
create_package_structure() {
    print_status "Creating package directory structure..."
    
    # Use absolute path for package directory
    local ABS_PACKAGE_DIR="$SCRIPT_DIR/$PACKAGE_DIR"
    
    # Remove existing package directory if it exists
    if [ -d "$ABS_PACKAGE_DIR" ]; then
        rm -rf "$ABS_PACKAGE_DIR"
    fi
    
    # Create main package directory
    mkdir -p "$ABS_PACKAGE_DIR"
    
    # Create subdirectories to match deploy.sh expectations
    mkdir -p "$ABS_PACKAGE_DIR/agentex"        # Server code + docker-compose
    mkdir -p "$ABS_PACKAGE_DIR/agentex-py"     # SDK
    mkdir -p "$ABS_PACKAGE_DIR/agentex-web"    # Frontend
    mkdir -p "$ABS_PACKAGE_DIR/tutorials"      # Tutorials
    
    print_success "Package directory structure created"
}

# Copy server code (agentex directory)
copy_server() {
    local agentex_home="$1"
    print_status "Copying server code (excluding build artifacts)..."
    
    # Use absolute paths for consistency
    local SERVER_SOURCE_DIR="$agentex_home/agentex"
    local SERVER_DEST_DIR="$SCRIPT_DIR/$PACKAGE_DIR/agentex"
    
    # Copy server directory excluding build artifacts and cache
    rsync -av \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '*.pyo' \
        --exclude '.pytest_cache' \
        --exclude '.coverage' \
        --exclude '.venv' \
        --exclude 'venv' \
        --exclude '.DS_Store' \
        --exclude '.env.local' \
        --exclude '.env.*.local' \
        "$SERVER_SOURCE_DIR/" "$SERVER_DEST_DIR/"
    
    print_success "Server code copied (build artifacts excluded)"
}

# Copy frontend code
copy_frontend() {
    local agentex_home="$1"
    print_status "Copying frontend code (excluding node_modules)..."
    
    # Use absolute paths to avoid directory change issues
    local FRONTEND_SOURCE_DIR="$agentex_home/agentex-web"
    local FRONTEND_DEST_DIR="$SCRIPT_DIR/$PACKAGE_DIR/agentex-web"
    
    # Copy frontend directory excluding node_modules and other build artifacts
    rsync -av \
        --exclude 'node_modules' \
        --exclude '.next' \
        --exclude '.env.local' \
        --exclude '.env.*.local' \
        --exclude 'npm-debug.log*' \
        --exclude 'yarn-debug.log*' \
        --exclude 'yarn-error.log*' \
        --exclude '.DS_Store' \
        "$FRONTEND_SOURCE_DIR/" "$FRONTEND_DEST_DIR/"
    
    print_success "Frontend code copied (node_modules excluded)"
}

# Copy SDK
copy_sdk() {
    local agentex_home="$1"
    print_status "Copying SDK (agentex-py, excluding build artifacts)..."
    
    # Use absolute paths for consistency  
    local SDK_SOURCE_DIR="$agentex_home/agentex-py"
    local SDK_DEST_DIR="$SCRIPT_DIR/$PACKAGE_DIR/agentex-py"
    
    # Copy SDK directory excluding build artifacts and cache
    rsync -av \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '*.pyo' \
        --exclude '.pytest_cache' \
        --exclude '.coverage' \
        --exclude 'dist' \
        --exclude 'build' \
        --exclude '*.egg-info' \
        --exclude '.venv' \
        --exclude 'venv' \
        --exclude '.DS_Store' \
        "$SDK_SOURCE_DIR/" "$SDK_DEST_DIR/"
    
    print_success "SDK copied (build artifacts excluded)"
}

# Copy tutorials
copy_tutorials() {
    local agentex_home="$1"
    print_status "Copying tutorials (excluding build artifacts)..."
    
    if [ -d "$agentex_home/tutorials" ]; then
        local TUTORIALS_SOURCE_DIR="$agentex_home/tutorials"
        local TUTORIALS_DEST_DIR="$SCRIPT_DIR/$PACKAGE_DIR/tutorials"
        
        # Copy tutorials excluding build artifacts and cache
        rsync -av \
            --exclude '__pycache__' \
            --exclude '*.pyc' \
            --exclude '*.pyo' \
            --exclude '.pytest_cache' \
            --exclude 'node_modules' \
            --exclude '.next' \
            --exclude '.venv' \
            --exclude 'venv' \
            --exclude '.DS_Store' \
            --exclude '.env.local' \
            --exclude '.env.*.local' \
            "$TUTORIALS_SOURCE_DIR/" "$TUTORIALS_DEST_DIR/"
        
        print_success "Tutorials copied (build artifacts excluded)"
    else
        print_warning "No tutorials directory found, skipping..."
    fi
}

# Service files not needed - deploy.sh is already on the VM

# Create simple README for tarball
create_simple_readme() {
    print_status "Creating simple README..."
    
    cat > "$SCRIPT_DIR/$PACKAGE_DIR/README.md" << 'EOF'
# AgentEx Alpha Package

This package contains the complete AgentEx source code for alpha testing.

## Contents

- `agentex/` - Server code with docker-compose.yml and Makefile
- `agentex-py/` - Python SDK with CLI tools
- `agentex-web/` - Frontend code with Makefile  
- `tutorials/` - Tutorial examples and documentation

## Deployment

This package contains only the source code. Deployment is handled by the deploy.sh script already installed on the VM.

```bash
# On the VM, run the pre-installed deploy script with the tarball:
/opt/agentex/deploy.sh /path/to/agentex-alpha-YYYYMMDD-HHMMSS.tar.gz
```

The deploy script (already on VM) will:
1. Extract the package to `/home/agentex/` and copy needed parts to `/opt/agentex/`
2. Start infrastructure services (docker-compose)
3. Install SDK dependencies and CLI tools
4. Install frontend dependencies (npm install)
5. Create convenient startup scripts
6. Generate comprehensive documentation

Note: This package excludes node_modules and build artifacts to keep it lightweight. Dependencies will be installed during deployment.

## Quick Start After Deployment

```bash
# SSH to the VM
ssh agentex@<vm-ip>

# Start the server (terminal 1)
cd /opt/agentex
./start-server.sh

# Start the frontend (terminal 2) 
cd /opt/agentex
./start-frontend.sh

# Use CLI tools
agentex --help
```

See `/opt/agentex/README-ALPHA.md` after deployment for complete instructions.
EOF

    print_success "Simple README created"
}

# Create the package tarball
create_tarball() {
    print_status "Creating tarball..."
    
    # Create tarball from the script directory
    tar -czf "$PACKAGE_NAME" -C "$SCRIPT_DIR" "$PACKAGE_DIR"
    
    print_success "Package created: $PACKAGE_NAME"
    print_status "Package size: $(du -h "$PACKAGE_NAME" | cut -f1)"
}

# Main execution
main() {
    # Handle help option
    if [ "$#" -ge 1 ] && [[ "$1" =~ ^(-h|--help)$ ]]; then
        usage
    fi
    
    print_status "Starting AgentEx Alpha package creation..."
    print_status "Working directory: $SCRIPT_DIR"
    
    # Determine AgentEx home directory
    local AGENTEX_HOME_DIR
    AGENTEX_HOME_DIR=$(determine_agentex_home "$@")
    
    # Determine and display source type
    if [ "$#" -ge 1 ]; then
        print_status "Using AgentEx home from command line argument: $AGENTEX_HOME_DIR"
    elif [ -n "${AGENTEX_HOME:-}" ]; then
        print_status "Using AgentEx home from AGENTEX_HOME environment variable: $AGENTEX_HOME_DIR"
    else
        print_status "Using AgentEx home from script directory (legacy): $AGENTEX_HOME_DIR"
    fi
    
    # Validate the directory
    if ! validate_agentex_home "$AGENTEX_HOME_DIR"; then
        exit 1
    fi
    print_success "Validated AgentEx home directory: $AGENTEX_HOME_DIR"
    
    check_dependencies
    create_package_structure
    copy_server "$AGENTEX_HOME_DIR"
    copy_frontend "$AGENTEX_HOME_DIR"  
    copy_sdk "$AGENTEX_HOME_DIR"
    copy_tutorials "$AGENTEX_HOME_DIR"
    create_simple_readme
    create_tarball
    
    print_success "Package creation completed successfully!"
    print_status "Package file: $PACKAGE_NAME"
    print_status ""
    print_status "To deploy on the VM:"
    print_status "1. Transfer $PACKAGE_NAME to your VM"
    print_status "2. Run: ./deploy-to-vm.sh <vm-ip> $PACKAGE_NAME"
    print_status "3. SSH in and start services as needed"
}

# Run main function
main "$@" 
