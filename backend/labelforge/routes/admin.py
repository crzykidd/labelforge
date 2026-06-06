from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from labelforge.catalog.loader import load_catalog
from labelforge.catalog.reconcile import reconcile_catalog_files
from labelforge.config import settings
from labelforge.routes.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])

_DEFAULT_PATH = Path("/app/labels.yml")


@router.post("/admin/reload-catalog")
async def reload_catalog() -> dict[str, Any]:
    """Re-run catalog reconciliation and reload from disk.

    Returns a summary of what changed (entries added/updated, whether the
    operator file was rewritten) plus the resulting catalog size.
    """
    yml_path = settings.data_dir / "labels.yml"
    baseline_path = settings.data_dir / "data" / "labels.default.yml"

    summary = reconcile_catalog_files(
        _DEFAULT_PATH,
        yml_path,
        baseline_path,
        auto_merge=settings.catalog_auto_merge,
    )
    load_catalog(yml_path)

    from labelforge.catalog.loader import get_catalog

    return {
        "wrote": summary["wrote"],
        "added": summary["added"],
        "updated": summary["updated"],
        "backed_up": summary["backed_up"],
        "reason": summary["reason"],
        "catalog_size": len(get_catalog()),
    }
