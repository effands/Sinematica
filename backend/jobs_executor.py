"""Sinematica Backend — Multi-Profile Job Executor & Task Balancer."""

import asyncio
import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional
import time
import uuid

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
from .scene_audio_direction import apply_scene_audio_direction, resolve_master_music_track
from .scene_direction import (
    apply_no_branding_direction,
    build_speaker_lock,
    choose_shot_count,
    ensure_unique_character_signatures,
)
from .content_quality import build_render_realism_guard, build_scene_blueprint_guard
from .storyboard_image import fetch_image_bytes, generate_storyboard_sheet

from omniflash.generators import upload_image, poll_video_status


class _SheetAlreadyBuilt(Exception):
    """Signals the storyboard sheet was produced by Gemini, so skip the Flow fallback."""

log = logging.getLogger("sinematica.jobs_executor")

HISTORY_FILE = settings.DATA_DIR / "jobs_history.json"
_active_jobs: Dict[str, Dict[str, Any]] = {}
_job_logs: Dict[str, List[Dict[str, Any]]] = {}


def _load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    if isinstance(item, dict) and "job_id" in item:
                        _active_jobs[item["job_id"]] = item
        except Exception as ex:
            log.warning("Gagal memuat history jobs: %s", ex)

_load_history()


def _save_history():
    try:
        data = list(_active_jobs.values())
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as ex:
        log.warning("Gagal menyimpan history jobs: %s", ex)


def log_event(job_id: str, message: str, level: str = "info", profile: str = None):
    entry = {
        "timestamp": time.strftime("%H:%M:%S"),
        "message": message,
        "level": level,
        "profile": profile or "System"
    }
    if job_id not in _job_logs:
        _job_logs[job_id] = []
    _job_logs[job_id].append(entry)
    log.info("[%s] [%s] %s", job_id, profile or "SYS", message)


def get_job_logs(job_id: str) -> List[Dict[str, Any]]:
    return _job_logs.get(job_id, [])


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    return _active_jobs.get(job_id)


def list_jobs() -> List[Dict[str, Any]]:
    return list(_active_jobs.values())


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
        "source_files": job_source_files(theme_image_path, storyboard),
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


FLOW_ALLOWED_DURATIONS = (4, 6, 8, 10)


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
    """Order at most seven Flow Ingredients by continuity, identity, then composition."""
    if drop_all_references:
        return []
    refs = []
    if continuity_media_id:
        refs.append(continuity_media_id)
    for media_id in character_ids:
        if media_id and media_id not in refs and len(refs) < limit:
            refs.append(media_id)
    for media_id in product_media_ids or []:
        if media_id and media_id not in refs and len(refs) < limit:
            refs.append(media_id)
    if not refs and storyboard_media_id:
        return [storyboard_media_id]
    if policy_attempt == 0 and storyboard_media_id and storyboard_media_id not in refs and len(refs) < limit:
        refs.append(storyboard_media_id)
    return refs[:limit]


def build_visual_style_guard(visual_style: str = "live_action", children_mode: bool = False) -> str:
    """Lock one rendering medium across character sheets, boards, and final video."""
    style = visual_style or ("3d_cartoon" if children_mode else "live_action")
    contracts = {
        "live_action": "LIVE-ACTION CINEMATIC PHOTOGRAPHY ONLY: real human actors, natural skin pores, realistic hair and fabric, optical cinematic camera capture. NO cartoon, anime, illustration, painting, comic art, stylized 3D, doll-like face, or cel shading.",
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
    if not selected:
        return ""
    return "\n\nFINISHING LOOK LOCK (DO NOT CHANGE BASE MEDIUM): " + "; ".join(selected) + "."


def adapt_template_for_visual_style(template: str, visual_style: str, children_mode: bool) -> str:
    """Remove photoreal-only template instructions when a stylized medium is selected."""
    if visual_style == "3d_cartoon":
        return template
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
    adapted = template.replace("Ultra photorealistic", "Strictly style-locked")
    adapted = adapted.replace("Natural skin texture | Realistic fabric", "Medium-consistent surfaces | Style-consistent costume rendering")
    adapted = adapted.replace("cartoon style, anime style, painterly rendering,", "mixed visual medium, photorealistic photography,")
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
    """Use prompt-only mode on the final retry when Flow rejects an input image."""
    reason = rejection_reason or ""
    is_reference_rejection = any(code in reason for code in _REFERENCE_IMAGE_POLICY_CODES)
    return is_reference_rejection and policy_attempt >= max_policy_rewrites


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
    connected = [item for item in instances if item.get("connected")]
    if not connected:
        return None
    if project_id:
        exact = next((item for item in connected if item.get("project_id") == project_id), None)
        if exact:
            return exact.get("instance_id")
    with_project = next((item for item in connected if item.get("project_id")), None)
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
    """Fold the storyboard's beat breakdown into the video prompt as text.

    Flow's video endpoint accepts real reference images, but its image endpoint gives us no
    way to pin a storyboard panel to the character sheets. So the composition guidance the
    panel was meant to carry is written into the prompt instead, while character identity
    keeps coming from the sheets attached as actual reference images.
    """
    shot = (scene.get("shot_type") or "").strip()
    camera = (scene.get("camera_movement") or "").strip()

    bits = []
    if shot:
        bits.append(f"Framing: {shot}.")
    if camera:
        bits.append(f"Camera: {camera}.")
    bits.append(
        "Stage it as a clear three-beat progression inside the clip: an opening frame that "
        "establishes where each character stands, a mid-action beat at the peak of the action, "
        "and an end frame that resolves the shot. Keep every character exactly as shown in the "
        "attached character sheets — same faces, colours, proportions and outfits throughout."
    )
    return " ".join(bits)


async def download_file(
    bridge, url: str, dest_path: Path, instance_id: Optional[str] = None,
    media_id: Optional[str] = None, project_id: Optional[str] = None,
):
    if url.startswith("data:"):
        import base64
        # format is data:video/mp4;base64,.....
        header, encoded = url.split(",", 1)
        video_bytes = base64.b64decode(encoded)
        with open(dest_path, "wb") as out:
            out.write(video_bytes)
    else:
        download_url = url
        exact_download_error = None
        if media_id and hasattr(bridge, "trpc_request"):
            try:
                await stream_exact_media_with_retry(
                    bridge,
                    media_id.rsplit("/", 1)[-1],
                    project_id or "",
                    instance_id,
                    dest_path,
                    attempts=6,
                    delay=3.0,
                )
                return
            except Exception as ex:
                exact_download_error = ex
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
                await asyncio.to_thread(stream_download, download_url, dest_path)
                return
            except Exception as ex:
                log.warning("Unduhan langsung MP4 gagal; mencoba profil Chrome: %s", ex)
        result = await bridge.download_url_with_retry(
            download_url, instance_id=instance_id, timeout=300, attempts=3, delay=2
        )
        with open(dest_path, "wb") as out:
            out.write(result["data"])


async def execute_storyboard_job(
    job_id: str,
    storyboard: Dict[str, Any],
    theme_image_path: Optional[str] = None,
    aspect_ratio: str = "landscape",
    duration: int = 10,
    flow_project_id: Optional[str] = None,
    force_uniform_duration: bool = False
):
    """Execute video generation for each scene across available Chrome profiles."""
    bridge = get_bridge()
    job_dir = settings.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    scenes = storyboard.get("scenes", [])
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
        "seo_story_context": seo_story_context,
        "seo_storyboard": seo_storyboard,
        "target_lang": storyboard.get("target_lang") or "",
        "target_country": storyboard.get("target_country") or "",
    }
    _active_jobs[job_id] = job_state

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

    # Check Flow Project ID
    project_id = flow_project_id or settings.get_flow_project_id()
    if not project_id:
        snap = bridge.instance_snapshot()
        for inst in snap:
            if inst.get("project_id"):
                project_id = inst["project_id"]
                break

    if not project_id:
        log_event(job_id, "⚠️ Flow Project ID belum diisi di Settings. Menggunakan default session project...", level="warning")
    else:
        log_event(job_id, f"🌐 [0%] Flow Project ID terdeteksi: {project_id[:16]}...")

    project_instance_id = choose_instance_for_project(bridge.instance_snapshot(), project_id)

    # Step 1: Upload Reference Image, or Generate one Anchor Seed Image PER Character in Flow
    ref_media_id = None
    affiliate_product = storyboard.get("affiliate_product") or {}
    affiliate_media_ids: List[str] = []
    character_media_ids: Dict[Any, str] = {}
    character_image_urls: Dict[Any, str] = {}
    character_image_paths: Dict[Any, str] = {}

    cfg = settings.get_settings()
    enable_seed_image = cfg.get("enable_character_seed_image", True)
    custom_template = cfg.get("character_seed_template") or settings.DEFAULT_CHARACTER_SHEET_TEMPLATE
    enable_scene_storyboard_image = cfg.get("enable_scene_storyboard_image", True)

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
        log_event(job_id, "⏭️ [Tahap 1/2] Pembuatan Gambar Anchor Seed Karakter di-bypass (Disabled oleh Settings)...")
    else:

        from omniflash.generators import generate_character_image
        first_target_id = choose_instance_for_project(bridge.instance_snapshot(), project_id)

        log_event(job_id, f"🎨 [5%] [Tahap 1/2] Membuat {len(characters)} Gambar Anchor Seed Karakter di Google Flow (Master Prompt Template)...")
        for c_idx, char in enumerate(characters, start=1):
            char_id = char.get("id", c_idx)
            char_name = char.get("name", f"Karakter {char_id}")
            char_seed = char.get("seed", storyboard.get("character_seed", 123456))
            char_desc = char.get('description', '')

            char_prompt = custom_template.replace("{char_name}", char_name).replace("{char_seed}", str(char_seed)).replace("{char_desc}", char_desc)
            owned_reference_paths = resolve_character_reference_paths(char, storyboard)
            if owned_reference_paths:
                char_prompt += (
                    "\n\nATTACHED CHARACTER REFERENCES ARE THE SINGLE SOURCE OF TRUTH for this character's "
                    "face, hairstyle, body shape, costume silhouette, colour palette, accessories, and "
                    "distinctive marks. Combine the views into one consistent identity; do not redesign, "
                    "recolour, substitute, or borrow traits from any other character."
                )

            suppress_references = False
            request_seed = char_seed
            for try_cnt in range(1, 5):
                try:
                    reference_media_ids = await upload_character_references(
                        bridge, owned_reference_paths, project_id, first_target_id
                    ) if owned_reference_paths and not suppress_references else []
                    if owned_reference_paths and not suppress_references and len(reference_media_ids) != len(owned_reference_paths):
                        raise RuntimeError(
                            f"Hanya {len(reference_media_ids)}/{len(owned_reference_paths)} referensi "
                            f"karakter '{char_name}' berhasil diunggah."
                        )
                    if reference_media_ids:
                        log_event(
                            job_id,
                            f"🧩 [{5 + c_idx}%] Memakai {len(reference_media_ids)} image reference "
                            f"khusus untuk karakter '{char_name}'.",
                        )
                    log_event(job_id, f"⏳ [{5 + c_idx}%] Mengirim request character seed image '{char_name}' (Seed: {request_seed}) [Percobaan {try_cnt}]...")
                    img_res = await generate_character_image(
                        bridge,
                        prompt=(char_prompt + build_visual_style_guard(visual_style, is_children)
                                + build_finishing_look_guard(storyboard)),
                        aspect="portrait", project_id=project_id,
                        instance_id=first_target_id,
                        reference_media_ids=reference_media_ids or None,
                    )
                    if reference_media_ids and not img_res.get("reference_applied"):
                        raise RuntimeError(
                            f"Google Flow tidak menerapkan image reference karakter '{char_name}'."
                        )
                    media_id = img_res.get("media_id")
                    if media_id:
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

                            # Cache character sheet locally immediately
                            sheet_got = await asyncio.to_thread(fetch_image_bytes, img_url)
                            if sheet_got and sheet_got.get("data"):
                                safe_name = "".join(c for c in char_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
                                local_file = job_dir / f"character_sheet_{char_id}_{safe_name}.png"
                                local_file.write_bytes(sheet_got["data"])
                                character_image_paths[char_id] = str(local_file)
                                character_image_paths[str(char_id)] = str(local_file)
                                character_image_paths[char_name] = str(local_file)
                                character_image_paths[char_name.lower()] = str(local_file)
                                log_event(job_id, f"💾 Character sheet '{char_name}' tersimpan di lokal: {local_file.name}")

                        log_event(job_id, f"✅ Gambar Seed Karakter '{char_name}' berhasil dibuat! Media ID: {media_id[:16]}...")
                        break
                except Exception as ex:
                    log_event(job_id, f"⚠️ Gagal generate seed image karakter '{char_name}' (Percobaan {try_cnt}): {ex}.", level="warning")
                    if try_cnt < 4:
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
                        await asyncio.sleep(2)

        missing_seeds = missing_character_seeds(characters, character_media_ids)
        if missing_seeds:
            missing_names = ", ".join(missing_seeds)
            error_message = (
                "Anchor seed karakter wajib tetapi gagal dibuat untuk: " + missing_names + ". "
                "Job dihentikan sebelum render scene agar identitas karakter tidak berubah."
            )
            job_state["status"] = "failed"
            job_state["error"] = error_message
            log_event(job_id, f"🛑 {error_message}", level="error")
            _save_history()
            return

        if character_media_ids and not ref_media_id:
            ref_media_id = list(character_media_ids.values())[0]

    # Step 2: Render each scene video across connected Chrome profiles
    completed_scene_paths = []
    music_video_mode = bool(storyboard.get("music_track_path"))
    continuity_media_id = None
    continuity_scene_number = None
    continuity_instance_id = None
    continuity_project_id = None
    affiliate_scene_numbers = resolve_affiliate_scene_numbers(
        total_scenes, affiliate_product.get("scene_position", "auto")
    ) if affiliate_product.get("enabled") else set()

    for idx, sc in enumerate(scenes, start=1):
        if job_state.get("cancelled"):
            log_event(job_id, "🛑 Eksekusi job dihentikan oleh pengguna.", level="warning")
            job_state["status"] = "cancelled"
            _save_history()
            return

        job_state["current_scene"] = idx
        scene_title = sc.get("title", f"Adegan {idx}")
        is_affiliate_scene = bool(sc.get("affiliate_scene")) or idx in affiliate_scene_numbers
        prompt = sc.get("prompt_for_flow", "")
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
            )
            log_event(
                job_id,
                f"✅ [Adegan {idx}/{total_scenes}] Prompt padat selesai via {pacing_provider}: "
                f"{shot_count} shot berbeda, aksi berantai, dialog terkunci, dan kontinuitas tersambung.",
            )

        speaker_lock = build_speaker_lock(sc, characters)
        if speaker_lock:
            prompt = f"{prompt.rstrip()}\n\n{speaker_lock}"

        prompt = apply_scene_audio_direction(
            prompt, sc, storyboard, music_video=music_video_mode
        )
        prompt = apply_no_branding_direction(prompt)
        # Re-assert after AI pacing rewrites so no later stage can silently change medium.
        prompt += build_visual_style_guard(visual_style, is_children)
        prompt += build_finishing_look_guard(storyboard)
        prompt += build_scene_blueprint_guard(sc)
        prompt += build_render_realism_guard(storyboard)

        scene_record = {
            "scene_number": idx,
            "title": scene_title,
            "prompt": prompt,
            "status": "rendering",
            "duration": scene_duration,
            "video_path": None,
            "profile_used": None,
        }
        job_state["scenes"].append(scene_record)

        snap_instances = [
            i for i in bridge.instance_snapshot()
            if i["connected"] and i.get("ready", True)
        ]
        snap_instances.sort(key=lambda item: item.get("instance_id") != project_instance_id)
        if not snap_instances:
            log_event(job_id, f"❌ [Adegan {idx}/{total_scenes}] Gagal: Tidak ada akun profil Chrome terhubung yang siap (ready).", level="error")
            scene_record["status"] = "failed"
            scene_record["error"] = "Tidak ada profil Chrome ready."
            continue

        scene_success = False
        last_error = None

        # Step 1.5: Generate ONE storyboard key-frame reference image for this scene (composition/blocking/lighting),
        # used ALONGSIDE the character seed image(s) as a second reference for the video render below.
        storyboard_media_id = None
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
            _sb_manifest_slot = True  # manifest appended once the sheet list is known
            sb_target_id = choose_instance_for_project(bridge.instance_snapshot(), project_id)

            # Feed the character sheets in as references, otherwise the panel invents new
            # faces and wardrobe and every scene ends up with different-looking characters.
            sb_chars = resolve_scene_characters(sc, storyboard.get("characters") or [], character_media_ids)
            sb_ref_ids = [c["media_id"] for c in sb_chars]
            if is_affiliate_scene:
                sb_ref_ids.extend(affiliate_media_ids)
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
            try:
                if storyboard_media_id:
                    raise _SheetAlreadyBuilt
                log_event(job_id, f"🖼️ [Adegan {idx}/{total_scenes}] Membuat gambar storyboard adegan — "
                                  f"melampirkan sheet: {who}...")
                from omniflash.generators import generate_character_image
                sb_img_res = await generate_character_image(
                    bridge, prompt=storyboard_prompt, aspect=aspect_ratio, project_id=project_id,
                    instance_id=sb_target_id, reference_media_ids=sb_ref_ids,
                    seed=storyboard.get("character_seed"),
                )
                sb_media = sb_img_res.get("media_id")
                if sb_media:
                    storyboard_media_id = sb_media
                    if sb_img_res.get("image_url"):
                        scene_record["storyboard_sheet_url"] = sb_img_res["image_url"]
                    if sb_img_res.get("reference_applied"):
                        log_event(job_id, f"✅ [Adegan {idx}/{total_scenes}] Gambar storyboard dibuat MENGIKUTI "
                                          f"{sb_img_res.get('reference_count')} character sheet! Media ID: {storyboard_media_id[:16]}...")
                    else:
                        log_event(job_id, f"✅ [Adegan {idx}/{total_scenes}] Gambar storyboard berhasil dibuat di Google Flow (Media ID: {storyboard_media_id[:16]}...).")
            except _SheetAlreadyBuilt:
                pass
            except Exception as ex:
                log_event(job_id, f"⚠️ [Adegan {idx}/{total_scenes}] Gagal membuat gambar storyboard key-frame: {ex}. Melanjutkan hanya dengan seed karakter...", level="warning")

        # Google Flow can reject either wording or a reference image on content policy.
        # Rewrite first, then progressively reduce references so one false-positive image
        # cannot leave the whole film waiting at 95%.
        max_policy_rewrites = int(cfg.get("max_policy_rewrites", 2) or 0)
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
                ) or flow_project_id or chosen.get("project_id") or project_id or settings.get_flow_project_id()

                log_event(job_id, f"🚀 [Adegan {idx}/{total_scenes}: '{scene_title}'] [{target_name}] Mengirim prompt video {scene_duration}s ke Google Flow (Model: abra_t2v_{scene_duration}s, Ratio: {aspect_ratio})...", profile=target_name)
                scene_record["profile_used"] = target_name

                try:
                    media_ids = None
                    v_chars = scene_characters_for_retry
                    character_ref_ids = [c["media_id"] for c in v_chars if c.get("media_id")]
                    scene_ref_ids = build_video_reference_ids(
                        character_ref_ids,
                        storyboard_media_id,
                        policy_attempt=policy_attempt,
                        drop_all_references=drop_all_scene_references,
                        continuity_media_id=available_continuity_id if owns_continuity else None,
                        product_media_ids=affiliate_media_ids if is_affiliate_scene else None,
                    )
                    scene_record["reference_count"] = len(scene_ref_ids)
                    scene_record["reference_media_ids"] = list(scene_ref_ids)

                    if owns_continuity:
                        log_event(
                            job_id,
                            f"🔗 [Adegan {idx}/{total_scenes}] Ingredients continuity aktif: frame akhir "
                            f"adegan {idx - 1} ditempatkan pertama, lalu {len(character_ref_ids)} seed "
                            "karakter dan storyboard terakhir.",
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
                            f"{len(scene_ref_ids)} sheet karakter; storyboard turunan dilepas agar identitas tidak berubah.",
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

                    log_event(job_id, f"✨ [Adegan {idx}/{total_scenes}] Render video {scene_duration}s selesai di Flow! Mengunduh MP4 ke storage...", profile=target_name)

                    # Download MP4 file
                    out_filename = f"scene_{idx:02d}.mp4"
                    out_path = job_dir / out_filename

                    await download_file(
                        bridge, video_url, out_path, instance_id=target_instance_id,
                        media_id=target_media_id, project_id=inst_project_id,
                    )

                    log_event(job_id, f"💾 [Adegan {idx}/{total_scenes}] Video MP4 berhasil diunduh dan tersimpan di storage ({out_filename})!", profile=target_name)

                    scene_record["status"] = "completed"
                    scene_record["video_path"] = str(out_path)
                    scene_record["relative_url"] = f"/storage/jobs/{job_id}/{out_filename}"
                    completed_scene_paths.append(str(out_path))

                    # Prepare a literal start frame for the immediately following scene.
                    # Any failure here is non-fatal: the established reference pipeline remains.
                    continuity_media_id = None
                    continuity_scene_number = None
                    continuity_instance_id = None
                    continuity_project_id = None
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
            log_event(job_id, f"🧠 [Adegan {idx}/{total_scenes}] Prompt/gambar ditolak filter. Meminta provider AI utama meracik prompt alternatif (percobaan {policy_attempt}/{max_policy_rewrites})...")

            from .gemini_storyboard import sanitize_prompt_for_policy
            revised = await asyncio.to_thread(sanitize_prompt_for_policy, prompt, policy_rejection, scene_title)
            if not revised:
                log_event(job_id, f"⚠️ [Adegan {idx}/{total_scenes}] Gemini tidak berhasil meracik prompt alternatif. Adegan dilewati.", level="warning")
                break

            prompt = apply_scene_audio_direction(
                revised, sc, storyboard, music_video=music_video_mode
            )
            prompt = apply_no_branding_direction(prompt)
            prompt += build_visual_style_guard(visual_style, is_children)
            prompt += build_finishing_look_guard(storyboard)
            if drop_all_scene_references:
                prompt = fictionalize_character_names(
                    prompt,
                    [c.get("name", "") for c in scene_characters_for_retry],
                )
            sc["prompt_for_flow"] = prompt
            scene_record["prompt"] = prompt
            scene_record["prompt_rewritten"] = policy_attempt
            log_event(job_id, f"✍️ [Adegan {idx}/{total_scenes}] Prompt alternatif siap. Mengulang render adegan ini...")

        if job_state.get("cancelled"):
            log_event(job_id, "🛑 Eksekusi job dibatalkan oleh pengguna.", level="warning")
            job_state["status"] = "cancelled"
            _save_history()
            return

        if not scene_success:
            scene_record["status"] = "failed"
            scene_record["error"] = str(last_error)
            log_event(job_id, f"❌ [Adegan {idx}/{total_scenes}] Seluruh profil Chrome gagal: {last_error}", level="error")

    # Step 3: Automatically stitch completed scenes into full cinematic film
    if job_state.get("cancelled"):
        log_event(job_id, "🛑 Eksekusi job dibatalkan oleh pengguna.", level="warning")
        job_state["status"] = "cancelled"
        _save_history()
        return

    if completed_scene_paths:
        log_event(job_id, f"🎞️ [95%] Menggabungkan {len(completed_scene_paths)} adegan menjadi Film Sinematik Utuh & membuat Subtitle SRT...")
        try:
            from .film_stitcher import generate_srt_subtitles
            srt_path = generate_srt_subtitles(job_dir, job_state["scenes"], duration_per_scene=duration)
            job_state["srt_subtitles_url"] = f"/storage/jobs/{job_id}/subtitles.srt"

            film_path = stitch_scenes(job_dir, completed_scene_paths, output_filename="cinematic_film.mp4")

            music_track = resolve_master_music_track(storyboard, cfg)
            if music_track and os.path.exists(music_track):
                log_event(job_id, "🎵 [98%] Menyatukan audio track musik latar dengan video klip...")
                from .film_stitcher import mux_audio_to_video
                film_path = mux_audio_to_video(job_dir, film_path, music_track, output_filename="cinematic_film_with_audio.mp4")

            job_state["cinematic_film_path"] = str(film_path)
            final_filename = os.path.basename(film_path)
            job_state["cinematic_film_url"] = f"/storage/jobs/{job_id}/{final_filename}"
            job_state["status"] = "completed"
            record_output_file_size(job_state, film_path)
            finish_job_timing(job_state)
            log_event(
                job_id,
                "✅ [100%] SELURUH PROSES SELESAI! Film sinematik utuh & Subtitle SRT siap diputar "
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

    _save_history()
