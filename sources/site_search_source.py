"""
site_search_source.py
----------------------
ПРЕПРОЕКТИРАН (22.08.2026) — виж Forum-monitor-bot-setup.md за пълния
контекст на решението. Кратко резюме:

Старата версия правеше keyword search през DuckDuckGo (site:domain
"фраза") за Mumsnet и The Student Room. Проверка на robots.txt показа,
че това е несъвместимо с изрично заявените правила на самите сайтове:

  - Mumsnet: "Disallow: /search?query=*" и "Disallow: /api/*" за всички
    ботове (User-agent: *). Няма съответстващ на правилата начин да се
    прави keyword search там автоматично.
  - The Student Room: "Disallow: /search/*" също за всички ботове, НО
    с една единствена, много точна изключение:
        Allow: /search.php?filter[type]=thread&sortby=date+desc&filter[date]=[NOW-1DAY+TO+*]
    т.е. изрично е позволено да се тегли списък с НОВИ нишки от
    последните 24 часа (без свободен текст по ключова дума).
  - DuckDuckGo: html.duckduckgo.com/html/, на който разчиташе старият
    код, също е "Disallow: /html" в собствения robots.txt на DuckDuckGo.

Затова:
  - Mumsnet вече е ИЗКЛЮЧЕН (enabled: false в config.yaml) — не съществува
    съответстващ на техните правила начин да теглим ключово търсене
    оттам с автоматизиран скрипт. Ако в бъдеще се уреди партньорски/
    платен достъп, тук може да се добави съответна имплементация.
  - The Student Room вече НЕ се пита с ключова фраза през DuckDuckGo.
    Вместо това теглим широкия, изрично позволен списък с нови нишки
    (endpoint по-долу) и прилагаме ЛОКАЛНО нашия matcher.py върху
    заглавие + форум — точно както прави reddit_source.py: тегли
    широко, филтрира локално. Това е едновременно по-съобразено с
    правилата И по-бързо (сървърно рендиран HTML, без блокиране,
    без нужда от JavaScript, обновява се на минути, не на часове).
"""

import re
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; EForumMonitor/1.0; "
        "+https://github.com/aeropenasos-gif/e-forum-monitor)"
    )
}

# Изрично позволеният endpoint в robots.txt на The Student Room:
# Allow: /search.php?filter[type]=thread&sortby=date+desc&filter[date]=[NOW-1DAY+TO+*]
TSR_RECENT_THREADS_URL = "https://www.thestudentroom.co.uk/search.php"
TSR_RECENT_THREADS_PARAMS = {
    "filter[type]": "thread",
    "sortby": "date desc",
    "filter[date]": "[NOW-1DAY TO *]",
}

_RELATIVE_TIME_RE = re.compile(
    r"(\d+)\s+(second|minute|hour|day)s?\s+ago", re.IGNORECASE
)


def _parse_relative_time(text: str, now: datetime):
    """
    Превръща "6 minutes ago" / "2 hours ago" / "1 day ago" в приблизителен
    datetime. The Student Room не дава абсолютен timestamp в HTML-а на
    списъка (само относително време), затова това си остава приблизително
    — маркираме го изрично с created_at_is_approximate=True надолу.
    Връща None, ако текстът не се разпознае (напр. "Yesterday, 14:32" —
    рядък edge case при по-стари нишки на по-късни страници).
    """
    match = _RELATIVE_TIME_RE.search(text or "")
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    delta = {
        "second": timedelta(seconds=amount),
        "minute": timedelta(minutes=amount),
        "hour": timedelta(hours=amount),
        "day": timedelta(days=amount),
    }[unit]
    return now - delta


def _fetch_tsr_recent_threads_page(page: int):
    """
    Тегли ЕДНА страница (20 нишки) от изрично позволения "нови нишки от
    последните 24ч" списък на The Student Room. Връща списък от речници
    със суров текст за локално сравнение с ключовите думи/идиоми.
    """
    params = dict(TSR_RECENT_THREADS_PARAMS)
    if page > 1:
        params["page"] = page

    try:
        response = requests.get(
            TSR_RECENT_THREADS_URL,
            params=params,
            headers=HEADERS,
            timeout=20,
        )
        print(
            f"[site_search][DEBUG] TSR recent-threads page={page} "
            f"status={response.status_code} resp_len={len(response.text)}"
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[site_search] Грешка при заявка към The Student Room: {exc}")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    thread_links = soup.select('a[href^="showthread.php?t="]')
    print(f"[site_search][DEBUG] TSR намерени нишки на страница {page}: {len(thread_links)}")

    now = datetime.now(timezone.utc)
    results = []
    for link in thread_links:
        row = link.find_parent("tr")
        if row is None:
            continue

        thread_id = link.get("href", "")
        title = link.get_text(strip=True)

        forum_link = row.select_one('a[href^="forumdisplay.php?f="]')
        forum_name = forum_link.get_text(strip=True) if forum_link else ""

        # Клетката с "smallfont" съдържа последния постващ + относително
        # време (напр. "started by: X" е в друга клетка; тук е "last post").
        time_cell = row.select_one("td.smallfont, td.alt2.smallfont")
        relative_time_text = time_cell.get_text(" ", strip=True) if time_cell else ""
        approx_time = _parse_relative_time(relative_time_text, now)

        thread_url = f"https://www.thestudentroom.co.uk/{thread_id}"
        results.append(
            {
                "id": thread_url,
                "url": thread_url,
                "text": f"{title}\n{forum_name}",
                "source_label": "The Student Room",
                "created_at": (approx_time or now).timestamp(),
                # Това е час на последна активност (не на създаване на
                # нишката), и е приблизителен (само относителен текст в
                # HTML-а, не абсолютен timestamp) — затова изрично true.
                "created_at_is_approximate": True,
            }
        )
    return results


def fetch_new_items(site_search_cfg: dict, search_terms):
    """
    Генератор за "best effort" форуми без официално API. Единственият
    активен източник тук в момента е The Student Room (виж модулния
    docstring по-горе защо Mumsnet е изключен и защо вече не се ползва
    DuckDuckGo).

    `search_terms` се приема заради обратна съвместимост с main.py, но
    вече НЕ се използва — не строим keyword-заявка към трета страна;
    вместо това връщаме широк списък от нови нишки, а `matcher.py`
    прави съвпадението локално (същия принцип като при reddit_source.py).
    """
    studentroom_cfg = (site_search_cfg or {}).get("studentroom", {}) or {}
    mumsnet_cfg = (site_search_cfg or {}).get("mumsnet", {}) or {}

    if mumsnet_cfg.get("enabled"):
        print(
            "[site_search] ПРЕДУПРЕЖДЕНИЕ: mumsnet.enabled=true в config.yaml, "
            "но Mumsnet's robots.txt забранява /search и /api/ за автоматизирани "
            "клиенти — няма имплементация, която да спазва това правило. "
            "Пропускам Mumsnet. Виж Forum-monitor-bot-setup.md, актуализация "
            "22.08.2026."
        )

    if not studentroom_cfg.get("enabled"):
        return

    pages_per_cycle = int(studentroom_cfg.get("pages_per_cycle", 2))
    for page in range(1, pages_per_cycle + 1):
        for item in _fetch_tsr_recent_threads_page(page):
            yield item
