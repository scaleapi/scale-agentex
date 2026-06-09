import pytest
from src.utils.request_utils import decode_request_body, strip_sensitive_items
from starlette.datastructures import Headers, QueryParams


@pytest.mark.unit
def test_decode_request_body_strips_api_key_fields():
    decoded = decode_request_body(
        b"""
        {
            "name": "safe",
            "api_key": "secret-1",
            "apiKey": "secret-2",
            "nested": {
                "x-agent-api-key": "secret-3",
                "visible": "kept"
            }
        }
        """
    )

    assert decoded == {"name": "safe", "nested": {"visible": "kept"}}


@pytest.mark.unit
def test_decode_request_body_omits_non_json_bodies():
    decoded = decode_request_body(b"api_key=secret&name=safe")

    assert decoded == "[non-json request body omitted]"


@pytest.mark.unit
def test_strip_sensitive_items_handles_headers_and_query_params():
    headers = strip_sensitive_items(
        Headers(
            {
                "x-api-key": "secret-1",
                "Authorization": "Bearer secret-2",
                "x-request-id": "req-1",
            }
        )
    )
    query_params = strip_sensitive_items(
        QueryParams("apiKey=secret-3&token=secret-4&name=safe")
    )

    assert dict(headers) == {"x-request-id": "req-1"}
    assert dict(query_params) == {"name": "safe"}
