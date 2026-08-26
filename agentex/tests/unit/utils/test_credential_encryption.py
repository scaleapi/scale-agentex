"""Unit tests for credential encryption.

The properties that matter are all about failing loudly. This module guards the
most sensitive thing agentex persists — a user's SGP API key — so every failure
mode must raise rather than degrade into storing or returning something usable.
"""

import pytest
from cryptography.fernet import Fernet
from src.utils import credential_encryption as ce


@pytest.fixture(autouse=True)
def _fresh_key(monkeypatch):
    """A distinct key per test, and a cleared cipher cache either side of it."""
    ce.reset_cache()
    monkeypatch.setenv(ce.ENV_KEY, Fernet.generate_key().decode())
    yield
    ce.reset_cache()


@pytest.mark.unit
class TestRoundTrip:
    def test_encrypt_then_decrypt_returns_the_original(self):
        secret = "ssk_is_deadbeefdeadbeefdeadbeefdeadbeef"
        assert ce.decrypt(ce.encrypt(secret)) == secret

    def test_ciphertext_does_not_contain_the_plaintext(self):
        secret = "ssk_is_deadbeefdeadbeefdeadbeefdeadbeef"
        assert secret not in ce.encrypt(secret)

    def test_same_plaintext_encrypts_differently_each_time(self):
        # Fernet includes an IV, so identical credentials don't produce identical
        # rows — otherwise the table would leak which users share a value.
        secret = "ssk_is_aaaa"
        assert ce.encrypt(secret) != ce.encrypt(secret)

    def test_unicode_survives(self):
        assert ce.decrypt(ce.encrypt("clé-café-✓")) == "clé-café-✓"


@pytest.mark.unit
class TestFailsClosed:
    def test_missing_key_raises_rather_than_storing_plaintext(self, monkeypatch):
        ce.reset_cache()
        monkeypatch.delenv(ce.ENV_KEY, raising=False)
        with pytest.raises(ce.CredentialEncryptionError, match="is unset"):
            ce.encrypt("secret")

    def test_blank_key_is_treated_as_missing(self, monkeypatch):
        ce.reset_cache()
        monkeypatch.setenv(ce.ENV_KEY, "   ")
        with pytest.raises(ce.CredentialEncryptionError, match="is unset"):
            ce.encrypt("secret")

    def test_malformed_key_raises(self, monkeypatch):
        ce.reset_cache()
        monkeypatch.setenv(ce.ENV_KEY, "not-a-valid-fernet-key")
        with pytest.raises(ce.CredentialEncryptionError, match="not a valid Fernet"):
            ce.encrypt("secret")

    def test_tampered_ciphertext_raises_not_returns_garbage(self):
        token = ce.encrypt("ssk_is_original")
        tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
        with pytest.raises(
            ce.CredentialEncryptionError, match="could not be decrypted"
        ):
            ce.decrypt(tampered)

    def test_ciphertext_from_a_different_key_raises(self, monkeypatch):
        token = ce.encrypt("ssk_is_original")
        # Simulates a rotated/replaced encryption key against existing rows: the
        # owner must be prompted to re-link, not silently treated as unlinked.
        ce.reset_cache()
        monkeypatch.setenv(ce.ENV_KEY, Fernet.generate_key().decode())
        with pytest.raises(ce.CredentialEncryptionError, match="different key"):
            ce.decrypt(token)

    @pytest.mark.parametrize("empty", ["", None])
    def test_empty_inputs_are_refused(self, empty):
        with pytest.raises(ce.CredentialEncryptionError):
            ce.encrypt(empty)
        with pytest.raises(ce.CredentialEncryptionError):
            ce.decrypt(empty)


@pytest.mark.unit
class TestIsConfigured:
    def test_true_with_a_valid_key(self):
        assert ce.is_configured() is True

    def test_false_without_a_key(self, monkeypatch):
        ce.reset_cache()
        monkeypatch.delenv(ce.ENV_KEY, raising=False)
        assert ce.is_configured() is False
