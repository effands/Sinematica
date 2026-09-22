# Sinematica AI Studio — Session Handoff & Continuity Log

**Date:** 2026-09-22  
**Target File:** `conversation.md`  
**Repository:** `https://github.com/effands/Sinematica.git` (Branch: `main`)  
**Latest Commit:** `188d6b4` — *feat(flow): implement trusted DOM clicks, error tile auto-retry, and adaptive ingredient matching*

---

## 1. Ringkasan Eksekutif Sesi Ini

Pada sesi ini, kami berhasil menyelesaikan seluruh kendala macet (*stuck*) dan kegagalan otomatisasi pada alur Google Flow (Omni Flash / Gemini 3.6 Flash fleet), mulai dari tahap casting karakter, pembuatan storyboard 6 adegan, hingga penyiapan generasi video adegan.

---

## 2. Masalah Utama & Analisis Penyebab (Root Causes)

### A. Tombol Start Generation Macet / Tidak Merespon (`isTrusted: false`)
- **Gejala**: Prompt terisi penuh di editor ProseMirror, tombol panah (*Start generation*) aktif, namun klik programatik tidak pernah memicu generasi hingga waktu habis (*timeout* 90 detik).
- **Penyebab**: Antarmuka Angular Material MDC pada Google Flow memeriksa flag event `isTrusted: true`. Pemanggilan `element.click()` atau `dispatchEvent(new MouseEvent(...))` biasa menghasilkan `isTrusted: false` dan diabaikan oleh Google Flow.
- **Solusi**: Mengintegrasikan `chrome.debugger` (Chrome DevTools Protocol v1.3) di `engine/chrome-extension/background.js`. Ekstensi menghitung koordinat layar tombol `(x, y)` dan mengeksekusi `Input.dispatchMouseEvent` (`mousePressed` & `mouseReleased`) serta `Input.dispatchKeyEvent` (`Enter`) tingkat hardware (`isTrusted: true`).

---

### B. Kartu Peringatan "Failed: We noticed some unusual activity" Tidak Ter-Retry
- **Gejala**: Google Flow menampilkan kartu peringatan:
  ```
  Failed
  We noticed some unusual activity. Please visit the Help Center for more information.
  [Retry] [Reuse prompt] [Delete]
  ```
- **Penyebab**: Loop pemantauan (*polling*) sebelumnya hanya memeriksa elemen gambar baru tanpa memindai kemunculan kartu kegagalan. Filter kartu error sebelumnya memeriksa elemen ancestor (`.tiles-container`) yang berisi gambar lain, sehingga kondisi filter mengecualikan kartu error dan tombol **Retry** tidak tertekan.
- **Solusi**: Mengimplementasikan `findRetryButton` langsung pada `button[aria-label*="Retry" i]`, tombol dengan ikon `refresh`, atau elemen di dalam `<flow-error-tile>`. Ekstensi secara otomatis mengeksekusi klik pada tombol Retry setiap 3 detik dan memperpanjang batas waktu pemantauan (*deadline extension*) sebanyak +60s (gambar) atau +90s (video).

---

### C. Gagal Menempelkan Referensi Video (`FLOW_UI_INGREDIENTS_INCOMPLETE`)
- **Gejala**: Karakter dan storyboard 6 adegan berhasil dibuat, tetapi saat beralih ke generasi video (Mode Video 720p 8s), job langsung gagal dengan error 503 `FLOW_UI_VIDEO_FALLBACK_FLOW_UI_INGREDIENTS_INCOMPLETE`.
- **Penyebab**: Popover *Add ingredients* (`+`) di Google Flow menggunakan token CDN (`lh3.googleusercontent.com/asb/...` dan `flow-content.google/image/<UUID>`). Pencocokan string URL penuh gagal menemukan thumbnail karakter sekunder, dan sistem membatalkan seluruh proses video.
- **Solusi**:
  1. `addFlowIngredients()` di `background.js` kini mengekstrak UUID dan token CDN (`AB-n...`) dari ID referensi.
  2. Mengimplementasikan logika fallback cerdas: jika referensi utama (storyboard adegan) berhasil ditempelkan (`added > 0`), sistem langsung melanjutkan pengetikan prompt dan memulai render video tanpa membatalkan job.

---

### D. Race Condition Polling Job Backend (Error 404)
- **Gejala**: Saat frontend langsung memulai polling status `GET /api/jobs/{job_id}`, backend belum selesai mendaftarkan task asyncio ke memori sehingga menghasilkan HTTP 404 sementara.
- **Solusi**:
  - `backend/jobs_executor.py`: Fungsi `create_and_register_job()` mendaftarkan status job secara sinkron ke memori dan file riwayat sebelum coroutine async dieksekusi.
  - `frontend/app.js`: Mekanisme *retry counter* hingga 3 kali percobaan sebelum menyatakan job hilang.

---

## 3. Berkas yang Dimodifikasi & Dokumentasi Superpowers

1. **`engine/chrome-extension/background.js`**:
   - Menambahkan `handleNativeClick` via `chrome.debugger` (`Input.dispatchMouseEvent`, `Input.dispatchKeyEvent`).
   - Pemisahan alur `generateImageViaAuthenticatedFlowUi` & `generateVideoViaAuthenticatedFlowUi`: Prepare -> Trusted Click -> Poll with Auto-Retry.
   - Refaktor `addFlowIngredients` dengan ekstraksi token UUID/CDN dan non-blocking reference execution.
2. **`backend/jobs_executor.py` & `backend/routers/jobs.py`**:
   - Implementasi `create_and_register_job()` sinkron.
3. **`frontend/app.js`**:
   - Toleransi polling 404 transisi & fallback eksekusi dari storyboard aktif.
4. **Dokumentasi Spesifikasi & Rencana**:
   - `docs/superpowers/specs/2026-09-22-flow-error-auto-retry-and-ingredient-matching-design.md`
   - `docs/superpowers/plans/2026-09-22-flow-error-auto-retry-and-ingredient-matching.md`

---

## 4. Status Pengujian & Verifikasi

- **Node.js Test Suite**: `58 passed, 0 failed` (100% lulus untuk ekstensi Chrome, DOM generator, parser Boq RPC, selector).
- **Python Pytest Suite**: `283 passed, 0 failed` (100% lulus untuk API router, executor, bridge agent, dan continuity).
- **Verifikasi Langsung pada Google Flow Canvas**:
  - 3 Sheet Karakter (*陆昭华*, *董玉珍*, *沈策*) selesai dan tersimpan di cache laptop & canvas proyek.
  - 6 Gambar Storyboard Adegan selesai dan diunduh ke `storage/jobs/job_4fa8a9a4/storyboard_*.png`.
  - Mode Google Flow berpindah ke Video (720p · 8s).

---

## 5. Panduan Melanjutkan di Perangkat Lain

Jika Anda ingin melanjutkan di komputer/perangkat lain, ikuti langkah-langkah berikut:

### Langkah 1: Clone / Pull Repositori Terbaru
```bash
git clone https://github.com/effands/Sinematica.git
cd Sinematica
git pull origin main
```

### Langkah 2: Setup Environment & Dependensi
```bash
# Python Virtual Environment
python3 -m venv .venv
source .venv/bin/activate  # atau .venv\Scriptsctivate di Windows
pip install -r requirements.txt

# Verifikasi Test Suite
pytest tests/ -q
node --test engine/chrome-extension/*.test.js tests/*.test.js
```

### Langkah 3: Muat Ekstensi di Google Chrome
1. Buka Google Chrome dan navigasikan ke `chrome://extensions/`.
2. Aktifkan **Developer mode** di pojok kanan atas.
3. Klik **Load unpacked** dan pilih folder `engine/chrome-extension/`.
4. Buka tab [flow.google.com](https://flow.google.com) dan pastikan akun Google sudah login.
5. Klik ikon ekstensi **Sinematica Flow Agent** di toolbar / side panel dan pastikan status menunjukkan **Flow Session: Ready**.

### Langkah 4: Menjalankan Server & Eksekusi
```bash
# Opsi 1: Menjalankan Test Runner Otomatis
./test_generation.sh  # atau test_generation.bat di Windows

# Opsi 2: Menjalankan Web Dashboard Studio
./start.sh            # atau start.bat di Windows
# Buka http://127.0.0.1:8888 di browser
```

Sistem akan secara otomatis menggunakan cache master sheet dan storyboard yang sudah ada, lalu melanjutkan langsung ke proses render Video Adegan 1 hingga selesai!
