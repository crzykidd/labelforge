import logging
from pathlib import Path

import yaml
from brother_ql.labels import ALL_LABELS, FormFactor
from brother_ql.models import ALL_MODELS

from labelforge.config import settings
from labelforge.models import LabelEntry

logger = logging.getLogger(__name__)

_catalog: dict[str, LabelEntry] = {}

# Map FormFactor enum values to the integer stored in LabelEntry.form_factor.
# FormFactor.DIE_CUT=1, ENDLESS=2, ROUND_DIE_CUT=3, PTOUCH_ENDLESS=4
_FORM_FACTOR_INT: dict[FormFactor, int] = {ff: ff.value for ff in FormFactor}


def _compute_compatibility(
    lib_label, printer_model: str, two_color: bool | None
) -> tuple[bool, str | None]:
    """Whether the configured printer can print this media, and why not.

    Library-derived (not from labels.yml). brother_ql's Label.works_with_model()
    is unusable in the pinned fork: it raises NameError on any restricted label
    and ignores two-color capability — see docs/decisions.md. Compute from the
    primitive Label fields instead.

    `two_color is None` means the configured model wasn't found in the library;
    treat all media as supported rather than wrongly disabling everything.
    """
    if two_color is None:
        return True, None
    restricted = list(getattr(lib_label, "restricted_to_models", []) or [])
    if restricted and printer_model not in restricted:
        return False, "Requires a wide-format printer (QL-1100 series)"
    if getattr(lib_label, "color", 0) and not two_color:
        return False, "Requires a two-color printer (QL-800 series)"
    return True, None


def load_catalog(yml_path: Path) -> None:
    global _catalog

    lib_labels = {label.identifier: label for label in ALL_LABELS}

    # Compatibility is computed against the configured printer at load time
    # (printer_model is fixed in config). A future POST /api/admin/reload-catalog
    # should call this again to recompute.
    printer_model = settings.printer_model
    model = next((m for m in ALL_MODELS if m.identifier == printer_model), None)
    if model is None:
        logger.warning(
            "Configured printer_model '%s' not in brother_ql — treating all media as supported",
            printer_model,
        )
    two_color = model.two_color if model is not None else None

    yml_entries: dict[str, dict] = {}
    if yml_path.exists():
        with yml_path.open() as fh:
            data = yaml.safe_load(fh) or {}
        for entry in data.get("labels", []):
            try:
                yml_entries[entry["id"]] = entry
            except (KeyError, TypeError):
                logger.warning("Skipping malformed catalog entry: %s", entry)
    else:
        logger.warning("labels.yml not found at %s — using library fallbacks only", yml_path)

    new_catalog: dict[str, LabelEntry] = {}
    lib_only = 0

    for lib_id, lib_label in lib_labels.items():
        form_factor_int = _FORM_FACTOR_INT.get(lib_label.form_factor, 0)
        dots = (lib_label.dots_printable[0], lib_label.dots_printable[1])
        tape = (lib_label.tape_size[0], lib_label.tape_size[1])
        restricted = list(getattr(lib_label, "restricted_to_models", []) or [])
        color = int(getattr(lib_label, "color", 0) or 0)
        supported, reason = _compute_compatibility(lib_label, printer_model, two_color)

        if lib_id in yml_entries:
            y = yml_entries[lib_id]
            entry = LabelEntry(
                id=lib_id,
                display_name=y.get("display_name", lib_id),
                brother_part=y.get("brother_part"),
                description=y.get("description"),
                category=y.get("category"),
                color_capable=bool(y.get("color_capable", False)),
                common_use=y.get("common_use") or [],
                preview_image=y.get("preview_image"),
                dots_printable=dots,
                tape_size=tape,
                form_factor=form_factor_int,
                restricted_to_models=restricted,
                color=color,
                supported=supported,
                incompatible_reason=reason,
            )
        else:
            entry = LabelEntry(
                id=lib_id,
                display_name=lib_id,
                dots_printable=dots,
                tape_size=tape,
                form_factor=form_factor_int,
                restricted_to_models=restricted,
                color=color,
                supported=supported,
                incompatible_reason=reason,
            )
            lib_only += 1

        new_catalog[lib_id] = entry

    yml_only = sum(1 for k in yml_entries if k not in lib_labels)
    for stale_id in yml_entries:
        if stale_id not in lib_labels:
            logger.warning("Catalog entry '%s' not in brother_ql library — hidden", stale_id)

    _catalog = new_catalog
    logger.info(
        "Catalog loaded: %d entries (%d library-only fallbacks, %d yml-only hidden)",
        len(new_catalog),
        lib_only,
        yml_only,
    )


def get_catalog() -> dict[str, LabelEntry]:
    return _catalog


def get_label(label_id: str) -> LabelEntry | None:
    return _catalog.get(label_id)
