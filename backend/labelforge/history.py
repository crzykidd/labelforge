import io
import json
import logging

from PIL import Image

from labelforge import settings_store
from labelforge.config import settings
from labelforge.db import get_connection
from labelforge.printer.client import to_print_bitmap

logger = logging.getLogger(__name__)


def insert_job_with_preview(
    image: Image.Image,
    payload_json: str,
    label_media: str,
    template_name: str | None = None,
    field_values: dict | None = None,
    batch_id: str | None = None,
    reprint_of: int | None = None,
) -> int:
    db_path = settings.data_dir / "data" / "app.db"
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO print_jobs
               (template_id, payload_json, label_media, field_values, batch_id, reprint_of)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                template_name,
                payload_json,
                label_media,
                json.dumps(field_values) if field_values is not None else None,
                batch_id,
                reprint_of,
            ),
        )
        conn.commit()
        job_id = cursor.lastrowid
    finally:
        conn.close()

    _save_preview(job_id, image)
    return job_id


def _save_preview(job_id: int, image: Image.Image) -> None:
    try:
        previews_dir = settings.data_dir / "label-previews"
        previews_dir.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        to_print_bitmap(image).save(buf, format="PNG")
        (previews_dir / f"{job_id}.png").write_bytes(buf.getvalue())

        db_path = settings.data_dir / "data" / "app.db"
        conn = get_connection(db_path)
        try:
            conn.execute(
                "UPDATE print_jobs SET preview_path = ? WHERE id = ?",
                (f"{job_id}.png", job_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to save preview for job %d", job_id, exc_info=True)


def prune_history() -> None:
    try:
        mode = settings_store.get("retention_mode")
        if mode == "forever":
            return

        db_path = settings.data_dir / "data" / "app.db"
        conn = get_connection(db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM print_jobs").fetchone()[0]

            if mode == "last_n":
                count = settings_store.get("retention_count")
                rows = conn.execute(
                    """SELECT id, preview_path FROM print_jobs
                       WHERE pinned = 0
                       AND id NOT IN (
                           SELECT id FROM print_jobs WHERE pinned = 0
                           ORDER BY created_at DESC, id DESC
                           LIMIT ?
                       )""",
                    (count,),
                ).fetchall()
            elif mode == "last_days":
                days = settings_store.get("retention_days")
                rows = conn.execute(
                    """SELECT id, preview_path FROM print_jobs
                       WHERE pinned = 0
                       AND created_at < datetime('now', ?)""",
                    (f"-{days} days",),
                ).fetchall()
            else:
                return

            if not rows:
                return

            ids = [r["id"] for r in rows]
            preview_paths = [r["preview_path"] for r in rows if r["preview_path"]]
            pruned = len(ids)
            db_size_before = db_path.stat().st_size if db_path.exists() else 0

            conn.execute(
                f"DELETE FROM print_jobs WHERE id IN ({','.join('?' * pruned)})",  # noqa: S608
                ids,
            )
            conn.commit()

            previews_dir = settings.data_dir / "label-previews"
            for fname in preview_paths:
                try:
                    (previews_dir / fname).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Could not delete preview file %s", fname, exc_info=True)

            if total > 0 and pruned / total > 0.1:
                logger.info("Running VACUUM after pruning %.0f%% of rows", 100 * pruned / total)
                try:
                    conn.execute("VACUUM")
                except Exception:
                    logger.warning("VACUUM failed", exc_info=True)

            db_size_after = db_path.stat().st_size if db_path.exists() else 0
            logger.info(
                "prune_history: pruned %d rows (mode=%s), DB %d → %d bytes",
                pruned, mode, db_size_before, db_size_after,
            )
        finally:
            conn.close()
    except Exception:
        logger.error("prune_history failed", exc_info=True)
