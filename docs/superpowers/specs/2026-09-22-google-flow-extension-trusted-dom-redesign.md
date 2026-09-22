# Spesifikasi Desain: Perombakan Ekstensi Chrome Sinematica Flow Agent (Trusted DOM & Synthetic DataTransfer)

## 1. Latar Belakang & Masalah
Google Flow (`flow.google.com`) telah beralih sepenuhnya ke arsitektur antarmuka baru berbasis **Angular Material MDC, Web Components, dan ProseMirror Editor**. 

Pembaruan tersebut menyebabkan pendekatan otomasi lama pada ekstensi Chrome mengalami kegagalan:
1. **Penolakan Input File Programatik**: Pemanggilan `<input type="file">.click()` atau pengisian file tanpa interaksi fisik ditolak oleh browser security model dan dropzone internal Google Flow.
2. **Ketergantungan API Usang**: Endpoint REST AI Sandbox lama mengembalikan error (403/404) karena Google Flow telah beralih ke format Google Boq `batchexecute` RPC (`wrb.fr`).
3. **Penyumbatan Event Pengetikan**: Form validation Angular Material mengunci tombol submit jika event pengetikan teks tidak membawa flag event `composed: true`.

Ekstensi referensi `ziqva-google-flow` telah membuktikan keberhasilan automasi di Google Flow terbaru dengan menggunakan teknik manipulasi ganda (Synthetic `DataTransfer` ClipboardEvent Paste, hardware-level clicks via `chrome.debugger`, dan parsing Boq RPC). Dokumen ini merinci rancangan perombakan total mesin otomasi ekstensi Sinematica dengan mengadopsi teknik terbukti tersebut sambil menjaga kompatibilitas penuh dengan infrastruktur backend dan multi-profile Chrome fleet Sinematica.

---

## 2. Arsitektur Modul Ekstensi Baru

Struktur modul di dalam `engine/chrome-extension/` dirombak menjadi arsitektur berlapis:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SINEMATICA BACKEND (FastAPI)                              │
│                    ws://127.0.0.1:8888/ws/agent (Multi-Profile Fleet)                  │
└───────────────────────────────────────────▲────────────────────────────────────────────┘
                                            │ WebSocket (JSON RPC)
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                    CHROME EXTENSION BACKGROUND (Service Worker)                        │
│   - background.js : Router pesan WebSocket, Fleet Pool register, Heartbeat             │
│   - flow-logger.js : Logging terpusat ke Backend, DevTools Console, & Side Panel       │
│   - Native Click Dispatcher : chrome.debugger (Input.dispatchMouseEvent)               │
└─────────────────────┬───────────────────────────────────────────┬──────────────────────┘
                      │ chrome.tabs.sendMessage                  │ Web Accessible Resources
┌─────────────────────▼────────────────────────┐ ┌────────────────▼──────────────────────┐
│       ISOLATED WORLD (Content Script)        │ │         MAIN WORLD (Page Context)      │
│  - content.js : Bridge pesan isolated/main   │ │  - flow-network-parser.js              │
│  - flow-executor.js :                        │ │    (Decode Boq RPC & translate events) │
│    * Injeksi file terpercaya (Synthetic Paste)│ │  - flow-interceptor.js                 │
│    * Manipulasi DOM ProseMirror & Toggles   │ │    (Sniff session tokens & Direct RPC) │
│    * Start Frame attachment & Trigger submit │ │                                        │
│    * Deteksi tile, visual cursor & retry     │ │                                        │
└──────────────────────────────────────────────┘ └────────────────────────────────────────┘
```

### Modul-Modul Utama:
1. **`flow-network-parser.js` (MAIN World & Node Test)**:
   - Mendekode paket respons Boq Google `batchexecute` (`)]}'\n...`) dan menerjemahkan RPC (`IMAGE_READY`, `VIDEO_READY`, `PROJECT_CREATED`, dll.).
   - Menyusun payload Boq RPC untuk kebutuhan upload background langsung jika diperlukan.
2. **`flow-interceptor.js` (MAIN World)**:
   - Melakukan intersepsi non-intrusif pada `window.fetch` dan `XMLHttpRequest` untuk membaca progres generasi media dari Google Flow secara real-time.
   - Menangkap session tokens dari `window.WIZ_global_data` (`FdrFJe`, `SNlM0e`, `cfb2h`).
3. **`flow-executor.js` (ISOLATED World)**:
   - Bertanggung jawab atas seluruh eksekusi UI DOM di tab Google Flow.
   - Mengelola manipulasi input file terpercaya via Synthetic `DataTransfer` ClipboardEvent Paste.
   - Mengelola interaksi menu pengaturan (*Settings Trigger popover*), pemilihan aspek rasio (9:16 / 16:9), dan penguncian output count `x1`.
   - Mengelola pemasangan gambar storyboard ke slot *Start Frame*.
   - Mengelola pengetikan teks prompt dengan `composed: true` dan klik tombol *Start generation*.
   - Mengelola pemantauan tile video hingga 100% dan penanganan retry otomatis jika terjadi kegagalan jaringan.
4. **`background.js` (Service Worker)**:
   - Menjaga koneksi WebSocket aktif ke backend Sinematica di `ws://127.0.0.1:8888/ws/agent`.
   - Melakukan registrasi profil fleet (`instance_id`, `project_id`, `ready: true`).
   - Menerima permintaan klik fisik dari content script dan menjalankannya melalui `chrome.debugger` (`Input.dispatchMouseEvent`).

---

## 3. Alur Eksekusi & Injeksi File Terpercaya (Trusted Flow Execution)

Setiap scene diproses dengan alur berikut di dalam `flow-executor.js`:

### A. Injeksi Gambar Terpercaya (*Trusted File Manipulation*)
1. Ekstensi menerima data gambar storyboard dalam format Base64 dari backend.
2. Mengonversi Base64 menjadi binary `Blob` $\rightarrow$ objek `File(blob, fileName, { type: mimeType })`.
3. Memasukkan objek `File` ke dalam objek `DataTransfer`.
4. Memicu event clipboard:
   ```javascript
   const pasteEvt = new ClipboardEvent('paste', {
     bubbles: true,
     cancelable: true,
     composed: true,
     clipboardData: dataTransfer
   });
   proseMirrorEditor.dispatchEvent(pasteEvt);
   ```
5. Fallback: Jika clipboard paste tidak memunculkan tile dalam batas waktu, salin file ke `<input type="file">` melalui `input.files = dataTransfer.files` dan picu `Event('change', { bubbles: true })`.
6. Menunggu hingga upload selesai (spinner tile menghilang dan thumbnail siap).

### B. Pengaturan Mode Video & Kunci Single Output (`x1`)
1. Mencari tombol *Settings Trigger* di sebelah kotak prompt.
2. Mengklik tombol settings hingga popover `flow-prompt-box-settings` terbuka.
3. Memilih Toggle Mode $\rightarrow$ `Video`.
4. Memilih Toggle Video Type $\rightarrow$ `Frames` (atau `Ingredients`).
5. Memilih Toggle Aspect Ratio $\rightarrow$ `9:16` atau `16:9` sesuai spesifikasi scene.
6. Memilih Toggle Output Count $\rightarrow$ `x1` (mengunci 1 output video saja per klik).
7. Menutup popover pengaturan via event `Escape` atau klik backdrop overlay.

### C. Pemasangan Frame Pembuka (*Start Frame Slot*)
1. Menghapus chip/media lama yang masih ada di prompt box dengan mengklik tombol silang (`×`).
2. Menghubungkan gambar storyboard yang baru diupload ke slot *Start Frame* pada prompt box.

### D. Pengetikan Prompt & Klik Submit
1. Memberi fokus pada area teks `.ProseMirror`.
2. Mengetikkan prompt gerakan adegan menggunakan `InputEvent('insertText', { data: text, composed: true, bubbles: true })` sehingga validator form Angular Material aktif dan tombol submit tidak terkunci.
3. Memicu klik tombol `<flow-generate-icon-button>`:
   - Utama: Menembakkan perintah klik fisik via `chrome.debugger` (`Input.dispatchMouseEvent`).
   - Fallback: Simulasi urutan event mouse sintetis (`mouseenter`, `mousedown`, `mouseup`, `click`).

### E. Pemantauan & Pengambilan Hasil
1. Mengawasi kemunculan tile generasi video baru pada canvas Google Flow.
2. Jika muncul status error atau tombol refresh, lakukan auto-retry hingga batas toleransi tercapai.
3. Saat video selesai (100%), ekstrak URL video `.mp4` dan kembalikan response berhasil ke backend via WebSocket.

---

## 4. Protokol Komunikasi WebSocket (Sinematica Fleet Compatibility)

1. **Endpoint**: `ws://127.0.0.1:8888/ws/agent`
2. **Pendaftaran Profil**:
   ```json
   {
     "type": "register",
     "instance_id": "profile-chrome-1",
     "project_id": "aaa1ca86-92ee-4436-b4d5-ace19f4481c9",
     "ready": true,
     "user_email": "user@gmail.com"
   }
   ```
3. **Pesan Tugas Perenderan**:
   ```json
   {
     "type": "execute_task",
     "id": "task-uuid-12345",
     "params": {
       "kind": "video",
       "prompt": "Cinematic camera movement...",
       "images": [
         {
           "fileName": "scene_01_storyboard.png",
           "base64Data": "iVBORw0KGgo...",
           "mimeType": "image/png"
         }
       ],
       "storyboard": {
         "aspectRatio": "9:16",
         "outputCount": 1
       },
       "projectId": "aaa1ca86-92ee-4436-b4d5-ace19f4481c9"
     }
   }
   ```
4. **Respon Tugas Selesai**:
   ```json
   {
     "type": "task_response",
     "id": "task-uuid-12345",
     "status": 200,
     "result": {
       "ok": true,
       "videoUrl": "https://flow-content.google/video/uuid.mp4",
       "mediaId": "media-uuid-999"
     }
   }
   ```

---

## 5. Rencana Pengujian & Kriteria Keberhasilan

1. **Node.js Test Suite**:
   - `node --test engine/chrome-extension/*.test.js` (Seluruh 49+ tes unit lulus 100%).
2. **Python Backend Test Suite**:
   - `.venv/bin/pytest tests/` (Seluruh 283+ tes integrasi lulus 100%).
3. **Syntax Validation**:
   - `node --check engine/chrome-extension/*.js` (Tidak ada galat sintaks pada service worker dan content scripts).
