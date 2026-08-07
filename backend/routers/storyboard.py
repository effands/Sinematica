"""Sinematica Backend — Storyboard Generation Router."""

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import shutil
import uuid
import logging
from pathlib import Path

from .. import settings

router = APIRouter(prefix="/api/storyboard", tags=["Storyboard"])
log = logging.getLogger("sinematica.routers.storyboard")


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


from ..gemini_storyboard import generate_storyboard, auto_suggest_details, generate_youtube_metadata, regenerate_single_scene


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
    reference_images: List[UploadFile] = File(None)
):
    try:
        saved_paths = []
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
