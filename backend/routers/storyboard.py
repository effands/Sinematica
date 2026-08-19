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

router = APIRouter(prefix="/api/storyboard", tags=["Storyboard"])
log = logging.getLogger("sinematica.routers.storyboard")

def _inject_actors_info(actor_ids: str, character_info: str, saved_paths: List[str]) -> str:
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
            
        selected = [a for a in all_actors if a["id"] in actor_ids_list]
        if not selected:
            return character_info
            
        appended_info = "\n\nDAFTAR AKTOR SPESIFIK (PASTIKAN MENGGUNAKAN SEED MEREKA UNTUK KARAKTER INI):\n"
        for idx, a in enumerate(selected):
            appended_info += f"- Aktor {idx+1} ({a['name']}): Seed={a['seed']}, Deskripsi Fisik={a['description']}\n"
            if a.get("image_path") and Path(a["image_path"]).exists():
                saved_paths.append(a["image_path"])
                
        return character_info + appended_info
    except Exception as ex:
        log.warning("Gagal memuat aktor: %s", ex)
        return character_info


class AutoSuggestRequest(BaseModel):
    theme: str
    microdrama_mode: Optional[bool] = False
    target_country: Optional[str] = ""
    dracin_theme: Optional[str] = ""


class SEOKitRequest(BaseModel):
    title: str
    premise: str


class RegenerateSceneRequest(BaseModel):
    film_title: str
    scene_number: int
    scene_title: Optional[str] = ""
    consistent_characters: Optional[str] = ""
    genre_style: Optional[str] = ""


from ..gemini_storyboard import generate_storyboard, auto_suggest_details, generate_youtube_metadata, regenerate_single_scene, generate_music_video_storyboard


@router.post("/seo_kit")
def generate_seo_metadata_kit(req: SEOKitRequest):
    if not req.title:
        req.title = "Film AI Sinematik"
    try:
        data = generate_youtube_metadata(req.title, req.premise or req.title)
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
    target_country: str = Form(""),
    dracin_theme: str = Form(""),
    fixed_scene_duration: Optional[int] = Form(None),
    target_total_duration: Optional[int] = Form(None),
    actor_ids: str = Form(""),
    reference_images: List[UploadFile] = File(None)
):
    try:
        saved_paths = []
        character_info = _inject_actors_info(actor_ids, character_info, saved_paths)
        
        if reference_images:
            for img in reference_images:
                if img.filename:
                    ext = Path(img.filename).suffix or ".jpg"
                    file_name = f"ref_{uuid.uuid4().hex[:8]}{ext}"
                    dest = settings.UPLOADS_DIR / file_name
                    with open(dest, "wb") as buffer:
                        shutil.copyfileobj(img.file, buffer)
                    saved_paths.append(str(dest))

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
            target_country=target_country,
            dracin_theme=dracin_theme,
            fixed_scene_duration=fixed_scene_duration,
            target_total_duration=target_total_duration
        )

        return {
            "success": True,
            "storyboard": storyboard,
            "reference_images": saved_paths,
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
        saved_paths = []
        character_info = _inject_actors_info(actor_ids, character_info, saved_paths)
        
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
