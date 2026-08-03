from typing import Optional
from fastapi import Header, HTTPException, Query, status
from app.config import settings


def verify_token(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None)
):
    """
    Validates Bearer token or query string token against settings.API_TOKEN if set.
    """
    if not settings.API_TOKEN:
        return True

    provided_token = None
    if authorization and authorization.startswith("Bearer "):
        provided_token = authorization.split("Bearer ", 1)[1].strip()
    elif token:
        provided_token = token.strip()

    if provided_token != settings.API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
