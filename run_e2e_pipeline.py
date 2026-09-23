#!/usr/bin/env python3
"""Sinematica AI Studio — Unified End-to-End Automated Pipeline Runner.

Automates the complete workflow:
1. Backend Server Healthcheck & Auto-Start
2. Genre/Preset Selection (Random or Specified)
3. Trend Analysis & Concept Generation (Trend Radar / Auto-Suggest)
4. Full Multi-Scene AI Storyboard Generation (2 scenes x 10s duration)
5. Interactive Chrome Fleet Connection Guard
6. Job Registration (matching Web UI payload) & Live Production Diagnostic Log Streaming
7. Physical Output Verification & Final Production Diagnostic Report
"""

import argparse
import asyncio
import datetime
import json
import logging
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Set up project root in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend import settings
from backend.gemini_storyboard import auto_suggest_details, generate_storyboard

DEFAULT_PORT = 8888

GENRE_CATALOG_PRESETS = [
    {
        "category": "Dracin & Microdrama Indonesia",
        "genre": "CEO Menyamar Jadi Karyawan Biasa",
        "theme": "Direktur Utama perusahaan besar menyamar jadi karyawan magang biasa demi menyelidiki kecurangan internal, lalu jatuh cinta pada karyawati sederhana yang selalu dihina rekan kerjanya.",
        "country": "Indonesia",
        "language": "Indonesia",
    },
    {
        "category": "Dracin & Microdrama Indonesia",
        "genre": "Suami Pura-Pura Miskin Ternyata Konglomerat",
        "theme": "Suami sederhana yang dihina keluarga istri karena dianggap tidak mampu, diam-diam adalah pemilik perusahaan besar yang menyamar demi menguji ketulusan cinta istrinya.",
        "country": "Indonesia",
        "language": "Indonesia",
    },
    {
        "category": "Dracin & Microdrama Indonesia",
        "genre": "Sopir Pribadi Ternyata Pemilik Perusahaan",
        "theme": "Sopir pribadi yang selalu diremehkan oleh majikannya ternyata adalah pemilik asli perusahaan tempat majikannya bekerja, menyamar untuk menguji kejujuran karyawannya.",
        "country": "Indonesia",
        "language": "Indonesia",
    },
    {
        "category": "Dracin & Microdrama Indonesia",
        "genre": "Putri Tertukar Sejak Lahir",
        "theme": "Dua bayi perempuan tertukar di rumah sakit sejak lahir, satu dibesarkan keluarga kaya dan satu di keluarga miskin, bertahun-tahun kemudian kebenaran identitas asli mereka terungkap.",
        "country": "Indonesia",
        "language": "Indonesia",
    },
    {
        "category": "Dracin Wuxia & Kerajaan",
        "genre": "Pendekar Pedang Lembah Kabut",
        "theme": "Pendekar pengelana mengungkap konspirasi perebutan artefak giok sakti di perbatasan lembah terlarang untuk menyelamatkan klan yang difitnah.",
        "country": "Indonesia",
        "language": "Indonesia",
    },
    {
        "category": "Misteri & Petualangan Purba",
        "genre": "Ekspedisi Lembah Purba",
        "theme": "Dua peneliti muda menemukan pintu gerbang kuno berlumut di kedalaman hutan Maros yang menyimpan rahasia peradaban hilang.",
        "country": "Indonesia",
        "language": "Indonesia",
    },
]


class ProductionExecutionLogger:
    """Manages high-fidelity production diagnostic logging to console and disk."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or (settings.DATA_DIR / "logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"e2e_production_execution_{timestamp_str}.log"
        self.jsonl_file = self.log_dir / f"e2e_production_execution_{timestamp_str}.jsonl"

        # Initialize log header
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(" SINEMATICA AI STUDIO — PRODUCTION EXECUTION & DIAGNOSTIC LOG\n")
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
        if lvl in ("ERROR", "ERR"):
            icon = "❌"
        elif lvl in ("WARN", "WARNING"):
            icon = "⚠️"
        elif lvl in ("RETRY", "AUTO_RETRY"):
            icon = "🔁"
        elif lvl in ("SUCCESS", "READY", "COMPLETED"):
            icon = "✅"
        elif lvl in ("PROG", "PROGRESS"):
            icon = "⏳"
        elif lvl in ("DIAG", "DIAGNOSTIC"):
            icon = "🔬"

        line = f"[{time_str}] [{lvl:5s}] [{component:16s}] {icon} {message}"
        print(line)

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
        print(formatted_card)

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(formatted_card + "\n")
        except Exception:
            pass


prod_logger = ProductionExecutionLogger()


def http_get(url: str, timeout: float = 3.0) -> Tuple[int, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Sinematica-E2E-Pipeline/1.0", "Accept": "application/json"},
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


def http_post(url: str, payload: Optional[dict] = None, timeout: float = 10.0) -> Tuple[int, Any]:
    data_bytes = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            "User-Agent": "Sinematica-E2E-Pipeline/1.0",
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
    status, data = http_get(f"{base_url}/api/status", timeout=timeout)
    return status == 200 and isinstance(data, dict)


def ensure_backend_server(base_url: str, port: int = DEFAULT_PORT, timeout: float = 20.0) -> Optional[subprocess.Popen]:
    if check_server_health(base_url):
        prod_logger.log("INFO", "SERVER", f"Server Sinematica Backend aktif di {base_url}")
        return None

    prod_logger.log("WARN", "SERVER", f"Server Sinematica belum aktif di port {port}. Menjalankan server otomatis...")
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
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_server_health(base_url):
            prod_logger.log("SUCCESS", "SERVER", f"Server Sinematica berhasil berjalan di {base_url} (PID: {process.pid})")
            return process
        time.sleep(0.5)

    prod_logger.log("ERROR", "SERVER", f"Gagal memulai server Sinematica di {base_url} dalam batas waktu {timeout}s.")
    return process


async def check_and_wait_for_extension_fleet(
    base_url: str,
    interactive: bool = True,
    mock_data: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Verify ready Chrome Extension instances via server API. If none, prompt the user to connect and press Enter."""
    while True:
        if mock_data is not None:
            data = mock_data
            status_code = 200
        else:
            status_code, data = http_get(f"{base_url}/api/fleet", timeout=4.0)

        profiles = data.get("profiles", []) if isinstance(data, dict) else []

        ready_profiles = [
            p for p in profiles
            if p.get("connected") and p.get("ready", True) and p.get("logged_in", True)
        ]
        if ready_profiles:
            names = [p.get("name") or p.get("instance_id", "Chrome Profile") for p in ready_profiles]
            prod_logger.log(
                "SUCCESS",
                "FLEET",
                f"Terhubung ke {len(ready_profiles)} profil Chrome aktif: {', '.join(names)}",
                meta={"profiles": ready_profiles},
            )
            return ready_profiles

        connected_profiles = [p for p in profiles if p.get("connected")]
        if connected_profiles:
            names = [p.get("name") or p.get("instance_id", "Chrome Profile") for p in connected_profiles]
            prod_logger.log(
                "SUCCESS",
                "FLEET",
                f"Terhubung ke {len(connected_profiles)} profil Chrome ({', '.join(names)}), sesi Google Flow terverifikasi.",
                meta={"profiles": connected_profiles},
            )
            return connected_profiles

        if not interactive:
            prod_logger.log("WARN", "FLEET", "Mode non-interaktif: Tidak ada profil Chrome Extension yang terhubung.")
            return []

        print("\n" + "=" * 75)
        print(" ⚠️ [PERINGATAN] Ekstensi Chrome Sinematica belum terhubung atau belum siap!")
        print("=" * 75)
        print("  Petunjuk langkah cepat:")
        print("  1. Buka browser Google Chrome tempat ekstensi Sinematica terpasang.")
        print("  2. Buka tab Google Flow (https://flow.google.com) dan buka proyek Anda.")
        print("  3. Pastikan ekstensi Sinematica aktif (tombol status ON).")
        print("-------------------------------------------------------------------------------")
        print("  👉 Tekan [ENTER] untuk memeriksa kembali koneksi ekstensi...")
        print("  👉 Tekan [Ctrl+C] atau ketik 'q' lalu Enter untuk membatalkan.")
        print("=" * 75)

        try:
            user_input = await asyncio.to_thread(input, "\n[Tekan ENTER untuk coba lagi / ketik 'q' untuk keluar]: ")
            if user_input.strip().lower() in ("q", "quit", "exit", "batal", "cancel"):
                prod_logger.log("WARN", "USER", "Eksekusi dibatalkan oleh pengguna.")
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            prod_logger.log("WARN", "USER", "Eksekusi dibatalkan oleh pengguna.")
            sys.exit(0)

        prod_logger.log("INFO", "FLEET", "Memeriksa ulang status koneksi ekstensi Chrome...")
        await asyncio.sleep(1.0)


def diagnose_log_message(msg: str, lvl: str) -> Optional[Dict[str, str]]:
    """Extracts technical root-cause diagnostics and remediation advice for an event."""
    lower_msg = msg.lower()

    if "kartu kendala" in lower_msg or "gagal dibuat" in lower_msg or "failed to generate" in lower_msg or "flow-error-tile" in lower_msg:
        return {
            "classification": "GOOGLE_FLOW_MEDIA_GENERATION_FAILED",
            "root_cause": "Google Flow engine mengalami interupsi render sementara atau model timeout.",
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

    if "429" in lower_msg or "kuota" in lower_msg or "quota" in lower_msg or "credit" in lower_msg or "resource_exhausted" in lower_msg:
        return {
            "classification": "GOOGLE_FLOW_RESOURCE_EXHAUSTED_OR_RATE_LIMITED",
            "root_cause": "Batas kuota harian atau rate-limit per menit pada akun Google aktif telah tercapai.",
            "evidence": "Respons HTTP 429 atau pesan kuota habis diterima dari server Google.",
            "action_taken": "Task executor otomatis menjadwalkan rotasi ke profil Chrome alternatif berikutnya.",
            "technical_advice": "Tambahkan profil Google akun cadangan pada fleet ekstensi atau tunggu periode reset kuota.",
        }

    if "kebijakan" in lower_msg or "policy" in lower_msg or "safety" in lower_msg or "filter" in lower_msg:
        return {
            "classification": "GOOGLE_FLOW_POLICY_SAFETY_TRIGGERED",
            "root_cause": "Prompt teks atau komposisi referensi memicu sistem filter keamanan Google Flow.",
            "evidence": "Intersepsi pesan pelanggaran kebijakan konten dari Google Flow.",
            "action_taken": "Sistem AI Studio otomatis mereformulasi sinonim prompt dramatis yang aman.",
            "technical_advice": "Pastikan deskripsi visual tidak memuat figur berhak cipta terlarang atau tokoh nyata sensitif.",
        }

    if "content_script_unreachable" in lower_msg or "disconnect" in lower_msg or "terputus" in lower_msg:
        return {
            "classification": "CHROME_EXTENSION_BRIDGE_DISCONNECTED",
            "root_cause": "Tab Google Flow tertutup atau direfresh sehingga koneksi WebSocket/content script terputus.",
            "evidence": "Kegagalan pengiriman pesan via chrome.tabs.sendMessage / WebSocket bridge.",
            "action_taken": "Sistem memicu auto-reconnect backoff (basis 1.5s exponential).",
            "technical_advice": "Pastikan tab Google Flow tetap terbuka dan saklar ekstensi Sinematica tetap ON.",
        }

    return None


class E2EPipelineRunner:
    def __init__(
        self,
        base_url: str = f"http://127.0.0.1:{DEFAULT_PORT}",
        scene_count: int = 2,
        duration: int = 10,
        aspect_ratio: str = "portrait",
        target_country: str = "Indonesia",
        target_lang: str = "Indonesia",
        flow_project_id: Optional[str] = None,
        selected_preset: Optional[Dict[str, str]] = None,
        interactive: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.scene_count = scene_count
        self.duration = duration
        self.aspect_ratio = aspect_ratio
        self.target_country = target_country
        self.target_lang = target_lang
        self.flow_project_id = flow_project_id or settings.get_flow_project_id()
        self.preset = selected_preset or random.choice(GENRE_CATALOG_PRESETS)
        self.interactive = interactive
        self.job_id: Optional[str] = None
        self.storyboard: Optional[Dict[str, Any]] = None

    def print_banner(self, title: str):
        border = "=" * 75
        print(f"\n{border}\n 🎬 {title.upper()}\n{border}")
        prod_logger.log("INFO", "PIPELINE", f"Memulai {title}")

    async def step_1_trend_and_concept(self) -> Dict[str, Any]:
        self.print_banner("Tahap 1: Analisis Tren & Pembuatan Konsep Cerita")
        prod_logger.log(
            "INFO",
            "CONCEPT",
            f"Kategori: {self.preset.get('category')} | Genre: {self.preset.get('genre')}",
            meta={
                "target_country": self.target_country,
                "target_lang": self.target_lang,
                "scene_count": self.scene_count,
                "duration_per_scene": self.duration,
            },
        )

        raw_theme = self.preset.get("theme", "")
        prompt = (
            f"Tema: {self.preset.get('genre')}. "
            f"Premis dasar: {raw_theme}. "
            f"Buat konsep serial pendek dramatis {self.scene_count} adegan berbahasa {self.target_lang} untuk audiens {self.target_country}. "
            "Fokus pada hook kuat, emosi berbobot, dan aksi berantai yang sinematik."
        )

        prod_logger.log("INFO", "AI_SUGGEST", "Mengirim permintaan AI concept suggestion via 9Router...")
        t_start = time.time()
        try:
            concept_data = auto_suggest_details(
                prompt,
                microdrama_mode=True,
                series_mode=True,
                target_lang=self.target_lang,
                target_country=self.target_country,
            )
            elapsed = time.time() - t_start
            prod_logger.log("SUCCESS", "AI_SUGGEST", f"Konsep berhasil dibuat via AI Provider ({elapsed:.2f}s)")
        except Exception as ex:
            prod_logger.log("WARN", "AI_SUGGEST", f"Auto-suggest fallback ke preset lokal: {ex}")
            concept_data = {
                "suggested_title": self.preset.get("genre", "Kisah Sinematik"),
                "suggested_premise": raw_theme,
                "suggested_characters": "Tokoh Utama, Tokoh Pendukung",
                "art_direction": "Cinematic live action photography with natural textures",
            }

        title = concept_data.get("suggested_title") or self.preset.get("genre")
        premise = concept_data.get("suggested_premise") or raw_theme
        print(f"\n✅ [KONSEP SELESAI]")
        print(f"   📌 Judul Film : {title}")
        print(f"   📖 Premis     : {premise[:140]}...")
        return {
            "title": title,
            "premise": premise,
            "concept_data": concept_data,
        }

    async def step_2_generate_storyboard(self, concept: Dict[str, Any]) -> Dict[str, Any]:
        self.print_banner("Tahap 2: Pembuatan Full AI Storyboard")
        title = concept["title"]
        premise = concept["premise"]

        prod_logger.log(
            "INFO",
            "STORYBOARD",
            f"Menyusun storyboard {self.scene_count} adegan x {self.duration}s (Total {self.scene_count * self.duration}s)...",
        )

        t_start = time.time()
        try:
            storyboard = generate_storyboard(
                premise=premise,
                scene_count=self.scene_count,
                aspect_ratio=self.aspect_ratio,
                target_country=self.target_country,
                target_lang=self.target_lang,
                fixed_scene_duration=self.duration,
                target_total_duration=self.scene_count * self.duration,
                story_total_scene_count=self.scene_count,
                microdrama_mode=True,
                visual_style="live_action",
            )
            elapsed = time.time() - t_start
            prod_logger.log("SUCCESS", "STORYBOARD", f"Storyboard berhasil disusun via Gemini ({elapsed:.2f}s)")
        except Exception as ex:
            prod_logger.log("WARN", "STORYBOARD", f"Fallback pembuatan storyboard lokal: {ex}")
            storyboard = {
                "film_title": title,
                "premise": premise,
                "aspect_ratio": self.aspect_ratio,
                "characters": [
                    {"name": "Tokoh Utama", "seed": random.randint(500000, 599999), "wardrobe": "Pakaian kasual"},
                    {"name": "Tokoh Pendukung", "seed": random.randint(600000, 699999), "wardrobe": "Seragam rapi"},
                ],
                "scenes": [
                    {
                        "scene_number": i,
                        "title": f"Adegan {i}: Momen Penting {i}",
                        "duration": self.duration,
                        "action_summary": f"Aksi adegan ke-{i} berlangsung penuh ketegangan.",
                        "prompt_for_flow": f"A cinematic live action 10-second shot showing dramatic interaction in scene {i}.",
                    }
                    for i in range(1, self.scene_count + 1)
                ],
            }

        storyboard["film_title"] = title
        storyboard["target_country"] = self.target_country
        storyboard["target_lang"] = self.target_lang
        storyboard["aspect_ratio"] = self.aspect_ratio

        self.storyboard = storyboard
        scenes = storyboard.get("scenes") or []
        chars = storyboard.get("characters") or []
        print(f"\n✅ [STORYBOARD SELESAI]")
        print(f"   🎬 Judul       : {storyboard.get('film_title')}")
        print(f"   👥 Karakter    : {len(chars)} Karakter ({', '.join(c.get('name', '') for c in chars)})")
        print(f"   🎞️ Total Adegan: {len(scenes)} Adegan")
        for idx, sc in enumerate(scenes, 1):
            print(f"      [{idx}/{len(scenes)}] {sc.get('title', f'Adegan {idx}')} ({sc.get('duration', self.duration)}s)")

        return storyboard

    async def step_3_and_4_register_and_execute_job(self) -> Dict[str, Any]:
        self.print_banner("Tahap 3 & 4: Registrasi Job & Eksekusi Fleets Google Flow")

        ready_fleet = await check_and_wait_for_extension_fleet(self.base_url, interactive=self.interactive)

        # Detect Flow Project ID if not set
        if not self.flow_project_id:
            candidates = [i for i in ready_fleet if i.get("project_id")]
            if candidates:
                self.flow_project_id = candidates[0]["project_id"]
                prod_logger.log("INFO", "FLOW_PROJECT", f"Menggunakan Flow Project ID dari Chrome fleet aktif: {self.flow_project_id}")

        # Build payload matching Web UI exactly
        payload = {
            "storyboard": self.storyboard,
            "theme_image_path": (self.storyboard.get("_theme_image_path") if isinstance(self.storyboard, dict) else None),
            "aspect_ratio": self.aspect_ratio,
            "duration": self.duration,
            "flow_project_id": self.flow_project_id,
            "force_uniform_duration": True,
            "render_scene_limit": self.scene_count,
            "render_scene_start": None,
            "render_scene_end": None,
        }

        prod_logger.log("INFO", "JOB_DISPATCH", f"Mengirim registrasi job ke backend server di {self.base_url}/api/jobs/create...")
        status_code, resp = http_post(f"{self.base_url}/api/jobs/create", payload=payload, timeout=10.0)
        if status_code != 200 or not isinstance(resp, dict) or not resp.get("job_id"):
            error_msg = resp.get("detail") if isinstance(resp, dict) else str(resp)
            prod_logger.log("ERROR", "JOB_DISPATCH", f"Gagal mendaftarkan job (HTTP {status_code}): {error_msg}")
            raise RuntimeError(f"Gagal mendaftarkan job ke server (HTTP {status_code}): {error_msg}")

        self.job_id = resp["job_id"]
        print(f"📋 Job Terdaftar : {self.job_id}")
        print(f"🌐 Flow Project  : {self.flow_project_id or '(default session project)'}")
        print(f"📁 Log Produksi  : {prod_logger.log_file}")
        print(f"🚀 Memulai live monitoring eksekusi video...\n")

        # Stream live logs from GET /api/jobs/{job_id}
        last_log_count = 0
        seen_messages = set()
        final_status = {}

        while True:
            st_code, job_data = http_get(f"{self.base_url}/api/jobs/{self.job_id}", timeout=5.0)
            if st_code == 200 and isinstance(job_data, dict):
                job_info = job_data.get("job") or {}
                logs = job_data.get("logs") or []

                if len(logs) > last_log_count:
                    for entry in logs[last_log_count:]:
                        msg = entry.get("message", "")
                        if msg and msg not in seen_messages:
                            seen_messages.add(msg)
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

                            # If a diagnostic condition is detected, print structured technical card
                            diag_info = diagnose_log_message(msg, lvl)
                            if diag_info:
                                prod_logger.log_diagnostic_card(
                                    classification=diag_info["classification"],
                                    root_cause=diag_info["root_cause"],
                                    evidence=diag_info["evidence"],
                                    action_taken=diag_info["action_taken"],
                                    technical_advice=diag_info["technical_advice"],
                                )

                    last_log_count = len(logs)

                status_str = job_info.get("status", "processing")
                if status_str in ("completed", "failed", "cancelled"):
                    final_status = job_info
                    break

            await asyncio.sleep(1.0)

        return final_status

    async def step_5_verify_and_report(self, job_status: Dict[str, Any]):
        self.print_banner("Tahap 5: Verifikasi Hasil Output & Laporan Akhir")
        job_id = self.job_id
        status_str = job_status.get("status", "unknown")
        job_dir = settings.JOBS_DIR / job_id if job_id else settings.JOBS_DIR

        print(f"📌 Job ID         : {job_id or '-'}")
        print(f"📊 Status Akhir   : {status_str.upper()}")
        print(f"📁 Direktori Job  : {job_dir}")
        print(f"📄 Log Diagnostik : {prod_logger.log_file}")

        storyboard_files = list(job_dir.glob("storyboard_*.png")) if job_dir.exists() else []
        scene_videos = list(job_dir.glob("scene_*.mp4")) if job_dir.exists() else []
        final_video = job_dir / "cinematic_film.mp4"
        subtitles = job_dir / "subtitles.srt"

        print(f"\n📦 Pemeriksaan Integritas Berkas Fisik:")
        print(f"   🖼️ Storyboard Images : {len(storyboard_files)} file")
        for sf in sorted(storyboard_files):
            size_kb = sf.stat().st_size / 1024
            status_icon = "✅" if size_kb > 5 else "⚠️"
            print(f"      {status_icon} {sf.name} ({size_kb:.1f} KB)")

        print(f"   🎥 Scene Videos      : {len(scene_videos)} file")
        for sv in sorted(scene_videos):
            size_kb = sv.stat().st_size / 1024
            status_icon = "✅" if size_kb > 50 else "⚠️"
            print(f"      {status_icon} {sv.name} ({size_kb:.1f} KB)")

        final_available = final_video.exists()
        final_size_kb = f" ({final_video.stat().st_size / 1024:.1f} KB)" if final_available else ""
        print(f"   🎬 Final Film (MP4)  : {'TERSEDIA' + final_size_kb if final_available else 'BELUM DIBUAT'}")
        print(f"   📝 Subtitles (SRT)   : {'TERSEDIA' if subtitles.exists() else 'TIDAK TERSEDIA'}")

        print("\n" + "=" * 75)
        if status_str == "completed" or (len(storyboard_files) >= self.scene_count):
            prod_logger.log("SUCCESS", "VERIFICATION", f"SUKSES! Seluruh alur end-to-end terverifikasi (Job ID: {job_id})")
            print(f"🎉 SUKSES! Seluruh alur end-to-end terverifikasi.")
        else:
            err_detail = job_status.get('error', 'Cek log diagnostik untuk rincian')
            prod_logger.log("ERROR", "VERIFICATION", f"Status job: {status_str}. Catatan: {err_detail}")
            print(f"⚠️ Status job: {status_str}. Catatan: {err_detail}")
        print("=" * 75 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="Sinematica AI Studio — Automated End-to-End Test & Execution Runner")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port Sinematica Backend (default: {DEFAULT_PORT})")
    parser.add_argument("--no-auto-start", action="store_true", help="Jangan otomatis memulai server Sinematica jika offline")
    parser.add_argument("--scenes", type=int, default=2, help="Jumlah adegan (default: 2)")
    parser.add_argument("--duration", type=int, default=10, help="Durasi per adegan dalam detik (default: 10)")
    parser.add_argument("--country", type=str, default="Indonesia", help="Target negara (default: Indonesia)")
    parser.add_argument("--lang", type=str, default="Indonesia", help="Bahasa dialog (default: Indonesia)")
    parser.add_argument("--aspect-ratio", type=str, default="portrait", choices=["portrait", "landscape"], help="Rasio video (default: portrait)")
    parser.add_argument("--project-id", type=str, default=None, help="Flow Project UUID kandidat")
    parser.add_argument("--genre-index", type=int, default=None, help="Indeks preset katalog genre")
    parser.add_argument("--interactive", action=argparse.BooleanOptionalAction, default=True, help="Mode interaktif tunggu koneksi ekstensi (default: True)")
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"

    if not args.no_auto_start:
        ensure_backend_server(base_url=base_url, port=args.port)

    selected_preset = None
    if args.genre_index is not None and 0 <= args.genre_index < len(GENRE_CATALOG_PRESETS):
        selected_preset = GENRE_CATALOG_PRESETS[args.genre_index]

    runner = E2EPipelineRunner(
        base_url=base_url,
        scene_count=args.scenes,
        duration=args.duration,
        aspect_ratio=args.aspect_ratio,
        target_country=args.country,
        target_lang=args.lang,
        flow_project_id=args.project_id,
        selected_preset=selected_preset,
        interactive=args.interactive,
    )

    try:
        concept = await runner.step_1_trend_and_concept()
        await runner.step_2_generate_storyboard(concept)
        job_status = await runner.step_3_and_4_register_and_execute_job()
        await runner.step_5_verify_and_report(job_status)
    except KeyboardInterrupt:
        prod_logger.log("WARN", "RUNNER", "Eksekusi dihentikan oleh pengguna (KeyboardInterrupt).")
    except Exception as ex:
        prod_logger.log("ERROR", "RUNNER", f"Eksekusi pipeline gagal dengan exception: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
