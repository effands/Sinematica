"""Sinematica — Image-to-Video, Text-to-Video & Reference-to-Video Generator with Polling."""

import asyncio
import base64
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..config import CLIENT_CTX, ENDPOINTS, POLL_INTERVAL, POLL_TIMEOUT
from .. import media_store
from .common import build_client_context, build_generation_context

log = logging.getLogger("sinematica.engine.generators.i2v")


def extract_api_error(result: dict) -> str:
    raw_err = ""
    top_level = result.get("error")
    if top_level:
        raw_err = str(top_level)
    else:
        data = result.get("data")
        if isinstance(data, dict):
            nested = data.get("error")
            if isinstance(nested, dict) and nested.get("message"):
                raw_err = str(nested["message"])
            elif isinstance(nested, str) and nested:
                raw_err = nested
            elif data.get("message"):
                raw_err = str(data["message"])
        elif data:
            raw_err = str(data)

    if not raw_err:
        status = result.get("status", 0)
        return f"HTTP {status}" if status else "Extension API Error"

    if "Cannot access contents" in raw_err or "FLOW_LOGIN_REQUIRED" in raw_err:
        return "Google Flow belum login di Chrome profile. Silakan buka https://labs.google/fx/tools/flow dan pastikan akun Google sudah posisi Login."

    return raw_err


async def upload_image(bridge, image_path: str, project_id: str = None, instance_id: str = None) -> str:
    """Upload a local reference image to Google Flow. Returns media_id string."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    body = {
        "clientContext": build_client_context(project_id),
        "imageBytes": img_b64,
    }

    log.info("Uploading reference image to Flow (%s): %s", instance_id or "auto", os.path.basename(image_path))
    result = await bridge.api_request(ENDPOINTS["upload_image"], body, instance_id=instance_id)

    status = result.get("status", 0)
    data = result.get("data", {})
    if status != 200:
        err = extract_api_error(result)
        raise ValueError(f"Gagal mengunggah gambar ke Flow: {err}")

    media_id = data.get("mediaId") or data.get("name")
    if not media_id and isinstance(data.get("media"), dict):
        media_id = data["media"].get("name")

    if not media_id:
        raise ValueError("Flow API tidak mengembalikan mediaId setelah upload gambar.")

    log.info("Gambar berhasil diunggah! media_id=%s", media_id)
    media_store.save(os.path.basename(image_path), media_id)
    return media_id


async def generate_video_t2v(bridge, prompt: str, aspect: str, project_id: str,
                             duration: int = 10, instance_id: str = None) -> List[str]:
    """Generate text to video using Omni Flash."""
    model_key = f"abra_t2v_{duration}s"
    aspect_ratio_enum = "VIDEO_ASPECT_RATIO_PORTRAIT" if aspect == "portrait" else "VIDEO_ASPECT_RATIO_LANDSCAPE"

    request = {
        "aspectRatio": aspect_ratio_enum,
        "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
        "videoModelKey": model_key,
        "seed": random.randint(1, 99999),
        "metadata": {},
    }

    body = {
        "clientContext": build_client_context(project_id),
        "requests": [request],
    }

    log.info('Generasi T2V: "%s" [%s]', prompt[:50], model_key)
    result = await bridge.api_request(ENDPOINTS["generate_t2v"], body, instance_id=instance_id)

    status = result.get("status", 0)
    if status != 200:
        err = extract_api_error(result)
        raise ValueError(f"Gagal submit generasi T2V ({status}): {err}")

    data = result.get("data", {})
    media = data.get("media", [])
    if not media:
        err = extract_api_error(result)
        raise ValueError(f"Google Flow tidak mengembalikan media video: {err}")

    media_ids = [m.get("name") for m in media if m.get("name")]
    return media_ids


async def generate_video_i2v(bridge, prompt: str, aspect: str, project_id: str,
                              start_image_id: str, duration: int = 8,
                              instance_id: str = None) -> List[str]:
    """Generate video from a start/reference image using Omni Flash."""
    model_key = f"abra_t2v_{duration}s"
    aspect_ratio_enum = "VIDEO_ASPECT_RATIO_PORTRAIT" if aspect == "portrait" else "VIDEO_ASPECT_RATIO_LANDSCAPE"

    request = {
        "aspectRatio": aspect_ratio_enum,
        "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
        "videoModelKey": model_key,
        "seed": random.randint(1, 99999),
        "metadata": {},
        "startImage": {"mediaId": start_image_id},
    }

    body = {
        "clientContext": build_client_context(project_id),
        "requests": [request],
    }

    log.info('Generasi I2V: "%s" [%s] start_image=%s', prompt[:50], model_key, start_image_id[:12])
    result = await bridge.api_request(ENDPOINTS["generate_i2v"], body, instance_id=instance_id)

    status = result.get("status", 0)
    if status != 200:
        err = extract_api_error(result)
        raise ValueError(f"Gagal submit generasi I2V: {err}")

    data = result.get("data", {})
    media = data.get("media", [])
    if not media:
        raise ValueError("Respons Google Flow tidak mengandung objek media.")

    media_ids = [m.get("name") for m in media if m.get("name")]
    return media_ids


async def generate_video_r2v(bridge, prompt: str, aspect: str, project_id: str,
                              reference_image_ids: List[str], duration: int = 10,
                              instance_id: str = None, attempts: int = 3,
                              retry_delay: float = 2.0) -> List[str]:
    """Generate video using multi-character reference images (Ingredients mode) in Google Flow."""
    model_key = f"abra_t2v_{duration}s"
    aspect_ratio_enum = "VIDEO_ASPECT_RATIO_PORTRAIT" if aspect == "portrait" else "VIDEO_ASPECT_RATIO_LANDSCAPE"

    # Google Flow accepts at most seven image references for one Ingredients request.
    # Keep this defensive cap even though the backend selector already prioritizes them.
    ref_objs = [{"mediaId": mid} for mid in reference_image_ids if mid][:7]

    request = {
        "aspectRatio": aspect_ratio_enum,
        "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
        "videoModelKey": model_key,
        "seed": random.randint(1, 99999),
        "metadata": {},
        "referenceImages": ref_objs,
    }

    body = {
        "clientContext": build_client_context(project_id),
        "requests": [request],
    }

    if not ref_objs:
        raise ValueError("Generasi R2V membutuhkan minimal satu image reference.")

    log.info('Generasi R2V (Ingredients %d gambar): "%s" [%s]', len(ref_objs), prompt[:50], model_key)
    endpoint = ENDPOINTS.get("generate_r2v", "/v1/video:batchAsyncGenerateVideoReferenceImages")
    result = None
    max_attempts = max(1, int(attempts or 1))
    for attempt in range(1, max_attempts + 1):
        # Every bridge call executes grecaptcha again in the Flow tab, producing a fresh token.
        result = await bridge.api_request(endpoint, body, instance_id=instance_id)
        status = result.get("status", 0)
        if status == 200:
            break
        err = extract_api_error(result)
        is_transient_captcha = status == 403 and "recaptcha" in err.lower()
        if is_transient_captcha and attempt < max_attempts:
            log.warning(
                "Token reCAPTCHA R2V ditolak (%d/%d); meminta token baru lalu mengulang Ingredients.",
                attempt, max_attempts,
            )
            await asyncio.sleep(retry_delay)
            continue
        raise ValueError(f"Gagal submit generasi R2V ({status}): {err}")

    data = result.get("data", {})
    media = data.get("media", [])
    if not media:
        err = extract_api_error(result)
        raise ValueError(f"Google Flow tidak mengembalikan media video: {err}")

    media_ids = [m.get("name") for m in media if m.get("name")]
    return media_ids


def find_video_url(obj) -> Optional[str]:
    """Recursively search a JSON structure for video download/serving URLs."""
    if isinstance(obj, str):
        if obj.startswith("http://") or obj.startswith("https://"):
            if any(ext in obj.lower() for ext in [".mp4", "servingurl", "download", "video", "googlevideo", "googleusercontent"]):
                return obj
        return None

    if isinstance(obj, dict):
        for key in ["servingUrl", "videoUrl", "downloadUrl", "url", "mp4Url", "fusedVideoUrl"]:
            val = obj.get(key)
            if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
                return val
            elif isinstance(val, dict):
                sub_url = find_video_url(val)
                if sub_url:
                    return sub_url

        for k, v in obj.items():
            if k not in ["clientContext"]:
                res = find_video_url(v)
                if res:
                    return res

    elif isinstance(obj, list):
        for item in obj:
            res = find_video_url(item)
            if res:
                return res

    return None


RAI_HINTS = {
    "PUBLIC_ERROR_REPUTATIONAL": (
        "Google Flow menolak prompt ini karena filter kebijakan konten (reputational). "
        "Biasanya dipicu penggambaran tokoh/institusi nyata seperti polisi, pejabat, merek, "
        "atau nama rumah sakit asli. Ubah adegan jadi generik lalu jalankan ulang."
    ),
    "PUBLIC_ERROR_SAFETY": (
        "Google Flow menolak prompt ini karena filter keamanan (kekerasan/konten sensitif). "
        "Perhalus deskripsi aksinya lalu jalankan ulang."
    ),
    "PUBLIC_ERROR_MINOR": (
        "Google Flow menolak prompt ini karena terdeteksi menggambarkan anak di bawah umur. "
        "Ubah usia/deskripsi karakter lalu jalankan ulang."
    ),
}


def find_failure_reason(item: dict) -> Optional[str]:
    """Return a human-readable reason when Flow has definitively failed this generation.

    Flow reports failures as `status: MEDIA_GENERATION_STATUS_FAILED` with the real cause
    nested under `operation.error.message`, so both a plain equality check on status and a
    top-level error lookup miss it and the caller waits out the whole timeout.
    """
    if not isinstance(item, dict):
        return None

    # Flow's batch-status response puts the definitive result here:
    # media[].mediaMetadata.mediaStatus.  Older responses used top-level fields,
    # so normalize both shapes before deciding whether polling should stop.
    metadata = item.get("mediaMetadata") or item.get("metadata") or {}
    media_status = metadata.get("mediaStatus") if isinstance(metadata, dict) else {}
    holders = [item.get("operation"), item.get("response"), media_status, metadata, item]

    status_values = [item.get("status"), item.get("state")]
    if isinstance(media_status, dict):
        status_values.extend((media_status.get("mediaGenerationStatus"), media_status.get("status")))
    status_str = " ".join(str(value or "") for value in status_values).upper()
    failed = "FAILED" in status_str or "ERROR" in status_str or "BLOCKED" in status_str

    message = None
    for holder in holders:
        if isinstance(holder, dict):
            err = holder.get("error")
            if isinstance(err, dict) and err.get("message"):
                message = str(err["message"])
                break
            if isinstance(err, str) and err:
                message = err
                break
    if not message:
        for holder in holders:
            if isinstance(holder, dict) and holder.get("errorMessage"):
                message = str(holder["errorMessage"])
                break

    if isinstance(media_status, dict):
        reasons = media_status.get("failureReasons")
        if not message and reasons:
            message = ", ".join(str(reason) for reason in reasons)

    if not failed and not message:
        return None

    reason = message or "Rendering gagal di server Google Flow"
    for code, hint in RAI_HINTS.items():
        if code in reason:
            return f"{reason} — {hint}"
    if "PROMINENT_PERSON" in reason or "PROMINENT_PEOPLE" in reason:
        return (
            f"{reason} — Google Flow menganggap prompt/gambar menyerupai tokoh terkenal. "
            "Hilangkan jabatan/nama yang terkesan tokoh nyata dan gunakan karakter fiktif generik."
        )
    return reason


def is_item_successful(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("done") is True or item.get("isDone") is True:
        return True

    status_str = str(item.get("status") or item.get("state") or item.get("operationStatus") or "").upper()
    if any(s in status_str for s in ["SUCCEEDED", "SUCCESSFUL", "COMPLETED", "DONE", "FINISHED"]):
        return True

    meta = item.get("mediaMetadata") or item.get("metadata") or {}
    if isinstance(meta, dict):
        media_status = meta.get("mediaStatus") or meta.get("status") or {}
        if isinstance(media_status, dict):
            gen_status = str(media_status.get("mediaGenerationStatus") or media_status.get("status") or "").upper()
            if any(s in gen_status for s in ["SUCCEEDED", "SUCCESSFUL", "COMPLETED", "DONE", "FINISHED"]):
                return True
        elif isinstance(media_status, str):
            if any(s in media_status.upper() for s in ["SUCCEEDED", "SUCCESSFUL", "COMPLETED", "DONE", "FINISHED"]):
                return True

    return False


# Index of the poll request schema Google Flow accepted, cached so later scenes skip re-probing.
_WORKING_VARIANT_IDX: Optional[int] = None


def _build_poll_operation_variants(clean_id: str) -> List[dict]:
    """Candidate shapes for one `operations[]` entry (proto type AsyncOperation).

    The first entry is the shape Google Flow actually accepted in production; a successful
    200 response echoes back `{"mediaGenerationId", "operation": {"name"}, "sceneId", "status"}`.
    The rest stay as fallbacks in case the upstream schema shifts again — the poller probes
    them in order and caches whichever one is accepted.
    """
    return [
        {"operation": {"name": clean_id}, "sceneId": ""},
        {"operation": {"name": clean_id}},
        {"operation": {"name": f"operations/{clean_id}"}},
        {"name": clean_id},
        {"name": f"operations/{clean_id}"},
    ]


def _dump_poll_diagnostics(media_id: str, elapsed: float, payload: dict):
    try:
        from ..config import ROOT_DIR
        # ROOT_DIR points at engine/, diagnostics belong in the project-level data/ folder.
        diag_path = Path(ROOT_DIR).parent / "data" / "poll_stuck_diagnostics.log"
        diag_path.parent.mkdir(parents=True, exist_ok=True)
        with open(diag_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} media_id={media_id} elapsed={int(elapsed)}s =====\n")
            f.write(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            f.write("\n")
    except Exception as dump_ex:
        log.warning("Gagal menulis poll_stuck_diagnostics.log: %s", dump_ex)


async def poll_video_status(bridge, media_id: str, project_id: str,
                            instance_id: str = None, timeout: int = POLL_TIMEOUT,
                            progress_callback = None) -> Dict[str, Any]:
    """Poll Google Flow for video rendering completion with progress percentage updates."""
    global _WORKING_VARIANT_IDX

    clean_id = media_id.rsplit("/", 1)[-1]
    op_variants = _build_poll_operation_variants(clean_id)

    start_time = asyncio.get_running_loop().time()
    estimated_duration = 35.0  # Estimated average render time in Flow (35s)
    _logged_stuck_dump = False
    rejected_variants: Dict[int, str] = {}

    while (asyncio.get_running_loop().time() - start_time) < timeout:
        elapsed = asyncio.get_running_loop().time() - start_time
        calc_pct = min(95, int((elapsed / estimated_duration) * 100))

        if progress_callback:
            try:
                progress_callback(int(elapsed), calc_pct)
            except Exception:
                pass

        # Use the schema already proven to work from Affilia
        variant_idx = 0
        body = {
            "clientContext": build_client_context(project_id),
            "media": [{"name": clean_id, "projectId": project_id}]
        }

        try:
            result = await bridge.api_request(ENDPOINTS["poll_status"], body, instance_id=instance_id)
        except Exception as poll_err:
            log.warning("Poll status request warning (instance %s): %s", instance_id, poll_err)
            await asyncio.sleep(POLL_INTERVAL)
            continue

        status_code = result.get("status", 0)
        data = result.get("data", {})

        if status_code == 400:
            # Schema rejected outright: mark it dead and immediately try the next candidate
            # instead of burning the whole poll window on a request that can never succeed.
            err_text = extract_api_error(result)
            rejected_variants[variant_idx] = err_text
            if _WORKING_VARIANT_IDX == variant_idx:
                _WORKING_VARIANT_IDX = None
            log.warning("Skema polling varian #%d ditolak Flow: %s", variant_idx, err_text)
            if not _logged_stuck_dump:
                _logged_stuck_dump = True
                _dump_poll_diagnostics(media_id, elapsed, {"rejected_body": body, "response": result})
            continue

        if status_code == 200:
            if _WORKING_VARIANT_IDX != variant_idx:
                _WORKING_VARIANT_IDX = variant_idx
                log.info("Skema polling varian #%d diterima Google Flow (HTTP 200).", variant_idx)
            top_url = find_video_url(data)

            # Fallback direct check via get_media endpoint if top_url is missing
            if not top_url and clean_id:
                try:
                    media_endpoint = f"/v1/media/{clean_id}"
                    m_res = await bridge.api_request(media_endpoint, {"clientContext": build_client_context(project_id)}, instance_id=instance_id)
                    if m_res.get("status") == 200:
                        m_data = m_res.get("data", {})
                        m_url = find_video_url(m_data)
                        if m_url:
                            top_url = m_url
                            if isinstance(data, dict):
                                data["media"] = [m_data]
                except Exception as m_ex:
                    log.warning("Fallback get_media request warning: %s", m_ex)

            ops = data.get("operations", [])
            media_arr = data.get("media", [])
            items_to_check = []
            if isinstance(ops, list):
                for op in ops:
                    if isinstance(op, dict):
                        items_to_check.append(op)
                        if isinstance(op.get("media"), dict):
                            items_to_check.append(op["media"])
                        if isinstance(op.get("response"), dict):
                            items_to_check.append(op["response"])
            if isinstance(media_arr, list):
                for m in media_arr:
                    if isinstance(m, dict):
                        items_to_check.append(m)

            # Check for a definitive failure first: a rejected generation never produces a
            # URL, so treating it as "still rendering" would stall until the timeout.
            for item in items_to_check:
                failure = find_failure_reason(item)
                if failure:
                    _dump_poll_diagnostics(media_id, elapsed, {"failed_response": data})
                    raise RuntimeError(f"Generasi video ditolak Google Flow: {failure}")

            for item in items_to_check:
                item_url = find_video_url(item) or top_url
                if is_item_successful(item) or item_url:
                    if not item_url and clean_id:
                        # Fallback: get encodedVideo (base64) directly from get_media if URL is not found
                        try:
                            m_res = await bridge.api_request(f"/v1/media/{clean_id}", {"clientContext": build_client_context(project_id)}, instance_id=instance_id)
                            m_data = m_res.get("data", {})
                            if isinstance(m_data, dict):
                                v = m_data.get("video", {})
                                if isinstance(v, dict):
                                    encoded = v.get("encodedVideo")
                                    if encoded:
                                        item_url = f"data:video/mp4;base64,{encoded}"
                        except Exception as ex:
                            log.warning("Gagal fetch encodedVideo: %s", ex)

                    if item_url:
                        log.info("Video render selesai! URL (termasuk b64): %s", item_url[:60] + "...")
                        if progress_callback:
                            progress_callback(int(elapsed), 100)
                        return {
                            "media_id": media_id,
                            "status": "COMPLETED",
                            "video_url": item_url,
                            "raw": item,
                        }
                    elif clean_id:
                        log.info("Video render selesai! Menggunakan direct flow media ID: %s", clean_id)
                        if progress_callback:
                            progress_callback(int(elapsed), 100)
                        return {
                            "media_id": media_id,
                            "status": "COMPLETED",
                            "video_url": f"flow_media_id:{clean_id}",
                            "raw": item,
                        }
                    else:
                        log.warning("Render dinyatakan sukses tapi tidak ada URL dan clean_id: %s", item)

            if top_url:
                log.info("Video render selesai (extracted fallback URL)! URL: %s", top_url[:60])
                if progress_callback:
                    progress_callback(int(elapsed), 100)
                return {
                    "media_id": media_id,
                    "status": "COMPLETED",
                    "video_url": top_url,
                    "raw": data,
                }

            if not _logged_stuck_dump and elapsed > estimated_duration * 2:
                _logged_stuck_dump = True
                log.warning(
                    "Poll status 200 tapi belum terdeteksi selesai setelah %ds (media_id=%s). Dump ke log.",
                    int(elapsed), media_id
                )
                _dump_poll_diagnostics(media_id, elapsed, {"status_code": status_code, "data": data})
        else:
            # Transient/unknown status (401, 429, 5xx, ...) — keep polling, but leave a trail.
            log.warning("Poll status return HTTP %s: %s", status_code, str(data)[:200])
            if not _logged_stuck_dump and elapsed > estimated_duration * 2:
                _logged_stuck_dump = True
                log.warning(
                    "Poll status BUKAN 200 (status=%s) setelah %ds (media_id=%s). "
                    "Dump lengkap ditulis ke poll_stuck_diagnostics.log.",
                    status_code, int(elapsed), media_id
                )
                _dump_poll_diagnostics(media_id, elapsed, result)

        await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Video rendering timeout ({timeout} detik).")

