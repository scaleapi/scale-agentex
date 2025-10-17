# syntax=docker/dockerfile:1
FROM python:3.12-slim


# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set environment variables for uv
ENV UV_CACHE_DIR=/tmp/uv-cache

WORKDIR /app

# Copy workspace and project files
COPY uv.lock pyproject.toml ./
COPY agentex-auth/ ./agentex-auth/

# Install dependencies directly into system Python
# First install the agentex-auth project dependencies
RUN --mount=type=cache,target=/tmp/uv-cache \
    cd agentex-auth && \
    uv pip install --system .

# Change to the agentex-auth directory for running the app
WORKDIR /app/agentex-auth

# Expose the default port that uvicorn will listen on
ENV PYTHONPATH=/app
EXPOSE 5000

# Run uvicorn directly - no uv run needed!
CMD ["ddtrace-run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "5000"] 
