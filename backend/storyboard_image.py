"""Sinematica Backend — Scene storyboard sheet composed by Gemini from character sheets.

Google Flow's image endpoint has no documented way to attach reference images, so pinning a
storyboard panel to the already-generated character sheets is done with Gemini's image models
instead, which accept image inputs officially. The finished sheet is then uploaded back into
Flow so it can serve as a reference for video generation.
"""

import base64
import logging
import time
from typing import Any, Dict, List, Optional

import requests

from . import settings

log = logging.getLogger("sinematica.storyboard_image")

GENAI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Newest first; each is tried until one produces an image.
DEFAULT_IMAGE_MODELS = [
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
]

IMAGE_REQUEST_TIMEOUT = 180
MAX_REFERENCE_IMAGES = 4


def fetch_image_bytes(url_or_path: Any, timeout: int = 60) -> Optional[Dict[str, Any]]:
    """Download or read a character sheet image so it can be handed to Gemini as an input part."""
    if not url_or_path:
        return None

    if isinstance(url_or_path, bytes):
        return {"mime_type": "image/png", "data": url_or_path}

    if isinstance(url_or_path, dict) and "data" in url_or_path:
        return url_or_path

    url_str = str(url_or_path).strip()
    if not url_str:
        return None

    # Case 1: Base64 data URI
    if url_str.startswith("data:image/"):
        try:
            header, b64data = url_str.split(",", 1)
            mime = header.split(";")[0].replace("data:", "").strip()
            data = base64.b64decode(b64data)
            return {"mime_type": mime or "image/png", "data": data}
        except Exception as ex:
            log.warning("Gagal dekode data URI image: %s", ex)
            return None

    # Case 2: File URI (file://...)
    if url_str.startswith("file://"):
        try:
            from urllib.parse import unquote, urlparse
            parsed = urlparse(url_str)
            local_path = Path(unquote(parsed.path).lstrip("/"))
            if not local_path.exists():
                local_path = Path(unquote(parsed.path))
            if local_path.exists():
                mime = "image/jpeg" if local_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                return {"mime_type": mime, "data": local_path.read_bytes()}
        except Exception as ex:
            log.warning("Gagal membaca file URI %s: %s", url_str, ex)

    # Case 3: Local file path on disk (absolute or relative)
    try:
        p = Path(url_str)
        if p.exists() and p.is_file():
            mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            return {"mime_type": mime, "data": p.read_bytes()}
    except Exception:
        pass

    # Case 4: Relative storage URL like /storage/jobs/... or /data/...
    if url_str.startswith("/storage/") or url_str.startswith("/data/"):
        try:
            rel = url_str.lstrip("/")
            local_path = settings.ROOT_DIR / rel
            if local_path.exists() and local_path.is_file():
                mime = "image/jpeg" if local_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                return {"mime_type": mime, "data": local_path.read_bytes()}
            local_path_data = settings.DATA_DIR / rel.replace("data/", "")
            if local_path_data.exists() and local_path_data.is_file():
                mime = "image/jpeg" if local_path_data.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                return {"mime_type": mime, "data": local_path_data.read_bytes()}
        except Exception as ex:
            log.warning("Gagal membaca path lokal storage %s: %s", url_str, ex)

    # Case 5: HTTP/HTTPS URL
    if url_str.startswith("http://") or url_str.startswith("https://"):
        try:
            resp = requests.get(url_str, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                mime = (resp.headers.get("Content-Type") or "image/png").split(";")[0].strip()
                if not mime.startswith("image/"):
                    mime = "image/png"
                return {"mime_type": mime, "data": resp.content}
            else:
                log.warning("Character sheet HTTP fetch gagal (HTTP %s): %s", resp.status_code, url_str)
        except Exception as ex:
            log.warning("Gagal mengunduh character sheet dari URL %s: %s", url_str, ex)

    return None


MODELS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"

# Discovered once per process: which image models this API key can really use.
_discovered_models: Optional[List[str]] = None

# Set once the API key proves it has no image quota, so the dead path is skipped afterwards.
_quota_exhausted: Optional[str] = None


def discover_image_models(api_key: str) -> List[str]:
    """Ask the API which image-capable models this key actually has, instead of guessing names."""
    global _discovered_models
    if _discovered_models is not None:
        return _discovered_models

    try:
        resp = requests.get(MODELS_ENDPOINT, params={"key": api_key, "pageSize": 200}, timeout=45)
    except Exception as ex:
        log.warning("Tidak dapat mengambil daftar model Gemini: %s", ex)
        return []

    if resp.status_code != 200:
        log.warning("Daftar model Gemini ditolak (HTTP %s): %s", resp.status_code, resp.text[:200])
        return []

    found = []
    for model in resp.json().get("models") or []:
        name = str(model.get("name", "")).replace("models/", "")
        methods = model.get("supportedGenerationMethods") or []
        if "generateContent" in methods and "image" in name.lower():
            found.append(name)

    # Newest generation first: gemini-3.x before gemini-2.x, stable before preview.
    found.sort(reverse=True)
    _discovered_models = found
    if found:
        log.info("Model gambar yang tersedia pada API key ini: %s", ", ".join(found))
    else:
        log.warning("API key ini tidak punya model gambar apa pun yang mendukung generateContent.")
    return found


def _image_models(api_key: str) -> List[str]:
    cfg = settings.get_settings()
    models: List[str] = []
    configured = (cfg.get("storyboard_image_model") or "").strip()
    if configured:
        models.append(configured)
    for m in discover_image_models(api_key) + DEFAULT_IMAGE_MODELS:
        if m not in models:
            models.append(m)
    return models


def generate_storyboard_sheet(prompt: str, reference_images: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Render one storyboard sheet that reuses the faces from `reference_images`.

    Returns {"image": bytes|None, "model": str|None, "error": str|None}. The error is passed
    back rather than only logged so the caller can show the real reason instead of silently
    dropping to a weaker fallback.
    """
    global _quota_exhausted
    if _quota_exhausted:
        # Every image model already answered "quota 0" for this key; retrying just burns
        # ~18 seconds per scene for a result that cannot arrive.
        return {"image": None, "model": None, "error": _quota_exhausted}

    api_keys = settings.get_gemini_api_keys()
    if not api_keys:
        return {"image": None, "model": None, "error": "Belum ada Gemini API Key di Pengaturan"}

    parts: List[Dict[str, Any]] = [{"text": prompt}]
    for ref in reference_images[:MAX_REFERENCE_IMAGES]:
        if not ref or not ref.get("data"):
            continue
        parts.append({
            "inline_data": {
                "mime_type": ref.get("mime_type") or "image/png",
                "data": base64.b64encode(ref["data"]).decode("utf-8"),
            }
        })

    if len(parts) == 1:
        return {"image": None, "model": None, "error": "Tidak ada character sheet yang bisa dilampirkan"}

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    last_err = None
    tried = []
    quota_hits = set()
    for key in api_keys:
        for model in _image_models(key):
            tried.append(model)
            try:
                resp = requests.post(
                    GENAI_ENDPOINT.format(model=model),
                    params={"key": key},
                    json=payload,
                    timeout=IMAGE_REQUEST_TIMEOUT,
                )
            except Exception as ex:
                last_err = ex
                log.warning("Model gambar %s tidak dapat dihubungi: %s", model, ex)
                continue

            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                log.warning("Model gambar %s menolak request: %s", model, last_err)
                if resp.status_code == 429:
                    quota_hits.add(model)
                continue

            image_bytes = _extract_inline_image(resp.json())
            if image_bytes:
                log.info("Storyboard sheet berhasil dibuat via %s (%d karakter dilampirkan, %d KB).",
                         model, len(parts) - 1, len(image_bytes) // 1024)
                return {"image": image_bytes, "model": model, "error": None}

            last_err = "Respons tidak memuat gambar"
            log.warning("Model gambar %s tidak mengembalikan gambar.", model)

    log.warning("Semua model gambar Gemini gagal membuat storyboard sheet: %s", last_err)
    _dump_image_diagnostics({"models_tried": tried, "last_error": str(last_err)})

    if quota_hits and quota_hits >= set(tried):
        # Not a transient error: this key simply has no image quota. Stop trying.
        _quota_exhausted = ("Kuota model gambar API Gemini = 0 (butuh billing). "
                            "Jalur ini dilewati; storyboard dibuat lewat Google Flow.")
        log.warning("Jalur storyboard via Gemini dinonaktifkan untuk sesi ini: kuota gambar nol.")
        return {"image": None, "model": None, "error": _quota_exhausted}

    return {"image": None, "model": None,
            "error": f"{len(set(tried))} model dicoba, terakhir: {str(last_err)[:160]}"}


def _dump_image_diagnostics(payload: Dict[str, Any]) -> None:
    """Persist why the image models refused, so the cause is inspectable after the run."""
    try:
        import json as _json
        path = settings.DATA_DIR / "storyboard_image_diagnostics.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n===== " + time.strftime("%Y-%m-%d %H:%M:%S") + " =====\n")
            f.write(_json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            f.write("\n")
    except Exception as ex:
        log.warning("Gagal menulis storyboard_image_diagnostics.log: %s", ex)


def _extract_inline_image(data: Dict[str, Any]) -> Optional[bytes]:
    """Pull the first inline image out of a generateContent response."""
    for candidate in data.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                try:
                    return base64.b64decode(inline["data"])
                except Exception as ex:
                    log.warning("Gagal mendekode gambar dari Gemini: %s", ex)
    return None
