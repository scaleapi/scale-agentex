FROM cgr.dev/chainguard/python:latest-dev AS base
ARG SOURCE_DIR=agentex

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /uvx /bin/

# Install system dependencies
USER root
RUN apk add --no-cache \
    bash \
    curl \
    postgresql-client \
    build-base \
    libpq \
    gcc

WORKDIR /app

# Copy dependency management files (workspace root + member + lockfile for reproducible builds)
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY ${SOURCE_DIR}/pyproject.toml ${SOURCE_DIR}/README.md ./${SOURCE_DIR}/

# Install core dependencies into a venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv venv /opt/venv && uv sync --frozen --no-dev --package agentex-backend
ENV PATH="/opt/venv/bin:$PATH"

# Development stage (for docker-compose)
FROM base AS dev
ENTRYPOINT []
ARG SOURCE_DIR=agentex

# Install dev dependencies to system Python
RUN uv sync --frozen --group dev --package agentex-backend

COPY ${SOURCE_DIR}/src/ ./src/
EXPOSE 5003
ENV PYTHONPATH=/app
CMD ["ddtrace-run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "5003", "--reload"]

# Docs builder stage
FROM base AS docs-builder
ARG SOURCE_DIR=agentex

# Install docs dependencies to system Python
RUN uv sync --frozen --group docs --package agentex-backend

COPY ${SOURCE_DIR}/docs/ docs/
COPY ${SOURCE_DIR}/src/ src/
RUN cd docs && mkdocs build

# Production stage
# NOTE: -dev variant required at runtime for apk (libpq, postgresql-client needed by psycopg2)
FROM cgr.dev/chainguard/python:latest-dev AS production
ENTRYPOINT []
ARG INCLUDE_DOCS=false
ARG SOURCE_DIR=agentex

# Install runtime system dependencies only (no build tools)
USER root
RUN apk add --no-cache \
    postgresql-client \
    libpq

WORKDIR /app

# Copy the venv with all installed packages from base stage
COPY --from=base /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application files
COPY ${SOURCE_DIR}/pyproject.toml ${SOURCE_DIR}/README.md ./
COPY ${SOURCE_DIR}/src/ src/
COPY ${SOURCE_DIR}/database/ database/
COPY ${SOURCE_DIR}/logging_config.conf logging_config.conf
COPY LICENSE /app/LICENSE

# Conditionally copy docs from builder stage
COPY --from=docs-builder /app/docs/site /app/docs/site

# Set ownership to Chainguard's default nonroot user (UID 65532)
RUN chown -R 65532:65532 /app

USER nonroot

EXPOSE 5003
ENV PYTHONPATH=/app
CMD ["ddtrace-run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "5003"]
