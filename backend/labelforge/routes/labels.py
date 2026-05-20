from fastapi import APIRouter, Depends, HTTPException

from labelforge.catalog.loader import get_catalog, get_label
from labelforge.models import LabelEntry
from labelforge.routes.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/labels", response_model=list[LabelEntry])
async def list_labels() -> list[LabelEntry]:
    return list(get_catalog().values())


@router.get("/labels/{label_id}", response_model=LabelEntry)
async def get_label_by_id(label_id: str) -> LabelEntry:
    entry = get_label(label_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown label media: {label_id}")
    return entry
