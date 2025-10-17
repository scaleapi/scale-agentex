# Agentex Authentication Service

A centralized authentication and authorization service for the Agentex ecosystem. This service provides identity verification and permission management through well-defined HTTP APIs, acting as a security gateway for the main Agentex application.

## Overview

The `agentex-auth` service follows a clean, pluggable architecture that supports multiple authentication providers. It serves two main functions:

1. **Authentication** (`/v1/authn`): Validates incoming request headers and returns user identity information
2. **Authorization** (`/v1/authz/*`): Manages fine-grained permissions using a `(principal, resource, operation)` model

### Architecture

- **Provider Pattern**: Supports multiple auth backends (currently SGP, can add WorkOS, Auth0, etc.)
- **Layered Design**: Clean separation between API, domain, and adapter layers
- **Dependency Injection**: Proper IoC container usage for extensibility
- **Microservice Integration**: Communicates with main agentex service via HTTP

## Local Development Setup

### Prerequisites

- Python 3.12
- Access to SGP (Scale's internal auth system) for authentication
- Main agentex service (optional, for integration testing)

### 1. Install Dependencies

```bash
# Install uv (if not already installed)
pip install uv

# Dependencies will be managed automatically by uv when running make commands
```

### 2. Environment Variables

Create a `.env` file in the agentex-auth root directory:

```bash
# Environment
ENVIRONMENT=development

# Authentication Provider Configuration
AUTH_PROVIDER=sgp
AUTH_PROVIDER_BASE_URL=https://sgp.scale.com  # Replace with actual SGP URL

# Optional: Logging
LOG_LEVEL=info
```

### 3. Running the Service

#### Option A: Direct Python (with auto-reload)
```bash
make dev
```

#### Option B: Docker
```bash
# Build the image
make build

# Run the container
make run
# or
docker run --rm -it -p 8000:8000 agentex-auth
```

The service will be available at: http://localhost:5006

### 4. Health Check

Verify the service is running:
```bash
curl http://localhost:5006/healthcheck
# Should return: 200 OK

curl http://localhost:5006/
# Should return: {"Agentex": "Authentication"}
```

## Integration with Main Agentex Service

To test the full authentication flow with the main agentex service:

### 1. Configure Main Agentex Service

In your main agentex `.env` file, add:
```bash
# Enable authentication by pointing to agentex-auth
AGENTEX_AUTH_URL=http://localhost:5006

# Other required agentex environment variables
DATABASE_URL=postgresql://user:pass@localhost:5432/agentex
MONGODB_URI=mongodb://localhost:27017
# ... etc
```

### 2. Start Both Services

```bash
# Terminal 1: Start agentex-auth
cd agentex-auth
make dev

# Terminal 2: Start main agentex service
cd agentex
# Follow agentex README to start the main service
```

### 3. Authentication Flow Testing

With both services running, requests to agentex will flow through authentication:

```bash
# This request will be authenticated via agentex-auth
curl -H "x-api-key: your-sgp-api-key" \
     -H "x-selected-account-id: your-account-id" \
     http://localhost:8080/agents

# Without auth headers (should work - bypassed routes)
curl http://localhost:8080/health
curl http://localhost:8080/docs
```

## API Endpoints

### Authentication
- `POST /v1/authn` - Verify request headers and return principal context

### Authorization  
- `POST /v1/authz/grant` - Grant permission to a principal on a resource
- `POST /v1/authz/revoke` - Revoke permission from a principal on a resource  
- `POST /v1/authz/check` - Check if a principal has permission for a resource
- `POST /v1/authz/search` - List resources available to a principal

### Health
- `GET /healthcheck` - Health check endpoint
- `GET /healthz` - Kubernetes-style health check
- `GET /readyz` - Kubernetes-style readiness check

## Development Features

### Local Development Mode

When `AGENTEX_AUTH_URL` is **not set** in the main agentex service:
- ✅ Authentication is completely disabled  
- ✅ All requests pass through without auth checks
- ✅ No dependency on agentex-auth service
- ✅ Perfect for local development

This design ensures that developers can work on the main agentex service without needing to run agentex-auth.

### Error Handling

The service uses consistent error handling with the main agentex service:
- Structured error responses: `{"message": "...", "code": 500, "data": null}`
- Specific handlers for different exception types
- Comprehensive logging for debugging

### CORS Configuration

Currently configured for development with `allow_origins=["*"]`. In production, this should be restricted to specific domains.

### Code Quality

Run linting and formatting:
```bash
make lint
```

## Testing

### Unit Testing Authentication
```bash
# Test authentication endpoint directly
curl -X POST http://localhost:5006/v1/authn \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-sgp-api-key" \
  -H "x-selected-account-id: your-account-id"
```

### Unit Testing Authorization
```bash
# Grant permission
curl -X POST http://localhost:5006/v1/authz/grant \
  -H "Content-Type: application/json" \
  -d '{
    "principal": {"user_id": "user123", "account_id": "acc456"},
    "resource": {"type": "agent", "selector": "agent789"},
    "operation": "read"
  }'

# Check permission
curl -X POST http://localhost:5006/v1/authz/check \
  -H "Content-Type: application/json" \
  -d '{
    "principal": {"user_id": "user123", "account_id": "acc456"},
    "resource": {"type": "agent", "selector": "agent789"},
    "operation": "read"
  }'
```

## Architecture Details

### Provider Pattern
The service is designed to support multiple authentication providers:
- **Current**: SGP (Scale's internal system)
- **Future**: WorkOS, Auth0, Okta, etc.
- **Configuration**: Set via `AUTH_PROVIDER` environment variable

### Hierarchical Authorization
The authorization system supports hierarchical permissions where child resources inherit permissions from parent resources (e.g., events/states inherit from their parent task).

### Integration Pattern
The main agentex service integrates via:
1. **Middleware**: `AgentexAuthMiddleware` intercepts requests
2. **Proxy**: `AgentexAuthenticationProxy` makes HTTP calls to agentex-auth
3. **Bypass Logic**: Whitelisted routes and agent-to-agent requests skip auth

## Troubleshooting

### Common Issues

1. **Service won't start**: Check that all required environment variables are set
2. **Authentication fails**: Verify SGP credentials and network connectivity
3. **Main agentex can't reach auth**: Ensure `AGENTEX_AUTH_URL` is correct
4. **CORS errors**: Check that the requesting origin is allowed

### Debug Mode

For detailed logging, set:
```bash
LOG_LEVEL=debug
```

### Logs

Check service logs for authentication attempts and errors:
```bash
# If running with Docker
docker logs <container-id>

# If running directly
# Logs will appear in terminal where uvicorn is running
```

