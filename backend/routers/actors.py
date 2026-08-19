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
    actors = _load_actors()
    return {"success": True, "actors": actors}

@router.post("")
async def create_actor(
    name: str = Form(...),
    description: str = Form(""),
    seed: Optional[int] = Form(None),
    image_file: UploadFile = File(...)
):
    try:
        actors = _load_actors()
        
        ext = Path(image_file.filename).suffix or ".jpg"
        actor_id = uuid.uuid4().hex[:8]
        file_name = f"actor_{actor_id}{ext}"
        dest = ACTORS_IMAGE_DIR / file_name
        
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)
            
        final_seed = seed if seed is not None else random.randint(100000, 999999)
            
        actor = {
            "id": actor_id,
            "name": name.strip(),
            "description": description.strip(),
            "seed": final_seed,
            "image_path": str(dest),
            "image_url": f"/storage/actors/{file_name}"
        }
        
        actors.append(actor)
        _save_actors(actors)
        
        return {"success": True, "actor": actor}
    except Exception as ex:
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
            try:
                if os.path.exists(a["image_path"]):
                    os.remove(a["image_path"])
            except:
                pass
        else:
            new_actors.append(a)
            
    if deleted:
        _save_actors(new_actors)
        return {"success": True}
    raise HTTPException(status_code=404, detail="Aktor tidak ditemukan")
