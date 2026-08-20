"""Formatting guards for readable, theme-aware YouTube SEO titles."""

import re


_GENERIC_WORDS = {
    "dan", "atau", "yang", "untuk", "dengan", "dari", "ke", "di", "vs",
    "the", "and", "for", "with", "film", "video", "movie", "short", "shorts",
    "pertarungan", "epik", "epic", "kisah", "cerita", "terbaik", "terbaru",
}


def theme_hashtags(theme: str, limit: int = 2) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", str(theme or ""))
    selected = []
    seen = set()
    for token in tokens:
        lowered = token.lower()
        if len(token) < 3 or lowered in _GENERIC_WORDS or lowered in seen:
            continue
        seen.add(lowered)
        selected.append("#" + token[0].upper() + token[1:])
        if len(selected) >= limit:
            break
    return selected or ["#FilmAI"]


def _naturalize_shouting_title(title: str) -> str:
    letters = [char for char in title if char.isalpha()]
    if letters and sum(char.isupper() for char in letters) / len(letters) >= 0.7:
        title = title.lower().title()
        title = re.sub(r"\bVs\b", "vs", title)
        for word in ("AI", "SEO", "POV", "ASMR", "UGC"):
            title = re.sub(rf"\b{word.title()}\b", word, title)
        title = re.sub(r"\bYoutube\b", "YouTube", title)
    return title.strip()


def normalize_seo_titles(titles, theme: str) -> list[str]:
    fallback_tags = theme_hashtags(theme)
    normalized = []
    for raw in titles or []:
        title = _naturalize_shouting_title(str(raw or "").strip())
        if not title:
            continue
        if not re.findall(r"(?<!\w)#[A-Za-z0-9_]+", title):
            title = f"{title.rstrip(' -|')} {' '.join(fallback_tags)}"
        normalized.append(title.strip())
    return normalized
