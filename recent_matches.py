"""
recent_matches.py
------------------
Поддържа "rolling" лог (state/recent_matches.json) на всички намерени
съвпадения — не само за да не се дублират известия (това го прави
main.py през seen_*.json), а за да захранва dashboard.py с данни за
таблото "последните 24 часа".

Логът пази записи до `keep_hours` часа назад (по подразбиране 48ч —
двойно повече от 24ч прозореца на таблото, за да има буфер дори ако
dashboard.py се пусне малко по-късно от очакваното).
"""

import json
import os
import time


def append_matches(path: str, entries: list, keep_hours: float = 48.0) -> None:
    """
    entries: списък от речници във формат:
        {
            "source_name": "reddit" | "site_search",
            "source_label": "...",
            "url": "...",
            "text": "...",
            "matches": [{"category": "...", "phrase": "..."}, ...],
            "created_at": <epoch>,
            "created_at_is_approximate": bool,
        }
    """
    now = time.time()
    existing = _load_raw(path)

    for entry in entries:
        entry = dict(entry)
        entry["found_at"] = now
        existing.append(entry)

    cutoff = now - (keep_hours * 3600)
    trimmed = [e for e in existing if e.get("found_at", 0) >= cutoff]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def _load_raw(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[recent_matches] Неуспешно зареждане на {path}: {exc}. Стартирам с празен лог.")
        return []


def load_recent(path: str, within_hours: float = 24.0) -> list:
    """Връща записите от последните `within_hours` часа, най-новите последни."""
    now = time.time()
    cutoff = now - (within_hours * 3600)
    entries = _load_raw(path)
    recent = [e for e in entries if e.get("created_at", e.get("found_at", 0)) >= cutoff]
    recent.sort(key=lambda e: e.get("created_at", e.get("found_at", 0)))
    return recent
