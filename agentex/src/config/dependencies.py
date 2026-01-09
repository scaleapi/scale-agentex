import asyncio
import os
from typing import Annotated

import httpx
import pymongo
import redis.asyncio as redis
from docker import DockerClient
from fastapi import Depends
from kubernetes_asyncio import config as k8s_config
from pymongo.database import Database as MongoDBDatabase
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from temporalio.client import Client as TemporalClient

from src.config.environment_variables import Environment, EnvironmentVariables
from src.utils.database import async_db_engine_creator
from src.utils.db_metrics import PostgresMetricsCollector
from src.utils.logging import make_logger

logger = make_logger(__name__)


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class GlobalDependencies(metaclass=Singleton):
    def __init__(self):
        self.environment_variables: EnvironmentVariables = (
            EnvironmentVariables.refresh()
        )
        self.temporal_client: TemporalClient | None = None
        self.database_async_read_write_engine: AsyncEngine | None = None
        self.database_async_middleware_read_write_engine: AsyncEngine | None = None
        self.docker_client = None
        self.mongodb_client: pymongo.MongoClient | None = None
        self.mongodb_database: MongoDBDatabase | None = None
        self.httpx_client: httpx.AsyncClient | None = None
        self.redis_pool: redis.ConnectionPool | None = None
        self.database_async_read_only_engine: AsyncEngine | None = None
        self.postgres_metrics_collector: PostgresMetricsCollector | None = None
        self._loaded = False

    async def create_temporal_client(self):
        # Import locally to avoid circular dependency
        from src.adapters.temporal.client_factory import TemporalClientFactory

        if not TemporalClientFactory.is_temporal_configured(self.environment_variables):
            return None
        else:
            logger.info(
                f"Creating temporal client with address: {self.environment_variables.TEMPORAL_ADDRESS}"
            )
            return await TemporalClientFactory.create_client_from_env(
                environment_variables=self.environment_variables
            )

    async def load(self):
        if self._loaded:
            return

        self.environment_variables = EnvironmentVariables.refresh()

        try:
            self.temporal_client = await self.create_temporal_client()
        except Exception as e:
            logger.error(f"Failed to initialize temporal client: {e}")
            self.temporal_client = None

        self.docker_client = None

        # echo_db_engine = self.environment_variables.ENVIRONMENT == Environment.DEV
        echo_db_engine = False
        # Increased pool sizes to handle higher concurrency
        # Each concurrent request needs ~1-2 connections
        async_db_pool_size = int(
            os.environ.get("POSTGRES_POOL_SIZE", "10")
        )  # Support 25-50 concurrent requests
        middleware_db_pool_size = int(
            os.environ.get("POSTGRES_MIDDLEWARE_POOL_SIZE", "5")
        )  # Support middleware operations

        # https://docs.sqlalchemy.org/en/20/core/engines.html#sqlalchemy.create_engine
        self.database_async_read_write_engine = create_async_engine(
            "postgresql+asyncpg://",
            async_creator=async_db_engine_creator(
                self.environment_variables.DATABASE_URL,
            ),
            echo=echo_db_engine,
            pool_size=async_db_pool_size,
            max_overflow=20,  # Allow 20 additional connections beyond pool_size when needed
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

        self.database_async_middleware_read_write_engine = create_async_engine(
            "postgresql+asyncpg://",
            async_creator=async_db_engine_creator(
                self.environment_variables.DATABASE_URL,
            ),
            echo=echo_db_engine,
            pool_size=middleware_db_pool_size,
            max_overflow=10,  # Allow 10 additional connections for middleware
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

        # Initialize MongoDB client and database
        try:
            mongodb_uri = self.environment_variables.MONGODB_URI
            mongodb_database_name = self.environment_variables.MONGODB_DATABASE_NAME

            logger.info("Connecting to MongoDB")

            self.mongodb_client = pymongo.MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=20000,
                connectTimeoutMS=20000,
                socketTimeoutMS=20000,
                retryWrites=False,  # Disable retryable writes for AWS DocumentDB compatibility
                maxPoolSize=self.environment_variables.MONGODB_MAX_POOL_SIZE,
                minPoolSize=self.environment_variables.MONGODB_MIN_POOL_SIZE,
                maxIdleTimeMS=30000,  # Close connections after 30 seconds of inactivity
                waitQueueTimeoutMS=5000,  # Wait up to 5 seconds for a connection from pool
            )
            self.mongodb_database = self.mongodb_client[mongodb_database_name]

            # Ping the database to verify connection
            self.mongodb_client.admin.command("ping")
            logger.info(
                f"Successfully connected to MongoDB database '{mongodb_database_name}'"
            )

            # Create MongoDB indexes after successful connection
            # This happens once at startup, not per request
            from src.config.mongodb_indexes import ensure_mongodb_indexes

            try:
                ensure_mongodb_indexes(self.mongodb_database)
                logger.info("MongoDB indexes ensured successfully")
            except Exception as index_error:
                # Don't fail startup if index creation fails
                # The app can still work, just slower
                logger.error(f"Failed to create MongoDB indexes: {index_error}")

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB client: {e}")
            self.mongodb_client = None
            self.mongodb_database = None

        # Load Kubernetes configuration (local or in-cluster)
        if self.environment_variables.ENVIRONMENT != Environment.DEV:
            k8s_config.load_incluster_config()

        self.httpx_client = httpx.AsyncClient()

        # Initialize Redis connection pool
        if self.environment_variables.REDIS_URL:
            self.redis_pool = redis.ConnectionPool.from_url(
                self.environment_variables.REDIS_URL,
                decode_responses=False,
                max_connections=self.environment_variables.REDIS_MAX_CONNECTIONS,
                socket_connect_timeout=self.environment_variables.REDIS_CONNECTION_TIMEOUT,
                socket_timeout=self.environment_variables.REDIS_SOCKET_TIMEOUT,
                health_check_interval=30,
            )
            logger.info(
                f"Redis connection pool initialized with max_connections={self.environment_variables.REDIS_MAX_CONNECTIONS}"
            )

        # Create readonly engine - falls back to primary database if no replica URL is set
        read_only_db_url = (
            self.environment_variables.READ_ONLY_DATABASE_URL
            or self.environment_variables.DATABASE_URL
        )
        if read_only_db_url:
            self.database_async_read_only_engine = create_async_engine(
                "postgresql+asyncpg://",
                async_creator=async_db_engine_creator(read_only_db_url),
                echo=echo_db_engine,
                pool_size=async_db_pool_size,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
            )

        # Initialize PostgreSQL metrics collector
        self.postgres_metrics_collector = PostgresMetricsCollector()
        environment = self.environment_variables.ENVIRONMENT
        service_name = os.environ.get("OTEL_SERVICE_NAME", "agentex")

        if self.database_async_read_write_engine:
            self.postgres_metrics_collector.register_engine(
                engine=self.database_async_read_write_engine,
                pool_name="main",
                db_url=self.environment_variables.DATABASE_URL,
                environment=environment,
                service_name=service_name,
            )

        if self.database_async_middleware_read_write_engine:
            self.postgres_metrics_collector.register_engine(
                engine=self.database_async_middleware_read_write_engine,
                pool_name="middleware",
                db_url=self.environment_variables.DATABASE_URL,
                environment=environment,
                service_name=service_name,
            )

        if self.database_async_read_only_engine:
            # Check if this is actually a replica (different URL from primary)
            is_replica = (
                self.environment_variables.READ_ONLY_DATABASE_URL is not None
                and self.environment_variables.READ_ONLY_DATABASE_URL
                != self.environment_variables.DATABASE_URL
            )
            self.postgres_metrics_collector.register_engine(
                engine=self.database_async_read_only_engine,
                pool_name="readonly",
                db_url=read_only_db_url,
                environment=environment,
                is_replica=is_replica,
                service_name=service_name,
            )

        self._loaded = True

    async def force_reload(self):
        """Force reload all dependencies with fresh environment variables"""
        # Stop metrics collection
        if self.postgres_metrics_collector:
            await self.postgres_metrics_collector.stop_collection()

        # Clear existing connections
        if self.database_async_read_write_engine:
            await self.database_async_read_write_engine.dispose()
        if self.database_async_middleware_read_write_engine:
            await self.database_async_middleware_read_write_engine.dispose()
        if self.database_async_read_only_engine:
            await self.database_async_read_only_engine.dispose()
        if self.mongodb_client:
            self.mongodb_client.close()

        # Reset state
        self._loaded = False
        self.temporal_client = None
        self.database_async_read_write_engine = None
        self.database_async_middleware_read_write_engine = None
        self.database_async_read_only_engine = None
        self.docker_client = None
        self.mongodb_client = None
        self.mongodb_database = None
        self.postgres_metrics_collector = None

        # Reload with fresh environment variables
        EnvironmentVariables.clear_cache()
        await self.load()


async def startup_global_dependencies():
    global_dependencies = GlobalDependencies()
    await global_dependencies.load()


def shutdown():
    pass


async def async_shutdown():
    global_dependencies = GlobalDependencies()

    # Stop PostgreSQL metrics collection
    if global_dependencies.postgres_metrics_collector:
        await global_dependencies.postgres_metrics_collector.stop_collection()

    run_concurrently = []
    if global_dependencies.database_async_read_only_engine:
        run_concurrently.append(
            global_dependencies.database_async_read_only_engine.dispose()
        )
    if global_dependencies.database_async_read_write_engine:
        run_concurrently.append(
            global_dependencies.database_async_read_write_engine.dispose()
        )
    if global_dependencies.database_async_middleware_read_write_engine:
        run_concurrently.append(
            global_dependencies.database_async_middleware_read_write_engine.dispose()
        )
    await asyncio.gather(*run_concurrently)

    # Close MongoDB connection
    if global_dependencies.mongodb_client:
        global_dependencies.mongodb_client.close()

    # Close HTTPX client
    if global_dependencies.httpx_client:
        await global_dependencies.httpx_client.aclose()


def resolve_environment_variable_dependency(environment_variable_key: str):
    return getattr(GlobalDependencies().environment_variables, environment_variable_key)


def DEnvironmentVariable(environment_variable_key: str):
    def resolve():
        return resolve_environment_variable_dependency(environment_variable_key)

    return Annotated[str, Depends(resolve)]


def httpx_client() -> httpx.AsyncClient:
    return GlobalDependencies().httpx_client


def database_async_read_write_engine() -> AsyncEngine:
    return GlobalDependencies().database_async_read_write_engine


def database_async_read_only_engine() -> AsyncEngine:
    return GlobalDependencies().database_async_read_only_engine


def middleware_async_read_only_engine() -> AsyncEngine:
    return GlobalDependencies().database_async_middleware_read_write_engine


DDatabaseAsyncReadWriteEngine = Annotated[
    AsyncEngine, Depends(database_async_read_write_engine)
]

DDatabaseAsyncReadOnlyEngine = Annotated[
    AsyncEngine, Depends(database_async_read_only_engine)
]


def database_async_read_write_session_maker(
    db_async_read_write_engine: DDatabaseAsyncReadWriteEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        autoflush=False, bind=db_async_read_write_engine, expire_on_commit=False
    )


def database_async_read_only_session_maker(
    db_async_read_only_engine: DDatabaseAsyncReadOnlyEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        autoflush=False, bind=db_async_read_only_engine, expire_on_commit=False
    )


def middleware_async_read_only_session_maker() -> async_sessionmaker[AsyncSession]:
    engine = middleware_async_read_only_engine()
    return async_sessionmaker(autoflush=False, bind=engine, expire_on_commit=False)


DDatabaseAsyncReadWriteSessionMaker = Annotated[
    async_sessionmaker[AsyncSession], Depends(database_async_read_write_session_maker)
]

DDatabaseAsyncReadOnlySessionMaker = Annotated[
    async_sessionmaker[AsyncSession], Depends(database_async_read_only_session_maker)
]

DEnvironmentVariables = Annotated[
    EnvironmentVariables, Depends(lambda: GlobalDependencies().environment_variables)
]
DTemporalClient = Annotated[
    TemporalClient, Depends(lambda: GlobalDependencies().temporal_client)
]
DDockerClient = Annotated[
    DockerClient, Depends(lambda: GlobalDependencies().docker_client)
]
DMongoDBDatabase = Annotated[
    MongoDBDatabase, Depends(lambda: GlobalDependencies().mongodb_database)
]
DHttpxClient = Annotated[
    httpx.AsyncClient, Depends(lambda: GlobalDependencies().httpx_client)
]
DRedisPool = Annotated[
    redis.ConnectionPool, Depends(lambda: GlobalDependencies().redis_pool)
]
