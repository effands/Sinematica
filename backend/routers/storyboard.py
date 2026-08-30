"""Sinematica Backend — Storyboard Generation Router."""

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import shutil
import uuid
import logging
from pathlib import Path
import math
import subprocess
import json

from .. import settings
from ..storyboard_actor_references import attach_character_references, select_actor_references

router = APIRouter(prefix="/api/storyboard", tags=["Storyboard"])
log = logging.getLogger("sinematica.routers.storyboard")

def _inject_actors_info(actor_ids: str, character_info: str, saved_paths: List[str]):
    if not actor_ids:
        return character_info
    
    actor_ids_list = [aid.strip() for aid in actor_ids.split(",") if aid.strip()]
    if not actor_ids_list:
        return character_info
        
    actors_db = settings.DATA_DIR / "actors.json"
    if not actors_db.exists():
        return character_info
        
    try:
        with open(actors_db, "r", encoding="utf-8") as f:
            all_actors = json.load(f)
            
        updated_info, selected = select_actor_references(actor_ids, character_info, all_actors)
        if not selected:
            return character_info
        saved_paths.extend(path for item in selected for path in item.get("paths") or [] if Path(path).exists())
        return updated_info
    except Exception as ex:
        log.warning("Gagal memuat aktor: %s", ex)
        return character_info


class AutoSuggestRequest(BaseModel):
    theme: str
    microdrama_mode: Optional[bool] = False
    target_country: Optional[str] = ""
    dracin_theme: Optional[str] = ""


class SEOKitRequest(BaseModel):
    title: Optional[str] = ""
    film_title: Optional[str] = ""
    premise: Optional[str] = ""


class RegenerateSceneRequest(BaseModel):
    film_title: str
    scene_number: int
    scene_title: Optional[str] = ""
    consistent_characters: Optional[str] = ""
    genre_style: Optional[str] = ""


from ..gemini_storyboard import generate_storyboard, auto_suggest_details, generate_youtube_metadata, regenerate_single_scene, generate_music_video_storyboard


@router.post("/seo_kit")
def generate_seo_metadata_kit(req: SEOKitRequest):
    title = req.title or req.film_title or "Film AI Sinematik"
    try:
        data = generate_youtube_metadata(title, req.premise or title)
        # Keep both key shapes so cached/older frontends remain compatible.
        data["seo_titles"] = data.get("seo_titles") or data.get("titles") or []
        data["tags_csv"] = data.get("tags_csv") or data.get("tags") or ""
        return {"success": True, "seo_kit": data}
    except Exception as ex:
        log.error("Error generating SEO kit: %s", ex)
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/regenerate_scene")
def regenerate_single_scene_endpoint(req: RegenerateSceneRequest):
    try:
        scene = regenerate_single_scene(
            film_title=req.film_title,
            scene_number=req.scene_number,
            scene_title=req.scene_title or f"Adegan {req.scene_number}",
            consistent_characters=req.consistent_characters or "",
            genre_style=req.genre_style or ""
        )
        return {"success": True, "scene": scene}
    except Exception as ex:
        log.error("Error regenerating scene %d: %s", req.scene_number, ex)
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/auto_concept")
def auto_concept_get(microdrama_mode: bool = False, target_country: str = "", dracin_theme: str = ""):
    try:
        suggestion = auto_suggest_details("", microdrama_mode=microdrama_mode, target_country=target_country, dracin_theme=dracin_theme)
        return {"success": True, "concept": suggestion.get("suggested_premise", ""), "suggestion": suggestion}
    except Exception as ex:
        log.error("Error auto-suggesting fresh concept: %s", ex)
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/suggest")
def suggest_concept(req: AutoSuggestRequest):
    theme = (req.theme or "").strip()
    if not theme:
        return auto_concept_get(microdrama_mode=req.microdrama_mode or False, target_country=req.target_country or "", dracin_theme=req.dracin_theme or "")
    try:
        suggestion = auto_suggest_details(theme, microdrama_mode=req.microdrama_mode or False, target_country=req.target_country or "", dracin_theme=req.dracin_theme or "")
        return {"success": True, "concept": suggestion.get("suggested_premise", theme), "suggestion": suggestion}
    except Exception as ex:
        log.error("Error auto-suggesting concept: %s", ex)
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/generate")
async def generate_ai_storyboard(
    premise: str = Form(...),
    scene_count: int = Form(4),
    aspect_ratio: str = Form("landscape"),
    character_info: str = Form(""),
    custom_instructions: str = Form(""),
    character_seed: Optional[int] = Form(None),
    microdrama_mode: bool = Form(False),
    ugc_mode: bool = Form(False),
    children_mode: bool = Form(False),
    script_mode: bool = Form(False),
    affiliate_enabled: bool = Form(False),
    affiliate_name: str = Form(""),
    affiliate_benefits: str = Form(""),
    affiliate_cta: str = Form(""),
    affiliate_style: str = Form("soft_selling"),
    affiliate_scene_position: str = Form("auto"),
    affiliate_reference_paths: str = Form("[]"),
    target_country: str = Form(""),
    target_lang: str = Form("Indonesia"),
    dracin_theme: str = Form(""),
    fixed_scene_duration: Optional[int] = Form(None),
    target_total_duration: Optional[int] = Form(None),
    actor_ids: str = Form(""),
    reference_images: List[UploadFile] = File(None),
    affiliate_images: List[UploadFile] = File(None),
):
    try:
        actor_paths = []
        uploaded_paths = []
        actors_db = settings.DATA_DIR / "actors.json"
        all_actors = json.loads(actors_db.read_text(encoding="utf-8")) if actors_db.exists() else []
        character_info, selected_actors = select_actor_references(actor_ids, character_info, all_actors)
        actor_paths.extend(path for item in selected_actors for path in item.get("paths") or [] if Path(path).exists())
        
        if reference_images:
            for img in reference_images:
                if img.filename:
                    ext = Path(img.filename).suffix or ".jpg"
                    file_name = f"ref_{uuid.uuid4().hex[:8]}{ext}"
                    dest = settings.UPLOADS_DIR / file_name
                    with open(dest, "wb") as buffer:
                        shutil.copyfileobj(img.file, buffer)
                    uploaded_paths.append(str(dest))

        saved_paths = actor_paths + uploaded_paths
        try:
            existing_affiliate_paths = json.loads(affiliate_reference_paths or "[]")
        except json.JSONDecodeError:
            existing_affiliate_paths = []
        affiliate_paths = [
            path for path in existing_affiliate_paths
            if isinstance(path, str) and Path(path).exists()
        ]
        if affiliate_images:
            for img in affiliate_images:
                if img.filename:
                    ext = Path(img.filename).suffix or ".jpg"
                    dest = settings.UPLOADS_DIR / f"product_{uuid.uuid4().hex[:8]}{ext}"
                    with open(dest, "wb") as buffer:
                        shutil.copyfileobj(img.file, buffer)
                    affiliate_paths.append(str(dest))

        affiliate_position = (
            int(affiliate_scene_position)
            if str(affiliate_scene_position).isdigit()
            else "auto"
        )
        affiliate_config = {
            "enabled": bool(affiliate_enabled),
            "name": affiliate_name.strip(),
            "benefits": affiliate_benefits.strip(),
            "cta": affiliate_cta.strip(),
            "style": affiliate_style,
            "scene_position": affiliate_position,
            "reference_paths": affiliate_paths,
        }

        storyboard = generate_storyboard(
            premise=premise,
            image_paths=saved_paths,
            scene_count=scene_count,
            aspect_ratio=aspect_ratio,
            character_info=character_info,
            custom_instructions=custom_instructions,
            character_seed=character_seed,
            microdrama_mode=microdrama_mode,
            ugc_mode=ugc_mode,
            children_mode=children_mode,
            script_mode=script_mode,
            affiliate_config=affiliate_config,
            target_country=target_country,
            target_lang=target_lang,
            dracin_theme=dracin_theme,
            fixed_scene_duration=fixed_scene_duration,
            target_total_duration=target_total_duration
        )
        storyboard = attach_character_references(storyboard, selected_actors)

        return {
            "success": True,
            "storyboard": storyboard,
            "reference_images": uploaded_paths,
        }
    except Exception as ex:
        log.error("Error generating storyboard: %s", ex, exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/generate-mv")
async def generate_mv_storyboard(
    lyrics: str = Form(...),
    aspect_ratio: str = Form("landscape"),
    character_info: str = Form(""),
    actor_ids: str = Form(""),
    audio_file: UploadFile = File(...)
):
    try:
        actors_db = settings.DATA_DIR / "actors.json"
        all_actors = json.loads(actors_db.read_text(encoding="utf-8")) if actors_db.exists() else []
        character_info, selected_actors = select_actor_references(actor_ids, character_info, all_actors)
        saved_paths = [path for item in selected_actors for path in item.get("paths") or [] if Path(path).exists()]
        
        ext = Path(audio_file.filename).suffix or ".mp3"
        file_name = f"music_{uuid.uuid4().hex[:8]}{ext}"
        dest = settings.UPLOADS_DIR / file_name
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(audio_file.file, buffer)
        
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(dest)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            duration = float(proc.stdout.strip())
        except (ValueError, TypeError):
            duration = 30.0 # fallback
            
        total_scenes = math.ceil(duration / 10.0)
        
        storyboard = generate_music_video_storyboard(
            lyrics=lyrics,
            audio_duration=duration,
            scene_count=total_scenes,
            aspect_ratio=aspect_ratio,
            character_info=character_info,
            image_paths=saved_paths
        )
        storyboard = attach_character_references(storyboard, selected_actors)
        
        # Inject the audio path so jobs_executor can use it
        storyboard["music_track_path"] = str(dest)

        return {
            "success": True,
            "storyboard": storyboard,
            "audio_duration": duration
        }
    except Exception as ex:
        log.error("Error generating MV storyboard: %s", ex, exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))
