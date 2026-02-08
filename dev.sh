#!/bin/bash
#
# Agentex Development Script
# Starts all services (backend + frontend) with a single command
# Delegates to existing Makefiles - this is an orchestration layer, not a replacement
#
# Usage:
#   ./dev.sh          Start all services
#   ./dev.sh setup    Install all prerequisites (macOS)
#   ./dev.sh stop     Stop all services
#   ./dev.sh logs     Show logs
#   ./dev.sh status   Check status of services
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/.dev-logs"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# SETUP / INSTALLATION
# =============================================================================

install_prerequisites() {
    echo ""
    echo "========================================"
    echo "   Agentex Development Setup           "
    echo "========================================"
    echo ""

    # Check OS
    if [[ "$OSTYPE" != "darwin"* ]]; then
        log_warn "This setup script is optimized for macOS."
        log_warn "For Linux, please install manually: Python 3.12+, uv, Docker, Node.js"
        exit 1
    fi

    # Step 1: Install Homebrew if not present
    log_info "Checking Homebrew..."
    if ! command -v brew &> /dev/null; then
        log_info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add brew to PATH for Apple Silicon
        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
        log_success "Homebrew installed"
    else
        log_success "Homebrew already installed"
    fi

    # Step 2: Install Python 3.12+ if needed
    log_info "Checking Python version..."
    local python_version=""
    if command -v python3 &> /dev/null; then
        python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    fi

    if [[ -z "$python_version" ]] || [[ "$(echo "$python_version < 3.12" | bc -l)" == "1" ]]; then
        log_info "Installing Python 3.12..."
        brew install python@3.12
        log_success "Python 3.12 installed"
    else
        log_success "Python $python_version already installed"
    fi

    # Step 3: Install uv
    log_info "Checking uv..."
    if ! command -v uv &> /dev/null; then
        log_info "Installing uv (fast Python package manager)..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Source the env to get uv in PATH
        source "$HOME/.local/bin/env" 2>/dev/null || true
        export PATH="$HOME/.local/bin:$PATH"
        log_success "uv installed"
    else
        log_success "uv already installed"
    fi

    # Step 4: Check Docker daemon is running (works with Docker Desktop or Rancher)
    log_info "Checking Docker..."
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker Desktop or Rancher Desktop."
        exit 1
    fi
    log_success "Docker is running"

    # Step 5: Install Node.js
    log_info "Checking Node.js..."
    if ! command -v node &> /dev/null; then
        log_info "Installing Node.js..."
        brew install node
        log_success "Node.js installed"
    else
        log_success "Node.js already installed ($(node --version))"
    fi

    # Step 6: Stop local Redis if running
    log_info "Checking for local Redis..."
    if brew services list 2>/dev/null | grep -q "redis.*started"; then
        log_info "Stopping local Redis (conflicts with Docker Redis)..."
        brew services stop redis
        log_success "Local Redis stopped"
    elif lsof -i :6379 &> /dev/null; then
        log_warn "Something is using port 6379. You may need to stop it manually."
    else
        log_success "No conflicting Redis found"
    fi

    # Step 7: Install agentex-sdk CLI
    log_info "Checking agentex CLI..."
    if ! command -v agentex &> /dev/null; then
        log_info "Installing agentex-sdk..."
        uv tool install agentex-sdk
        log_success "agentex-sdk installed"
    else
        log_success "agentex CLI already installed"
    fi

    # Step 8: Install backend dependencies
    log_info "Installing backend dependencies..."
    cd "$SCRIPT_DIR/agentex"
    if [ ! -d ".venv" ]; then
        uv venv
    fi
    uv sync --group dev
    log_success "Backend dependencies installed"
    cd "$SCRIPT_DIR"

    # Step 9: Install frontend dependencies
    log_info "Installing frontend dependencies..."
    cd "$SCRIPT_DIR/agentex-ui"
    npm install
    log_success "Frontend dependencies installed"
    cd "$SCRIPT_DIR"

    echo ""
    echo "========================================"
    log_success "Setup complete!"
    echo "========================================"
    echo ""
    echo "You can now run:"
    echo "  ./dev.sh              # Start the development environment"
    echo ""
    echo "Once running, create your first agent:"
    echo "  agentex init          # Create a new agent"
    echo "  cd <your-agent-name>"
    echo "  uv venv && source .venv/bin/activate && uv sync"
    echo "  agentex agents run --manifest manifest.yaml"
    echo ""
}

# =============================================================================
# PREREQUISITES CHECK (auto-installs if missing)
# =============================================================================

ensure_prerequisites() {
    log_info "Checking prerequisites..."

    local needs_install=false

    # Check what's missing (things we can auto-install)
    if ! command -v brew &> /dev/null && [[ "$OSTYPE" == "darwin"* ]]; then
        needs_install=true
    fi

    if ! command -v uv &> /dev/null; then
        needs_install=true
    fi

    if ! command -v node &> /dev/null; then
        needs_install=true
    fi

    if ! command -v agentex &> /dev/null; then
        needs_install=true
    fi

    # Docker must be running (can't auto-install - user chooses Docker Desktop or Rancher)
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker Desktop or Rancher Desktop."
        exit 1
    fi

    if [ "$needs_install" = true ]; then
        log_info "Some prerequisites missing - installing automatically..."
        install_prerequisites
    else
        log_success "All prerequisites found"
    fi
}

check_redis_conflict() {
    # Check if local redis is running on port 6379
    if lsof -i :6379 &> /dev/null; then
        log_warn "Port 6379 is in use. This may conflict with Docker Redis."
        log_warn "If you have local Redis running, stop it with: brew services stop redis"
    fi
}

setup_log_dir() {
    mkdir -p "$LOG_DIR"
}

start_backend() {
    log_info "Starting backend services..."

    cd "$SCRIPT_DIR/agentex"

    # Delegate to Makefile (handles deps + docker compose)
    make dev > "$LOG_DIR/backend.log" 2>&1 &
    local pid=$!
    echo $pid > "$BACKEND_PID_FILE"

    log_success "Backend starting (PID: $pid)"
    log_info "Backend logs: tail -f $LOG_DIR/backend.log"

    cd "$SCRIPT_DIR"
}

start_frontend() {
    log_info "Starting frontend..."

    cd "$SCRIPT_DIR/agentex-ui"

    # Delegate to Makefile (handles deps + dev server)
    make dev > "$LOG_DIR/frontend.log" 2>&1 &
    local pid=$!
    echo $pid > "$FRONTEND_PID_FILE"

    log_success "Frontend starting (PID: $pid)"
    log_info "Frontend logs: tail -f $LOG_DIR/frontend.log"

    cd "$SCRIPT_DIR"
}

wait_for_backend() {
    log_info "Waiting for backend to be healthy..."

    local max_attempts=90
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        # Check if swagger endpoint responds (indicates FastAPI is ready)
        if curl -s http://localhost:5003/openapi.json > /dev/null 2>&1; then
            log_success "Backend is healthy!"
            return 0
        fi

        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done

    echo ""
    log_warn "Backend health check timed out. It may still be starting up."
    log_info "Check logs with: ./dev.sh logs"
}

stop_services() {
    log_info "Stopping all services..."

    # Stop frontend
    if [ -f "$FRONTEND_PID_FILE" ]; then
        local frontend_pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$frontend_pid" 2>/dev/null; then
            kill "$frontend_pid" 2>/dev/null || true
            log_success "Frontend stopped"
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi

    # Stop backend (docker compose)
    cd "$SCRIPT_DIR/agentex"
    docker compose down 2>/dev/null || true
    log_success "Backend stopped"

    if [ -f "$BACKEND_PID_FILE" ]; then
        rm -f "$BACKEND_PID_FILE"
    fi

    cd "$SCRIPT_DIR"

    log_success "All services stopped"
}

show_logs() {
    local service="${1:-all}"

    case "$service" in
        backend)
            tail -f "$LOG_DIR/backend.log"
            ;;
        frontend)
            tail -f "$LOG_DIR/frontend.log"
            ;;
        all|*)
            log_info "Showing all logs (Ctrl+C to exit)"
            tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
            ;;
    esac
}

show_status() {
    echo ""
    echo "=== Agentex Development Status ==="
    echo ""

    # Check backend
    echo -n "Backend (Docker): "
    if docker compose -f "$SCRIPT_DIR/agentex/docker-compose.yml" ps 2>/dev/null | grep -q "Up"; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${RED}Stopped${NC}"
    fi

    # Check frontend
    echo -n "Frontend (Next.js): "
    if [ -f "$FRONTEND_PID_FILE" ] && kill -0 "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${RED}Stopped${NC}"
    fi

    echo ""
    echo "=== URLs ==="
    echo "Frontend:     http://localhost:3000"
    echo "Backend API:  http://localhost:5003"
    echo "Swagger:      http://localhost:5003/swagger"
    echo "Temporal UI:  http://localhost:8080"
    echo ""
}

start_all() {
    ensure_prerequisites
    check_redis_conflict
    setup_log_dir

    echo ""
    echo "========================================"
    echo "   Starting Agentex Development Env    "
    echo "========================================"
    echo ""

    start_backend
    start_frontend

    echo ""
    log_info "Services are starting up..."
    echo ""
    echo "=== URLs (will be ready shortly) ==="
    echo "Frontend:     http://localhost:3000"
    echo "Backend API:  http://localhost:5003"
    echo "Swagger:      http://localhost:5003/swagger"
    echo "Temporal UI:  http://localhost:8080"
    echo ""
    echo "=== Commands ==="
    echo "./dev.sh logs      - View all logs"
    echo "./dev.sh logs backend  - View backend logs"
    echo "./dev.sh logs frontend - View frontend logs"
    echo "./dev.sh status    - Check service status"
    echo "./dev.sh stop      - Stop all services"
    echo ""

    # Wait for backend to be healthy
    wait_for_backend

    echo ""
    log_success "Development environment is ready!"
    log_info "Open http://localhost:3000 to access the UI"
    echo ""
    log_info "To create an agent, in a new terminal run:"
    echo "  agentex init"
    echo "  cd <your-agent-name>"
    echo "  uv venv && source .venv/bin/activate && uv sync"
    echo "  agentex agents run --manifest manifest.yaml"
    echo ""
}

# Main command router
case "${1:-start}" in
    start|"")
        start_all
        ;;
    setup)
        install_prerequisites
        ;;
    stop)
        stop_services
        ;;
    logs)
        show_logs "$2"
        ;;
    status)
        show_status
        ;;
    restart)
        stop_services
        sleep 2
        start_all
        ;;
    help|--help|-h)
        echo "Agentex Development Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  (none)    Start everything (auto-installs prerequisites if needed)"
        echo "  setup     Just install prerequisites without starting"
        echo "  stop      Stop all services"
        echo "  restart   Restart all services"
        echo "  logs      Show logs (logs backend|frontend|all)"
        echo "  status    Check service status"
        echo ""
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run './dev.sh help' for usage"
        exit 1
        ;;
esac
