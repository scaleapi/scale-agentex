<div align="center">
  <h1 align="center">Agentex</h1>
  <p align="center">
    Build and deploy intelligent agents with ease
    <br />
    <a href="https://agentex.sgp.scale.com/docs"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/scaleapi/scale-agentex-python">Python SDK</a>
    ·
    <a href="https://github.com/scaleapi/scale-agentex/issues">Report Bug</a>
    ·
    <a href="https://github.com/scaleapi/scale-agentex/issues">Request Feature</a>
  </p>
  
  <p align="center">
    <a href="https://pypi.org/project/agentex-sdk/"><img src="https://img.shields.io/pypi/v/agentex-sdk?label=agentex-sdk" alt="PyPI Version"></a>
    <img src="https://img.shields.io/badge/python-3.12+-blue" alt="Python 3.12+">
    <a href="https://github.com/scaleapi/scale-agentex/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License"></a>
    <a href="https://github.com/scaleapi/scale-agentex"><img src="https://img.shields.io/github/stars/scaleapi/scale-agentex?style=social" alt="GitHub Stars"></a>
  </p>
</div>

## About The Project

AI agent capabilities can be understood in five levels, from simple chatbots to fully autonomous, self-driving agentic systems:

<img width="960" height="417" alt="image" src="https://github.com/user-attachments/assets/68beed69-9737-4ae5-96fc-47f3477dd1f3" />


Today, most AI applications are limited to Level 3 (L3) and below, relying on synchronous request/response patterns. This restricts their ability to handle complex, long-running, or autonomous workflows.

Agentex is designed to be future-proof, enabling you to build, deploy, and scale agents at any level (L1–L5). As your needs grow, you can seamlessly progress from basic to advanced agentic AI—without changing your core architecture.

In this README we will start with scaffolding an L1 example just to learn the ropes. For more complicated levels, refer to the Python SDK and Docs mentioned below. Since we have documentation resources in several places, here is how to use each of them.

| Resource | Description |
|----------|-------------|
| **This README** | **Getting Started**: Spin up a simple agent on your local computer from scratch in minutes. This comes with a full development UI and agent server. |
| **[Python SDK](https://github.com/scaleapi/scale-agentex-python)** | **Examples**: Agent-building tutorials that work out of the box. These show how to build up from simple to more complex agents using Agentex. |
| **[Docs Site](https://agentex.sgp.scale.com/docs)** | **Concepts**: More in depth details on the what, why, and how of building L1-L5 agents.<br><br>**Enterprise Support**: Description of how our zero-ops deployment works. Learn how to share hundreds of agents with the rest of your company. Each agent is hosted and scaled independently on cloud-agnostic infrastructure. |

## Getting Started

Here is what we will build together in this README. We'll start with a Hello World agent, but quickly switch to a more intelligent one!

https://github.com/user-attachments/assets/9badad0d-f939-4243-ba39-68cafdae0078


### Prerequisites

- **Install Python 3.12+ (Required)**: https://www.python.org/downloads/

```bash
# Install uv (fast Python package manager) https://docs.astral.sh/uv/getting-started/installation/
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Docker and Node.js
brew install docker docker-compose node

# Stop redis - On Mac the default redis will conflict with the redis that is started up by our docker compose file
brew services stop redis
```

#### Install the Agentex SDK

You will need the Agentex CLI to create your first Agent. Use `uv tool` to install the `agentex` CLI in an self-contained environment, but still make it globally available. 

```bash
uv tool install agentex-sdk
```

The installation was successful if you see help output after you run `agentex -h`.

<img width="563" height="199" alt="Agentex CLI help output" src="https://github.com/user-attachments/assets/50799cf0-c925-4fd9-84bd-044a6ef97287" />


## Setup

Before you share your agents with other people (or your company), you'll want a fully isolated developer sandbox. This allows you to freely develop agents without affecting anyone else or be affected by anyone else.

To do this, you just need to spin up the [Agentex Server](https://github.com/scaleapi/scale-agentex/tree/main/agentex) and a [Developer UI](https://github.com/scaleapi/scale-agentex/tree/main/agentex-ui) which allows you to interact with your agent nicely. This way you'll know how your agent feels in a simple UI.

> Each agent also ships with a `dev.ipynb` notebook for those uninterested in a UI, but more on that later

### Terminal 1 - Agentex Server

First, open up a terminal. Then run the following commands.

*Note: you should run these commands at the root of this repository.*

```bash
cd agentex/
# Install dependencies in a virtual environment
uv venv && source .venv/bin/activate && uv sync 
# Start backend services via docker compose (see Makefile for details)
make dev
```

### (Optional) Terminal 1.5 - LazyDocker

It's hard to see if everything is healthy when you just run docker compose in a single terminal since all the logs are jumbled up. Instead, we recommend installing [lazydocker](https://github.com/jesseduffield/lazydocker) and running the following shortcut in a separate terminal.

```bash
lzd
```

This gives a terminal for you to ensure all of the backend servers are healthy and you can review logs for each individual server in isolation. You know your Agent Server is fully running if all of the services from the docker compose are marked `(healthy)` in the top left panel of lazydocker.

<img width="863" height="729" alt="image" src="https://github.com/user-attachments/assets/64e2e8cf-7559-43e8-a641-3e56f799225e" />



### Terminal 2 - Frontend Server

Then, open up a second terminal. Then run the following commands.

*Note: you should run these commands at the root of this repository.*

```bash
cd agentex-ui/
# Install dependencies (see Makefile for details)
make install
# Starts web interface on localhost (default port 3000)
make dev
```

## Create Your First Agent

The Agentex Python SDK natively ships with a CLI. Use this CLI to scaffold your first "Hello World" agent. Run `agentex -h` to ensure the CLI is available.

### Terminal 3 - Initialize your Agent code

Let's create a **sync** agent at first. A sync agent is blocking on each user query. The agent cannot take additional requests while it's responding. This is the most classic chat-style agent you're probably very familiar with by now. You'll need to have a directory to put this agent in, so please have a destination in mind.

```bash
# Creates a working AI agent at your specified directory
agentex init
```

Here is an example of the CLI flow you should follow with some example responses. You can change the responses if you'd like.

<img width="573" height="759" alt="image" src="https://github.com/user-attachments/assets/7b3b97da-d3d2-499f-b8e8-9facfeb20791" />



### Set up your agent's environment

Set up your virtual environment, install dependencies, and enter your virtual environment

```bash
cd your-agent-name/
uv venv && source .venv/bin/activate && uv sync 
```

> Note: If you are using an IDE, we recommend you setting your virtual environment path to `.venv/bin/python` to get linting

### Your Agent Server

In the same Terminal 3, start your Agent Server (in your virtual environment).

This server will auto-reload as you make changes to your agent code. Your print statements and error logs will appear here.

```bash
# Starts your agent
agentex agents run --manifest manifest.yaml
```

> The `manifest.yaml` defines important parameters the Agentex backend needs to know to start the agent like its name and the location of crucial project files. For now, the `agentex init` command sets this up correctly for you based on your answers to the CLI questions. If you want to learn about all of these parameters and how to edit this file, please refer to our [docs](https://agentex.sgp.scale.com/docs).

## Test your Agent

You should see your agent appear in the developer UI when you visit http://localhost:3000 in your browser. As you can see, this agent just responds with a "Hello World" message. It's main purpose is to show how simple the agent's standard entrypoint is.

<img width="1728" height="992" alt="image" src="https://github.com/user-attachments/assets/4d0da048-ee0f-4a69-b95e-a90855816e3e" />


Let's make it slightly more interesting by allowing an AI to respond in a streaming fashion.

Simply copy the code from [this streaming example](https://github.com/scaleapi/scale-agentex-python/blob/main/examples/tutorials/00_sync/020_streaming/project/acp.py) and replace your existing `project/acp.py` file with it (see the above video for a walkthrough):

> Note: As you can see, code and files are very portable. As long as your `manifest.yaml` and `acp.py` is configured correctly your agent should work out of the box.

### Set up environment variables

In order for us to use AI, you need an API key to the provider of your choice. Our tutorial starts you off with an OpenAI call for simplicity. To start, define your OpenAI API Key in a `.env` file as shown below. 

> If you do not use OpenAI, replace the OpenAI call with the LLM provider of your choice and put the appropriate API key in the `.env` file.

Create a .env file in the root of your agent folder (at the same level as the `manifest.yaml`).

```bash
touch .env

# Add environment variables to this file i.e.
OPENAI_API_KEY="..."
```

> If you modify your .env file, you will need to restart the server via `Ctrl-C` and re-run this command. Note: This will not delete any chat history you already have. This history is persisted by the Agentex backend service.

Your agent should auto-reload and look like this now:

<img width="1728" height="991" alt="image" src="https://github.com/user-attachments/assets/63105a1e-3a33-43df-8680-b66403321d96" />


At this point, feel free to play around with the UI.
1. Start a conversation with your agent
2. See your agent respond
3. Investigate your agent's behavior by opening the traces tab (top right corner icon). 

> Troubleshooting: If your agent response doesn't stream, you should run `brew services stop redis` as mentioned in the preqrequisite section.

## Recommended Next Steps

> To do more complex things like those suggested below, it's best to consult the [Python SDK tutorials](https://github.com/scaleapi/scale-agentex-python/tree/main/examples) and [Docs Site](https://agentex.sgp.scale.com/docs) for guidance.

The world is your oyster at this point. Here are some suggestions on what to try next!

> Hint: If you need help you can probably vibe-code some of these with Claude Code, Cursor, or Codex. Just make sure to add our docs as context!

|What to try|Description|
|--|--|
| **Make your AI Agentic** | Add a tool call or two to see how that changes the Agent's behavior in the UI. |
| **Make multiple agents** | Why stop at 1? Make a couple agents |
| **Multi Agent System** | Make agents that use sub-agents. Use our Agent Developer Kit (ADK) to send messages between agents. |
| **Async Agent** | A chat agent is cool, but an asynchronous agent that in the background is even cooler. Switch to the "Agentic ACP" agent to make your first async agent. |
| **Temporal-Powered Async Agent** | As your agents get more complex and start incorporating the following techniques (human escalation, complex multi-step tools). We have partnered with [Temporal](https://docs.temporal.io/develop/python) to power up our Agents with Temporal's durable execution. |

## Contact

**Original Authors**  
| [@felix8696](https://github.com/felixs8696) | [@jasonyang101](https://github.com/jasonyang101) |
|--------------------------------------------|----------------------------------------------------|
| <a href="https://github.com/felixs8696"><img src="https://github.com/felixs8696.png" width="60" height="60" alt="@felix8696" /></a> | <a href="https://github.com/jasonyang101"><img src="https://github.com/jasonyang101.png" width="60" height="60" alt="@jasonyang101" /></a> |

**Maintainers**  
| [@danielmillerp](https://github.com/danielmillerp) | [@RoxyFarhad](https://github.com/RoxyFarhad) | [@smoreinis](https://github.com/smoreinis) | [@MichaelSun48](https://github.com/MichaelSun48) | [@declan-scale](https://github.com/declan-scale) |
|----------------------------------------------------|-----------------------------------------------|-----------------------------------------------|------------------------------------------------|-----------------------------------------------|
| <a href="https://github.com/danielmillerp"><img src="https://github.com/danielmillerp.png" width="60" height="60" alt="@danielmillerp" /></a> | <a href="https://github.com/RoxyFarhad"><img src="https://github.com/RoxyFarhad.png" width="60" height="60" alt="@RoxyFarhad" /></a> | <a href="https://github.com/smoreinis"><img src="https://github.com/smoreinis.png" width="60" height="60" alt="@smoreinis" /></a> | <a href="https://github.com/MichaelSun48"><img src="https://github.com/MichaelSun48.png" width="60" height="60" alt="@MichaelSun48" /></a> | <a href="https://github.com/declan-scale"><img src="https://github.com/declan-scale.png" width="60" height="60" alt="@declan-scale" /></a> |


---

## Why Open Source?

At Scale, we've spent the last three years building enterprise AI agents and learned how different every use case is. To unify our approach, we built a single delivery framework and now we're open-sourcing it to share what we've learned. Many enterprises have built upon open source tooling, and we want to contribute to that ecosystem. Our goal is simple: see more useful AI in production.

Agentex is also cloud-agnostic and Kubernetes-native. We intentionally kept it lightweight and unopinionated to maximize flexibility and to incur minimal infrastructure and security overhead.

Here are the differences between Open Source vs Enterprise to meet different organizational needs:

| Feature | Open Source Edition | Enterprise Edition |
|---------|--------------------|--------------------|
| **Source Code** | ✅ Open source server, developer UI, and SDK | ✅ Open source server, developer UI, and SDK |
| **Local Development** | ✅ Use this repo for local development | ✅ Use this repo for local development |
| **Community Support** | ✅ GitHub issues, discussions, pull requests | ✅ GitHub issues, discussions, pull requests |
| **GitOps Setup** | ❌ DIY deployment using public helm charts and the `agentex` CLI in CI/CD | ✅ Scale sets up CI/CD on select repositories for automatic agent deployment |
| **Builder Tools** | ❌ Bring your own (vector stores, models, etc.) | ✅ Model inference, knowledge bases, etc. |
| **Agent Operations (AgentOps)** | ❌ Not included | ✅ Full agent lifecycle management: hosting, version control, interaction UI, tracing, evaluation |
| **Identity Management** | ❌ No user management | ✅ SSO/SAML authentication, centralized API key management |
| **Enterprise Operations** | ❌ Self-service setup | ✅ Uptime/availability SLAs, security reviews, deployment, installation, ongoing maintenance |

**Ready for Enterprise?** Contact our team at https://scale.com/demo to discuss your requirements.

> For our current and future customers, Agentex is a module that is hosted and deployed as part of the Scale GenAI Platform's Enterprise License. This open source project is meant to give people a local development ability and community support.

---
## Troubleshooting

#### Redis Port Conflict
If you have Redis running locally, it may conflict with Docker Redis:
```bash
# Stop local Redis (macOS)
brew services stop redis

# Stop local Redis (Linux)
sudo systemctl stop redis-server
```

#### Port or Address Already in Use

- If you are running multiple agents at the same time and see `ACP: ERROR:    [Errno 48] Address already in use`, modify the `local_development.agent.port` field in your `manifest.yaml` to use a different port for each agent or just Ctrl-C any agents you're not currently working on. Don't wory your messages will still persist.
- If you are running processes that conflict witht he ports in the docker compose, either kill those conflicting processes (if you don't need them) or modify the docker compose to use different ports.

Use this command to find and kill processes on conflicting ports (if you don't need those processes).
```bash
# Kill process on specific port (replace <port> and <PID> accordingly)
lsof -i TCP:<port>
kill -9 <PID>
```

#### `agentex` Command Not Found
If you get "command not found: agentex", make sure you've installed the SDK:
```bash
uv tool install agentex-sdk
# Now agentex commands should work
agentex --help
```

#### Wrong agentex-sdk Version (0.0.1 instead of latest)
If you only get agentex-sdk version 0.0.1, it's because you're using Python < 3.12:
```bash
# Check your Python version
python --version

# If it shows < 3.12, upgrade Python first (see Prerequisites section above)
# Then uninstall the SDK via whatever you used to install the older version and reinstall agentex-sdk using UV
uv tool uninstall agentex-sdk
uv tool install agentex-sdk

# Verify you now have the latest version
python -c "import agentex; print(f'agentex-sdk version: {agentex.__version__}')"
```

---
## Contributing

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this project.

