
from fastapi import Header, HTTPException

from labelforge.config import settings


async def require_auth(authorization: str | None = Header(None)) -> None:
    """FastAPI dependency: enforce Bearer token on all protected routes."""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must use Bearer scheme")
    token = authorization[7:]
    if token != settings.api_token:
        raise HTTPException(status_code=403, detail="Invalid API token")
