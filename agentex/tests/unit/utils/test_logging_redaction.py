"""Tests for the log redaction safety net in src.utils.logging.

Even if a future code path interpolates an object carrying a credential (e.g. a
principal context dict with an api_key) into a log message, the value must be
masked before the record is emitted.
"""

import logging

import pytest
from src.utils.logging import make_logger, redact_sensitive_text

# Fake credential shaped like a real key; not a live secret.
FAKE_KEY = "ssk_is_deadbeefdeadbeefdeadbeef00"  # noqa: S105

pytestmark = pytest.mark.unit


def test_redacts_api_key_in_principal_dict_repr():
    # The exact shape that leaked: a principal context rendered via %s/f-string.
    principal_repr = (
        "{'api_key': '" + FAKE_KEY + "', 'user_id': 'user-1', "
        "'service_account_id': None, 'account_id': 'acct-1', 'metadata': {}}"
    )
    out = redact_sensitive_text(principal_repr)

    assert FAKE_KEY not in out
    assert "[REDACTED]" in out
    # Non-sensitive identifiers are preserved for debuggability.
    assert "user-1" in out
    assert "acct-1" in out


@pytest.mark.parametrize(
    "text",
    [
        "api_key='" + FAKE_KEY + "'",  # pydantic / kwargs repr
        '"api_key": "' + FAKE_KEY + '"',  # json
        "api_key=" + FAKE_KEY,  # unquoted
        "apiKey: " + FAKE_KEY,  # camelCase
        "token: " + FAKE_KEY,
        "secret=" + FAKE_KEY,
        "authorization: " + FAKE_KEY,
        "authorization: Bearer " + FAKE_KEY,  # scheme-prefixed header
        "Authorization=Bearer " + FAKE_KEY,
        "cookie='" + FAKE_KEY + "'",
    ],
)
def test_redacts_common_renderings(text):
    assert FAKE_KEY not in redact_sensitive_text(text)


def test_leaves_non_sensitive_text_untouched():
    text = (
        "Granting create permission on agent:abc for user_id=user-1 account_id=acct-1"
    )
    assert redact_sensitive_text(text) == text


def test_unquoted_value_does_not_over_redact_rest_of_line():
    # Only the single token after the key is masked, not the trailing words.
    out = redact_sensitive_text("token: " + FAKE_KEY + " while processing request")
    assert FAKE_KEY not in out
    assert "while processing request" in out


def test_make_logger_redacts_secret_end_to_end(caplog):
    logger = make_logger("test_logging_redaction_e2e")
    principal = {"api_key": FAKE_KEY, "user_id": "user-1", "account_id": "acct-1"}

    with caplog.at_level(logging.INFO):
        logger.info("Checking read permission for principal %s", principal)

    assert FAKE_KEY not in caplog.text
    # The log line still made it through, with safe identifiers intact.
    assert "user-1" in caplog.text
