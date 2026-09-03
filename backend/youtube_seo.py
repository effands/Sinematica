"""Formatting guards for readable, theme-aware YouTube SEO titles and marketing kits."""

from typing import Any, Dict, List, Optional
import re


_GENERIC_WORDS = {
    "dan", "atau", "yang", "untuk", "dengan", "dari", "ke", "di", "vs",
    "the", "and", "for", "with", "film", "video", "movie", "short", "shorts",
    "pertarungan", "epik", "epic", "kisah", "cerita", "terbaik", "terbaru",
}


def storyboard_to_seo_context(storyboard: Optional[Dict[str, Any]]) -> str:
    """Create a compact, factual SEO brief from the actual storyboard."""
    if not isinstance(storyboard, dict) or not storyboard:
        return ""
    lines = [
        f"Judul storyboard: {storyboard.get('film_title') or ''}",
        f"Premis: {storyboard.get('premise') or storyboard.get('source_script') or storyboard.get('theme') or ''}",
        f"Genre/gaya: {storyboard.get('genre_style') or ''}",
    ]
    brief = storyboard.get("creative_brief") or {}
    if isinstance(brief, dict):
        brief_labels = {
            "background": "Konteks brief", "result": "Tujuan konten",
            "audience": "Target audiens", "product_value": "Pain point/USP",
            "execution": "Angle/tone/CTA", "constraints": "Batasan final",
        }
        for key, label in brief_labels.items():
            value = str(brief.get(key) or "").strip()
            if value:
                lines.append(f"{label}: {value}")
    characters = storyboard.get("characters") or []
    character_bits = []
    for character in characters[:10]:
        if not isinstance(character, dict):
            continue
        name = str(character.get("name") or "").strip()
        role = str(character.get("role") or character.get("description") or "").strip()
        if name:
            character_bits.append(f"{name}: {role[:180]}")
    if character_bits:
        lines.append("Karakter nyata dalam storyboard: " + "; ".join(character_bits))

    for index, scene in enumerate((storyboard.get("scenes") or [])[:60], start=1):
        if not isinstance(scene, dict):
            continue
        number = scene.get("scene_number") or index
        title = scene.get("title") or f"Adegan {number}"
        action = scene.get("action_summary") or ""
        narration = scene.get("narration_id") or scene.get("voiceover_script") or ""
        dialogue = "; ".join(
            str(item.get("line") or "").strip()
            for item in (scene.get("dialogue") or []) if isinstance(item, dict) and item.get("line")
        )
        ending = scene.get("end_state") or ""
        detail = " ".join(filter(None, [str(action), f"Dialog: {dialogue}" if dialogue else "", f"Narasi: {narration}" if narration else "", f"Akhir: {ending}" if ending else ""]))
        lines.append(f"Adegan {number} — {title}: {detail}".strip())
    return "\n".join(line for line in lines if line.split(":", 1)[-1].strip())[:24000]


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
    normalized = []
    for raw in titles or []:
        title = _naturalize_shouting_title(str(raw or "").strip())
        if not title:
            continue
        normalized.append(title[:100].rstrip(" -|"))
    if not normalized:
        clean_theme = (theme or "Film AI Sinematik").strip()
        normalized = [
            f"{clean_theme} - Konflik yang Mengubah Segalanya",
            f"Apa yang Terjadi dalam {clean_theme}?",
            f"{clean_theme} - Sebuah Kisah tentang Pilihan dan Keberanian",
        ]
    return [title[:100].rstrip(" -|") for title in normalized[:3]]


def normalize_hashtags(raw: Dict[str, Any], theme: str) -> List[str]:
    """Keep three relevant description hashtags separate from backend keyword tags."""
    values = raw.get("hashtags") or raw.get("video_hashtags") or []
    if isinstance(values, str):
        values = re.findall(r"(?<!\w)#[\w]+", values)
    clean = []
    seen = set()
    for value in values if isinstance(values, (list, tuple, set)) else []:
        token = "#" + re.sub(r"[^\w]", "", str(value).lstrip("#"))
        if len(token) > 1 and token.lower() not in seen:
            clean.append(token)
            seen.add(token.lower())
        if len(clean) == 3:
            break
    for token in theme_hashtags(theme, limit=3):
        if token.lower() not in seen and len(clean) < 3:
            clean.append(token)
            seen.add(token.lower())
    return clean[:3]


def _extract_thumbnail_prompt(raw: Dict[str, Any], film_title: str, premise: str, aspect_ratio: str = "landscape") -> str:
    """Extract a thumbnail prompt and force it to match the rendered video's ratio."""
    target_ratio = "9:16" if str(aspect_ratio).lower() in {"portrait", "9:16", "vertical"} else "16:9"
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
            prompt = val.strip()
            wrong_ratio = "16:9" if target_ratio == "9:16" else "9:16"
            prompt = re.sub(re.escape(wrong_ratio), target_ratio, prompt, flags=re.IGNORECASE)
            if target_ratio == "9:16":
                prompt = re.sub(r"\b(?:horizontal|landscape|widescreen)\b", "vertical", prompt, flags=re.IGNORECASE)
            else:
                prompt = re.sub(r"\bvertical\b", "horizontal", prompt, flags=re.IGNORECASE)
            if target_ratio not in prompt:
                prompt = f"{prompt.rstrip(' .')}, {target_ratio} aspect ratio, composition optimized for the source video."
            return prompt

    title_clean = film_title or "Cinematic Film"
    desc_snippet = (premise or title_clean)[:120].strip()
    return (
        f"High-impact {target_ratio} YouTube video cover for '{title_clean}', featuring {desc_snippet}, "
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
    return ", ".join(extracted_tags[:12])


def normalize_youtube_seo_kit(data: Optional[Dict[str, Any]], film_title: str = "", premise: str = "", aspect_ratio: str = "landscape", storyboard: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Ensure YouTube SEO Kit is 100% complete with normalized titles, description, chapters, pinned comment, thumbnail prompt, and tags."""
    raw = data or {}
    title_clean = (film_title or raw.get("film_title") or "Film AI Sinematik").strip()
    premise_clean = (premise or raw.get("premise") or title_clean).strip()

    raw_titles = raw.get("titles") or raw.get("seo_titles") or raw.get("title_options") or []
    if isinstance(raw_titles, str):
        raw_titles = [raw_titles]

    normalized_titles = normalize_seo_titles(raw_titles, title_clean)
    hashtags = normalize_hashtags(raw, title_clean)

    # 1. Build automatic Video Chapters (Timestamps) from storyboard scenes if available
    chapters_list = []
    chapters_str = ""
    sb = storyboard or raw.get("storyboard")
    if isinstance(sb, dict) and sb.get("scenes"):
        curr_time = 0
        for s_idx, scene in enumerate(sb.get("scenes") or []):
            mins = curr_time // 60
            secs = curr_time % 60
            time_tag = f"{mins:02d}:{secs:02d}"
            s_name = (scene.get("title") or f"Adegan {s_idx + 1}").strip()
            chapters_list.append(f"{time_tag} - {s_name}")
            dur = int(scene.get("duration") or 10)
            curr_time += dur
        if chapters_list:
            chapters_str = "\n".join(chapters_list)

    desc = str(raw.get("description") or raw.get("video_description") or raw.get("desc") or "").strip()
    if not desc:
        desc = (
            f"{title_clean} menghadirkan {premise_clean}.\n"
            f"Ikuti konflik utama dan keputusan yang mengubah perjalanan para karakternya.\n\n"
            f"Tonton sampai akhir, lalu bagikan pendapatmu tentang momen yang paling berkesan.\n\n"
            f"{' '.join(hashtags)}"
        )
    elif not re.findall(r"(?<!\w)#[\w]+", desc):
        desc = f"{desc.rstrip()}\n\n{' '.join(hashtags)}"

    # Append Chapters into description if not already present
    if chapters_str and "00:00" not in desc:
        desc = f"{desc.rstrip()}\n\n⏱️ DAFTAR BABAK (CHAPTERS):\n{chapters_str}"

    pinned_comment = str(raw.get("pinned_comment") or "").strip()
    if not pinned_comment:
        pinned_comment = f"💬 Menurut kamu, apa momen atau keputusan paling berkesan di film '{title_clean}'? Tulis pendapatmu di kolom komentar ya! 👇"

    thumbnail_ratio = "9:16" if str(aspect_ratio).lower() in {"portrait", "9:16", "vertical"} else "16:9"
    thumbnail_prompt = _extract_thumbnail_prompt(raw, title_clean, premise_clean, aspect_ratio)
    tags_csv = _extract_tags_csv(raw, title_clean, premise_clean)

    copy_all_text = f"""=== JUDUL YOUTUBE ===
{normalized_titles[0] if normalized_titles else title_clean}

=== DESKRIPSI LENGKAP ===
{desc}

=== KOMENTAR TERSEMAT (PINNED COMMENT) ===
{pinned_comment}

=== TAGS BACKEND (PASTE KE YOUTUBE STUDIO) ===
{tags_csv}
"""

    result = {
        "titles": normalized_titles,
        "seo_titles": normalized_titles,
        "description": desc,
        "hashtags": hashtags,
        "pinned_comment": pinned_comment,
        "chapters": chapters_list,
        "chapters_text": chapters_str,
        "copy_all_text": copy_all_text.strip(),
        "thumbnail_prompt": thumbnail_prompt,
        "thumbnailPrompt": thumbnail_prompt,
        "thumbnail_aspect_ratio": thumbnail_ratio,
        "tags": tags_csv,
        "tags_csv": tags_csv,
        "target_lang": raw.get("target_lang") or "Indonesia",
        "target_country": raw.get("target_country") or "",
        "generated_via": raw.get("generated_via") or "Sinematica AI SEO Engine"
    }
    return result
