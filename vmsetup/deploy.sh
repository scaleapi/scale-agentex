#!/bin/bash
# Agentex Alpha Deployment Script (v2.0)
# Deploys the full Agentex application suite from tarball
# Safe to run multiple times - fully idempotent

set -e

print_info() { echo "ℹ️  INFO: $1"; }
print_success() { echo "✅ SUCCESS: $1"; }
print_error() { echo "❌ ERROR: $1" >&2; }
print_warning() { echo "⚠️  WARNING: $1"; }

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path-to-agentex-tarball>"
    echo "Example: $0 /tmp/agentex-alpha-v1.2.3.tar.gz"
    echo ""
    echo "This script is safe to run multiple times."
    exit 1
fi

TARBALL_PATH="$1"
DEPLOY_DIR="/opt/agentex"

# === 1. INPUT VALIDATION (NEW ROBUST LOGIC) ===
print_info "🚀 Deploying Agentex Alpha from tarball: $1"
# Resolve the provided path to a canonical, absolute path.
# This handles relative paths (e.g., ./file, ../file) correctly.
# `readlink -f` is a standard tool for this.
TARBALL_PATH=$(readlink -f "$1")

# Now, check if the resolved file path actually exists and is a regular file.
# This check happens *before* any cleanup or deployment actions.
if [ ! -f "$TARBALL_PATH" ]; then
    print_error "File not found at the specified path."
    print_error "Input given: $1"
    print_error "Resolved to: $TARBALL_PATH"
    print_error "Please provide a correct path to the .tar.gz file."
    exit 1
fi
print_success "Found tarball at: $TARBALL_PATH"

# --- The rest of the script continues only if the file is found ---
DEPLOY_DIR="/opt/agentex"

# === CLEANUP PHASE ===
print_info "🧹 Cleaning up any previous deployments..."

# Stop ALL agentex-related containers (not just from current compose file)
print_info "Stopping all agentex-related Docker containers..."
if docker ps -q --filter "name=agentex" | head -1 | read; then
    docker ps -q --filter "name=agentex" | xargs -r docker stop
    print_info "Stopped running agentex containers"
fi

# Remove stopped agentex containers
if docker ps -aq --filter "name=agentex" | head -1 | read; then
    docker ps -aq --filter "name=agentex" | xargs -r docker rm
    print_info "Removed stopped agentex containers"
fi

# Stop any docker-compose services in deploy directory
find "$DEPLOY_DIR" -name "docker-compose.yml" -type f 2>/dev/null | while read compose_file; do
    compose_dir=$(dirname "$compose_file")
    print_info "Stopping services in $compose_dir"
    cd "$compose_dir"
    docker-compose down --remove-orphans || true
done

# Clean up any orphaned networks
docker network ls --filter "name=agentex" -q 2>/dev/null | xargs -r docker network rm 2>/dev/null || true

# Clean up any orphaned volumes
print_info "Cleaning up orphaned Docker volumes..."
docker volume prune -f || true

# === FILE CLEANUP ===
print_info "Cleaning previous deployment files..."
cd "$DEPLOY_DIR"

# Remove application directories and the virtual environment
for dir in agentex agentex-py agentex-web tutorials venv; do
    if [ -d "$dir" ]; then
        print_info "Removing $dir"
        rm -rf "$dir"
    fi
done

# Remove old startup scripts
for script in start-frontend.sh start-frontend-npm.sh manage-infrastructure.sh README-ALPHA.md; do
    if [ -f "$script" ]; then
        print_info "Removing old $script"
        rm -f "$script"
    fi
done

# === EXTRACTION PHASE ===
print_info "📦 Extracting application files to home directory..."

# Extract tarball to agentex user home directory first
HOME_DIR="/home/agentex"
cd "$HOME_DIR"

# Clean up any previous extractions in home directory
sudo -u agentex rm -rf agentex agentex-py agentex-web tutorials 2>/dev/null || true

# Extract tarball to home directory (strip top-level package directory)
sudo -u agentex tar -xzf "$TARBALL_PATH" -C "$HOME_DIR" --strip-components=1

print_info "📁 Copying necessary components to /opt/agentex..."

# Move only the needed directories to /opt/agentex (no tutorials)
if [ -d "$HOME_DIR/agentex" ]; then
    mv "$HOME_DIR/agentex" "$DEPLOY_DIR/"
    print_success "Moved agentex/ to /opt/agentex/"
else
    print_error "No agentex/ directory found in tarball!"
    exit 1
fi

if [ -d "$HOME_DIR/agentex-py" ]; then
    mv "$HOME_DIR/agentex-py" "$DEPLOY_DIR/"
    print_success "Moved agentex-py/ to /opt/agentex/"
else
    print_warning "No agentex-py/ directory found in tarball"
fi

if [ -d "$HOME_DIR/agentex-web" ]; then
    mv "$HOME_DIR/agentex-web" "$DEPLOY_DIR/"
    print_success "Moved agentex-web/ to /opt/agentex/"
else
    print_warning "No agentex-web/ directory found in tarball"
fi

# Tutorials stay in home directory - no moving needed
if [ -d "$HOME_DIR/tutorials" ]; then
    print_success "Tutorials available at ~/tutorials/ (left in home directory)"
else
    print_warning "No tutorials/ directory found in tarball"
fi

# === HOME DIRECTORY CLEANUP ===
print_info "🧹 Cleaning up home directory..."

# Remove the uploaded tarball (deploy script will be cleaned up by orchestrator)
TARBALL_NAME=$(basename "$TARBALL_PATH")
sudo -u agentex rm -f "$HOME_DIR/$TARBALL_NAME" || print_warning "Could not remove tarball from home directory"

# Remove any remaining extraction artifacts (be explicit about what we remove)
# Keep: tutorials/, any README files, hidden directories (.ssh, .bashrc, etc.)
for item in agentex agentex-py agentex-web; do
    if [ -d "$HOME_DIR/$item" ]; then
        sudo -u agentex rm -rf "$HOME_DIR/$item" || print_warning "Could not remove remaining $item directory"
    fi
done

# Remove any other files that came from the package but keep README files
sudo -u agentex find "$HOME_DIR" -maxdepth 1 -type f -name "*.md" ! -name "README*" -delete 2>/dev/null || true

print_success "Home directory cleaned - kept tutorials/, README files, and user config files"

# Ensure correct ownership for /opt/agentex
sudo chown -R agentex:agentex "$DEPLOY_DIR"

print_success "Application structure created:"
print_info "  /opt/agentex/agentex/          # Server + docker-compose.yml"
print_info "  /opt/agentex/agentex-py/       # Python SDK"
print_info "  /opt/agentex/agentex-web/      # Frontend"
print_info "  /home/agentex/tutorials/       # Tutorials"
print_info "  /home/agentex/                 # Clean home directory with only tutorials and config"

# === 5. VIRTUAL ENVIRONMENT CREATION (THE FIX IS HERE) ===
print_info "🐍 Creating Python 3.12 virtual environment with pip..."
# Use --seed to ensure pip is installed in the venv.
# Use --clear to avoid interactive prompts if the directory exists.
sudo -u agentex uv venv --seed --clear -p 3.12 /opt/agentex/venv
print_success "Virtual environment created successfully at /opt/agentex/venv"

# === DISCOVERY PHASE ===
print_info "🔍 Setting up application paths..."

# Set known paths after our structured copy
COMPOSE_DIR="$DEPLOY_DIR/agentex"
SERVER_PATH="$DEPLOY_DIR/agentex"
FRONTEND_PATH="$DEPLOY_DIR/agentex-web"

# Verify critical paths exist
if [ ! -f "$COMPOSE_DIR/docker-compose.yml" ]; then
    print_error "No docker-compose.yml found at expected location: $COMPOSE_DIR/docker-compose.yml"
    exit 1
fi
print_success "Found docker-compose.yml at: $COMPOSE_DIR/docker-compose.yml"

if [ ! -d "$SERVER_PATH" ]; then
    print_error "No server directory found at: $SERVER_PATH"
    exit 1
fi
print_success "Server directory confirmed: $SERVER_PATH"

if [ ! -d "$FRONTEND_PATH" ]; then
    print_warning "No frontend directory found at: $FRONTEND_PATH"
else
    print_success "Frontend directory confirmed: $FRONTEND_PATH"
fi

# === INFRASTRUCTURE STARTUP ===
print_info "🚀 Starting infrastructure services (detached mode)..."
cd "$COMPOSE_DIR"
docker-compose pull || print_warning "Some images failed to pull, continuing with cached versions"
docker-compose up -d --remove-orphans
print_info "⏳ Waiting for infrastructure services to start..."
sleep 45
print_info "📊 Infrastructure service status:"
docker-compose ps

# === SDK INSTALLATION ===
print_info "🐍 Installing Python SDK into virtual environment..."
SDK_PATH="$DEPLOY_DIR/agentex-py"
if [ -f "$SDK_PATH/pyproject.toml" ]; then
    print_info "Installing Agentex Python SDK from: $SDK_PATH"
    cd "$SDK_PATH"
    
    # Install in development mode into the dedicated venv
    sudo -u agentex /opt/agentex/venv/bin/pip install -e . --force-reinstall
    print_success "Agentex SDK installed into the Python 3.12 virtual environment."
else
    print_warning "No agentex-py/pyproject.toml found - continuing without SDK"
fi

# === TUTORIALS SETUP ===
print_info "📚 Tutorials are already in home directory from extraction - no copying needed"

# === SCRIPT CREATION ===
print_info "📝 Creating information scripts..."

# Info script explaining the setup (no start-server.sh since it runs in docker-compose)
sudo -u agentex tee "$DEPLOY_DIR/start-frontend.sh" > /dev/null <<'SCRIPT_EOF'
#!/bin/bash
# Agentex Frontend Information
echo "ℹ️  The Agentex frontend runs automatically via docker-compose!"
echo ""
echo "📊 Check status:"
echo "  agentex-status"
echo ""
echo "🌐 Access frontend:"
echo "  http://localhost:3000 (if accessing locally)"
echo "  Or use SSH port forwarding: ssh -L 3000:localhost:3000 agentex@<vm-ip>"
echo ""
echo "📋 Manage services:"
echo "  agentex-start    # Start all services (frontend + backend + infrastructure)"
echo "  agentex-stop     # Stop all services"
echo "  agentex-restart  # Restart all services"
echo "  agentex-logs     # View service logs"
echo ""
echo "🏠 Tutorials are available at: ~/tutorials/"
SCRIPT_EOF

# Alternative frontend script - run with npm directly
sudo -u agentex tee "$DEPLOY_DIR/start-frontend-npm.sh" > /dev/null <<'SCRIPT_EOF'
#!/bin/bash
# Start Agentex Frontend with npm (alternative to docker-compose)

echo "🎨 Starting Agentex Frontend with npm..."
cd /opt/agentex/agentex-web

# Kill any existing frontend processes
pkill -f "next dev" 2>/dev/null || true
pkill -f "npm.*dev" 2>/dev/null || true

echo "Installing dependencies if needed..."
npm install

echo "Starting frontend on 0.0.0.0:3000 (accessible externally)..."
echo "Access at: http://localhost:3000"
echo "Or via SSH port forwarding: ssh -L 3000:localhost:3000 agentex@<vm-ip>"
echo ""
echo "To stop: pkill -f 'next dev'"
echo ""

# Start in background with output to log file
nohup npm run dev -- --hostname 0.0.0.0 > /opt/agentex/logs/frontend.log 2>&1 &
echo "Frontend started in background. Check logs: tail -f /opt/agentex/logs/frontend.log"
echo "Process ID: $!"
SCRIPT_EOF

# Infrastructure management script
sudo -u agentex tee "$DEPLOY_DIR/manage-infrastructure.sh" > /dev/null <<'SCRIPT_EOF'
#!/bin/bash
# Manage Agentex Infrastructure Services
COMMAND="${1:-status}"
cd /opt/agentex
case "$COMMAND" in
    "start") docker-compose up -d --remove-orphans ;;
    "stop") docker-compose down --remove-orphans ;;
    "restart") docker-compose restart ;;
    "logs") docker-compose logs -f ;;
    "clean") docker-compose down --remove-orphans --volumes && docker system prune -f ;;
    "status"|*) docker-compose ps; echo "Usage: $0 [start|stop|restart|logs|clean|status]" ;;
esac
SCRIPT_EOF

# Make scripts executable
chmod +x "$DEPLOY_DIR/start-frontend.sh" 
chmod +x "$DEPLOY_DIR/start-frontend-npm.sh"
chmod +x "$DEPLOY_DIR/manage-infrastructure.sh"

# === BASH CONFIGURATION ===
print_info "⚙️  Updating user configuration..."
sudo -u agentex sed -i '/# Agentex Alpha Testing Aliases/,$d' /home/agentex/.bashrc
sudo -u agentex tee -a /home/agentex/.bashrc > /dev/null <<'ALIAS_EOF'

# Agentex Alpha Testing Aliases (Updated: $(date))
alias agentex-logs='(cd /opt/agentex/agentex && docker-compose logs -f)'
alias agentex-status='(cd /opt/agentex/agentex && docker-compose ps)'
alias agentex-restart='(cd /opt/agentex/agentex && docker-compose restart)'
alias agentex-stop='(cd /opt/agentex/agentex && docker-compose down --remove-orphans)'
alias agentex-start='(cd /opt/agentex/agentex && docker-compose up -d --remove-orphans)'
alias agentex-frontend='(cd /opt/agentex && ./start-frontend.sh)'
alias agentex-frontend-npm='(cd /opt/agentex && ./start-frontend-npm.sh)'
alias agentex-infra='(cd /opt/agentex && ./manage-infrastructure.sh)'
alias agentex-clean='(cd /opt/agentex && ./manage-infrastructure.sh clean)'
alias agentex-env='source /opt/agentex/venv/bin/activate'
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

source /opt/agentex/venv/bin/activate

ALIAS_EOF

# === README CREATION ===
sudo -u agentex tee "$DEPLOY_DIR/README-ALPHA.md" > /dev/null <<README_EOF
# Agentex Alpha Testing Environment

Welcome! Everything is pre-configured and ready to use.

**Last Deployed:** $(date)

## 🚀 Quick Start

Your infrastructure services (databases, etc.) start automatically in the background.

### 1. Activate the Environment (Optional, but recommended)

To use the `agentex` CLI or other Python tools directly, activate the virtual environment:
\`\`\`bash
source venv/bin/activate
# Or use the alias:
agentex-env
\`\`\`
*Note: The start scripts below do this automatically for you.*

### 2. Start the Application Components

**Infrastructure Services Auto-Start via Docker Compose:**
- Backend API: http://localhost:5003 (auto-started)
- Temporal UI: http://localhost:8080

**Frontend Options:**
- Docker Compose: Included but you can start it manually if needed
- **NPM (Recommended)**: \`./start-frontend-npm.sh\` - runs in background on 0.0.0.0:3000

**Check status:**
\`\`\`bash
agentex-status  # Check infrastructure services
./start-frontend.sh  # Frontend access information
./start-frontend-npm.sh  # Start frontend with npm (runs in background)
\`\`\`

## 🔧 Management Commands

- \`agentex-status\`: Check status of infrastructure services.
- \`agentex-logs\`: Follow the logs from all services.
- \`agentex-restart\`: Restart all services.
- \`agentex-clean\`: Full cleanup (stops and removes containers and volumes).

## 📁 Environment Details
- **Python Environment**: \`/opt/agentex/venv\` (Python 3.12)
- **Server Code**: \`$SERVER_PATH\`
- **Frontend Code**: \`$FRONTEND_PATH\`
- **Infrastructure Config**: \`$COMPOSE_DIR\`

Happy coding! 🎉
README_EOF

# === FINAL VALIDATION ===
print_success "🎉 Agentex Alpha deployment successful!"
print_info "📖 Full instructions for the user are in: /opt/agentex/README-ALPHA.md"