import logging

from fastapi import APIRouter, Depends, HTTPException

from labelforge.catalog.loader import get_label
from labelforge.config import settings
from labelforge.db import get_connection
from labelforge.models import PrintJobResponse, QuickPrintRequest
from labelforge.printer.client import PrintError, print_image
from labelforge.render.text import RenderError, render_text
from labelforge.routes.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.post("/print/quick", response_model=PrintJobResponse)
async def quick_print(request: QuickPrintRequest) -> PrintJobResponse:
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

    db_path = settings.data_dir / "data" / "app.db"
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO print_jobs (payload_json, label_media) VALUES (?, ?)",
            (request.model_dump_json(), request.label_media),
        )
        conn.commit()
        job_id = cursor.lastrowid
    finally:
        conn.close()

    return PrintJobResponse(job_id=job_id, status=outcome)
