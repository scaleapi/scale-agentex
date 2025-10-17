# Deployment Commands Reference

Quick reference for the three core deployment commands: build, secrets sync, and deploy.

---

## Prerequisites: Cluster Setup

Before using deployment commands, ensure you have:

- **kubectl** installed and configured
- **Cluster access** - Contact your administrators for access
- **Namespace provisioned** - Get a namespace for your agent

### Verify Your Setup

```bash
# Check current kubectl context
kubectl config current-context

# Switch to target cluster
kubectl config use-context your-cluster-context

# Verify namespace exists
kubectl get namespace your-namespace
```

---

## agentex agents build

Creates a Docker image of your agent.

### Usage

```bash
agentex agents build --manifest manifest.yaml [--registry REGISTRY] [--push]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--manifest` | ✅ | Path to manifest file |
| `--registry` | ❌ | Registry URL for pushing image |
| `--push` | ❌ | Push image to registry after building |

### Examples

```bash
# Build locally only
agentex agents build --manifest manifest.yaml

# Build and push to registry
agentex agents build --manifest manifest.yaml \
  --registry gcr.io/my-project --push
```

### Registry Login

```bash
# Google Container Registry
gcloud auth configure-docker

# Amazon ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin your-account.dkr.ecr.us-west-2.amazonaws.com
```

---

## agentex secrets sync

Manages credentials and secrets in your Kubernetes cluster.

### Usage

```bash
agentex secrets sync --manifest manifest.yaml --cluster CLUSTER \
  [--namespace NAMESPACE] [--values VALUES_FILE] [--no-interactive]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--manifest` | ✅ | Path to manifest file |
| `--cluster` | ✅ | Target cluster name (kubectl context) |
| `--namespace` | ❌* | Kubernetes namespace (*required in non-interactive mode) |
| `--values` | ❌ | Path to values file containing secrets |
| `--no-interactive` | ❌ | Disable interactive prompts |

### What It Does

Syncs two types of secrets:
1. **User-Defined Secrets** - API keys, tokens defined in `manifest.yaml` → `agent.credentials`
2. **Image Pull Secrets** - Docker registry credentials from `deployment.imagePullSecrets`

### Examples

```bash
# Interactive mode (prompts for secret values)
agentex secrets sync --manifest manifest.yaml --cluster production

# Non-interactive with values file (CI/CD)
agentex secrets sync --manifest manifest.yaml \
  --cluster production --namespace agentex-agents \
  --values secrets.yaml --no-interactive
```

### Values File Format

```yaml
# secrets.yaml
credentials:
  openai-secret:
    api-key: "sk-your-key-here"
  my-api-secret:
    api-key: "your-api-key"
    endpoint: "https://api.example.com"

imagePullSecrets:
  my-registry-secret:
    registry: "gcr.io"
    username: "_json_key"
    password: "your-service-account-json"
```

---

## agentex agents deploy

Deploys your agent to Kubernetes using Helm.

### Usage

```bash
agentex agents deploy --environment ENVIRONMENT --cluster CLUSTER \
  [--manifest manifest.yaml] [--tag TAG] [--no-interactive]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--environment` | ✅ | Environment name from environments.yaml |
| `--cluster` | ✅ | Target cluster name (kubectl context) |
| `--manifest` | ❌ | Path to manifest file (default: manifest.yaml) |
| `--namespace` | ❌ | Override namespace from environments.yaml |
| `--tag` | ❌ | Override image tag |
| `--repository` | ❌ | Override image repository |
| `--no-interactive` | ❌ | Disable prompts |

### What It Does

1. Loads configuration from `environments.yaml`
2. Validates kubectl access to target cluster
3. Merges manifest with environment-specific overrides
4. Deploys using Helm (atomic operation)

### Examples

```bash
# Interactive deployment to dev
agentex agents deploy --environment dev --cluster dev-cluster

# Non-interactive deployment to prod (CI/CD)
agentex agents deploy --environment prod --cluster prod-cluster \
  --tag v1.2.3 --no-interactive

# Deploy with custom image
agentex agents deploy --environment staging --cluster staging-cluster \
  --repository my-registry.io/my-agent --tag feature-xyz
```

---

## Common Troubleshooting

### Build Issues

**Error: Cannot connect to Docker daemon**
→ Start Docker Desktop or the Docker daemon

**Error: unauthorized: authentication required**
→ Login to your registry (see Registry Login above)

### Secrets Issues

**Error: Unable to connect to cluster**
→ Verify kubectl context: `kubectl config current-context`

**Error: Namespace does not exist**
→ Create it: `kubectl create namespace my-namespace`

**Error: secrets is forbidden**
→ Check permissions: `kubectl auth can-i create secrets -n your-namespace`

### Deploy Issues

**Error: ImagePullBackOff**
→ Verify image pull secrets: `kubectl get secrets -n your-namespace`

**Error: UPGRADE FAILED**
→ Check Helm status: `helm status my-agent -n your-namespace`

**Error: deployments.apps is forbidden**
→ Check RBAC: `kubectl auth can-i create deployments -n your-namespace`

---

## Monitoring After Deployment

```bash
# Check pod status
kubectl get pods -n your-namespace

# View agent logs
kubectl logs -l app.kubernetes.io/name=agentex-agent -n your-namespace

# Follow logs in real-time
kubectl logs -f -l app.kubernetes.io/name=agentex-agent -n your-namespace

# Check Helm release
helm status my-agent -n your-namespace
```

---

## Next Steps

- Need configuration help? See [Manifest Configuration](../manifest_setup.md)
- Return to [Deployment Overview](overview.md)
