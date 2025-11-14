import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..security import (
    ADMIN_USERNAME,
    create_access_token,
    is_password_set,
    load_credentials,
    set_admin_password,
    validate_reset_token,
    validate_setup_token,
    verify_admin_password,
)

logger = logging.getLogger(__name__)

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
def setup(
    payload: PasswordPayload,
    request: Request,
    setup_token: Optional[str] = Query(None, description="Setup token for first boot password configuration"),
    reset_token: Optional[str] = Query(None, description="Reset token for password reset"),
) -> dict:
    """
    Set up admin password. Requires either:
    - setup_token: For first boot (when no password is set)
    - reset_token: For password reset (when needs_reset=True)
    """
    # Get client IP for audit logging
    client_ip = request.client.host if request.client else "unknown"
    
    # Check if password is already set
    password_set = is_password_set()
    creds = load_credentials()
    needs_reset = creds.get("needs_reset", False) if creds else False
    
    # Determine which scenario we're in
    if password_set and not needs_reset:
        logger.warning(f"Password setup attempted but password already configured (IP: {client_ip})")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password already configured"
        )
    
    # Validate token based on scenario
    if needs_reset:
        # Password reset scenario - requires reset_token
        if not reset_token:
            logger.warning(f"Password reset attempted without reset_token (IP: {client_ip})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Reset token required for password reset"
            )
        if not validate_reset_token(reset_token):
            logger.warning(f"Invalid reset_token provided (IP: {client_ip})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid reset token"
            )
        logger.info(f"Password reset initiated (IP: {client_ip})")
    else:
        # First boot scenario - requires setup_token
        if not setup_token:
            logger.warning(f"First boot password setup attempted without setup_token (IP: {client_ip})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Setup token required for first boot password configuration"
            )
        if not validate_setup_token(setup_token):
            logger.warning(f"Invalid setup_token provided (IP: {client_ip})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid setup token"
            )
        logger.info(f"First boot password setup initiated (IP: {client_ip})")
    
    # Set the password
    try:
        set_admin_password(payload.password)
        logger.info(f"Admin password successfully configured (IP: {client_ip}, reset={needs_reset})")
        return _token_response(ADMIN_USERNAME)
    except ValueError as e:
        logger.warning(f"Password setup failed: {e} (IP: {client_ip})")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/token")
def login(payload: LoginPayload) -> dict:
    if not is_password_set():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin password not configured")
    if not verify_admin_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    return _token_response(ADMIN_USERNAME)
