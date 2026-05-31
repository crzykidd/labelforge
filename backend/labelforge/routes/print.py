import logging

from fastapi import APIRouter, Depends, HTTPException

from labelforge.catalog.loader import get_label
from labelforge.config import settings
from labelforge import settings_store
from labelforge.history import insert_job_with_preview
from labelforge.models import PrintJobResponse, QuickPrintRequest
from labelforge.printer.client import PrintError, StatusUnavailable, media_compatible, print_image, status_read
from labelforge.render.text import RenderError, render_text
from labelforge.routes.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.post("/print/quick", response_model=PrintJobResponse)
async def quick_print(request: QuickPrintRequest, override: bool = False) -> PrintJobResponse:
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    if get_label(request.label_media) is None:
        raise HTTPException(status_code=400, detail=f"Unknown label media: {request.label_media}")

    try:
        image = render_text(
            text=request.text,
            font_name=request.font,
            font_size=request.font_size,
            alignment=request.alignment,
            orientation=request.orientation,
            bold=request.bold,
            italic=request.italic,
            label_media=request.label_media,
        )
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
            if status["media_id"] is not None and not media_compatible(status["media_id"], request.label_media):
                if not override:
                    raise HTTPException(status_code=409, detail={
                        "error": "media_mismatch",
                        "expected": request.label_media,
                        "loaded": status["media_id"],
                        "override_allowed": True,
                        "message": (
                            f"Printer has {status['media_id']} loaded, "
                            f"template expects {request.label_media}. "
                            "Pass override=true to print anyway."
                        ),
                    })
                logger.warning(
                    "Media mismatch (override): loaded=%s expected=%s",
                    status["media_id"], request.label_media,
                )
        except StatusUnavailable:
            logger.warning("Printer status unavailable; proceeding without check")

    try:
        outcome = print_image(
            image=image,
            label_media=request.label_media,
            model=settings.printer_model,
            backend=settings.printer_backend,
            host=settings.printer_host,
        )
    except PrintError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job_id = insert_job_with_preview(
        image=image,
        payload_json=request.model_dump_json(),
        label_media=request.label_media,
    )

    try:
        settings_store.set("last_quick_print", request.model_dump())
    except Exception:
        logger.warning("Failed to record last_quick_print", exc_info=True)

    return PrintJobResponse(
        job_id=job_id,
        status=outcome,
        preview_url=f"/api/history/{job_id}/preview.png",
    )
