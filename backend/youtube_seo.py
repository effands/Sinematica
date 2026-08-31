"""Formatting guards for readable, theme-aware YouTube SEO titles and marketing kits."""

from typing import Any, Dict, List, Optional
import re


_GENERIC_WORDS = {
    "dan", "atau", "yang", "untuk", "dengan", "dari", "ke", "di", "vs",
    "the", "and", "for", "with", "film", "video", "movie", "short", "shorts",
    "pertarungan", "epik", "epic", "kisah", "cerita", "terbaik", "terbaru",
}


def theme_hashtags(theme: str, limit: int = 2) -> List[str]:
    # Support alphanumeric and international characters (e.g. Hangul, Hanzi, Arabic, Latin)
    tokens = re.findall(r"[\w]+", str(theme or ""))
    selected = []
    seen = set()
    for token in tokens:
        lowered = token.lower()
        if len(token) < 2 or lowered in _GENERIC_WORDS or lowered in seen:
            continue
        seen.add(lowered)
        # Preserve original casing for non-ascii or capitalize first letter for latin
        tag_text = token if not token[0].isascii() else token[0].upper() + token[1:]
        selected.append("#" + tag_text)
        if len(selected) >= limit:
            break
    return selected or ["#FilmAI", "#ShortFilm"]


def _naturalize_shouting_title(title: str) -> str:
    letters = [char for char in title if char.isalpha()]
    if letters and sum(char.isupper() for char in letters) / len(letters) >= 0.7:
        title = title.lower().title()
        title = re.sub(r"\bVs\b", "vs", title)
        for word in ("AI", "SEO", "POV", "ASMR", "UGC"):
            title = re.sub(rf"\b{word.title()}\b", word, title)
        title = re.sub(r"\bYoutube\b", "YouTube", title)
    return title.strip()


def normalize_seo_titles(titles, theme: str) -> List[str]:
    fallback_tags = theme_hashtags(theme)
    normalized = []
    for raw in titles or []:
        title = _naturalize_shouting_title(str(raw or "").strip())
        if not title:
            continue
        if not re.findall(r"(?<!\w)#[\w]+", title):
            title = f"{title.rstrip(' -|')} {' '.join(fallback_tags)}"
        normalized.append(title.strip())
    if not normalized:
        clean_theme = (theme or "Film AI Sinematik").strip()
        tags_suffix = " ".join(fallback_tags)
        normalized = [
            f"{clean_theme} - Kisah Paling Menegangkan & Spektakuler {tags_suffix}",
            f"Saksikan {clean_theme} - Film AI Sinematik Epik {tags_suffix}",
            f"{clean_theme} (Official AI Short Film) {tags_suffix}",
        ]
    return normalized


def _extract_thumbnail_prompt(raw: Dict[str, Any], film_title: str, premise: str) -> str:
    """Extract or generate a high-impact 16:9 English thumbnail prompt."""
    candidates = [
        "thumbnail_prompt", "thumbnailPrompt", "thumbnail",
        "prompt_thumbnail", "thumbnail_image_prompt", "image_prompt",
        "thumbnail_description", "thumbnail_concept", "thumbnail_idea",
        "cover_prompt", "cover_image_prompt", "prompt"
    ]
    for key in candidates:
        val = raw.get(key)
        if isinstance(val, dict):
            val = val.get("prompt") or val.get("description") or val.get("text") or ""
        if isinstance(val, list):
            val = " ".join(str(v).strip() for v in val if str(v).strip())
        if val and isinstance(val, str) and val.strip() and val.strip() != "-":
            return val.strip()

    title_clean = film_title or "Cinematic Film"
    desc_snippet = (premise or title_clean)[:120].strip()
    return (
        f"High-impact 16:9 YouTube video thumbnail for '{title_clean}', featuring {desc_snippet}, "
        f"dramatic cinematic lighting, volumetric glowing rays, highly expressive detailed main character, "
        f"bold glowing cinematic typography, ultra-sharp 8k resolution, photorealistic masterpiece, eye-catching composition."
    )


def _extract_tags_csv(raw: Dict[str, Any], film_title: str, premise: str) -> str:
    """Extract or generate 10 comma-separated long-tail keyword tags."""
    candidates = [
        "tags", "tags_csv", "tagsCsv", "keywords", "long_tail_tags",
        "longTailTags", "youtube_tags", "tag_list", "tags_list",
        "key_phrases", "search_tags", "hashtags"
    ]
    extracted_tags: List[str] = []

    for key in candidates:
        val = raw.get(key)
        if not val:
            continue
        if isinstance(val, (list, tuple, set)):
            for item in val:
                s = str(item).strip().strip('"\'#[]')
                if s and s not in extracted_tags:
                    extracted_tags.append(s)
        elif isinstance(val, str) and val.strip():
            # Might be comma-separated or newline-separated
            cleaned = val.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
            tokens = [t.strip().strip('#') for t in re.split(r"[,;\n\t]+", cleaned) if t.strip()]
            for t in tokens:
                if t and t not in extracted_tags:
                    extracted_tags.append(t)
        if len(extracted_tags) >= 5:
            break

    if not extracted_tags:
        clean_title = (film_title or "Film AI Sinematik").strip()
        extracted_tags = [
            clean_title,
            f"{clean_title} full video",
            f"{clean_title} official story",
            f"{clean_title} animated film",
            "ai film animation",
            "cinematic ai video",
            "google flow video generator",
            "gemini ai animation",
            "short film ai 2026",
            "trending youtube viral"
        ]

    # Ensure clean formatting
    return ", ".join(extracted_tags[:15])


def normalize_youtube_seo_kit(data: Optional[Dict[str, Any]], film_title: str = "", premise: str = "") -> Dict[str, Any]:
    """Ensure YouTube SEO Kit is 100% complete with normalized titles, description, thumbnail prompt, and tags."""
    raw = data or {}
    title_clean = (film_title or raw.get("film_title") or "Film AI Sinematik").strip()
    premise_clean = (premise or raw.get("premise") or title_clean).strip()

    raw_titles = raw.get("titles") or raw.get("seo_titles") or raw.get("title_options") or []
    if isinstance(raw_titles, str):
        raw_titles = [raw_titles]

    normalized_titles = normalize_seo_titles(raw_titles, title_clean)

    desc = str(raw.get("description") or raw.get("video_description") or raw.get("desc") or "").strip()
    if not desc:
        hashtags = " ".join(theme_hashtags(title_clean, limit=5))
        desc = (
            f"Saksikan film sinematik {title_clean}. Sebuah kisah memukau yang menghadirkan petualangan dan emosi mendalam.\n\n"
            f"Diproduksi menggunakan teknologi AI sinematik generasi terbaru dengan visual spektakuler dan audio memukau.\n\n"
            f"👉 Jangan lupa Like, Comment, dan Subscribe untuk menikmati konten sinematik berkualitas tinggi berikutnya!\n\n"
            f"{hashtags} #FilmAI #GoogleFlow #GeminiAI"
        )

    thumbnail_prompt = _extract_thumbnail_prompt(raw, title_clean, premise_clean)
    tags_csv = _extract_tags_csv(raw, title_clean, premise_clean)

    result = {
        "titles": normalized_titles,
        "seo_titles": normalized_titles,
        "description": desc,
        "thumbnail_prompt": thumbnail_prompt,
        "thumbnailPrompt": thumbnail_prompt,
        "tags": tags_csv,
        "tags_csv": tags_csv,
        "generated_via": raw.get("generated_via") or "Sinematica AI SEO Engine"
    }
    return result
