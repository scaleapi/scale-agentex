from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class EnvVarKeys(str, Enum):
    ENVIRONMENT = "ENVIRONMENT"
    AUTH_PROVIDER_BASE_URL = "AUTH_PROVIDER_BASE_URL"
    AUTH_PROVIDER = "AUTH_PROVIDER"


class Environment(str, Enum):
    DEV = "development"
    STAGING = "staging"
    PROD = "production"


class Provider(str, Enum):
    sgp = "sgp"
    workos = "workos"


refreshed_environment_variables = None


class EnvironmentVariables(BaseModel):
    ENVIRONMENT: str = Environment.DEV
    AUTH_PROVIDER_BASE_URL: Optional[str] = None
    AUTH_PROVIDER: str = Provider.sgp

    @classmethod
    def refresh(cls) -> Optional[EnvironmentVariables]:
        global refreshed_environment_variables
        if refreshed_environment_variables is not None:
            return refreshed_environment_variables

        if os.environ.get(EnvVarKeys.ENVIRONMENT) == Environment.DEV:
            load_dotenv(dotenv_path=Path(PROJECT_ROOT / ".env"), override=True)

        environment_variables = EnvironmentVariables(
            ENVIRONMENT=os.environ.get(EnvVarKeys.ENVIRONMENT, Environment.DEV),
            AUTH_PROVIDER_BASE_URL=os.environ.get(EnvVarKeys.AUTH_PROVIDER_BASE_URL),
            AUTH_PROVIDER=os.environ.get(EnvVarKeys.AUTH_PROVIDER, Provider.sgp),
        )
        refreshed_environment_variables = environment_variables
        return refreshed_environment_variables
