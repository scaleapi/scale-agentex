.PHONY: build run dev

IMAGE ?= agentex-auth

build:
	cd .. && docker buildx build -t $(IMAGE) -f agentex-auth/Dockerfile . --platform linux/amd64

run:
	docker run --rm -it -p 5000:5000 $(IMAGE)

# Start the app locally with auto-reload for development
# Requires dependencies installed in the local environment
# (e.g. `pip install -e .[dev]`)

dev:
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 5000 

lint:
	uv run ruff check --fix && uv run ruff format
