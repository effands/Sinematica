"""Non-destructive post-production QC using FFmpeg signal statistics."""

from __future__ import annotations

import json
import re
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable


SIGNAL_RE = re.compile(r"lavfi\.signalstats\.(YAVG|UAVG|VAVG|YDIF)=(-?[0-9.]+)")


def parse_signalstats(text: str) -> dict[str, list[float]]:
    values = {key: [] for key in ("YAVG", "UAVG", "VAVG", "YDIF")}
    for key, raw in SIGNAL_RE.findall(text or ""):
        values[key].append(float(raw))
    return values


def summarize_signalstats(values: dict[str, list[float]]) -> dict[str, float | None]:
    def mean(key: str):
        return round(statistics.fmean(values.get(key) or []), 2) if values.get(key) else None
    y = values.get("YAVG") or []
    return {
        "exposure_y": mean("YAVG"), "chroma_u": mean("UAVG"), "chroma_v": mean("VAVG"),
        "mean_frame_difference": mean("YDIF"),
        "luma_variation": round(statistics.pstdev(y), 2) if len(y) > 1 else 0.0 if y else None,
    }


def assess_scene_consistency(scene_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable = [item for item in scene_stats if item.get("exposure_y") is not None]
    if not usable:
        return []
    ref_y = statistics.median(item["exposure_y"] for item in usable)
    ref_u = statistics.median(item["chroma_u"] for item in usable)
    ref_v = statistics.median(item["chroma_v"] for item in usable)
    findings = []
    for index, item in enumerate(scene_stats, start=1):
        if item.get("exposure_y") is None:
            findings.append({"scene": index, "severity": "review", "issue": "video_unreadable"})
            continue
        exposure_delta = abs(item["exposure_y"] - ref_y)
        wb_delta = ((item["chroma_u"] - ref_u) ** 2 + (item["chroma_v"] - ref_v) ** 2) ** .5
        if exposure_delta > 12:
            findings.append({"scene": index, "severity": "warning", "issue": "exposure_mismatch", "delta": round(exposure_delta, 2)})
        if wb_delta > 7:
            findings.append({"scene": index, "severity": "warning", "issue": "white_balance_mismatch", "delta": round(wb_delta, 2)})
        if (item.get("luma_variation") or 0) > 18:
            findings.append({"scene": index, "severity": "review", "issue": "possible_flicker_or_exposure_pumping", "delta": item["luma_variation"]})
    return findings


def build_postproduction_report(
    video_paths: Iterable[str], *, ffmpeg_bin: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    executable = ffmpeg_bin or shutil.which("ffmpeg")
    scene_stats = []
    for raw_path in video_paths:
        path = Path(raw_path)
        if not executable or not path.exists():
            scene_stats.append({"file": path.name, "exposure_y": None, "chroma_u": None, "chroma_v": None})
            continue
        command = [executable, "-hide_banner", "-loglevel", "error", "-i", str(path), "-vf", "fps=2,signalstats,metadata=print:file=-", "-an", "-f", "null", "-"]
        result = runner(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        summary = summarize_signalstats(parse_signalstats((result.stdout or "") + "\n" + (result.stderr or "")))
        scene_stats.append({"file": path.name, **summary})
    findings = assess_scene_consistency(scene_stats)
    return {
        "version": 1,
        "status": "review_needed" if findings else "automatic_checks_passed",
        "reference_policy": "median scene color/exposure; consistency is prioritized over an aggressive look",
        "scene_stats": scene_stats,
        "findings": findings,
        "manual_review": [
            "Watch at 0.5x, especially the first 3 seconds of every clip.",
            "Inspect hands/fingers, mouth, face/skin texture, hair, product edges and object geometry.",
            "Mute once to inspect mouth rhythm, then replay with audio to verify sentence onsets and lipsync drift.",
            "Listen on headphones for missing ambience, excessive music, noisy edits and misplaced foley.",
            "Use crop/cutaway/speed adjustment only after a human confirms the defect; regenerate visible severe defects.",
        ],
        "limitations": "Automated signals flag exposure, white-balance and possible flicker outliers. Warping, texture melting, ghosting and lipsync require visual/audio review and are never auto-repaired.",
    }


def save_postproduction_report(job_dir: Path, video_paths: Iterable[str]) -> tuple[str, dict[str, Any]]:
    report = build_postproduction_report(video_paths)
    output = Path(job_dir) / "postproduction_qc.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output), report
