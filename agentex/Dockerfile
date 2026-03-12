FROM 022465994601.dkr.ecr.us-west-2.amazonaws.com/golden/chainguard/python:3.12-dev AS base
ARG SOURCE_DIR=public/agentex

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
    gcc \
    busybox

WORKDIR /app

# Copy dependency management files
COPY ${SOURCE_DIR}/pyproject.toml ${SOURCE_DIR}/README.md ./

# Install core dependencies to system Python (Chainguard prefix is /usr)
ENV UV_PROJECT_ENVIRONMENT=/usr
RUN uv sync

# Development stage (for docker-compose)
FROM base AS dev
ENTRYPOINT []
ARG SOURCE_DIR=public/agentex

# Install dev dependencies to system Python
RUN uv sync --group dev

COPY ${SOURCE_DIR}/src/ ./src/
EXPOSE 5003
ENV PYTHONPATH=/app
CMD ["ddtrace-run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "5003", "--reload"]

# Docs builder stage
FROM base AS docs-builder
ARG SOURCE_DIR=public/agentex

# Install docs dependencies to system Python
RUN uv sync --group docs

COPY ${SOURCE_DIR}/docs/ docs/
COPY ${SOURCE_DIR}/src/ src/
RUN cd docs && mkdocs build

# Production stage
# NOTE: -dev variant required at runtime for apk (libpq, postgresql-client needed by psycopg2)
FROM 022465994601.dkr.ecr.us-west-2.amazonaws.com/golden/chainguard/python:3.12-dev AS production
ENTRYPOINT []
ARG INCLUDE_DOCS=false
ARG SOURCE_DIR=public/agentex

# Install runtime system dependencies only (no build tools)
USER root
RUN apk add --no-cache \
    postgresql-client \
    libpq

WORKDIR /app

# Copy Python packages and console_scripts from base stage (Chainguard installs to /usr/lib/python3.12)
COPY --from=base /usr/lib/python3.12 /usr/lib/python3.12
# Copy only the Python-installed console_scripts (e.g. uvicorn, ddtrace-run), not build tools
COPY --from=base /usr/bin/uvicorn /usr/bin/uvicorn
COPY --from=base /usr/bin/ddtrace-run /usr/bin/ddtrace-run
COPY --from=base /usr/bin/python3 /usr/bin/python3
COPY --from=base /usr/bin/python3.12 /usr/bin/python3.12

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
