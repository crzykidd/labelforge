from fastapi import APIRouter, Depends

from labelforge.models import FontInfo
from labelforge.render.fonts import get_fonts
from labelforge.routes.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/fonts", response_model=list[FontInfo])
async def list_fonts() -> list[FontInfo]:
    return [
        FontInfo(name=f.name, path=f.path, family=f.family, style=f.style)
        for f in get_fonts()
    ]
