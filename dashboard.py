#!/usr/bin/env python3
"""
dashboard.py
------------
Генерира dashboard.html — самостоятелна HTML страница с релевантните
нишки от последните N часа (по подразбиране 24ч), подредени по "сила
на съвпадение".

ВАЖНО — какво прави и какво НЕ прави този скрипт:
    - Само ЧЕТЕ state/recent_matches.json (записан от main.py) и
      генерира статичен HTML файл, който отваряш локално в браузър.
    - НЕ пише, НЕ превежда и НЕ публикува нищо в никакъв форум.
    - Изборът на теми, писането на чернова и публикуването остават
      изцяло твое ръчно действие — виж README.md, раздел
      "Табло за преглед + чернови".

Пускане:
    python3 dashboard.py
    (после отвори dashboard.html в браузъра — или виж run_dashboard.sh
    / run_dashboard.command / run_dashboard.bat за пускане с едно
    кликване, което го отваря автоматично)
"""

import html
import sys
import time
import webbrowser

import yaml

import recent_matches


def load_config(path="config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _relative_time_bg(seconds_ago: float) -> str:
    seconds_ago = max(0, int(seconds_ago))
    if seconds_ago < 60:
        return "преди по-малко от минута"
    minutes = seconds_ago // 60
    if minutes < 60:
        return f"преди {minutes} мин."
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if remaining_minutes:
        return f"преди {hours} ч. {remaining_minutes} мин."
    return f"преди {hours} ч."


def _score(entry: dict, weights: dict, oldest_ts: float, newest_ts: float) -> float:
    matches = entry.get("matches", []) or []
    keyword_hits = sum(1 for m in matches if m.get("category") == "keyword")
    idiom_hits = sum(1 for m in matches if m.get("category") != "keyword")

    score = (
        keyword_hits * float(weights.get("per_keyword_match", 1.0))
        + idiom_hits * float(weights.get("per_idiom_match", 1.5))
    )

    recency_bonus_max = float(weights.get("recency_bonus_max", 2.0))
    span = max(newest_ts - oldest_ts, 1.0)
    created_at = entry.get("created_at") or entry.get("found_at") or oldest_ts
    recency_fraction = (created_at - oldest_ts) / span
    score += recency_fraction * recency_bonus_max

    return round(score, 2)


# --- Категорийни цветове за източниците (fixed order, по dataviz палитра) ---
SOURCE_COLORS = {
    "reddit": {"light": "#2a78d6", "dark": "#3987e5", "label": "Reddit"},
    "site_search": {"light": "#eb6834", "dark": "#d95926", "label": "Mumsnet / TSR"},
}

# Сила на съвпадение -> степен от sequential blue ramp (light / dark)
SCORE_STEPS = [
    {"min": 0.0, "light": "#cde2fb", "dark": "#184f95", "text_light": "#0b0b0b", "text_dark": "#ffffff"},
    {"min": 1.5, "light": "#9ec5f4", "dark": "#1c5cab", "text_light": "#0b0b0b", "text_dark": "#ffffff"},
    {"min": 3.0, "light": "#5598e7", "dark": "#256abf", "text_light": "#0b0b0b", "text_dark": "#ffffff"},
    {"min": 4.5, "light": "#2a78d6", "dark": "#3987e5", "text_light": "#ffffff", "text_dark": "#0b0b0b"},
]


def _score_step(score: float) -> dict:
    step = SCORE_STEPS[0]
    for candidate in SCORE_STEPS:
        if score >= candidate["min"]:
            step = candidate
    return step


def _highlight(text: str, matches: list) -> str:
    escaped = html.escape(text or "")
    phrases = sorted({m["phrase"] for m in matches}, key=len, reverse=True)
    for phrase in phrases:
        escaped_phrase = html.escape(phrase)
        # Просто, регистронезависимо подчертаване за визуален преглед
        # (не е regex word-boundary като в matcher.py — тук е само за
        # визуално ориентиране в таблото, не за самата логика на съвпадение).
        idx = escaped.lower().find(escaped_phrase.lower())
        if idx != -1:
            escaped = (
                escaped[:idx]
                + f"<mark>{escaped[idx:idx + len(escaped_phrase)]}</mark>"
                + escaped[idx + len(escaped_phrase):]
            )
    return escaped


def render_html(entries_with_scores: list, window_hours: float, generated_at: float) -> str:
    total = len(entries_with_scores)
    reddit_count = sum(1 for e, _ in entries_with_scores if e.get("source_name") == "reddit")
    site_search_count = total - reddit_count
    approx_count = sum(1 for e, _ in entries_with_scores if e.get("created_at_is_approximate"))

    rows_html = []
    for rank, (entry, score) in enumerate(entries_with_scores, start=1):
        source_name = entry.get("source_name", "site_search")
        source_meta = SOURCE_COLORS.get(source_name, SOURCE_COLORS["site_search"])
        source_label = html.escape(entry.get("source_label") or source_meta["label"])

        created_at = entry.get("created_at") or entry.get("found_at") or generated_at
        approx_marker = " *" if entry.get("created_at_is_approximate") else ""
        time_str = _relative_time_bg(generated_at - created_at) + approx_marker

        matches = entry.get("matches", []) or []
        unique_phrases = sorted({m["phrase"] for m in matches})
        phrase_chips = "".join(
            f'<span class="chip">{html.escape(phrase)}</span>' for phrase in unique_phrases
        )

        snippet = _highlight(entry.get("text", "")[:400], matches)
        step = _score_step(score)
        url = html.escape(entry.get("url") or "#")

        rows_html.append(
            f"""
            <tr>
              <td class="col-rank">{rank}</td>
              <td>
                <span class="score-badge"
                      style="--step-light:{step['light']}; --step-dark:{step['dark']};
                             --step-text-light:{step['text_light']}; --step-text-dark:{step['text_dark']};">
                  {score:.1f}
                </span>
              </td>
              <td>
                <span class="source-tag"
                      style="--src-light:{source_meta['light']}; --src-dark:{source_meta['dark']};">
                  {source_label}
                </span>
              </td>
              <td class="col-time">{time_str}</td>
              <td>{phrase_chips}</td>
              <td class="col-snippet">{snippet}</td>
              <td><a class="open-link" href="{url}" target="_blank" rel="noopener">Отвори ↗</a></td>
            </tr>
            """
        )

    rows_joined = "\n".join(rows_html) if rows_html else (
        '<tr><td colspan="7" class="empty-state">'
        "Няма релевантни съвпадения в избрания прозорец. "
        "Пусни GitHub Actions run-а (или изчакай следващия цикъл) и опитай отново."
        "</td></tr>"
    )

    generated_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(generated_at))

    return f"""<!DOCTYPE html>
<html lang="bg">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Eligna Forum Monitor — Табло за преглед</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1:      #fcfcfb;
    --page-plane:     #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --gridline:       #e1e0d9;
    --border:         rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      color-scheme: dark;
      --surface-1:      #1a1a19;
      --page-plane:     #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted:     #898781;
      --gridline:       #2c2c2a;
      --border:         rgba(255,255,255,0.10);
    }}
  }}

  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--page-plane);
    color: var(--text-primary);
  }}
  .viz-root {{
    max-width: 1180px;
    margin: 0 auto;
    padding: 32px 24px 64px;
  }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .subtitle {{ color: var(--text-secondary); font-size: 13px; margin: 0 0 24px; }}

  .callout {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 13px;
    color: var(--text-secondary);
    margin-bottom: 24px;
    line-height: 1.5;
  }}
  .callout strong {{ color: var(--text-primary); }}

  .stat-row {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 24px;
  }}
  .stat-tile {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
  }}
  .stat-tile .value {{
    font-size: 24px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }}
  .stat-tile .label {{
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 2px;
  }}

  .legend {{
    display: flex;
    gap: 16px;
    align-items: center;
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 12px;
  }}
  .legend-dot {{
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 6px;
    background: var(--dot-light);
  }}
  @media (prefers-color-scheme: dark) {{
    .legend-dot {{ background: var(--dot-dark); }}
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    font-size: 13px;
  }}
  th {{
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-muted);
    padding: 10px 12px;
    border-bottom: 1px solid var(--gridline);
  }}
  td {{
    padding: 10px 12px;
    border-bottom: 1px solid var(--gridline);
    vertical-align: top;
    color: var(--text-primary);
  }}
  tr:last-child td {{ border-bottom: none; }}
  .col-rank {{ color: var(--text-muted); font-variant-numeric: tabular-nums; width: 28px; }}
  .col-time {{ color: var(--text-secondary); white-space: nowrap; }}
  .col-snippet {{ max-width: 420px; color: var(--text-secondary); }}
  .empty-state {{ text-align: center; color: var(--text-muted); padding: 32px; }}

  mark {{
    background: #cde2fb;
    color: #0b0b0b;
    border-radius: 3px;
    padding: 0 2px;
  }}
  @media (prefers-color-scheme: dark) {{
    mark {{ background: #184f95; color: #ffffff; }}
  }}

  .chip {{
    display: inline-block;
    font-size: 11px;
    background: var(--page-plane);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    border-radius: 999px;
    padding: 2px 8px;
    margin: 2px 4px 2px 0;
    white-space: nowrap;
  }}

  .score-badge {{
    display: inline-block;
    min-width: 32px;
    text-align: center;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    border-radius: 6px;
    padding: 3px 8px;
    background: var(--step-light);
    color: var(--step-text-light);
  }}
  @media (prefers-color-scheme: dark) {{
    .score-badge {{ background: var(--step-dark); color: var(--step-text-dark); }}
  }}

  .source-tag {{
    display: inline-block;
    font-size: 12px;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 6px;
    color: #ffffff;
    background: var(--src-light);
  }}
  @media (prefers-color-scheme: dark) {{
    .source-tag {{ background: var(--src-dark); }}
  }}

  .open-link {{
    color: #2a78d6;
    text-decoration: none;
    font-weight: 500;
    white-space: nowrap;
  }}
  @media (prefers-color-scheme: dark) {{
    .open-link {{ color: #3987e5; }}
  }}

  footer {{
    margin-top: 24px;
    font-size: 12px;
    color: var(--text-muted);
  }}
</style>
</head>
<body>
<div class="viz-root">
  <h1>Eligna Forum Monitor — Табло за преглед</h1>
  <p class="subtitle">
    Последните {window_hours:g} часа · генерирано на {generated_str} ·
    {total} релевантни нишки
  </p>

  <div class="callout">
    <strong>Как да ползваш това табло:</strong> избери нишка от списъка,
    отвори линка за контекст, после занеси линка + откъса в чат с Claude
    (skill „reddit-uk-translator“), за да получиш чернова на отговор на
    английски + превод на български за проверка. <strong>Таблото не пише
    и не публикува нищо</strong> — финалната редакция и публикуването
    остават изцяло твое ръчно действие, с твоя собствена преценка.
  </div>

  <div class="stat-row">
    <div class="stat-tile">
      <div class="value">{total}</div>
      <div class="label">Общо релевантни нишки</div>
    </div>
    <div class="stat-tile">
      <div class="value">{reddit_count}</div>
      <div class="label">От Reddit</div>
    </div>
    <div class="stat-tile">
      <div class="value">{site_search_count}</div>
      <div class="label">От Mumsnet / The Student Room</div>
    </div>
    <div class="stat-tile">
      <div class="value">{approx_count}</div>
      <div class="label">С приблизително време (* виж по-долу)</div>
    </div>
  </div>

  <div class="legend">
    <span><span class="legend-dot" style="--dot-light:#2a78d6; --dot-dark:#3987e5;"></span>Reddit</span>
    <span><span class="legend-dot" style="--dot-light:#eb6834; --dot-dark:#d95926;"></span>Mumsnet / The Student Room</span>
    <span>* = приблизително време (виж README.md, раздел "Ограничения")</span>
  </div>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Сила</th>
        <th>Източник</th>
        <th>Кога</th>
        <th>Съвпадения</th>
        <th>Откъс</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {rows_joined}
    </tbody>
  </table>

  <footer>
    Генерирано локално от dashboard.py — нищо от тук не се изпраща никъде автоматично.
  </footer>
</div>
</body>
</html>
"""


def main() -> int:
    config = load_config()
    dashboard_cfg = config.get("dashboard", {}) or {}
    run_cfg = config.get("run", {}) or {}

    window_hours = float(dashboard_cfg.get("window_hours", 24))
    output_file = dashboard_cfg.get("output_file", "dashboard.html")
    weights = dashboard_cfg.get("score_weights", {}) or {}
    recent_matches_path = run_cfg.get("recent_matches_file", "state/recent_matches.json")

    entries = recent_matches.load_recent(recent_matches_path, within_hours=window_hours)

    now = time.time()
    if entries:
        timestamps = [e.get("created_at") or e.get("found_at") or now for e in entries]
        oldest_ts, newest_ts = min(timestamps), max(timestamps)
    else:
        oldest_ts, newest_ts = now, now

    scored = [(e, _score(e, weights, oldest_ts, newest_ts)) for e in entries]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    html_content = render_html(scored, window_hours, now)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[dashboard] Записан {output_file} с {len(scored)} нишки от последните {window_hours:g}ч.")

    if "--no-open" not in sys.argv:
        try:
            webbrowser.open(f"file://{__import__('os').path.abspath(output_file)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[dashboard] Не успях да отворя браузъра автоматично: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
