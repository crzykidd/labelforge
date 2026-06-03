from fastapi import APIRouter

from labelforge.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    # auth_required lets the SPA decide whether to show the token gate.
    return {"status": "ok", "auth_required": not settings.disable_auth}
