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

ADMIN_USERNAME = "admin"
CREDENTIALS_ENV_KEY = "e4c7f92a1d8b3f6e0a9d7c4b2f1e8a6c5d0f3b9a7c2d6e1f0a8c4d7b3e9f2a6d"
JWT_SECRET_ENV_KEY = "f9a2c3e7d54b8a1f0c69f4e2d8b1a7c6e0d4f8b5c2a7e9f3b6d1c4e8f0a2b7d9"
JWT_EXPIRE_MINUTES_ENV_KEY = "14"
DEFAULT_EXPIRY_MINUTES = 30
ALGORITHM = "HS256"

DEFAULT_SETUP_TOKEN_EXPIRY_MINUTES = 30
SETUP_TOKEN_PATH_ENV_KEY = "NUNET_SETUP_TOKEN_PATH"
SETUP_TOKEN_EXPIRY_MINUTES_ENV_KEY = "NUNET_SETUP_TOKEN_EXPIRY_MINUTES"

_bearer_scheme = HTTPBearer(auto_error=False)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _credentials_path() -> Path:
    env_path = os.getenv(CREDENTIALS_ENV_KEY)
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (_repo_root() / "deploy" / "admin_credentials.json").resolve()


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




def _setup_token_path() -> Path:
    env_path = os.getenv(SETUP_TOKEN_PATH_ENV_KEY)
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (Path.home() / "nunet" / "appliance" / "setup_token.json").resolve()


def _setup_token_expiry_minutes() -> int:
    value = os.getenv(SETUP_TOKEN_EXPIRY_MINUTES_ENV_KEY)
    if value:
        try:
            minutes = int(value)
            if minutes > 0:
                return minutes
        except ValueError:
            pass
    return DEFAULT_SETUP_TOKEN_EXPIRY_MINUTES


def _load_setup_token() -> Optional[Dict[str, Any]]:
    path = _setup_token_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
            if isinstance(data, dict):
                return data
    except Exception:
        return None
    return None


def _write_setup_token(token: str, expires_at: datetime, created_at: datetime) -> None:
    payload = {
        "token": token,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    path = _setup_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    try:
        os.chmod(path, 0o600)
    except PermissionError:
        pass
    except NotImplementedError:
        pass


def clear_setup_token() -> None:
    path = _setup_token_path()
    if path.exists():
        path.unlink()


def get_or_create_setup_token() -> Tuple[str, datetime]:
    now = _now_utc()
    data = _load_setup_token()
    if data and "token" in data and "expires_at" in data:
        try:
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except Exception:
            expires_at = None
        if expires_at and expires_at > now:
            return data["token"], expires_at

    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(minutes=_setup_token_expiry_minutes())
    _write_setup_token(token, expires_at, now)
    return token, expires_at


def validate_setup_token(token: str) -> bool:
    if not token:
        return False
    data = _load_setup_token()
    if not data:
        return False
    stored_token = data.get("token")
    expires_at_raw = data.get("expires_at")
    if not stored_token or not expires_at_raw:
        return False
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    if expires_at <= _now_utc():
        return False
    return secrets.compare_digest(stored_token, token)


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

    clear_setup_token()

    return payload


def clear_credentials() -> None:
    path = _credentials_path()
    if path.exists():
        path.unlink()
    clear_setup_token()


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

