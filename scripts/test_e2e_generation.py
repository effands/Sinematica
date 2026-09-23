#!/usr/bin/env python3
"""
Sinematica AI Studio — Automated E2E Scene Generation Test Runner.
Executes real scene generation directly from Scene Master / saved job history
without requiring manual browser clicks, auto-verifies server and fleet connectivity,
and streams crystal-clear real-time generation logs.
"""

import argparse
import datetime
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

from backend import settings

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


class ProductionExecutionLogger:
    """Manages high-fidelity production diagnostic logging to console and disk."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or (settings.DATA_DIR / "logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"e2e_test_generation_{timestamp_str}.log"
        self.jsonl_file = self.log_dir / f"e2e_test_generation_{timestamp_str}.jsonl"

        # Initialize log header
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(" SINEMATICA AI STUDIO — E2E SCENE TEST EXECUTION & DIAGNOSTIC LOG\n")
            f.write(f" Started at : {datetime.datetime.now().isoformat()}\n")
            f.write(f" Python     : {sys.version.split()[0]} ({sys.platform})\n")
            f.write(f" Log File   : {self.log_file}\n")
            f.write("=" * 80 + "\n\n")

    def log(
        self,
        level: str,
        component: str,
        message: str,
        meta: Optional[Dict[str, Any]] = None,
        diagnostic: Optional[Dict[str, Any]] = None,
    ):
        now = datetime.datetime.now()
        iso_ts = now.isoformat()
        time_str = now.strftime("%H:%M:%S.%f")[:-3]
        lvl = level.upper()

        icon = "ℹ️"
        color = BLUE
        if lvl in ("ERROR", "ERR"):
            icon = "❌"
            color = RED
        elif lvl in ("WARN", "WARNING"):
            icon = "⚠️"
            color = YELLOW
        elif lvl in ("RETRY", "AUTO_RETRY"):
            icon = "🔁"
            color = MAGENTA
        elif lvl in ("SUCCESS", "READY", "COMPLETED"):
            icon = "✅"
            color = GREEN
        elif lvl in ("PROG", "PROGRESS"):
            icon = "⏳"
            color = CYAN
        elif lvl in ("DIAG", "DIAGNOSTIC"):
            icon = "🔬"
            color = CYAN

        line = f"[{time_str}] [{lvl:5s}] [{component:16s}] {icon} {message}"
        print(f"{color}{line}{RESET}")

        # Write formatted text to log file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{iso_ts}] [{lvl}] [{component}] {message}\n")
                if meta:
                    f.write(f"   ├─ META: {json.dumps(meta, ensure_ascii=False)}\n")
                if diagnostic:
                    f.write(f"   └─ DIAGNOSTIC: {json.dumps(diagnostic, ensure_ascii=False)}\n")
        except Exception:
            pass

        # Write structured JSONL
        try:
            record = {
                "timestamp": iso_ts,
                "level": lvl,
                "component": component,
                "message": message,
                "meta": meta or {},
                "diagnostic": diagnostic or {},
            }
            with open(self.jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def log_diagnostic_card(
        self,
        classification: str,
        root_cause: str,
        evidence: str,
        action_taken: str,
        technical_advice: str,
    ):
        card = [
            f"   ┌── 🔬 [PRODUCTION DIAGNOSTIC ANALYSIS] ────────────────────────────",
            f"   │  • Classification : {classification}",
            f"   │  • Root Cause     : {root_cause}",
            f"   │  • Evidence       : {evidence}",
            f"   │  • Action Taken   : {action_taken}",
            f"   │  • Troubleshooting: {technical_advice}",
            f"   └───────────────────────────────────────────────────────────────────",
        ]
        formatted_card = "\n".join(card)
        print(f"{YELLOW}{formatted_card}{RESET}")

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(formatted_card + "\n")
        except Exception:
            pass


prod_logger = ProductionExecutionLogger()


def diagnose_log_message(msg: str, lvl: str) -> Optional[Dict[str, str]]:
    """Extracts technical root-cause diagnostics and remediation advice for an event."""
    lower_msg = str(msg).lower()

    if (
        "kartu kendala" in lower_msg
        or "gagal dibuat" in lower_msg
        or "failed to generate" in lower_msg
        or "flow-error-tile" in lower_msg
        or "image_retry" in lower_msg
        or "video_retry" in lower_msg
    ):
        return {
            "classification": "GOOGLE_FLOW_MEDIA_GENERATION_FAILED",
            "root_cause": "Google Flow engine mengalami interupsi render sementara atau model timeout pada kanvas.",
            "evidence": "Elemen <flow-error-tile> terdeteksi pada kanvas Flow ('Maaf, video/gambar ini gagal dibuat').",
            "action_taken": "Ekstensi otomatis memicu tombol Retry / Coba Lagi (maksimal 2x percobaan).",
            "technical_advice": "Jika gagal berulang setelah 2x retry, periksa ketersediaan kuota Google Sandbox atau rotasi profil.",
        }

    if "401" in lower_msg or "unauthenticated" in lower_msg or "login" in lower_msg or "sesi" in lower_msg:
        return {
            "classification": "GOOGLE_FLOW_AUTH_SESSION_EXPIRED",
            "root_cause": "Token otorisasi OAuth / SAPISID cookie sesi Google Flow telah kedaluwarsa.",
            "evidence": "Backend menerima respons HTTP 401 Unauthenticated dari API Google Flow.",
            "action_taken": "Ekstensi mencoba auto-probe cookie sesi SAPISID dari tab aktif.",
            "technical_advice": "Buka tab Google Flow di Chrome lalu buka sidepanel ekstensi untuk memperbarui token.",
        }

    if (
        "429" in lower_msg
        or "kuota" in lower_msg
        or "quota" in lower_msg
        or "credit" in lower_msg
        or "resource_exhausted" in lower_msg
        or "kredit habis" in lower_msg
    ):
        return {
            "classification": "GOOGLE_FLOW_RESOURCE_EXHAUSTED_OR_RATE_LIMITED",
            "root_cause": "Batas kuota harian atau rate-limit per menit pada akun Google aktif telah tercapai.",
            "evidence": "Respons HTTP 429 atau pesan kuota habis diterima dari server Google.",
            "action_taken": "Task executor otomatis menjadwalkan rotasi ke profil Chrome alternatif berikutnya.",
            "technical_advice": "Tambahkan profil Google akun cadangan pada fleet ekstensi atau tunggu periode reset kuota.",
        }

    if (
        "kebijakan" in lower_msg
        or "policy" in lower_msg
        or "safety" in lower_msg
        or "filter" in lower_msg
        or "ditolak google flow" in lower_msg
    ):
        return {
            "classification": "GOOGLE_FLOW_POLICY_SAFETY_TRIGGERED",
            "root_cause": "Prompt teks atau komposisi referensi memicu sistem filter keamanan Google Flow.",
            "evidence": "Intersepsi pesan pelanggaran kebijakan konten dari Google Flow.",
            "action_taken": "Sistem AI Studio otomatis mereformulasi sinonim prompt dramatis yang aman.",
            "technical_advice": "Pastikan deskripsi visual tidak memuat figur berhak cipta terlarang atau tokoh nyata sensitif.",
        }

    if (
        "content_script_unreachable" in lower_msg
        or "disconnect" in lower_msg
        or "terputus" in lower_msg
        or "tidak ada profil chrome" in lower_msg
    ):
        return {
            "classification": "CHROME_EXTENSION_BRIDGE_DISCONNECTED",
            "root_cause": "Tab Google Flow tertutup atau direfresh sehingga koneksi WebSocket/content script terputus.",
            "evidence": "Kegagalan pengiriman pesan via chrome.tabs.sendMessage / WebSocket bridge.",
            "action_taken": "Sistem memicu auto-reconnect backoff (basis 1.5s exponential).",
            "technical_advice": "Pastikan tab Google Flow tetap terbuka dan saklar ekstensi Sinematica tetap ON.",
        }

    if "gagal mengunduh" in lower_msg or "unduhan media flow" in lower_msg or "transfer mp4 tidak lengkap" in lower_msg:
        return {
            "classification": "MEDIA_DOWNLOAD_CORRUPTED_OR_TIMEOUT",
            "root_cause": "Kegagalan transfer byte stream chunk atau timeout koneksi saat mengunduh media dari Google CDN.",
            "evidence": "Ukuran payload tidak sesuai atau status HTTP download gagal.",
            "action_taken": "Sistem mengulang unduhan media terautentikasi melalui tab Chrome.",
            "technical_advice": "Periksa kestabilan bandwidth internet dan pastikan sesi download memiliki cookie lengkap.",
        }

    return None


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
        default=0,
        help="Maximum number of new scenes to render for this test run (default: 0 for all pending scenes, set 1 for single-scene checkpoint)",
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
    parser.add_argument(
        "--interactive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prompt to press Enter to retry if Chrome Extension is not connected (default: True)",
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


def wait_for_fleet_interactive(
    base_url: str,
    interactive: bool = True,
) -> Tuple[bool, str, List[dict]]:
    """Check Chrome fleet connectivity. If not ready and interactive=True, prompt the user to connect and press Enter to retry."""
    while True:
        fleet_ready, fleet_msg, profiles = check_fleet_ready(base_url)
        if fleet_ready:
            return True, fleet_msg, profiles

        print(f"\n{YELLOW}==============================================================================={RESET}")
        print(f"{YELLOW}{BOLD} ⚠️ [PERINGATAN] Ekstensi Chrome Sinematica Belum Terhubung atau Belum Siap!{RESET}")
        print(f"{YELLOW}==============================================================================={RESET}")
        print("  Petunjuk langkah cepat:")
        print("  1. Buka browser Google Chrome tempat ekstensi Sinematica terpasang.")
        print("  2. Buka tab Google Flow (https://flow.google.com) dan buka proyek Anda.")
        print("  3. Pastikan ekstensi Sinematica aktif dan terhubung.")
        print("-------------------------------------------------------------------------------")
        print(f"  👉 {GREEN}Tekan [ENTER]{RESET} untuk memeriksa kembali koneksi ekstensi...")
        print(f"  👉 {RED}Tekan [Ctrl+C]{RESET} atau ketik 'q' lalu Enter untuk membatalkan.")
        print(f"{YELLOW}==============================================================================={RESET}")

        if not interactive:
            return False, fleet_msg, profiles

        try:
            user_input = input("\n[Tekan ENTER untuk coba lagi / ketik 'q' untuk keluar]: ")
            if user_input.strip().lower() in ("q", "quit", "exit", "batal", "cancel"):
                print(f"\n{RED}🛑 Eksekusi dibatalkan oleh pengguna.{RESET}")
                return False, "Dibatalkan oleh pengguna", []
        except (KeyboardInterrupt, EOFError):
            print(f"\n{RED}🛑 Eksekusi dibatalkan oleh pengguna.{RESET}")
            return False, "Dibatalkan oleh pengguna", []

        print(f"{CYAN}🔍 Memeriksa ulang status koneksi ekstensi Chrome...{RESET}")
        time.sleep(1.0)


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
    print(f"Log Diagnostik: {CYAN}{prod_logger.log_file}{RESET}")
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
                    msg = entry.get("message", "")
                    if msg:
                        lvl = entry.get("level", "info")
                        profile = entry.get("profile") or "FLEET"
                        meta = entry.get("meta")
                        diagnostic = entry.get("diagnostic")

                        # Determine component category
                        comp = "FLOW:EXEC"
                        if "storyboard" in msg.lower():
                            comp = "STORYBOARD"
                        elif "seed" in msg.lower() or "character" in msg.lower():
                            comp = "CHARACTER"
                        elif "unduh" in msg.lower() or "download" in msg.lower():
                            comp = "DOWNLOAD"
                        elif "stitch" in msg.lower() or "gabung" in msg.lower():
                            comp = "STITCHER"
                        elif "retry" in msg.lower() or "coba lagi" in msg.lower():
                            comp = "AUTO_RETRY"

                        prod_logger.log(lvl, comp, msg, meta=meta, diagnostic=diagnostic)

                        # Render diagnostic card if diagnostic detected or provided
                        diag_info = diagnostic or diagnose_log_message(msg, lvl)
                        if diag_info and isinstance(diag_info, dict) and "classification" in diag_info:
                            prod_logger.log_diagnostic_card(
                                classification=diag_info.get("classification", "UNKNOWN"),
                                root_cause=diag_info.get("root_cause", ""),
                                evidence=diag_info.get("evidence", ""),
                                action_taken=diag_info.get("action_taken", ""),
                                technical_advice=diag_info.get("technical_advice", ""),
                            )
                seen_log_count = len(logs)

            job_status = job.get("status", "processing")
            if job_status != last_status:
                last_status = job_status

            if job_status == "completed":
                prod_logger.log("SUCCESS", "JOB", f"Job {job_id} selesai dengan sukses!")
                print(f"\n{GREEN}{BOLD}✔ JOB SELESAI DENGAN SUKSES!{RESET}")
                return True, job
            elif job_status in ("failed", "cancelled"):
                prod_logger.log("ERROR", "JOB", f"Job {job_id} berakhir dengan status: {job_status.upper()}")
                print(f"\n{RED}{BOLD}✖ JOB BERAKHIR DENGAN STATUS: {job_status.upper()}{RESET}")
                return False, job

        time.sleep(poll_interval)

    prod_logger.log("ERROR", "JOB", f"Timeout pengujian ({max_timeout}s) tercapai untuk job {job_id}.")
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
    prod_logger.log("INFO", "TEST_RUNNER", f"Memulai Automated E2E Scene Test Runner di {base_url}")

    # 1. Ensure Backend Server is online
    server_process = None
    if not check_server_health(base_url):
        if args.no_auto_start:
            prod_logger.log("ERROR", "SERVER", f"Server di {base_url} tidak aktif. Jalankan server terlebih dahulu.")
            print(f"{RED}[ERROR]{RESET} Server di {base_url} tidak aktif. Jalankan server terlebih dahulu.")
            return 1
        server_process = ensure_server_running(base_url, port=args.port)
        if not check_server_health(base_url):
            return 1
    else:
        prod_logger.log("SUCCESS", "SERVER", f"Terhubung ke Backend Sinematica di {base_url}.")
        print(f"{GREEN}[SYS]{RESET} Terhubung ke Backend Sinematica di {base_url}.")

    # 2. Check Chrome Fleet connection
    fleet_ready, fleet_msg, profiles = wait_for_fleet_interactive(base_url, interactive=args.interactive)
    prod_logger.log("INFO" if fleet_ready else "WARN", "FLEET", fleet_msg, meta={"profiles": profiles})
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
            prod_logger.log("INFO", "SCENE_MASTER", f"Mengambil storyboard Scene Master terbaru: '{title}' ({target_job_id})")
            print(f"{GREEN}[SCENE MASTER]{RESET} Mengambil storyboard Scene Master terbaru: {BOLD}'{title}'{RESET} ({target_job_id})")

    if not target_job_id:
        prod_logger.log("ERROR", "SCENE_MASTER", "Tidak ditemukan storyboard/job yang tersimpan di Scene Master (data/jobs_history.json).")
        print(f"{RED}[ERROR]{RESET} Tidak ditemukan storyboard/job yang tersimpan di Scene Master (data/jobs_history.json).")
        return 1

    # 4. Trigger Resume Execution
    limit = args.limit if (args.limit and args.limit > 0) else None
    scene_start = args.scene if args.scene else None
    scene_end = args.scene if args.scene else None

    prod_logger.log("INFO", "EXEC_TRIGGER", f"Memulai eksekusi otomatis (Limit: {limit or 'Semua'}, Scene: {args.scene or 'Otomatis'})...")
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
        prod_logger.log("ERROR", "EXEC_TRIGGER", f"Gagal memicu resume job: {ex}")
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
        prod_logger.log("WARN", "USER", "Pengujian dihentikan pengguna.")
        print(f"\n{YELLOW}[USER]{RESET} Pengujian dihentikan pengguna.")
        cancel_running_job(base_url, target_job_id)
        return 130

    # 6. Report Summary
    if final_job:
        print_summary_report(final_job)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
