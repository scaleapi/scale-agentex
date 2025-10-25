# Agentex

## Getting Started

### Installation

```bash
pip install uv
brew install docker-compose

# Optional, for managing a k9s-like UI for docker compose
# https://github.com/jesseduffield/lazydocker
brew install lazydocker
echo "alias lzd='lazydocker'" >> ~/.zshrc
source ~/.zshrc
```

## Development

### Visuals (What you get when running locally)

**LazyDocker (Docker Compose Viewer) + Locally Run Agent**
(instructions below)
<img width="1920" alt="Screenshot 2025-03-20 at 10 01 53 PM" src="https://github.com/user-attachments/assets/97f192a2-72bc-4edd-857e-2d2ff247535d" />

**Localhost Agent Web UI**
<img width="1728" alt="Screenshot 2025-03-20 at 10 09 17 PM" src="https://github.com/user-attachments/assets/da6ad41e-0cdd-44c6-a9fa-626355cbfa7c" />

### Development Instructions

**Start all services using Docker Compose**
```bash
make dev

# Optional, in separate terminal, use a k9s-like UI for docker compose
# Shortcuts: https://github.com/jesseduffield/lazydocker/blob/master/docs/keybindings/Keybindings_en.md
lzd
```

**Install Agentex Python SDK**
```bash
# Install the official Agentex Python SDK
pip install agentex-sdk

# Verify installation
agentex --help
```

**(Important!) Set your environment to dev mode**
All new terminals should have this set until you're ready to deploy your agent to staging (more instructions below)
```bash
export ENVIRONMENT=development # Set this to do local development
```

**Create an agent**
```bash
# Navigate to any directory where you want to create your agent
mkdir my-agents && cd my-agents

agentex init
# Respond to the prompts to create your agent

# For any credentials you assign to environment variables in your manifest,
# you will need to set them in a local .env file and load them using
# load_dotenv(). It is recommended only to use load_dotenv() during development, 
# like this:
#
# if os.environ.get("ENVIRONMENT") == "development":
#     load_dotenv()
```

**Deploy an agent for dev/staging testing**
```bash
# Replace manifest.yaml with the path to your manifest.yaml file
agentex agents build --manifest manifest.yaml --push
agentex agents deploy --manifest manifest.yaml
```

**Start an agent locally**
```bash
# For local testing and development
agentex agents run --manifest manifest.yaml
```

### Further Reading

- Check out the [Agentex Python SDK repository](https://github.com/scaleapi/scale-agentex-python) for examples and tutorials
- Read the documentation at [dev.agentex.scale.com/docs](https://dev.agentex.scale.com/docs)

