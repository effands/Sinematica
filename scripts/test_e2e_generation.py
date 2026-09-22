#!/usr/bin/env python3
"""
Sinematica AI Studio — Automated E2E Scene Generation Test Runner.
Executes real scene generation directly from Scene Master / saved job history
without requiring manual browser clicks, auto-verifies server and fleet connectivity,
and streams crystal-clear real-time generation logs.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

DEFAULT_HISTORY_FILE = WORKSPACE_DIR / "data" / "jobs_history.json"
DEFAULT_PORT = 8888

# ANSI Terminal Colors
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
DIM = "\033[2m"


def parse_cli_arguments(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sinematica AI Studio - Automated E2E Scene Generation Test Runner"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Sinematica backend port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum number of new scenes to render for this test run (default: 1 for quick E2E verification, set 0 for all)",
    )
    parser.add_argument(
        "--scene",
        type=int,
        default=None,
        help="Target a specific single scene number to test (e.g. --scene 1)",
    )
    parser.add_argument(
        "--job-id",
        type=str,
        default=None,
        help="Explicit job ID to resume/test (defaults to the latest job in Scene Master / history)",
    )
    parser.add_argument(
        "--no-auto-start",
        action="store_true",
        help="Do not auto-start the Sinematica server if it is offline",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Total test timeout in seconds (default: 900s / 15 minutes)",
    )
    return parser.parse_args(argv)


def _http_get(url: str, timeout: float = 3.0) -> Tuple[int, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Sinematica-E2E-Runner/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            body = response.read().decode("utf-8")
            try:
                return status, json.loads(body)
            except Exception:
                return status, body
    except urllib.error.HTTPError as err:
        try:
            body = err.read().decode("utf-8")
            return err.code, json.loads(body)
        except Exception:
            return err.code, None
    except Exception:
        return 0, None


def _http_post(url: str, payload: Optional[dict] = None, timeout: float = 5.0) -> Tuple[int, Any]:
    data_bytes = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            "User-Agent": "Sinematica-E2E-Runner/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            body = response.read().decode("utf-8")
            try:
                return status, json.loads(body)
            except Exception:
                return status, body
    except urllib.error.HTTPError as err:
        try:
            body = err.read().decode("utf-8")
            return err.code, json.loads(body)
        except Exception:
            return err.code, None
    except Exception:
        return 0, None


def check_server_health(base_url: str, timeout: float = 2.0) -> bool:
    status, data = _http_get(f"{base_url}/api/status", timeout=timeout)
    return status == 200 and isinstance(data, dict)


def ensure_server_running(base_url: str, port: int = DEFAULT_PORT) -> Optional[subprocess.Popen]:
    if check_server_health(base_url):
        return None

    print(f"{YELLOW}[SYS]{RESET} Server Sinematica offline di port {port}. Menjalankan server otomatis...")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        cmd,
        cwd=str(WORKSPACE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 15
    while time.time() < deadline:
        if check_server_health(base_url):
            print(f"{GREEN}[SYS]{RESET} Server Sinematica siap di {base_url}!")
            return process
        time.sleep(0.5)

    print(f"{RED}[ERROR]{RESET} Timeout menunggu server Sinematica aktif di port {port}.")
    return process


def check_fleet_ready(
    base_url: str, mock_data: Optional[dict] = None
) -> Tuple[bool, str, List[dict]]:
    if mock_data is not None:
        profiles = mock_data.get("profiles", [])
    else:
        status, data = _http_get(f"{base_url}/api/fleet", timeout=3.0)
        if status != 200 or not isinstance(data, dict):
            return False, "Gagal menghubungi endpoint /api/fleet", []
        profiles = data.get("profiles", [])

    if not profiles:
        return (
            False,
            "Tidak ada profil Chrome Extension yang terhubung. Buka Chrome dengan ekstensi Sinematica aktif.",
            [],
        )

    connected_profiles = [p for p in profiles if p.get("connected")]
    if not connected_profiles:
        return False, "Profil Chrome terdaftar tetapi status disconnected.", profiles

    ready_profiles = [p for p in connected_profiles if p.get("ready", True) and p.get("logged_in")]
    if not ready_profiles:
        instance_ids = ", ".join(p.get("instance_id", "unknown") for p in connected_profiles)
        return (
            True,
            f"Profil Chrome terhubung ({instance_ids}), sesi Google Flow aktif.",
            connected_profiles,
        )

    instance_ids = ", ".join(p.get("instance_id", "unknown") for p in ready_profiles)
    return (
        True,
        f"Profil Chrome Fleet siap ({len(ready_profiles)} profil: {instance_ids}).",
        ready_profiles,
    )


def find_latest_scene_master_job(history_file_path: Path = DEFAULT_HISTORY_FILE) -> Optional[dict]:
    if not history_file_path.exists():
        return None
    try:
        with open(history_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            valid_jobs = [
                j
                for j in data
                if isinstance(j, dict)
                and (j.get("storyboard") or j.get("seo_storyboard"))
            ]
            if valid_jobs:
                return valid_jobs[0]
            return data[0] if isinstance(data[0], dict) else None
    except Exception as ex:
        print(f"{YELLOW}[WARN]{RESET} Gagal membaca history jobs: {ex}")
    return None


def trigger_job_resume(
    base_url: str,
    job_id: str,
    limit: Optional[int] = None,
    scene_start: Optional[int] = None,
    scene_end: Optional[int] = None,
) -> dict:
    payload = {}
    if limit is not None and limit > 0:
        payload["render_scene_limit"] = limit
    if scene_start is not None and scene_start > 0:
        payload["render_scene_start"] = scene_start
    if scene_end is not None and scene_end > 0:
        payload["render_scene_end"] = scene_end

    status, data = _http_post(f"{base_url}/api/jobs/{job_id}/resume", payload, timeout=6.0)
    if status != 200:
        raise RuntimeError(
            f"Gagal melanjutkan job {job_id} (HTTP {status}): {data.get('detail') if isinstance(data, dict) else data}"
        )
    return data if isinstance(data, dict) else {}


def format_log_line(entry: dict) -> str:
    ts = entry.get("timestamp", time.strftime("%H:%M:%S"))
    msg = entry.get("message", "")
    profile = entry.get("profile", "System")
    lvl = entry.get("level", "info").lower()

    if "berhasil" in msg.lower() or "success" in msg.lower() or lvl == "success" or "ready" in msg.lower():
        color = GREEN
        icon = "✔"
    elif "gagal" in msg.lower() or "error" in msg.lower() or lvl == "error" or "timeout" in msg.lower():
        color = RED
        icon = "✖"
    elif "warning" in msg.lower() or "warn" in lvl:
        color = YELLOW
        icon = "⚠"
    elif "mengirim" in msg.lower() or "render" in msg.lower() or "%" in msg:
        color = CYAN
        icon = "⚙"
    else:
        color = BLUE
        icon = "ℹ"

    return f"{DIM}[{ts}]{RESET} {color}{icon} [{profile}] {msg}{RESET}"


def stream_job_logs_until_completion(
    base_url: str,
    job_id: str,
    poll_interval: float = 1.0,
    max_timeout: int = 900,
) -> Tuple[bool, dict]:
    print(f"\n{BOLD}=================== LIVE GENERATION TEST LOG STREAM ==================={RESET}")
    print(f"Memantau eksekusi Job ID: {CYAN}{job_id}{RESET}...")
    print(f"{BOLD}======================================================================={RESET}\n")

    seen_log_count = 0
    start_time = time.time()
    last_status = ""

    while time.time() - start_time < max_timeout:
        status, data = _http_get(f"{base_url}/api/jobs/{job_id}", timeout=4.0)
        if status == 200 and isinstance(data, dict):
            job = data.get("job") or {}
            logs = data.get("logs") or []

            # Print fresh logs
            if len(logs) > seen_log_count:
                for entry in logs[seen_log_count:]:
                    print(format_log_line(entry))
                seen_log_count = len(logs)

            job_status = job.get("status", "processing")
            if job_status != last_status:
                last_status = job_status

            if job_status == "completed":
                print(f"\n{GREEN}{BOLD}✔ JOB SELESAI DENGAN SUKSES!{RESET}")
                return True, job
            elif job_status in ("failed", "cancelled"):
                print(f"\n{RED}{BOLD}✖ JOB BERAKHIR DENGAN STATUS: {job_status.upper()}{RESET}")
                return False, job

        time.sleep(poll_interval)

    print(f"\n{RED}{BOLD}✖ TIMEOUT PENGUJIAN ({max_timeout}s) TERCAPAI.{RESET}")
    return False, {}


def cancel_running_job(base_url: str, job_id: str) -> None:
    print(f"\n{YELLOW}[SYS]{RESET} Membatalkan job {job_id}...")
    _http_post(f"{base_url}/api/jobs/{job_id}/cancel", {}, timeout=3.0)


def print_summary_report(job: dict) -> None:
    print(f"\n{BOLD}==================== GENERATION TEST SUMMARY ===================={RESET}")
    title = job.get("title", "Untitled")
    job_id = job.get("job_id", "-")
    status = job.get("status", "unknown")
    total_scenes = job.get("total_scenes", 0)
    film_path = job.get("cinematic_film_path")
    scenes = job.get("scenes", [])

    status_color = GREEN if status == "completed" else RED
    print(f"Judul Film    : {BOLD}{title}{RESET}")
    print(f"Job ID        : {CYAN}{job_id}{RESET}")
    print(f"Status Akhir  : {status_color}{status.upper()}{RESET}")
    print(f"Total Adegan  : {len(scenes)} / {total_scenes}")

    if scenes:
        print("\nRincian Adegan:")
        for sc in scenes:
            num = sc.get("scene_number", "?")
            sc_stat = sc.get("status", "pending")
            vpath = sc.get("video_path") or "-"
            print(f"  - Adegan #{num:02d} [{sc_stat.upper()}]: {vpath}")

    if film_path:
        print(f"\nFile Video Utama: {GREEN}{film_path}{RESET}")
    print(f"{BOLD}================================================================={RESET}\n")


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_cli_arguments(argv)
    base_url = f"http://127.0.0.1:{args.port}"

    print(f"\n{BOLD}==================================================================={RESET}")
    print(f"   {CYAN}SINEMATICA AI STUDIO — AUTOMATED E2E SCENE TEST RUNNER{RESET}")
    print(f"{BOLD}==================================================================={RESET}\n")

    # 1. Ensure Backend Server is online
    server_process = None
    if not check_server_health(base_url):
        if args.no_auto_start:
            print(f"{RED}[ERROR]{RESET} Server di {base_url} tidak aktif. Jalankan server terlebih dahulu.")
            return 1
        server_process = ensure_server_running(base_url, port=args.port)
        if not check_server_health(base_url):
            return 1
    else:
        print(f"{GREEN}[SYS]{RESET} Terhubung ke Backend Sinematica di {base_url}.")

    # 2. Check Chrome Fleet connection
    fleet_ready, fleet_msg, profiles = check_fleet_ready(base_url)
    print(f"{CYAN}[FLEET]{RESET} {fleet_msg}")
    if not fleet_ready:
        print(f"{YELLOW}[TIPS]{RESET} Buka Google Chrome dengan ekstensi Sinematica aktif dan tab Google Flow terbuka.")
        return 1

    # 3. Identify Job to execute / resume
    target_job_id = args.job_id
    target_job = None

    if not target_job_id:
        target_job = find_latest_scene_master_job()
        if target_job:
            target_job_id = target_job.get("job_id")
            title = target_job.get("title", "Scene Master Storyboard")
            print(f"{GREEN}[SCENE MASTER]{RESET} Mengambil storyboard Scene Master terbaru: {BOLD}'{title}'{RESET} ({target_job_id})")

    if not target_job_id:
        print(f"{RED}[ERROR]{RESET} Tidak ditemukan storyboard/job yang tersimpan di Scene Master (data/jobs_history.json).")
        return 1

    # 4. Trigger Resume Execution
    limit = args.limit if (args.limit and args.limit > 0) else None
    scene_start = args.scene if args.scene else None
    scene_end = args.scene if args.scene else None

    print(f"{CYAN}[SYS]{RESET} Memulai eksekusi otomatis (Limit: {limit or 'Semua'}, Scene: {args.scene or 'Otomatis'})...")
    try:
        trigger_job_resume(
            base_url=base_url,
            job_id=target_job_id,
            limit=limit,
            scene_start=scene_start,
            scene_end=scene_end,
        )
    except Exception as ex:
        print(f"{RED}[ERROR]{RESET} {ex}")
        return 1

    # 5. Stream Live Logs
    success = False
    final_job = {}
    try:
        success, final_job = stream_job_logs_until_completion(
            base_url=base_url,
            job_id=target_job_id,
            max_timeout=args.timeout,
        )
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[USER]{RESET} Pengujian dihentikan pengguna.")
        cancel_running_job(base_url, target_job_id)
        return 130

    # 6. Report Summary
    if final_job:
        print_summary_report(final_job)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
