"""Sinematica Backend — Actors/Character Registry Router."""

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from typing import List, Dict, Any, Optional
import shutil
import uuid
import logging
import json
import os
import random
from pathlib import Path

from .. import settings
from ..actor_references import actor_reference_paths, normalize_actor, validate_image_uploads

router = APIRouter(prefix="/api/actors", tags=["Actors"])
log = logging.getLogger("sinematica.routers.actors")

ACTORS_DB_PATH = settings.DATA_DIR / "actors.json"
ACTORS_IMAGE_DIR = settings.DATA_DIR.parent / "storage" / "actors"

os.makedirs(ACTORS_IMAGE_DIR, exist_ok=True)

def _load_actors() -> List[Dict[str, Any]]:
    if not ACTORS_DB_PATH.exists():
        return []
    try:
        with open(ACTORS_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        log.warning("Gagal memuat actors.json: %s", ex)
        return []

def _save_actors(actors: List[Dict[str, Any]]):
    with open(ACTORS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(actors, f, indent=4)

@router.get("")
def list_actors():
    actors = [normalize_actor(actor) for actor in _load_actors()]
    return {"success": True, "actors": actors}

@router.post("")
async def create_actor(
    name: str = Form(...),
    description: str = Form(""),
    seed: Optional[int] = Form(None),
    image_files: List[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
):
    uploads = [item for item in (image_files or []) if item and getattr(item, "filename", None)]
    if image_file and getattr(image_file, "filename", None):
        uploads.append(image_file)
    try:
        validate_image_uploads(uploads)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))

    written = []
    try:
        actors = _load_actors()
        actor_id = uuid.uuid4().hex[:8]
        images = []
        extensions = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
        for index, upload in enumerate(uploads, start=1):
            ext = extensions[upload.content_type.casefold()]
            file_name = f"actor_{actor_id}_{index}{ext}"
            dest = ACTORS_IMAGE_DIR / file_name
            with open(dest, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            written.append(dest)
            images.append({
                "path": str(dest),
                "url": f"/storage/actors/{file_name}",
                "primary": index == 1,
            })
            
        final_seed = seed if seed is not None else random.randint(100000, 999999)
            
        actor = {
            "id": actor_id,
            "name": name.strip(),
            "description": description.strip(),
            "seed": final_seed,
            "images": images,
            "image_path": images[0]["path"],
            "image_url": images[0]["url"],
        }
        
        actors.append(actor)
        _save_actors(actors)
        
        return {"success": True, "actor": actor}
    except Exception as ex:
        for path in written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        log.error("Error mendaftarkan aktor: %s", ex)
        raise HTTPException(status_code=500, detail=str(ex))

@router.delete("/{actor_id}")
def delete_actor(actor_id: str):
    actors = _load_actors()
    new_actors = []
    deleted = False
    for a in actors:
        if a["id"] == actor_id:
            deleted = True
            root = ACTORS_IMAGE_DIR.resolve()
            for raw_path in actor_reference_paths(a):
                try:
                    path = Path(raw_path).resolve()
                    path.relative_to(root)
                    if path.is_file():
                        path.unlink()
                except (OSError, ValueError):
                    pass
        else:
            new_actors.append(a)
            
    if deleted:
        _save_actors(new_actors)
        return {"success": True}
    raise HTTPException(status_code=404, detail="Aktor tidak ditemukan")
