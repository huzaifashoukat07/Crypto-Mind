from fastapi import Header, HTTPException, status

from .config import settings


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency guarding every REST endpoint except /api/health.
    A no-op if API_AUTH_TOKEN isn't set on the server (local-only use)."""
    if not settings.api_auth_token:
        return
    if authorization != f"Bearer {settings.api_auth_token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token")


def check_ws_token(token: str | None) -> bool:
    """Same check for the WebSocket endpoint, which can't send custom headers
    from a browser -- the token is passed as a query param instead."""
    if not settings.api_auth_token:
        return True
    return token == settings.api_auth_token
