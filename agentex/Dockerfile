# Public versioned Chainguard language images require org access; install Python 3.12 from Wolfi instead.
FROM cgr.dev/chainguard/wolfi-base:latest AS base
ARG SOURCE_DIR=agentex

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /uvx /bin/

# Install system dependencies
USER root
RUN apk add --no-cache \
    bash \
    curl \
    postgresql-client \
    build-base \
    libpq \
    gcc \
    python-3.12-dev \
    py3.12-pip

WORKDIR /app

# Copy dependency management files (workspace root + member + lockfile for reproducible builds)
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY ${SOURCE_DIR}/pyproject.toml ${SOURCE_DIR}/README.md ./${SOURCE_DIR}/

# Install core dependencies to system Python (Debian installs to /usr/local)
ENV UV_PROJECT_ENVIRONMENT=/usr
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
# Public versioned Chainguard language images require org access; install Python 3.12 from Wolfi instead.
FROM cgr.dev/chainguard/wolfi-base:latest AS production
ENTRYPOINT []
ARG INCLUDE_DOCS=false
ARG SOURCE_DIR=agentex

# Install runtime system dependencies only (no build tools)
USER root
RUN apk add --no-cache \
    postgresql-client \
    libpq \
    python-3.12

WORKDIR /app

# Copy Python packages and console_scripts from base stage.
COPY --from=base /usr/lib/python3.12 /usr/lib/python3.12
COPY --from=base /usr/bin/uvicorn /usr/bin/uvicorn
COPY --from=base /usr/bin/ddtrace-run /usr/bin/ddtrace-run
COPY --from=base /usr/bin/alembic /usr/bin/alembic

# Remove non-functional Cargo.lock metadata from temporalio wheel
# (quinn-proto is a transitive Rust dep not used at runtime — temporalio uses gRPC/TCP, not QUIC)
RUN rm -f /usr/lib/python3.12/site-packages/temporalio/bridge/Cargo.lock

# Copy application files
COPY ${SOURCE_DIR}/pyproject.toml ${SOURCE_DIR}/README.md ./
COPY ${SOURCE_DIR}/src/ src/
COPY ${SOURCE_DIR}/database/ database/
COPY ${SOURCE_DIR}/logging_config.conf logging_config.conf
COPY LICENSE /app/LICENSE

# Conditionally copy docs from builder stage
COPY --from=docs-builder /app/docs/site /app/docs/site

# Set ownership to Chainguard's default nonroot user.
RUN chown -R 65532:65532 /app

USER nonroot

EXPOSE 5003
ENV PYTHONPATH=/app
CMD ["ddtrace-run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "5003"]
