# Sinematica AI Studio — Master Agent Handover & Knowledge Memory

> **File:** `AGENT_CONTEXT_HANDOVER.md`  
> **Terakhir Diperbarui:** 23 September 2026  
> **Repositori:** `https://github.com/effands/Sinematica`  
> **Tujuan:** Dokumentasi lengkap memori konteks, arsitektur sistem, kebiasaan & preferensi user, aturan mutlak (*inviolable rules*), riwayat bug & solusi, serta panduan kerja untuk agent AI penerus.

---

## 1. Profil Proyek & Ikhtisar Sistem

**Sinematica AI Studio** adalah platform orkestrasi otomatisasi pembuatan film sinematik AI berdurasi penuh (multi-scene) yang terintegrasi langsung dengan **Google Flow (Imagen 3 & Google Veo 2)** melalui **Chrome Extension (Sinematica Flow Agent)** dan **Python Backend (FastAPI)**.

### Komponen Utama:
1. **Frontend Dashboard (`http://127.0.0.1:8888`)**:
   - Berbasis Vanilla JS & Tailwind CSS (`frontend/app.js`, `frontend/index.html`).
   - Fitur: Brainstorming Ide/Premis AI, Casting Karakter, Preset Genre/Vibe, Pemilihan Durasi Scene (4s, 6s, 8s, 10s), Rasio Aspek (9:16 Portrait, 16:9 Landscape), dan Monitoring Job Real-time.
2. **Backend Server (`backend/`)**:
   - Python FastAPI (`backend/main.py`, `backend/jobs_executor.py`).
   - Menjalankan pipeline pembuatan karakter, penyusunan storyboard, pembuatan dense prompt multi-shot, pemantauan status render, unduhan file video MP4, dan penjahitan video otomatis (*auto-stitch*).
3. **Chrome Extension (`engine/chrome-extension/`)**:
   - Manifest V3 (`background.js`, `content.js`, `flow-executor.js`, `flow-interceptor.js`, `flow-project.js`).
   - Bertugas mengotomatisasi DOM Google Flow (`https://flow.google.com/*`) secara tepercaya: konfigurasi setelan (mode Video/Gambar, rasio, durasi, output x1), pemasangan thumbnail referensi (*Ingredients/Bahan*), pengetikan prompt ke editor ProseMirror, eksekusi tombol kirim, dan intersepsi respon network RPC (Boq batchexecute).

---

## 2. Alur Pipeline 3 Tahap Sinematika (WAJIB & MUTLAK)

Proses pembuatan film di Sinematica **HARUS** melewati 3 tahap berurutan tanpa melewati tahap apa pun:

```
[Tahap 1: Character Seed Generation]
    └── Menghasilkan 1-3 Character Sheet (wajah, profil, pose 9-grid) per karakter film.
    └── Menyimpan media_id di Google Flow & master cache lokal (`storage/film_assets/`).

[Tahap 2: Storyboard Key-Frame Generation] (DILARANG DISKIP!)
    └── Menghasilkan 1 Gambar Storyboard per adegan (16:9 atau 9:16).
    └── Gambar storyboard dibuat dengan melampirkan sheet karakter Tahap 1 sebagai referensi (Ingredients).
    └── Mengunci komposisi, blocking, pencahayaan, dan tata letak sebelum video dibuat.

[Tahap 3: Multi-Angle Scene Video Generation]
    └── Menghasilkan video per adegan (10s/8s/6s/4s) via Google Veo di Google Flow.
    └── Wajib melampirkan 2-4 Add Image References (Ingredients):
        [1] Gambar Storyboard Adegan (Tahap 2)
        [2+] Character Sheets (Tahap 1)
    └── Mengetik prompt padat multi-shot (3-5 beats) + Spoken Language Lock.
    └── Mengunduh video MP4 hasil render ke `storage/jobs/{job_id}/scene_XX.mp4`.

[Tahap Akhir: Auto-Stitch]
    └── Menggabungkan seluruh `scene_XX.mp4` menjadi film utuh final dengan audio & transisi sinkron.
```

---

## 3. Kebiasaan, Preferensi, & Standar Kerja User (CRITICAL)

1. **Non-Regresif (*Feature Isolation*)**:
   - **ATURAN MUTLAK**: Ketika mengerjakan fitur A atau memperbaiki bug A, **JANGAN SAMPAI** merusak fitur B yang sudah berjalan sebelumnya.
   - Selalu jalankan verifikasi penuh sebelum dan sesudah perubahan kode:
     - Node.js tests: `node --test engine/chrome-extension/*.test.js`
     - Backend tests: `.\.venv\Scripts\pytest tests/ -q`
2. **Dukungan Penuh Multi-Bahasa (Bilingual ID/EN)**:
   - Browser user menggunakan antarmuka **Google Flow Bahasa Indonesia** (tetapi kode harus tetap kompatibel dengan Bahasa Inggris).
   - Pemetaan Label:
     - Settings Trigger: `"Pemicu setelan"` / `"Settings trigger"` / `button.settings-trigger-button`
     - Mode: `"Gambar"` / `"Image"`, `"Video"`
     - Submode: `"Bahan"` / `"Ingredients"`, `"Frame"` / `"Frames"`
     - Durasi: `"10 dtk"` / `"10 detik"` / `"10s"`, `"8 dtk"` / `"8s"`, `"6 dtk"` / `"6s"`, `"4 dtk"` / `"4s"`
     - Rasio: `"16:9"` / `crop_16_9` / `landscape`, `"9:16"` / `crop_9_16` / `portrait`
     - Jumlah Output: Terkunci pada `"x1"` / `"1"`
     - Tombol Start: `"Mulai pembuatan"` / `"Start generation"` / `flow-generate-icon-button button`
     - Project Baru: `"+ Project baru"` / `"New project"`
3. **Preservasi Akun Google Multi-Login (`/u/X`)**:
   - Akun Google user login pada profil index ke-3 (`https://flow.google.com/u/3/project/...`).
   - Setiap navigasi URL atau URL builder (`FlowProject.buildProjectUrl`) **HARUS** mempertahankan prefix `/u/3` (atau `/u/X`). Dilarang membuang prefix `/u/X` karena akan melempar tab kembali ke home akun default `/u/0`.
4. **Single Atomic Submit (Anti-Double / Triple Click)**:
   - Dilarang menembakkan event berulang-ulang tanpa jeda yang menyebabkan Google Flow membuat video 3x (1 sukses, 2 gagal).
   - Submit dilakukan menggunakan rantai event terpadu yang aman:
     1. In-page pointer chain (`pointerdown` ➔ `mousedown` ➔ `pointerup` ➔ `mouseup` ➔ `click`) pada tombol Start.
     2. KeyboardEvent `Enter` (keycode 13) pada editor ProseMirror yang terfokus.
     3. Hardware CDP click via `chrome.debugger` jika tersedia.

---

## 4. Kebijakan Keamanan Prompt Google Flow (Veo Safety Rules)

Google Veo (Video) memiliki filter keamanan AI yang jauh lebih ketat dibanding Imagen (Gambar). Pelanggaran akan memicu error: *"Perintah ini mungkin melanggar kebijakan kami tentang pembuatan gambar tokoh berpengaruh / kebijakan konten"*.

### Aturan Formulasi Prompt Aman:
1. **Dilarang Menggunakan Kata "Real Human Actors"**:
   - ❌ *Salah:* `LIVE-ACTION PHOTOGRAPHY ONLY: real human actors...`
   - ✅ *Benar:* `LIVE-ACTION PHOTOGRAPHY ONLY: original fictional characters, natural skin texture and pores, realistic hair and fabric physics, optical cinematic camera capture. NO cartoon, anime, 3D CGI animation, Pixar style, illustration, painting, comic art, doll-like face, plastic skin, or cel shading.`
2. **Dilarang Topik Eksperimen Biologis / Medis / Injeksi Hewan**:
   - ❌ *Salah:* `quarantine laboratory`, `micro-injector seated in rubber valve`, `injecting sedatives into juvenile creature in culture chamber (为培养舱内的幼兽注入镇静剂)`, `radiation shielding`.
   - ✅ *Benar:* `subterranean research study room`, `examining glowing mineral crystal with precision tools`, `gentle herbal essence applied to a botanical leaf`.
3. **Dilarang Sengketa Hukum / Skandal Keuangan Nyata / Nama IP Populer**:
   - ❌ *Salah:* `30 million debt scandal (三千万烂账)`, `eviction order (驱逐协议)`, nama karakter tabrakan IP (`陆沉 / Lu Chen` dari game populer).
   - ✅ *Benar:* `heritage archive box`, `family legacy rights document`, nama karakter fiktif orisinal (`陆冉 / Lu Ran`, `林宛 / Lin Wan`, `Mateo`, `Elena`).
4. **Hindari Penumpukan Prompt Berlebihan (Prompt Bloat)**:
   - Prompt video Veo **TIDAK BOLEH** ditempeli teks panduan internal panjang 5.000 karakter (seperti aturan audit Bahasa Indonesia, aturan engsel pintu mobil, atau aturan properti).
   - Prompt Veo harus fokus pada: **Opening State ➔ 3-5 Shot Beats Timeline ➔ Final Continuity Frame ➔ Spoken Language Lock ➔ Visual Style Lock** (panjang total di bawah 1.500 karakter).

---

## 5. Peta File & Arsitektur Kode

| File | Peran & Tanggung Jawab Utama |
| :--- | :--- |
| `engine/chrome-extension/background.js` | Service worker ekstensi: mengelola `generateImageViaAuthenticatedFlowUi`, `generateVideoViaAuthenticatedFlowUi`, `selectFlowOption` multi-bahasa, attachment ingredients, dan native click debugger. |
| `engine/chrome-extension/flow-executor.js` | Content script DOM automation: memastikan kanvas project aktif (`ensureProject`), interaksi prompt box, dan manajemen overlay settings. |
| `engine/chrome-extension/flow-project.js` | Deteksi & validasi project URL, ekstraksi UUID 36-karakter, dan preservasi prefix user multi-login (`/u/X`). |
| `engine/chrome-extension/flow-interceptor.js` | Skrip MAIN world: menangkap event `VIDEO_READY`, `IMAGE_READY`, token sesi, dan RPC Boq batchexecute. |
| `backend/jobs_executor.py` | Eksekutor utama job film: orkestrasi 3 tahap, koordinasi failover profil Chrome, perakitan prompt akhir, pemantauan render, dan unduhan MP4. |
| `backend/gemini_storyboard.py` | Mesin AI naskah & storyboard: brainstorming ide, penyusunan creative brief, prompt visual, `POLICY_SAFE_RULES`, dan auto-sanitasi jika terjadi penolakan kebijakan. |
| `backend/scene_pacing.py` | Pacing 10 detik padat (*dense multi-angle rewrite*): membagi adegan menjadi 3-5 camera beats terukur (0-3.3s, 3.3-6.6s, 6.6-10s). |
| `engine/omniflash/generators/i2v.py` | Generator video R2V/T2V & uploader media gambar ke Google Flow. |
| `data/settings.json` | Konfigurasi tersimpan: provider AI, template storyboard, flag `enable_scene_storyboard_image = true`. |

---

## 6. Perintah Verifikasi & Pengujian (*Testing Commands*)

Setiap kali melakukan perubahan, jalankan perintah berikut di terminal:

```powershell
# 1. Jalankan Unit Tests Chrome Extension (62 tests)
node --test engine/chrome-extension/*.test.js

# 2. Jalankan Backend Tests (286 tests)
.\.venv\Scripts\pytest tests/ -q

# 3. Operasikan Browser Skill (bsk) jika perlu inspeksi/uji live DOM
& "C:\Users\Administrator\.local\bin\bsk.exe" session start --browser 649ccee8 --no-focus
& "C:\Users\Administrator\.local\bin\bsk.exe" tab list --scope user --session <SESSION_ID>
& "C:\Users\Administrator\.local\bin\bsk.exe" evaluate --session <SESSION_ID> <JS_EXPRESSION>
```

---

## 7. Status Terakhir Proyek & Siap Lanjut

- **Git Commit Terakhir**: `0167289` (*fix: sanitize safety policy filters for biological/medical terms and streamline final video prompt*).
- **Semua Unit Test**: `62 Node.js tests passed`, `286 Pytest tests passed` (100% Green).
- **Status Dashboard**: Aktif di `http://127.0.0.1:8888`.
- **Ekstensi Chrome**: Siap di-load dari folder `engine/chrome-extension`.
- **Branch**: `main` (sinkron dengan `origin/main`).

Semua memori, aturan, riwayat pengujian, dan arsitektur telah tercatat rapi di file ini untuk digunakan oleh agen AI selanjutnya. 🎬🚀
