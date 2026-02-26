# Agentex

This package is part of the [Scale Agentex](https://github.com/scaleapi/scale-agentex) project.

For installation, development, and deployment instructions, please refer to the main [Agentex README](https://github.com/scaleapi/scale-agentex#readme).

## Windows Support

Windows users should use the PowerShell build script (`build.ps1`) instead of the Makefile for all development commands.

### Quick Start (Windows)

```powershell
# Install dependencies
.\build.ps1 install-dev

# Start development server
.\build.ps1 dev

# Run tests
.\build.ps1 test

# See all available commands
.\build.ps1 help
```

### Command Reference

All `make` commands have equivalent PowerShell commands:

| Makefile Command | PowerShell Command |
|-----------------|-------------------|
| `make help` | `.\build.ps1 help` |
| `make install` | `.\build.ps1 install` |
| `make install-dev` | `.\build.ps1 install-dev` |
| `make dev` | `.\build.ps1 dev` |
| `make dev-stop` | `.\build.ps1 dev-stop` |
| `make test` | `.\build.ps1 test` |
| `make test-unit` | `.\build.ps1 test-unit` |
| `make migration NAME="name"` | `.\build.ps1 migration -Name "name"` |
| `make serve-docs` | `.\build.ps1 serve-docs` |

For a complete list of available commands, run:

```powershell
.\build.ps1 help
```
