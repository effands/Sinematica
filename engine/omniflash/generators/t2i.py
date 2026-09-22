"""Sinematica Engine — Flow Text-to-Image (T2I) Character & Concept Generator.
Ported directly from proven Affilia engine.
"""

import base64
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..config import ENDPOINTS, DEFAULT_PROJECT
from .common import build_client_context, build_generation_context

log = logging.getLogger("sinematica.engine.generators.t2i")

IMAGE_ASPECTS = {
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",   # 16:9
    "4x3":       "IMAGE_ASPECT_RATIO_4_3",          # 4:3
    "square":    "IMAGE_ASPECT_RATIO_SQUARE",        # 1:1
    "3x4":       "IMAGE_ASPECT_RATIO_3_4",           # 3:4
    "portrait":  "IMAGE_ASPECT_RATIO_PORTRAIT",      # 9:16
}

ASPECT_RATIO_MAP = {
    "portrait":  "9:16",
    "landscape": "16:9",
    "square":    "1:1",
    "4x3":       "4:3",
    "3x4":       "3:4",
}

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _encode_reference_images(paths: Optional[List[str]]) -> List[Dict[str, str]]:
    """Convert local reference image paths to base64 objects for direct extension DOM upload."""
    encoded = []
    for path_str in paths or []:
        p = Path(path_str)
        if p.is_file():
            try:
                b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
                mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                encoded.append({
                    "fileName": p.name,
                    "base64Data": b64,
                    "mimeType": mime,
                })
            except Exception as ex:
                log.warning("Gagal membaca gambar referensi %s: %s", path_str, ex)
    return encoded


def _parse_image_results(data: dict) -> List[Dict[str, str]]:
    results = []
    media_list = data.get("media", [])

    for item in media_list:
        r = {"media_id": "", "image_url": ""}
        name = item.get("name", "")
        if name:
            r["media_id"] = name

        img = item.get("image", {})
        gen = img.get("generatedImage", {})
        url = gen.get("fifeUrl", "") or gen.get("imageUri", "")
        if url:
            r["image_url"] = url
            if not r["media_id"]:
                match = UUID_RE.search(url)
                if match:
                    r["media_id"] = match.group()

        results.append(r)

    return results


# Index of the reference-image request schema Flow accepted, cached across calls.
_IMG_REF_VARIANT_IDX: Optional[int] = None

# Set once every reference shape has been refused. Retrying costs ~30s per scene for a
# result that is discarded anyway; cleared automatically when a new schema is learned.
_ALL_REF_VARIANTS_REJECTED = False


def reset_reference_probing() -> None:
    """Allow probing again, e.g. after learning the real schema from the Flow UI."""
    global _ALL_REF_VARIANTS_REJECTED, _IMG_REF_VARIANT_IDX
    _ALL_REF_VARIANTS_REJECTED = False
    _IMG_REF_VARIANT_IDX = None


def _dump_image_ref_diagnostics(payload: dict):
    """Record rejected reference-image schemas so the accepted shape can be pinned down."""
    try:
        from ..config import ROOT_DIR
        path = Path(ROOT_DIR).parent / "data" / "image_ref_diagnostics.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            f.write(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            f.write("\n")
    except Exception as ex:
        log.warning("Gagal menulis image_ref_diagnostics.log: %s", ex)


DEFAULT_IMAGE_MODEL = "GEM_PIX_2"


def _learned_image_model() -> Optional[str]:
    """The model the Flow UI itself picked, or None when nothing trustworthy is known."""
    try:
        from backend.flow_schema import get_learned_schema
        model = (get_learned_schema().get("image_model") or "").strip()
        return model or None
    except Exception:
        return None


def _learned_reference_payload(ref_ids: List[str]) -> Optional[Dict[str, Any]]:
    """Attach references the exact way Flow's own website does, once we have seen it do so."""
    try:
        from backend.flow_schema import build_reference_payload
        return build_reference_payload(ref_ids)
    except Exception:
        return None


def _build_reference_variants(ref_ids: List[str], project_id: str = None) -> List[Dict[str, Any]]:
    """Candidate ways to attach reference images to an image-generation request."""
    # Ensure we try both raw UUIDs and fully qualified project paths
    raw_media = [{"mediaId": m} for m in ref_ids if m]
    
    full_names = []
    for m in ref_ids:
        if m and not m.startswith("projects/") and project_id:
            full_names.append(f"projects/{project_id}/media/{m}")
        elif m:
            full_names.append(m)

    image_inputs_full = [{"imageInputType": "IMAGE_INPUT_TYPE_REFERENCE", "name": m} for m in full_names]
    image_inputs_raw = [{"imageInputType": "IMAGE_INPUT_TYPE_REFERENCE", "name": m} for m in ref_ids if m]
    
    variants = [
        {"imageInputs": image_inputs_full},
        {"imageInputs": image_inputs_raw},
        {"inputImages": raw_media},
        {"referenceImages": raw_media},
        {"referenceMedia": raw_media},
        {"subjectReferences": raw_media},
        {"characterReferences": raw_media},
        {"_prompt_parts": [{"mediaId": m} for m in ref_ids if m]},
        {"_prompt_parts": [{"media": {"mediaId": m}} for m in ref_ids if m]},
        {"_prompt_parts": [{"image": {"mediaId": m}} for m in ref_ids if m]},
    ]
    return variants


async def _generate_character_image_api_fallback(bridge, prompt: str, aspect: str = "landscape", project_id: str = None,
                                                instance_id: str = None, reference_media_ids: List[str] = None,
                                                seed: int = None) -> Dict[str, str]:
    """Fallback generator using direct Flow REST API."""
    global _IMG_REF_VARIANT_IDX, _ALL_REF_VARIANTS_REJECTED

    aspect_ratio = IMAGE_ASPECTS.get(aspect, "IMAGE_ASPECT_RATIO_LANDSCAPE")
    # Match Flow's per-request image-reference limit. Preserve caller priority/order.
    ref_ids = [m for m in (reference_media_ids or []) if m][:7]
    proj = project_id or "aaa1ca86-92ee-4436-b4d5-ace19f4481c9"
    endpoint = f"/v1/projects/{proj}/flowMedia:batchGenerateImages"

    def build_body(variant: Optional[Dict[str, Any]], model: str = DEFAULT_IMAGE_MODEL) -> Dict[str, Any]:
        parts = [{"text": prompt}]
        request_item = {
            "clientContext": build_client_context(project_id),
            "seed": seed if seed is not None else random.randint(100000, 999999),
            "imageAspectRatio": aspect_ratio,
            "imageModelName": model,
        }
        if variant:
            extra = dict(variant)
            prompt_parts = extra.pop("_prompt_parts", None)
            if prompt_parts:
                parts = parts + prompt_parts
            request_item.update(extra)
        request_item["structuredPrompt"] = {"parts": parts}
        return {"clientContext": build_client_context(project_id), "requests": [request_item]}

    result = None
    reference_applied = False
    reference_error = None

    learned_variant = _learned_reference_payload(ref_ids) if ref_ids else None
    if learned_variant:
        _ALL_REF_VARIANTS_REJECTED = False

    if ref_ids:
        learned_model = _learned_image_model()
        variants = []
        if learned_variant:
            variants.append((learned_variant, learned_model or DEFAULT_IMAGE_MODEL))
            if learned_model:
                variants.append((learned_variant, DEFAULT_IMAGE_MODEL))
        variants.extend((v, DEFAULT_IMAGE_MODEL) for v in _build_reference_variants(ref_ids, proj))
        
        # Deduplicate variants while keeping order
        seen_variants = []
        unique_variants = []
        for v_shape, v_mod in variants:
            key = (json.dumps(v_shape, sort_keys=True), v_mod)
            if key not in seen_variants:
                seen_variants.append(key)
                unique_variants.append((v_shape, v_mod))
        variants = unique_variants

        order = list(range(len(variants)))
        if _IMG_REF_VARIANT_IDX is not None and _IMG_REF_VARIANT_IDX < len(variants):
            order = [_IMG_REF_VARIANT_IDX] + [i for i in order if i != _IMG_REF_VARIANT_IDX]

        endpoints_to_try = [
            f"/v1/projects/{proj}/flowMedia:batchGenerateImages",
        ]

        rejected = {}
        for ep in endpoints_to_try:
            if result is not None:
                break
            for vi in order:
                shape, model = variants[vi]
                log.info('Generasi Image + %d referensi (ep: %s, varian #%d, model %s)', len(ref_ids), ep.split(':')[-1], vi, model)
                try:
                    attempt = await bridge.api_request(ep, build_body(shape, model), instance_id=instance_id, timeout=60.0)
                except Exception as ex:
                    log.warning("Varian #%d timeout/error: %s", vi, ex)
                    attempt = {"status": 500, "error": str(ex)}
                
                if attempt.get("status") == 200:
                    if _IMG_REF_VARIANT_IDX != vi:
                        _IMG_REF_VARIANT_IDX = vi
                        log.info("Skema referensi gambar %s varian #%d diterima Google Flow.", ep.split(':')[-1], vi)
                    result = attempt
                    reference_applied = True
                    _ALL_REF_VARIANTS_REJECTED = False
                    break
                key_name = f"{ep.split(':')[-1]}#var{vi}"
                rejected[key_name] = str(attempt.get("data") or attempt.get("error"))[:300]

        if result is None:
            _ALL_REF_VARIANTS_REJECTED = True
            reference_error = "; ".join(f"#{k}: {v[:120]}" for k, v in sorted(rejected.items()))
            _dump_image_ref_diagnostics({
                "endpoint": endpoint,
                "reference_ids": ref_ids,
                "rejected_variants": rejected,
            })
            raise ValueError(f"Gagal melampirkan referensi gambar karakter di Google Flow: {reference_error}")

    if result is None:
        log.info('Generasi Image Seed Karakter di Flow (Affilia Native Schema): "%s" [%s]', prompt[:50], aspect)
        result = await bridge.api_request(endpoint, build_body(None), instance_id=instance_id)

    status = result.get("status", 0)
    if status != 200:
        err = result.get("error") or result.get("data", {})
        raise ValueError(f"Gagal generate image karakter di Google Flow ({status}): {err}")

    data = result.get("data", {})
    results = _parse_image_results(data)

    if not results or not results[0].get("media_id"):
        raise ValueError("Google Flow tidak mengembalikan mediaId untuk gambar karakter.")

    # Report whether the references were actually honoured, so callers can say so truthfully
    # instead of assuming the request went through as asked.
    out = dict(results[0])
    out["reference_applied"] = reference_applied
    out["reference_count"] = len(ref_ids) if reference_applied else 0
    if reference_error:
        out["reference_error"] = reference_error
    return out


async def generate_character_image(
    bridge, prompt: str, aspect: str = "landscape", project_id: str = None,
    instance_id: str = None, reference_media_ids: List[str] = None,
    seed: int = None, reference_image_paths: List[str] = None, timeout: float = 240.0
) -> Dict[str, Any]:
    """Generate a character/concept image in Google Flow visibly via Chrome Extension DOM automation."""
    aspect_ratio_str = ASPECT_RATIO_MAP.get(aspect, "9:16" if aspect == "portrait" else "16:9")
    images_payload = _encode_reference_images(reference_image_paths)

    task_payload = {
        "kind": "image",
        "prompt": prompt,
        "storyboard": {
            "aspectRatio": aspect_ratio_str,
            "outputCount": 1,
        },
        "projectId": project_id or "",
        "seed": seed if seed is not None else random.randint(100000, 999999),
        "timeoutMs": int(timeout * 1000),
    }

    if images_payload:
        task_payload["images"] = images_payload
    if reference_media_ids:
        task_payload["referenceMediaIds"] = reference_media_ids

    log.info("Memulai generasi gambar karakter di Chrome Extension (aspect: %s, ref_images: %d)", aspect_ratio_str, len(images_payload))

    # Prefer Extension DOM automation
    if hasattr(bridge, "execute_task"):
        try:
            task_res = await bridge.execute_task(task_payload, instance_id=instance_id, timeout=timeout)
            status = task_res.get("status", 200)
            res_data = task_res.get("result") or task_res.get("data") or {}
            
            if status == 200 and res_data.get("ok", True):
                img_url = res_data.get("imageUrl") or res_data.get("url") or res_data.get("downloadImageUrl")
                media_id = res_data.get("mediaId") or res_data.get("id")
                if not media_id and img_url:
                    match = UUID_RE.search(img_url)
                    if match:
                        media_id = match.group()
                
                if img_url or media_id:
                    return {
                        "media_id": media_id or f"media_{int(time.time())}",
                        "image_url": img_url or "",
                        "download_url": img_url or "",
                        "reference_applied": len(images_payload) > 0 or bool(reference_media_ids),
                        "reference_count": len(images_payload) or len(reference_media_ids or []),
                    }
            error_msg = res_data.get("error") or task_res.get("error") or "Unknown DOM generation error"
            log.warning("Ekstensi DOM image generation mengembalikan error: %s. Mencoba fallback API...", error_msg)
        except Exception as ex:
            log.warning("Gagal eksekusi DOM image generation via extension (%s). Mencoba fallback API...", ex)

    # Secondary fallback to direct API
    return await _generate_character_image_api_fallback(
        bridge, prompt, aspect, project_id, instance_id, reference_media_ids, seed
    )
    out["reference_applied"] = reference_applied
    out["reference_count"] = len(ref_ids) if reference_applied else 0
    if reference_error:
        out["reference_error"] = reference_error
    return out
