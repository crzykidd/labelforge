import io
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from labelforge.config import settings
from labelforge.db import get_connection
from labelforge.models import (
    BatchJobResult,
    BatchPrintRequest,
    BatchPrintResponse,
    PrintRequest,
)
from labelforge.printer.client import PrintError, print_image
from labelforge.render.template import render_template
from labelforge.render.text import RenderError
from labelforge.routes.auth import require_auth
from labelforge.templates import store

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


def _db_path():
    return settings.data_dir / "data" / "app.db"


def _apply_defaults(template_fields, values: dict[str, str]) -> dict[str, str]:
    """Return values dict with defaults filled in; raise HTTPException for missing required."""
    result = dict(values)
    for field in template_fields:
        if field.name not in result:
            if field.default is not None:
                result[field.name] = field.default
            elif field.required:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: '{field.name}'",
                )
    return result


def _insert_job(
    template_name: str,
    label_media: str,
    field_values: dict,
    request_json: str,
    batch_id: str | None = None,
) -> int:
    conn = get_connection(_db_path())
    try:
        cursor = conn.execute(
            """INSERT INTO print_jobs
               (template_id, payload_json, label_media, field_values, batch_id)
               VALUES (?, ?, ?, ?, ?)""",
            (
                template_name,
                request_json,
                label_media,
                json.dumps(field_values),
                batch_id,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


@router.post("/print/{name}")
async def print_template(name: str, body: PrintRequest) -> dict:
    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    values = _apply_defaults(tmpl.field_schema, body.fields)

    try:
        image = render_template(tmpl, values)
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        outcome = print_image(
            image=image,
            label_media=tmpl.label_media,
            model=settings.printer_model,
            backend=settings.printer_backend,
            host=settings.printer_host,
        )
    except PrintError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job_id = _insert_job(name, tmpl.label_media, values, body.model_dump_json())

    # preview_url points at the history preview route, which lands in a later slice.
    return {
        "job_id": job_id,
        "status": outcome,
        "template": name,
        "label_media": tmpl.label_media,
        "preview_url": f"/api/history/{job_id}/preview.png",
    }


@router.post("/preview/{name}")
async def preview_template(name: str, body: PrintRequest) -> Response:
    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    values = _apply_defaults(tmpl.field_schema, body.fields)

    try:
        image = render_template(tmpl, values)
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.post("/print/{name}/batch", response_model=BatchPrintResponse)
async def batch_print(name: str, body: BatchPrintRequest) -> BatchPrintResponse:
    count = len(body.labels)
    if count < 1:
        raise HTTPException(status_code=400, detail="Batch count must be >= 1")
    if count > 1000:
        raise HTTPException(status_code=400, detail="Batch count exceeds maximum (1000)")

    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    batch_id = str(uuid.uuid4())
    jobs: list[BatchJobResult] = []
    succeeded = 0
    failed = 0

    for label_values in body.labels:
        try:
            values = _apply_defaults(tmpl.field_schema, label_values)
            image = render_template(tmpl, values)
            outcome = print_image(
                image=image,
                label_media=tmpl.label_media,
                model=settings.printer_model,
                backend=settings.printer_backend,
                host=settings.printer_host,
            )
            job_id = _insert_job(
                name, tmpl.label_media, values,
                BatchPrintRequest(labels=[label_values]).model_dump_json(),
                batch_id=batch_id,
            )
            jobs.append(BatchJobResult(job_id=job_id, status=outcome))
            succeeded += 1
        except (HTTPException, RenderError, PrintError, ValueError) as exc:
            msg = exc.detail if isinstance(exc, HTTPException) else str(exc)
            jobs.append(BatchJobResult(job_id=-1, status=f"error: {msg}"))
            failed += 1
        except Exception as exc:
            jobs.append(BatchJobResult(job_id=-1, status=f"error: {exc}"))
            failed += 1

    # Return 200 if at least one succeeded; 500 if all failed.
    # Mixed results return 200 — 207 deferred per api.md.
    if failed == count:
        raise HTTPException(
            status_code=500,
            detail=BatchPrintResponse(
                batch_id=batch_id, jobs=jobs, succeeded=0, failed=failed
            ).model_dump(),
        )

    return BatchPrintResponse(
        batch_id=batch_id, jobs=jobs, succeeded=succeeded, failed=failed
    )
