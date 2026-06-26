from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DATA_DIR = Path(__file__).resolve().parent / "data"
_HISTORY_FILE = _DATA_DIR / "research_history.json"


def _record_identity(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("question", "")).strip(),
        str(item.get("created_at", "")).strip(),
    )


def load_persisted_history() -> list[dict[str, Any]]:
    """Load previously published history records from disk."""

    if not _HISTORY_FILE.exists():
        return []

    try:
        payload = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(payload, list):
        return []

    return [item for item in payload if isinstance(item, dict)]


def save_persisted_history(history: list[dict[str, Any]]) -> None:
    """Persist the published history records to disk atomically."""

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = _HISTORY_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(history, indent=2), encoding="utf-8")
    temp_file.replace(_HISTORY_FILE)


def merge_history_records(*history_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge history sources without duplicating published records."""

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for history in history_sets:
        for item in history:
            if not isinstance(item, dict):
                continue
            identity = _record_identity(item)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(item)
    return merged