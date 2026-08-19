"""Sinematica Backend — Cinematic Film Stitcher (FFmpeg Video Merger) & SRT Subtitle Generator."""

import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any

log = logging.getLogger("sinematica.film_stitcher")


def extract_continuity_frame(
    video_path: Path,
    output_path: Path,
    *,
    ffmpeg_bin: str = None,
    runner=subprocess.run,
) -> str | None:
    """Extract a stable frame 0.2 seconds before a scene ends for the next scene."""
    source = Path(video_path)
    destination = Path(output_path)
    executable = ffmpeg_bin or shutil.which("ffmpeg")
    if not executable or not source.exists():
        return None

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "-y",
        "-sseof", "-0.2",
        "-i", str(source),
        "-frames:v", "1",
        "-q:v", "2",
        str(destination),
    ]
    proc = runner(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode == 0 and destination.exists() and destination.stat().st_size > 0:
        return str(destination)

    destination.unlink(missing_ok=True)
    log.warning("Gagal mengekstrak continuity frame dari %s: %s", source, proc.stderr[-300:])
    return None


def format_srt_timestamp(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def generate_srt_subtitles(job_dir: Path, scenes: List[Dict[str, Any]], duration_per_scene: int = 10) -> str:
    """Generate an SRT subtitle file from narration text per scene.

    Each scene can carry its own `duration`; `duration_per_scene` is only the fallback for
    scenes that do not. Using a single fixed length would desynchronise every later subtitle
    once the storyboard mixes 4s and 10s shots.
    """
    srt_path = job_dir / "subtitles.srt"
    current_time = 0.0

    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, sc in enumerate(scenes, start=1):
            try:
                scene_len = float(sc.get("duration") or duration_per_scene)
            except (TypeError, ValueError):
                scene_len = float(duration_per_scene)
            if scene_len <= 0:
                scene_len = float(duration_per_scene)

            narration = sc.get("narration_id") or sc.get("action_summary") or sc.get("title", "")
            if not narration:
                current_time += scene_len
                continue

            start_ts = format_srt_timestamp(current_time)
            end_ts = format_srt_timestamp(current_time + max(scene_len - 0.5, 0.5))

            f.write(f"{idx}\n")
            f.write(f"{start_ts} --> {end_ts}\n")
            f.write(f"{narration}\n\n")

            current_time += scene_len

    log.info("Subtitle SRT berhasil dibuat: %s", srt_path)
    return str(srt_path)


def _probe_duration(ffprobe_bin: str, path: str) -> float:
    proc = subprocess.run(
        [ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        return float(proc.stdout.strip())
    except (ValueError, TypeError):
        return 10.0


def stitch_scenes_with_transition(job_dir: Path, ordered_video_paths: List[str],
                                   transition: str = "fade", transition_duration: float = 0.6,
                                   output_filename: str = "cinematic_film.mp4") -> str:
    """Concatenate scene MP4s with a simple crossfade/dissolve transition between each clip using FFmpeg xfade."""
    existing_files = [p for p in ordered_video_paths if os.path.exists(p)]
    if len(existing_files) < 2:
        return stitch_scenes(job_dir, existing_files, output_filename=output_filename)

    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    if not ffmpeg_bin or not ffprobe_bin:
        log.warning("FFmpeg/FFprobe tidak ditemukan, transisi fade dilewati (fallback hard-cut concat)...")
        return stitch_scenes(job_dir, existing_files, output_filename=output_filename)

    xfade_style = "fade" if transition not in ("fade", "dissolve", "wipeleft", "wiperight") else transition
    durations = [_probe_duration(ffprobe_bin, p) for p in existing_files]

    inputs: List[str] = []
    for p in existing_files:
        inputs += ["-i", p]

    filter_parts = []
    last_v = "0:v"
    last_a = "0:a"
    cumulative = durations[0]

    for i in range(1, len(existing_files)):
        d = max(0.1, min(transition_duration, durations[i - 1] - 0.1, durations[i] - 0.1))
        offset = max(0.0, cumulative - d)
        vout = f"v{i}"
        aout = f"a{i}"
        filter_parts.append(f"[{last_v}][{i}:v]xfade=transition={xfade_style}:duration={d:.2f}:offset={offset:.2f}[{vout}]")
        filter_parts.append(f"[{last_a}][{i}:a]acrossfade=d={d:.2f}[{aout}]")
        last_v, last_a = vout, aout
        cumulative += durations[i] - d

    output_path = job_dir / output_filename
    cmd = [ffmpeg_bin, "-y"] + inputs + [
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{last_v}]", "-map", f"[{last_a}]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac",
        str(output_path)
    ]

    log.info("Running FFmpeg crossfade stitch (%s, %d klip)...", xfade_style, len(existing_files))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        log.warning("Crossfade stitch gagal (%s), fallback ke hard-cut concat...", proc.stderr[-300:])
        return stitch_scenes(job_dir, existing_files, output_filename=output_filename)

    log.info("Film sinematik dengan transisi berhasil dibuat! %s", output_path)
    return str(output_path)


def stitch_scenes(job_dir: Path, ordered_video_paths: List[str], output_filename: str = "cinematic_film.mp4") -> str:
    """Concatenate ordered scene MP4 files into a single high-quality cinematic film."""
    if not ordered_video_paths:
        raise ValueError("Tidak ada video adegan yang dipilih untuk digabungkan.")

    existing_files = [p for p in ordered_video_paths if os.path.exists(p)]
    if not existing_files:
        raise ValueError("File video adegan tidak ditemukan di disk.")

    concat_file_path = job_dir / "concat_list.txt"
    output_path = job_dir / output_filename

    # Create FFmpeg concat list file
    with open(concat_file_path, "w", encoding="utf-8") as f:
        for vp in existing_files:
            clean_path = str(Path(vp).resolve()).replace("\\", "/")
            f.write(f"file '{clean_path}'\n")

    # Check if FFmpeg is available on system
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        log.info("FFmpeg binary tidak ditemukan di PATH, mencoba moviepy fallback...")
        try:
            from moviepy.editor import VideoFileClip, concatenate_videoclips
            clips = [VideoFileClip(p) for p in existing_files]
            final_clip = concatenate_videoclips(clips, method="compose")
            final_clip.write_videofile(str(output_path), codec="libx264", audio_codec="aac")
            for clip in clips:
                clip.close()
            return str(output_path)
        except Exception as ex:
            raise RuntimeError(f"Gagal menggabungkan video dengan MoviePy: {ex}")

    # Use FFmpeg fast concat
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file_path),
        "-c", "copy",
        str(output_path)
    ]

    log.info("Running FFmpeg concat command: %s", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if proc.returncode != 0:
        cmd_reencode = [
            ffmpeg_bin,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            str(output_path)
        ]
        log.info("Retrying FFmpeg re-encode concat: %s", " ".join(cmd_reencode))
        proc2 = subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc2.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {proc2.stderr}")

    log.info("Film sinematik berhasil digabungkan! %s", output_path)
    return str(output_path)


def mux_audio_to_video(job_dir: Path, video_path: str, audio_path: str, output_filename: str = "cinematic_film_with_audio.mp4") -> str:
    """Mux background audio track onto the video using FFmpeg.
    
    Replaces the original video's audio with the new audio track and trims to the shortest stream.
    """
    if not os.path.exists(video_path) or not os.path.exists(audio_path):
        log.warning("File tidak ditemukan untuk proses mux_audio_to_video.")
        return video_path
        
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        log.warning("FFmpeg tidak ditemukan, skip muxing audio.")
        return video_path
        
    output_path = job_dir / output_filename
    
    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0?",
        "-map", "1:a:0?",
        "-shortest",
        str(output_path)
    ]
    
    log.info("Running FFmpeg audio mux command...")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        log.warning("Muxing audio gagal: %s", proc.stderr)
        return video_path
        
    log.info("Audio track berhasil digabungkan (muxed)! %s", output_path)
    return str(output_path)
