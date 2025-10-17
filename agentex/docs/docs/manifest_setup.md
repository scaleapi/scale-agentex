# Agent Configuration Guide

Agent configuration uses **two files** that work together:

- **`manifest.yaml`**: Defines how your agent works (build, runtime, credentials)
- **`environments.yaml`**: Defines how to configure your agent per environment (namespace, auth, resources)

The `manifest.yaml` file is automatically generated when you run `agentex init`. You should create `environments.yaml` next to it to configure deployment settings for each environment.

## File Structure Overview

Agent configuration uses **two files** that work together:

### `manifest.yaml` - Core Agent Definition
The manifest is organized into four main sections:

1. **[Build Configuration](#build-configuration)** - Defines Docker image creation
2. **[Local Development](#local-development-configuration)** - Settings for running locally
3. **[Agent Configuration](#agent-configuration)** - Core agent properties and credentials
4. **[Deployment Configuration](#deployment-configuration)** - Kubernetes deployment settings

### `environments.yaml` - Environment-Specific Configuration
Located next to your manifest.yaml, this file defines:

1. **[Kubernetes Configuration](#kubernetes-configuration)** - Namespace for each environment
2. **[Auth Principal Configuration](#auth-principal-configuration)** - User and account identity for deployment authorization
3. **[Helm Overrides](#helm-overrides)** - Environment-specific resource tuning

**See the [Environment Configuration section](#environment-configuration-environmentsyaml) for complete details.**

## Build Configuration

The `build` section defines how your agent's Docker image is created. This configuration is used by the `agentex agents build` command.

```yaml
build:
  context:
    # Root directory for the build context (usually ../../../)
    root: ../
    
    # Paths to include in the Docker build context
    # Include your agent code directory
    include_paths:
      - my-agent
    
    # Path to your agent's Dockerfile (relative to root)
    dockerfile: my-agent/Dockerfile
    
    # Path to .dockerignore file (relative to root)
    dockerignore: my-agent/.dockerignore
```

### Key Points:

- **`root`**: Keep as `../` unless you have a custom project structure
- **`include_paths`**: Must include your agent's directory
- **`dockerfile`**: Points to your agent's Dockerfile
- **`dockerignore`**: Helps exclude unnecessary files from the build context

## Local Development Configuration

The `local_development` section is used by the `agentex agents run` command to start your agent locally.

```yaml
local_development:
  agent:
    port: 8000  # Port for your local ACP server
    host_address: host.docker.internal  # Docker networking address
  
  paths:
    # Path to your ACP server file (relative to manifest.yaml)
    acp: project/acp.py
    
    # Path to Temporal worker file (only for Temporal agents)
    worker: project/run_worker.py
```

### Key Points:

- **`port`**: The port where your ACP server runs locally (default: 8000)
- **`host_address`**: Use `host.docker.internal` for Docker, `localhost` for direct execution
- **`acp`**: Path to your ACP server file
- **`worker`**: Only needed for Temporal-enabled agents

## Agent Configuration

The `agent` section defines your agent's core properties and is used by all CLI commands.

### Basic Agent Properties

```yaml
agent:
  # Unique name for your agent (used for routing and identification)
  name: my-agent
  
  # Description of what your agent does
  description: "A helpful agent that processes user requests"
```

### Temporal Configuration

For agents that use Temporal workflows for long-running tasks:

```yaml
agent:
  temporal:
    enabled: true
    workflows:
      - name: my-agent  # Must match @workflow.defn name
        queue_name: my_agent_queue  # Temporal task queue
```

### Credentials Mapping

Map Kubernetes secrets to environment variables in your agent:

```yaml
agent:
  credentials:
    - env_var_name: "OPENAI_API_KEY"
      secret_name: "openai-secret"
      secret_key: "api-key"
    - env_var_name: "DATABASE_URL"
      secret_name: "db-credentials"
      secret_key: "connection-string"
```

### Key Points:

- **`name`**: Must be unique across your organization (used for task routing)
- **`temporal.enabled`**: Set to `true` for long-running workflow agents
- **`credentials`**: Maps secrets to environment variables (used by `agentex secrets sync`)

## Deployment Configuration

The `deployment` section defines how your agent is deployed to Kubernetes clusters.

### Image Configuration

```yaml
deployment:
  image:
    repository: ""  # Update with your container registry
    tag: "latest"   # Default tag (use versioned tags in production)
```

### Image Pull Secrets

For private container registries:

```yaml
deployment:
  imagePullSecrets:
    - name: my-registry-secret
```

### Global Deployment Settings

Default settings that apply to all clusters:

```yaml
deployment:
  global:
    agent:
      name: "my-agent"
      description: "My agent description"
    
    # Default replica count
    replicaCount: 1
    
    # Default resource requirements
    resources:
      requests:
        cpu: "500m"
        memory: "1Gi"
      limits:
        cpu: "1000m"
        memory: "2Gi"
```

### Key Points:

- **`image.repository`**: Must be updated with your container registry URL
- **`imagePullSecrets`**: Required for private registries (configured via `agentex secrets sync`)
- **`global`**: Default settings that can be overridden with `--override-file`

## Complete Example

```yaml
# Temporal-enabled agent for long-running workflows
build:
  context:
    root: ../
    include_paths:
      - my-temporal-agent
    dockerfile: my-temporal-agent/Dockerfile
    dockerignore: my-temporal-agent/.dockerignore

local_development:
  agent:
    port: 8000
    host_address: host.docker.internal
  paths:
    acp: project/acp.py
    worker: project/run_worker.py

agent:
  name: my-temporal-agent
  description: "A long-running agent using Temporal workflows"
  temporal:
    enabled: true
    workflows:
      - name: my-temporal-agent
        queue_name: my_temporal_agent_queue
  credentials:
    - env_var_name: "OPENAI_API_KEY"
      secret_name: "openai-secret"
      secret_key: "api-key"

deployment:
  image:
    repository: "gcr.io/my-project"
    tag: "latest"
  imagePullSecrets:
    - name: my-registry-secret
  global:
    agent:
      name: "my-temporal-agent"
      description: "A long-running agent using Temporal workflows"
    replicaCount: 1
    resources:
      requests:
        cpu: "500m"
        memory: "1Gi"
      limits:
        cpu: "1000m"
        memory: "2Gi"
```

## Environment Configuration (environments.yaml)

In addition to `manifest.yaml`, each agent should have an `environments.yaml` file that defines environment-specific deployment settings. This file should be located **next to your manifest.yaml**.

### Purpose and Benefits

The `environments.yaml` file separates environment-specific configuration from the core agent definition:

- **`manifest.yaml`**: Defines how your agent works (build, runtime, credentials)
- **`environments.yaml`**: Defines how to configure your agent per environment (namespace, auth, resources)

### File Structure

```yaml
schema_version: "v1"

environments:
  dev:
    kubernetes:
      namespace: "my-team-my-agent-dev"
    auth:
      principal:
        user_id: "my-dev-cluster-user-id"
        account_id: "my-dev-cluster-account-id"  
    helm_overrides:
      resources:
        requests:
          cpu: "200m"
          memory: "512Mi"
      
  prod:
    kubernetes:
      namespace: "my-team-my-agent-prod"
    auth:
      principal:
        user_id: "my-prod-cluster-user-id"
        account_id: "my-prod-cluster-account-id"
    helm_overrides:
      replicaCount: 3
      resources:
        requests:
          cpu: "1000m"
          memory: "2Gi"
        limits:
          cpu: "2000m"
          memory: "4Gi"
```

### Configuration Sections

#### Kubernetes Configuration
```yaml
kubernetes:
  namespace: "my-team-my-agent-dev"  # Where to deploy this agent
```

**Best Practices:**
- Include team name for isolation: `{team}-{agent}-{env}`
- Use lowercase with hyphens: `sgp-my-agent-dev`
- Keep under 63 characters (Kubernetes limit)

#### Auth Principal Configuration
```yaml
auth:
  principal:
    user_id: "my-dev-cluster-user-id"    # Unique identifier for the user who is deploying the agent
    account_id: "my-dev-cluster-account-id"  # Account/tenant identifier
```

**Auth Principal Purpose:**
- **User Identification**: Identifies the user/service account deploying the agent
- **Deployment Authorization**: Controls who can deploy agents to specific environments
- **Account/Tenant Isolation**: Associates deployments with specific accounts or tenants
- **Audit Trail**: Tracks who deployed which agents and when

**Best Practices:**
- **Unique per environment**: Use different user_id for dev vs prod deployment contexts
- **Environment-specific**: `my-dev-cluster-user-id` vs `my-prod-cluster-user-id`
- **Consistent format**: Use same naming pattern across your organization
- **Proper identifiers**: user_id should identify the deploying user/service, account_id should identify the account_id that the agent should be created in.

#### Helm Overrides
```yaml
helm_overrides:
  replicaCount: 3  # Override default replica count
  resources:
    requests:
      cpu: "1000m"
      memory: "2Gi"
    limits:
      cpu: "2000m" 
      memory: "4Gi"
  autoscaling:
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
```

**Common Overrides:**
- **replicaCount**: Number of pod replicas
- **resources**: CPU and memory requests/limits
- **autoscaling**: Horizontal pod autoscaling settings
- **env**: Additional environment variables
- **nodeSelector**: Node selection constraints

### Creating environments.yaml

To create an `environments.yaml` file for your agent:

```bash
cd teams/my-team/agents/my-agent/

# Create environments.yaml with your specific values
cat > environments.yaml << EOF
schema_version: "v1"

environments:
  dev:
    kubernetes:
      namespace: "my-team-my-agent-dev"
    auth:
      principal:
        user_id: "my-dev-cluster-user-id"
        account_id: "my-dev-cluster-account-id"
    helm_overrides: {}
      
  prod:
    kubernetes:
      namespace: "my-team-my-agent-prod"
    auth:
      principal:
        user_id: "my-prod-cluster-user-id"
        account_id: "my-prod-cluster-account-id"
    helm_overrides:
      replicaCount: 3
      resources:
        requests:
          cpu: "1000m"
          memory: "2Gi"
EOF
```

!!! note "Missing environments.yaml?"
    If you see an error about "environments.yaml not found", create one using the template above. This file is required for deployment to ensure proper environment isolation and auth principal configuration.

## CLI Command Reference

- **`agentex agents run`**: Uses `local_development` config to run locally
- **`agentex agents build`**: Uses `build` section to create Docker image
- **`agentex secrets sync`**: Uses `agent.credentials` to create K8s secrets
- **`agentex agents deploy`**: Merges `deployment` + `environments.yaml` for deployment

## Best Practices

1. **Keep build context minimal**: Use `.dockerignore` to exclude unnecessary files
2. **Use versioned tags**: Replace `"latest"` with specific versions in production
3. **Secure credentials**: Never put actual secrets in the manifest - use the credentials mapping
4. **Environment-specific overrides**: Use `--override-file` for different deployment environments
5. **Consistent naming**: Use kebab-case for agent names (e.g., `my-agent`, not `my_agent`)

## Next Steps

After configuring your manifest:

1. Test locally with `agentex agents run --manifest manifest.yaml`
2. Build your image with `agentex agents build --manifest manifest.yaml`
3. Configure secrets with `agentex secrets sync --manifest manifest.yaml --cluster your-cluster`
4. Deploy with `agentex agents deploy --environment dev --cluster your-cluster --manifest manifest.yaml`

For deployment-specific configuration, see the [Deployment Guide](deployment/overview.md).
