from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..security import (
    ADMIN_USERNAME,
    create_access_token,
    is_password_set,
    load_credentials,
    set_admin_password,
    verify_admin_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class PasswordPayload(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)


class LoginPayload(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


def _token_response(username: str) -> dict:
    token, expires_at = create_access_token(username)
    seconds = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": max(seconds, 0),
        "username": username,
    }


@router.get("/status")
def get_status() -> dict:
    creds = load_credentials()
    return {
        "password_set": is_password_set(),
        "username": (creds or {}).get("username", ADMIN_USERNAME),
    }


@router.post("/setup")
def setup(payload: PasswordPayload) -> dict:
    if is_password_set():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password already configured")

    set_admin_password(payload.password)
    return _token_response(ADMIN_USERNAME)


@router.post("/token")
def login(payload: LoginPayload) -> dict:
    if not is_password_set():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin password not configured")
    if not verify_admin_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    return _token_response(ADMIN_USERNAME)
