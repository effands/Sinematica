"""Timing fields shared by automatic and manual render jobs."""

import time
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
