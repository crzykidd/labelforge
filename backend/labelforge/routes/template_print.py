import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from labelforge import settings_store
from labelforge.config import settings
from labelforge.history import insert_job_with_preview
from labelforge.models import (
    BatchJobResult,
    BatchPrintRequest,
    BatchPrintResponse,
    PrintRequest,
)
from labelforge.printer.client import PrintError, StatusUnavailable, media_compatible, print_image, status_read, to_print_bitmap
from labelforge.render.template import render_template
from labelforge.render.text import RenderError
from labelforge.routes.auth import require_auth
from labelforge.templates import store

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


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


@router.post("/print/{name}")
async def print_template(name: str, body: PrintRequest, override: bool = False) -> dict:
    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    values = _apply_defaults(tmpl.field_schema, body.fields)

    try:
        image = render_template(tmpl, values)
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if settings_store.get("printer_status_check"):
        timeout_ms = settings_store.get("printer_status_timeout_ms")
        try:
            status = status_read(
                host=settings.printer_host,
                backend=settings.printer_backend,
                timeout_ms=timeout_ms,
            )
            if status["errors"]:
                code = status["errors"][0].lower().replace(" ", "_")
                raise HTTPException(status_code=409, detail={
                    "error": "printer_error",
                    "code": code,
                    "message": f"Printer error: {', '.join(status['errors'])}",
                    "raw": status,
                })
            if status["media_id"] is not None and not media_compatible(status["media_id"], tmpl.label_media):
                if not override:
                    raise HTTPException(status_code=409, detail={
                        "error": "media_mismatch",
                        "expected": tmpl.label_media,
                        "loaded": status["media_id"],
                        "override_allowed": True,
                        "message": (
                            f"Printer has {status['media_id']} loaded, "
                            f"template expects {tmpl.label_media}. "
                            "Pass override=true to print anyway."
                        ),
                    })
                logger.warning(
                    "Media mismatch (override): loaded=%s expected=%s",
                    status["media_id"], tmpl.label_media,
                )
        except StatusUnavailable:
            logger.warning("Printer status unavailable; proceeding without check")

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

    job_id = insert_job_with_preview(
        image=image,
        payload_json=body.model_dump_json(),
        label_media=tmpl.label_media,
        template_name=name,
        field_values=values,
    )

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
    to_print_bitmap(image).save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.post("/print/{name}/batch", response_model=BatchPrintResponse)
async def batch_print(name: str, body: BatchPrintRequest, override: bool = False) -> BatchPrintResponse:
    count = len(body.labels)
    if count < 1:
        raise HTTPException(status_code=400, detail="Batch count must be >= 1")
    if count > 1000:
        raise HTTPException(status_code=400, detail="Batch count exceeds maximum (1000)")

    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    # Status check once before the loop — avoids per-label overhead
    if settings_store.get("printer_status_check"):
        timeout_ms = settings_store.get("printer_status_timeout_ms")
        try:
            status = status_read(
                host=settings.printer_host,
                backend=settings.printer_backend,
                timeout_ms=timeout_ms,
            )
            if status["errors"]:
                code = status["errors"][0].lower().replace(" ", "_")
                raise HTTPException(status_code=409, detail={
                    "error": "printer_error",
                    "code": code,
                    "message": f"Printer error: {', '.join(status['errors'])}",
                    "raw": status,
                })
            if status["media_id"] is not None and not media_compatible(status["media_id"], tmpl.label_media):
                if not override:
                    raise HTTPException(status_code=409, detail={
                        "error": "media_mismatch",
                        "expected": tmpl.label_media,
                        "loaded": status["media_id"],
                        "override_allowed": True,
                        "message": (
                            f"Printer has {status['media_id']} loaded, "
                            f"template expects {tmpl.label_media}. "
                            "Pass override=true to print anyway."
                        ),
                    })
                logger.warning(
                    "Media mismatch (override): loaded=%s expected=%s",
                    status["media_id"], tmpl.label_media,
                )
        except StatusUnavailable:
            logger.warning("Printer status unavailable; proceeding without check")

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
            job_id = insert_job_with_preview(
                image=image,
                payload_json=BatchPrintRequest(labels=[label_values]).model_dump_json(),
                label_media=tmpl.label_media,
                template_name=name,
                field_values=values,
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
