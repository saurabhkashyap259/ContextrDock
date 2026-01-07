"""Encryption utility using Fernet for securing connector credentials."""

from cryptography.fernet import Fernet

from src.config import settings


# Initialize Fernet cipher with key from settings
_cipher = Fernet(settings.fernet_key.encode())


def encrypt_data(plaintext: str) -> str:
    """
    Encrypt plaintext string using Fernet symmetric encryption.
    
    Args:
        plaintext: String to encrypt (e.g., API key, access token)
        
    Returns:
        Base64-encoded encrypted string
        
    Example:
        >>> encrypted = encrypt_data("my-api-key-123")
        >>> print(encrypted)
        gAAAAABf...encrypted-data...
    """
    plaintext_bytes = plaintext.encode("utf-8")
    encrypted_bytes = _cipher.encrypt(plaintext_bytes)
    return encrypted_bytes.decode("utf-8")


def decrypt_data(encrypted: str) -> str:
    """
    Decrypt Fernet-encrypted string.
    
    Args:
        encrypted: Base64-encoded encrypted string from encrypt_data()
        
    Returns:
        Original plaintext string
        
    Raises:
        cryptography.fernet.InvalidToken: If encrypted string is invalid or corrupted
        
    Example:
        >>> plaintext = decrypt_data(encrypted_string)
        >>> print(plaintext)
        my-api-key-123
    """
    encrypted_bytes = encrypted.encode("utf-8")
    decrypted_bytes = _cipher.decrypt(encrypted_bytes)
    return decrypted_bytes.decode("utf-8")
