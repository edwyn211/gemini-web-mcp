"""Authentication service with encrypted credential storage."""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class AuthService:
    """
    Manages authentication state with optional encryption.
    
    Encryption uses Fernet (AES-128-CBC) with a key derived from:
    - AUTH_ENCRYPTION_KEY environment variable, or
    - Machine-specific salt + optional passphrase
    """

    # Anchored to the project root (src/services/ -> parents[2]) so paths do
    # not depend on the process working directory (/app inside Docker).
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    AUTH_STATE_PATH = _PROJECT_ROOT / "auth_state.json"
    ENCRYPTED_PATH = _PROJECT_ROOT / "auth_state.encrypted"
    SALT_PATH = _PROJECT_ROOT / ".auth_salt"

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize AuthService.
        
        Args:
            encryption_key: Optional encryption key. If not provided, 
                           uses AUTH_ENCRYPTION_KEY env var or generates one.
        """
        self._encryption_key = encryption_key or os.getenv("AUTH_ENCRYPTION_KEY")
        self._fernet: Optional[Fernet] = None

    def _get_or_create_salt(self) -> bytes:
        """Get or create a persistent salt for key derivation."""
        if self.SALT_PATH.exists():
            return self.SALT_PATH.read_bytes()
        
        salt = os.urandom(16)
        self.SALT_PATH.write_bytes(salt)
        # Restrict permissions
        os.chmod(self.SALT_PATH, 0o600)
        return salt

    def _derive_key(self, passphrase: str) -> bytes:
        """Derive encryption key from passphrase using PBKDF2."""
        salt = self._get_or_create_salt()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,  # OWASP recommended minimum
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        return key

    def _get_fernet(self) -> Fernet:
        """Get or create Fernet instance for encryption/decryption."""
        if self._fernet is None:
            if self._encryption_key:
                # Use provided key directly (must be valid Fernet key)
                try:
                    self._fernet = Fernet(self._encryption_key.encode())
                except Exception:
                    # If not valid Fernet key, derive from it as passphrase
                    key = self._derive_key(self._encryption_key)
                    self._fernet = Fernet(key)
            else:
                # Generate machine-specific key
                machine_id = self._get_machine_id()
                key = self._derive_key(machine_id)
                self._fernet = Fernet(key)
        return self._fernet

    def _get_machine_id(self) -> str:
        """Get a machine-specific identifier for key derivation."""
        # Try various sources of machine identity
        sources = [
            "/etc/machine-id",
            "/var/lib/dbus/machine-id",
        ]
        
        for source in sources:
            try:
                return Path(source).read_text().strip()
            except Exception:
                continue
        
        # Fallback: use hostname + username
        import socket
        import getpass
        return f"{socket.gethostname()}:{getpass.getuser()}"

    def encrypt_auth_state(self, auth_data: Optional[dict] = None) -> bool:
        """
        Encrypt auth_state.json to auth_state.encrypted.
        
        Args:
            auth_data: Optional auth data. If not provided, reads from AUTH_STATE_PATH.
            
        Returns:
            True if successful.
        """
        try:
            if auth_data is None:
                if not self.AUTH_STATE_PATH.exists():
                    logger.warning("No auth_state.json to encrypt")
                    return False
                auth_data = json.loads(self.AUTH_STATE_PATH.read_text())
            
            fernet = self._get_fernet()
            encrypted = fernet.encrypt(json.dumps(auth_data).encode())
            
            self.ENCRYPTED_PATH.write_bytes(encrypted)
            os.chmod(self.ENCRYPTED_PATH, 0o600)
            
            logger.info(f"Auth state encrypted to {self.ENCRYPTED_PATH}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to encrypt auth state: {e}")
            return False

    def decrypt_auth_state(self) -> Optional[dict]:
        """
        Decrypt auth_state.encrypted.
        
        Returns:
            Decrypted auth data, or None if decryption fails.
        """
        try:
            if not self.ENCRYPTED_PATH.exists():
                # Fall back to unencrypted file
                if self.AUTH_STATE_PATH.exists():
                    logger.warning("Using unencrypted auth_state.json")
                    return json.loads(self.AUTH_STATE_PATH.read_text())
                return None
            
            fernet = self._get_fernet()
            encrypted = self.ENCRYPTED_PATH.read_bytes()
            decrypted = fernet.decrypt(encrypted)
            
            return json.loads(decrypted.decode())
            
        except Exception as e:
            logger.error(f"Failed to decrypt auth state: {e}")
            # Try unencrypted as fallback
            if self.AUTH_STATE_PATH.exists():
                logger.warning("Falling back to unencrypted auth_state.json")
                return json.loads(self.AUTH_STATE_PATH.read_text())
            return None

    def get_storage_state_path(self) -> Optional[Path]:
        """
        Get the path to use for Playwright storage state.
        
        If encrypted file exists, decrypts to temp file and returns that path.
        Otherwise returns AUTH_STATE_PATH if it exists.
        """
        if self.ENCRYPTED_PATH.exists():
            auth_data = self.decrypt_auth_state()
            if auth_data:
                # Write to temp location for Playwright
                temp_path = Path("/tmp/gemini_auth_state.json")
                temp_path.write_text(json.dumps(auth_data))
                os.chmod(temp_path, 0o600)
                return temp_path
        
        if self.AUTH_STATE_PATH.exists():
            return self.AUTH_STATE_PATH
        
        return None

    def rotate_encryption_key(self, new_key: str) -> bool:
        """
        Rotate encryption key by re-encrypting with new key.
        
        Args:
            new_key: New encryption key or passphrase.
            
        Returns:
            True if successful.
        """
        try:
            # Decrypt with old key
            auth_data = self.decrypt_auth_state()
            if auth_data is None:
                return False
            
            # Update key
            self._encryption_key = new_key
            self._fernet = None  # Reset to use new key
            
            # Re-encrypt
            return self.encrypt_auth_state(auth_data)
            
        except Exception as e:
            logger.error(f"Failed to rotate encryption key: {e}")
            return False

    def secure_delete_plaintext(self) -> bool:
        """
        Securely delete unencrypted auth_state.json after encryption.
        
        Returns:
            True if file was deleted or didn't exist.
        """
        try:
            if not self.AUTH_STATE_PATH.exists():
                return True
            
            # Overwrite with random data before deleting
            size = self.AUTH_STATE_PATH.stat().st_size
            self.AUTH_STATE_PATH.write_bytes(os.urandom(size))
            self.AUTH_STATE_PATH.unlink()
            
            logger.info("Securely deleted plaintext auth_state.json")
            return True
            
        except Exception as e:
            logger.error(f"Failed to securely delete auth state: {e}")
            return False
