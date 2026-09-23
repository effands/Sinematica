"""Sinematica Backend — Multi-Profile Job Executor & Task Balancer."""

import asyncio
import datetime
import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional
import time
import uuid
import random

from . import settings
from .bridge_manager import get_bridge, ensure_ready
from .character_seed_guard import missing_character_seeds
from .character_seed_fallback import (
    alternate_character_seed,
    build_safe_character_seed_prompt,
    is_unsafe_generation_error,
)
from .character_reference_flow import resolve_character_reference_paths, upload_character_references
from .film_stitcher import extract_continuity_frame, stitch_scenes
from .execution_metrics import finish_job_timing, record_output_file_size
from .gallery_cleanup import cleanup_job_files, job_source_files
from .media_download import stream_download, stream_exact_media_with_retry
from .scene_pacing import rewrite_dense_prompt_with_ai, should_try_gemini_storyboard_image
from .scene_continuity import continuity_start_image
from .film_asset_cache import (FilmAssetCache, AssetRecoveryRequired, character_asset_key,
                               ensure_film_asset_id, serialize_film_execution)
from .scene_execution import character_sheet_description, build_physical_execution_guard, scene_execution_context
from .scene_audio_direction import apply_scene_audio_direction, resolve_master_music_track
from .scene_direction import (
    apply_no_branding_direction,
    build_speaker_lock,
    build_character_wardrobe_lock,
    enforce_spoken_language_lock,
    choose_shot_count,
    ensure_unique_character_signatures,
)
from .content_quality import build_render_realism_guard, build_scene_blueprint_guard
from .storyboard_image import fetch_image_bytes, generate_storyboard_sheet
from .profile_reference_cache import (
    ensure_character_media_for_profile,
    ensure_files_for_profile,
    profile_key,
)

from omniflash.generators import upload_image, poll_video_status, harvest_project_videos


class _SheetAlreadyBuilt(Exception):
    """Signals the storyboard sheet was produced by Gemini, so skip the Flow fallback."""


def is_flow_auth_error(error: Exception) -> bool:
    """Return True when retrying with the same Chrome session cannot succeed."""
    text = str(error).lower()
    return any(marker in text for marker in (
        "(401)", "'code': 401", '"code": 401', "unauthenticated",
        "invalid authentication credentials", "flow_login_expired",
    ))

log = logging.getLogger("sinematica.jobs_executor")

HISTORY_FILE = settings.DATA_DIR / "jobs_history.json"
_active_jobs: Dict[str, Dict[str, Any]] = {}
_job_logs: Dict[str, List[Dict[str, Any]]] = {}


def is_flow_quota_error(error: Exception) -> bool:
    """Identify exhausted Flow capacity so this profile is skipped for later scenes."""
    text = str(error or "").lower()
    return any(marker in text for marker in (
        "quota", "credit", "insufficient", "rate limit", "too many requests", "429",
        "limit reached", "out of credits", "not enough credits",
    ))


def has_known_zero_flow_credits(instance: dict) -> bool:
    """Reject only a known negative quota; zero in registration is stale/unknown.

    The extension can register before the Flow account panel is scraped and
    report its persisted default as 0. Treating that value as authoritative
    caused valid accounts (the user's Flow panel showed 935 credits) to be
    blocked before the authenticated refresh ran.
    """
    if not isinstance(instance, dict) or "credits" not in instance:
        return False
    value = instance.get("credits")
    if isinstance(value, bool):
        return False
    try:
        return float(value) < 0
    except (TypeError, ValueError):
        return False


async def profile_has_zero_flow_credits(bridge, instance: dict) -> bool:
    """Refresh quota once through the authenticated Flow endpoint when possible."""
    try:
        response = await bridge.api_request(
            "/v1/credits", None, instance_id=instance.get("instance_id"), timeout=6
        )
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            return False
        details = data.get("details") if isinstance(data.get("details"), dict) else {}
        raw = details.get("value", data.get("credits"))
        match = re.search(r"-?\d+(?:[.,]\d+)?", str(raw)) if raw is not None else None
        # The extension's credit endpoint may expose a persisted/default 0
        # before the Flow account panel has finished loading. Do not block a
        # generation on that ambiguous value; a real exhausted account is
        # handled by the generation response (quota error) itself.
        return bool(match and float(match.group(0).replace(',', '.')) < 0)
    except Exception:
        # Unknown quota is not a reason to discard a connected profile.
        return False


async def usable_flow_profiles(bridge, instances: list[dict]) -> list[dict]:
    usable = []
    for instance in instances:
        if not await profile_has_zero_flow_credits(bridge, instance):
            usable.append(instance)
    return usable


def _load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    if isinstance(item, dict) and "job_id" in item:
                        # A process restart cancels in-memory asyncio tasks. Never
                        # resurrect their stale `processing` flag, otherwise the
                        # frontend shows an endless spinner and may offer a
                        # misleading stop action. The durable assets remain
                        # resumable from the last completed stage.
                        if item.get("status") == "processing":
                            item["status"] = "interrupted"
                            item.setdefault(
                                "error",
                                "Backend dimulai ulang sebelum job selesai; gunakan Resume dari cache.",
                            )
                        _active_jobs[item["job_id"]] = item
        except Exception as ex:
            log.warning("Gagal memuat history jobs: %s", ex)

_load_history()


def _save_history():
    try:
        data = list(_active_jobs.values())
        if HISTORY_FILE.exists():
            backup = HISTORY_FILE.with_suffix(".json.bak")
            backup.write_bytes(HISTORY_FILE.read_bytes())
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as ex:
        log.warning("Gagal menyimpan history jobs: %s", ex)


def classify_diagnostic(
    message: str,
    level: str = "info",
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, str]]:
    """Analyzes execution events to generate technical root-cause diagnostics and remediation advice."""
    lower_msg = str(message).lower()
    lvl = str(level).lower()

    if (
        "flow-error-tile" in lower_msg
        or "gagal dibuat" in lower_msg
        or "failed to generate" in lower_msg
        or "kartu kendala" in lower_msg
        or "image_retry" in lower_msg
        or "video_retry" in lower_msg
    ):
        return {
            "classification": "GOOGLE_FLOW_MEDIA_GENERATION_FAILED",
            "root_cause": "Google Flow generation engine encountered an internal render error or model timeout on canvas.",
            "evidence": "Detected <flow-error-tile> element on Google Flow canvas ('Maaf, video/gambar ini gagal dibuat').",
            "action_taken": "Automated retry mechanism triggered on failed tile (max 2 attempts).",
            "technical_advice": "Check Google account GPU quota, verify prompt length, or rotate Chrome profile if failure persists.",
        }

    if (
        "401" in lower_msg
        or "unauthenticated" in lower_msg
        or "waiting_for_login" in lower_msg
        or ("token" in lower_msg and "kedaluwarsa" in lower_msg)
    ):
        return {
            "classification": "GOOGLE_FLOW_AUTH_SESSION_EXPIRED",
            "root_cause": "Google OAuth authorization token or SAPISID session cookie has expired.",
            "evidence": "HTTP 401 response or missing authentication headers from Chrome extension.",
            "action_taken": "Pipeline pauses or triggers automated session cookie probing from active Flow tab.",
            "technical_advice": "Open Google Flow tab in Chrome and interact with the sidepanel to refresh session tokens.",
        }

    if (
        "429" in lower_msg
        or "kuota" in lower_msg
        or "quota" in lower_msg
        or "credit" in lower_msg
        or "resource_exhausted" in lower_msg
        or "kredit habis" in lower_msg
    ):
        return {
            "classification": "GOOGLE_FLOW_RESOURCE_EXHAUSTED_OR_RATE_LIMITED",
            "root_cause": "Daily credit quota exhausted or per-minute rate limit reached for current Google profile.",
            "evidence": "HTTP 429 status or zero credit balance reported by Google Flow API.",
            "action_taken": "Job executor automatically flags profile and fails over to the next available Chrome profile.",
            "technical_advice": "Connect secondary Google account profiles to the Fleet or wait for credit renewal window.",
        }

    if (
        "kebijakan" in lower_msg
        or "policy" in lower_msg
        or "safety" in lower_msg
        or "ditolak google flow" in lower_msg
        or "filter keamanan" in lower_msg
    ):
        return {
            "classification": "GOOGLE_FLOW_POLICY_SAFETY_TRIGGERED",
            "root_cause": "Prompt semantic tokens or reference composition triggered Google Flow content safety filter.",
            "evidence": "Interception of safety policy moderation rejection response from Google Flow.",
            "action_taken": "AI Studio autonomously reformulates dramatic synonyms and relaxes brand/celebrity reference constraints.",
            "technical_advice": "Verify prompt descriptions for prohibited real-world public figures, violence, or sensitive keywords.",
        }

    if (
        "content_script_unreachable" in lower_msg
        or "tidak ada profil chrome" in lower_msg
        or "terputus" in lower_msg
        or "bridge disconnected" in lower_msg
    ):
        return {
            "classification": "CHROME_EXTENSION_BRIDGE_DISCONNECTED",
            "root_cause": "Chrome Extension background worker suspended or Google Flow tab closed/reloaded.",
            "evidence": "WebSocket bridge connection failure or chrome.tabs.sendMessage timeout.",
            "action_taken": "System initiates exponential backoff reconnect attempts and prompts user in CLI.",
            "technical_advice": "Ensure Google Chrome is open with the Sinematica extension ON and tab navigated to https://flow.google.com.",
        }

    if (
        ("composer" in lower_msg and "tidak menyediakan kontrol image" in lower_msg)
        or ("file input" in lower_msg and "gagal" in lower_msg)
    ):
        return {
            "classification": "DOM_ELEMENT_SELECTOR_NOT_FOUND",
            "root_cause": "Google Flow web UI DOM hierarchy or component class attributes changed.",
            "evidence": "Content script DOM query selector cascade failed to locate target interactive element.",
            "action_taken": "Fails over to alternative selectors and full DOM traversal strategies.",
            "technical_advice": "Inspect Google Flow DOM elements and update selector fallback definitions in flow-executor.js.",
        }

    if (
        "gagal mengunduh" in lower_msg
        or "unduhan media flow" in lower_msg
        or "transfer mp4 tidak lengkap" in lower_msg
    ):
        return {
            "classification": "MEDIA_DOWNLOAD_CORRUPTED_OR_TIMEOUT",
            "root_cause": "Chunk transfer timeout or network stream disconnection during authenticated media download.",
            "evidence": "Binary chunk checksum/size mismatch or HTTP read stream timeout.",
            "action_taken": "Retrying authenticated media download chunks via Chrome tab bridge with exponential backoff.",
            "technical_advice": "Check network bandwidth stability and verify Google CDN media URLs are accessible.",
        }

    if "ffmpeg" in lower_msg or "gagal menggabungkan film" in lower_msg:
        return {
            "classification": "FFMPEG_ENCODING_STITCH_FAILED",
            "root_cause": "FFmpeg executable failed during video concatenation, audio mix, or subtitle burning.",
            "evidence": "Non-zero return code or stream syntax error emitted by FFmpeg process.",
            "action_taken": "Fallback to raw stream copy concatenation without filters.",
            "technical_advice": "Verify that ffmpeg is installed in system PATH and source MP4 clips have valid headers.",
        }

    if lvl in ("error", "warning") or "gagal" in lower_msg or "error" in lower_msg:
        return {
            "classification": "EXECUTION_RUNTIME_WARNING_OR_ERROR",
            "root_cause": f"Pipeline encountered an unexpected runtime condition: {message[:120]}",
            "evidence": f"Event level: {level.upper()} | Message: {message}",
            "action_taken": "Automated recovery or error state recorded in job ledger.",
            "technical_advice": "Review full diagnostic logs in data/jobs/<job_id>/execution_diagnostics.jsonl for complete stack trace.",
        }

    return None


def log_event(
    job_id: str,
    message: str,
    level: str = "info",
    profile: str = None,
    meta: Optional[Dict[str, Any]] = None,
    diagnostic: Optional[Dict[str, Any]] = None,
):
    now = datetime.datetime.now()
    iso_ts = now.isoformat()
    time_str = now.strftime("%H:%M:%S.%f")[:-3]
    diag = diagnostic or classify_diagnostic(message, level, meta)

    entry = {
        "timestamp": time_str,
        "iso_timestamp": iso_ts,
        "message": message,
        "level": level,
        "profile": profile or "System",
        "meta": meta or {},
        "diagnostic": diag or {},
    }
    if job_id not in _job_logs:
        _job_logs[job_id] = []
    _job_logs[job_id].append(entry)
    log.info("[%s] [%s] [%s] %s", iso_ts, profile or "SYS", level.upper(), message)

    # Persist structured diagnostic log line to job directory and central logger
    if job_id:
        try:
            job_dir = JOBS_DIR / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            diag_file = job_dir / "execution_diagnostics.jsonl"
            with open(diag_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            exec_file = job_dir / "execution.log"
            diag_extra = f"\n   └─ DIAGNOSTIC: {json.dumps(diag, ensure_ascii=False)}" if diag else ""
            meta_extra = f"\n   ├─ META: {json.dumps(meta, ensure_ascii=False)}" if meta else ""
            with open(exec_file, "a", encoding="utf-8") as f:
                f.write(f"[{iso_ts}] [{level.upper():5s}] [{profile or 'SYS'}] {message}{meta_extra}{diag_extra}\n")
        except Exception:
            pass

    try:
        logs_dir = settings.DATA_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        today_str = now.strftime("%Y-%m-%d")
        central_log = logs_dir / f"jobs_execution_{today_str}.log"
        central_jsonl = logs_dir / f"jobs_execution_{today_str}.jsonl"

        with open(central_log, "a", encoding="utf-8") as f:
            f.write(f"[{iso_ts}] [{level.upper():5s}] [{job_id or 'NO_JOB'}] [{profile or 'SYS'}] {message}\n")
        with open(central_jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps({**entry, "job_id": job_id}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def get_job_logs(job_id: str) -> List[Dict[str, Any]]:
    return _job_logs.get(job_id, [])


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    job = _active_jobs.get(job_id)
    if job is not None:
        return job
    if isinstance(job_id, str) and job_id.startswith("job__"):
        return _active_jobs.get("job_" + job_id[5:])
    return None


def list_jobs() -> List[Dict[str, Any]]:
    return list(_active_jobs.values())


def _job_created_at_from_directory(job_dir: Path) -> float:
    timestamps = []
    for path in job_dir.glob("*"):
        try:
            timestamps.append(path.stat().st_mtime)
        except OSError:
            continue
    if timestamps:
        return min(timestamps)
    try:
        return job_dir.stat().st_mtime
    except OSError:
        return time.time()


def recover_jobs_from_storage() -> List[Dict[str, Any]]:
    """Rebuild missing gallery history entries from storage/jobs folders.

    The actual videos live under storage/jobs. If jobs_history.json is overwritten,
    Gallery should still show existing rendered folders instead of looking empty.
    """
    recovered = 0
    settings.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    for job_dir in sorted(settings.JOBS_DIR.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0):
        if not job_dir.is_dir():
            continue
        job_id = job_dir.name
        if job_id in _active_jobs:
            continue

        clips = sorted(job_dir.glob("scene_*.mp4"))
        film_candidates = [
            job_dir / "cinematic_film_with_audio.mp4",
            job_dir / "cinematic_film.mp4",
            job_dir / "cinematic_film_custom.mp4",
        ]
        film_path = next((p for p in film_candidates if p.exists()), None)
        if not clips and not film_path:
            continue

        created_at = _job_created_at_from_directory(job_dir)
        title = job_id.replace("_", " ").title()
        if film_path and job_id.startswith("job_render_"):
            title = "Sequencer Custom Render"

        _active_jobs[job_id] = {
            "job_id": job_id,
            "title": title,
            "status": "completed" if film_path else "completed_partial",
            "current_scene": len(clips),
            "total_scenes": len(clips),
            "aspect_ratio": "portrait",
            "scenes": [
                {
                    "scene_number": index,
                    "status": "completed",
                    "video_url": f"/storage/jobs/{job_id}/{clip.name}",
                    "relative_url": f"/storage/jobs/{job_id}/{clip.name}",
                }
                for index, clip in enumerate(clips, start=1)
            ],
            "cinematic_film_path": str(film_path) if film_path else None,
            "cinematic_film_url": f"/storage/jobs/{job_id}/{film_path.name}" if film_path else None,
            "cancelled": False,
            "created_at": created_at,
            "created_at_formatted": time.strftime("%d %b %Y, %H:%M", time.localtime(created_at)),
            "initial_prompt": "",
            "recovered_from_storage": True,
        }
        recovered += 1

    if recovered:
        _save_history()
    return list_jobs()


def cancel_job(job_id: str) -> bool:
    job = _active_jobs.get(job_id)
    if job:
        job["cancelled"] = True
        job["status"] = "cancelled"
        log_event(job_id, "🛑 [USER] Permintaan pembatalan job diterima. Menghentikan render...", level="warning")
        _save_history()
        return True
    return False


def delete_job(job_id: str) -> bool:
    job = _active_jobs.get(job_id)
    job_dir = settings.JOBS_DIR / job_id
    existed = job is not None or job_dir.exists()
    remaining_jobs = [item for jid, item in _active_jobs.items() if jid != job_id]
    cleanup = cleanup_job_files(
        job_id,
        job,
        remaining_jobs,
        jobs_dir=settings.JOBS_DIR,
        uploads_dir=settings.UPLOADS_DIR,
    )
    if cleanup.errors:
        raise RuntimeError("; ".join(cleanup.errors))
    _active_jobs.pop(job_id, None)
    _job_logs.pop(job_id, None)
    _save_history()
    return existed


def hide_gallery_job(job_id: str) -> bool:
    """Hide a job from Gallery without deleting any rendered files."""
    job = _active_jobs.get(job_id)
    job_dir = settings.JOBS_DIR / job_id
    if not job_dir.is_dir():
        return False
    if job:
        job["gallery_hidden"] = True
        _save_history()
    return True


delete_job_clips = hide_gallery_job


def delete_multiple_jobs(job_ids: List[str]) -> int:
    count = 0
    for jid in job_ids:
        if delete_job(jid):
            count += 1
    return count


def update_job(job_id: str, new_title: Optional[str] = None, new_status: Optional[str] = None) -> bool:
    job = _active_jobs.get(job_id)
    if job:
        if new_title:
            job["title"] = new_title.strip()
        if new_status:
            job["status"] = new_status.strip()
        _save_history()
        return True
    return False


def create_render_job(title: str) -> str:
    """Register a new job entry for a manual/custom render (e.g. multi-clip sequencer merge)."""
    job_id = f"job_render_{uuid.uuid4().hex[:8]}"
    job_dir = settings.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    job_state = {
        "job_id": job_id,
        "title": title,
        "status": "processing",
        "current_scene": 0,
        "total_scenes": 0,
        "aspect_ratio": "landscape",
        "scenes": [],
        "cinematic_film_path": None,
        "cancelled": False,
        "created_at": time.time(),
        "created_at_formatted": time.strftime("%d %b %Y, %H:%M"),
        "source_files": [],
    }
    _active_jobs[job_id] = job_state
    _save_history()
    return job_id


def mark_render_job_completed(job_id: str, film_path: str):
    job = _active_jobs.get(job_id)
    if job:
        job["status"] = "completed"
        job["cinematic_film_path"] = film_path
        job["cinematic_film_url"] = f"/storage/jobs/{job_id}/{Path(film_path).name}"
        record_output_file_size(job, film_path)
        finish_job_timing(job)
        _save_history()


def create_and_register_job(
    storyboard: Dict[str, Any],
    theme_image_path: Optional[str] = None,
    aspect_ratio: str = "landscape",
    duration: int = 10,
    flow_project_id: Optional[str] = None,
    force_uniform_duration: bool = False,
    render_scene_limit: Optional[int] = None,
    render_scene_start: Optional[int] = None,
    render_scene_end: Optional[int] = None,
    job_id: Optional[str] = None,
) -> str:
    """Create and immediately register a storyboard job state synchronously in memory and history.

    This ensures that GET /api/jobs/{job_id} returns a valid job immediately when
    the frontend starts polling, even before the async worker coroutine acquires the
    execution lock or begins scene processing.
    """
    if not job_id:
        job_id = f"job_{uuid.uuid4().hex[:8]}"

    job_dir = settings.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    all_scenes = storyboard.get("scenes", [])
    scenes = [s for i, s in enumerate(all_scenes, 1)
              if (render_scene_start is None or int(s.get("scene_number") or i) >= render_scene_start)
              and (render_scene_end is None or int(s.get("scene_number") or i) <= render_scene_end)]
    total_scenes = len(scenes)

    seo_scene_lines = []
    for scene_index, scene in enumerate(scenes, start=1):
        scene_number = scene.get("scene_number") or scene_index
        scene_title = scene.get("title") or f"Adegan {scene_number}"
        scene_action = scene.get("action_summary") or ""
        scene_narration = scene.get("narration_id") or scene.get("voiceover_script") or ""
        seo_scene_lines.append(
            f"Adegan {scene_number} — {scene_title}: {scene_action}"
            + (f" Narasi: {scene_narration}" if scene_narration else "")
        )
    seo_story_context = "\n".join(filter(None, [
        storyboard.get("premise") or storyboard.get("source_script") or storyboard.get("theme") or "",
        *seo_scene_lines,
    ]))[:16000]
    seo_storyboard = {
        key: storyboard.get(key)
        for key in ("film_title", "premise", "source_script", "theme", "genre_style", "characters", "scenes")
        if storyboard.get(key) is not None
    }

    started_at = time.time()
    job_state = {
        "job_id": job_id,
        "title": storyboard.get("film_title", "Sinematica Story"),
        "status": "processing",
        "current_scene": 0,
        "total_scenes": total_scenes,
        "aspect_ratio": aspect_ratio,
        "scenes": [],
        "cinematic_film_path": None,
        "cancelled": False,
        "created_at": started_at,
        "started_at": started_at,
        "created_at_formatted": time.strftime("%d %b %Y, %H:%M"),
        "initial_prompt": storyboard.get("premise") or storyboard.get("theme") or "",
        "storyboard": storyboard,
        "theme_image_path": theme_image_path,
        "duration": duration,
        "force_uniform_duration": force_uniform_duration,
        "flow_project_id": flow_project_id,
        "render_scene_limit": render_scene_limit,
        "render_scene_start": render_scene_start,
        "render_scene_end": render_scene_end,
        "seo_story_context": seo_story_context,
        "seo_storyboard": seo_storyboard,
        "target_lang": storyboard.get("target_lang") or "",
        "target_country": storyboard.get("target_country") or "",
        "profile_failures": {},
        "execution_stage": "registered",
    }
    _active_jobs[job_id] = job_state
    _save_history()
    return job_id


FLOW_ALLOWED_DURATIONS = (4, 6, 8, 10)
TEXTLESS_CHARACTER_SHEET_REVISION = "textless-v2"


def resolve_scene_duration(scene: Dict[str, Any], fallback: int) -> int:
    """Pick the per-scene duration, snapped to a length Google Flow actually supports.

    The storyboard may ask for any number; Flow only ships 4s/6s/8s/10s models, so anything
    else is rounded to the nearest supported value instead of failing the render.
    """
    raw = scene.get("duration")
    try:
        wanted = int(raw)
    except (TypeError, ValueError):
        wanted = int(fallback)
    if wanted in FLOW_ALLOWED_DURATIONS:
        return wanted
    return min(FLOW_ALLOWED_DURATIONS, key=lambda d: (abs(d - wanted), d))


def resolve_scene_characters(scene: Dict[str, Any], characters: List[Dict[str, Any]],
                             available_ids: Dict[Any, str], limit: int = 10) -> List[Dict[str, Any]]:
    """Work out which characters belong in this scene, accurately matching by ID or Name.

    Uses character tags, name matching in scene text, or falls back to including all available
    character sheets so multi-character stories never drop reference images.
    """
    if not available_ids:
        return []

    # Build multi-index lookup maps
    char_by_id = {}
    char_by_name = {}

    for c in (characters or []):
        cid = c.get("id")
        cname = str(c.get("name") or "").strip()
        if cid is not None:
            char_by_id[cid] = c
            char_by_id[str(cid)] = c
        if cname:
            char_by_name[cname.lower()] = c

    # Map available_ids to int/str keys and character name keys
    media_by_id_or_name = {}
    for k, v in available_ids.items():
        media_by_id_or_name[k] = v
        media_by_id_or_name[str(k)] = v
        c_obj = char_by_id.get(k) or char_by_id.get(str(k)) or char_by_name.get(str(k).lower())
        if c_obj and c_obj.get("name"):
            media_by_id_or_name[str(c_obj["name"]).lower()] = v

    matched_items = []
    seen = set()

    # 1. Check characters_in_scene tags (can contain ints, str ints, or character names)
    raw_tags = scene.get("characters_in_scene") or []
    for tag in raw_tags:
        target_char = char_by_id.get(tag) or char_by_id.get(str(tag)) or char_by_name.get(str(tag).lower())
        media_id = media_by_id_or_name.get(tag) or media_by_id_or_name.get(str(tag)) or media_by_id_or_name.get(str(tag).lower())

        cid = target_char.get("id") if target_char else tag
        cname = target_char.get("name") if target_char else str(tag)

        desc = target_char.get("description") or target_char.get("desc") if target_char else ""
        if media_id and cid not in seen:
            seen.add(cid)
            matched_items.append({
                "id": cid,
                "name": cname,
                "description": desc,
                "media_id": media_id,
                "matched_by": "tag"
            })

    if matched_items:
        return matched_items[:limit]

    # 2. Text searching in scene title, action_summary, prompt_for_flow, narration_id
    haystack = " ".join(str(scene.get(k) or "") for k in
                        ("title", "action_summary", "prompt_for_flow", "narration_id")).lower()

    for c in (characters or []):
        cid = c.get("id")
        cname = str(c.get("name") or "").strip()
        if not cname or cid in seen:
            continue

        media_id = media_by_id_or_name.get(cid) or media_by_id_or_name.get(str(cid)) or media_by_id_or_name.get(cname.lower())
        if not media_id:
            continue

        name_lower = cname.lower()
        tokens = [t for t in name_lower.split() if len(t) >= 2]
        if name_lower in haystack or any(t in haystack for t in tokens):
            seen.add(cid)
            matched_items.append({
                "id": cid,
                "name": cname,
                "description": c.get("description") or c.get("desc") or "",
                "media_id": media_id,
                "matched_by": "nama"
            })

    if matched_items:
        return matched_items[:limit]

    # 3. Fallback: Include ALL available character sheets for the scene (up to limit),
    # so multi-character stories don't drop character references!
    for c in (characters or []):
        cid = c.get("id")
        cname = str(c.get("name") or "").strip()
        if cid in seen:
            continue
        media_id = media_by_id_or_name.get(cid) or media_by_id_or_name.get(str(cid)) or media_by_id_or_name.get(cname.lower())
        if media_id:
            seen.add(cid)
            matched_items.append({
                "id": cid,
                "name": cname or f"Karakter {cid}",
                "description": c.get("description") or c.get("desc") or "",
                "media_id": media_id,
                "matched_by": "karakter cerita"
            })
            if len(matched_items) >= limit:
                break

    if matched_items:
        return matched_items[:limit]

    # Fallback to available_ids keys if characters list was empty
    for k, v in available_ids.items():
        if k not in seen:
            seen.add(k)
            matched_items.append({
                "id": k,
                "name": f"Karakter {k}",
                "description": "",
                "media_id": v,
                "matched_by": "available_id"
            })
            if len(matched_items) >= limit:
                break

    return matched_items[:limit]


def build_video_reference_ids(character_ids: List[str], storyboard_media_id: Optional[str],
                              policy_attempt: int = 0, limit: int = 7,
                              drop_all_references: bool = False,
                              continuity_media_id: Optional[str] = None,
                              product_media_ids: Optional[List[str]] = None) -> List[str]:
    """Order at most seven Flow Ingredients by:
    1. Continuity frame from previous scene (lighting, room, and environmental anchor)
    2. Storyboard sheet of current scene (camera angle, shot blocking, and action progression)
    3. Character identity sheets (facial structure and wardrobe lock)
    4. Affiliate product images (if applicable)
    Strictly follows Google Flow's maximum 7 reference image limit.
    """
    if drop_all_references:
        return []
    refs = []

    # Slot 1: Continuity frame (Frame terakhir scene sebelumnya)
    if continuity_media_id and continuity_media_id not in refs and len(refs) < limit:
        refs.append(continuity_media_id)

    # Slot 2: Storyboard sheet (Pemandu komposisi shot & variasi angle adegan ini)
    # The storyboard remains mandatory on every attempt. Policy retries may
    # adjust the prompt, but must not silently turn the video into prompt-only
    # generation or drop the scene's composition reference.
    if storyboard_media_id and storyboard_media_id not in refs and len(refs) < limit:
        refs.append(storyboard_media_id)

    # Slot 3+: Character sheets (Sheet identitas karakter pemeran)
    for media_id in character_ids:
        if media_id and media_id not in refs and len(refs) < limit:
            refs.append(media_id)

    # Slot 4+: Product / Affiliate media
    for media_id in product_media_ids or []:
        if media_id and media_id not in refs and len(refs) < limit:
            refs.append(media_id)

    # Fallback if no refs were gathered but storyboard is available
    if not refs and storyboard_media_id and len(refs) < limit:
        refs.append(storyboard_media_id)

    return refs[:limit]


def build_visual_style_guard(visual_style: str = "live_action", children_mode: bool = False) -> str:
    """Lock one rendering medium across character sheets, boards, and final video."""
    style = visual_style or ("3d_cartoon" if children_mode else "live_action")
    contracts = {
        "live_action": "LIVE-ACTION PHOTOGRAPHY ONLY: original fictional characters, natural skin texture and pores, realistic hair and fabric physics, optical cinematic camera capture. NO cartoon, anime, 3D CGI animation, Pixar style, illustration, painting, comic art, doll-like face, plastic skin, or cel shading.",
        "3d_cartoon": "STYLIZED 3D ANIMATION ONLY: sculpted 3D characters, modeled volume, rounded forms, physically based 3D materials, feature-animation lighting, identical model-sheet proportions. NO live-action people, photography, realistic skin pores, 2D drawing, anime, or flat cel animation.",
        "2d_animation": "HAND-DRAWN 2D ANIMATION ONLY: clean consistent line art, flat graphic shapes, controlled cel shading, painted 2D backgrounds, identical model-sheet proportions. NO live-action photography, photoreal skin, 3D render, clay, CGI volume, or anime-style redesign.",
        "anime_2d": "2D ANIME PRODUCTION STYLE ONLY: clean ink lines, consistent anime model sheets, controlled cel shading, expressive anime faces, painted 2D backgrounds. NO live-action photography, photoreal skin, western 3D cartoon, clay, or realistic CGI.",
        "toy_brick": "ORIGINAL TOY-BRICK 3D ANIMATION ONLY: interlocking plastic-brick environments, original block-figure characters, simple cylindrical heads and claw-like hands, glossy molded plastic, stop-motion-inspired movement. NO LEGO logos, branded sets, licensed minifigures, live-action humans, 2D drawing, or photoreal skin.",
        "line_character": "MINIMALIST LINE-CHARACTER ANIMATION ONLY: consistent clean monoline characters, simple geometric bodies, sparse flat colour accents, restrained backgrounds, precise readable silhouettes. NO photorealism, 3D volume, textured skin, painterly shading, or style switching.",
        "claymation": "HANDCRAFTED CLAYMATION STOP-MOTION ONLY: consistent sculpted clay puppets, visible handmade fingerprints, miniature practical sets, tactile surfaces, frame-by-frame movement. NO live-action actors, smooth CGI plastic, 2D illustration, or photoreal skin.",
        "storybook_watercolor": "WATERCOLOR STORYBOOK ANIMATION ONLY: consistent hand-painted watercolor characters, pigment blooms, textured cold-press paper, delicate ink contours, layered illustrated backgrounds. NO live action, 3D CGI, plastic materials, anime cel shading, or photorealism.",
        "paper_cutout": "PAPER-CUTOUT ANIMATION ONLY: layered hand-cut paper characters, visible paper fibres, hinged flat limbs, collage scenery, soft tabletop shadows. NO live-action humans, 3D CGI characters, clay, or photoreal skin.",
        "pixel_art": "CINEMATIC PIXEL-ART ANIMATION ONLY: one consistent pixel grid, deliberate limited palette, crisp pixel silhouettes, sprite-consistent proportions. NO smooth vectors, live action, 3D rendering, anti-aliased photorealism, or mixed pixel resolutions.",
        "comic_book": "CINEMATIC COMIC-BOOK ANIMATION ONLY: consistent graphic-novel designs, bold ink contours, controlled halftone shading, dramatic panel composition, limited print palette. NO live-action photography, 3D CGI, watercolor, or character redesign.",
    }
    return "\n\nVISUAL STYLE LOCK (HIGHEST PRIORITY): " + contracts.get(style, contracts["live_action"])


def build_live_action_guard(children_mode: bool) -> str:
    """Backward-compatible guard used by older callers and tests."""
    return "" if children_mode else build_visual_style_guard("live_action")


def build_finishing_look_guard(storyboard: Dict[str, Any]) -> str:
    """Apply curated YouTube finishing modifiers without changing the base medium."""
    maps = {
        "visual_vibe": {
            "pro_cinematic": "polished professional cinematic production design and premium YouTube storytelling finish",
            "clean_commercial": "clean commercial art direction, uncluttered composition and readable subject separation",
            "documentary": "grounded observational documentary mood and authentic environments",
            "sci_fi": "original futuristic science-fiction production design with coherent non-franchise technology",
            "ugc_natural": "authentic creator-led UGC mood with natural smartphone immediacy and candid staging",
            "korean_drama": "refined Korean drama mood with elegant emotional framing and polished television finish",
            "microdrama": "fast-paced short-form microdrama staging with expressive reactions and clear story beats",
            "kids_colorful": "cheerful child-friendly energy with playful design and bright readable storytelling",
            "cozy_lifestyle": "warm intimate lifestyle mood with relaxed domestic staging and tactile comfort",
            "luxury_premium": "high-end luxury editorial finish with refined materials and restrained composition",
            "dark_thriller": "mysterious suspense-thriller atmosphere with controlled shadows and readable staging",
        },
        "lighting_style": {
            "soft_light": "soft diffused key light with gentle shadows", "golden_hour": "warm golden-hour directional light",
            "volumetric": "controlled volumetric light shafts and atmospheric depth", "chiaroscuro": "dramatic chiaroscuro contrast",
            "low_key": "low-key cinematic lighting with readable faces", "backlight": "strong rim backlight and clear silhouettes",
            "rainy": "overcast rainy ambience with wet-surface reflections",
        },
        "color_palette": {
            "warm": "cohesive warm amber colour palette", "cool": "cohesive cool blue-cyan colour palette",
            "vibrant": "controlled vibrant saturation with protected character colours", "pastel": "soft cohesive pastel palette",
            "earthy": "natural earthy ochre, olive and brown palette", "complementary": "controlled complementary colour harmony",
            "teal_orange": "cinematic teal-and-orange palette with consistent grading",
        },
    }
    selected = [mapping.get(storyboard.get(field) or "", "") for field, mapping in maps.items()]
    selected = [item for item in selected if item]
    auto_direction = str(storyboard.get("auto_art_direction") or "").strip()
    if auto_direction:
        selected.append(auto_direction)
    ugc_extra = ""
    if str(storyboard.get("ugc_variant") or "").lower() == "raw_amateur":
        ugc_extra = "\n\nRAW AMATEUR SMARTPHONE LOCK: authentic creator UGC handheld camera, front-facing mobile lens, natural room ambience. NO cinematic dolly/crane/drone."
    if not selected:
        return ugc_extra
    return "\n\nFINISHING LOOK LOCK (DO NOT CHANGE BASE MEDIUM): " + "; ".join(selected) + "." + ugc_extra


def adapt_template_for_visual_style(template: str, visual_style: str, children_mode: bool) -> str:
    """Remove photoreal-only template instructions when a stylized medium is selected."""
    style_labels = {
        "live_action": "LIVE-ACTION CINEMATIC",
        "2d_animation": "HAND-DRAWN 2D ANIMATION",
        "anime_2d": "2D ANIME",
        "toy_brick": "TOY-BRICK 3D ANIMATION",
        "line_character": "MINIMALIST LINE-CHARACTER ANIMATION",
        "claymation": "CLAYMATION STOP-MOTION",
        "storybook_watercolor": "WATERCOLOR STORYBOOK",
        "paper_cutout": "PAPER-CUTOUT ANIMATION",
        "pixel_art": "PIXEL-ART ANIMATION",
        "comic_book": "COMIC-BOOK ANIMATION",
    }
    style_label = style_labels.get(visual_style, "LIVE-ACTION CINEMATIC")
    adapted = str(template or "")
    if visual_style != "live_action":
        replacements = (
            (r"\bultra[- ]?photorealistic\b", "strictly medium-consistent"),
            (r"\bphotorealistic\b", "medium-consistent"),
            (r"\bphotorealism\b", "mixed-medium rendering"),
            (r"\beditorial fashion photography\b", f"professional {style_label.lower()} presentation"),
            (r"\blive[- ]action photography\b", "mixed visual medium"),
            (r"\bnatural skin (?:texture|pores)\b", "style-consistent facial surfaces"),
            (r"\brealistic skin (?:texture|pores)\b", "style-consistent facial surfaces"),
            (r"\brealistic fabric\b", "style-consistent costume materials"),
            (r"\breal human(?:s| actors| people)?\b", "off-medium character rendering"),
        )
        for pattern, replacement in replacements:
            adapted = re.sub(pattern, replacement, adapted, flags=re.IGNORECASE)
        # Legacy negative lists explicitly banned the very media now selected. Replace the
        # whole cluster instead of leaving contradictory tokens beside the final guard.
        adapted = re.sub(
            r"cartoon style,\s*anime style,\s*painterly rendering,?",
            "mixed visual medium, unrequested rendering style, inconsistent art direction,",
            adapted,
            flags=re.IGNORECASE,
        )
    # Children's templates historically embedded 3D in their headings and render
    # directions. Replace those phrases so the user's selected medium is authoritative.
    adapted = adapted.replace("3D CARTOON", style_label)
    adapted = adapted.replace("3D cartoon", style_label.lower())
    adapted = adapted.replace("Soft 3D cartoon render", style_label)
    adapted = adapted.replace("Smooth rounded forms", "Forms consistent with the selected visual medium")
    return adapted


def resolve_affiliate_scene_numbers(total_scenes: int, position: Any) -> set[int]:
    """Resolve one explicit scene or a natural two-scene block around the midpoint."""
    total = max(1, int(total_scenes or 1))
    if isinstance(position, int) or str(position).isdigit():
        return {max(1, min(total, int(position)))}
    first = max(1, total // 2)
    return {first, min(total, first + 1)}


_REFERENCE_IMAGE_POLICY_CODES = (
    "PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED",
    "PUBLIC_ERROR_IP_INPUT_IMAGE",
)


def should_drop_character_references(rejection_reason: str, policy_attempt: int,
                                     max_policy_rewrites: int) -> bool:
    """Keep authored image references while rewriting only the rejected prompt."""
    # Character sheets, storyboard and continuity frames are part of the
    # user's identity/continuity rules. A policy retry must not silently turn
    # the request into prompt-only generation; sanitize the text instead.
    return False


def fictionalize_character_names(prompt: str, character_names: List[str]) -> str:
    """Remove potentially protected names while keeping stable aliases for the scene."""
    rewritten = prompt or ""
    unique_names = list(dict.fromkeys(name.strip() for name in character_names if name and name.strip()))
    for index, name in enumerate(unique_names):
        alias = f"Fictional Character {chr(ord('A') + index)}"
        rewritten = re.sub(re.escape(name), alias, rewritten, flags=re.IGNORECASE)
    return (
        rewritten.rstrip()
        + "\n\nUse entirely original fictional adult characters with non-celebrity faces. "
        "Do not imitate any real person, public figure, actor, protected character, brand, or franchise."
    )


def choose_instance_for_project(instances: List[Dict[str, Any]], project_id: Optional[str]) -> Optional[str]:
    """Choose the connected Chrome identity that actually owns the requested Flow project."""
    connected = [item for item in instances
                 if item.get("connected") and item.get('ready', True) and item.get('logged_in', True)]
    if not connected:
        return None
    def auth_healthy(item: Dict[str, Any]) -> bool:
        return item.get("last_api_status") not in (401, 403)
    def version_key(item: Dict[str, Any]) -> tuple:
        parts = re.findall(r"\d+", str(item.get("version") or "0"))
        return tuple(int(part) for part in (parts + [0, 0, 0])[:3])
    connected.sort(
        key=lambda x: (
            auth_healthy(x),
            bool(x.get("oauth_ready")),
            version_key(x),
            x.get("ready", True),
        ),
        reverse=True,
    )
    if project_id:
        exact = next((item for item in connected
                      if item.get("project_id") == project_id and auth_healthy(item)), None)
        if exact:
            return exact.get("instance_id")
    with_project = next((item for item in connected if item.get("project_id") and auth_healthy(item)), None)
    return (with_project or connected[0]).get("instance_id")


def build_sheet_manifest(sheet_chars: List[Dict[str, Any]]) -> str:
    """Spell out which attached sheet belongs to which character."""
    if not sheet_chars:
        return ""
    lines = []
    for i, c in enumerate(sheet_chars, start=1):
        name = c.get("name", f"Karakter {i}")
        desc = c.get("description") or c.get("desc") or ""
        desc_str = f": {desc}" if desc else ""
        lines.append(f"  {i}. {name}{desc_str} — character sheet labelled \"{name}\"")
    return (
        "\nATTACHED CHARACTER SHEETS (in the order supplied):\n"
        + "\n".join(lines)
        + "\nEach attached sheet carries its character's name printed on the page. Match every "
          "character in this scene to the sheet bearing that same name, and use only these "
          "characters — do not invent anyone else.\n"
    )


def build_composition_addendum(scene: Dict[str, Any]) -> str:
    """Fold the storyboard's 3-5 multi-angle shot flow into the video prompt as text.

    Flow's video endpoint accepts real reference images, but its image endpoint gives us no
    way to pin a storyboard panel to the character sheets. So the composition guidance the
    panel was meant to carry is written into the prompt instead, while character identity
    keeps coming from the sheets attached as actual reference images.
    """
    shot = (scene.get("shot_type") or "").strip()
    camera = (scene.get("camera_movement") or "").strip()
    shot_flow = scene.get("shot_flow") or []

    bits = []
    if shot:
        bits.append(f"Framing: {shot}.")
    if camera:
        bits.append(f"Camera: {camera}.")

    if shot_flow and isinstance(shot_flow, list):
        flow_lines = []
        for sf in shot_flow:
            if isinstance(sf, dict):
                t = sf.get("time") or sf.get("timecode") or ""
                ang = sf.get("angle") or sf.get("camera_angle") or sf.get("shot") or ""
                desc = sf.get("description") or sf.get("action") or ""
                flow_lines.append(f"[{t}] {ang} - {desc}".strip())
            elif isinstance(sf, str) and sf.strip():
                flow_lines.append(sf.strip())
        if flow_lines:
            bits.append("Cinematic 3-5 multi-angle camera beat progression across the clip: " + " -> ".join(flow_lines) + ".")
    else:
        bits.append(
            "Stage it as a dynamic 3 to 5 multi-angle camera beat progression: opening low-angle close-up "
            "establishing physical action, cutting to medium-wide environment interaction, over-the-shoulder focus, "
            "and resolving into a wide framing. Keep every character exactly as shown in the attached character sheets — "
            "same faces, colours, proportions and outfits throughout."
        )
    return " ".join(bits)


async def download_file(
    bridge, url: str, dest_path: Path, instance_id: Optional[str] = None,
    media_id: Optional[str] = None, project_id: Optional[str] = None,
    media_kind: str = "video", job_id: Optional[str] = None, label: Optional[str] = None,
):
    target_label = label or dest_path.name
    if job_id:
        log_event(job_id, f"📥 Memulai proses unduh {media_kind} '{target_label}'...")

    # Check for ui_video wrapper in either url or media_id
    raw_ui_token = None
    if isinstance(url, str) and "ui_video:" in url:
        raw_ui_token = url
    elif media_id and "ui_video:" in str(media_id):
        raw_ui_token = str(media_id)

    if raw_ui_token:
        import base64
        encoded_url = raw_ui_token.split("ui_video:", 1)[1].split("?", 1)[0].strip()
        try:
            decoded_url = base64.urlsafe_b64decode(encoded_url + "=" * (-len(encoded_url) % 4)).decode("utf-8")
        except Exception as ex:
            raise RuntimeError(f"Handle video Flow UI tidak valid: {ex}") from ex
        if not decoded_url.startswith(("https://", "http://")):
            raise RuntimeError(f"Handle video Flow UI tidak berisi URL unduhan yang valid: {decoded_url}")
        
        # 1. Try direct stream download for public / signed CDN targets
        try:
            if job_id:
                log_event(job_id, f"🌐 Mengunduh stream {media_kind} langsung dari URL CDN terautentikasi...")
            await asyncio.to_thread(stream_download, decoded_url, dest_path, media_kind=media_kind)
            if dest_path.exists() and dest_path.stat().st_size > 1000:
                if job_id:
                    size_kb = dest_path.stat().st_size / 1024
                    size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
                    log_event(job_id, f"💾 Berhasil mengunduh dan menyimpan {media_kind} '{target_label}' ({size_str})!")
                return
        except Exception as dl_ex:
            if job_id:
                log_event(job_id, f"⚠️ Unduhan stream langsung belum berhasil ({dl_ex}); mencoba via extension bridge...", level="warning")
            log.info("Unduhan langsung URL UI belum berhasil (%s); mencoba via extension bridge...", dl_ex)

        # 2. Try download through extension with authenticated cookies & session
        try:
            if job_id:
                log_event(job_id, f"🔌 Mengunduh {media_kind} melalui bridge ekstensi Chrome ({instance_id or 'default'})...")
            result = await bridge.download_url_with_retry(
                decoded_url, instance_id=instance_id, timeout=300, attempts=3, delay=2
            )
            if result and result.get("data"):
                dest_path.write_bytes(result["data"])
                if job_id:
                    size_kb = dest_path.stat().st_size / 1024
                    size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
                    log_event(job_id, f"💾 Berhasil mengunduh dan menyimpan {media_kind} '{target_label}' via extension bridge ({size_str})!")
                return
        except Exception as bridge_dl_ex:
            if job_id:
                log_event(job_id, f"⚠️ Unduhan via extension bridge gagal ({bridge_dl_ex}).", level="warning")
            log.warning("Unduhan via extension bridge gagal: %s", bridge_dl_ex)
        return
    if url.startswith("data:"):
        import base64
        # format is data:video/mp4;base64,.....
        header, encoded = url.split(",", 1)
        video_bytes = base64.b64decode(encoded)
        if video_bytes.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF8")):
            raise RuntimeError("Flow mengembalikan thumbnail gambar, bukan video MP4.")
        with open(dest_path, "wb") as out:
            out.write(video_bytes)
        if job_id:
            size_kb = dest_path.stat().st_size / 1024
            size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
            log_event(job_id, f"💾 Data {media_kind} '{target_label}' ({size_str}) berhasil disimpan.")
    else:
        download_url = url
        exact_download_error = None
        if media_id and hasattr(bridge, "trpc_request"):
            try:
                if job_id:
                    log_event(job_id, f"🔍 Meminta signed URL CDN segar ke Google Flow untuk media {media_id[:16]}...")
                await stream_exact_media_with_retry(
                    bridge,
                    media_id.rsplit("/", 1)[-1],
                    project_id or "",
                    instance_id,
                    dest_path,
                    attempts=6,
                    delay=3.0,
                    downloader=lambda signed_url, destination: stream_download(
                        signed_url, destination, media_kind=media_kind
                    ),
                )
                if job_id and dest_path.exists():
                    size_kb = dest_path.stat().st_size / 1024
                    size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
                    log_event(job_id, f"💾 Berhasil mengunduh stream {media_kind} '{target_label}' ({size_str})!")
                return
            except Exception as ex:
                exact_download_error = ex
                if job_id:
                    log_event(job_id, f"⚠️ Resolver signed CDN belum selesai ({ex}); memakai URL unduhan alternatif...", level="warning")
                log.warning("Unduhan URL CDN segar belum berhasil; memakai URL polling/API: %s", ex)
        if url.startswith("flow_media_id:"):
            clean_id = url.split(":", 1)[1]
            if download_url == url:
                # UUID-only /v1/media/{id}?alt=media is not a valid Flow download route and
                # consistently returns HTTP 400 INVALID_ARGUMENT. Keep the actionable resolver
                # failure instead of hiding it behind a known-invalid fallback request.
                raise RuntimeError(
                    "Flow menyelesaikan render tetapi signed download URL belum dapat diambil "
                    f"untuk media {clean_id}. Pastikan ekstensi terbaru sudah di-reload. "
                    f"Detail resolver: {exact_download_error or 'URL belum dipublikasikan'}"
                )
        if download_url.startswith(("https://", "http://")) and "aisandbox-pa.googleapis.com" not in download_url:
            try:
                # Signed Flow URLs are directly reachable by the backend. Streaming them avoids
                # converting an entire MP4 to base64 inside Chrome and pushing it over WebSocket.
                if job_id:
                    log_event(job_id, f"🌐 Mengunduh stream {media_kind} langsung dari URL bertanda tangan...")
                await asyncio.to_thread(stream_download, download_url, dest_path, media_kind=media_kind)
                if job_id and dest_path.exists():
                    size_kb = dest_path.stat().st_size / 1024
                    size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
                    log_event(job_id, f"💾 Berhasil mengunduh stream {media_kind} '{target_label}' ({size_str})!")
                return
            except Exception as ex:
                if job_id:
                    log_event(job_id, f"⚠️ Unduhan stream langsung gagal ({ex}); beralih ke bridge profil Chrome...", level="warning")
                log.warning("Unduhan langsung MP4 gagal; mencoba profil Chrome: %s", ex)
        if job_id:
            log_event(job_id, f"🔌 Mengunduh {media_kind} melalui bridge ekstensi Chrome ({instance_id or 'default'})...")
        result = await bridge.download_url_with_retry(
            download_url, instance_id=instance_id, timeout=300, attempts=3, delay=2
        )
        with open(dest_path, "wb") as out:
            out.write(result["data"])
        if media_kind != "image" and result["data"].startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF8")):
            dest_path.unlink(missing_ok=True)
            raise RuntimeError("Flow mengembalikan thumbnail gambar, bukan video MP4.")
        if job_id and dest_path.exists():
            size_kb = dest_path.stat().st_size / 1024
            size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
            log_event(job_id, f"💾 Berhasil mengunduh dan menyimpan {media_kind} '{target_label}' ({size_str})!")


async def recover_character_master(cache, key, bridge, job_dir, job_id: Optional[str] = None):
    """Retry a generated sheet's download, never its generation."""
    pending = cache.state(key) or {}
    char_name = pending.get('name') or key
    if not pending.get('media_id'):
        raise AssetRecoveryRequired('Sheet belum memiliki media ID untuk dipulihkan.')
    if job_id:
        log_event(job_id, f"📥 Mengunduh file master sheet '{char_name}' dari Google Flow...")
    temporary = job_dir / f"sheet_download_{uuid.uuid4().hex}.png"
    try:
        await download_file(
            bridge, pending.get('image_url') or 'flow_media_id:' + pending['media_id'], temporary,
            instance_id=pending.get('instance_id'), media_id=pending['media_id'],
            project_id=pending.get('project_id'), media_kind="image", job_id=job_id,
            label=f"Sheet {char_name}",
        )
        saved_path = cache.save(
            key,
            temporary.read_bytes(),
            name=pending.get('name'),
            media_id=pending.get('media_id'),
            project_id=pending.get('project_id'),
            image_url=pending.get('image_url'),
        )
        if job_id:
            log_event(job_id, f"💾 Master sheet '{char_name}' berhasil disimpan ke master cache film.")
        return saved_path
    except Exception as error:
        raise AssetRecoveryRequired(
            'Sheet sudah dibuat tetapi belum tersimpan lokal. Hubungkan akun asal lalu Resume untuk '
            'mengunduh ulang; generasi ulang diblokir.'
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


@serialize_film_execution
async def execute_storyboard_job(
    job_id: str,
    storyboard: Dict[str, Any],
    theme_image_path: Optional[str] = None,
    aspect_ratio: str = "landscape",
    duration: int = 10,
    flow_project_id: Optional[str] = None,
    force_uniform_duration: bool = False,
    render_scene_limit: Optional[int] = None,
    render_scene_start: Optional[int] = None,
    render_scene_end: Optional[int] = None,
):
    """Execute video generation for each scene across available Chrome profiles."""
    bridge = get_bridge()
    job_dir = settings.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    all_scenes = storyboard.get("scenes", [])
    scenes = [s for i, s in enumerate(all_scenes, 1)
              if (render_scene_start is None or int(s.get("scene_number") or i) >= render_scene_start)
              and (render_scene_end is None or int(s.get("scene_number") or i) <= render_scene_end)]
    # Flow media IDs are project-scoped. Resolve the active project first and
    # bind the film cache to that project so a sheet from an older Flow project
    # can never be mistaken for the current character reference.
    asset_cache = None
    total_scenes = len(scenes)

    # Persist a job-owned SEO narrative. Gallery SEO must describe this rendered
    # video's actual scenes, never whichever storyboard happens to be open later.
    seo_scene_lines = []
    for scene_index, scene in enumerate(scenes, start=1):
        scene_number = scene.get("scene_number") or scene_index
        scene_title = scene.get("title") or f"Adegan {scene_number}"
        scene_action = scene.get("action_summary") or ""
        scene_narration = scene.get("narration_id") or scene.get("voiceover_script") or ""
        seo_scene_lines.append(
            f"Adegan {scene_number} — {scene_title}: {scene_action}"
            + (f" Narasi: {scene_narration}" if scene_narration else "")
        )
    seo_story_context = "\n".join(filter(None, [
        storyboard.get("premise") or storyboard.get("source_script") or storyboard.get("theme") or "",
        *seo_scene_lines,
    ]))[:16000]
    seo_storyboard = {
        key: storyboard.get(key)
        for key in ("film_title", "premise", "source_script", "theme", "genre_style", "characters", "scenes")
        if storyboard.get(key) is not None
    }

    started_at = time.time()
    existing_state = _active_jobs.get(job_id)
    if existing_state:
        job_state = existing_state
        job_state["execution_stage"] = "character_sheets"
        job_state["started_at"] = started_at
        job_state["cancelled"] = False
        job_state["status"] = "processing"
    else:
        job_state = {
            "job_id": job_id,
            "title": storyboard.get("film_title", "Sinematica Story"),
            "status": "processing",
            "current_scene": 0,
            "total_scenes": total_scenes,
            "aspect_ratio": aspect_ratio,
            "scenes": [],
            "cinematic_film_path": None,
            "cancelled": False,
            "created_at": started_at,
            "started_at": started_at,
            "created_at_formatted": time.strftime("%d %b %Y, %H:%M"),
            "initial_prompt": storyboard.get("premise") or storyboard.get("theme") or "",
            "storyboard": storyboard,
            "theme_image_path": theme_image_path,
            "duration": duration,
            "force_uniform_duration": force_uniform_duration,
            "flow_project_id": flow_project_id,
            "render_scene_limit": render_scene_limit,
            "seo_story_context": seo_story_context,
            "seo_storyboard": seo_storyboard,
            "target_lang": storyboard.get("target_lang") or "",
            "target_country": storyboard.get("target_country") or "",
            "profile_failures": {},
            "execution_stage": "character_sheets",
        }
        _active_jobs[job_id] = job_state
    # Persist the complete storyboard immediately so a backend restart before
    # the first scene/error checkpoint can still resume this job.
    _save_history()

    planned_durations = [
        duration if force_uniform_duration else resolve_scene_duration(sc, duration) for sc in scenes
    ]
    total_runtime = sum(planned_durations)
    job_state["total_duration"] = total_runtime
    if force_uniform_duration:
        pacing_note = f"{total_scenes} adegan x {duration}s (durasi seragam)"
    else:
        pacing_note = f"{total_scenes} adegan, ritme {'/'.join(str(d) for d in planned_durations)}s"
    log_event(job_id, f"🚀 [0%] Memulai eksekusi film '{job_state['title']}' ({pacing_note} = total {total_runtime}s)...")
    log_event(job_id, f"🔌 [0%] Memeriksa kesiapan profil Chrome Agent terhubung...")

    try:
        await ensure_ready(timeout=30)
    except Exception as ex:
        job_state["status"] = "failed"
        job_state["error"] = str(ex)
        log_event(job_id, f"❌ Gagal memulai job: {ex}", level="error")
        return

    def _handle_flow_progress(msg: dict):
        stage = msg.get("stage", "FLOW")
        text = msg.get("message", "")
        if text:
            profile_name = msg.get("profile") or "FLOW"
            log_event(job_id, f"[{stage}] {text}", level="info", profile=profile_name)

    bridge.add_progress_listener(_handle_flow_progress)

    # Check Flow Project ID
    project_id = flow_project_id or settings.get_flow_project_id()
    if not project_id:
        snap = bridge.instance_snapshot()
        candidates = sorted(
            [i for i in snap if i.get("project_id") and i.get("connected") and i.get("ready", True) and i.get("logged_in", True)],
            key=lambda x: (
                x.get("last_api_status") not in (401, 403),
                bool(x.get("oauth_ready")),
                tuple(int(part) for part in (re.findall(r"\d+", str(x.get("version") or "0")) + [0, 0, 0])[:3]),
                x.get("ready", True),
            ),
            reverse=True,
        )
        if candidates:
            project_id = candidates[0]["project_id"]

    if not project_id:
        log_event(job_id, "⚠️ Flow Project ID belum diisi di Settings. Menggunakan default session project...", level="warning")
    else:
        log_event(job_id, f"🌐 [0%] Flow Project ID kandidat: {project_id}")

    project_instance_id = choose_instance_for_project(bridge.instance_snapshot(), project_id)
    selected_profile = next((item for item in bridge.instance_snapshot()
                             if item.get('instance_id') == project_instance_id), {})
    project_id = selected_profile.get('project_id') or project_id
    # Keep the media-owning Flow project stable across storyboard failover.
    # A mutable project_id would make Stage 3 re-upload same-origin media.
    origin_project_id = project_id
    asset_cache = FilmAssetCache(
        settings.STORAGE_DIR / 'film_assets',
        f"{ensure_film_asset_id(storyboard)}:{project_id or 'default-session'}",
    )
    log_event(
        job_id,
        f"🎯 [0%] Flow Project ID yang dipakai: {project_id or '(default session project)'}"
        f" | Profil: {selected_profile.get('name') or selected_profile.get('instance_id') or '(otomatis)'}",
    )

    # Step 1: Upload Reference Image, or Generate one Anchor Seed Image PER Character in Flow
    ref_media_id = None
    affiliate_product = storyboard.get("affiliate_product") or {}
    affiliate_media_ids: List[str] = []
    character_media_ids: Dict[Any, str] = {}
    character_image_urls: Dict[Any, str] = {}
    character_image_paths: Dict[Any, str] = {}
    character_media_by_profile: Dict[Any, Dict[Any, str]] = {}
    file_media_by_profile: Dict[Any, Dict[str, str]] = {}
    storyboard_media_by_profile: Dict[Tuple[int, Any], str] = {}

    cfg = settings.get_settings()
    # Character sheets are a mandatory identity stage in the film pipeline.
    # Keep the legacy setting readable for compatibility, but never allow it to
    # bypass the user's required sheet -> storyboard -> video order.
    enable_seed_image = True
    custom_template = cfg.get("character_seed_template") or settings.DEFAULT_CHARACTER_SHEET_TEMPLATE
    # A storyboard Image is also mandatory before any Video request.  The old
    # toggle could accidentally send a film straight to Video without its
    # storyboard reference.
    enable_scene_storyboard_image = True

    # Children's stories need 3D cartoon animals, not photoreal humans, so they get their
    # own sheet templates instead of the cinematic defaults.
    is_children = bool(storyboard.get("children_mode"))
    visual_style = storyboard.get("visual_style") or ("3d_cartoon" if is_children else "live_action")
    if is_children:
        custom_template = settings.CHILDREN_CHARACTER_SHEET_TEMPLATE
    custom_template = adapt_template_for_visual_style(custom_template, visual_style, is_children)

    # The theme image is an additional visual guide; it must never replace the mandatory
    # per-character anchor sheets.
    if theme_image_path and Path(theme_image_path).exists():
        log_event(job_id, "📸 [5%] Mengunggah gambar referensi tema ke Google Flow...")
        try:
            ref_media_id = await upload_image(
                bridge, theme_image_path, project_id=project_id, instance_id=project_instance_id
            )
            log_event(job_id, f"✅ [5%] Gambar referensi berhasil diunggah ke Flow! (Media ID: {ref_media_id[:16]}...)")
        except Exception as ex:
            log_event(job_id, f"⚠️ Gagal mengunggah gambar referensi: {ex}. Melanjutkan tanpa Media ID...", level="warning")

    if affiliate_product.get("enabled"):
        product_paths = [
            path for path in affiliate_product.get("reference_paths") or []
            if isinstance(path, str) and Path(path).exists()
        ]
        if product_paths:
            log_event(job_id, f"🛍️ [5%] Mengunggah {len(product_paths)} referensi produk affiliate ke Ingredients...")
            for product_path in product_paths:
                try:
                    affiliate_media_ids.append(await upload_image(
                        bridge, product_path, project_id=project_id, instance_id=project_instance_id
                    ))
                except Exception as ex:
                    log_event(job_id, f"⚠️ Referensi produk gagal diunggah ({ex}).", level="warning")

    characters = storyboard.get("characters") or []
    if not characters:
        char_desc = storyboard.get("consistent_characters") or storyboard.get("genre_style") or job_state["title"]
        characters = [{"id": 1, "name": job_state["title"], "seed": storyboard.get("character_seed", 123456), "description": char_desc}]
    characters = ensure_unique_character_signatures(characters)
    storyboard["characters"] = characters

    if not enable_seed_image:
        log_event(job_id, "⏭️ [TAHAP 1/3] Pembuatan Gambar Anchor Seed Karakter di-bypass (Disabled oleh Settings)...")
    else:

        from omniflash.generators import generate_character_image
        seed_instances = await usable_flow_profiles(bridge, [item for item in bridge.instance_snapshot()
                          if item.get('connected') and item.get('ready', True) and item.get('logged_in', True)
                          and not has_known_zero_flow_credits(item)])
        # Flow media and authenticated UI sessions are project-scoped. Never
        # fail over a character-sheet request to a profile from another Flow
        # project: that profile cannot use this job's assets and commonly
        # returns a misleading auth failure. Keep failover only within the
        # requested/origin project.
        exact_project_seed_instances = [
            item for item in seed_instances
            if item.get('project_id') == project_id
        ]
        if project_id:
            seed_instances = exact_project_seed_instances
        if not seed_instances:
            connected_profiles = [item for item in bridge.instance_snapshot()
                                  if item.get('connected') and item.get('ready', True) and item.get('logged_in', True)]
            all_quota_empty = bool(connected_profiles)
            for connected_profile in connected_profiles:
                if not await profile_has_zero_flow_credits(bridge, connected_profile):
                    all_quota_empty = False
                    break
            if all_quota_empty:
                job_state["status"] = "waiting_for_quota"
                job_state["error"] = (
                    "Semua profil Chrome Flow yang terhubung melaporkan kredit 0. "
                    "Hubungkan profil Flow lain atau isi ulang kredit, lalu Resume job."
                )
                log_event(job_id, f"⏸️ [TAHAP 1/3] {job_state['error']}", level="warning")
                _save_history()
                return
        seed_instances.sort(key=lambda item: item.get('instance_id') != choose_instance_for_project(seed_instances, project_id))
        first_target_id = seed_instances[0].get('instance_id') if seed_instances else None
        origin_instance_id = first_target_id
        if not first_target_id:
            raise RuntimeError('Tidak ada profil Chrome Flow yang aktif untuk membuat character sheet.')

        log_event(job_id, f"🎨 [5%] [TAHAP 1/3] Memeriksa master cache untuk {len(characters)} karakter; hanya sheet yang belum ada akan dibuat.")
        for c_idx, char in enumerate(characters, start=1):
            char_id = char.get("id", c_idx)
            char_name = char.get("name", f"Karakter {char_id}")
            char_seed = char.get("seed", storyboard.get("character_seed", 123456))
            char_desc = character_sheet_description(char)
            char["sheet_revision"] = TEXTLESS_CHARACTER_SHEET_REVISION

            safe_name = "".join(c for c in char_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
            local_sheet_file = job_dir / f"character_sheet_{char_id}_{safe_name}.png"
            log_event(job_id, f"🔍 [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Memeriksa ketersediaan master sheet untuk '{char_name}'...")
            try:
                owned_reference_paths = resolve_character_reference_paths(char, storyboard)
                asset_key = character_asset_key(char, visual_style, owned_reference_paths)
                cached_sheet = asset_cache.ready_path(asset_key)
                existing_asset = asset_cache.state(asset_key)
                if not cached_sheet and existing_asset:
                    # A Flow media handle is enough for storyboard/video
                    # Ingredients. Do not spend another generation timeout
                    # trying to download an image sheet that is already known
                    # to exist in Flow.
                    pending_media_id = existing_asset.get("media_id") if isinstance(existing_asset, dict) else None
                    if pending_media_id:
                        for alias in (char_id, str(char_id), char_name, char_name.lower()):
                            character_media_ids[alias] = pending_media_id
                        log_event(
                            job_id,
                            f"♻️ [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Sheet '{char_name}' sudah tersedia di Flow (Media ID: {pending_media_id[:16]}...); memakai media ID yang ada tanpa generate ulang.",
                        )
                        continue
                    log_event(job_id, f"📥 [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Memulihkan master sheet '{char_name}' dari storage Flow...")
                    cached_sheet = await recover_character_master(asset_cache, asset_key, bridge, job_dir, job_id=job_id)
                if not cached_sheet and local_sheet_file.exists():
                    log_event(job_id, f"💾 [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Mengimpor sheet '{char_name}' dari file lokal '{local_sheet_file.name}'...")
                    cached_sheet = asset_cache.save(asset_key, local_sheet_file.read_bytes(), name=char_name)
                if cached_sheet:
                    for alias in (char_id, str(char_id), char_name, char_name.lower()):
                        character_image_paths[alias] = cached_sheet
                    try:
                        log_event(job_id, f"📤 [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Menyiapkan media ID sheet '{char_name}' untuk profil Flow...")
                        reused_map, _ = await ensure_character_media_for_profile(
                            bridge, [char], character_image_paths, project_id, first_target_id,
                            character_media_by_profile, upload_fn=upload_image,
                        )
                        character_media_ids.update(reused_map)
                    except Exception as ex:
                        cached_media_id = (existing_asset or {}).get("media_id") if isinstance(existing_asset, dict) else None
                        cached_project_id = (existing_asset or {}).get("project_id") if isinstance(existing_asset, dict) else None
                        if cached_media_id and (not cached_project_id or cached_project_id == project_id):
                            for alias in (char_id, str(char_id), char_name, char_name.lower()):
                                character_media_ids[alias] = cached_media_id
                            log_event(
                                job_id,
                                f"♻️ [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Cache lokal '{char_name}' siap; media ID Flow sudah tersedia. "
                                "Upload ulang tidak diperlukan, tanpa generate ulang.",
                            )
                        else:
                            raise
                    log_event(job_id, f"💾 [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Master sheet '{char_name}' siap dari cache laptop; tanpa generate ulang.")
                    continue
            except Exception as ex:
                # A cached sheet (local bytes or a Flow media ID) is an
                # already-paid asset. A temporary upload/session failure must
                # never turn into a second paid generation. Keep the job
                # resumable and recover the same cache after Flow reconnects.
                if existing_asset and (
                    existing_asset.get('media_id') or cached_sheet or existing_asset.get('status') == 'ready'
                ):
                    job_state['status'] = 'waiting_for_reference'
                    job_state['error'] = f"Cache/import sheet '{char_name}' perlu dipulihkan: {ex}. Gunakan Resume."
                    log_event(job_id, job_state['error'], level='warning')
                    _save_history()
                    return

                # There is no cached asset to preserve, so a fresh generation
                # is valid here.

            # The character name is part of the authored sheet contract so the
            # asset can be identified visually in Flow/Gallery. Do not prepend
            # a contradictory "library-only / do not render the name" prompt:
            # the selected template already controls the exact header layout.
            char_prompt = custom_template.replace("{char_name}", char_name) \
                .replace("{char_seed}", str(char_seed)) \
                .replace("{char_desc}", char_desc)
            owned_reference_paths = resolve_character_reference_paths(char, storyboard)
            if owned_reference_paths:
                char_prompt += (
                    f"\n\nATTACHED CHARACTER REFERENCES ARE THE SINGLE SOURCE OF TRUTH (STRICT IDENTITY LOCK):\n"
                    f"Use the attached uploaded reference image as the strict identity reference for {char_name}. "
                    f"Preserve the exact identity of the person across all 9 panels:\n"
                    f"• Identical face structure and bone structure\n"
                    f"• Identical facial proportions\n"
                    f"• Identical skin tone and natural realistic skin texture\n"
                    f"• Preserve natural asymmetry and distinctive facial features\n"
                    f"• Do not beautify, reshape, smooth unnaturally, or alter the face\n"
                    f"• No age change; no hairstyle change unless explicitly requested\n"
                    f"• The same person must be immediately recognizable in every panel.\n"
                    f"Combine the views into one consistent identity; do not redesign, "
                    f"recolour, substitute, or borrow traits from any other character."
                )

            suppress_references = False
            request_seed = char_seed
            # A sheet failure is recoverable: keep rotating profiles and
            # rewriting the prompt before allowing the character stage to end.
            # Four attempts were too few for Flow's intermittent policy/session
            # failures and caused an incomplete cast to reach stage 2.
            max_character_attempts = max(12, len(seed_instances) * 4)
            for try_cnt in range(1, max_character_attempts + 1):
                if job_state.get("cancelled"):
                    job_state["status"] = "cancelled"
                    log_event(job_id, "🛑 Eksekusi dihentikan sebelum retry character sheet berikutnya.", level="warning")
                    _save_history()
                    return
                # Rotate through every currently connected Flow profile instead of
                # retrying an expired OAuth session on the same profile.
                live_seed_instances = [item for item in bridge.instance_snapshot()
                                       if item.get('connected') and item.get('ready', True) and item.get('logged_in', True)
                                       and not has_known_zero_flow_credits(item)]
                exact_live_seed_instances = [
                    item for item in live_seed_instances
                    if item.get('project_id') == project_id
                ]
                if project_id:
                    live_seed_instances = exact_live_seed_instances
                live_seed_instances = [item for item in live_seed_instances
                                       if not job_state.get('profile_failures', {}).get(
                                           item.get('instance_id'), {}
                                       ).get('quota_exhausted')]
                if live_seed_instances:
                    seed_target = live_seed_instances[(try_cnt - 1) % len(live_seed_instances)]
                    seed_instance_id = seed_target.get('instance_id')
                    seed_project_id = seed_target.get('project_id') or project_id
                else:
                    job_state["status"] = "waiting_for_quota"
                    job_state["error"] = (
                        f"Semua profil Flow kehabisan kredit saat membuat sheet '{char_name}'. "
                        "Hubungkan profil Flow lain atau isi ulang kredit, lalu Resume job."
                    )
                    log_event(job_id, f"⏸️ [TAHAP 1/3] {job_state['error']}", level="warning")
                    _save_history()
                    return
                try:
                    if owned_reference_paths and not suppress_references:
                        log_event(
                            job_id,
                            f"📸 [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Mengunggah {len(owned_reference_paths)} referensi gambar asli '{char_name}' ke Google Flow...",
                        )
                    reference_media_ids = await upload_character_references(
                        bridge, owned_reference_paths, seed_project_id, seed_instance_id
                    ) if owned_reference_paths and not suppress_references else []
                    if owned_reference_paths and not suppress_references and len(reference_media_ids) != len(owned_reference_paths):
                        raise RuntimeError(
                            f"Hanya {len(reference_media_ids)}/{len(owned_reference_paths)} referensi "
                            f"karakter '{char_name}' berhasil diunggah."
                        )
                    if reference_media_ids:
                        log_event(
                            job_id,
                            f"🧩 [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Memakai {len(reference_media_ids)} image reference "
                            f"khusus untuk karakter '{char_name}'.",
                        )
                    log_event(job_id, f"⏳ [{5 + c_idx}%] [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] [FLOW:INIT] Mengirim request character seed image '{char_name}' (Seed: {request_seed}, Profil: {seed_target.get('name') or seed_instance_id}) [Percobaan {try_cnt}/{max_character_attempts}]...")

                    def _on_char_progress(evt):
                        stage = evt.get("stage") or ""
                        msg = evt.get("message") or ""
                        pct = evt.get("percent") or (evt.get("data") or {}).get("percent")
                        pct_str = f" ({pct}%)" if pct is not None else ""
                        if msg:
                            log_event(job_id, f"⏳ [{5 + c_idx}%] [FLOW:{stage}] [Karakter: {char_name}] {msg}{pct_str}", profile=seed_target.get('name') or seed_instance_id)

                    if hasattr(bridge, "add_progress_listener"):
                        bridge.add_progress_listener(_on_char_progress)

                    try:
                        img_res = await generate_character_image(
                            bridge,
                            prompt=(char_prompt + build_visual_style_guard(visual_style, is_children)
                                    + build_finishing_look_guard(storyboard)),
                            aspect="landscape", project_id=seed_project_id,
                            instance_id=seed_instance_id,
                            reference_media_ids=reference_media_ids or None,
                            reference_image_paths=owned_reference_paths or None,
                            seed=request_seed,
                        )
                    finally:
                        if hasattr(bridge, "remove_progress_listener"):
                            bridge.remove_progress_listener(_on_char_progress)
                    if reference_media_ids and not img_res.get("reference_applied"):
                        raise RuntimeError(
                            f"Google Flow tidak menerapkan image reference karakter '{char_name}'."
                        )
                    media_id = img_res.get("media_id")
                    if media_id:
                        log_event(job_id, f"✨ [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Character sheet '{char_name}' berhasil digenerate di Flow (Media ID: {media_id[:16]}...). Mengunduh gambar master...", profile=seed_target.get('name') or seed_instance_id)
                        asset_cache.record(asset_key, status='download_pending', name=char_name,
                                           media_id=media_id, image_url=img_res.get('image_url'),
                                           project_id=seed_project_id, instance_id=seed_instance_id)
                        cached_sheet = await recover_character_master(asset_cache, asset_key, bridge, job_dir, job_id=job_id)
                        for alias in (char_id, str(char_id), char_name, char_name.lower()):
                            character_image_paths[alias] = cached_sheet
                        character_media_ids[char_id] = media_id
                        character_media_ids[str(char_id)] = media_id
                        character_media_ids[char_name] = media_id
                        character_media_ids[char_name.lower()] = media_id

                        img_url = img_res.get("image_url")
                        if img_url:
                            character_image_urls[char_id] = img_url
                            character_image_urls[str(char_id)] = img_url
                            character_image_urls[char_name] = img_url
                            character_image_urls[char_name.lower()] = img_url

                            log_event(job_id, f"💾 [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Master sheet '{char_name}' tersimpan di master cache film.")

                        log_event(job_id, f"✅ [TAHAP 1/3: Karakter {c_idx}/{len(characters)}] Gambar Seed Karakter '{char_name}' berhasil dibuat! Media ID: {media_id[:16]}...")
                        break
                except Exception as ex:
                    log_event(job_id, f"⚠️ Gagal generate seed image karakter '{char_name}' (Percobaan {try_cnt}): {ex}.", level="warning")
                    if job_state.get("cancelled"):
                        job_state["status"] = "cancelled"
                        _save_history()
                        return
                    # A successful Flow generation can be followed by a local
                    # download failure. Keep the durable Flow media handle and
                    # continue rendering instead of stopping before video.
                    cached_state = asset_cache.state(asset_key) or {}
                    if isinstance(ex, AssetRecoveryRequired) and cached_state.get("media_id"):
                        recovered_media_id = cached_state["media_id"]
                        for alias in (char_id, str(char_id), char_name, char_name.lower()):
                            character_media_ids[alias] = recovered_media_id
                        log_event(
                            job_id,
                            f"⚠️ Sheet lokal '{char_name}' belum terunduh, tetapi media ID Flow tersedia; "
                            "render video dilanjutkan memakai asset Flow.",
                            level="warning",
                        )
                        break
                    if isinstance(ex, AssetRecoveryRequired) or cached_state:
                        job_state['status'] = 'waiting_for_reference'
                        job_state['error'] = f"Sheet '{char_name}' sudah dibuat; pulihkan unduhan dengan Resume: {ex}"
                        log_event(job_id, job_state['error'], level='warning')
                        _save_history()
                        return
                    if "recaptcha" in str(ex).lower() or "unusual_activity" in str(ex).lower():
                        error_message = (
                            "Google Flow menolak verifikasi reCAPTCHA (aktivitas tidak biasa) pada profil yang dipakai. "
                            "Semua profil Flow aktif sudah dicoba; buka Flow manual, selesaikan verifikasi bila muncul, "
                            "tunggu beberapa menit, lalu Resume job."
                        )
                        alternate_count = sum(
                            1 for item in bridge.instance_snapshot()
                            if item.get('connected') and item.get('ready', True)
                            and item.get('logged_in', True)
                            and item.get('instance_id') != seed_instance_id
                        )
                        if try_cnt < max_character_attempts and alternate_count:
                            log_event(
                                job_id,
                                f"🔁 reCAPTCHA ditolak pada profil {seed_instance_id}; "
                                "otomatis mencoba akun Flow aktif berikutnya.",
                                level="warning",
                            )
                            continue
                        job_state["status"] = "waiting_for_login"
                        job_state["error"] = error_message
                        log_event(job_id, f"🛡️ {error_message}", level="error")
                        _save_history()
                        return
                    if is_flow_auth_error(ex):
                        error_message = (
                            "Sesi OAuth Google Flow kedaluwarsa. Token lama sudah ditolak Google; "
                            "buka Flow, lakukan satu generate manual agar extension menangkap token baru, "
                            "lalu klik Resume job. "
                            f"Flow Project ID yang dipakai: {seed_project_id or project_id or '(default session project)'}."
                        )
                        # OAuth failure is profile-specific. Give the next connected
                        # Flow profile a chance before pausing the whole job.
                        alternate_count = sum(
                            1 for item in bridge.instance_snapshot()
                            if item.get('connected') and item.get('ready', True)
                            and item.get('logged_in', True)
                            and item.get('instance_id') != seed_instance_id
                        )
                        if try_cnt < max_character_attempts and alternate_count:
                            log_event(
                                job_id,
                                f"🔁 OAuth gagal pada profil {seed_instance_id} / project {seed_project_id}; "
                                "otomatis mencoba profil Flow berikutnya.",
                                level="warning",
                            )
                            continue
                        job_state["status"] = "waiting_for_login"
                        job_state["error"] = error_message
                        log_event(job_id, f"🔐 {error_message}", level="error")
                        _save_history()
                        return
                    if "FLOW_UI_IMAGE_MODE_CONTROL_MISSING" in str(ex):
                        job_state["status"] = "waiting_for_reference"
                        job_state["error"] = (
                            "Flow tidak menyediakan kontrol Image pada composer aktif. "
                            "Reload extension/refresh tab Flow lalu Resume; prompt tidak di-retry karena ini error UI."
                        )
                        log_event(job_id, f"⏸️ [TAHAP 1/3] {job_state['error']}", level="warning")
                        _save_history()
                        return
                    if is_flow_quota_error(ex):
                        job_state.setdefault("profile_failures", {})[seed_instance_id] = {
                            "name": seed_target.get("name") if 'seed_target' in locals() else seed_instance_id,
                            "quota_exhausted": True,
                            "error": str(ex),
                            "stage": "character_sheet",
                        }
                        log_event(
                            job_id,
                            f"💳 Profil Flow {seed_instance_id} kehabisan kredit; otomatis pindah ke profil lain.",
                            level="warning",
                        )
                        continue
                    if try_cnt < max_character_attempts:
                        if is_unsafe_generation_error(ex):
                            if try_cnt == 1:
                                char_prompt = build_safe_character_seed_prompt(
                                    char_name, char_desc, char_seed,
                                    has_references=bool(owned_reference_paths),
                                )
                                log_event(
                                    job_id,
                                    f"🛡️ Filter keamanan Flow menolak nama/prompt '{char_name}'. "
                                    "Percobaan berikutnya menghapus nama inti dan memakai identitas visual netral.",
                                    level="warning",
                                )
                            elif try_cnt == 2:
                                suppress_references = True
                                char_prompt = build_safe_character_seed_prompt(
                                    char_name, char_desc, char_seed,
                                    distinct_reinterpretation=True,
                                )
                                log_event(
                                    job_id,
                                    f"🧬 Fallback netral '{char_name}' masih ditolak. Percobaan terakhir "
                                    "memakai reinterpretasi orisinal dengan palet/kostum berbeda dan tanpa "
                                    "referensi bermerek.",
                                    level="warning",
                                )
                            else:
                                suppress_references = True
                                request_seed = alternate_character_seed(char_seed)
                                char_prompt = build_safe_character_seed_prompt(
                                    char_name, char_desc, request_seed,
                                    minimal_reinterpretation=True,
                                )
                                log_event(
                                    job_id,
                                    f"🆘 Reinterpretasi '{char_name}' masih ditolak. Percobaan final "
                                    "memakai identitas manusia generik, prompt minimal, dan seed alternatif; "
                                    "hasil tetap dipetakan ke peran karakter asli.",
                                    level="warning",
                                )
                        elif try_cnt == 1:
                            char_prompt = build_safe_character_seed_prompt(
                                char_name, char_desc, char_seed,
                                has_references=bool(owned_reference_paths),
                            )
                            log_event(
                                job_id,
                                f"🔁 Generate sheet '{char_name}' gagal. Menulis ulang prompt otomatis "
                                "dengan sinonim yang lebih aman lalu mencoba lagi.",
                                level="warning",
                            )
                        elif try_cnt == 2:
                            suppress_references = True
                            char_prompt = build_safe_character_seed_prompt(
                                char_name, char_desc, char_seed,
                                distinct_reinterpretation=True,
                            )
                            log_event(
                                job_id,
                                f"🔁 Prompt alternatif kedua untuk sheet '{char_name}' dibuat otomatis; "
                                "profil Flow berikutnya akan dicoba.",
                                level="warning",
                            )
                        elif try_cnt % 3 == 0:
                            request_seed = alternate_character_seed(char_seed + try_cnt)
                            char_prompt = build_safe_character_seed_prompt(
                                char_name, char_desc, request_seed,
                                minimal_reinterpretation=True,
                            )
                            log_event(
                                job_id,
                                f"🔁 Sinonim/prompt dan seed alternatif untuk sheet '{char_name}' dibuat otomatis "
                                f"(percobaan {try_cnt}/{max_character_attempts}).",
                                level="warning",
                            )
                        await asyncio.sleep(2)

        missing_seeds = missing_character_seeds(characters, character_media_ids)
        if missing_seeds:
            missing_names = ", ".join(missing_seeds)
            # Character sheets are a hard prerequisite for both storyboard and
            # video references. Never enter stage 2 with only a partial cast:
            # that is how a scene gets generated with the wrong/one character.
            error_message = (
                "Character sheet belum selesai untuk: " + missing_names + ". "
                "Storyboard dan video ditahan; hubungkan/siapkan profil Flow lalu Resume."
            )
            job_state["status"] = "waiting_for_reference"
            job_state["error"] = error_message
            log_event(job_id, f"⛔ [TAHAP 1/3] {error_message}", level="error")
            _save_history()
            return

        if character_media_ids and not ref_media_id:
            ref_media_id = list(character_media_ids.values())[0]

        # The IDs above belong only to the profile/project that created or uploaded them.
        # Other accounts receive their own IDs lazily from the same durable local files.
        character_media_by_profile[profile_key(first_target_id, project_id)] = dict(character_media_ids)

    # Stage 2: Build every scene storyboard before any scene video is submitted.
    # The old implementation generated a storyboard and immediately rendered
    # that scene inside the same loop, which allowed scene 1 to enter Video
    # while scene 2 was still being created as Image. Keep the storyboard media
    # handles in memory and persist them on the scene records for Resume.
    storyboard_prebuilt: Dict[int, Dict[str, Any]] = {}
    if enable_scene_storyboard_image:
        job_state["execution_stage"] = "storyboards"
        job_state["execution_stage_total"] = total_scenes
        job_state["execution_stage_completed"] = 0
        log_event(job_id, f"🖼️ [TAHAP 2/3] Menyusun seluruh storyboard Image ({total_scenes} scene) sebelum Video dimulai...")
        from omniflash.generators import generate_character_image
        for sb_idx, sb_sc in enumerate(scenes, start=1):
            if job_state.get("cancelled"):
                job_state["status"] = "cancelled"
                _save_history()
                return
            sb_title = sb_sc.get("title", f"Adegan {sb_idx}")
            sb_duration = duration if force_uniform_duration else resolve_scene_duration(sb_sc, duration)
            existing_storyboard_id = sb_sc.get("storyboard_media_id")
            existing_storyboard_path = sb_sc.get("storyboard_sheet_path")
            log_event(job_id, f"🔍 [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] Memeriksa ketersediaan storyboard untuk adegan '{sb_title}'...")
            if existing_storyboard_id:
                storyboard_prebuilt[sb_idx] = {
                    "media_id": existing_storyboard_id,
                    "path": existing_storyboard_path if existing_storyboard_path and Path(existing_storyboard_path).exists() else None,
                    "image_url": sb_sc.get("storyboard_image_url"),
                }
                if project_instance_id and project_id:
                    storyboard_media_by_profile[(sb_idx, profile_key(project_instance_id, project_id))] = existing_storyboard_id
                log_event(
                    job_id,
                    f"♻️ [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] Storyboard adegan {sb_idx}/{total_scenes} sudah tersimpan (Media ID: {existing_storyboard_id[:16]}...); tidak generate ulang.",
                )
                job_state["execution_stage_completed"] = sb_idx
                continue
            sb_prompt = sb_sc.get("prompt_for_flow", "")
            sb_prompt = enforce_spoken_language_lock(sb_prompt, sb_sc, storyboard.get("target_lang") or "")
            sb_prompt = apply_no_branding_direction(sb_prompt)
            sb_prompt += build_visual_style_guard(visual_style, is_children)
            sb_prompt += build_finishing_look_guard(storyboard)
            sb_prompt += build_scene_blueprint_guard(sb_sc)
            sb_prompt += build_render_realism_guard(storyboard)
            sb_prompt += build_physical_execution_guard(sb_sc, prompt=sb_sc.get("prompt_for_flow") or "")

            sb_candidates = await usable_flow_profiles(bridge, [
                item for item in bridge.instance_snapshot()
                if item.get("connected") and item.get("ready", True)
                and item.get("logged_in", True)
                and not has_known_zero_flow_credits(item)
                and not job_state.get("profile_failures", {}).get(
                    item.get("instance_id"), {}
                ).get("quota_exhausted")
            ])
            # A Flow media ID is project-scoped. Never send a storyboard's
            # character IDs through a connected profile from another project;
            # that path produces misleading API-key/401 errors. Fail over only
            # among profiles that belong to the requested project.
            exact_sb_candidates = [
                item for item in sb_candidates
                if item.get("project_id") == origin_project_id
            ]
            if origin_project_id:
                sb_candidates = exact_sb_candidates
            sb_candidates.sort(
                key=lambda item: item.get("instance_id")
                != choose_instance_for_project(sb_candidates, project_id)
            )
            if not sb_candidates:
                raise RuntimeError(
                    f"Storyboard scene {sb_idx} ditahan: tidak ada profil Flow dengan kredit yang tersedia. "
                    "Hubungkan profil lain atau isi ulang kredit, lalu Resume job."
                )
            sb_res = None
            sb_last_error = None
            for sb_profile in sb_candidates or [{}]:
                sb_target_id = sb_profile.get("instance_id") or choose_instance_for_project(
                    bridge.instance_snapshot(), project_id
                )
                sb_project_id = sb_profile.get("project_id") or project_id
                try:
                    same_origin_storyboard_profile = (
                        sb_target_id == origin_instance_id
                        and sb_project_id == origin_project_id
                        and all(
                            c.get("media_id")
                            for c in resolve_scene_characters(sb_sc, characters, character_media_ids)
                        )
                    )
                    if same_origin_storyboard_profile:
                        # Reuse the IDs produced by the character stage. This
                        # avoids an unnecessary upload on Resume/new storyboard
                        # attempts in the same Flow project.
                        sb_character_media_ids = character_media_ids
                    else:
                        sb_character_media_ids, _ = await ensure_character_media_for_profile(
                            bridge, characters, character_image_paths, sb_project_id, sb_target_id,
                            character_media_by_profile, upload_fn=upload_image,
                        )
                    sb_chars = resolve_scene_characters(sb_sc, characters, sb_character_media_ids)
                    sb_ref_ids = [c["media_id"] for c in sb_chars if c.get("media_id")]
                    sb_ref_paths = []
                    for c in sb_chars:
                        cid = c.get("id")
                        cname = str(c.get("name") or "").lower()
                        src = (
                            character_image_paths.get(cid)
                            or character_image_paths.get(str(cid))
                            or character_image_paths.get(cname)
                        )
                        if src and Path(src).is_file():
                            sb_ref_paths.append(str(src))

                    profile_prompt = (
                        sb_prompt
                        + build_sheet_manifest(sb_chars)
                        + f"\n\nSCENE STORYBOARD ONLY: Create exactly one textless multi-angle "
                        f"storyboard contact sheet for scene {sb_idx}, titled '{sb_title}'. "
                        "This is an Image asset, not a video. Do not generate motion or video output."
                    )
                    def _on_sb_progress(evt):
                        stage = evt.get("stage") or ""
                        msg = evt.get("message") or ""
                        pct = evt.get("percent") or (evt.get("data") or {}).get("percent")
                        pct_str = f" ({pct}%)" if pct is not None else ""
                        if msg:
                            log_event(job_id, f"⏳ [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] [FLOW:{stage}] {msg}{pct_str}", profile=sb_profile.get('name') or sb_target_id)

                    for sb_try in range(1, 4):
                        try:
                            log_event(
                                job_id,
                                f"🖼️ [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] Mengirim request storyboard Image ke profil {sb_profile.get('name') or sb_target_id} "
                                f"({sb_target_id}, project {sb_project_id}) "
                                f"[Percobaan {sb_try}/3]...",
                                profile=sb_profile.get('name') or sb_target_id,
                            )
                            if hasattr(bridge, "add_progress_listener"):
                                bridge.add_progress_listener(_on_sb_progress)
                            try:
                                sb_res = await generate_character_image(
                                    bridge, prompt=profile_prompt, aspect="landscape",
                                    project_id=sb_project_id, instance_id=sb_target_id,
                                    reference_media_ids=sb_ref_ids,
                                    reference_image_paths=sb_ref_paths,
                                    seed=storyboard.get("character_seed"),
                                )
                            finally:
                                if hasattr(bridge, "remove_progress_listener"):
                                    bridge.remove_progress_listener(_on_sb_progress)
                            if sb_res.get("media_id"):
                                log_event(job_id, f"✨ [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] Storyboard Image berhasil dibuat di Flow (Media ID: {sb_res.get('media_id')[:16]}...). Mengunduh gambar...", profile=sb_profile.get('name') or sb_target_id)
                                break
                        except Exception as ex:
                            sb_last_error = ex
                            log_event(
                                job_id,
                                f"⚠️ [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] Storyboard di profil "
                                f"{sb_profile.get('name') or sb_target_id} gagal ({ex})",
                                level="warning",
                                profile=sb_profile.get('name') or sb_target_id,
                            )
                            # Authentication/session failures are profile state,
                            # not prompt failures. Do not waste three storyboard
                            # attempts against the same expired session.
                            if is_flow_auth_error(ex):
                                break
                            if sb_try < 3:
                                await asyncio.sleep(2.5)
                    if sb_res and sb_res.get("media_id"):
                        break
                    if sb_last_error and is_flow_quota_error(sb_last_error):
                        job_state.setdefault("profile_failures", {})[sb_target_id] = {
                            "name": sb_profile.get("name") or sb_target_id,
                            "quota_exhausted": True,
                            "error": str(sb_last_error),
                            "stage": "storyboard",
                        }
                        continue
                except Exception as ex:
                    sb_last_error = ex
                    log_event(
                        job_id,
                        f"⚠️ Profil storyboard {sb_profile.get('name') or sb_target_id} "
                        f"tidak tersedia ({ex}); mencoba profil berikutnya.",
                        level="warning",
                    )
                    if is_flow_quota_error(ex):
                        job_state.setdefault("profile_failures", {})[sb_target_id] = {
                            "name": sb_profile.get("name") or sb_target_id,
                            "quota_exhausted": True,
                            "error": str(ex),
                            "stage": "storyboard",
                        }
                    continue
            if not sb_res or not sb_res.get("media_id"):
                if sb_last_error and is_flow_auth_error(sb_last_error):
                    job_state["status"] = "waiting_for_login"
                    job_state["error"] = (
                        "Semua profil Flow menolak autentikasi saat melampirkan "
                        "reference storyboard. Buka Flow pada profil yang login, "
                        "lakukan satu generate manual, lalu Resume; sheet cache "
                        "tidak akan dibuat ulang."
                    )
                    log_event(job_id, f"⏸️ [TAHAP 2/3] {job_state['error']}", level="warning")
                    _save_history()
                    return
                log_event(
                    job_id,
                    f"⚠️ [TAHAP 2/3] Storyboard Image scene {sb_idx}/{total_scenes} dilewati ({sb_last_error or 'Image fallback tidak tersedia'}); melanjutkan langsung dengan referensi karakter...",
                    level="warning",
                )
                job_state["execution_stage_completed"] = sb_idx
                continue

            sb_path = job_dir / f"storyboard_{sb_idx:02d}.png"
            if sb_res.get("image_url"):
                log_event(job_id, f"📥 [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] Mengunduh file gambar storyboard ({sb_path.name})...")
                try:
                    await download_file(
                        bridge, sb_res["image_url"], sb_path,
                        instance_id=sb_target_id, media_id=sb_res.get("media_id"),
                        project_id=sb_project_id, media_kind="image",
                        job_id=job_id, label=f"Storyboard Adegan {sb_idx}",
                    )
                except Exception as dl_err:
                    log_event(job_id, f"⚠️ Unduhan langsung storyboard adegan {sb_idx} gagal ({dl_err}); mencoba alternatif fetch...", level="warning")
                    got = await asyncio.to_thread(fetch_image_bytes, sb_res["image_url"])
                    if got and got.get("data"):
                        sb_path.write_bytes(got["data"])
            if sb_path.exists() and sb_path.stat().st_size > 0:
                size_kb = sb_path.stat().st_size / 1024
                size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
                log_event(job_id, f"💾 [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] Gambar storyboard tersimpan ({size_str}).")
            storyboard_prebuilt[sb_idx] = {
                "media_id": sb_res["media_id"],
                "path": str(sb_path) if sb_path.exists() else None,
                "image_url": sb_res.get("image_url"),
            }
            storyboard_media_by_profile[(sb_idx, profile_key(sb_target_id, sb_project_id))] = sb_res["media_id"]
            sb_sc["storyboard_media_id"] = sb_res["media_id"]
            sb_sc["storyboard_sheet_path"] = str(sb_path) if sb_path.exists() else None
            sb_sc["storyboard_image_url"] = sb_res.get("image_url")
            job_state["execution_stage_completed"] = sb_idx
            log_event(job_id, f"✅ [TAHAP 2/3: Adegan {sb_idx}/{total_scenes}] Storyboard adegan selesai sebagai 1 Image. Belum mengirim Video.")
        _save_history()

    # The legacy inline storyboard block below is disabled after the global
    # storyboard phase; its media handles are injected from storyboard_prebuilt
    # so each scene is still rendered exactly once in the Video phase.
    enable_scene_storyboard_image = False

    # Step 3: Render each scene video across connected Chrome profiles, only
    # after every storyboard above has completed.
    log_event(job_id, f"🎬 [TRANSISI TAHAP 2 ➔ 3] Seluruh {total_scenes} storyboard Image siap! Memulai perenderan Video Adegan 1..{total_scenes}...")
    job_state["execution_stage"] = "videos"
    job_state["execution_stage_total"] = total_scenes
    job_state["execution_stage_completed"] = 0
    completed_scene_paths = []
    rendered_in_batch = 0
    batch_paused = False
    music_video_mode = bool(storyboard.get("music_track_path"))
    continuity_media_id = None
    continuity_scene_number = None
    continuity_instance_id = None
    continuity_project_id = None
    continuity_local_path = None
    affiliate_scene_numbers = resolve_affiliate_scene_numbers(
        total_scenes, affiliate_product.get("scene_position", "auto")
    ) if affiliate_product.get("enabled") else set()

    # Flow is more reliable when a long film is dispatched in small background
    # waves.  This is an execution throttle only: storyboard content and prompts
    # remain unchanged.  An explicit render_scene_limit still keeps its old
    # quota/checkpoint behavior; otherwise use the automatic six-scene waves.
    automatic_batch_size = 6 if render_scene_limit is None else None
    automatic_batch_number = 0

    def scan_rendered_batch() -> List[str]:
        """Rescan durable MP4 outputs before starting the next background wave."""
        found = []
        for scene_number in range(1, total_scenes + 1):
            candidate = job_dir / f"scene_{scene_number:02d}.mp4"
            if candidate.exists() and candidate.stat().st_size > 1024:
                found.append(str(candidate))
        return found

    for idx, sc in enumerate(scenes, start=1):
        if automatic_batch_size and rendered_in_batch >= automatic_batch_size:
            automatic_batch_number += 1
            delay = random.uniform(2.0, 4.0)
            log_event(
                job_id,
                f"⏸️ Batch background {automatic_batch_number} selesai ({automatic_batch_size} scene). "
                f"Menunggu {delay:.1f} detik sebelum scan hasil dan melanjutkan...",
            )
            await asyncio.sleep(delay)
            scanned_paths = scan_rendered_batch()
            completed_scene_paths = list(dict.fromkeys(completed_scene_paths + scanned_paths))
            log_event(
                job_id,
                f"🔎 Scan batch selesai: {len(scanned_paths)}/{total_scenes} file scene valid ditemukan. "
                f"Melanjutkan batch berikutnya di background.",
            )
            rendered_in_batch = 0
            job_state["rendered_in_batch"] = 0
            job_state["last_batch_scan_count"] = len(scanned_paths)
            _save_history()

        if job_state.get("cancelled"):
            log_event(job_id, "🛑 Eksekusi job dihentikan oleh pengguna.", level="warning")
            job_state["status"] = "cancelled"
            _save_history()
            return

        job_state["current_scene"] = idx
        scene_title = sc.get("title", f"Adegan {idx}")
        is_affiliate_scene = bool(sc.get("affiliate_scene")) or idx in affiliate_scene_numbers
        prompt = sc.get("prompt_for_flow", "")
        prompt = enforce_spoken_language_lock(prompt, sc, storyboard.get("target_lang") or "")
        scene_duration = duration if force_uniform_duration else resolve_scene_duration(sc, duration)
        if scene_duration == 10 and not storyboard.get("script_mode"):
            shot_count = choose_shot_count(sc, prompt)
            log_event(
                job_id,
                f"⚡ [Adegan {idx}/{total_scenes}] Menyusun {shot_count} shot/mini-beat multi-angle yang padat...",
            )
            pacing_scene = dict(sc)
            if idx > 1:
                previous_scene = scenes[idx - 2]
                pacing_scene["previous_scene_title"] = previous_scene.get("title") or ""
                pacing_scene["previous_scene_action"] = previous_scene.get("action_summary") or ""
                pacing_scene["previous_scene_prompt"] = previous_scene.get("prompt_for_flow") or ""
                pacing_scene["previous_scene_end_state"] = previous_scene.get("end_state") or ""
            prompt, pacing_provider = await asyncio.to_thread(
                rewrite_dense_prompt_with_ai,
                prompt,
                pacing_scene,
                scene_duration,
                children_mode=is_children,
                target_lang=storyboard.get("target_lang") or "",
            )
            log_event(
                job_id,
                f"✅ [Adegan {idx}/{total_scenes}] Prompt padat selesai via {pacing_provider}: "
                f"{shot_count} shot berbeda, aksi berantai, dialog terkunci, dan kontinuitas tersambung.",
            )

        prompt = enforce_spoken_language_lock(prompt, sc, storyboard.get("target_lang") or "")
        speaker_lock = build_speaker_lock(sc, characters)
        wardrobe_lock = build_character_wardrobe_lock(sc, characters)
        if speaker_lock:
            prompt = f"{prompt.rstrip()}\n\n{speaker_lock}"
        if wardrobe_lock:
            prompt = f"{prompt.rstrip()}\n\n{wardrobe_lock}"

        prompt = apply_scene_audio_direction(
            prompt, sc, storyboard, music_video=music_video_mode
        )
        prompt = apply_no_branding_direction(prompt)
        # Sanitize the complete, AI-rewritten scene—not only the base template. This
        # prevents a late scene prompt from reintroducing photoreal/live-action terms
        # into an anime, cartoon, comic, watercolor, or other stylized production.
        prompt = adapt_template_for_visual_style(prompt, visual_style, is_children)
        # Re-assert after AI pacing rewrites so no later stage can silently change medium.
        prompt += build_visual_style_guard(visual_style, is_children)
        prompt += build_finishing_look_guard(storyboard)
        prompt += "\n\nREFERENCE TEXT EXCLUSION LOCK: Any name, seed number, label, title bar, UI box, caption, border, or printed metadata visible in reference images is not part of the scene. Never render it, copy it, float it, overlay it, or turn it into a sign/card/subtitle. The final video frame must contain only the cinematic scene and physical story objects. No readable text unless explicitly required by the story, and even then use blurred/unreadable marks instead of words."

        out_filename = f"scene_{idx:02d}.mp4"
        out_path = job_dir / out_filename

        # A quota batch limits only NEW scene videos. Existing files are always discovered
        # and included for free, so resume never spends a slot on completed work.
        if (
            render_scene_limit is not None
            and rendered_in_batch >= render_scene_limit
            and not (out_path.exists() and out_path.stat().st_size > 1024)
        ):
            batch_paused = True
            job_state["next_scene"] = idx
            remaining = total_scenes - idx + 1
            log_event(
                job_id,
                f"⏸️ Batas batch {render_scene_limit} scene baru tercapai. "
                f"Tersisa {remaining} scene; isi slot batch berikutnya lalu Resume.",
                level="warning",
            )
            break

        scene_record = {
            "scene_number": idx,
            "title": scene_title,
            "prompt": prompt,
            "status": "rendering",
            "duration": scene_duration,
            "video_path": None,
            "profile_used": None,
        }
        prebuilt_storyboard = storyboard_prebuilt.get(idx) or {}
        if prebuilt_storyboard:
            scene_record["storyboard_media_id"] = prebuilt_storyboard.get("media_id")
            if prebuilt_storyboard.get("path"):
                scene_record["storyboard_sheet_url"] = (
                    f"/storage/jobs/{job_id}/{Path(prebuilt_storyboard['path']).name}"
                )
        job_state["scenes"].append(scene_record)

        if out_path.exists() and out_path.stat().st_size > 1024:
            log_event(job_id, f"⏩ [Adegan {idx}/{total_scenes}] Video adegan sudah selesai sebelumnya ({out_filename}). Melanjutkan adegan berikutnya...")
            scene_record["status"] = "completed"
            scene_record["video_path"] = str(out_path)
            scene_record["video_url"] = f"/storage/jobs/{job_id}/{out_filename}"
            completed_scene_paths.append(str(out_path))

            last_frame_path = job_dir / f"scene_{idx:02d}_last_frame.jpg"
            if not last_frame_path.exists():
                try:
                    await asyncio.to_thread(extract_last_frame, str(out_path), str(last_frame_path))
                except Exception:
                    pass
            if last_frame_path.exists() and enable_continuity_frames:
                try:
                    continuity_instance_id = choose_instance_for_project(bridge.instance_snapshot(), project_id)
                    continuity_media_id = await upload_image(
                        bridge, str(last_frame_path), project_id=project_id, instance_id=continuity_instance_id
                    )
                    continuity_local_path = str(last_frame_path)
                    continuity_scene_number = idx
                    log_event(job_id, f"🔗 [Adegan {idx}/{total_scenes}] Frame akhir siap menjadi pembuka adegan {idx + 1}.")
                except Exception:
                    pass

            job_state["current_scene"] = idx
            continue

        snap_instances = await usable_flow_profiles(bridge, [
            i for i in bridge.instance_snapshot()
            if i["connected"] and i.get("ready", True) and i.get("logged_in", True)
            and not has_known_zero_flow_credits(i)
            and not job_state.get("profile_failures", {}).get(i.get("instance_id"), {}).get("quota_exhausted")
        ])
        if origin_project_id:
            snap_instances = [
                item for item in snap_instances
                if item.get("project_id") == origin_project_id
            ]
        snap_instances.sort(key=lambda item: item.get("instance_id") != project_instance_id)
        if not snap_instances:
            log_event(job_id, f"❌ [Adegan {idx}/{total_scenes}] Gagal: Tidak ada akun profil Chrome terhubung yang siap (ready).", level="error")
            scene_record["status"] = "failed"
            scene_record["error"] = "Tidak ada profil Chrome ready."
            continue

        scene_success = False
        last_error = None
        rendered_in_batch += 1
        job_state["rendered_in_batch"] = rendered_in_batch

        # Step 1.5: Generate ONE storyboard key-frame reference image for this scene (composition/blocking/lighting),
        # used ALONGSIDE the character seed image(s) as a second reference for the video render below.
        storyboard_media_id = prebuilt_storyboard.get("media_id")
        storyboard_sheet_path = prebuilt_storyboard.get("path")
        if prebuilt_storyboard:
            log_event(
                job_id,
                f"⏭️ [TAHAP 3/3] Storyboard scene {idx}/{total_scenes} sudah siap; "
                "sekarang baru masuk ke Video.",
            )
        if enable_scene_storyboard_image:
            # Cartoon sheets are an explicit production mode. Keyword guessing caused
            # live-action drama characters to be rendered as illustrations.
            is_cartoon = is_children
            scene_storyboard_template = (settings.CHILDREN_SCENE_STORYBOARD_TEMPLATE if is_cartoon
                                         else (cfg.get("scene_storyboard_template") or settings.DEFAULT_SCENE_STORYBOARD_TEMPLATE))
            sb_fields = {
                "{scene_action}": sc.get("action_summary") or prompt,
                "{camera_movement}": sc.get("camera_movement") or "",
                "{art_direction}": storyboard.get("art_direction") or storyboard.get("genre_style") or "",
                "{scene_title}": scene_title,
                "{scene_number}": str(idx),
                "{scene_duration}": str(scene_duration),
                "{shot_type}": sc.get("shot_type") or "",
            }
            storyboard_prompt = scene_storyboard_template
            for token, value in sb_fields.items():
                storyboard_prompt = storyboard_prompt.replace(token, value)
            storyboard_prompt = adapt_template_for_visual_style(storyboard_prompt, visual_style, is_children)
            storyboard_prompt += build_visual_style_guard(visual_style, is_children)
            storyboard_prompt += build_finishing_look_guard(storyboard)
            storyboard_prompt += (
                "\n\nPHYSICAL BLOCKING PRIORITY: " + scene_execution_context(sc)
                + "\nPanels represent successive physical states, not compulsory camera cuts. "
                "Keep camera side, hinge, handle, hand and actor inside/outside consistent. "
                "For door/contact actions, retain a medium three-quarter view showing hand, door edge "
                "and body clearance throughout reach/contact/movement/release; this overrides any "
                "generic panel-angle rotation above. Never depict a hand through glass or a body in the door sweep."
            )
            _sb_manifest_slot = True  # manifest appended once the sheet list is known
            sb_target_id = choose_instance_for_project(bridge.instance_snapshot(), project_id)

            sb_character_media_ids = character_media_ids
            uploaded_names = []
            if enable_seed_image:
                sb_character_media_ids, uploaded_names = await ensure_character_media_for_profile(
                    bridge, characters, character_image_paths, project_id, sb_target_id,
                    character_media_by_profile, upload_fn=upload_image,
                )
            if uploaded_names:
                log_event(
                    job_id,
                    f"🔄 [Adegan {idx}/{total_scenes}] Character sheet diunggah ke profil storyboard: "
                    + ", ".join(uploaded_names),
                )

            # Feed the character sheets in as references, otherwise the panel invents new
            # faces and wardrobe and every scene ends up with different-looking characters.
            sb_chars = resolve_scene_characters(sc, storyboard.get("characters") or [], sb_character_media_ids)
            sb_ref_ids = [c["media_id"] for c in sb_chars]
            if is_affiliate_scene:
                sb_product_ids, _ = await ensure_files_for_profile(
                    bridge, affiliate_product.get("reference_paths") or [], project_id, sb_target_id,
                    file_media_by_profile, upload_fn=upload_image,
                )
                sb_ref_ids.extend(sb_product_ids)
            storyboard_prompt += build_sheet_manifest(sb_chars)

            who = ", ".join(f"{c['name']} ({c['matched_by']})" for c in sb_chars) or "tanpa karakter"

            # Preferred route: let Gemini compose the sheet from the real character images.
            # Its image models accept picture inputs officially, so the faces are genuinely
            # carried over instead of being re-invented from a text description.
            if sb_chars and should_try_gemini_storyboard_image(cfg):
                try:
                    log_event(job_id, f"🖼️ [Adegan {idx}/{total_scenes}] Menyusun storyboard via Gemini "
                                      f"dari character sheet: {who}...")
                    refs = []
                    for c in sb_chars:
                        cid = c.get("id")
                        cname = str(c.get("name") or "").lower()
                        src = (character_image_paths.get(cid) or 
                               character_image_paths.get(str(cid)) or 
                               character_image_paths.get(cname) or 
                               character_image_urls.get(cid) or 
                               character_image_urls.get(str(cid)) or 
                               character_image_urls.get(cname))
                        if src:
                            got = await asyncio.to_thread(fetch_image_bytes, src)
                            if got:
                                refs.append(got)
                    if is_affiliate_scene:
                        for product_path in affiliate_product.get("reference_paths") or []:
                            got = await asyncio.to_thread(fetch_image_bytes, product_path)
                            if got:
                                refs.append(got)

                    sheet = {"image": None, "error": "Character sheet tidak dapat diunduh dari Flow"}
                    if refs:
                        sheet = await asyncio.to_thread(
                            generate_storyboard_sheet, storyboard_prompt, refs
                        )

                    if sheet.get("image"):
                        sheet_path = job_dir / f"storyboard_{idx:02d}.png"
                        sheet_path.write_bytes(sheet["image"])
                        storyboard_sheet_path = str(sheet_path)
                        storyboard_media_id = await upload_image(
                            bridge, str(sheet_path), project_id=project_id, instance_id=sb_target_id
                        )
                        scene_record["storyboard_sheet_url"] = f"/storage/jobs/{job_id}/{sheet_path.name}"
                        log_event(job_id, f"✅ [Adegan {idx}/{total_scenes}] Storyboard tersusun MENGIKUTI "
                                          f"{len(refs)} character sheet via {sheet.get('model')} & terunggah ke Flow! "
                                          f"Media ID: {storyboard_media_id[:16]}...")
                    else:
                        # Never fail silently: the reason decides whether the faces stay consistent.
                        log_event(job_id, f"⚠️ [Adegan {idx}/{total_scenes}] Gemini tidak dapat menyusun storyboard "
                                          f"({sheet.get('error')}). Beralih ke jalur cadangan...", level="warning")
                except Exception as ex:
                    log_event(job_id, f"⚠️ [Adegan {idx}/{total_scenes}] Penyusunan storyboard via Gemini gagal: {ex}. "
                                      f"Beralih ke jalur cadangan...", level="warning")
            elif sb_chars:
                log_event(
                    job_id,
                    f"⏭️ [Adegan {idx}/{total_scenes}] Provider utama "
                    f"{str(cfg.get('default_text_provider') or '').title()}; melewati Gemini Image "
                    "dan langsung memakai Google Flow.",
                )

            # Fallback: compose the sheet inside Flow itself when the Gemini route was
            # unavailable (no API key, download failed, or every image model refused).
            if enable_scene_storyboard_image and not storyboard_media_id:
                for sb_try in range(1, 4):
                    try:
                        log_event(job_id, f"🖼️ [Adegan {idx}/{total_scenes}] Membuat gambar storyboard adegan di Google Flow [Percobaan {sb_try}/3] — melampirkan sheet: {who}...")
                        from omniflash.generators import generate_character_image
                        sb_img_res = await generate_character_image(
                            bridge, prompt=storyboard_prompt, aspect="landscape", project_id=project_id,
                            instance_id=sb_target_id, reference_media_ids=sb_ref_ids,
                            seed=storyboard.get("character_seed"),
                        )
                        sb_media = sb_img_res.get("media_id")
                        if sb_media:
                            storyboard_media_id = sb_media
                            if sb_img_res.get("image_url"):
                                scene_record["storyboard_sheet_url"] = sb_img_res["image_url"]
                                sheet_got = await asyncio.to_thread(fetch_image_bytes, sb_img_res["image_url"])
                                if not sheet_got or not sheet_got.get("data"):
                                    try:
                                        private_sheet = await bridge.download_url(
                                            sb_img_res["image_url"], instance_id=sb_target_id, timeout=120
                                        )
                                        if private_sheet.get("data"):
                                            sheet_got = {"data": private_sheet["data"]}
                                    except Exception:
                                        pass
                                if sheet_got and sheet_got.get("data"):
                                    sheet_path = job_dir / f"storyboard_{idx:02d}.png"
                                    sheet_path.write_bytes(sheet_got["data"])
                                    storyboard_sheet_path = str(sheet_path)
                                    scene_record["storyboard_sheet_url"] = f"/storage/jobs/{job_id}/{sheet_path.name}"
                            if sb_img_res.get("reference_applied"):
                                log_event(job_id, f"✅ [Adegan {idx}/{total_scenes}] Gambar storyboard berhasil dibuat MENGIKUTI "
                                                  f"{sb_img_res.get('reference_count')} character sheet! Media ID: {storyboard_media_id[:16]}...")
                            else:
                                log_event(job_id, f"✅ [Adegan {idx}/{total_scenes}] Gambar storyboard berhasil dibuat di Google Flow (Media ID: {storyboard_media_id[:16]}...).")
                            break
                        else:
                            raise RuntimeError("Google Flow tidak mengembalikan media_id gambar storyboard.")
                    except Exception as ex:
                        log_event(job_id, f"⚠️ [Adegan {idx}/{total_scenes}] Percobaan {sb_try}/3 membuat gambar storyboard: {ex}", level="warning")
                        if sb_try < 3:
                            await asyncio.sleep(2.5)
                        else:
                            log_event(job_id, f"⚠️ [Adegan {idx}/{total_scenes}] Storyboard tidak dapat dibuat setelah 3x percobaan. Melanjutkan hanya dengan referensi karakter...", level="warning")

        # Google Flow can reject either wording or a reference image on content policy.
        # Rewrite first, then progressively reduce references so one false-positive image
        # cannot leave the whole film waiting at 95%.
        max_policy_rewrites = int(cfg.get("max_policy_rewrites", 5) or 5)
        policy_attempt = 0
        drop_all_scene_references = False
        scene_characters_for_retry = resolve_scene_characters(
            sc, storyboard.get("characters") or [], character_media_ids
        )
        available_continuity_id = continuity_start_image(
            continuity_media_id, continuity_scene_number, idx
        )

        while True:
            policy_rejection = None

            if available_continuity_id and continuity_instance_id:
                candidate_instances = sorted(
                    snap_instances,
                    key=lambda item: item.get("instance_id") != continuity_instance_id,
                )
            else:
                start_idx = (idx - 1) % len(snap_instances)
                candidate_instances = snap_instances[start_idx:] + snap_instances[:start_idx]

            # Character/storyboard media and continuity media are project
            # scoped. Keep Video on the owning project whenever that project
            # has a connected candidate; do not fail over into another
            # account/project with foreign media IDs.
            required_project_id = (
                continuity_project_id
                if available_continuity_id and continuity_project_id
                else origin_project_id
            )
            exact_video_candidates = [
                item for item in candidate_instances
                if item.get("project_id") == required_project_id
            ]
            if exact_video_candidates:
                candidate_instances = exact_video_candidates

            for chosen in candidate_instances:
                if job_state.get("cancelled"):
                    break

                target_instance_id = chosen["instance_id"]
                target_name = chosen["name"]
                owns_continuity = (
                    available_continuity_id
                    and not drop_all_scene_references
                    and target_instance_id == continuity_instance_id
                )
                inst_project_id = (
                    continuity_project_id if owns_continuity else None
                ) or chosen.get("project_id") or flow_project_id or project_id or settings.get_flow_project_id()

                log_event(job_id, f"🚀 [Adegan {idx}/{total_scenes}: '{scene_title}'] [{target_name}] Mengirim prompt video {scene_duration}s ke Google Flow (Model: abra_t2v_{scene_duration}s, Ratio: {aspect_ratio})...", profile=target_name)
                scene_record["profile_used"] = target_name

                try:
                    media_ids = None
                    profile_character_ids = character_media_ids
                    uploaded_names = []
                    # Always initialize this before any reference upload.  An upload
                    # failure must be handled by the profile failover path, not turn
                    # the whole job into an untracked UnboundLocalError.
                    profile_continuity_id = None
                    if enable_seed_image:
                        # The original generation profile already owns these Flow
                        # media IDs. Re-uploading its local mirrors on every Resume
                        # is unnecessary and can fail behind Flow's upload CORS.
                        # Other profiles still go through the normal upload/failover
                        # path below.
                        same_origin_profile = (
                            target_instance_id == origin_instance_id
                            and inst_project_id == origin_project_id
                            and all(
                                c.get("media_id")
                                for c in resolve_scene_characters(sc, characters, character_media_ids)
                            )
                        )
                        if not same_origin_profile:
                            profile_character_ids, uploaded_names = await ensure_character_media_for_profile(
                                bridge, characters, character_image_paths, inst_project_id, target_instance_id,
                                character_media_by_profile, upload_fn=upload_image,
                            )
                        else:
                            log_event(
                                job_id,
                                f"♻️ [Adegan {idx}/{total_scenes}] Memakai media ID character sheet dari Flow project asal; tidak upload ulang.",
                                profile=target_name,
                            )
                    if uploaded_names:
                        log_event(
                            job_id,
                            f"🔄 Character sheet otomatis dipindahkan ke {target_name}: "
                            + ", ".join(uploaded_names),
                            profile=target_name,
                        )
                    v_chars = resolve_scene_characters(
                        sc, storyboard.get("characters") or [], profile_character_ids
                    )
                    character_ref_ids = [c["media_id"] for c in v_chars if c.get("media_id")]
                    profile_storyboard_media_id = storyboard_media_by_profile.get(
                        (idx, profile_key(target_instance_id, inst_project_id))
                    )
                    if (
                        not profile_storyboard_media_id
                        and target_instance_id == origin_instance_id
                        and inst_project_id == origin_project_id
                    ):
                        # Resume may reconstruct storyboard_prebuilt from the
                        # durable scene record without rebuilding the in-memory
                        # per-profile map. The media ID is already owned by this
                        # same Flow project, so reuse it instead of uploading the
                        # local PNG again.
                        profile_storyboard_media_id = (
                            storyboard_prebuilt.get(idx, {}).get("media_id")
                            or sc.get("storyboard_media_id")
                        )
                        if profile_storyboard_media_id:
                            storyboard_media_by_profile[
                                (idx, profile_key(target_instance_id, inst_project_id))
                            ] = profile_storyboard_media_id
                            log_event(
                                job_id,
                                f"♻️ [Adegan {idx}/{total_scenes}] Memakai media ID storyboard Image dari Flow project asal; tidak upload ulang.",
                                profile=target_name,
                            )
                    if storyboard_sheet_path and not profile_storyboard_media_id:
                        uploaded_storyboard_ids, uploaded_count = await ensure_files_for_profile(
                            bridge, [storyboard_sheet_path], inst_project_id, target_instance_id,
                            file_media_by_profile, upload_fn=upload_image,
                        )
                        profile_storyboard_media_id = uploaded_storyboard_ids[0] if uploaded_storyboard_ids else None
                        if profile_storyboard_media_id:
                            storyboard_media_by_profile[(idx, profile_key(target_instance_id, inst_project_id))] = profile_storyboard_media_id
                        if uploaded_count:
                            log_event(
                                job_id,
                                f"🔄 Storyboard sheet adegan {idx} diunggah ke {target_name}.",
                                profile=target_name,
                            )
                    profile_product_ids = []
                    if is_affiliate_scene:
                        profile_product_ids, _ = await ensure_files_for_profile(
                            bridge, affiliate_product.get("reference_paths") or [],
                            inst_project_id, target_instance_id, file_media_by_profile,
                            upload_fn=upload_image,
                        )
                    profile_continuity_id = available_continuity_id if owns_continuity else None
                    if available_continuity_id and not owns_continuity and continuity_local_path:
                        uploaded_continuity_ids, _ = await ensure_files_for_profile(
                            bridge, [continuity_local_path], inst_project_id, target_instance_id,
                            file_media_by_profile, upload_fn=upload_image,
                        )
                        profile_continuity_id = uploaded_continuity_ids[0] if uploaded_continuity_ids else None
                    scene_ref_ids = build_video_reference_ids(
                        character_ref_ids,
                        profile_storyboard_media_id,
                        policy_attempt=policy_attempt,
                        drop_all_references=drop_all_scene_references,
                        continuity_media_id=profile_continuity_id,
                        product_media_ids=profile_product_ids if is_affiliate_scene else None,
                    )
                    scene_record["reference_count"] = len(scene_ref_ids)
                    scene_record["reference_media_ids"] = list(scene_ref_ids)

                    if owns_continuity:
                        log_event(
                            job_id,
                            f"🔗 [Adegan {idx}/{total_scenes}] Prioritas referensi (Maks 7): "
                            f"[1] Frame akhir adegan {idx - 1} -> [2] Storyboard adegan -> "
                            f"[3+] {len(character_ref_ids)} Sheet Karakter.",
                            profile=target_name,
                        )
                    elif profile_storyboard_media_id:
                        log_event(
                            job_id,
                            f"🎨 [Adegan {idx}/{total_scenes}] Prioritas referensi (Maks 7): "
                            f"[1] Storyboard adegan -> [2+] {len(character_ref_ids)} Sheet Karakter.",
                            profile=target_name,
                        )

                    if drop_all_scene_references:
                        log_event(
                            job_id,
                            f"🧑‍🎨 [Adegan {idx}/{total_scenes}] Retry final tanpa image reference: "
                            "sheet/storyboard dianggap menyerupai tokoh terkenal; memakai prompt-only "
                            "dengan karakter fiktif generik.",
                            level="warning",
                            profile=target_name,
                        )
                    elif policy_attempt >= 1 and character_ref_ids:
                        log_event(
                            job_id,
                            f"🛡️ [Adegan {idx}/{total_scenes}] Retry aman: tetap memakai "
                            f"{len(scene_ref_ids)} reference (storyboard + sheet karakter) tetap dipertahankan.",
                            level="warning",
                            profile=target_name,
                        )

                    # Reference mode ("Ingredients") reads sheets as style/identity guides.
                    # Start-image mode would paste the sheet in as the literal opening frame,
                    # so any scene carrying the storyboard sheet must go through R2V.
                    if not media_ids and scene_ref_ids:
                        try:
                            from omniflash.generators import generate_video_r2v
                            log_event(
                                job_id,
                                f"🧷 [Adegan {idx}/{total_scenes}] Mengirim video dengan "
                                f"{len(scene_ref_ids)} Add Image Reference (Ingredients wajib).",
                                profile=target_name,
                            )
                            media_ids = await generate_video_r2v(
                                bridge=bridge,
                                prompt=prompt,
                                aspect=aspect_ratio,
                                project_id=inst_project_id,
                                reference_image_ids=scene_ref_ids,
                                duration=scene_duration,
                                instance_id=target_instance_id
                            )
                        except Exception as r2v_err:
                            # Never silently discard character/storyboard references. The outer
                            # profile loop may retry R2V elsewhere, but prompt-only T2V is not an
                            # equivalent fallback and causes visible identity/continuity drift.
                            raise RuntimeError(
                                f"Ingredients wajib gagal setelah retry; T2V tanpa reference dibatalkan: {r2v_err}"
                            ) from r2v_err

                    if not media_ids:
                        from omniflash.generators import generate_video_t2v
                        media_ids = await generate_video_t2v(
                            bridge=bridge,
                            prompt=prompt,
                            aspect=aspect_ratio,
                            project_id=inst_project_id,
                            duration=scene_duration,
                            instance_id=target_instance_id
                        )

                    if not media_ids:
                        raise ValueError("Google Flow tidak mengembalikan media ID untuk adegan ini.")

                    target_media_id = media_ids[0]
                    # Persist the full ID before polling/downloading so a completed Flow render
                    # remains recoverable even if the backend restarts during file transfer.
                    scene_record["media_id"] = target_media_id
                    _save_history()
                    log_event(job_id, f"📥 [Adegan {idx}/{total_scenes}] Request diterima Flow! Media ID: {target_media_id[:16]}... Menunggu render selesai...", profile=target_name)

                    last_pct = -1
                    def on_poll_progress(elapsed, sc_pct):
                        nonlocal last_pct
                        if job_state.get("cancelled"):
                            raise asyncio.CancelledError("Job cancelled by user.")
                        if elapsed > 0 and (elapsed % 2 == 0 or sc_pct != last_pct):
                            last_pct = sc_pct
                            overall_pct = min(95, int(((idx - 1) + (sc_pct / 100.0)) / total_scenes * 100))
                            log_event(job_id, f"⏳ [Adegan {idx}/{total_scenes} - {sc_pct}% | Total Progress: {overall_pct}%] Merender video {scene_duration}s di Google Flow ({elapsed}s berjalan / est. ~35s)...", profile=target_name)

                    # Await poll strictly until render complete
                    poll_result = await poll_video_status(bridge, target_media_id, project_id=inst_project_id, instance_id=target_instance_id, progress_callback=on_poll_progress)
                    video_url = poll_result.get("video_url")

                    if not video_url:
                        raise RuntimeError("Video selesai namun URL unduhan tidak ditemukan.")

                    log_event(job_id, f"✨ [Adegan {idx}/{total_scenes}] Render video {scene_duration}s selesai di Flow! Media ID: {target_media_id[:16]}... Mengunduh MP4 ke storage...", profile=target_name)

                    # Download MP4 file
                    out_filename = f"scene_{idx:02d}.mp4"
                    out_path = job_dir / out_filename

                    log_event(job_id, f"📥 [Adegan {idx}/{total_scenes}] Memulai proses unduh file video '{out_filename}'...", profile=target_name)
                    await download_file(
                        bridge, video_url, out_path, instance_id=target_instance_id,
                        media_id=target_media_id, project_id=inst_project_id,
                        job_id=job_id, label=out_filename, media_kind="video",
                    )

                    log_event(job_id, f"💾 [Adegan {idx}/{total_scenes}] Video MP4 berhasil diunduh dan tersimpan di storage ({out_filename})!", profile=target_name)

                    scene_record["status"] = "completed"
                    scene_record["video_url"] = video_url
                    scene_record["video_path"] = str(out_path)
                    scene_record["relative_url"] = f"/storage/jobs/{job_id}/{out_filename}"
                    completed_scene_paths.append(str(out_path))
                    job_state["execution_stage_completed"] = len(
                        [item for item in job_state["scenes"] if item.get("status") == "completed"]
                    )

                    # Prepare a literal start frame for the immediately following scene.
                    # Any failure here is non-fatal: the established reference pipeline remains.
                    continuity_media_id = None
                    continuity_scene_number = None
                    continuity_instance_id = None
                    continuity_project_id = None
                    continuity_local_path = None
                    if idx < total_scenes:
                        continuity_path = job_dir / f"continuity_{idx:02d}.jpg"
                        try:
                            extracted = await asyncio.to_thread(
                                extract_continuity_frame, out_path, continuity_path
                            )
                            if extracted:
                                uploaded_continuity_id = await upload_image(
                                    bridge,
                                    extracted,
                                    project_id=inst_project_id,
                                    instance_id=target_instance_id,
                                )
                                continuity_media_id = uploaded_continuity_id
                                continuity_local_path = str(continuity_path)
                                continuity_scene_number = idx
                                continuity_instance_id = target_instance_id
                                continuity_project_id = inst_project_id
                                scene_record["continuity_frame_url"] = (
                                    f"/storage/jobs/{job_id}/{continuity_path.name}"
                                )
                                scene_record["continuity_media_id"] = uploaded_continuity_id
                                log_event(
                                    job_id,
                                    f"🔗 [Adegan {idx}/{total_scenes}] Frame akhir siap menjadi "
                                    f"pembuka adegan {idx + 1}.",
                                    profile=target_name,
                                )
                        except Exception as continuity_ex:
                            log_event(
                                job_id,
                                f"⚠️ [Adegan {idx}/{total_scenes}] Frame continuity tidak tersedia "
                                f"({continuity_ex}); adegan berikutnya memakai fallback normal.",
                                level="warning",
                                profile=target_name,
                            )

                    _save_history()

                    log_event(job_id, f"✅ [Adegan {idx}/{total_scenes}] Selesai 100%! Tersimpan di {out_filename}. Siap melangkah ke adegan berikutnya.", profile=target_name)
                    scene_success = True
                    break

                except asyncio.CancelledError:
                    log_event(job_id, "🛑 Eksekusi job dibatalkan oleh pengguna.", level="warning")
                    job_state["status"] = "cancelled"
                    _save_history()
                    return
                except Exception as ex:
                    last_error = ex
                    # A content-policy rejection is about the prompt, not the account, so every
                    # other Chrome profile would be rejected the same way. Stop retrying.
                    if "ditolak Google Flow" in str(ex):
                        policy_rejection = str(ex)
                        log_event(job_id, f"🚫 [Adegan {idx}/{total_scenes}] {ex}", level="error", profile=target_name)
                        break
                    if is_flow_quota_error(ex):
                        job_state.setdefault("profile_failures", {})[target_instance_id] = {
                            "name": target_name,
                            "quota_exhausted": True,
                            "error": str(ex),
                            "scene": idx,
                        }
                        _save_history()
                        log_event(
                            job_id,
                            f"🔁 [{target_name}] Kuota/limit Flow habis. Profil ini dilewati untuk scene berikutnya; "
                            "mengimpor ulang character sheet lokal ke profil berikutnya...",
                            level="warning",
                            profile=target_name,
                        )
                    elif profile_continuity_id:
                        log_event(
                            job_id,
                            f"🔗 [Adegan {idx}/{total_scenes}] Frame akhir adegan {idx - 1} diimpor ke profil {target_name}; "
                            "continuity tetap menjadi reference pertama.",
                            profile=target_name,
                        )
                    else:
                        log_event(job_id, f"⚠️ [{target_name}] Kendala/Kuota: {ex}. Otomatis beralih mencoba profil Chrome berikutnya...", level="warning", profile=target_name)

            if scene_success or not policy_rejection or job_state.get("cancelled"):
                break

            if policy_attempt >= max_policy_rewrites:
                log_event(job_id, f"🚫 [Adegan {idx}/{total_scenes}] Masih ditolak setelah {policy_attempt}x penulisan ulang prompt. Adegan dilewati.", level="error")
                break

            policy_attempt += 1
            drop_all_scene_references = should_drop_character_references(
                policy_rejection, policy_attempt, max_policy_rewrites
            )
            log_event(job_id, f"🧠 [Adegan {idx}/{total_scenes}] Prompt/gambar ditolak filter. Meminta provider AI meracik sinonim prompt yang aman & dramatis (percobaan {policy_attempt}/{max_policy_rewrites})...")

            from .gemini_storyboard import sanitize_prompt_for_policy
            try:
                revised = await asyncio.to_thread(
                    sanitize_prompt_for_policy, prompt, policy_rejection, scene_title
                )
            except TypeError:
                revised = await asyncio.to_thread(
                    sanitize_prompt_for_policy, prompt, policy_rejection
                )
            except Exception as sanitize_err:
                log_event(job_id, f"⚠️ [Adegan {idx}/{total_scenes}] Sanitasi prompt error ({sanitize_err}).", level="warning")
                revised = None

            if not revised:
                log_event(job_id, f"⚠️ [Adegan {idx}/{total_scenes}] Provider AI tidak berhasil meracik prompt alternatif. Adegan dilewati.", level="warning")
                break

            prompt = apply_scene_audio_direction(
                enforce_spoken_language_lock(revised, sc, storyboard.get("target_lang") or ""),
                sc, storyboard, music_video=music_video_mode
            )
            retry_speaker_lock = build_speaker_lock(sc, characters)
            retry_wardrobe_lock = build_character_wardrobe_lock(sc, characters)
            if retry_speaker_lock:
                prompt = f"{prompt.rstrip()}\n\n{retry_speaker_lock}"
            if retry_wardrobe_lock:
                prompt = f"{prompt.rstrip()}\n\n{retry_wardrobe_lock}"
            prompt = apply_no_branding_direction(prompt)
            prompt = adapt_template_for_visual_style(prompt, visual_style, is_children)
            prompt += build_visual_style_guard(visual_style, is_children)
            prompt += build_finishing_look_guard(storyboard)
            prompt += "\n\nREFERENCE TEXT EXCLUSION LOCK: Any name, seed number, label, title bar, UI box, caption, border, or printed metadata visible in reference images is not part of the scene. Never render it, copy it, float it, overlay it, or turn it into a sign/card/subtitle. The final video frame must contain only the cinematic scene and physical story objects. No readable text unless explicitly required by the story, and even then use blurred/unreadable marks instead of words."
            sc["prompt_for_flow"] = prompt
            scene_record["prompt"] = prompt
            scene_record["prompt_rewritten"] = policy_attempt
            log_event(job_id, f"✍️ [Adegan {idx}/{total_scenes}] Prompt alternatif dengan sinonim aman siap. Mengulang render adegan ini...")

        if job_state.get("cancelled"):
            log_event(job_id, "🛑 Eksekusi job dibatalkan oleh pengguna.", level="warning")
            job_state["status"] = "cancelled"
            _save_history()
            return

        if not scene_success:
            scene_record["status"] = "failed"
            scene_record["error"] = str(last_error)
            log_event(job_id, f"❌ [Adegan {idx}/{total_scenes}] Seluruh profil Chrome gagal: {last_error}", level="error")

    # Step 3: Pre-Stitching Scene Reconciliation & Final Video Stitching
    if job_state.get("cancelled"):
        log_event(job_id, "🛑 Eksekusi job dibatalkan oleh pengguna.", level="warning")
        job_state["status"] = "cancelled"
        _save_history()
        return

    # Check for missing scenes and harvest directly from Google Flow canvas
    missing_scenes = [
        s for s in job_state.get("scenes", [])
        if s.get("status") != "completed" or not (job_dir / f"scene_{s.get('scene_number', s.get('id', 1)):02d}.mp4").exists()
    ]

    if missing_scenes and not job_state.get("cancelled"):
        log_event(
            job_id,
            f"🔍 Mendeteksi {len(missing_scenes)} adegan belum lengkap. Memeriksa kanvas Google Flow untuk merekonsiliasi seluruh video yang telah dihasilkan...",
        )
        try:
            live_instances = [i for i in bridge.instance_snapshot() if i.get("connected")]
            target_instance_id = project_instance_id or (live_instances[0].get("instance_id") if live_instances else None)
            inst_project_id = project_id or (live_instances[0].get("project_id") if live_instances else None)

            harvest_res = await harvest_project_videos(
                bridge, instance_id=target_instance_id, project_id=inst_project_id, timeout=90
            )
            harvested_videos = (harvest_res.get("videos") if isinstance(harvest_res, dict) else []) or []
            if harvested_videos:
                log_event(
                    job_id,
                    f"📦 Ditemukan {len(harvested_videos)} video pada kanvas Google Flow. Memulai pemulihan adegan...",
                )

                # Track URLs already claimed by completed scenes to avoid downloading duplicates
                claimed_urls = {
                    s.get("video_url")
                    for s in job_state.get("scenes", [])
                    if s.get("status") == "completed" and s.get("video_url")
                }

                # Filter only valid unclaimed videos from Flow canvas
                available_unclaimed = [
                    hv for hv in harvested_videos
                    if hv.get("video_url") and hv.get("video_url") not in claimed_urls
                ]

                for s in missing_scenes:
                    sc_num = s.get("scene_number", s.get("id", 1))
                    out_filename = f"scene_{sc_num:02d}.mp4"
                    out_path = job_dir / out_filename

                    matched = None
                    sc_prompt = (s.get("prompt") or s.get("visual_prompt") or s.get("action") or "").lower()

                    # 1. Try matching by prompt label among unclaimed videos
                    for idx_u, hv in enumerate(available_unclaimed):
                        hv_label = (hv.get("label") or "").lower()
                        if hv_label and (hv_label in sc_prompt or sc_prompt in hv_label):
                            matched = available_unclaimed.pop(idx_u)
                            break

                    # 2. If no prompt match, take next available unclaimed video in chronological order
                    if not matched and available_unclaimed:
                        matched = available_unclaimed.pop(0)

                    if matched and matched.get("video_url"):
                        v_url = matched["video_url"]
                        claimed_urls.add(v_url)
                        log_event(
                            job_id,
                            f"📥 [Rekonsiliasi Adegan {sc_num}/{total_scenes}] Mengunduh video dari kanvas Flow ({out_filename})...",
                        )
                        await download_file(
                            bridge, v_url, out_path, instance_id=target_instance_id, project_id=inst_project_id,
                            job_id=job_id, label=out_filename, media_kind="video",
                        )
                        s["status"] = "completed"
                        s["video_url"] = v_url
                        s["video_path"] = str(out_path)
                        s["relative_url"] = f"/storage/jobs/{job_id}/{out_filename}"
                        log_event(
                            job_id,
                            f"✅ [Rekonsiliasi Adegan {sc_num}/{total_scenes}] Berhasil dipulihkan dan disimpan ({out_filename})!",
                        )
            _save_history()
        except Exception as harvest_err:
            log_event(
                job_id,
                f"⚠️ Rekonsiliasi kanvas Google Flow menemui kendala: {harvest_err}",
                level="warning",
            )

    # Reconstruct completed_scene_paths strictly in scene order
    completed_scene_paths = []
    for s in job_state.get("scenes", []):
        sc_num = s.get("scene_number", s.get("id", 1))
        sc_path = job_dir / f"scene_{sc_num:02d}.mp4"
        if sc_path.exists() and s.get("status") == "completed":
            completed_scene_paths.append(str(sc_path))
    job_state["execution_stage_completed"] = len(completed_scene_paths)

    if completed_scene_paths:
        job_state["execution_stage"] = "stitching"
        log_event(job_id, f"🎞️ [TAHAP 4/4: 95%] Seluruh {len(completed_scene_paths)} adegan video siap! Memulai pasca-produksi & penggabungan film...")
        try:
            from .film_stitcher import generate_srt_subtitles
            log_event(job_id, f"📝 [TAHAP 4/4: 96%] Menyusun subtitle SRT sinkron untuk {len(completed_scene_paths)} adegan...")
            srt_path = generate_srt_subtitles(job_dir, job_state["scenes"], duration_per_scene=duration)
            job_state["srt_subtitles_url"] = f"/storage/jobs/{job_id}/subtitles.srt"
            log_event(job_id, f"💾 [TAHAP 4/4: 96%] Subtitle SRT berhasil dibuat ({Path(srt_path).name})!")

            log_event(job_id, f"🎬 [TAHAP 4/4: 97%] Menggabungkan {len(completed_scene_paths)} file MP4 dengan FFmpeg concat...")
            film_path = stitch_scenes(job_dir, completed_scene_paths, output_filename="cinematic_film.mp4")
            log_event(job_id, f"💾 [TAHAP 4/4: 97%] Penggabungan potongan video selesai ({Path(film_path).name})!")

            music_track = resolve_master_music_track(storyboard, cfg)
            if music_track and os.path.exists(music_track):
                log_event(job_id, f"🎵 [TAHAP 4/4: 98%] Menyatukan audio track musik latar '{Path(music_track).name}' dengan film...")
                from .film_stitcher import mux_audio_to_video
                film_path = mux_audio_to_video(job_dir, film_path, music_track, output_filename="cinematic_film_with_audio.mp4")
                log_event(job_id, f"💾 [TAHAP 4/4: 98%] Muxing audio latar berhasil!")

            job_state["cinematic_film_path"] = str(film_path)
            final_filename = os.path.basename(film_path)
            job_state["cinematic_film_url"] = f"/storage/jobs/{job_id}/{final_filename}"
            job_state["status"] = "waiting_for_quota" if batch_paused else "completed"
            record_output_file_size(job_state, film_path)
            finish_job_timing(job_state)
            if batch_paused:
                log_event(
                    job_id,
                    f"💾 Checkpoint batch tersimpan. Preview sementara berisi "
                    f"{len(completed_scene_paths)}/{total_scenes} scene; lanjutkan saat slot Flow tersedia.",
                    level="warning",
                )
            else:
                log_event(
                    job_id,
                    "✅ [TAHAP 4/4: 100%] SELURUH PROSES SELESAI! Film sinematik utuh & Subtitle SRT siap diputar "
                    f"di Galeri. Waktu proses total: {job_state['processing_duration']}; "
                    f"ukuran file: {job_state['output_size_display']}.",
                )
        except Exception as ex:
            log_event(job_id, f"⚠️ Gagal menggabungkan film sinematik: {ex}", level="warning")
            job_state["status"] = "completed_partial"
    else:
        job_state["status"] = "failed"
        log_event(job_id, "❌ Job gagal: Tidak ada adegan yang berhasil dirender.", level="error")

    if not job_state.get("completed_at"):
        finish_job_timing(job_state)

    try:
        bridge.remove_progress_listener(_handle_flow_progress)
    except Exception:
        pass

    _save_history()


def resume_job(job_id: str, render_scene_limit: Optional[int] = None, render_scene_start: Optional[int] = None, render_scene_end: Optional[int] = None) -> bool:
    """Resume execution of an existing job from where it left off, reusing finished scenes and character sheets."""
    canonical_job_id = "job_" + job_id[5:] if isinstance(job_id, str) and job_id.startswith("job__") else job_id
    job = get_job_status(canonical_job_id)
    if not job:
        return False
    storyboard = job.get("storyboard") or job.get("seo_storyboard")
    if not storyboard or not storyboard.get("scenes"):
        return False

    job["status"] = "processing"
    job["cancelled"] = False
    # None deliberately means "all remaining scenes". Always replace the previous
    # batch limit so clearing the UI field does not accidentally reuse an old quota.
    job["render_scene_limit"] = render_scene_limit
    job["render_scene_start"] = render_scene_start
    job["render_scene_end"] = render_scene_end
    _active_jobs[canonical_job_id] = job
    _save_history()

    log_event(canonical_job_id, f"🔄 [USER] Melanjutkan eksekusi job '{job.get('title')}' dari adegan yang belum selesai...")

    # Queue the coroutine after the HTTP handler has returned. Starting the
    # heavy executor inline can monopolize the event loop before FastAPI sends
    # the Resume response, making the server appear frozen to the UI/launcher.
    execution = execute_storyboard_job(
            job_id=canonical_job_id,
            storyboard=storyboard,
            theme_image_path=job.get("theme_image_path"),
            aspect_ratio=job.get("aspect_ratio", "landscape"),
            duration=job.get("duration", 10),
            flow_project_id=job.get("flow_project_id"),
            force_uniform_duration=job.get("force_uniform_duration", False),
            render_scene_limit=job.get("render_scene_limit"),
            render_scene_start=job.get("render_scene_start"),
            render_scene_end=job.get("render_scene_end"),
        )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Preserve the synchronous/unit-test call contract; the HTTP route
        # always has a running loop and uses the deferred scheduling path.
        asyncio.create_task(execution)
    else:
        loop.call_soon(asyncio.create_task, execution)
    return True

