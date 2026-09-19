# AgentEx Workspace Makefile
.PHONY: repo-setup help lint test

repo-setup: ## Setup development environment for the workspace
	uv sync --group dev
	uv run pre-commit install

lint: ## Run backend lint + format checks (delegates to agentex/)
	$(MAKE) -C agentex lint

test: ## Run backend tests (delegates to agentex/; see agentex/Makefile for FILE/NAME/ARGS)
	$(MAKE) -C agentex test

help: ## Show this help message  
	@echo "AgentEx Workspace Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\\n", $$1, $$2}'