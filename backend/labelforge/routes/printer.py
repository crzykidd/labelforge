import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from labelforge import settings_store
from labelforge.catalog.loader import get_label
from labelforge.config import settings
from labelforge.printer.client import StatusUnavailable, status_read

logger = logging.getLogger(__name__)

router = APIRouter(tags=["printer"])


@router.get("/printer/status")
async def get_printer_status() -> dict:
    timeout_ms = settings_store.get("printer_status_timeout_ms")

    try:
        status = status_read(
            host=settings.printer_host,
            backend=settings.printer_backend,
            timeout_ms=timeout_ms,
        )
    except StatusUnavailable as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "status_unavailable", "message": str(exc)},
        )

    media_id = status["media_id"]
    loaded_media = None
    if media_id is not None:
        label = get_label(media_id)
        if label:
            display_name = label.display_name
        elif status["length_mm"] == 0:
            display_name = f"{status['width_mm']}mm Continuous"
        else:
            display_name = f"{status['width_mm']}mm × {status['length_mm']}mm"

        loaded_media = {
            "id": media_id,
            "display_name": display_name,
            "width_mm": status["width_mm"],
            "length_mm": status["length_mm"],
            "color_capable": status["color_capable"],
        }

    return {
        "ready": status["ready"],
        "model": status["model"],
        "loaded_media": loaded_media,
        "errors": status["errors"],
        "source": status["source"],
    }
