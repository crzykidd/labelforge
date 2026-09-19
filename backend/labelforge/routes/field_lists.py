import logging

from fastapi import APIRouter, Depends, HTTPException

from labelforge.field_lists import store
from labelforge.models import FieldList, FieldListCreate, FieldListUpdate
from labelforge.routes.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


def _load_or_404(name: str) -> FieldList:
    fl = store.get_field_list(name)
    if fl is None:
        raise HTTPException(status_code=404, detail=f"Field list '{name}' not found")
    return fl


@router.get("/field-lists", response_model=list[FieldList])
async def list_field_lists() -> list[FieldList]:
    return store.list_field_lists()


@router.get("/field-lists/{name}", response_model=FieldList)
async def get_field_list(name: str) -> FieldList:
    return _load_or_404(name)


@router.post("/field-lists", response_model=FieldList, status_code=201)
async def create_field_list(data: FieldListCreate) -> FieldList:
    try:
        return store.create_field_list(data)
    except ValueError as exc:
        msg = str(exc)
        status = 409 if "already exists" in msg else 400
        raise HTTPException(status_code=status, detail=msg) from exc


@router.put("/field-lists/{name}", response_model=FieldList)
async def update_field_list(name: str, data: FieldListUpdate) -> FieldList:
    result = store.update_field_list(name, data)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Field list '{name}' not found")
    return result


@router.delete("/field-lists/{name}", status_code=204)
async def delete_field_list(name: str) -> None:
    if not store.delete_field_list(name):
        raise HTTPException(status_code=404, detail=f"Field list '{name}' not found")
