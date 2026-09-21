# Sinematica AI Studio — Video Generation & End-to-End Workflow Architecture

## Purpose

Document the technical workflows, execution lifecycle, load-balancing mechanisms, and end-to-end pipeline of Sinematica AI Studio, specifically detailing the per-scene video generation loop and full studio lifecycle.

---

## Diagram 1: Per-Scene Video Generation & Multi-Scene Fleet Lifecycle

This diagram illustrates the lifecycle from when a scene is scheduled, allocated to an available Chrome profile instance, uploaded, executed via Google Flow (Native API or DOM UI Fallback), polled to completion, streamed chunk-by-chunk over WebSockets, and validated into local storage.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               SINEMATICA BACKEND (Python FastAPI) : JOBS EXECUTOR                                │
└────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                                         │
                                    [1. Start Job: Loop Per Scene]
                                                         │
                                                         ▼
                                   ┌───────────────────────────────────────────┐
                                   │  Pemeriksaan Artifact Storyboard Lokal    │
                                   │  (Pastikan scene_XX_storyboard.png siap)  │
                                   └─────────────────────┬─────────────────────┘
                                                         │
                                    [2. Alokasi Profil Chrome Fleet]
                                                         │
                                                         ▼
                                   ┌───────────────────────────────────────────┐
                                   │  BridgeManager: Pilih Instance Fleet      │
                                   │  (Round-Robin / Status Ready & Idle)      │
                                   │  Contoh: Profile A (Project ID: 0183e...) │
                                   └─────────────────────┬─────────────────────┘
                                                         │
                                    [3. Kirim Perintah Upload Gambar via WS]
                                                         │
                                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           CHROME EXTENSION RUNTIME (Profil Terpilih / background.js)                             │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                                  │
│  [3.1] Upload Gambar Storyboard:                                                                                 │
│        • flow-api-client.js membentuk URL /v1/flow/uploadImage?key=API_KEY                                       │
│        • Mengirim base64 payload dengan clientContext: { projectId: "0183e..." }                                 │
│        • Google Flow merespons dengan mediaId (contoh: "media-uuid-999")                                         │
│        • flow-logger.js mencatat: [API:PROXY] Storyboard Upload Success                                          │
│                                                                                                                  │
│  [3.2] Penyelesaian Keamanan (reCAPTCHA Enterprise):                                                             │
│        • flow-recaptcha.js memicu window.grecaptcha.enterprise.execute() di tab Flow                             │
│        • Mendapatkan token captcha dengan action "VIDEO_GENERATION"                                              │
│        • flow-logger.js mencatat: [CAPTCHA] Solved token successfully                                            │
│                                                                                                                  │
│  [3.3] Pengiriman Request I2V (Image-to-Video):                                                                  │
│        • Menyusun payload startImage: { mediaId: "media-uuid-999" }                                              │
│        • Injeksi Bearer Token OAuth Google (ya29...) + clientContext Project ID                                  │
│        • Endpoint: /v1/video:batchAsyncGenerateVideoStartImage                                                   │
│                                                                                                                  │
│        ┌───────────────────────── Jalur Percabangan Eksekusi ──────────────────────────┐                         │
│        │                                                                               │                         │
│        ▼ (HTTP 200 OK)                                                                 ▼ (HTTP 401 / 503 Gagal)  │
│  ┌───────────────────────────┐                                           ┌───────────────────────────┐           │
│  │    JALUR NATIVE API       │                                           │     JALUR DOM FALLBACK    │           │
│  │  Menerima response JSON   │                                           │  • flow-composer-editor   │           │
│  │  berisi mediaGenerationId │                                           │    ketik prompt & event   │           │
│  │  untuk di-polling         │                                           │  • flow-composer-config   │           │
│  │                           │                                           │    pilih 9:16/16:9 & dur  │           │
│  │                           │                                           │  • flow-composer-ingred   │           │
│  │                           │                                           │    pilih tile storyboard  │           │
│  │                           │                                           │  • Klik "Start generation"│           │
│  └─────────────┬─────────────┘                                           └─────────────┬─────────────┘           │
│                │                                                                       │                         │
│                └───────────────────────────────────┬───────────────────────────────────┘                         │
│                                                    │                                                             │
└────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┘
                                                     │
                                [4. Polling Status Render Video]
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             SIKLUS POLLING & PROGRESS (engine/omniflash/i2v.py)                                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                                  │
│   Loop Polling (Interval 8 detik, Timeout 420 detik):                                                            │
│   ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│   │ 1. Kirim request: /v1/video:batchCheckAsyncVideoGenerationStatus                                          │  │
│   │ 2. Hitung progres kalkulasi: 0% → 30% → 65% → 95%                                                         │  │
│   │ 3. Broadcast status live ke Dashboard WebSocket (/ws/status)                                              │  │
│   │ 4. Periksa kondisi status:                                                                                │  │
│   │    • IN_PROGRESS  → Lanjutkan loop sleep(8)                                                               │  │
│   │    • FAILED       → Tangkap error message, alihkan ke profil Chrome cadangan                             │  │
│   │    • SUCCEEDED    → Dapatkan signed CDN URL video (.mp4)                                                  │  │
│   └───────────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                                  │
└────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                     │
                             [5. Streaming Unduhan File Video MP4]
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               TRANSMISI & PENYIMPANAN FILE VIDEO LOKAL                                           │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                                  │
│  1. Extension Service Worker melakukan stream fetch() terhadap Signed CDN URL Google Flow.                       │
│  2. Extension mengirimkan payload download_start (total ukuran chunk) ke backend.                                │
│  3. Data video dialirkan per-potongan 384 KB (download_chunk) via WebSocket secara efisien.                      │
│  4. Backend (media_download.py) menyusun ulang chunk binary menjadi file utuh.                                  │
│  5. File disimpan ke storage/jobs/<job_id>/scene_01.mp4.                                                          │
│  6. Validasi integritas (Post-Production QC): verifikasi durasi file dan codec video.                            │
│  7. Adegan selesai → Executor melanjutkan ke Scene 02 pada profil fleet berikutnya.                             │
│                                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Diagram 2: End-to-End Sinematica AI Studio System Architecture

This diagram maps the full journey from initial user inputs, character casting references, multi-provider AI text generation, storyboard image artifacts, parallel fleet execution across multiple Chrome instances, to final post-production audio-video concatenation via FFmpeg.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   TAHAP 1: INPUT PENGGUNA & CASTING KARAKTER                                     │
└────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                                         │
                ┌────────────────────────────────────────┴────────────────────────────────────────┐
                ▼                                                                                 ▼
     [Karakter & Aktor (Casting)]                                                     [Ide Cerita & Skenario]
  • Unggah 1-4 Foto Referensi                                                       • Topik, Genre, Jumlah Adegan
  • Disimpan di storage/actors/                                                     • Target Audience & Rasio Aspek
  • Validasi format JPEG/PNG/WebP                                                   • Bahasa Naskah & Pacing
                │                                                                                 │
                └────────────────────────────────────────┬────────────────────────────────────────┘
                                                         │
                                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           TAHAP 2: MULTI-PROVIDER AI STORYBOARD & PROMPT GENERATION                              │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                                  │
│   Sistem Text Provider Router (backend/text_generation.py) mengeksekusi pembuatan storyboard secara otomatis:    │
│                                                                                                                  │
│   ┌────────────────────────────────────── URUTAN FAILOVER OTOMATIS ──────────────────────────────────────────┐   │
│   │                                                                                                          │   │
│   │   [1. Gemini 3.6 Flash] ──(Quota 429)──► [2. OpenAI GPT-4.1] ──(Quota 429)──► [3. DeepSeek Chat]         │   │
│   │                                                                                    │                     │   │
│   │   [5. Local Web2API]    ◄─────────────── [4. Groq / 9Router] ◄─────────────────────┘                     │   │
│   │                                                                                                          │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                        │                                                         │
│                                                        ▼                                                         │
│   Hasil Storyboard Teks:                                                                                         │
│   • Breakdown scene demi scene (Narasi, Dialog, Visual Prompt, Audio Direction)                                  │
│   • Continuity Check: Menjaga konsistensi kostum, lighting, dan interaksi karakter.                              │
│                                                                                                                  │
└────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                                         │
                                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             TAHAP 3: PEMBUATAN ARTIFACT GAMBAR STORYBOARD LOKAL                                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                                  │
│   1. Generate Anchor Character Sheet untuk setiap karakter menggunakan foto referensi casting.                   │
│   2. Generate Gambar Storyboard per Scene menggunakan Character Sheet sebagai panduan visual komposisi.          │
│   3. Simpan seluruh gambar storyboard di storage/jobs/<job_id>/scene_XX_storyboard.png.                          │
│                                                                                                                  │
└────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                                         │
                                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               TAHAP 4: ORKESTRASI & LOAD BALANCING FLEET PROFIL CHROME                           │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                                  │
│   Jobs Executor mendistribusikan render adegan ke armada Chrome Fleet secara paralel:                            │
│                                                                                                                  │
│          ┌─────────────────────────────────── BridgeManager ───────────────────────────────────┐                 │
│          │                                                                                     │                 │
│          ▼ (Render Scene 1 & 4)                 ▼ (Render Scene 2 & 5)                         ▼ (Render Scene 3)│
│   ┌───────────────────────┐             ┌───────────────────────┐                    ┌───────────────────────┐   │
│   │   Chrome Profile 1    │             │   Chrome Profile 2    │                    │   Chrome Profile 3    │   │
│   │ • Tab Flow Project A  │             │ • Tab Flow Project B  │                    │ • Tab Flow Project C  │   │
│   │ • Upload SB 1 ke ProjA│             │ • Upload SB 2 ke ProjB│                    │ • Upload SB 3 ke ProjC│   │
│   │ • Submit I2V Proj A   │             │ • Submit I2V Proj B   │                    │ • Submit I2V Proj C   │   │
│   │ • Unduh Scene 01.mp4  │             │ • Unduh Scene 02.mp4  │                    │ • Unduh Scene 03.mp4  │   │
│   └───────────────────────┘             └───────────────────────┘                    └───────────────────────┘   │
│                                                                                                                  │
│   Live Structured Logging:                                                                                       │
│   Seluruh event profil ([AUTH], [CAPTCHA], [DOM], [API], [DOWNLOAD]) dialirkan via WebSocket ke:                 │
│   • Extension Side Panel Live Terminal                                                                           │
│   • Dashboard Web Execution Terminal                                                                            │
│   • Berkas data/logs/flow_fleet_YYYY-MM-DD.log                                                                   │
│                                                                                                                  │
└────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                                         │
                                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            TAHAP 5: POST-PRODUCTION, STITCHING & PENYAJIAN FILM                                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                                  │
│   1. Post-Production QC (backend/postproduction_qc.py):                                                          │
│      • Memeriksa kelengkapan seluruh klip scene_01.mp4 hingga scene_XX.mp4.                                      │
│      • Validasi header MP4, frame rate, dan audio channel.                                                       │
│                                                                                                                  │
│   2. Cinematic Film Stitcher (backend/film_stitcher.py):                                                         │
│      • Menggabungkan (concatenate) semua potongan video adegan menggunakan FFmpeg.                               │
│      • Menghasilkan satu file video utuh: storage/jobs/<job_id>/cinematic_film.mp4.                              │
│      • Otomatis membuat thumbnail cover dari scene pembuka.                                                      │
│                                                                                                                  │
│   3. Video Gallery & Studio Viewer:                                                                              │
│      • Menampilkan film di tab Video Gallery pada web dashboard (http://127.0.0.1:8888).                         │
│      • Fitur pemutaran klip per-adegan, download film utuh, dan ekspor metadata YouTube/SEO.                    │
│                                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
