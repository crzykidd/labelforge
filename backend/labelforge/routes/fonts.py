from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from labelforge.models import FontInfo
from labelforge.render.fonts import get_font_path, get_fonts
from labelforge.routes.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])

_MEDIA_TYPES: dict[str, str] = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}


@router.get("/fonts", response_model=list[FontInfo])
async def list_fonts() -> list[FontInfo]:
    return [FontInfo(name=f.name, path=f.path, family=f.family, style=f.style) for f in get_fonts()]


@router.get("/fonts/{name}/file")
async def get_font_file(name: str) -> FileResponse:
    """Serve the raw font bytes for a font known to the server.

    The path is resolved exclusively via get_font_path() — the scanner's
    allow-list — so user input is never joined onto a directory.  Unknown
    names and path-traversal attempts both 404.
    """
    path = get_font_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Font not found: {name}")
    font_path = Path(path)
    suffix = font_path.suffix.lower()
    media_type = _MEDIA_TYPES.get(suffix, "application/octet-stream")
    return FileResponse(
        path=font_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
