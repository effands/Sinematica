"""Sinematica Backend — Video Gallery & Cinematic Sequencer Router with Complete CRUD Operations."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import os
import shutil

from .. import settings
from ..jobs_executor import (
    list_jobs,
    get_job_status,
    delete_job,
    delete_multiple_jobs,
    update_job,
    create_render_job,
    mark_render_job_completed,
    recover_jobs_from_storage,
)
from ..film_stitcher import stitch_scenes, stitch_scenes_with_transition
from ..gallery_metadata import gallery_metadata

router = APIRouter(prefix="/api/gallery", tags=["Gallery & Sequencer"])


class CompileFilmRequest(BaseModel):
    job_id: str
    scene_video_paths: List[str]
    output_name: Optional[str] = "cinematic_film_custom.mp4"


class BatchDeleteRequest(BaseModel):
    job_ids: List[str]


class ClipRef(BaseModel):
    job_id: str
    filename: str


class RenderSelectionRequest(BaseModel):
    clips: List[ClipRef]
    transition: str = "fade"  # "fade" or "none" (hard cut)
    title: Optional[str] = "Sequencer Custom Render"


class UpdateJobRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None


@router.get("")
def get_gallery_items():
    """Get all generated jobs with video clips and full cinematic film URLs."""
    jobs = sorted(
        recover_jobs_from_storage(),
        key=lambda item: item.get("created_at") or 0,
        reverse=True,
    )
    gallery_data = []

    for job in jobs:
        job_id = job.get("job_id")
        job_dir = settings.JOBS_DIR / job_id

        clips = []
        if job_dir.exists():
            for f in sorted(job_dir.glob("scene_*.mp4")):
                clips.append({
                    "filename": f.name,
                    "local_path": str(f),
                    "url": f"/storage/jobs/{job_id}/{f.name}"
                })

        cinematic_film = None
        cinematic_path = job_dir / "cinematic_film.mp4"
        if cinematic_path.exists():
            cinematic_film = f"/storage/jobs/{job_id}/cinematic_film.mp4"

        import time
        created_ts = job.get("created_at") or time.time()
        created_fmt = job.get("created_at_formatted") or time.strftime("%d %b %Y, %H:%M", time.localtime(created_ts))

        gallery_data.append({
            "job_id": job_id,
            "title": job.get("title", "Film Sinematik"),
            "status": job.get("status"),
            "aspect_ratio": job.get("aspect_ratio", "portrait"),
            "clips": clips,
            "cinematic_film_url": cinematic_film,
            "created_at": created_ts,
            "created_at_formatted": created_fmt,
            **gallery_metadata(job),
        })

    return {"gallery": gallery_data}


@router.put("/{job_id}")
def update_gallery_item(job_id: str, req: UpdateJobRequest):
    """Update title or status of a gallery job item."""
    success = update_job(job_id, new_title=req.title, new_status=req.status)
    if not success:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    return {"success": True, "message": f"Job {job_id} berhasil diperbarui."}


@router.delete("/{job_id}")
def delete_single_job(job_id: str):
    """Delete a single job item and its associated files."""
    success = delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    return {"success": True, "message": f"Job {job_id} berhasil dihapus."}


@router.post("/batch_delete")
def batch_delete_jobs(req: BatchDeleteRequest):
    """Delete multiple selected job items in bulk."""
    count = delete_multiple_jobs(req.job_ids)
    return {"success": True, "deleted_count": count, "message": f"{count} job berhasil dihapus."}


@router.post("/render_selection")
def render_selection(req: RenderSelectionRequest):
    """Auto-render: merge hand-picked clips (from any job) in chosen order with a fade transition."""
    if len(req.clips) < 1:
        raise HTTPException(status_code=400, detail="Pilih minimal 1 klip untuk di-render.")

    paths = []
    for c in req.clips:
        p = settings.JOBS_DIR / c.job_id / c.filename
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"Klip tidak ditemukan: {c.filename}")
        paths.append(str(p))

    job_id = create_render_job(req.title or "Sequencer Custom Render")
    out_dir = settings.JOBS_DIR / job_id

    try:
        if req.transition == "none" or len(paths) < 2:
            output_path = stitch_scenes(out_dir, paths)
        else:
            output_path = stitch_scenes_with_transition(out_dir, paths, transition=req.transition)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Gagal render sequencer: {ex}")

    mark_render_job_completed(job_id, output_path)

    return {
        "success": True,
        "job_id": job_id,
        "message": "Video hasil pilihan berhasil digabungkan!",
        "film_url": f"/storage/jobs/{job_id}/{Path(output_path).name}"
    }


@router.post("/compile_film")
def compile_custom_film(req: CompileFilmRequest):
    """Compile ordered video clips into a single cinematic film."""
    job_dir = settings.JOBS_DIR / req.job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Directory job tidak ditemukan.")

    try:
        out_name = req.output_name or "cinematic_film_custom.mp4"
        output_path = stitch_scenes(job_dir, req.scene_video_paths, output_filename=out_name)

        return {
            "success": True,
            "message": "Film sinematik berhasil digabungkan!",
            "film_url": f"/storage/jobs/{req.job_id}/{out_name}"
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Gagal gabungkan film: {ex}")
