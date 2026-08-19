"""Slack route ack helper: an ack-only result (empty dict) must be a TRULY EMPTY 200
body — Slack renders a bare ``{}`` JSON body as a stray message, so "show nothing" has
to send no body, not ``{}``. A non-empty result is sent as JSON."""

import json

import pytest
from fastapi.responses import JSONResponse
from src.api.routes.slack import _slack_ack


@pytest.mark.unit
class TestSlackAck:
    def test_empty_result_is_empty_200_body(self):
        resp = _slack_ack({})
        assert resp.status_code == 200
        assert resp.body == b""  # not b"{}" — nothing for Slack to render

    def test_non_empty_result_is_json(self):
        payload = {"response_type": "ephemeral", "text": "hi"}
        resp = _slack_ack(payload)
        assert isinstance(resp, JSONResponse)
        assert json.loads(resp.body) == payload
