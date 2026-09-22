# Blueprint Produksi 1 Scene Menghasilkan 1 Video & Rincian Interaksi Klik Google Flow

## Ringkasan Eksekutif & Tujuan Utama
Dokumen ini mendokumentasikan prinsip fundamental, alur kerja konseptual (workflow non-teknis), dan rincian teknis interaksi klik antarmuka (DOM UI clicks) di Google Flow untuk menghasilkan **tepat 1 video sinematik per 1 scene adegan**.

Filosofi inti yang digunakan adalah **"Storyboard-First"** (Kunci Gambar Frame Awal Terlebih Dahulu, Baru Digerakkan Menjadi Video). Pendekatan ini mencegah inkonsistensi visual, perubahan wajah karakter secara acak, ataupun lompatan suasana tempat antar-adegan.

---

## Bagian 1: Workflow Konseptual (Non-Teknis) Produksi Adegan

Proses pembuatan 1 video klip pada setiap scene berjalan dalam 5 tahapan terstruktur:

### 1. Menentukan Penampilan Karakter (Kamus Visual & Casting)
* Sebelum scene diproses, sistem telah memegang kartu identitas/foto patokan karakter (fitur wajah, pakaian, siluet, dan warna rambut).
* Karakter ini menjadi acuan identitas visual mutlak agar tidak berubah di sepanjang film.

### 2. Melukis Gambar Storyboard Adegan (Kunci Frame Awal)
* Sistem menggabungkan identitas karakter dengan deskripsi suasana dan naskah adegan.
* Dihasilkan **satu gambar diam (Storyboard Image)** yang menggambarkan komposisi, pencahayaan, dan sudut kamera adegan tersebut secara presisi.
* Gambar ini disimpan di penyimpanan lokal sebagai artefak frame awal (*Start Image*).

### 3. Membawa Gambar Storyboard ke Google Flow
* Sistem mengalokasikan salah satu profil Chrome Fleet yang sedang aktif dan siap digunakan.
* Gambar storyboard diunggah ke proyek Google Flow pada profil tersebut.
* **Prinsip Utama:** Gambar storyboard adegan ini dijadikan sebagai **Frame Pembuka (Start Image)** video, bukan foto mentah karakter, sehingga sejak detik ke-0 (frame pertama) visual video sudah pasti sesuai naskah.

### 4. Mengetik Naskah Gerakan & Menekan Tombol Render
* Di Google Flow, sistem secara otomatis:
  1. Mengetik prompt instruksi gerakan kamera dan aksi subjek.
  2. Memilih format aspek rasio (9:16 vertikal atau 16:9 horisontal), durasi, dan **mengunci output menjadi single output (x1)**.
  3. Memulai proses pembuatan video (*Start Generation*).

### 5. Menunggu & Menarik Video Jadi ke Komputer Lokal
* Sistem memantau status render di Google Flow (dari proses render berjalan hingga selesai 100%).
* Setelah video selesai dirender, sistem langsung mengunduh file video `.mp4` ke direktori lokal (contoh: `storage/jobs/<job_id>/scene_01.mp4`).
* File video diverifikasi integritasnya sebelum melanjutkan ke scene berikutnya.

---

## Bagian 2: Rincian Interaksi Klik di Antarmuka Google Flow (UI Click Blueprint)

Berikut adalah urutan langkah demi langkah interaksi klik dan kontrol DOM yang dieksekusi di antarmuka web Google Flow untuk setiap adegan:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        ALUR KLIK & INTERAKSI DI GOOGLE FLOW                           │
└────────────────────────────────────────────────────────────────────────────────────────┘

 [1. Setup & Navigasi]
   ├─► Klik "New Project" / "Create Project" (bila belum berada di canvas proyek aktif)
   └─► Klik Chip "Agent Mode" (ubah ke status Manual jika sedang aktif)

 [2. Settings Trigger Popover]
   ├─► Klik tombol "Settings Trigger" (pil di samping prompt box: '9:16 · Video · x1')
   ├─► Klik Toggle Mode ───────────► Pilih "Video"
   ├─► Klik Toggle Video Type ─────► Pilih "Frames" (atau "Ingredients")
   ├─► Klik Toggle Aspect Ratio ───► Pilih "9:16" (Vertikal) atau "16:9" (Horisontal)
   ├─► Klik Toggle Output Count ───► Pilih "x1" (Kunci 1 Video saja per generate)
   └─► Klik Backdrop / Luar Overlay ► Tutup panel pengaturan popup

 [3. Memasang Frame Pembuka (Start Image)]
   ├─► Klik tombol "Hapus / Remove (×)" pada Chip lama di prompt box
   ├─► Klik tombol "Add Ingredients / Add Media" (atau slot Start Frame)
   ├─► Klik Tile Gambar Storyboard Scene pada daftar aset
   └─► Klik tombol "Add to prompt" / "Set as Start Frame"

 [4. Mengetik Prompt & Memulai Render]
   ├─► Klik Area Kotak Teks (ProseMirror contenteditable prompt box)
   ├─► Injeksi teks prompt arah visual & gerakan kamera
   └─► Klik tombol "Start generation" (Tombol Panah / <flow-generate-icon-button>)

 [5. Pemantauan & Pengambilan Hasil]
   ├─► Monitor Tile Video baru di canvas & indikator progress spinner
   ├─► [Kondisi Gagal Jaringan]: Klik tombol "Retry / Coba lagi" (ikon refresh) pada tile
   ├─► [Render Selesai 100%]:
   │     ├─► Klik tombol menu "More options (⋮)" pada tile video
   │     └─► Klik item menu "Download" (unduh berkas .mp4 ke storage lokal)
   └─► Reset prompt box siap untuk adegan berikutnya
```

---

## Bagian 3: Standar Kualitas & Reliability

1. **Konsistensi Visual Mutlak (Storyboard-First):**
   * Video selalu digenerasikan dari gambar storyboard lokal yang sudah dikomposisikan, bukan langsung dari *text-to-video* mentah.
2. **Kunci Single Output (`x1`):**
   * Pengaturan `Output count: x1` selalu dipastikan aktif pada setiap eksekusi agar tidak memboroskan kuota akun Google Flow.
3. **Isolasi Kepemilikan Profil (Project-Scoped):**
   * Akun/profil Chrome yang mengunggah storyboard adalah profil yang sama yang merender dan mengunduh videonya.
4. **Pemisahan Render vs Unduh:**
   * Gangguan pada saat proses unduhan file video tidak boleh memicu render ulang yang membuang waktu; sistem cukup mengulang unduhan (*download retry*) dari profil pemilik aset.
