# Makefile for AgentEx SGP App Docker builds

# Default variables
IMAGE_NAME ?= agentex-sgp-app
TAG ?= latest
PLATFORM ?= linux/amd64
REGISTRY ?= 

# Full image name with optional registry
FULL_IMAGE_NAME = $(if $(REGISTRY),$(REGISTRY)/$(IMAGE_NAME),$(IMAGE_NAME))

# Default target
.PHONY: help
help: ## Show this help message
	@echo "Available targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: setup-buildx
setup-buildx: ## Set up Docker buildx builder (run once)
	@echo "Setting up Docker buildx builder..."
	@docker buildx inspect agentex-builder >/dev/null 2>&1 || \
		docker buildx create --name agentex-builder --driver docker-container --bootstrap
	@docker buildx use agentex-builder
	@echo "✅ Docker buildx builder 'agentex-builder' is ready"

.PHONY: build
build: typecheck lint ## Build Docker image for linux/amd64 platform
	@echo "Building $(FULL_IMAGE_NAME):$(TAG) for platform $(PLATFORM)..."
	docker buildx build --platform $(PLATFORM) -t $(FULL_IMAGE_NAME):$(TAG) .
	@echo "✅ Build complete: $(FULL_IMAGE_NAME):$(TAG)"

.PHONY: build-no-cache
build-no-cache: typecheck lint ## Build Docker image without cache
	@echo "Building $(FULL_IMAGE_NAME):$(TAG) for platform $(PLATFORM) (no cache)..."
	docker buildx build --platform $(PLATFORM) --no-cache -t $(FULL_IMAGE_NAME):$(TAG) .
	@echo "✅ Build complete: $(FULL_IMAGE_NAME):$(TAG)"

.PHONY: build-debug
build-debug: typecheck lint ## Build Docker image with verbose output for debugging
	@echo "Building $(FULL_IMAGE_NAME):$(TAG) for platform $(PLATFORM) (debug mode)..."
	docker buildx build --platform $(PLATFORM) --progress=plain --no-cache -t $(FULL_IMAGE_NAME):$(TAG) .
	@echo "✅ Build complete: $(FULL_IMAGE_NAME):$(TAG)"

.PHONY: build-and-load
build-and-load: typecheck lint ## Build Docker image and load it to local Docker daemon
	@echo "Building and loading $(FULL_IMAGE_NAME):$(TAG) for platform $(PLATFORM)..."
	docker buildx build --platform $(PLATFORM) --load -t $(FULL_IMAGE_NAME):$(TAG) .
	@echo "✅ Build complete and loaded: $(FULL_IMAGE_NAME):$(TAG)"

.PHONY: run
run: ## Run the Docker container locally
	@echo "Running $(FULL_IMAGE_NAME):$(TAG)..."
	docker run --rm -p 3000:3000 --platform $(PLATFORM) $(FULL_IMAGE_NAME):$(TAG)

.PHONY: run-detached
run-detached: ## Run the Docker container in detached mode
	@echo "Running $(FULL_IMAGE_NAME):$(TAG) in detached mode..."
	docker run -d --name agentex-sgp-app -p 3000:3000 --platform $(PLATFORM) $(FULL_IMAGE_NAME):$(TAG)
	@echo "✅ Container started. Access at http://localhost:3000"

.PHONY: stop
stop: ## Stop the running container
	@echo "Stopping agentex-sgp-app container..."
	docker stop agentex-sgp-app || true
	docker rm agentex-sgp-app || true
	@echo "✅ Container stopped and removed"

.PHONY: push
push: ## Push the image to registry (requires REGISTRY to be set)
	@if [ -z "$(REGISTRY)" ]; then \
		echo "❌ Error: REGISTRY must be set to push image"; \
		echo "Usage: make push REGISTRY=your-registry.com"; \
		exit 1; \
	fi
	@echo "Pushing $(FULL_IMAGE_NAME):$(TAG)..."
	docker push $(FULL_IMAGE_NAME):$(TAG)
	@echo "✅ Push complete: $(FULL_IMAGE_NAME):$(TAG)"

.PHONY: build-and-push
build-and-push: typecheck lint ## Build and push Docker image directly (requires REGISTRY to be set)
	@if [ -z "$(REGISTRY)" ]; then \
		echo "❌ Error: REGISTRY must be set to build and push image"; \
		echo "Usage: make build-and-push REGISTRY=your-registry.com"; \
		exit 1; \
	fi
	@echo "Building and pushing $(FULL_IMAGE_NAME):$(TAG) for platform $(PLATFORM)..."
	docker buildx build --platform $(PLATFORM) --push -t $(FULL_IMAGE_NAME):$(TAG) .
	@echo "✅ Build and push complete: $(FULL_IMAGE_NAME):$(TAG)"

.PHONY: clean
clean: ## Remove the Docker image
	@echo "Removing $(FULL_IMAGE_NAME):$(TAG)..."
	docker rmi $(FULL_IMAGE_NAME):$(TAG) || true
	@echo "✅ Image removed"

.PHONY: inspect
inspect: ## Inspect the Docker image
	@echo "Inspecting $(FULL_IMAGE_NAME):$(TAG)..."
	docker inspect $(FULL_IMAGE_NAME):$(TAG)

.PHONY: logs
logs: ## Show logs from running container
	docker logs -f agentex-sgp-app

.PHONY: shell
shell: ## Open shell in running container
	docker exec -it agentex-sgp-app /bin/sh

# Development helpers
.PHONY: dev
dev: install ## Run development server locally (without Docker)
	npm run dev

.PHONY: install
install: ## Install dependencies
	npm install

.PHONY: typecheck
typecheck: ## Run TypeScript type checking
	npm run typecheck

.PHONY: lint
lint: ## Run linting
	npm run lint

# Quick build and run
.PHONY: build-and-run
build-and-run: build-and-load run ## Build and run the container

.PHONY: build-and-run-detached
build-and-run-detached: build-and-load run-detached ## Build and run the container in detached mode

# Example usage with custom parameters:
# make build TAG=v1.0.0 REGISTRY=myregistry.com
# make push TAG=v1.0.0 REGISTRY=myregistry.com
# make build IMAGE_NAME=my-custom-name TAG=latest 