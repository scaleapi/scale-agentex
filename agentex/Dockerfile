FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    htop \
    vim \
    curl \
    tar \
    python3-dev \
    postgresql-client \
    build-essential \
    libpq-dev \
    gcc \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency management files
COPY agentex/pyproject.toml agentex/README.md ./

# Install core dependencies
ENV UV_PROJECT_ENVIRONMENT=/usr/local
RUN uv sync

# Development stage (for docker-compose)
FROM base AS dev

# Install dev dependencies
RUN uv sync --group dev

COPY agentex/src/ ./src/
EXPOSE 5003
ENV PYTHONPATH=/app
CMD ["ddtrace-run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "5003", "--reload"]

# Docs builder stage
FROM base AS docs-builder

# Install docs dependencies
RUN uv sync --group docs

COPY agentex/docs/ docs/
COPY agentex/src/ src/
RUN cd docs && mkdocs build

# Production stage
FROM base AS production
ARG INCLUDE_DOCS=false

# Conditionally copy docs from builder stage
COPY --from=docs-builder /app/docs/site /app/docs/site

COPY agentex/src/ src/
COPY agentex/database/ database/
COPY agentex/logging_config.conf logging_config.conf
COPY LICENSE /app/LICENSE

EXPOSE 5003
ENV PYTHONPATH=/app
CMD ["ddtrace-run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "5003"]
