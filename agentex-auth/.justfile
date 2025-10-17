dev:
    uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 5006

lint:
    uv run ruff check --fix && uv run ruff format