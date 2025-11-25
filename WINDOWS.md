# Windows Development Guide

This guide explains how to use Agentex on Windows. All functionality available through Makefiles is also available via PowerShell scripts.

## Prerequisites

### Required Software

1. **Python 3.12+** - Download from https://www.python.org/downloads/
2. **Docker Desktop for Windows** - Download from https://www.docker.com/products/docker-desktop/
    1. Alternatively, if you need a license-free version, explore: 
        https://rancherdesktop.io/
        https://podman.io/docs/installation
3. **Node.js** - Download from https://nodejs.org/
4. **uv (Python package manager)** - Install with PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## PowerShell Scripts

Each directory with a Makefile now has an equivalent `build.ps1` PowerShell script:

- `/build.ps1` - Root workspace commands
- `/agentex/build.ps1` - Backend development commands
- `/agentex-ui/build.ps1` - Frontend development commands

### PowerShell Execution Policy

If you encounter execution policy errors when running scripts, you may need to adjust your PowerShell execution policy:

```powershell
# Check current policy
Get-ExecutionPolicy

# Set policy for current user (recommended)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Getting Started

### 1. Setup the Repository

```powershell
# Clone the repository
git clone https://github.com/scaleapi/scale-agentex.git
cd scale-agentex

# Setup the workspace
.\build.ps1 repo-setup
```

### 2. Start the Backend (Terminal 1)

```powershell
cd agentex

# Create and activate virtual environment
uv venv
.venv\Scripts\Activate.ps1

# Install dependencies
uv sync

# Start development server with Docker Compose
.\build.ps1 dev
```

### 3. Start the Frontend (Terminal 2)

```powershell
cd agentex-ui

# Install dependencies
.\build.ps1 install

# Start development server
.\build.ps1 dev
```

The UI will be available at http://localhost:3000

### 4. Create and Run Your Agent (Terminal 3)

```powershell
# Install the Agentex SDK globally
uv tool install agentex-sdk

# Create a new agent
agentex init

# Navigate to your agent directory
cd your-agent-name

# Create and activate virtual environment
uv venv
.venv\Scripts\Activate.ps1
uv sync

# Start your agent
agentex agents run --manifest manifest.yaml
```

## Command Reference

### Root Workspace Commands

| Purpose | Command |
|---------|---------|
| Setup development environment | `.\build.ps1 repo-setup` |
| Show help | `.\build.ps1 help` |

### Backend (agentex/) Commands

| Purpose | Command |
|---------|---------|
| Install dependencies | `.\build.ps1 install` |
| Install with dev dependencies | `.\build.ps1 install-dev` |
| Start development server | `.\build.ps1 dev` |
| Stop development server | `.\build.ps1 dev-stop` |
| Run tests | `.\build.ps1 test` |
| Run unit tests | `.\build.ps1 test-unit` |
| Run integration tests | `.\build.ps1 test-integration` |
| Create migration | `.\build.ps1 migration -Name "migration_name"` |
| Apply migrations | `.\build.ps1 apply-migrations` |
| Serve documentation | `.\build.ps1 serve-docs` |
| Build Docker image | `.\build.ps1 docker-build` |
| Show all commands | `.\build.ps1 help` |

### Frontend (agentex-ui/) Commands

| Purpose | Command |
|---------|---------|
| Install dependencies | `.\build.ps1 install` |
| Start development server | `.\build.ps1 dev` |
| Run TypeScript type checking | `.\build.ps1 typecheck` |
| Run linting | `.\build.ps1 lint` |
| Build Docker image | `.\build.ps1 build` |
| Run Docker container | `.\build.ps1 run` |
| Stop Docker container | `.\build.ps1 stop` |
| Show all commands | `.\build.ps1 help` |

## Common Issues

### Port Conflicts

If you encounter port conflicts:

```powershell
# Find process using a specific port (e.g., 5003)
netstat -ano | findstr :5003

# Kill process by PID
Stop-Process -Id <PID> -Force
```

### Redis Conflicts

If you have Redis installed as a Windows service:

```powershell
# Stop Redis service
Stop-Service redis

# Or kill Redis process
Get-Process redis-server | Stop-Process
```

### Virtual Environment

To activate your virtual environment:

```powershell
# PowerShell
.venv\Scripts\Activate.ps1

# Command Prompt
.venv\Scripts\activate.bat
```

To deactivate:

```powershell
deactivate
```

### Docker Issues

Ensure Docker Desktop is running:

1. Open Docker Desktop
2. Wait for it to fully start (green indicator in system tray)
3. Verify with: `docker --version`

If Docker Compose fails:

```powershell
# Try stopping and cleaning up
cd agentex
.\build.ps1 dev-wipe

# Then start again
.\build.ps1 dev
```

## Testing

### Running Tests

```powershell
cd agentex

# Run all tests
.\build.ps1 test

# Run specific test file
.\build.ps1 test -File tests\unit\test_example.py

# Run tests matching a pattern
.\build.ps1 test -Name "crud"

# Run with coverage
.\build.ps1 test-cov

# Show test help
.\build.ps1 test-help
```

## Docker Builds

### Building Images

```powershell
# Backend
cd agentex
.\build.ps1 docker-build

# Frontend
cd agentex-ui
.\build.ps1 build-and-load
```

### Running Containers

```powershell
cd agentex-ui

# Run in foreground
.\build.ps1 run

# Run in background
.\build.ps1 run-detached

# View logs
.\build.ps1 logs

# Stop container
.\build.ps1 stop
```

## IDE Configuration

### VS Code

Add to your `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": ".venv\\Scripts\\python.exe",
  "python.terminal.activateEnvironment": true
}
```

### PyCharm

1. Open Settings → Project → Python Interpreter
2. Click gear icon → Add
3. Select "Existing environment"
4. Browse to `.venv\Scripts\python.exe`

## Differences from macOS/Linux

### Path Separators

Windows uses backslashes (`\`) instead of forward slashes (`/`) for paths:

- macOS/Linux: `.venv/bin/activate`
- Windows: `.venv\Scripts\Activate.ps1`

### Line Endings

Windows uses CRLF (`\r\n`) while Linux uses LF (`\n`). Git should handle this automatically, but if you encounter issues:

```powershell
# Configure Git to handle line endings
git config --global core.autocrlf true
```

### Shell Differences

Some commands work differently:

| Purpose | macOS/Linux | Windows PowerShell |
|---------|-------------|-------------------|
| List files | `ls` | `Get-ChildItem` or `ls` (alias) |
| Environment variables | `export VAR=value` | `$env:VAR = "value"` |
| Current directory | `pwd` | `Get-Location` or `pwd` (alias) |
| Remove files | `rm -rf folder` | `Remove-Item -Recurse -Force folder` |

## Getting Help

For any command, use the help flag:

```powershell
# Root workspace
.\build.ps1 help

# Backend
cd agentex
.\build.ps1 help

# Frontend
cd agentex-ui
.\build.ps1 help

# Agentex CLI
agentex --help
```

## Additional Resources

- [Main README](../README.md) - General getting started guide
- [Agentex Backend README](../agentex/README.md) - Backend-specific details
- [Agentex UI README](../agentex-ui/README.md) - Frontend-specific details
- [Python SDK](https://github.com/scaleapi/scale-agentex-python) - Agent development examples
- [Documentation](https://agentex.sgp.scale.com/docs) - Comprehensive concepts and guides

