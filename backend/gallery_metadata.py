"""Presentation-safe metadata exposed by the Video Gallery API."""

import re


def _seo_context_from_job(job):
    saved = job.get("seo_story_context")
    if saved:
        return saved
    lines = [job.get("initial_prompt") or job.get("premise") or ""]
    for index, scene in enumerate(job.get("scenes") or [], start=1):
        number = scene.get("scene_number") or index
        title = scene.get("title") or f"Adegan {number}"
        detail = scene.get("action_summary") or scene.get("prompt") or ""
        lines.append(f"Adegan {number} — {title}: {detail}")
    return "\n".join(item for item in lines if item)[:16000]


def _localization_from_job(job):
    language = job.get("target_lang") or ""
    country = job.get("target_country") or ""
    if language and country:
        return language, country

    scenes = job.get("scenes") or []
    corpus = "\n".join([
        str(job.get("title") or ""),
        str(job.get("initial_prompt") or ""),
        *(str(scene.get("title") or "") + " " + str(scene.get("prompt") or "") for scene in scenes),
    ])
    # Recover localization for legacy jobs written before these fields were persisted.
    if re.search(r"[\uac00-\ud7af]", corpus):
        return language or "Korea", country or "South Korea"
    if re.search(r"[\u3040-\u30ff]", corpus):
        return language or "Jepang", country or "Japan"
    if re.search(r"[\u0600-\u06ff]", corpus):
        return language or "Arab", country or ""
    if re.search(r"[\u0400-\u04ff]", corpus):
        return language or "Rusia", country or "Russia"
    return language, country


def gallery_metadata(job):
    target_lang, target_country = _localization_from_job(job)
    return {
        "total_duration": job.get("total_duration"),
        "output_size_bytes": job.get("output_size_bytes"),
        "output_size_display": job.get("output_size_display"),
        "processing_seconds": job.get("processing_seconds"),
        "processing_duration": job.get("processing_duration"),
        "initial_prompt": job.get("initial_prompt") or job.get("premise") or "",
        "seo_story_context": _seo_context_from_job(job),
        "seo_storyboard": job.get("seo_storyboard") or None,
        "target_lang": target_lang,
        "target_country": target_country,
        "postproduction_qc": job.get("postproduction_qc") or None,
        "postproduction_qc_url": job.get("postproduction_qc_url") or None,
    }
