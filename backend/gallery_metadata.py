"""Presentation-safe metadata exposed by the Video Gallery API."""


def gallery_metadata(job):
    return {
        "total_duration": job.get("total_duration"),
        "output_size_bytes": job.get("output_size_bytes"),
        "output_size_display": job.get("output_size_display"),
        "processing_seconds": job.get("processing_seconds"),
        "processing_duration": job.get("processing_duration"),
        "initial_prompt": job.get("initial_prompt") or job.get("premise") or "",
    }
