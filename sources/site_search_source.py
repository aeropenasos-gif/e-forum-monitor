"""
site_search_source.py
----------------------
"Best effort" мониторинг на форуми, които НЯМАТ публично API
(в момента: Mumsnet, The Student Room).

Директно "чукане" на техните собствени search-страници е ненадеждно,
защото са силно динамични (JavaScript) и подлежат на чести промени.
Затова използваме DuckDuckGo HTML търсене (https://html.duckduckgo.com/html/)
с оператор site:<domain>, което е стабилно за просто читане на HTML и
не изисква API ключ.

ВАЖНО ограничение (обяснено и в README.md):
    Резултатите зависят от това кога DuckDuckGo е индексирал дадена
    страница — това може да отнеме от няколко минути до няколко часа.
    Това НЕ е мониторинг в реално време като при Reddit API, а
    приблизителен, но полезен "best effort" сигнал.
"""

import time
import requests
from bs4 import BeautifulSoup

DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ElignaForumMonitor/1.0; "
        "+https://eligna.app)"
    )
}


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _search_duckduckgo(query: str):
    """
    Изпраща едно търсене към DuckDuckGo HTML endpoint и връща списък от
    (url, title, snippet).
    """
    try:
        response = requests.post(
            DUCKDUCKGO_HTML_URL,
            data={"q": query},
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[site_search] Грешка при заявка към DuckDuckGo: {exc}")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    results = []
    for result in soup.select(".result"):
        link_tag = result.select_one(".result__a")
        snippet_tag = result.select_one(".result__snippet")
        if not link_tag or not link_tag.get("href"):
            continue
        url = link_tag["href"]
        title = link_tag.get_text(strip=True)
        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
        results.append((url, title, snippet))
    return results


def fetch_new_items(site_search_cfg: dict, search_terms):
    """
    Генератор, който за всеки активен сайт (mumsnet, studentroom, ...)
    прави групирани DuckDuckGo заявки за всички ключови фрази и връща:
        {
            "id": "<url на резултата>",
            "url": "<url>",
            "text": "<заглавие + snippet>",
            "source_label": "<Mumsnet / The Student Room>",
        }
    """
    if not search_terms:
        return

    batch_size = int(site_search_cfg.get("batch_size", 8))
    delay = float(site_search_cfg.get("delay_between_requests", 1.5))

    sites = {
        key: value
        for key, value in site_search_cfg.items()
        if isinstance(value, dict) and value.get("enabled")
    }

    for _site_key, site_cfg in sites.items():
        domain = site_cfg.get("domain")
        label = site_cfg.get("label", domain)
        if not domain:
            continue

        for batch in _chunk(search_terms, batch_size):
            quoted_terms = [f'"{term}"' for term in batch]
            query = f"site:{domain} (" + " OR ".join(quoted_terms) + ")"
            results = _search_duckduckgo(query)

            for url, title, snippet in results:
                yield {
                    "id": url,
                    "url": url,
                    "text": f"{title}\n{snippet}",
                    "source_label": label,
                    # DuckDuckGo не ни дава точен момент на публикуване —
                    # използваме момента на намиране като приблизителна
                    # стойност и го отбелязваме изрично като такава, за
                    # да не подвежда таблото за "последните 24 часа".
                    "created_at": time.time(),
                    "created_at_is_approximate": True,
                }

            time.sleep(delay)
