# Docker Setup for Agentex SGP App

This document explains how to build and run the Agentex SGP App using Docker.

## Quick Start

### First Time Setup

```bash
# Set up Docker buildx (run once)
make setup-buildx
```

### Build and Run

```bash
# Build the Docker image (uses docker buildx)
make build-and-load

# Run the container
make run
```

Access the application at [http://localhost:3000](http://localhost:3000)

### Build with Custom Tag

```bash
# Build with a specific tag
make build TAG=v1.0.0

# Build with custom image name and tag
make build IMAGE_NAME=my-agentex-app TAG=production
```

## Available Make Commands

Run `make help` to see all available commands:

- `make setup-buildx` - Set up Docker buildx builder (run once)
- `make build` - Build Docker image for linux/amd64 platform (buildx)
- `make build-and-load` - Build and load image to local Docker daemon
- `make build-no-cache` - Build Docker image without cache
- `make build-debug` - Build with verbose output for debugging
- `make build-and-push` - Build and push directly to registry
- `make run` - Run the Docker container locally
- `make run-detached` - Run the Docker container in detached mode
- `make stop` - Stop the running container
- `make push` - Push the image to registry (requires REGISTRY to be set)
- `make clean` - Remove the Docker image
- `make inspect` - Inspect the Docker image
- `make logs` - Show logs from running container
- `make shell` - Open shell in running container

## Docker Image Details

### Simple Single-Stage Build

The Dockerfile uses a straightforward single-stage approach:

1. **Node.js 20 Debian**: Base image with Debian; installs libvips (Sharp) and build tools
2. **Install dependencies**: Clean `npm ci --omit=dev`
3. **Copy source**: Application code (excluding local `node_modules`)
4. **Build**: Standard Next.js build (`npm run build`) and run with `next start`
5. **Security**: Non-root user for production runtime

### Clean Build Environment

- **No local node_modules**: .dockerignore ensures local dependencies are never copied
- **Fresh installs**: All dependencies are installed cleanly in the container
- **Simplified process**: Single stage eliminates complexity and potential issues

### Image Notes

- Runs as non-root user for security
- `.dockerignore` excludes local `node_modules` and build artifacts
- Leverages Docker layer caching for faster rebuilds
- Further optimization (optional): adopt Next.js standalone output if needed

### Platform Support

- Built for `linux/amd64` platform by default
- Can be customized with `PLATFORM` variable

## Environment Variables

The application runs with the following default environment variables:

- `NODE_ENV=production`
- `NEXT_TELEMETRY_DISABLED=1`
- `PORT=3000`
- `HOSTNAME=0.0.0.0`

To configure public runtime variables, pass them when running the container:

```bash
# Explicit env flags
docker run --rm -p 3000:3000 \
  -e NEXT_PUBLIC_AGENTEX_API_BASE_URL=http://localhost:5003 \
  -e NEXT_PUBLIC_SGP_APP_URL=https://egp.dashboard.scale.com \
  agentex-sgp-app:latest

# Or via an env file
docker run --rm -p 3000:3000 --env-file .env.local agentex-sgp-app:latest
```

## Registry Usage

To push to a container registry:

```bash
# Build and push to Docker Hub
make build TAG=v1.0.0 REGISTRY=yourusername
make push TAG=v1.0.0 REGISTRY=yourusername

# Build and push to private registry
make build TAG=v1.0.0 REGISTRY=your-registry.com/your-namespace
make push TAG=v1.0.0 REGISTRY=your-registry.com/your-namespace
```

## Development

For local development without Docker:

```bash
# Install dependencies
make install

# Run development server
make dev

# Type check
make typecheck

# Lint code
make lint
```

## Container Management

### Run in Background

```bash
make run-detached
```

### View Logs

```bash
make logs
```

### Access Container Shell

```bash
make shell
```

### Stop Container

```bash
make stop
```

## Troubleshooting

### Build Issues

If you encounter build issues:

1. Try building without cache: `make build-no-cache`
2. Ensure Docker is running and has sufficient resources
3. Check that all dependencies in package.json are accessible

### Runtime Issues

If the container fails to start:

1. Check logs: `make logs`
2. Verify port 3000 is not already in use
3. Ensure the image was built successfully: `make inspect`

### Performance

For better performance:

- Increase Docker Desktop memory allocation if builds are slow
- Use Docker BuildKit for faster builds
- Consider using a `.dockerignore` file (already included)
