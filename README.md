# 🎬 Sinematica AI Studio

Dashboard & Engine lokal untuk **Auto Generate Video Sinematik via Google Flow (Omni Flash)** dengan kecerdasan **Gemini 3.6 Flash**, dukungan **Multi-Profile Chrome Fleet Balancer**, dan **Galeri & Editor Penggabung Film Sinematik (FFmpeg)**.

---

## 🌟 Fitur Utama Sinematica

1. **Gemini 3.6 Flash Storyboard & Visual Prompt Engine**:
   - Menganalisis gambar referensi tema/karakter (Multimodal Vision).
   - Menghasilkan adegan demi adegan (*scene-by-scene script*) dengan prompt detail Bahasa Inggris untuk Google Flow.
   - Menjaga konsistensi rupa karakter, pencahayaan, dan gaya sinematik di seluruh adegan.

2. **Multi-Profile Chrome Fleet Manager (Chrome Add-on)**:
   - Ekstensi Chrome custom (`engine/chrome-extension`) dapat dimuat di **banyak profil Chrome sekaligus** (Chrome Profile 1, Profile 2, dst).
   - Server backend akan **otomatis membagi (load balance / round-robin)** tugas render adegan ke profil-profil Chrome yang terhubung sehingga proses pembuatan video jauh lebih cepat.

3. **Multi-Flow Auto Task Execution & Real-time Terminal**:
   - Pemantauan status live render per adegan per profil Chrome.
   - Otomatis mengunduh file video MP4 hasil render ke penyimpanan lokal (`storage/jobs/<job_id>/scene_XX.mp4`).

4. **Interactive Video Gallery & Cinematic Film Director**:
   - Galeri untuk menonton klip adegan video.
   - Otomatis menggabungkan (*concatenate*) klip adegan cerita menjadi satu **Film Sinematik Utuh** (`cinematic_film.mp4`) menggunakan FFmpeg.
   - Sekali klik untuk mengunduh film utuh atau klip adegan individual.

---

## 🚀 Setup & Cara Penggunaan

### 1. Jalankan Application Server (FastAPI)
Klik ganda file **`start.bat`** atau jalankan perintah di terminal:

```bash
start.bat
```

Server akan berjalan di: **`http://127.0.0.1:8001`**

### 2. Isi Gemini API Key
- Buka dashboard di `http://127.0.0.1:8001`.
- Klik tombol **⚙️ Pengaturan API Key** di sudut kiri bawah.
- Masukkan **Gemini API Key** gratis dari [Google AI Studio](https://aistudio.google.com/apikey).

### 3. Load Chrome Extension Add-on di Profil Chrome
Untuk menggunakan banyak profil Chrome (Multi-Flow):
1. Buka browser Google Chrome (bisa buka beberapa jendela profil Chrome yang berbeda).
2. Di setiap profil Chrome, buka URL: `chrome://extensions`
3. Aktifkan **Developer mode** di pojok kanan atas.
4. Klik **Load unpacked**, pilih folder: `E:\AUTO KLIK\Sinematica\engine\chrome-extension`
5. Buka tab [flow.google.com](https://flow.google.com/) di masing-masing profil Chrome dan pastikan akun Google sudah **Login**. Alamat lama `labs.google/fx/flow` dan `labs.google/fx/tools/flow` juga tetap dikenali oleh extension.
6. Extension di setiap profil akan otomatis terhubung ke dashboard Sinematica! (Cek tab **Chrome Profile Fleet** di dashboard untuk memastikan status menjadi *Siap / Online*).

---

## 📽️ Langkah Membuat Film Sinematik Auto-Generate

1. Buka tab **Gemini 3.6 Storyboard** di dashboard.
2. Upload 1 atau lebih **Gambar Referensi Tema/Karakter**.
3. Tulis **Premis / Ide Cerita Adegan**, tentukan jumlah adegan (misal 4 adegan) & Aspect Ratio (9:16 Portrait atau 16:9 Landscape).
4. Klik **✨ Generate AI Storyboard (Gemini 3.6 Flash)**.
5. Setelah adegan storyboard selesai diracik oleh Gemini, klik **🚀 Kirim & Eksekusi ke Flow**.
6. Masuk ke tab **Execution Terminal** untuk memantau proses render video yang secara otomatis dikerjakan oleh Fleet Profil Chrome Anda.
7. Setelah selesai, buka tab **Video Gallery & Film Director** untuk menonton klip adegan dan mengunduh **Film Sinematik Utuh**!

---

## 📁 Struktur Folder

```
Sinematica/
├── engine/
│   ├── chrome-extension/     # Add-on Ekstensi Chrome untuk Multi-Profile
│   └── omniflash/            # Extension bridge & Flow API generator library
├── backend/
│   ├── main.py               # FastAPI web server entry point
│   ├── bridge_manager.py     # Fleet connection pool manager
│   ├── gemini_storyboard.py  # Gemini 3.6 Flash vision & prompt engine
│   ├── jobs_executor.py      # Task scheduler & load balancer
│   ├── film_stitcher.py      # FFmpeg video merger
│   └── routers/              # Endpoint REST & WebSocket API
├── frontend/
│   ├── index.html            # Ultra-modern glassmorphic studio SPA
│   ├── style.css             # Rich visual theme design system
│   └── app.js                # Dynamic dashboard controller
├── storage/
│   ├── uploads/              # Gambar referensi yang diunggah
│   └── jobs/<job_id>/        # Video adegan & film sinematik utuh
├── data/
│   └── settings.json         # Konfigurasi terimpan
├── .env                      # Environment variables
├── start.bat                 # Launcher script Windows
└── requirements.txt          # Python dependencies
```
