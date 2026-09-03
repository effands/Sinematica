"""Sinematica Backend — Jobs & Execution Router."""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import uuid
import logging

from ..jobs_executor import execute_storyboard_job, get_job_status, get_job_logs, list_jobs, cancel_job, resume_job

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])
log = logging.getLogger("sinematica.routers.jobs")


class JobCreateRequest(BaseModel):
    storyboard: Dict[str, Any]
    theme_image_path: Optional[str] = None
    aspect_ratio: str = "landscape"
    duration: int = 10
    flow_project_id: Optional[str] = None
    # False = honour each scene's own duration from the storyboard (varied pacing).
    force_uniform_duration: bool = False
    # Maximum number of new scene videos for this run. None means render all pending scenes.
    render_scene_limit: Optional[int] = Field(default=None, ge=1)


class JobResumeRequest(BaseModel):
    render_scene_limit: Optional[int] = Field(default=None, ge=1)


@router.post("/create")
async def create_job(req: JobCreateRequest):
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    log.info("Spawning immediate asyncio task for job %s...", job_id)
    asyncio.create_task(
        execute_storyboard_job(
            job_id=job_id,
            storyboard=req.storyboard,
            theme_image_path=req.theme_image_path,
            aspect_ratio=req.aspect_ratio,
            duration=req.duration,
            flow_project_id=req.flow_project_id,
            force_uniform_duration=req.force_uniform_duration,
            render_scene_limit=req.render_scene_limit,
        )
    )

    return {
        "success": True,
        "job_id": job_id,
        "message": "Job eksekusi video telah didaftarkan dan langsung berjalan di background."
    }


@router.get("/list")
def get_all_jobs():
    return {"jobs": list_jobs()}


@router.post("/{job_id}/cancel")
def cancel_running_job(job_id: str):
    success = cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan atau sudah selesai.")
    return {"success": True, "message": f"Job {job_id} berhasil dibatalkan."}


@router.post("/{job_id}/resume")
async def resume_existing_job(job_id: str, req: Optional[JobResumeRequest] = None):
    success = resume_job(job_id, req.render_scene_limit if req else None)
    if not success:
        raise HTTPException(status_code=400, detail="Job tidak dapat dilanjutkan. Pastikan data storyboard tersimpan dan job valid.")
    return {"success": True, "message": f"Job {job_id} berhasil dilanjutkan dari adegan yang belum selesai."}


@router.get("/{job_id}")
def get_single_job(job_id: str):
    job = get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    return {"job": job, "logs": get_job_logs(job_id)}


@router.get("/{job_id}/logs")
def get_single_job_logs(job_id: str):
    return {"job_id": job_id, "logs": get_job_logs(job_id)}
