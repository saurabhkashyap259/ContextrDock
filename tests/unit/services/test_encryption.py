"""Tests for Fernet encryption utility."""

import pytest
from cryptography.fernet import InvalidToken

from src.services.encryption import encrypt_data, decrypt_data


def test_encrypt_data() -> None:
    """Test encrypting data."""
    plaintext = "my-secret-api-key"
    
    encrypted = encrypt_data(plaintext)
    
    assert isinstance(encrypted, str)
    assert len(encrypted) > 0
    assert encrypted != plaintext


def test_decrypt_data() -> None:
    """Test decrypting data."""
    plaintext = "my-secret-api-key"
    encrypted = encrypt_data(plaintext)
    
    decrypted = decrypt_data(encrypted)
    
    assert decrypted == plaintext


def test_encrypt_decrypt_roundtrip() -> None:
    """Test encrypt/decrypt roundtrip preserves data."""
    original = "slack-bot-token-xoxb-123456789"
    
    encrypted = encrypt_data(original)
    decrypted = decrypt_data(encrypted)
    
    assert decrypted == original


def test_encrypt_empty_string() -> None:
    """Test encrypting empty string."""
    encrypted = encrypt_data("")
    decrypted = decrypt_data(encrypted)
    
    assert decrypted == ""


def test_encrypt_unicode() -> None:
    """Test encrypting unicode characters."""
    plaintext = "API key with émojis 🔐🔑"
    
    encrypted = encrypt_data(plaintext)
    decrypted = decrypt_data(encrypted)
    
    assert decrypted == plaintext


def test_encrypt_json() -> None:
    """Test encrypting JSON-like strings."""
    plaintext = '{"access_token": "secret", "refresh_token": "also-secret"}'
    
    encrypted = encrypt_data(plaintext)
    decrypted = decrypt_data(encrypted)
    
    assert decrypted == plaintext


def test_decrypt_invalid_token() -> None:
    """Test decrypting invalid token raises error."""
    invalid_encrypted = "not-a-valid-encrypted-string"
    
    with pytest.raises(Exception):  # Will raise InvalidToken
        decrypt_data(invalid_encrypted)


def test_encrypt_long_string() -> None:
    """Test encrypting long strings."""
    plaintext = "x" * 10000  # 10KB string
    
    encrypted = encrypt_data(plaintext)
    decrypted = decrypt_data(encrypted)
    
    assert decrypted == plaintext
    assert len(encrypted) > len(plaintext)


def test_encrypt_deterministic() -> None:
    """Test that encryption is non-deterministic (different output each time)."""
    plaintext = "my-secret"
    
    encrypted1 = encrypt_data(plaintext)
    encrypted2 = encrypt_data(plaintext)
    
    # Different ciphertexts
    assert encrypted1 != encrypted2
    
    # But both decrypt to same plaintext
    assert decrypt_data(encrypted1) == plaintext
    assert decrypt_data(encrypted2) == plaintext


def test_encrypt_connector_credentials() -> None:
    """Test encrypting realistic connector credentials."""
    credentials = {
        "access_token": "test-token-1234567890-1234567890-abcdefghijklmnopqrstuvwx",
        "refresh_token": "test-refresh-token-1-abcdef",
        "expires_at": "2026-01-07T12:00:00Z",
    }
    import json
    plaintext = json.dumps(credentials)
    
    encrypted = encrypt_data(plaintext)
    decrypted = decrypt_data(encrypted)
    decrypted_dict = json.loads(decrypted)
    
    assert decrypted_dict == credentials
