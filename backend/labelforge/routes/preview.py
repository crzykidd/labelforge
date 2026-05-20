import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from labelforge.catalog.loader import get_label
from labelforge.models import QuickPrintRequest
from labelforge.render.text import RenderError, render_text
from labelforge.routes.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.post("/preview/quick")
async def preview_quick(request: QuickPrintRequest) -> Response:
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

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
