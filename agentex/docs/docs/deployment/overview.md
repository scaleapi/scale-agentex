# Deploying Your Agent

With your agent developed and tested locally, the next step is deploying it to a live Kubernetes cluster where it can handle production workloads. Agentex provides deployment commands that work in both manual workflows (for learning and troubleshooting) and automated CI/CD pipelines (recommended for production).

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

## The Deployment Process

Deploying an agent involves three core commands:

1. **[Build](commands.md#agentex-agents-build)** - Create and push a Docker image
2. **[Sync Secrets](commands.md#agentex-secrets-sync)** - Configure credentials in cluster
3. **[Deploy](commands.md#agentex-agents-deploy)** - Deploy using Helm charts

### Quick Command Reference

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
```

For detailed command documentation, usage examples, and troubleshooting, see the [Commands Reference](commands.md).

---

## Production Deployment: CI/CD Integration

Agentex is designed from the ground up for automated, enterprise-grade deployment. Rather than treating CI/CD as an afterthought, the platform embraces a **"build once, deploy everywhere"** philosophy where the same Docker image flows through development, staging, and production environments with security and automation built in from day one.

### Why Automate with CI/CD?

Manual deployments don't scale. When you're managing multiple agents across environments, copying commands between terminals and manually syncing secrets becomes error-prone and time-consuming. Agentex's deployment architecture solves this by integrating three critical capabilities:

**Immutable Artifacts**: Build your agent once into a Docker image, then deploy that exact same artifact to dev, staging, and production. No "works on my machine" problems, no environment drift.

**Secure Secrets Management**: Secrets never live in code. The `agentex secrets sync` command bridges your secrets manager (AWS Secrets Manager, Azure Key Vault, etc.) directly to Kubernetes, creating a secure pipeline where credentials flow from source of truth to runtime without ever touching disk or code repositories.

**Environment Promotion**: Use the same manifest and commands across all environments. The only difference is which secrets YAML you load and which environment profile you select—everything else is identical.

### The Automated Pipeline

A typical CI/CD pipeline for Agentex follows four core stages:

1. **Build** - Create a Docker image with `agentex agents build` and generate metadata (commit SHA, author, timestamp) for audit trails
2. **Push** - Upload the image to your container registry (GCR, ECR, ACR, or GitHub Container Registry)
3. **Secrets Sync** - Run `agentex secrets sync` to inject credentials from your secrets manager into the Kubernetes namespace
4. **Deploy** - Execute `agentex agents deploy` with environment-specific Helm overrides to roll out the agent

These four stages are the **core Agentex deployment steps**, but your organization can integrate additional phases around them based on your release processes—testing phases (unit, integration, E2E tests), security scanning, compliance checks, manual approval gates, or any custom validation steps your team requires. The Agentex commands are designed to fit seamlessly into your existing CI/CD workflows.

### Getting Started with CI/CD

Ready to automate your deployments? The [CI/CD Setup Guide](cicd.md) walks through:

- Setting up CI/CD pipelines for automatic deployment (examples use GitHub Actions)
- Configuring secrets synchronization with your secrets manager
- Implementing build metadata for deployment history tracking
- Environment-specific deployment strategies

The commands shown in the Quick Reference above are the same commands your CI/CD pipeline will use—just executed automatically instead of manually.

---

## Next Steps

- **[Integrate CI/CD](cicd.md)** - Set up automated deployment pipelines (recommended for production)
- **[Commands Reference](commands.md)** - Detailed documentation for all deployment commands
- **[Agent Configuration Files](../configuration.md)** - Configure your agent's manifest.yaml and environments.yaml
