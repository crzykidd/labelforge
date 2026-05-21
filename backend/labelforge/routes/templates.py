import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from labelforge.catalog.loader import get_label
from labelforge.models import Template, TemplateCreate, TemplateUpdate
from labelforge.routes.auth import require_auth
from labelforge.templates import store
from labelforge.templates.fields import detect_fields, merge_schema

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


def _load_or_404(name: str) -> Template:
    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return tmpl


@router.get("/templates", response_model=list[Template])
async def list_templates() -> list[Template]:
    return store.list_templates()


@router.get("/templates/{name}", response_model=Template)
async def get_template(name: str) -> Template:
    return _load_or_404(name)


@router.post("/templates", response_model=Template, status_code=201)
async def create_template(data: TemplateCreate) -> Template:
    if get_label(data.label_media) is None:
        raise HTTPException(status_code=400, detail=f"Unknown label media: {data.label_media!r}")

    objects = data.canvas_json.get("objects", [])
    if not objects:
        raise HTTPException(status_code=400, detail="Template has no elements")

    detected = detect_fields(data.canvas_json)
    data.field_schema = merge_schema(detected, data.field_schema)

    try:
        return store.create_template(data)
    except ValueError as exc:
        msg = str(exc)
        status = 409 if "already exists" in msg else 400
        raise HTTPException(status_code=status, detail=msg) from exc


@router.put("/templates/{name}", response_model=Template)
async def update_template(name: str, data: TemplateUpdate) -> Template:
    existing = _load_or_404(name)

    if data.label_media is not None and get_label(data.label_media) is None:
        raise HTTPException(status_code=400, detail=f"Unknown label media: {data.label_media!r}")

    if data.canvas_json is not None:
        detected = detect_fields(data.canvas_json)
        data.field_schema = merge_schema(detected, existing.field_schema)

    result = store.update_template(name, data)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return result


@router.delete("/templates/{name}", status_code=204)
async def delete_template(name: str) -> None:
    if not store.soft_delete(name):
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")


class _DuplicateRequest(BaseModel):
    name: str
    label_media: str


@router.post("/templates/{name}/duplicate", response_model=Template, status_code=201)
async def duplicate_template(name: str, body: _DuplicateRequest) -> Template:
    _load_or_404(name)  # 404 if source doesn't exist / is deleted

    if get_label(body.label_media) is None:
        raise HTTPException(status_code=400, detail=f"Unknown label media: {body.label_media!r}")

    try:
        return store.duplicate(name, body.name, body.label_media)
    except ValueError as exc:
        msg = str(exc)
        status = 409 if "already exists" in msg else 400
        raise HTTPException(status_code=status, detail=msg) from exc
