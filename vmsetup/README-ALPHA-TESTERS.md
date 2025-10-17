# AgentEx Alpha Testing Guide

Welcome to AgentEx alpha testing! This guide will help you get started with the pre-configured development environment.

## Getting Started

You've been provided with access to a pre-configured VM running the complete AgentEx development stack. Everything is ready to use!

### Connecting to Your VM

```bash
# Connect via SSH (replace with your assigned IP)
ssh agentex@<your-vm-ip>

# For full functionality, use port forwarding to access web interfaces
ssh -L 3000:localhost:3000 -L 5003:localhost:5003 -L 8080:localhost:8080 agentex@<your-vm-ip>
```

### First Steps

Once connected, verify everything is running:

```bash
# Check service status
agentex-status

# View service logs
agentex-logs

# If services aren't running, start them
agentex-start
```

## Available Services

### 1. AgentEx Frontend (Port 3000)
- **URL**: http://localhost:3000 (via SSH port forwarding)
- **Purpose**: Main user interface for agent management and task execution
- **Features**: Create agents, run tasks, view results

### 2. AgentEx Backend API (Port 5003)
- **URL**: http://localhost:5003 (via SSH port forwarding)
- **Purpose**: REST API for agent operations
- **Documentation**: Available at http://localhost:5003/docs

### 3. Temporal UI (Port 8080)
- **URL**: http://localhost:8080 (via SSH port forwarding)
- **Purpose**: Monitor long-running workflows and agent executions
- **Use**: View workflow history, debug failed executions

## Quick Commands Reference

### Service Management
```bash
agentex-status          # Check all services
agentex-start           # Start all services
agentex-stop            # Stop all services  
agentex-restart         # Restart all services
agentex-logs            # View service logs
agentex-clean           # Clean restart (removes all data)
```

### Development Environment
```bash
agentex-env             # Activate Python environment
cd ~/tutorials          # Access tutorial examples
ll                      # List files (alias for ls -alF)
```

### Frontend Management
```bash
agentex-frontend        # Show frontend access info
agentex-frontend-npm    # Start frontend manually (if needed)
```

## Working with Tutorials

Tutorial examples are available in your home directory:

```bash
cd ~/tutorials
ls -la
```

### Available Tutorial Categories

1. **Sync Agents** (`00_sync/`)
   - Basic ACP (Agent Communication Protocol) examples
   - Multi-turn conversations
   - Streaming responses
   - Integration examples

2. **Agentic Workflows** (`10_agentic/`)
   - Base agent patterns
   - Temporal workflows for long-running tasks
   - State machine implementations
   - Advanced agent behaviors

### Running Tutorial Examples

```bash
# Navigate to a tutorial
cd ~/tutorials/00_sync/000_hello_acp

# Examine the structure
ls -la
cat README.md

# Follow tutorial-specific instructions
# Each tutorial has its own README with setup steps
```

## Creating Your Own Agents

### Using the AgentEx CLI

Activate the Python environment and use the CLI:

```bash
# Activate environment
agentex-env

# Create a new agent project
agentex init

# Navigate to the project
cd my-test-agent

# Follow the generated README for next steps
```

### Development Workflow

1. **Create Agent**: Use CLI or copy from tutorials
2. **Develop Logic**: Edit agent code (Python)
3. **Test Locally**: Run agent on the VM
4. **Deploy**: Use AgentEx deployment features
5. **Monitor**: Use Temporal UI to track execution

## Common Tasks

### Testing Agent Communication

```bash
# In Python environment
agentex-env
python

# Basic API test
import requests
response = requests.get('http://localhost:5003/health')
print(response.json())
```

### Viewing Agent Logs

```bash
# Application logs
agentex-logs

# Specific service logs
cd /opt/agentex/agentex
docker-compose logs agentex

# Frontend logs (if running manually)
tail -f /opt/agentex/logs/frontend.log
```

### Restarting Services

If something goes wrong:

```bash
# Restart everything
agentex-restart

# Or restart specific components
cd /opt/agentex/agentex
docker-compose restart agentex

# For frontend issues
agentex-frontend-npm
```

## File Locations

### Important Directories
```
/opt/agentex/           # Main application directory
├── agentex/            # Server code and configuration
├── agentex-py/         # Python SDK and CLI tools
├── agentex-web/        # Frontend application
├── venv/               # Python virtual environment
└── logs/               # Application logs

/home/agentex/
├── tutorials/          # Tutorial examples
└── .bashrc             # Your shell configuration
```

### Configuration Files
- **Docker Compose**: `/opt/agentex/agentex/docker-compose.yml`
- **Environment**: Use `agentex-env` to activate Python environment
- **Aliases**: Pre-configured in `~/.bashrc`

## Troubleshooting

### Services Not Responding

1. **Check service status**:
   ```bash
   agentex-status
   ```

2. **Restart services**:
   ```bash
   agentex-restart
   ```

3. **View detailed logs**:
   ```bash
   agentex-logs
   ```

### Frontend Not Accessible

1. **Verify port forwarding**:
   ```bash
   # Make sure you connected with port forwarding
   ssh -L 3000:localhost:3000 -L 5003:localhost:5003 -L 8080:localhost:8080 agentex@<vm-ip>
   ```

2. **Check frontend process**:
   ```bash
   pgrep -f "next dev"  # Should show a process ID
   ```

3. **Restart frontend manually**:
   ```bash
   agentex-frontend-npm
   ```

### API Errors

1. **Check backend status**:
   ```bash
   curl http://localhost:5003/health
   ```

2. **View backend logs**:
   ```bash
   cd /opt/agentex/agentex
   docker-compose logs agentex
   ```

### Python Environment Issues

1. **Reactivate environment**:
   ```bash
   agentex-env
   ```

2. **Verify CLI installation**:
   ```bash
   agentex-env
   agentex --help
   ```

### Network Connectivity

1. **Test local connectivity**:
   ```bash
   curl http://localhost:3000  # Frontend
   curl http://localhost:5003  # Backend
   curl http://localhost:8080  # Temporal UI
   ```

2. **Check Docker networks**:
   ```bash
   docker network ls
   docker ps
   ```

## Getting Help

### Documentation
- **Complete Guide**: `/opt/agentex/README-ALPHA.md`
- **Tutorial READMEs**: Each tutorial has specific instructions
- **API Docs**: http://localhost:5003/docs (when backend is running)

### Log Files
- **Application Logs**: `agentex-logs`
- **Frontend Logs**: `/opt/agentex/logs/frontend.log`
- **Docker Logs**: `cd /opt/agentex/agentex && docker-compose logs`

### Support Commands
```bash
# System information
uname -a
docker version
python --version

# AgentEx version
agentex-env && agentex --version

# Service health check
agentex-status
curl http://localhost:5003/health
```

## Best Practices

### Development
1. **Always activate the environment**: Use `agentex-env` before Python work
2. **Check service status first**: Run `agentex-status` before starting development
3. **Use tutorials as templates**: Copy and modify existing examples
4. **Monitor with Temporal UI**: Track agent execution and debug issues

### Testing
1. **Test locally first**: Use the VM environment before deploying elsewhere
2. **Check logs regularly**: Use `agentex-logs` to monitor system health
3. **Restart cleanly**: Use `agentex-restart` rather than manual Docker commands

### Troubleshooting
1. **Start simple**: Test basic connectivity before complex operations
2. **Use provided tools**: Leverage the pre-configured aliases and scripts
3. **Check one service at a time**: Isolate issues to specific components

## Next Steps

1. **Explore Tutorials**: Start with `~/tutorials/00_sync/000_hello_acp`
2. **Create Your First Agent**: Use `agentex init`
3. **Experiment with the UI**: Access http://localhost:3000
4. **Monitor Workflows**: Use Temporal UI at http://localhost:8080
5. **Provide Feedback**: Share your experience with the AgentEx team

Happy testing! 🚀 