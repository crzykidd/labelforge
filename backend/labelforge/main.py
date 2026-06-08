import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from labelforge import history as history_module
from labelforge.bootstrap import __version__, configure_logging
from labelforge.catalog.loader import load_catalog
from labelforge.catalog.reconcile import reconcile_catalog_files
from labelforge.config import settings
from labelforge.db import init_db
from labelforge.render.fonts import load_fonts
from labelforge.routes import admin as admin_router
from labelforge.routes import fonts, health, labels
from labelforge.routes import history as history_router
from labelforge.routes import preview as preview_router
from labelforge.routes import print as print_router
from labelforge.routes import printer as printer_router
from labelforge.routes import settings as settings_router
from labelforge.routes import template_print as template_print_router
from labelforge.routes import templates as templates_router
from labelforge.routes import version as version_router

logger = logging.getLogger(__name__)


def _ensure_writable(path: Path) -> None:
    """Fail fast with an actionable message if DATA_DIR isn't writable.

    The container runs as non-root (uid 1000). A volume/bind-mount owned by
    another uid is the most common reason startup dies, so surface it clearly.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        logger.critical(
            "DATA_DIR %s is NOT writable by uid=%d gid=%d (%s). The container runs as "
            "non-root (uid 1000); make the mounted volume or host directory writable by "
            "that uid — e.g. `chown -R 1000:1000 <host-path>` for a bind mount, or run with "
            "`--user $(id -u):$(id -g)`.",
            path,
            os.getuid(),
            os.getgid(),
            exc,
        )
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # Re-assert logging after uvicorn has set up its own, so our runtime logs show.
    configure_logging()
    logger.info("labelforge %s — running startup", __version__)
    logger.info(
        "Effective config: data_dir=%s printer_host=%s printer_model=%s backend=%s "
        "default_media=%s disable_auth=%s catalog_auto_merge=%s log_level=%s",
        settings.data_dir,
        settings.printer_host,
        settings.printer_model,
        settings.printer_backend,
        settings.default_label_media,
        settings.disable_auth,
        settings.catalog_auto_merge,
        settings.log_level,
    )

    data_dir: Path = settings.data_dir
    _ensure_writable(data_dir)
    (data_dir / "data").mkdir(parents=True, exist_ok=True)
    (data_dir / "fonts").mkdir(parents=True, exist_ok=True)
    logger.info("Data directory ready: %s", data_dir)

    yml_path = data_dir / "labels.yml"
    baseline_path = data_dir / "data" / "labels.default.yml"
    default_yml = Path("/app/labels.yml")
    try:
        summary = reconcile_catalog_files(
            default_yml,
            yml_path,
            baseline_path,
            auto_merge=settings.catalog_auto_merge,
        )
        logger.info("Catalog reconcile: %s", summary["reason"])
    except Exception:
        logger.error("Catalog reconcile failed — loading existing file as-is", exc_info=True)

    db_path = data_dir / "data" / "app.db"
    try:
        init_db(db_path)
    except Exception:
        logger.critical("Database initialization failed at %s", db_path, exc_info=True)
        raise

    load_catalog(yml_path)
    load_fonts(data_dir / "fonts")

    try:
        history_module.prune_history()
    except Exception:
        logger.error("Startup retention pruning failed", exc_info=True)

    logger.info("Startup complete — labelforge %s ready", __version__)

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
        # Expected: the task we just cancelled re-raises CancelledError on await.
        pass


app = FastAPI(
    title="labelforge",
    version=__version__,
    description="Self-hosted Brother QL label printer API",
    lifespan=lifespan,
)

app.include_router(admin_router.router, prefix="/api")
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
app.include_router(version_router.router, prefix="/api")

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
