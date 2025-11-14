import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from modules.path_constants import ADMIN_CREDENTIALS_PATH

ADMIN_USERNAME = "admin"
CREDENTIALS_ENV_KEY = "e4c7f92a1d8b3f6e0a9d7c4b2f1e8a6c5d0f3b9a7c2d6e1f0a8c4d7b3e9f2a6d"
JWT_SECRET_ENV_KEY = "f9a2c3e7d54b8a1f0c69f4e2d8b1a7c6e0d4f8b5c2a7e9f3b6d1c4e8f0a2b7d9"
JWT_EXPIRE_MINUTES_ENV_KEY = "14"
DEFAULT_EXPIRY_MINUTES = 30
ALGORITHM = "HS256"

_bearer_scheme = HTTPBearer(auto_error=False)


def _credentials_path() -> Path:
    env_path = os.getenv(CREDENTIALS_ENV_KEY)
    if env_path:
        return Path(env_path).expanduser().resolve()
    return ADMIN_CREDENTIALS_PATH.resolve()


def load_credentials() -> Optional[Dict[str, Any]]:
    path = _credentials_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
            if not isinstance(data, dict):
                return None
            return data
    except Exception:
        return None


def is_password_set() -> bool:
    creds = load_credentials()
    if not creds:
        return False
    return bool(creds.get("password_hash")) and not creds.get("needs_reset", False)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def set_admin_password(password: str, username: str = ADMIN_USERNAME) -> Dict[str, Any]:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    now = _now_utc().isoformat()
    payload = {
        "username": username,
        "password_hash": _hash_password(password),
        "created_at": now,
        "updated_at": now,
        "needs_reset": False,
    }

    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    try:
        os.chmod(path, 0o600)
    except PermissionError:
        pass
    except NotImplementedError:
        pass

    # Delete both setup and reset tokens when password is set
    clear_setup_token()
    clear_reset_token()

    return payload


def clear_credentials() -> None:
    path = _credentials_path()
    if path.exists():
        path.unlink()


def verify_admin_password(password: str) -> bool:
    creds = load_credentials()
    if not creds or "password_hash" not in creds:
        return False
    stored_hash = creds["password_hash"].encode("utf-8")
    return bcrypt.checkpw(password.encode("utf-8"), stored_hash)


def _jwt_secret() -> str:
    env_secret = os.getenv(JWT_SECRET_ENV_KEY)
    if env_secret:
        return env_secret
    creds = load_credentials()
    if not creds or "password_hash" not in creds:
        return "nunet-appliance-default-secret"
    digest = hashlib.sha256(creds["password_hash"].encode("utf-8")).hexdigest()
    return digest


def _token_expiry_minutes() -> int:
    value = os.getenv(JWT_EXPIRE_MINUTES_ENV_KEY)
    if value:
        try:
            minutes = int(value)
            if minutes > 0:
                return minutes
        except ValueError:
            pass
    return DEFAULT_EXPIRY_MINUTES


def create_access_token(subject: str = ADMIN_USERNAME, *, expires_minutes: Optional[int] = None) -> Tuple[str, datetime]:
    expire_minutes = expires_minutes if expires_minutes and expires_minutes > 0 else _token_expiry_minutes()
    now = _now_utc()
    expire = now + timedelta(minutes=expire_minutes)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)
    return token, expire


def validate_token(token: str) -> bool:
    try:
        jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
        return True
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme)) -> str:
    if not is_password_set():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin password not configured")
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None
    return payload.get("sub", ADMIN_USERNAME)


def credentials_path() -> Path:
    return _credentials_path()


# Setup token management (for first boot password setup)
def _setup_token_path() -> Path:
    """Return the path to the setup token file."""
    return Path.home() / ".secrets" / "setup_token"


def get_setup_token() -> Optional[str]:
    """Get the setup token if it exists."""
    token_file = _setup_token_path()
    if not token_file.exists():
        return None
    try:
        with token_file.open("r", encoding="utf-8") as fp:
            token = fp.read().strip()
            return token if token else None
    except Exception:
        return None


def validate_setup_token(token: str) -> bool:
    """Validate the provided setup token against the stored token."""
    if not token:
        return False
    stored_token = get_setup_token()
    if not stored_token:
        return False
    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(token.strip(), stored_token.strip())


def ensure_setup_token() -> str:
    """
    Ensure setup token exists, generate if not.
    Returns the token (existing or newly generated).
    """
    token_file = _setup_token_path()
    secrets_dir = token_file.parent
    
    # Ensure secrets directory exists
    secrets_dir.mkdir(parents=True, exist_ok=True)
    try:
        secrets_dir.chmod(0o700)
    except Exception:
        pass
    
    # Check if token already exists
    existing_token = get_setup_token()
    if existing_token:
        return existing_token
    
    # Generate new token (12 bytes = ~16 URL-safe chars)
    token = secrets.token_urlsafe(12)
    try:
        with token_file.open("w", encoding="utf-8") as fp:
            fp.write(token)
        token_file.chmod(0o600)
    except Exception:
        # If we can't write, return empty string - caller should handle
        return ""
    
    return token


def clear_setup_token() -> None:
    """Delete setup token after successful password setup."""
    token_file = _setup_token_path()
    try:
        if token_file.exists():
            token_file.unlink()
    except Exception:
        pass  # Non-critical if we can't delete the token


# Reset token management (for password reset flow)
def _reset_token_path() -> Path:
    """Return the path to the reset token file."""
    return Path.home() / ".secrets" / "reset_token"


def get_reset_token() -> Optional[str]:
    """Get the reset token if it exists."""
    token_file = _reset_token_path()
    if not token_file.exists():
        return None
    try:
        with token_file.open("r", encoding="utf-8") as fp:
            token = fp.read().strip()
            return token if token else None
    except Exception:
        return None


def validate_reset_token(token: str) -> bool:
    """Validate the provided reset token against the stored token."""
    if not token:
        return False
    stored_token = get_reset_token()
    if not stored_token:
        return False
    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(token.strip(), stored_token.strip())


def clear_reset_token() -> None:
    """Delete reset token after successful password setup."""
    token_file = _reset_token_path()
    try:
        if token_file.exists():
            token_file.unlink()
    except Exception:
        pass  # Non-critical if we can't delete the token

