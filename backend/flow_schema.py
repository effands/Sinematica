"""Sinematica Backend — Learn Google Flow's real request shapes from its own web UI.

Flow's image endpoint is undocumented, so rather than guessing field names we watch what the
Flow website itself sends (the Chrome extension already sniffs every request) and reuse that
exact structure. Whatever the UI can do, Sinematica can then do too.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from . import settings

log = logging.getLogger("sinematica.flow_schema")

SAMPLES_FILE = settings.DATA_DIR / "flow_ui_samples.json"
LEARNED_FILE = settings.DATA_DIR / "flow_learned_schema.json"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# Keys that carry a media id but are not reference attachments.
_NON_REFERENCE_KEYS = {"projectid", "sessionid", "clientcontext", "seed", "workflowid"}

_learned_cache: Optional[Dict[str, Any]] = None


def _load(path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as ex:
        log.warning("Gagal membaca %s: %s", path.name, ex)
    return default


def _save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as ex:
        log.warning("Gagal menulis %s: %s", path.name, ex)


def _looks_like_media_ref(value: Any) -> bool:
    """True when a value is a media id, or an object/list wrapping one."""
    if isinstance(value, str):
        return bool(UUID_RE.match(value.strip()))
    if isinstance(value, dict):
        return any(_looks_like_media_ref(v) for k, v in value.items()
                   if k.lower() not in _NON_REFERENCE_KEYS)
    if isinstance(value, list):
        return bool(value) and all(_looks_like_media_ref(v) for v in value)
    return False


def _find_reference_field(request_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Locate the field the Flow UI uses to attach reference images."""
    for key, value in request_item.items():
        if key.lower() in _NON_REFERENCE_KEYS or key == "structuredPrompt":
            continue
        if isinstance(value, list) and _looks_like_media_ref(value):
            return {"style": "top_level", "field": key, "example": value[:2]}

    # The media may instead ride inside the multimodal prompt parts.
    parts = (request_item.get("structuredPrompt") or {}).get("parts")
    if isinstance(parts, list):
        media_parts = [p for p in parts if isinstance(p, dict) and "text" not in p and _looks_like_media_ref(p)]
        if media_parts:
            return {"style": "prompt_part", "field": "structuredPrompt.parts", "example": media_parts[:2]}
    return None


def record_ui_request(url: str, payload: str) -> Optional[Dict[str, Any]]:
    """Store an image-generation request made by the Flow UI and learn its shape.

    Returns the learned schema when this sample taught us something new.
    """
    if not url or not payload or not any(k in url for k in ("flowMedia", "batchGenerate", "image")):
        return None

    try:
        body = json.loads(payload)
    except Exception:
        return None  # truncated or binary sample

    requests_list = body.get("requests")
    if not isinstance(requests_list, list) or not requests_list:
        return None
    item = requests_list[0]
    if not isinstance(item, dict):
        return None

    samples = _load(SAMPLES_FILE, [])
    samples.append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "url": url, "request_item": item})
    _save(SAMPLES_FILE, samples[-20:])

    reference = _find_reference_field(item)
    if not reference:
        # A plain text-only request teaches nothing about attaching images, and recording its
        # model would overwrite a genuinely useful lesson from a reference-carrying request.
        return None

    model_name = item.get("imageModelName")

    learned = _load(LEARNED_FILE, {})
    changed = False

    if model_name and learned.get("image_model") != model_name:
        learned["image_model"] = model_name
        changed = True
        log.info("Belajar dari UI Flow: imageModelName = %s", model_name)

    if reference and learned.get("reference") != reference:
        learned["reference"] = reference
        changed = True
        log.info("Belajar dari UI Flow: gambar referensi dikirim lewat '%s' (%s)",
                 reference["field"], reference["style"])

    if changed:
        learned["learned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save(LEARNED_FILE, learned)
        global _learned_cache
        _learned_cache = learned
        try:
            from omniflash.generators.t2i import reset_reference_probing
            reset_reference_probing()   # a real schema arrived; give attaching another go
        except Exception:
            pass
        return learned
    return None


def get_learned_schema(refresh: bool = False) -> Dict[str, Any]:
    """Return whatever has been learned from the Flow UI so far."""
    global _learned_cache
    if _learned_cache is None or refresh:
        _learned_cache = _load(LEARNED_FILE, {})
    return _learned_cache


def build_reference_payload(media_ids: List[str]) -> Optional[Dict[str, Any]]:
    """Build the reference attachment exactly the way the Flow UI does it.

    Returns None when nothing has been learned yet, so callers keep their own fallbacks.
    """
    learned = get_learned_schema()
    reference = learned.get("reference")
    if not reference or not media_ids:
        return None

    example = (reference.get("example") or [None])[0]
    entries = [_shape_like(example, mid) for mid in media_ids]

    if reference["style"] == "top_level":
        return {reference["field"]: entries}
    return {"_prompt_parts": entries}


def _shape_like(example: Any, media_id: str) -> Any:
    """Rebuild `example` with a different media id, preserving its exact nesting."""
    if isinstance(example, str):
        return media_id
    if isinstance(example, dict):
        return {k: _shape_like(v, media_id) for k, v in example.items()}
    return {"mediaId": media_id}
