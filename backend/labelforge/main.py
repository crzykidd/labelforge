import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from labelforge import history as history_module
from labelforge.catalog.loader import load_catalog
from labelforge.config import settings
from labelforge.db import init_db
from labelforge.render.fonts import load_fonts
from labelforge.routes import fonts, health, labels
from labelforge.routes import history as history_router
from labelforge.routes import print as print_router
from labelforge.routes import preview as preview_router
from labelforge.routes import printer as printer_router
from labelforge.routes import settings as settings_router
from labelforge.routes import template_print as template_print_router
from labelforge.routes import templates as templates_router


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    data_dir: Path = settings.data_dir
    (data_dir / "data").mkdir(parents=True, exist_ok=True)
    (data_dir / "fonts").mkdir(parents=True, exist_ok=True)
    logger.info("Data directory: %s", data_dir)

    yml_path = data_dir / "labels.yml"
    if not yml_path.exists():
        default_yml = Path("/app/labels.yml")
        if default_yml.exists():
            shutil.copy(default_yml, yml_path)
            logger.info("Copied default labels.yml to %s", yml_path)
        else:
            logger.warning(
                "labels.yml missing at %s and no default at /app/labels.yml", yml_path
            )

    db_path = data_dir / "data" / "app.db"
    init_db(db_path)
    logger.info("Database ready: %s", db_path)

    load_catalog(yml_path)
    load_fonts(data_dir / "fonts")

    try:
        history_module.prune_history()
    except Exception:
        logger.error("Startup retention pruning failed", exc_info=True)

    async def _retention_loop() -> None:
        while True:
            await asyncio.sleep(6 * 3600)
            try:
                history_module.prune_history()
            except Exception:
                logger.error("Scheduled retention pruning failed", exc_info=True)

    retention_task = asyncio.create_task(_retention_loop())

    yield

    retention_task.cancel()
    try:
        await retention_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="labelforge",
    version="0.0.1",
    description="Self-hosted Brother QL label printer API",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/api")
app.include_router(labels.router, prefix="/api")
app.include_router(fonts.router, prefix="/api")
app.include_router(print_router.router, prefix="/api")
app.include_router(preview_router.router, prefix="/api")
app.include_router(printer_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(templates_router.router, prefix="/api")
app.include_router(template_print_router.router, prefix="/api")
app.include_router(history_router.router, prefix="/api")

_FRONTEND_DIST = Path("/app/frontend/dist")

if _FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=_FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        return FileResponse(_FRONTEND_DIST / "index.html")
