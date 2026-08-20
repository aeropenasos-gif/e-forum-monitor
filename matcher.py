"""
matcher.py
----------
Проверява дали даден текст (пост/коментар) съдържа някоя от ключовите
фрази или идиоматичните асоциации, дефинирани в config.yaml.

Съзнателно е държан прост и без "магия" — за да е лесно да се обясни
на неопитен с код човек как точно работи съвпадението:

    1. Всяка фраза от config.yaml се превръща в regex с "\\b" (word
       boundary) в началото и края, за да не съвпада вътре в други думи
       (напр. "family app" да не съвпадне в "familyappliance").
    2. Търсенето е без значение на главни/малки букви (case-insensitive),
       освен ако в config.yaml е зададено matching.case_sensitive: true.
"""

import re


def _compile_terms(keywords_cfg, case_sensitive: bool):
    """
    Връща списък от (category, phrase, compiled_regex) за всички
    фрази и идиоматични асоциации от config.yaml.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = []

    for phrase in keywords_cfg.get("phrases", []) or []:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        compiled.append(("keyword", phrase, re.compile(pattern, flags)))

    idiom_groups = keywords_cfg.get("idiom_associations", {}) or {}
    for group_name, phrases in idiom_groups.items():
        for phrase in phrases or []:
            pattern = r"\b" + re.escape(phrase) + r"\b"
            compiled.append((group_name, phrase, re.compile(pattern, flags)))

    return compiled


class Matcher:
    def __init__(self, config: dict):
        keywords_cfg = config.get("keywords", {}) or {}
        matching_cfg = config.get("matching", {}) or {}
        case_sensitive = bool(matching_cfg.get("case_sensitive", False))
        self._terms = _compile_terms(keywords_cfg, case_sensitive)

    def find_matches(self, text: str):
        """
        Връща списък от съвпадения във формат:
            [{"category": "...", "phrase": "..."}, ...]
        Празен списък, ако няма съвпадение.
        """
        if not text:
            return []

        matches = []
        seen_phrases = set()
        for category, phrase, regex in self._terms:
            if phrase in seen_phrases:
                continue
            if regex.search(text):
                matches.append({"category": category, "phrase": phrase})
                seen_phrases.add(phrase)
        return matches

    def build_search_terms(self):
        """
        Връща плоския списък от всички фрази (без категория) —
        използва се от site_search модула за DuckDuckGo заявките.
        """
        return [phrase for _category, phrase, _regex in self._terms]
