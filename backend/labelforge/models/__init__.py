from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LabelEntry(BaseModel):
    id: str
    display_name: str
    brother_part: str | None = None
    description: str | None = None
    category: str | None = None
    color_capable: bool = False
    printer_requirements: list[str] = []
    common_use: list[str] = []
    preview_image: str | None = None
    # library-derived fields
    dots_printable: tuple[int, int] = (0, 0)
    tape_size: tuple[int, int] = (0, 0)
    # form_factor integer: 1=die-cut, 2=continuous, 3=round, 4=ptouch-continuous
    form_factor: int = 0


class FontInfo(BaseModel):
    name: str
    path: str
    family: str
    style: str


class QuickPrintRequest(BaseModel):
    text: str = Field(..., min_length=1)
    font: str
    font_size: int = Field(48, ge=6, le=200)
    alignment: Literal["left", "center", "right"] = "left"
    orientation: Literal["standard", "rotated"] = "standard"
    label_media: str
    bold: bool = False
    italic: bool = False


class PrintJobResponse(BaseModel):
    job_id: int
    status: str
    preview_url: str | None = None


# ── Templates ────────────────────────────────────────────────────────────────

class FieldSpec(BaseModel):
    name: str
    type: Literal["text", "number", "date", "enum"] = "text"
    required: bool = True
    default: str | None = None
    increment: bool = False
    enum_values: list[str] = []


class Template(BaseModel):
    name: str
    display_name: str
    label_media: str
    canvas_json: dict
    field_schema: list[FieldSpec]
    created_at: str
    updated_at: str


class TemplateCreate(BaseModel):
    name: str
    display_name: str | None = None
    label_media: str
    canvas_json: dict
    field_schema: list[FieldSpec] = []


class TemplateUpdate(BaseModel):
    display_name: str | None = None
    label_media: str | None = None
    canvas_json: dict | None = None
    field_schema: list[FieldSpec] | None = None


# ── Print / batch ─────────────────────────────────────────────────────────────

class PrintRequest(BaseModel):
    fields: dict[str, str] = {}


class BatchPrintRequest(BaseModel):
    labels: list[dict[str, str]]


class BatchJobResult(BaseModel):
    job_id: int
    status: str


class BatchPrintResponse(BaseModel):
    batch_id: str
    jobs: list[BatchJobResult]
    succeeded: int
    failed: int
