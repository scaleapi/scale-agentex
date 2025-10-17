# AgentEx Workspace Makefile
.PHONY: repo-setup help

repo-setup: ## Setup development environment for the workspace
	uv sync --group dev
	uv run pre-commit install

help: ## Show this help message  
	@echo "AgentEx Workspace Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\\n", $$1, $$2}'