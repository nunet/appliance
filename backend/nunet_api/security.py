# nunet_api/app/security.py
import os
from fastapi import Header, HTTPException

API_TOKEN = os.getenv("NUNET_API_TOKEN")

def require_token(authorization: str = Header(None)):
    if not API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
