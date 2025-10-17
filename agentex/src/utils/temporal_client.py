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


class DateTimeJSONEncoder(AdvancedJSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        return super().default(o)


class DateTimeJSONTypeConverter(JSONTypeConverter):
    def to_typed_value(
        self, hint: type, value: Any
    ) -> Any | None | _JSONTypeConverterUnhandled:
        if hint == datetime.datetime:
            return datetime.datetime.fromisoformat(value)
        return JSONTypeConverter.Unhandled


class DateTimePayloadConverter(CompositePayloadConverter):
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


custom_data_converter = dataclasses.replace(
    DataConverter.default,
    payload_converter_class=DateTimePayloadConverter,
)


async def get_temporal_client(temporal_address: str, metrics_url: str = None) -> Client:
    if not metrics_url:
        client = await Client.connect(
            target_host=temporal_address, data_converter=custom_data_converter
        )
    else:
        runtime = Runtime(
            telemetry=TelemetryConfig(metrics=OpenTelemetryConfig(url=metrics_url))
        )
        client = await Client.connect(
            target_host=temporal_address,
            data_converter=custom_data_converter,
            runtime=runtime,
        )
    return client
