from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

from src.utils.logging import make_logger
from src.utils.model_utils import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = make_logger(__name__)


class EnvVarKeys(str, Enum):
    ENVIRONMENT = "ENVIRONMENT"
    OPENAI_API_KEY = "OPENAI_API_KEY"
    DATABASE_URL = "DATABASE_URL"
    READ_ONLY_DATABASE_URL = "READ_ONLY_DATABASE_URL"
    TEMPORAL_ADDRESS = "TEMPORAL_ADDRESS"
    TEMPORAL_NAMESPACE = "TEMPORAL_NAMESPACE"
    REDIS_URL = "REDIS_URL"
    AGENTEX_BASE_URL = "AGENTEX_BASE_URL"
    TEMPORAL_WORKER_ACTIVITY_THREAD_POOL_SIZE = (
        "TEMPORAL_WORKER_ACTIVITY_THREAD_POOL_SIZE"
    )
    TEMPORAL_WORKER_MAX_ACTIVITIES_PER_WORKER = (
        "TEMPORAL_WORKER_MAX_ACTIVITIES_PER_WORKER"
    )
    BUILD_REGISTRY_URL = "BUILD_REGISTRY_URL"
    BUILD_CONTEXTS_PATH = "BUILD_CONTEXTS_PATH"
    BUILD_CONTEXT_PVC_NAME = "BUILD_CONTEXT_PVC_NAME"
    BUILD_REGISTRY_SECRET_NAME = "BUILD_REGISTRY_SECRET_NAME"
    AGENTS_NAMESPACE = "AGENTS_NAMESPACE"
    MONGODB_URI = "MONGODB_URI"
    MONGODB_DATABASE_NAME = "MONGODB_DATABASE_NAME"
    MONGODB_MAX_POOL_SIZE = "MONGODB_MAX_POOL_SIZE"
    MONGODB_MIN_POOL_SIZE = "MONGODB_MIN_POOL_SIZE"
    REDIS_MAX_CONNECTIONS = "REDIS_MAX_CONNECTIONS"
    REDIS_CONNECTION_TIMEOUT = "REDIS_CONNECTION_TIMEOUT"
    REDIS_SOCKET_TIMEOUT = "REDIS_SOCKET_TIMEOUT"
    REDIS_STREAM_MAXLEN = "REDIS_STREAM_MAXLEN"
    IMAGE_PULL_SECRET_NAME = "IMAGE_PULL_SECRET_NAME"
    AGENTEX_AUTH_URL = "AGENTEX_AUTH_URL"
    ALLOWED_ORIGINS = "ALLOWED_ORIGINS"
    DD_AGENT_HOST = "DD_AGENT_HOST"
    DD_STATSD_PORT = "DD_STATSD_PORT"
    HTTPX_CONNECT_TIMEOUT = "HTTPX_CONNECT_TIMEOUT"
    HTTPX_READ_TIMEOUT = "HTTPX_READ_TIMEOUT"
    HTTPX_WRITE_TIMEOUT = "HTTPX_WRITE_TIMEOUT"
    HTTPX_POOL_TIMEOUT = "HTTPX_POOL_TIMEOUT"
    HTTPX_STREAMING_READ_TIMEOUT = "HTTPX_STREAMING_READ_TIMEOUT"
    SSE_KEEPALIVE_PING_INTERVAL = "SSE_KEEPALIVE_PING_INTERVAL"
    AGENTEX_SERVER_TASK_QUEUE = "AGENTEX_SERVER_TASK_QUEUE"
    ENABLE_HEALTH_CHECK_WORKFLOW = "ENABLE_HEALTH_CHECK_WORKFLOW"
    WEBHOOK_REQUEST_TIMEOUT = "WEBHOOK_REQUEST_TIMEOUT"
    TASK_STATE_STORAGE_PHASE = "TASK_STATE_STORAGE_PHASE"
    TASK_MESSAGE_STORAGE_PHASE = "TASK_MESSAGE_STORAGE_PHASE"


class Environment(str, Enum):
    DEV = "development"
    STAGING = "staging"
    PROD = "production"


refreshed_environment_variables = None


class EnvironmentVariables(BaseModel):
    ENVIRONMENT: str | None = Environment.DEV
    OPENAI_API_KEY: str | None
    DATABASE_URL: str | None
    READ_ONLY_DATABASE_URL: str | None = None
    TEMPORAL_ADDRESS: str | None
    TEMPORAL_NAMESPACE: str | None
    REDIS_URL: str | None
    AGENTEX_BASE_URL: str | None
    TEMPORAL_WORKER_ACTIVITY_THREAD_POOL_SIZE: int = 4  # Default 4 for local dev
    TEMPORAL_WORKER_MAX_ACTIVITIES_PER_WORKER: int = 10  # Default 10 for local dev
    BUILD_REGISTRY_URL: str | None = None
    BUILD_CONTEXTS_PATH: str | None = None
    BUILD_CONTEXT_PVC_NAME: str | None = None
    BUILD_REGISTRY_SECRET_NAME: str | None = None
    AGENTS_NAMESPACE: str | None = None
    MONGODB_URI: str | None = None
    MONGODB_DATABASE_NAME: str | None = "agentex"
    MONGODB_MAX_POOL_SIZE: int = 50
    MONGODB_MIN_POOL_SIZE: int = 5
    REDIS_MAX_CONNECTIONS: int = 50  # Increased for SSE streaming
    REDIS_CONNECTION_TIMEOUT: int = 60  # Connection timeout in seconds
    REDIS_SOCKET_TIMEOUT: int = 30  # Socket timeout in seconds
    REDIS_STREAM_MAXLEN: int = (
        10000  # Max entries per Redis stream to prevent unbounded growth
    )
    IMAGE_PULL_SECRET_NAME: str | None = None
    AGENTEX_AUTH_URL: str | None = None
    ALLOWED_ORIGINS: str | None = None
    HTTPX_CONNECT_TIMEOUT: float = 10.0  # HTTPX connection timeout in seconds
    HTTPX_READ_TIMEOUT: float = 30.0  # HTTPX read timeout in seconds
    HTTPX_WRITE_TIMEOUT: float = 30.0  # HTTPX write timeout in seconds
    HTTPX_POOL_TIMEOUT: float = 10.0  # HTTPX pool timeout in seconds
    HTTPX_STREAMING_READ_TIMEOUT: float = (
        300.0  # HTTPX streaming read timeout in seconds (5 minutes)
    )
    SSE_KEEPALIVE_PING_INTERVAL: int = 15  # SSE keepalive ping interval in seconds
    AGENTEX_SERVER_TASK_QUEUE: str | None = None
    ENABLE_HEALTH_CHECK_WORKFLOW: bool = False
    WEBHOOK_REQUEST_TIMEOUT: float = 15.0  # Webhook request timeout in seconds
    TASK_STATE_STORAGE_PHASE: str = (
        "mongodb"  # mongodb | dual_write | dual_read | postgres
    )
    TASK_MESSAGE_STORAGE_PHASE: str = (
        "mongodb"  # mongodb | dual_write | dual_read | postgres
    )

    @classmethod
    def refresh(cls, force_refresh: bool = False) -> EnvironmentVariables | None:
        global refreshed_environment_variables
        if refreshed_environment_variables is not None and not force_refresh:
            return refreshed_environment_variables

        if os.environ.get(EnvVarKeys.ENVIRONMENT) == Environment.DEV:
            load_dotenv(dotenv_path=Path(PROJECT_ROOT / ".env"), override=True)
        environment_variables = EnvironmentVariables(
            ENVIRONMENT=os.environ.get(EnvVarKeys.ENVIRONMENT),
            OPENAI_API_KEY=os.environ.get(EnvVarKeys.OPENAI_API_KEY),
            DATABASE_URL=os.environ.get(EnvVarKeys.DATABASE_URL),
            READ_ONLY_DATABASE_URL=os.environ.get(EnvVarKeys.READ_ONLY_DATABASE_URL),
            TEMPORAL_ADDRESS=os.environ.get(EnvVarKeys.TEMPORAL_ADDRESS),
            TEMPORAL_NAMESPACE=os.environ.get(EnvVarKeys.TEMPORAL_NAMESPACE),
            REDIS_URL=os.environ.get(EnvVarKeys.REDIS_URL),
            AGENTEX_BASE_URL=os.environ.get(EnvVarKeys.AGENTEX_BASE_URL),
            BUILD_REGISTRY_URL=os.environ.get(EnvVarKeys.BUILD_REGISTRY_URL),
            BUILD_CONTEXTS_PATH=os.environ.get(EnvVarKeys.BUILD_CONTEXTS_PATH),
            BUILD_CONTEXT_PVC_NAME=os.environ.get(EnvVarKeys.BUILD_CONTEXT_PVC_NAME),
            BUILD_REGISTRY_SECRET_NAME=os.environ.get(
                EnvVarKeys.BUILD_REGISTRY_SECRET_NAME
            ),
            AGENTS_NAMESPACE=os.environ.get(EnvVarKeys.AGENTS_NAMESPACE),
            MONGODB_URI=os.environ.get(EnvVarKeys.MONGODB_URI),
            MONGODB_DATABASE_NAME=os.environ.get(
                EnvVarKeys.MONGODB_DATABASE_NAME, "agentex"
            ),
            MONGODB_MAX_POOL_SIZE=int(
                os.environ.get(EnvVarKeys.MONGODB_MAX_POOL_SIZE, "50")
            ),
            MONGODB_MIN_POOL_SIZE=int(
                os.environ.get(EnvVarKeys.MONGODB_MIN_POOL_SIZE, "5")
            ),
            REDIS_MAX_CONNECTIONS=int(
                os.environ.get(EnvVarKeys.REDIS_MAX_CONNECTIONS, "100")
            ),
            REDIS_CONNECTION_TIMEOUT=int(
                os.environ.get(EnvVarKeys.REDIS_CONNECTION_TIMEOUT, "20")
            ),
            REDIS_SOCKET_TIMEOUT=int(
                os.environ.get(EnvVarKeys.REDIS_SOCKET_TIMEOUT, "30")
            ),
            REDIS_STREAM_MAXLEN=int(
                os.environ.get(EnvVarKeys.REDIS_STREAM_MAXLEN, "10000")
            ),
            IMAGE_PULL_SECRET_NAME=os.environ.get(EnvVarKeys.IMAGE_PULL_SECRET_NAME),
            AGENTEX_AUTH_URL=os.environ.get(EnvVarKeys.AGENTEX_AUTH_URL),
            ALLOWED_ORIGINS=os.environ.get(EnvVarKeys.ALLOWED_ORIGINS, "*"),
            DD_AGENT_HOST=os.environ.get(EnvVarKeys.DD_AGENT_HOST),
            DD_STATSD_PORT=os.environ.get(EnvVarKeys.DD_STATSD_PORT),
            HTTPX_CONNECT_TIMEOUT=float(
                os.environ.get(EnvVarKeys.HTTPX_CONNECT_TIMEOUT, "10.0")
            ),
            HTTPX_READ_TIMEOUT=float(
                os.environ.get(EnvVarKeys.HTTPX_READ_TIMEOUT, "30.0")
            ),
            HTTPX_WRITE_TIMEOUT=float(
                os.environ.get(EnvVarKeys.HTTPX_WRITE_TIMEOUT, "30.0")
            ),
            HTTPX_POOL_TIMEOUT=float(
                os.environ.get(EnvVarKeys.HTTPX_POOL_TIMEOUT, "10.0")
            ),
            HTTPX_STREAMING_READ_TIMEOUT=float(
                os.environ.get(EnvVarKeys.HTTPX_STREAMING_READ_TIMEOUT, "300.0")
            ),
            SSE_KEEPALIVE_PING_INTERVAL=int(
                os.environ.get(EnvVarKeys.SSE_KEEPALIVE_PING_INTERVAL, "15")
            ),
            AGENTEX_SERVER_TASK_QUEUE=os.environ.get(
                EnvVarKeys.AGENTEX_SERVER_TASK_QUEUE
            ),
            ENABLE_HEALTH_CHECK_WORKFLOW=(
                os.environ.get(EnvVarKeys.ENABLE_HEALTH_CHECK_WORKFLOW, "false")
                == "true"
            ),
            WEBHOOK_REQUEST_TIMEOUT=float(
                os.environ.get(EnvVarKeys.WEBHOOK_REQUEST_TIMEOUT, "15.0")
            ),
            TASK_STATE_STORAGE_PHASE=os.environ.get(
                EnvVarKeys.TASK_STATE_STORAGE_PHASE, "mongodb"
            ),
            TASK_MESSAGE_STORAGE_PHASE=os.environ.get(
                EnvVarKeys.TASK_MESSAGE_STORAGE_PHASE, "mongodb"
            ),
        )
        refreshed_environment_variables = environment_variables
        return refreshed_environment_variables

    @classmethod
    def clear_cache(cls):
        """Clear the cached environment variables to force refresh on next access"""
        global refreshed_environment_variables
        refreshed_environment_variables = None
