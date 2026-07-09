#!/bin/bash
#
# Agentex Development Script
# Starts all services (backend + frontend) with a single command
# Delegates to existing Makefiles - this is an orchestration layer, not a replacement
#
# Usage:
#   ./dev.sh          Start all services (Docker backend + frontend)
#   ./dev.sh local    Start all services WITHOUT Docker (embedded pg/redis, local temporal/mongo/otel)
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
MODE_FILE="$LOG_DIR/mode"  # records "docker" or "local" so stop/status know how to act

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
    echo "  ./dev.sh              # Start the development environment (Docker)"
    echo "  ./dev.sh local        # Start without Docker (embedded services)"
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

    if [ "$needs_install" = true ]; then
        log_info "Some prerequisites missing - installing automatically..."
        install_prerequisites
    else
        log_success "All prerequisites found"
    fi
}

require_docker() {
    # Docker must be running for the Docker-based backend (can't auto-install -
    # the user chooses Docker Desktop or Rancher).
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker Desktop or Rancher Desktop."
        log_info "Tip: run './dev.sh local' to start the backend WITHOUT Docker."
        exit 1
    fi
}

# Install the OpenTelemetry Collector (contrib). It is NOT distributed via Homebrew,
# so we fetch the official release binary for this OS/arch. Best-effort: OTel is
# optional, so any failure returns non-zero and the caller just warns.
install_otel_collector() {
    local ver="0.156.0"
    local os arch
    case "$(uname -s)" in
        Darwin) os=darwin ;;
        Linux)  os=linux ;;
        *) log_warn "Unsupported OS for otel auto-install."; return 1 ;;
    esac
    case "$(uname -m)" in
        arm64|aarch64) arch=arm64 ;;
        x86_64|amd64)  arch=amd64 ;;
        *) log_warn "Unsupported arch for otel auto-install."; return 1 ;;
    esac

    local tarball="otelcol-contrib_${ver}_${os}_${arch}.tar.gz"
    local base="https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${ver}"

    local dest
    if [ -w /opt/homebrew/bin ]; then dest=/opt/homebrew/bin
    elif [ -w /usr/local/bin ]; then dest=/usr/local/bin
    else dest="$HOME/.local/bin"; mkdir -p "$dest"; fi

    log_info "Installing OpenTelemetry collector v${ver} (release binary; not in Homebrew)..."
    local tmp; tmp="$(mktemp -d)"
    if ! curl -fL -o "$tmp/otel.tar.gz" "${base}/${tarball}"; then
        rm -rf "$tmp"; return 1
    fi
    # Verify against the release checksums file when available.
    if curl -fsL -o "$tmp/checksums.txt" "${base}/otelcol-contrib_${ver}_checksums.txt"; then
        local expected actual
        expected="$(grep " ${tarball}\$" "$tmp/checksums.txt" | awk '{print $1}')"
        actual="$(shasum -a 256 "$tmp/otel.tar.gz" | awk '{print $1}')"
        if [ -n "$expected" ] && [ "$expected" != "$actual" ]; then
            log_warn "otel collector checksum mismatch; skipping install."
            rm -rf "$tmp"; return 1
        fi
    fi
    if ! tar xzf "$tmp/otel.tar.gz" -C "$tmp" otelcol-contrib; then
        rm -rf "$tmp"; return 1
    fi
    install -m 0755 "$tmp/otelcol-contrib" "$dest/otelcol-contrib" || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"
    # Make it findable this session if we landed in ~/.local/bin.
    case ":$PATH:" in *":$dest:"*) : ;; *) export PATH="$dest:$PATH" ;; esac
    log_success "otel collector installed to $dest/otelcol-contrib"
}

ensure_local_service_binaries() {
    # `local` mode runs Postgres/Redis/Temporal with no install (bundled /
    # auto-downloaded). MongoDB is REQUIRED for the full stack (the Temporal worker
    # needs it) so we always ensure it and FAIL FAST if we can't. The OTel collector is
    # genuinely optional, so its install is best-effort. Honors the runner opt-out
    # flags forwarded in "$@": --lean/--no-otel skip the OTel install, and an external
    # --mongo-uri means the runner won't launch a local mongod (so no local install).
    local want_mongo=true want_otel=true
    for arg in "$@"; do
        case "$arg" in
            --no-otel)  want_otel=false ;;
            --lean)     want_otel=false ;;
            --mongo-uri|--mongo-uri=*) want_mongo=false ;;
        esac
    done

    # ----- MongoDB: required (unless pointing at an external --mongo-uri) -----
    if [ "$want_mongo" = true ]; then
        if command -v mongod &> /dev/null; then
            log_success "mongod already installed"
        elif command -v brew &> /dev/null; then
            log_info "Installing MongoDB (mongod) via Homebrew (required for local mode)..."
            brew tap mongodb/brew &> /dev/null || true
            # Modern Homebrew refuses to install from an untrusted tap; trust it first.
            brew trust mongodb/brew &> /dev/null || true
            if ! brew install mongodb-community; then
                log_error "MongoDB install failed, but it is REQUIRED for local mode."
                log_error "Install mongod manually, or pass --mongo-uri to use an external MongoDB."
                exit 1
            fi
        else
            log_error "mongod is not installed and Homebrew is unavailable to install it."
            log_error "MongoDB is REQUIRED for local mode — install mongod (https://www.mongodb.com/docs/manual/administration/install-community/),"
            log_error "or pass --mongo-uri to use an external MongoDB."
            exit 1
        fi
    else
        log_info "Using external MongoDB (--mongo-uri); skipping local mongod install."
    fi

    # ----- OTel collector: optional -----
    if [ "$want_otel" = true ]; then
        if command -v otelcol-contrib &> /dev/null || command -v otelcol &> /dev/null; then
            log_success "otel collector already installed"
        else
            install_otel_collector || log_warn "otel collector install failed; telemetry will be skipped (the app runs fine without it)."
        fi
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
    log_info "Starting backend services (Docker)..."

    cd "$SCRIPT_DIR/agentex"

    # Delegate to Makefile (handles deps + docker compose)
    make dev > "$LOG_DIR/backend.log" 2>&1 &
    local pid=$!
    echo $pid > "$BACKEND_PID_FILE"
    echo "docker" > "$MODE_FILE"

    log_success "Backend starting (PID: $pid)"
    log_info "Backend logs: tail -f $LOG_DIR/backend.log"

    cd "$SCRIPT_DIR"
}

start_backend_local() {
    log_info "Starting backend services (local, no Docker)..."

    cd "$SCRIPT_DIR/agentex"

    # Run the docker-free runner DIRECTLY via `uv run` (not `make`) so a SIGTERM
    # from `./dev.sh stop` is forwarded straight to the Python supervisor, which
    # tears down the embedded datastores cleanly. --group dev-local pulls
    # pgserver/redislite/greenlet.
    uv run --group dev-local python -m scripts.dev_local "$@" > "$LOG_DIR/backend.log" 2>&1 &
    local pid=$!
    echo $pid > "$BACKEND_PID_FILE"
    echo "local" > "$MODE_FILE"

    log_success "Backend starting (PID: $pid)"
    log_info "Backend logs: tail -f $LOG_DIR/backend.log"

    cd "$SCRIPT_DIR"
}

# Kill a PID and all its descendants. The frontend runs as make -> npm -> next, so
# killing only the recorded (make) PID orphans the npm/next children; over repeated
# runs those pile up and hold ports 3000, 3001, 3002, ... This walks the tree.
kill_tree() {
    local pid=$1
    [ -z "$pid" ] && return 0
    local child
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
}

# Sweep any stray `next dev` server belonging to THIS repo's UI. Scoped by absolute
# path so it never touches another project's dev server, and catches orphans whose
# parent (make/npm) has already exited.
sweep_stray_frontends() {
    pkill -f "$SCRIPT_DIR/agentex-ui/node_modules/.bin/next" 2>/dev/null || true
}

start_frontend() {
    log_info "Starting frontend..."

    # Clear any stale frontend from a previous run first, so `next dev` can bind :3000
    # instead of silently climbing to :3001/:3002/...
    sweep_stray_frontends

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

# Echo the recorded backend mode ("docker" or "local"), defaulting to docker.
current_mode() {
    if [ -f "$MODE_FILE" ]; then cat "$MODE_FILE"; else echo "docker"; fi
}

stop_services() {
    log_info "Stopping all services..."

    # Stop frontend: kill the whole make -> npm -> next tree, then sweep any strays
    # orphaned by earlier runs (their parent may already be gone).
    if [ -f "$FRONTEND_PID_FILE" ]; then
        kill_tree "$(cat "$FRONTEND_PID_FILE")"
        rm -f "$FRONTEND_PID_FILE"
    fi
    sweep_stray_frontends
    log_success "Frontend stopped"

    # Stop backend according to how it was started.
    local mode
    mode=$(current_mode)

    if [ "$mode" = "local" ]; then
        if [ -f "$BACKEND_PID_FILE" ]; then
            local backend_pid
            backend_pid=$(cat "$BACKEND_PID_FILE")
            if kill -0 "$backend_pid" 2>/dev/null; then
                log_info "Stopping local backend (PID: $backend_pid) — tearing down embedded services..."
                kill -TERM "$backend_pid" 2>/dev/null || true
                local waited=0
                while kill -0 "$backend_pid" 2>/dev/null && [ "$waited" -lt 20 ]; do
                    sleep 1
                    waited=$((waited + 1))
                done
                if kill -0 "$backend_pid" 2>/dev/null; then
                    log_warn "Backend did not stop gracefully; forcing."
                    kill -9 "$backend_pid" 2>/dev/null || true
                fi
            fi
        fi
        log_success "Backend stopped"
    else
        cd "$SCRIPT_DIR/agentex"
        docker compose down 2>/dev/null || true
        cd "$SCRIPT_DIR"
        log_success "Backend stopped"
    fi

    rm -f "$BACKEND_PID_FILE" "$MODE_FILE"

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
    local mode
    mode=$(current_mode)

    echo ""
    echo "=== Agentex Development Status ==="
    echo ""

    # Check backend
    echo -n "Backend ($mode): "
    if [ "$mode" = "local" ]; then
        if [ -f "$BACKEND_PID_FILE" ] && kill -0 "$(cat "$BACKEND_PID_FILE")" 2>/dev/null; then
            echo -e "${GREEN}Running${NC}"
        else
            echo -e "${RED}Stopped${NC}"
        fi
    else
        if docker compose -f "$SCRIPT_DIR/agentex/docker-compose.yml" ps 2>/dev/null | grep -q "Up"; then
            echo -e "${GREEN}Running${NC}"
        else
            echo -e "${RED}Stopped${NC}"
        fi
    fi

    # Check frontend — report by what's actually serving :3000, not just the recorded
    # PID (make/npm can exit while next keeps serving, and vice versa).
    echo -n "Frontend (Next.js): "
    if lsof -nP -iTCP:3000 -sTCP:LISTEN &> /dev/null \
       || { [ -f "$FRONTEND_PID_FILE" ] && kill -0 "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null; }; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${RED}Stopped${NC}"
    fi

    # Temporal UI port differs: local dev server uses 8233, Docker UI uses 8080.
    local temporal_ui="http://localhost:8080"
    [ "$mode" = "local" ] && temporal_ui="http://localhost:8233"

    echo ""
    echo "=== URLs ==="
    echo "Frontend:     http://localhost:3000"
    echo "Backend API:  http://localhost:5003"
    echo "Swagger:      http://localhost:5003/swagger"
    echo "Temporal UI:  $temporal_ui"
    echo ""
}

start_all() {
    ensure_prerequisites
    require_docker
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

start_all_local() {
    ensure_prerequisites                # no Docker requirement in local mode
    ensure_local_service_binaries "$@"  # ensure mongod (required) + otel (optional); honors --mongo-uri/--lean
    setup_log_dir

    echo ""
    echo "========================================"
    echo "   Starting Agentex Development Env (Local, no Docker)   "
    echo "========================================"
    echo ""

    start_backend_local "$@"
    start_frontend

    echo ""
    log_info "Services are starting up (embedded Postgres/Redis + Temporal + MongoDB [required] + OTel [optional])..."
    echo ""
    echo "=== URLs (will be ready shortly) ==="
    echo "Frontend:     http://localhost:3000"
    echo "Backend API:  http://localhost:5003"
    echo "Swagger:      http://localhost:5003/swagger"
    echo "Temporal UI:  http://localhost:8233"
    echo ""
    echo "=== Commands ==="
    echo "./dev.sh logs      - View all logs"
    echo "./dev.sh logs backend  - View backend logs"
    echo "./dev.sh logs frontend - View frontend logs"
    echo "./dev.sh status    - Check service status"
    echo "./dev.sh stop      - Stop all services"
    echo ""

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
    local)
        shift  # drop the 'local' subcommand so only flags reach dev_local.py
        start_all_local "$@"
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
        # Restart in whatever mode was last used. stop_services clears MODE_FILE,
        # so capture the mode first. (Local restarts use default flags — the original
        # runner flags are not persisted.)
        restart_mode=$(current_mode)
        stop_services
        sleep 2
        if [ "$restart_mode" = "local" ]; then
            start_all_local
        else
            start_all
        fi
        ;;
    help|--help|-h)
        echo "Agentex Development Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  (none)    Start everything with Docker (auto-installs prerequisites if needed)"
        echo "  local     Start everything WITHOUT Docker (embedded pg/redis + Temporal + MongoDB + OTel)"
        echo "            MongoDB is required for the full stack and is auto-installed; OTel is optional."
        echo "            Flags pass through to the runner, e.g.:"
        echo "              ./dev.sh local --full        # whole stack (default)"
        echo "              ./dev.sh local --lean        # Postgres + Redis + API + MongoDB only"
        echo "              ./dev.sh local --no-temporal # skip Temporal + worker"
        echo "  setup     Just install prerequisites without starting"
        echo "  stop      Stop all services (Docker or local)"
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
