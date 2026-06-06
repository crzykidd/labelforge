import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from labelforge import settings_store
from labelforge.catalog.loader import get_label
from labelforge.config import settings
from labelforge.history import insert_job_with_preview
from labelforge.models import (
    BatchJobResult,
    BatchPrintRequest,
    BatchPrintResponse,
    PrintRequest,
)
from labelforge.printer.client import (
    PrintError,
    StatusUnavailable,
    media_compatible,
    print_image,
    status_read,
    to_print_bitmap,
)
from labelforge.render.template import detect_overflow, render_template
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


def _apply_sample_defaults(template_fields, values: dict[str, str]) -> dict[str, str]:
    """Return values dict with caller-supplied values first, then defaults,
    then field name as sample.

    Never raises — every field gets a value, so preview always renders.
    """
    result = dict(values)
    for field in template_fields:
        if field.name not in result:
            # Use stored default if set; otherwise show the field name itself so
            # {type} renders as the literal text "type" — makes variables visible in preview.
            result[field.name] = field.default if field.default is not None else field.name
    return result


def _resolve_effective_media(body_label_media: str | None, tmpl_label_media: str) -> str:
    """Validate and return the effective media id, raising HTTPException on invalid input."""
    if body_label_media is None:
        return tmpl_label_media
    label = get_label(body_label_media)
    if label is None or not label.supported:
        raise HTTPException(
            status_code=400,
            detail=f"Label media '{body_label_media}' is not a supported catalog entry",
        )
    return body_label_media


@router.post("/print/{name}")
async def print_template(name: str, body: PrintRequest, override: bool = False) -> dict:
    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    effective_media = _resolve_effective_media(body.label_media, tmpl.label_media)
    values = _apply_defaults(tmpl.field_schema, body.fields)

    try:
        image = render_template(tmpl, values, media_override=body.label_media)
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
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "printer_error",
                        "code": code,
                        "message": f"Printer error: {', '.join(status['errors'])}",
                        "raw": status,
                    },
                )
            media_id = status["media_id"]
            if media_id is not None and not media_compatible(media_id, effective_media):
                if not override:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "media_mismatch",
                            "expected": effective_media,
                            "loaded": media_id,
                            "override_allowed": True,
                            "message": (
                                f"Printer has {media_id} loaded, "
                                f"template expects {effective_media}. "
                                "Pass override=true to print anyway."
                            ),
                        },
                    )
                logger.warning(
                    "Media mismatch (override): loaded=%s expected=%s",
                    media_id,
                    effective_media,
                )
        except StatusUnavailable:
            logger.warning("Printer status unavailable; proceeding without check")

    try:
        outcome = print_image(
            image=image,
            label_media=effective_media,
            model=settings.printer_model,
            backend=settings.printer_backend,
            host=settings.printer_host,
        )
    except PrintError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job_id = insert_job_with_preview(
        image=image,
        payload_json=body.model_dump_json(),
        label_media=effective_media,
        template_name=name,
        field_values=values,
    )

    overflow = detect_overflow(tmpl, effective_media)

    return {
        "job_id": job_id,
        "status": outcome,
        "template": name,
        "label_media": effective_media,
        "overflow": overflow,
        "preview_url": f"/api/history/{job_id}/preview.png",
    }


@router.post("/preview/{name}")
async def preview_template(name: str, body: PrintRequest) -> Response:
    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    effective_media = _resolve_effective_media(body.label_media, tmpl.label_media)

    # Preview is a layout check — fill missing fields with samples rather than failing.
    values = _apply_sample_defaults(tmpl.field_schema, body.fields)

    try:
        image = render_template(tmpl, values, media_override=body.label_media)
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    buf = io.BytesIO()
    # Two-color templates render as RGB; preserve color in the preview PNG.
    # Mono templates apply the print threshold so preview == print.
    preview = image if image.mode == "RGB" else to_print_bitmap(image)
    preview.save(buf, format="PNG")

    overflow = detect_overflow(tmpl, effective_media)
    headers: dict[str, str] = {}
    if overflow:
        headers["X-Label-Overflow"] = "true"

    return Response(content=buf.getvalue(), media_type="image/png", headers=headers)


@router.post("/print/{name}/batch", response_model=BatchPrintResponse)
async def batch_print(
    name: str, body: BatchPrintRequest, override: bool = False
) -> BatchPrintResponse:
    count = len(body.labels)
    if count < 1:
        raise HTTPException(status_code=400, detail="Batch count must be >= 1")
    if count > 1000:
        raise HTTPException(status_code=400, detail="Batch count exceeds maximum (1000)")

    tmpl = store.get_template(name)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    effective_media = _resolve_effective_media(body.label_media, tmpl.label_media)

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
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "printer_error",
                        "code": code,
                        "message": f"Printer error: {', '.join(status['errors'])}",
                        "raw": status,
                    },
                )
            media_id = status["media_id"]
            if media_id is not None and not media_compatible(media_id, effective_media):
                if not override:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "media_mismatch",
                            "expected": effective_media,
                            "loaded": media_id,
                            "override_allowed": True,
                            "message": (
                                f"Printer has {media_id} loaded, "
                                f"template expects {effective_media}. "
                                "Pass override=true to print anyway."
                            ),
                        },
                    )
                logger.warning(
                    "Media mismatch (override): loaded=%s expected=%s",
                    media_id,
                    effective_media,
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
            image = render_template(tmpl, values, media_override=body.label_media)
            outcome = print_image(
                image=image,
                label_media=effective_media,
                model=settings.printer_model,
                backend=settings.printer_backend,
                host=settings.printer_host,
            )
            job_id = insert_job_with_preview(
                image=image,
                payload_json=BatchPrintRequest(labels=[label_values]).model_dump_json(),
                label_media=effective_media,
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

    return BatchPrintResponse(batch_id=batch_id, jobs=jobs, succeeded=succeeded, failed=failed)
