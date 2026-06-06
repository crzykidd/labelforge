import logging
import shutil
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def merge_catalog(operator: dict, old_default: dict, new_default: dict) -> tuple[dict, list[str]]:
    """3-way merge of labels.yml documents keyed by entry id.

    Returns (merged_document, change_log_lines). Operator always wins on conflict.

    Rules:
    - New entry (id in new_default, not in operator): added verbatim.
    - Existing entry: for each field in new_default, take the new value only when
      the operator never customized it (op_val == old_val). Otherwise keep op_val.
    - Operator-only entry: kept as-is regardless of what the default says.
    """

    def _entries(doc: dict) -> list[dict]:
        return [e for e in (doc.get("labels") or []) if isinstance(e, dict) and "id" in e]

    op_by_id = {e["id"]: e for e in _entries(operator)}
    old_by_id = {e["id"]: e for e in _entries(old_default)}
    new_by_id = {e["id"]: e for e in _entries(new_default)}

    changes: list[str] = []
    merged_labels: list[dict] = []

    # Pass 1: operator's entries in their original order
    for op_entry in _entries(operator):
        entry_id = op_entry["id"]

        if entry_id not in new_by_id:
            # Operator-only or removed-from-default: keep as-is, never delete
            merged_labels.append(dict(op_entry))
            continue

        merged = dict(op_entry)
        old_entry = old_by_id.get(entry_id, {})
        new_entry = new_by_id[entry_id]

        for field, new_val in new_entry.items():
            if field == "id":
                continue
            old_val = old_entry.get(field)
            op_val = op_entry.get(field)
            if op_val == old_val and new_val != op_val:
                merged[field] = new_val
                changes.append(f"updated {entry_id}.{field}")

        merged_labels.append(merged)

    # Pass 2: brand-new entries from new_default not present in operator
    op_ids = set(op_by_id)
    for new_entry in _entries(new_default):
        if new_entry["id"] not in op_ids:
            merged_labels.append(dict(new_entry))
            changes.append(f"added {new_entry['id']}")

    return {"labels": merged_labels}, changes


def reconcile_catalog_files(
    default_path: Path,
    yml_path: Path,
    baseline_path: Path,
    auto_merge: bool = True,
) -> dict:
    """Reconcile the bundled default catalog into the operator's copy.

    Called at startup and from the reload-catalog admin endpoint.
    Returns a summary dict: {wrote, added, updated, backed_up, reason}.
    Never raises — callers log and continue on failure.
    """
    summary: dict = {"wrote": False, "added": 0, "updated": 0, "backed_up": False, "reason": ""}

    if not default_path.exists():
        summary["reason"] = f"no default at {default_path}"
        return summary

    default_bytes = default_path.read_bytes()

    # Case 1: First run — no operator file yet
    if not yml_path.exists():
        shutil.copy(default_path, yml_path)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(default_path, baseline_path)
        summary["reason"] = "first-run: copied default to operator file and baseline"
        logger.info("First-run: copied %s → %s and %s", default_path, yml_path, baseline_path)
        return summary

    # Case 2: Operator file exists but no baseline (upgrading to this feature for the first time)
    if not baseline_path.exists():
        if auto_merge:
            with yml_path.open() as fh:
                op_doc = yaml.safe_load(fh) or {}
            with default_path.open() as fh:
                new_doc = yaml.safe_load(fh) or {}

            op_ids = {
                e["id"] for e in (op_doc.get("labels") or []) if isinstance(e, dict) and "id" in e
            }
            new_entries = [
                e
                for e in (new_doc.get("labels") or [])
                if isinstance(e, dict) and "id" in e and e["id"] not in op_ids
            ]

            if new_entries:
                bak = yml_path.parent / (yml_path.name + ".bak")
                shutil.copy(yml_path, bak)
                summary["backed_up"] = True
                op_doc.setdefault("labels", []).extend(new_entries)
                yml_path.write_text(yaml.safe_dump(op_doc, sort_keys=False, allow_unicode=True))
                summary["added"] = len(new_entries)
                summary["wrote"] = True
                logger.info(
                    "No-baseline transition: added %d new catalog entries. "
                    "Field-level corrections apply on the next default change. Backup: %s",
                    len(new_entries),
                    bak,
                )
            else:
                logger.info(
                    "No-baseline transition: no new catalog entries to add. "
                    "Field-level corrections will apply on the next default change."
                )
        else:
            logger.info(
                "CATALOG_AUTO_MERGE=false: no baseline present; "
                "updated default is available but not applied"
            )

        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(default_path, baseline_path)
        summary["reason"] = (
            f"no-baseline transition: {summary['added']} entries added, baseline written"
        )
        return summary

    # Case 3: Baseline exists — check whether the default has changed
    baseline_bytes = baseline_path.read_bytes()
    if default_bytes == baseline_bytes:
        summary["reason"] = "default unchanged, no-op"
        return summary

    if not auto_merge:
        logger.info("CATALOG_AUTO_MERGE=false: updated default catalog detected but not applied")
        summary["reason"] = "auto_merge disabled, update detected but not applied"
        return summary

    # Default changed — run full 3-way merge
    with yml_path.open() as fh:
        op_doc = yaml.safe_load(fh) or {}
    with baseline_path.open() as fh:
        old_doc = yaml.safe_load(fh) or {}
    with default_path.open() as fh:
        new_doc = yaml.safe_load(fh) or {}

    merged_doc, changes = merge_catalog(op_doc, old_doc, new_doc)

    added = sum(1 for c in changes if c.startswith("added "))
    updated_fields = sum(1 for c in changes if c.startswith("updated "))

    bak = yml_path.parent / (yml_path.name + ".bak")
    shutil.copy(yml_path, bak)
    summary["backed_up"] = True
    logger.info("Backed up operator labels.yml → %s", bak)

    yml_path.write_text(yaml.safe_dump(merged_doc, sort_keys=False, allow_unicode=True))
    shutil.copy(default_path, baseline_path)

    summary["wrote"] = True
    summary["added"] = added
    summary["updated"] = updated_fields
    summary["reason"] = f"merged: {added} entries added, {updated_fields} fields updated"

    for line in changes:
        logger.info("Catalog reconcile: %s", line)
    logger.info(
        "Catalog reconcile complete: %d entries added, %d fields updated",
        added,
        updated_fields,
    )

    return summary
