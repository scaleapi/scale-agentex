# Deploying Your Agent

Deploying your agent to production involves three main steps that prepare, configure, and deploy your agent to a Kubernetes cluster. This guide provides an overview of the deployment process and links to detailed documentation for each command.

## Prerequisites

Before deploying, you need:
- **kubectl** installed and configured
- **Cluster access** - Contact your cluster administrators for access
- **Namespace** - Get a namespace provisioned for your agent
- **Permissions** - RBAC access to create deployments and secrets

Verify your setup:
```bash
kubectl config current-context  # Check cluster connection
kubectl get namespace your-namespace  # Verify namespace exists
```

!!! Note
    If your company has CI/CD pipelines set up, much of this may be automated. This guide covers manual deployment.

## Overview

The deployment process follows three steps:

1. **[Build](commands.md#agentex-agents-build)** - Create and push a Docker image
2. **[Sync Secrets](commands.md#agentex-secrets-sync)** - Configure credentials in cluster
3. **[Deploy](commands.md#agentex-agents-deploy)** - Deploy using Helm charts

## Quick Start

For experienced users, here's the complete deployment sequence:

```bash
# 1. Build and push your agent image
agentex agents build --manifest manifest.yaml \
  --registry gcr.io/my-project --push

# 2. Sync secrets to the cluster
agentex secrets sync --manifest manifest.yaml \
  --cluster production --namespace my-agent-namespace \
  --values production-secrets.yaml --no-interactive

# 3. Deploy your agent
agentex agents deploy --environment prod --cluster production \
  --manifest manifest.yaml \
  --no-interactive

# 4. Check deployment status
kubectl get pods -n agentex-agents
helm status my-agent-production -n agentex-agents
```

## Detailed Documentation

- **[Commands Reference](commands.md)** - Complete guide for all deployment commands
- **[Manifest Configuration](../manifest_setup.md)** - Configure your agent's manifest.yaml and environments.yaml

## Common Workflows

### Development Deployment
For deploying to a development cluster:

```bash
# Build without pushing (for local development)
agentex agents build --manifest manifest.yaml

# Sync secrets interactively
agentex secrets sync --manifest manifest.yaml --cluster dev-cluster

# Deploy with interactive prompts
agentex agents deploy --environment dev --cluster dev-cluster --manifest manifest.yaml
```

### Production Deployment
For production deployments with CI/CD:

```bash
# Build and push to production registry
agentex agents build --manifest manifest.yaml \
  --registry your-prod-registry.com --push

# Sync secrets non-interactively
# Typically this prod-secrets.yaml is setup by fetching from
#   your companys secret management vaults and created in the pipelines
agentex secrets sync --manifest manifest.yaml \
  --cluster prod-cluster --namespace production \
  --values prod-secrets.yaml --no-interactive

# Deploy to production environment
agentex agents deploy --environment prod --cluster prod-cluster \
  --manifest manifest.yaml \
  --no-interactive
```

## Next Steps

1. Review the [Commands Reference](commands.md) for detailed command documentation
2. Configure your agent with the [Manifest Configuration](../manifest_setup.md) guide
3. Follow the Quick Start sequence above to deploy your agent
