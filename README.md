# Agentex - Quick Start Development Guide

Build and deploy intelligent agents with ease using Agentex's comprehensive platform.

## 🚀 Quick 3-Terminal Setup

Get started with Agentex in under 5 minutes using our three-terminal workflow:

### Prerequisites

#### Python Version Requirement ⚠️

**IMPORTANT**: Agentex SDK requires Python 3.12 or higher. 

First, check your current Python version:
```bash
python --version
# or
python3 --version
```

If you're not on Python 3.12+, follow the setup instructions below for your preferred Python version manager:

##### Option 1: Using pyenv (Recommended for macOS/Linux)
```bash
# Install pyenv if not already installed
curl https://pyenv.run | bash
# or on macOS: brew install pyenv

# Install and set Python 3.12
pyenv install 3.12.0
pyenv global 3.12.0  # Set globally
# or pyenv local 3.12.0  # Set for current project only

# Verify installation
python --version  # Should show Python 3.12.x
```

##### Option 2: Using conda/miniconda
```bash
# Create new environment with Python 3.12
conda create -n agentex-sdk python=3.12
conda activate agentex-sdk

# Verify installation
python --version  # Should show Python 3.12.x
```

##### Option 3: Using uv (Fast Python installer)
```bash
# Install uv if not already installed
pip install uv

# Install Python 3.12 with uv
uv python install 3.12

# Create and activate virtual environment
uv venv --python 3.12
source .venv/bin/activate

# Verify installation
python --version  # Should show Python 3.12.x
```

#### Install underlying dependencies

```bash
# Install required tools (make sure you're using Python 3.12+)
pip install uv
brew install docker docker-compose node

# Optional but recommended - Docker management UI
brew install lazydocker
echo "alias lzd='lazydocker'" >> ~/.zshrc
source ~/.zshrc

# In the main agentex directory
# Do this if you need to work with packages from scale-pypi such as egp_services/scale-oldowan
source ./setup-codeartifact.sh
```

#### Install the SDK

**⚠️ Important**: Verify you're using Python 3.12+ before installing:
```bash
python --version  # Must show 3.12.x or higher
```

##### Option 0: Editable Install (Recommended for Development)

Use this if you want to:
- Contribute to agentex-sdk development
- Modify SDK source code and see changes immediately
- Debug SDK issues or add custom features
- Stay on the bleeding edge with latest unreleased features

```bash
# Clone the SDK repository
cd ../  # Go up one directory from your current project
git clone git@github.com:scaleapi/agentex-python.git
cd agentex-python

# Create virtual environment with Python 3.12
uv venv
source .venv/bin/activate  # Activate the virtual environment

# Install in editable mode - changes to source code are reflected immediately
uv sync  # This installs the SDK in development/editable mode

# Verify editable installation
python -c "import agentex; print(f'agentex-sdk version: {agentex.__version__} (editable)')"
```

**What this does**: An editable install links your local SDK code to your Python environment. When you modify the SDK source files, the changes are immediately available without reinstalling - perfect for development!

##### Option 1: Standard Installation

Use this for normal usage when you just want to use the SDK:

```bash
# Install via pip
pip install agentex-sdk

# Install via uv 
uv add agentex-sdk  # If you have an existing project
uv pip install agentex-sdk # else

# Verify you got the latest version (should be 0.2.4 or higher)
python -c "import agentex; print(f'agentex-sdk version: {agentex.__version__}')"
```

**Troubleshooting**: If you see version 0.0.1, it means you're using Python < 3.12. The latest agentex-sdk versions require Python 3.12+.


---

## Terminal 1: Backend Services

Set up and start all backend services:

```bash
cd agentex/
# Optional: make clean to clear venv and uv.lock

# Note: no need to source the venv because it is running in docker-compose
make dev      # Installs uv dependencies and starts Docker services

# Optional: Monitor Docker containers with a UI
lzd  # (lazydocker command)
```

**Services started:**
- 🔌 **Port 5003**: Backend API server
- 🗄️ **Port 5432**: PostgreSQL database  
- ⚡ **Port 6379**: Redis cache
- 🍃 **Port 27017**: MongoDB
- ⏱️ **Port 7233**: Temporal server
- 🌐 **Port 8080**: Temporal Web UI

---

## Terminal 2: Frontend

Set up and start the web interface:

```bash
cd agentex-web/
make dev  # Installs npm dependencies and starts dev server
```

**Service started:**
- 🌐 **Port 3000**: Next.js web interface

Access at: **http://localhost:3000**

---

## Terminal 3: SDK & Agent Development

The Agentex Python SDK is now available as a separate package. Install it to create and run your agents!

NOTE: This SDK is portable anywhere in your file directories. However, to hook into our CI/CD system, please
clone the agentex-agents repository: https://github.com/scaleapi/agentex-agents, and work within your team.

### Verify SDK is installed

```bash
# Verify installation
agentex --help
```

### Create Your First Agent

```bash
# IMPORTANT: Set development mode for all terminals where you use the SDK
export ENVIRONMENT=development

# Create a new agent
agentex init
# Follow the prompts to create your agent

# Run your agent
cd your-agent-name/
export ENVIRONMENT=development && agentex agents run --manifest manifest.yaml
```

**Agent started:**
- 🤖 **Port 8000**: Your agent's ACP server

> **Note**: For the SDK installation and usage instructions, visit the [agentex-python repository](https://github.com/scaleapi/agentex-python)

---

## 🎯 Verify Everything Works

1. **Backend Health**: `curl http://localhost:5003/health`
2. **Frontend Access**: Open http://localhost:3000
3. **SDK Installation**: Run `agentex --help`
4. **Agent Interaction**: Use the web UI to chat with your agent
5. **Docker Status**: Run `docker ps` or `lzd` to see all services

---

## 🛠️ Essential CLI Commands

### Agent Management
```bash
agentex agents list          # List all agents
agentex agents run --manifest manifest.yaml  # Run agent locally
agentex agents build --manifest manifest.yaml --push  # Build & deploy
```

### Package Management
```bash
# For new projects
uv add agentex-sdk           # Add the SDK to your project (if using uv)
pip install agentex-sdk      # Or install with pip

# For existing projects
agentex uv sync              # Sync dependencies (if using uv)
agentex uv add requests      # Add new dependencies
```

### Development Tools
```bash
agentex init                 # Create new agent
agentex tasks list          # View agent tasks
agentex secrets create      # Manage secrets
```

---

## 📦 Package Management Options

When creating an agent with `agentex init`, you can choose between:

### Option 1: uv (Recommended)
- Uses `pyproject.toml` for dependency management
- Faster dependency resolution and installation
- Better dependency isolation
- Use `agentex uv` commands for package management

### Option 2: pip (Traditional)
- Uses `requirements.txt` for dependency management
- Traditional pip-based workflow
- Good for teams familiar with pip

---

## 🚨 Common Problems & Solutions

### Redis Port Conflict
If you have Redis running locally, it may conflict with Docker Redis:
```bash
# Stop local Redis (macOS)
brew services stop redis

# Stop local Redis (Linux)
sudo systemctl stop redis-server
```

### Port Already in Use
Use this command to find and kill processes on conflicting ports:
```bash
# Kill process on specific port (replace 8000 with your port)
kill -9 $(lsof -i TCP:8000 | grep LISTEN | awk '{print $2}')
```

Referenced from: [What's Running on Port 8000? (And how to stop it)](https://medium.com/@valgaze/utility-post-whats-running-on-port-8000-and-how-to-stop-it-2ed771fbb422)

### Docker Permission Issues
```bash
# Add user to docker group (Linux)
sudo usermod -aG docker $USER
# Restart terminal after running this
```

### `agentex` Command Not Found
If you get "command not found: agentex", make sure you've installed the SDK:
```bash
pip install agentex-sdk
# Now agentex commands should work
agentex --help
```

### Wrong agentex-sdk Version (0.0.1 instead of latest)
If you only get agentex-sdk version 0.0.1, it's because you're using Python < 3.12:
```bash
# Check your Python version
python --version

# If it shows < 3.12, upgrade Python first (see Prerequisites section above)
# Then reinstall the SDK
pip uninstall agentex-sdk
pip install agentex-sdk

# Verify you now have the latest version
python -c "import agentex; print(f'agentex-sdk version: {agentex.__version__}')"
```

### Environment Variables
For SDK usage, always set the development environment:
```bash
export ENVIRONMENT=development
```

---

## 📁 Repository Structure

```
agentex/
├── agentex/           # Backend server & services
├── agentex-web/       # Next.js frontend 
└── agentex-auth/      # Authentication proxy
```

### Individual READMEs
- **[agentex/README.md](agentex/README.md)**: Backend setup, Docker services, database migrations
- **[agentex-web/README.md](agentex-web/README.md)**: Frontend setup, environment variables

### External Resources
- **[agentex-python](https://github.com/scaleapi/agentex-python)**: Python SDK, CLI tools, and tutorials

---

## 🎓 Next Steps

1. **Explore SDK Features**: Check out the [agentex-python repository](https://github.com/scaleapi/agentex-python)
2. **Read Documentation**: Visit [dev.agentex.scale.com/docs](https://dev.agentex.scale.com/docs)
3. **Check Examples**: Explore the examples in the agentex-python repository
4. **Monitor with Temporal**: Access Temporal UI at http://localhost:8080
5. **View API Docs**: Backend API documentation at http://localhost:5003/api

---

## 🔗 Quick Links

- **Web Interface**: http://localhost:3000
- **Backend API**: http://localhost:5003
- **Temporal UI**: http://localhost:8080  
- **Documentation**: https://agentex.scale.com/docs
- **Python SDK**: https://github.com/scaleapi/agentex-python

---

## 🐳 Docker Management

**Useful Docker Commands:**
```bash
docker ps              # List running containers
docker compose down     # Stop all services
docker compose up       # Restart services
lzd                    # LazyDocker UI (if installed)
```

Happy building! 🚀 
