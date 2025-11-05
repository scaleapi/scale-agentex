"""
Temporal client factory for creating and configuring Temporal clients.
"""

import dataclasses
import datetime
from typing import Any

from temporalio.client import Client
from temporalio.converter import (
    AdvancedJSONEncoder,
    CompositePayloadConverter,
    DataConverter,
    DefaultPayloadConverter,
    JSONPlainPayloadConverter,
    JSONTypeConverter,
    _JSONTypeConverterUnhandled,
)
from temporalio.runtime import OpenTelemetryConfig, Runtime, TelemetryConfig

from src.adapters.temporal.exceptions import TemporalConnectionError
from src.config.environment_variables import EnvironmentVariables
from src.utils.logging import make_logger

logger = make_logger(__name__)


class DateTimeJSONEncoder(AdvancedJSONEncoder):
    """Custom JSON encoder that handles datetime objects."""

    def default(self, o: Any) -> Any:
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        return super().default(o)


class DateTimeJSONTypeConverter(JSONTypeConverter):
    """Custom JSON type converter for datetime objects."""

    def to_typed_value(
        self, hint: type, value: Any
    ) -> Any | None | _JSONTypeConverterUnhandled:
        if hint == datetime.datetime:
            return datetime.datetime.fromisoformat(value)
        return JSONTypeConverter.Unhandled


class DateTimePayloadConverter(CompositePayloadConverter):
    """Custom payload converter that handles datetime serialization."""

    def __init__(self) -> None:
        json_converter = JSONPlainPayloadConverter(
            encoder=DateTimeJSONEncoder,
            custom_type_converters=[DateTimeJSONTypeConverter()],
        )
        super().__init__(
            *[
                c if not isinstance(c, JSONPlainPayloadConverter) else json_converter
                for c in DefaultPayloadConverter.default_encoding_payload_converters
            ]
        )


# Custom data converter with datetime support
custom_data_converter = dataclasses.replace(
    DataConverter.default,
    payload_converter_class=DateTimePayloadConverter,
)


class TemporalClientFactory:
    """
    Factory class for creating and configuring Temporal clients.
    Provides a clean interface for client creation with proper error handling.
    """

    @staticmethod
    async def create_client(
        temporal_address: str,
        temporal_namespace: str | None = None,
        metrics_url: str | None = None,
        data_converter: DataConverter | None = None,
    ) -> Client:
        """
        Create a Temporal client with the specified configuration.

        Args:
            temporal_address: The Temporal server address
            temporal_namespace: Optional namespace to connect to
            metrics_url: Optional OpenTelemetry metrics endpoint
            data_converter: Optional custom data converter

        Returns:
            Configured Temporal client

        Raises:
            TemporalConnectionError: If client creation fails
        """
        if not temporal_address or temporal_address in [
            "false",
            "False",
            "null",
            "None",
            "",
            "undefined",
        ]:
            raise TemporalConnectionError(
                "Temporal address is not configured or is invalid"
            )

        try:
            # Use custom data converter if not provided
            if data_converter is None:
                data_converter = custom_data_converter

            # Build connection options
            connect_options = {
                "target_host": temporal_address,
                "data_converter": data_converter,
            }

            if temporal_namespace:
                connect_options["namespace"] = temporal_namespace

            # Add telemetry if metrics URL is provided
            if metrics_url:
                logger.info(
                    f"Configuring Temporal client with metrics URL: {metrics_url}"
                )
                runtime = Runtime(
                    telemetry=TelemetryConfig(
                        metrics=OpenTelemetryConfig(url=metrics_url)
                    )
                )
                connect_options["runtime"] = runtime

            # Create the client
            client = await Client.connect(**connect_options)
            logger.info(
                f"Successfully created Temporal client for address: {temporal_address}"
            )
            return client

        except Exception as e:
            logger.error(f"Failed to create Temporal client: {e}")
            raise TemporalConnectionError(
                message=f"Failed to connect to Temporal at {temporal_address}",
                detail=str(e),
            ) from e

    @staticmethod
    async def create_client_from_env(
        environment_variables: EnvironmentVariables | None = None,
        metrics_url: str | None = None,
    ) -> Client:
        """
        Create a Temporal client using environment variables.

        Args:
            environment_variables: Environment variables instance (will refresh if None)
            metrics_url: Optional OpenTelemetry metrics endpoint

        Returns:
            Configured Temporal client

        Raises:
            TemporalConnectionError: If client creation fails
        """
        if environment_variables is None:
            environment_variables = EnvironmentVariables.refresh()

        return await TemporalClientFactory.create_client(
            temporal_address=environment_variables.TEMPORAL_ADDRESS,
            temporal_namespace=environment_variables.TEMPORAL_NAMESPACE,
            metrics_url=metrics_url,
        )

    @staticmethod
    def is_temporal_configured(
        environment_variables: EnvironmentVariables | None = None,
    ) -> bool:
        """
        Check if Temporal is properly configured in environment variables.

        Args:
            environment_variables: Environment variables instance (will refresh if None)

        Returns:
            True if Temporal is configured, False otherwise
        """
        if environment_variables is None:
            environment_variables = EnvironmentVariables.refresh()

        temporal_address = environment_variables.TEMPORAL_ADDRESS
        return temporal_address not in [
            "false",
            "False",
            "null",
            "None",
            "",
            "undefined",
            False,
            None,
        ]
