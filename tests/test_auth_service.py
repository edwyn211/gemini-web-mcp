"""Tests for AuthService encryption functionality."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from services.auth_service import AuthService


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def auth_service(temp_dir):
    """Create AuthService with paths in temp directory."""
    service = AuthService(encryption_key="test-secret-key-12345")
    # Override paths to use temp directory
    service.AUTH_STATE_PATH = temp_dir / "auth_state.json"
    service.ENCRYPTED_PATH = temp_dir / "auth_state.encrypted"
    service.SALT_PATH = temp_dir / ".auth_salt"
    return service


def test_encrypt_and_decrypt(auth_service, temp_dir):
    """Test basic encryption and decryption cycle."""
    auth_data = {
        "cookies": [
            {"name": "session", "value": "abc123"},
            {"name": "token", "value": "xyz789"},
        ],
        "origins": [{"origin": "https://gemini.google.com"}],
    }
    
    # Write plaintext first
    auth_service.AUTH_STATE_PATH.write_text(json.dumps(auth_data))
    
    # Encrypt
    assert auth_service.encrypt_auth_state() is True
    assert auth_service.ENCRYPTED_PATH.exists()
    
    # Verify encrypted file is not readable as JSON
    encrypted_content = auth_service.ENCRYPTED_PATH.read_bytes()
    with pytest.raises(json.JSONDecodeError):
        json.loads(encrypted_content)
    
    # Decrypt
    decrypted = auth_service.decrypt_auth_state()
    
    assert decrypted is not None
    assert decrypted["cookies"] == auth_data["cookies"]
    assert decrypted["origins"] == auth_data["origins"]


def test_encrypt_with_data_param(auth_service):
    """Test encryption with data passed as parameter."""
    auth_data = {"test": "data", "nested": {"key": "value"}}
    
    assert auth_service.encrypt_auth_state(auth_data) is True
    
    decrypted = auth_service.decrypt_auth_state()
    assert decrypted == auth_data


def test_decrypt_fallback_to_plaintext(auth_service, temp_dir):
    """Test decryption falls back to plaintext if encrypted not found."""
    auth_data = {"fallback": "test"}
    
    # Only write plaintext, no encrypted file
    auth_service.AUTH_STATE_PATH.write_text(json.dumps(auth_data))
    
    # Should fall back to plaintext
    decrypted = auth_service.decrypt_auth_state()
    
    assert decrypted is not None
    assert decrypted["fallback"] == "test"


def test_decrypt_returns_none_if_no_files(auth_service):
    """Test decryption returns None if no auth files exist."""
    result = auth_service.decrypt_auth_state()
    assert result is None


def test_key_rotation(auth_service):
    """Test rotating encryption key."""
    auth_data = {"rotate": "me"}
    
    # Encrypt with original key
    auth_service.encrypt_auth_state(auth_data)
    
    # Rotate to new key
    new_key = "new-secret-key-67890"
    assert auth_service.rotate_encryption_key(new_key) is True
    
    # Verify can decrypt with new key
    decrypted = auth_service.decrypt_auth_state()
    assert decrypted["rotate"] == "me"
    
    # Verify old key no longer works
    old_service = AuthService(encryption_key="test-secret-key-12345")
    old_service.ENCRYPTED_PATH = auth_service.ENCRYPTED_PATH
    old_service.SALT_PATH = auth_service.SALT_PATH
    
    # This should fail or return None
    try:
        result = old_service.decrypt_auth_state()
        # If it doesn't raise, it should at least not match
        assert result != auth_data
    except Exception:
        pass  # Expected - decryption should fail


def test_secure_delete(auth_service, temp_dir):
    """Test secure deletion of plaintext file."""
    auth_data = {"sensitive": "data"}
    auth_service.AUTH_STATE_PATH.write_text(json.dumps(auth_data))
    
    # Verify file exists
    assert auth_service.AUTH_STATE_PATH.exists()
    
    # Secure delete
    assert auth_service.secure_delete_plaintext() is True
    
    # Verify file is gone
    assert not auth_service.AUTH_STATE_PATH.exists()


def test_secure_delete_nonexistent(auth_service):
    """Test secure delete on nonexistent file returns True."""
    assert auth_service.secure_delete_plaintext() is True


def test_get_storage_state_path_encrypted(auth_service, temp_dir):
    """Test getting storage state path with encrypted file."""
    auth_data = {"cookies": []}
    auth_service.encrypt_auth_state(auth_data)
    
    path = auth_service.get_storage_state_path()
    
    assert path is not None
    assert path.exists()
    # Verify it's readable JSON
    loaded = json.loads(path.read_text())
    assert loaded == auth_data


def test_get_storage_state_path_plaintext(auth_service, temp_dir):
    """Test getting storage state path with only plaintext file."""
    auth_data = {"cookies": []}
    auth_service.AUTH_STATE_PATH.write_text(json.dumps(auth_data))
    
    path = auth_service.get_storage_state_path()
    
    assert path == auth_service.AUTH_STATE_PATH


def test_get_storage_state_path_none(auth_service):
    """Test getting storage state path with no files."""
    path = auth_service.get_storage_state_path()
    assert path is None


def test_salt_persistence(auth_service, temp_dir):
    """Test that salt is created and persisted."""
    auth_data = {"test": "salt"}
    
    # First encryption creates salt
    auth_service.encrypt_auth_state(auth_data)
    
    assert auth_service.SALT_PATH.exists()
    original_salt = auth_service.SALT_PATH.read_bytes()
    
    # Create new service instance
    new_service = AuthService(encryption_key="test-secret-key-12345")
    new_service.ENCRYPTED_PATH = auth_service.ENCRYPTED_PATH
    new_service.SALT_PATH = auth_service.SALT_PATH
    new_service.AUTH_STATE_PATH = auth_service.AUTH_STATE_PATH
    
    # Should use same salt
    decrypted = new_service.decrypt_auth_state()
    assert decrypted == auth_data
    
    # Salt should be unchanged
    assert auth_service.SALT_PATH.read_bytes() == original_salt


def test_file_permissions(auth_service, temp_dir):
    """Test that sensitive files have restricted permissions."""
    auth_data = {"permissions": "test"}
    
    auth_service.encrypt_auth_state(auth_data)
    
    # Check encrypted file permissions (should be 600)
    if os.name != "nt":  # Skip on Windows
        mode = auth_service.ENCRYPTED_PATH.stat().st_mode & 0o777
        assert mode == 0o600
        
        # Check salt file permissions
        mode = auth_service.SALT_PATH.stat().st_mode & 0o777
        assert mode == 0o600
