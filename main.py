#!/usr/bin/env python3
"""
main.py
-------
Оркестрира целия цикъл на проверка:

    1. Зарежда config.yaml
    2. Зарежда вече "видените" елементи (state/*.json), за да не се
       изпращат дублирани известия
    3. Тегли нови коментари/постове от Reddit
    4. Тегли (best-effort) нови резултати от Mumsnet / The Student Room
    5. Проверява всеки нов елемент срещу ключовите думи/асоциации
    6. За всяко съвпадение — изпраща Telegram съобщение веднага
    7. В края на цикъла — изпраща един обобщен e-mail с всички съвпадения
    8. Записва обновеното "видяно" състояние
    9. Добавя всяко съвпадение в state/recent_matches.json — rolling лог,
       от който dashboard.py по-късно генерира таблото "последните 24ч"

Скриптът е проектиран да НЕ гърми целия run, ако един източник (напр.
Mumsnet скрапера) се счупи — грешката се логва и останалите източници
продължават нормално.
"""

import json
import os
import sys

import yaml

import recent_matches
from matcher import Matcher
from notifier import format_match_message, send_email_digest, send_telegram
from sources import reddit_source, site_search_source


def load_config(path="config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen(path: str) -> set:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("seen_ids", []))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[main] Неуспешно зареждане на {path}: {exc}. Стартирам с празно състояние.")
        return set()


def save_seen(path: str, seen_ids: set, max_ids: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ids_list = list(seen_ids)
    if len(ids_list) > max_ids:
        ids_list = ids_list[-max_ids:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"seen_ids": ids_list}, f, ensure_ascii=False, indent=2)


def process_source(source_name, items_iterable, seen_ids, matcher, chat_id):
    """
    Обхожда items от даден източник, филтрира вече видените, проверява
    за съвпадения, изпраща Telegram веднага и връща:
        (нови_видени_id, email_batch, log_entries)

    email_batch:  списък от (item, matches) — за e-mail дигеста.
    log_entries:  списък от речници — за state/recent_matches.json,
                  който по-късно захранва dashboard.py (таблото).
    """
    new_seen_ids = set()
    email_batch = []
    log_entries = []

    try:
        for item in items_iterable:
            item_id = item["id"]
            if item_id in seen_ids or item_id in new_seen_ids:
                continue
            new_seen_ids.add(item_id)

            matches = matcher.find_matches(item.get("text", ""))
            if not matches:
                continue

            message = format_match_message(item, matches)
            sent = send_telegram(message, chat_id=chat_id)
            print(f"[main] Съвпадение ({source_name}): {item['url']} -> Telegram изпратен: {sent}")
            email_batch.append((item, matches))
            log_entries.append(
                {
                    "source_name": source_name,
                    "source_label": item.get("source_label", source_name),
                    "url": item.get("url"),
                    "text": item.get("text", ""),
                    "matches": matches,
                    "created_at": item.get("created_at"),
                    "created_at_is_approximate": item.get("created_at_is_approximate", False),
                }
            )

    except Exception as exc:  # noqa: BLE001 — не искаме един източник да събори целия run
        print(f"[main] Грешка в източник '{source_name}': {exc}")

    return new_seen_ids, email_batch, log_entries


def main() -> int:
    config = load_config()
    matcher = Matcher(config)

    run_cfg = config.get("run", {})
    max_ids = int(run_cfg.get("max_seen_ids_per_source", 5000))
    reddit_seen_path = run_cfg.get("reddit_seen_file", "state/seen_reddit.json")
    site_search_seen_path = run_cfg.get("site_search_seen_file", "state/seen_site_search.json")
    recent_matches_path = run_cfg.get("recent_matches_file", "state/recent_matches.json")
    recent_matches_keep_hours = float(run_cfg.get("recent_matches_keep_hours", 48))

    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or (
        config.get("recipients", {}).get("telegram", {}) or {}
    ).get("chat_id")

    email_to_env = os.environ.get("EMAIL_TO")
    if email_to_env:
        email_to = [addr.strip() for addr in email_to_env.split(",") if addr.strip()]
    else:
        email_to = (config.get("recipients", {}).get("email", {}) or {}).get("to", [])

    all_email_batch = []
    all_log_entries = []

    # --- Reddit ---
    reddit_cfg = config.get("reddit", {}) or {}
    if reddit_cfg.get("enabled", True):
        seen_reddit = load_seen(reddit_seen_path)
        try:
            items = reddit_source.fetch_new_items(reddit_cfg)
            new_ids, email_batch, log_entries = process_source(
                "reddit", items, seen_reddit, matcher, chat_id
            )
            seen_reddit |= new_ids
            all_email_batch.extend(email_batch)
            all_log_entries.extend(log_entries)
        finally:
            save_seen(reddit_seen_path, seen_reddit, max_ids)
    else:
        print("[main] Reddit е изключен в config.yaml — пропускам.")

    # --- Mumsnet / The Student Room (best effort) ---
    site_search_cfg = config.get("site_search", {}) or {}
    if any(
        isinstance(v, dict) and v.get("enabled")
        for v in site_search_cfg.values()
    ):
        seen_site_search = load_seen(site_search_seen_path)
        search_terms = matcher.build_search_terms()
        try:
            items = site_search_source.fetch_new_items(site_search_cfg, search_terms)
            new_ids, email_batch, log_entries = process_source(
                "site_search", items, seen_site_search, matcher, chat_id
            )
            seen_site_search |= new_ids
            all_email_batch.extend(email_batch)
            all_log_entries.extend(log_entries)
        finally:
            save_seen(site_search_seen_path, seen_site_search, max_ids)
    else:
        print("[main] Mumsnet/The Student Room са изключени в config.yaml — пропускам.")

    # --- Обобщен e-mail за всички съвпадения от този цикъл ---
    if all_email_batch:
        sent = send_email_digest(all_email_batch, email_to)
        print(f"[main] E-mail дигест с {len(all_email_batch)} съвпадения изпратен: {sent}")
    else:
        print("[main] Няма нови съвпадения в този цикъл.")

    # --- Rolling лог за dashboard.py (таблото "последните 24 часа") ---
    if all_log_entries:
        recent_matches.append_matches(
            recent_matches_path, all_log_entries, keep_hours=recent_matches_keep_hours
        )
        print(f"[main] Записани {len(all_log_entries)} нови записа в {recent_matches_path}.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
