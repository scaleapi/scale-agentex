import os
import sys
import traceback
from logging.config import fileConfig

# Add the project root directory to the Python path
# This will help Python find the agentex module
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
sys.path.insert(0, project_root)
print(f"Added {project_root} to Python path")

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add explicit error handling to catch import errors
try:
    print("Starting migration - importing modules")
    from src.adapters.orm import BaseORM
    from src.config.environment_variables import EnvironmentVariables
    from src.utils.database import adjust_db_url

    print("Successfully imported agentex modules")
except Exception as e:
    print("ERROR IMPORTING MODULES:", str(e))
    print("Traceback:")
    traceback.print_exc()
    sys.exit(1)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

try:
    print("Getting database URL")
    env_vars = EnvironmentVariables.refresh()
    database_url = env_vars.DATABASE_URL.replace("postgres://", "postgresql://")
    database_url = adjust_db_url(database_url)
    print("Connecting to database")
    config.set_main_option("sqlalchemy.url", database_url)
except Exception as e:
    print("ERROR CONFIGURING DATABASE:", str(e))
    print("Traceback:")
    traceback.print_exc()
    sys.exit(1)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = BaseORM.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    try:
        url = config.get_main_option("sqlalchemy.url")
        print("Connecting to database with URL:", url)
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )

        with context.begin_transaction():
            context.run_migrations()
    except Exception as e:
        print("ERROR IN OFFLINE MIGRATIONS:", str(e))
        print("Traceback:")
        traceback.print_exc()
        sys.exit(1)


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    try:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
    except Exception as e:
        print("ERROR IN ONLINE MIGRATIONS:", str(e))
        print("Traceback:")
        traceback.print_exc()
        sys.exit(1)


try:
    print("Starting migration execution")
    if context.is_offline_mode():
        print("Running in offline mode")
        run_migrations_offline()
    else:
        print("Running in online mode")
        run_migrations_online()
    print("Migration completed successfully")
except Exception as e:
    print("ERROR IN MIGRATION EXECUTION:", str(e))
    print("Traceback:")
    traceback.print_exc()
    sys.exit(1)
