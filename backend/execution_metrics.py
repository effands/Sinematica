"""Timing fields shared by automatic and manual render jobs."""

import time
from pathlib import Path
from typing import Any, Dict, Optional


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def finish_job_timing(job: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    finished = time.time() if now is None else float(now)
    started = float(job.get("started_at") or job.get("created_at") or finished)
    elapsed = round(max(0.0, finished - started), 3)
    job["started_at"] = started
    job["completed_at"] = finished
    job["processing_seconds"] = elapsed
    job["processing_duration"] = format_elapsed(elapsed)
    return job


def record_output_file_size(job: Dict[str, Any], output_path) -> Dict[str, Any]:
    size_bytes = Path(output_path).stat().st_size
    size_mb = round(size_bytes / (1024 * 1024), 2)
    job["output_size_bytes"] = size_bytes
    job["output_size_mb"] = size_mb
    job["output_size_display"] = f"{size_bytes / (1024 * 1024):.2f} MB"
    return job
