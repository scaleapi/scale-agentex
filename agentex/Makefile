# AgentEx Makefile
# Provides automation for development workflows


#
# Development Commands
#

.PHONY: install install-dev install-docs clean help

help: ## Show this help message
	@echo "AgentEx Development Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install dependencies
	@echo "🚀 Installing dependencies..."
	uv sync
	cd .. && uv run pre-commit install

install-dev: ../repo-setup ## Install dependencies including dev group
	@echo "🚀 Installing dependencies with dev group..."
	uv sync --group dev

../repo-setup:
	@$(MAKE) -C .. repo-setup

install-docs: ## Install docs dependencies
	@echo "🚀 Installing docs dependencies..."
	uv sync --group docs

clean: ## Clean virtual environment and lock file
	@echo "🧹 Cleaning virtual environment..."
	rm -rf .venv uv.lock

env: ## Activate virtual environment
	@echo "Use: source .venv/bin/activate"


#
# Development Server
#

dev: install-dev ## Start development server with Docker Compose
	@echo "🚀 Starting development server with Docker Compose..."
	docker compose up --build

dev-stop: ## Stop development server
	@echo "Stopping dev server"
	docker compose down

dev-wipe: ## Stop dev server and wipe DB
	@echo "Stopping dev server and wiping DB"
	docker compose down -v

# Database Commands
#

migration: ## Create a new migration (usage: make migration NAME="migration_name")
	@if [ -z "$(NAME)" ]; then \
		echo "❌ Error: NAME is required"; \
		echo "Usage: make migration NAME=\"migration_name\""; \
		exit 1; \
	fi
	cd database/migrations && alembic revision --autogenerate -m '$(NAME)'
	cd database/migrations && alembic history > migration_history.txt

apply-migrations: ## Apply database migrations
	cd database/migrations && alembic upgrade head

#
# Documentation
#

serve-docs: ## Serve documentation locally
	@echo "📚 Installing docs dependencies..."
	uv sync --group docs
	cd docs && uv run mkdocs serve -a localhost:8001

build-docs: ## Build documentation
	@echo "📚 Building documentation..."
	uv sync --group docs
	cd docs && uv run mkdocs build

docker-build: ## Build production Docker image
	@echo "🐳 Building production Docker image..."
	docker buildx build --platform=linux/amd64 --load -f Dockerfile --target production -t agentex:latest ../

docker-build-with-docs: ## Build production Docker image with docs included
	@echo "🐳 Building production Docker image with docs..."
	docker buildx build --platform=linux/amd64 --load -f Dockerfile --target production -t agentex:latest --build-arg INCLUDE_DOCS=true .

#
# Deployment Commands
#

minikube: ## Deploy to Minikube
	make -f Makefile.minikube dev

staging-deploy: ## Deploy to staging
	make -f Makefile.staging deploy

staging-setup: ## Setup staging environment
	make -f Makefile.staging setup

staging-update-backend: ## Update backend in staging
	make -f Makefile.staging build-and-push-backend

staging-update-backend-tagged: ## Update backend with tags in staging
	make -f Makefile.staging build-and-push-backend-tagged

staging-update-web: ## Update web in staging
	make -f Makefile.staging build-and-push-web

staging-update-all: ## Update all services in staging
	make -f Makefile.staging build-and-push-all

staging-port-forward: ## Port forward staging services
	make -f Makefile.staging port-forward

#
# Test Commands
#

test: ## Run tests (examples: make test FILE=path/to/test.py, make test NAME=pattern, make test ARGS="-v")
	@uv run python scripts/run_tests.py \
		$(if $(FILE),$(FILE)) \
		$(if $(NAME),-k "$(NAME)") \
		$(if $(ARGS),--pytest-args "$(ARGS)")

test-unit: ## Run unit tests only
	@uv run python scripts/run_tests.py -m unit

test-integration: ## Run integration tests only
	@uv run python scripts/run_tests.py -m integration

test-cov: ## Run tests with coverage report
	@uv run python scripts/run_tests.py --cov=src --cov-report=html --cov-report=term

test-docker-check: ## Check Docker environment setup for testing
	@uv run python scripts/test_setup.py --check-docker

test-help: ## Show test command examples
	@echo "Test Command Examples:"
	@echo "  make test                              # Run all tests"
	@echo "  make test FILE=tests/unit/             # Run all unit tests"  
	@echo "  make test FILE=tests/unit/test_foo.py  # Run specific file"
	@echo "  make test NAME=crud                    # Run tests matching 'crud'"
	@echo "  make test NAME='test_create or test_update'  # Multiple patterns"
	@echo "  make test ARGS='-v -s'                 # Pass pytest arguments"
	@echo "  make test-unit                         # Shortcut for unit tests"
	@echo "  make test-integration                  # Shortcut for integration tests"
	@echo "  make test-cov                          # Run with coverage report"
	@echo "  make test-docker-check                 # Check Docker setup"
