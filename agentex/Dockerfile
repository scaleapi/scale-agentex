FROM python:3.12-slim-trixie AS base
ARG SOURCE_DIR=agentex

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /uvx /bin/

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    postgresql-client \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency management files (workspace root + member + lockfile for reproducible builds)
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY ${SOURCE_DIR}/pyproject.toml ${SOURCE_DIR}/README.md ./${SOURCE_DIR}/

# Install core dependencies to system Python (Debian installs to /usr/local)
ENV UV_PROJECT_ENVIRONMENT=/usr/local
RUN uv sync --frozen --no-dev --package agentex-backend

# Development stage (for docker-compose)
FROM base AS dev
ENTRYPOINT []
ARG SOURCE_DIR=agentex

# Install dev dependencies to system Python
RUN uv sync --frozen --group dev --package agentex-backend

COPY ${SOURCE_DIR}/src/ ./src/
EXPOSE 5003
ENV PYTHONPATH=/app
# Dev / single-worker stage. `--reload` doesn't work with `--workers >1`.
# Production multi-worker config is set in the final stage at the bottom of
# this file.
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
FROM python:3.12-slim-trixie AS production
ENTRYPOINT []
ARG INCLUDE_DOCS=false
ARG SOURCE_DIR=agentex

# Install runtime system dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages and console_scripts from base stage (Debian installs to /usr/local)
COPY --from=base /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=base /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=base /usr/local/bin/ddtrace-run /usr/local/bin/ddtrace-run
COPY --from=base /usr/local/bin/alembic /usr/local/bin/alembic

# Remove non-functional Cargo.lock metadata from temporalio wheel
# (quinn-proto is a transitive Rust dep not used at runtime — temporalio uses gRPC/TCP, not QUIC)
RUN rm -f /usr/local/lib/python3.12/site-packages/temporalio/bridge/Cargo.lock

# Copy application files
COPY ${SOURCE_DIR}/pyproject.toml ${SOURCE_DIR}/README.md ./
COPY ${SOURCE_DIR}/src/ src/
COPY ${SOURCE_DIR}/database/ database/
COPY ${SOURCE_DIR}/logging_config.conf logging_config.conf
COPY LICENSE /app/LICENSE

# Conditionally copy docs from builder stage
COPY --from=docs-builder /app/docs/site /app/docs/site

# Create nonroot user and set ownership
RUN adduser --disabled-password --gecos '' --uid 65532 nonroot && chown -R nonroot:nonroot /app

USER nonroot

EXPOSE 5003
ENV PYTHONPATH=/app
# Run uvicorn with multiple workers so a single pod isn't bottlenecked to one
# in-flight request at a time. The MongoDB adapter uses `pymongo` (sync) inside
# `async def` methods, which blocks the event loop for the duration of every
# Mongo round-trip; the only way to get per-pod concurrency today is via
# separate worker processes. Default of 4 is a safe match for the typical 1
# CPU / 2Gi pod limits; bump UVICORN_WORKERS up to ~cpu_count when those
# limits are increased.
ENV UVICORN_WORKERS=4
CMD ["sh", "-c", "exec ddtrace-run uvicorn src.api.app:app --host 0.0.0.0 --port 5003 --workers ${UVICORN_WORKERS}"]
