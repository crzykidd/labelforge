import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from labelforge.catalog.loader import get_label
from labelforge.config import settings
from labelforge.db import get_connection
from labelforge.history import insert_job_with_preview
from labelforge.models import HistoryDetail, HistoryItem, PinRequest, QuickPrintRequest
from labelforge.printer.client import PrintError, print_image
from labelforge.render.template import render_template
from labelforge.render.text import RenderError, render_text
from labelforge.routes.auth import require_auth
from labelforge.templates import store

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


def _db_path():
    return settings.data_dir / "data" / "app.db"


def _row_to_item(row) -> HistoryItem:
    return HistoryItem(
        id=row["id"],
        template_id=row["template_id"],
        is_quick_print=row["template_id"] is None,
        field_values=json.loads(row["field_values"]) if row["field_values"] else None,
        label_media=row["label_media"],
        pinned=bool(row["pinned"]),
        created_at=row["created_at"],
        reprint_of=row["reprint_of"],
        batch_id=row["batch_id"],
        preview_url=f"/api/history/{row['id']}/preview.png",
    )


def _row_to_detail(row) -> HistoryDetail:
    item = _row_to_item(row)
    payload = None
    if row["payload_json"]:
        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            pass
    return HistoryDetail(**item.model_dump(), payload_json=payload)


@router.get("/history", response_model=list[HistoryItem])
async def list_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    template: str | None = None,
    pinned: bool | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
) -> list[HistoryItem]:
    sql = "SELECT * FROM print_jobs WHERE 1=1"
    params: list = []
    if template is not None:
        sql += " AND template_id = ?"
        params.append(template)
    if pinned is not None:
        sql += " AND pinned = ?"
        params.append(1 if pinned else 0)
    if from_ is not None:
        sql += " AND created_at >= ?"
        params.append(from_)
    if to is not None:
        sql += " AND created_at <= ?"
        params.append(to)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = get_connection(_db_path())
    try:
        rows = conn.execute(sql, params).fetchall()  # noqa: S608
    finally:
        conn.close()
    return [_row_to_item(r) for r in rows]


@router.get("/history/{job_id}", response_model=HistoryDetail)
async def get_history(job_id: int) -> HistoryDetail:
    conn = get_connection(_db_path())
    try:
        row = conn.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Print job {job_id} not found")
    return _row_to_detail(row)


@router.get("/history/{job_id}/preview.png", response_class=FileResponse)
async def history_preview(job_id: int) -> Response:
    conn = get_connection(_db_path())
    try:
        row = conn.execute("SELECT preview_path FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Print job not found")
    if not row["preview_path"]:
        raise HTTPException(status_code=404, detail="Preview not available")
    preview_file = settings.data_dir / "label-previews" / row["preview_path"]
    if not preview_file.exists():
        raise HTTPException(status_code=404, detail="Preview file not found")
    return FileResponse(str(preview_file), media_type="image/png")


@router.post("/history/{job_id}/reprint")
async def reprint_history(job_id: int) -> dict:
    conn = get_connection(_db_path())
    try:
        row = conn.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Print job {job_id} not found")

    if row["template_id"] is not None:
        return await _reprint_template(job_id, row)
    return await _reprint_quick(job_id, row)


async def _reprint_template(job_id: int, row) -> dict:
    tmpl = store.get_template(row["template_id"], include_deleted=True)
    if tmpl is None:
        raise HTTPException(
            status_code=409,
            detail=f"Template '{row['template_id']}' no longer exists and cannot be reprinted",
        )
    # Reprint on the media from the original history row, not the template's stored media.
    # This reproduces one-off media overrides from the recall page exactly.
    row_media = row["label_media"]
    if get_label(row_media) is None:
        raise HTTPException(
            status_code=409,
            detail=f"Label media '{row_media}' is no longer in the catalog",
        )
    field_values = json.loads(row["field_values"]) if row["field_values"] else {}
    try:
        image = render_template(tmpl, field_values, media_override=row_media)
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        outcome = print_image(
            image=image,
            label_media=row_media,
            model=settings.printer_model,
            backend=settings.printer_backend,
            host=settings.printer_host,
        )
    except PrintError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    new_id = insert_job_with_preview(
        image=image,
        payload_json=row["payload_json"],
        label_media=row_media,
        template_name=row["template_id"],
        field_values=field_values,
        reprint_of=job_id,
    )
    return {"job_id": new_id, "status": outcome, "reprint_of": job_id}


async def _reprint_quick(job_id: int, row) -> dict:
    try:
        request = QuickPrintRequest(**json.loads(row["payload_json"]))
    except Exception as exc:
        raise HTTPException(
            status_code=409, detail=f"Cannot reconstruct quick-print request: {exc}"
        ) from exc
    if get_label(request.label_media) is None:
        raise HTTPException(
            status_code=409,
            detail=f"Label media '{request.label_media}' is no longer in the catalog",
        )
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
    new_id = insert_job_with_preview(
        image=image,
        payload_json=row["payload_json"],
        label_media=request.label_media,
        reprint_of=job_id,
    )
    return {"job_id": new_id, "status": outcome, "reprint_of": job_id}


@router.post("/history/{job_id}/pin", response_model=HistoryItem)
async def pin_history(job_id: int, body: PinRequest) -> HistoryItem:
    conn = get_connection(_db_path())
    try:
        if not conn.execute("SELECT 1 FROM print_jobs WHERE id = ?", (job_id,)).fetchone():
            raise HTTPException(status_code=404, detail=f"Print job {job_id} not found")
        conn.execute(
            "UPDATE print_jobs SET pinned = ? WHERE id = ?",
            (1 if body.pinned else 0, job_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_item(row)
    finally:
        conn.close()


@router.delete("/history/{job_id}", status_code=204)
async def delete_history(job_id: int) -> None:
    conn = get_connection(_db_path())
    try:
        row = conn.execute("SELECT preview_path FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Print job {job_id} not found")
        conn.execute("DELETE FROM print_jobs WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()
    if row["preview_path"]:
        try:
            (settings.data_dir / "label-previews" / row["preview_path"]).unlink(missing_ok=True)
        except Exception:
            logger.warning("Could not delete preview file for job %d", job_id, exc_info=True)
