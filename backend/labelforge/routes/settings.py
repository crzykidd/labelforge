from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from labelforge import settings_store
from labelforge.routes.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    return settings_store.get_all()


@router.put("/settings")
async def update_settings(body: dict[str, Any]) -> dict[str, Any]:
    # Validate all keys first (all-or-nothing)
    for key, value in body.items():
        try:
            settings_store.validate(key, value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Write all
    for key, value in body.items():
        settings_store.set(key, value)
    return settings_store.get_all()
