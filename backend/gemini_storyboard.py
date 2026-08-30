"""Sinematica Backend — Gemini 3.6 Flash Multi-Character & Multi-Angle Cinematic Storyboard Engine."""

import json
import logging
import random
import requests
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from PIL import Image

from . import settings
from .scene_direction import ensure_unique_character_signatures
from .text_generation import generate_text

log = logging.getLogger("sinematica.storyboard")

WEB2API_TIMEOUT = 180


ADULT_ACTION_RULES = """ATURAN KEPADATAN AKSI (WAJIB — INI YANG MEMBUAT CERITA TIDAK MEMBOSANKAN):
1. **Setiap adegan WAJIB mengubah situasi.** Di akhir adegan harus ada sesuatu yang berbeda dari awalnya:
   informasi baru terbongkar, konflik naik satu tingkat, keputusan diambil, atau hubungan antar tokoh berubah.
   Jika sebuah adegan bisa dihapus tanpa mengubah cerita, adegan itu SALAH dan harus dirancang ulang.
2. **DILARANG adegan "cuma jalan".** Tokoh berjalan, menatap ke kejauhan, memandang kota, menyesap kopi,
   atau memasuki ruangan TIDAK boleh menjadi isi utama sebuah adegan. Aktivitas semacam itu hanya boleh
   menjadi latar sambil tokoh melakukan aksi dramatis yang sesungguhnya.
3. **Mulai dari tengah aksi (start late, end early).** Buang basa-basi pembuka. Adegan dimulai tepat saat
   konflik sudah berjalan, dan dipotong tepat setelah titik baliknya — jangan menunggu tokoh datang lalu duduk.
3a. **Khusus adegan 10 detik, gunakan 3–5 shot bertimestamp:** 3 untuk dialog/emosi, 4 untuk drama normal,
   5 untuk aksi/perang/kejaran. Setiap shot memuat minimal dua aksi terkait dan shot terakhir berisi reveal,
   keputusan, benturan, atau reaksi tajam yang mengubah situasi. Tidak boleh ada slow motion, tatapan diam,
   pose beku, jalan kosong, atau jeda tanpa aksi. Jika ada dialog, wajib minimal DUA giliran bicara pendek
   yang dipisahkan reaksi fisik/counter-action—bukan satu kalimat yang dipanjangkan selama sepuluh detik.
4. **Adegan pertama WAJIB langsung menyodorkan konflik atau pertanyaan besar** dalam 2 detik pertama.
   DILARANG membuka film dengan establishing shot kota, gedung, atau tokoh berjalan tanpa masalah.
5. **Maksimal SATU establishing shot** di seluruh film, itu pun wajib memuat aksi dramatis di dalamnya.
6. Field `action_summary` WAJIB memuat kata kerja aksi konkret (menampar, merebut, membanting, menuduh,
   membongkar, mengusir, menangis, berteriak) — bukan kata kerja pasif seperti "terlihat", "berada",
   "menikmati", "berjalan menuju", atau "memandangi"."""

CHILDREN_ACTION_RULES = """ATURAN CERITA ANAK (WAJIB — MENGGANTIKAN ATURAN KONFLIK DEWASA):
1. **Konflik harus RINGAN dan ramah anak.** Yang boleh: kehilangan barang kesayangan, tersesat sebentar,
   salah paham kecil antar sahabat, takut mencoba hal baru, belajar berbagi/antre/minta maaf, atau
   kesulitan lucu (terpeleset, kehujanan, tidak sampai meraih sesuatu).
2. **DILARANG KERAS**: kekerasan sekecil apa pun (memukul, menampar, mendorong), pengkhianatan, fitnah,
   balas dendam, bentakan, tangisan sedih berkepanjangan, tokoh jahat menakutkan, kematian, luka, darah,
   perebutan harta, atau adegan yang bisa membuat anak takut/cemas.
3. **Setiap adegan tetap harus ADA KEJADIAN** — bukan sekadar berjalan atau memandang. Tapi kejadiannya
   berupa: menemukan sesuatu, mencoba lalu gagal dengan lucu, saling menolong, atau menemukan jalan keluar.
4. **Akhir WAJIB bahagia dan menenangkan**: masalah selesai, sahabat berbaikan, ada pelajaran sederhana
   (berbagi itu menyenangkan, berani mencoba, jujur itu baik) yang ditunjukkan lewat perbuatan, bukan digurui.
5. **Bahasa sangat sederhana** untuk usia 4-5 tahun: kalimat 5-8 kata, kata sehari-hari, tanpa istilah sulit,
   tanpa kiasan. Boleh ada pengulangan kata/kalimat yang menyenangkan karena anak menyukai pola berulang.
6. Field `action_summary` memakai kata kerja ramah: menemukan, memanggil, membantu, memberi, memeluk,
   melompat, mencari, tertawa, berbagi, mencoba lagi. DILARANG memakai kata kerja kasar.
7. **TOKOH WAJIB HEWAN/BONEKA/MAKHLUK LUCU 3D**, bukan anak manusia. Ini bukan pilihan gaya semata:
   Google Flow menolak video yang menggambarkan anak di bawah umur, jadi tokoh manusia anak akan gagal render.
   Beri nama sederhana yang mudah diingat dan diucapkan anak (Nino, Momo, Cici,Upi, Bibo)."""

POLICY_SAFE_RULES = """
ATURAN WAJIB LOLOS FILTER KEBIJAKAN GOOGLE FLOW (JANGAN DILANGGAR):
Google Flow MENOLAK video yang menggambarkan institusi/tokoh nyata. Penolakan = adegan gagal total.
1. **Aparat & Pejabat**: DILARANG menyebut `police`, `police officer`, `polisi`, seragam kepolisian, tentara,
   hakim, jaksa, atau pejabat pemerintah. Ganti dengan peran netral: `security officer`, `court usher`,
   `private investigator`, `family lawyer`, `hospital administrator`.
2. **Nama Institusi & Merek Asli**: DILARANG memakai nama rumah sakit, sekolah, bank, perusahaan, hotel,
   atau merek yang benar-benar ada (misal 'RS Harapan Bunda'). Ciptakan nama fiktif yang terdengar wajar.
3. **Tokoh Publik**: DILARANG menyebut nama orang terkenal, selebriti, atau politisi.
4. **Dokumen Resmi Negara**: hindari KTP, paspor, lambang negara, atau berkas resmi pemerintah.
   Untuk hasil tes DNA/medis, sebut generik: `a sealed laboratory result envelope`.
5. **Kekerasan**: konflik emosional (bentakan, tamparan ringan, air mata) masih boleh, tapi hindari darah,
   luka, senjata api, dan penggambaran cedera serius.
Drama, konflik, dan intensitas emosinya WAJIB tetap kuat — hanya elemen di atas yang diganti.
"""


def sanitize_prompt_for_policy(prompt_for_flow: str, rejection_reason: str = "", scene_title: str = "") -> Optional[str]:
    """Rewrite a video prompt that Google Flow rejected so the scene can be retried.

    Keeps the dramatic beat, characters, seeds, camera work, and lighting intact, and only
    swaps out whatever tends to trip Flow's policy filters. Returns the rewritten English
    prompt, or None when no model could produce one.
    """
    prompt = f"""
Anda adalah Script Doctor spesialis lolos moderasi konten Google Flow (AI video generator).

Sebuah prompt video DITOLAK oleh Google Flow.
Judul adegan: "{scene_title or 'Adegan'}"
Alasan penolakan dari Google: "{rejection_reason or 'PUBLIC_ERROR_REPUTATIONAL'}"

PROMPT YANG DITOLAK:
\"\"\"{prompt_for_flow}\"\"\"

{POLICY_SAFE_RULES}

TUGAS ANDA:
Tulis ULANG prompt tersebut dalam Bahasa Inggris agar LOLOS filter, dengan syarat mutlak:
1. PERTAHANKAN: seluruh nama karakter beserta Seed ID-nya, sudut & gerakan kamera, jenis lensa,
   color grading, tata cahaya, lokasi umum, dan inti dramatis adegan.
2. PERTAHANKAN dialog bahasa asli/lokal yang dikutip (jika ada) — boleh diperhalus kalimatnya,
   tetapi TETAP dalam bahasa tersebut, jangan diterjemahkan ke Inggris.
3. GANTI hanya elemen yang melanggar aturan di atas dengan padanan fiktif/netral.
4. Jangan menambah adegan baru, jangan mengubah jumlah karakter.

OUTPUT WAJIB FORMAT JSON VALID (tanpa teks lain di luar JSON):
{{
  "revised_prompt": "Prompt video 10 detik versi baru dalam Bahasa Inggris yang aman dari filter",
  "changes": "Ringkasan singkat Bahasa Indonesia: apa yang diganti dan jadi apa"
}}
"""

    try:
        result = generate_text(prompt, json_output=True)
        parsed = json.loads(_extract_json_text(result.text))
        revised = (parsed.get("revised_prompt") or "").strip()
        if revised:
            log.info("Prompt adegan berhasil ditulis ulang via %s (%s).", result.provider, result.model)
            return revised
    except Exception as ex:
        log.warning("Sanitasi prompt via provider AI gagal: %s", ex)

    web_txt = _call_web2api(prompt)
    if web_txt:
        try:
            parsed = json.loads(_extract_json_text(web_txt))
            revised = (parsed.get("revised_prompt") or "").strip()
            if revised:
                log.info("Prompt adegan ditulis ulang via fallback Web2API. Perubahan: %s", parsed.get("changes", "-"))
                return revised
        except Exception as ex:
            log.warning("Fallback Web2API mengembalikan JSON sanitasi tidak valid: %s", ex)

    return None


def _extract_json_text(raw: str) -> str:
    """Strip the markdown fences Gemini usually wraps JSON in."""
    txt = (raw or "").strip()
    if "```json" in txt:
        return txt.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in txt:
        return txt.split("```", 1)[1].split("```", 1)[0].strip()
    return txt


def _call_web2api(prompt_text: str, dropped_images: int = 0) -> Optional[str]:
    """Generate text via a local gemini-web2api bridge once every API key is exhausted.

    The bridge exposes an OpenAI-compatible endpoint backed by a signed-in
    gemini.google.com session, so it needs no API key and burns no quota. It cannot
    accept images, so reference pictures are dropped on this path — callers pass
    `dropped_images` so the loss is reported instead of silently ignored.
    """
    cfg = settings.get_settings()
    if not cfg.get("enable_web2api_fallback"):
        return None

    base_url = (cfg.get("web2api_base_url") or "").strip().rstrip("/")
    if not base_url:
        log.warning("Fallback Web2API aktif tetapi web2api_base_url kosong.")
        return None

    if dropped_images:
        log.warning(
            "Fallback Web2API tidak mendukung input gambar: %d gambar referensi diabaikan. "
            "Storyboard akan dirancang dari teks premis saja.", dropped_images
        )

    headers = {"Content-Type": "application/json"}
    token = (cfg.get("web2api_api_key") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    model_name = cfg.get("web2api_model") or "gemini-2.5-flash"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt_text}],
        "stream": False,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions", json=payload, headers=headers, timeout=WEB2API_TIMEOUT
        )
    except Exception as ex:
        log.warning("Fallback Web2API tidak dapat dihubungi di %s: %s", base_url, ex)
        return None

    if resp.status_code != 200:
        log.warning("Fallback Web2API menolak request (HTTP %s): %s", resp.status_code, resp.text[:300])
        return None

    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as ex:
        log.warning("Fallback Web2API mengembalikan format tak terduga: %s", ex)
        return None

    if not (content or "").strip():
        log.warning("Fallback Web2API mengembalikan jawaban kosong.")
        return None

    log.info("Teks berhasil dihasilkan via fallback Web2API (model %s).", model_name)
    return content


DRACIN_THEME_POOL = [
    "CEO Menyamar Jadi Karyawan Biasa",
    "Mertua Jahat vs Menantu Sabar",
    "Putri Tertukar Sejak Lahir",
    "Istri Berkhianat, Suami Bangkit Balas Dendam",
    "Suami Pura-Pura Miskin, Ternyata Konglomerat",
    "Diusir dari Rumah, Kembali Jadi Pewaris Kaya Raya",
    "Anak Sambung Dihina, Ternyata Anak Kandung Pengusaha",
    "Perjodohan Paksa Berujung Cinta Sejati",
    "Sopir Pribadi Ternyata Pemilik Perusahaan",
    "Direhabilitasi Keluarga Setelah Difitnah",
    "Janda Muda Dihina Keluarga Mantan Suami, Ternyata CEO Rahasia",
    "Pembantu Rumah Tangga Ternyata Pewaris Tunggal",
    "Kembaran Jahat Menukar Identitas demi Warisan",
    "Suami Kontrak Jatuh Cinta Sungguhan",
    "Anak Durhaka Menyesal Setelah Orang Tua Sukses Kembali",
]


def build_local_realism_rules(target_country: str = "") -> str:
    """Build instruction block that forces skin tone, wardrobe, environment, names, and language to match a target country/local audience."""
    country = (target_country or "").strip()
    if not country:
        return ""
    return f"""
ATURAN WAJIB REALISME LOKAL / TARGET NEGARA: "{country}"
1. **Skin Tone & Etnisitas**: Seluruh karakter WAJIB memiliki warna kulit, fitur wajah, dan ciri etnis yang sesuai populasi asli "{country}" — JANGAN gunakan skin tone/fitur wajah Kaukasia/Barat kecuali karakter tersebut memang secara eksplisit dideskripsikan sebagai warga asing/ekspatriat dalam premis cerita.
2. **Gaya Busana & Wardrobe**: Pakaian, aksesoris, dan gaya rambut karakter WAJIB mencerminkan budaya/fashion sehari-hari masyarakat "{country}" (baik gaya kasual, formal kantoran, hingga mewah), bukan gaya Barat generik.
3. **Lingkungan & Set Lokasi**: Latar tempat (rumah, jalanan, kantor, kendaraan, signage, interior) WAJIB terlihat autentik seperti kondisi nyata di "{country}" — arsitektur, dekorasi, dan detail lingkungan lokal, bukan skyline/interior ala Amerika/Eropa generik.
4. **Nama Karakter**: Gunakan nama-nama yang lazim dan natural dipakai di "{country}", bukan nama Barat (contoh: hindari "Julian Mercer", "Elena Rostova" — gunakan nama yang umum di "{country}").
5. **Realita Sosial "Merakyat"**: Premis, konflik, dan detail kehidupan sehari-hari (makanan, transportasi, kebiasaan, dialog) WAJIB terasa dekat dengan realita masyarakat "{country}" sehari-hari, bukan fantasi hidup mewah generik ala Hollywood yang tidak membumi.
6. Setiap `prompt_for_flow` WAJIB tetap menyisipkan deskripsi fisik/etnis & wardrobe lokal ini secara eksplisit dalam Bahasa Inggris (sesuaikan dengan etnis mayoritas di {country}, misal jika negara target adalah Jepang: "East Asian Japanese woman, fair skin tone, wearing minimalist modern office wear...").
7. **Bahasa Suara/Dialog Video**: Kalau karakter berbicara di adegan, dialognya WAJIB diucapkan dalam bahasa asli "{country}" (bukan Inggris) — kutip langsung dialognya di dalam `prompt_for_flow` sesuai format yang dijelaskan di aturan Dynamic Multi-Angle Camera. Jangan biarkan Google Flow menghasilkan suara berbahasa Inggris untuk konten yang menyasar penonton "{country}".
"""


def auto_suggest_details(theme: str = "", microdrama_mode: bool = False, target_country: str = "", dracin_theme: str = "") -> Dict[str, Any]:
    """Auto-suggest character matrix, creative cinematic premise, and seeds using Gemini AI."""
    seed_main = random.randint(100000, 999999)
    seed_2 = random.randint(100000, 999999)
    seed_3 = random.randint(100000, 999999)

    user_prompt = f"""TEMA UTAMA PENGGUNA (WAJIB DIIKUTI SECARA KETAT & SETIA): "{theme}"

PETUNJUK BAHASA & TEMA:
1. Pahami tema dari pengguna dalam BAHASA APAPUN (Bahasa Indonesia, Inggris, Arab, Jepang, dll).
2. Anda HARUS merancang cerita yang 100% SESUAI DENGAN TEMA TERSEBUT. Jangan pernah membelokkan tema (Misal: Jika pengguna memasukkan tentang 'Bahaya Rokok', WAJIB merancang film drama medis/sosial sinematik tentang bahaya merokok dan dampaknya, BUKAN sci-fi alien/cyberpunk yang tidak relevan).
3. Berikan `suggested_premise` dan `suggested_character` dalam bahasa yang sama dengan input pengguna (jika Bahasa Indonesia, tulis Bahasa Indonesia yang kaya & dramatis).""" if theme.strip() else "Buatkan sebuah konsep cerita film sinematik original yang sangat spektakuler, emosional, penuh plot twist dan visual memukau."

    dracin_theme_instruction = f"""
TEMA DRACIN WAJIB DIPAKAI: "{dracin_theme}"
Rancang cerita mengikuti premis tema dracin populer ini secara 100% setia, jangan menyimpang ke tema lain.""" if dracin_theme.strip() else f"""
PILIH SATU TEMA DRACIN POPULER BERIKUT (yang paling relate dengan tema/premis pengguna jika ada, atau pilih bebas jika premis kosong):
{chr(10).join('- ' + t for t in DRACIN_THEME_POOL)}"""

    local_realism_instruction = build_local_realism_rules(target_country)

    if microdrama_mode:
        prompt = f"""
Anda adalah Microdrama Production AI (Story Brain, Cinematic Director, Prompt Packager, & Quality Assurance Auditor).
Tugas Anda adalah merancang KONSEP SHORT-FORM VERTICAL MICRODRAMA / DRACIN (3 EPISODE ARC FORMULA) yang sangat adiktif, dramatis, dan emosional (berdasarkan Master System Prompt Production AI):

CORE MICRODRAMA STYLE:
- Dramatic, Emotional, Fast-paced, Curiosity-driven, Addictive, Subtitle-friendly, Suitable for Vertical Platforms (9:16).
- Berfokus pada: Injustice, betrayal, rejection, status reversal (penghinaan -> pembalasan), hidden secrets, dan emotional payoff yang memuaskan penonton.
{dracin_theme_instruction}
{local_realism_instruction}

{user_prompt}

WAJIB RANCANG DENGAN FORMULA 3 EPISODE MICRODRAMA ARCHITECTURE:
- Paragraf 1 (Episode 1 - Hook and Humiliation): Introduce protagonist, establish injustice, show humiliation/rejection/loss, end with a mystery/cliffhanger.
- Paragraf 2 (Episode 2 - Conflict and Mystery): Increase pressure, reveal new information, antagonist appears stronger, protagonist hides a secret, end with a major clue or reversal.
- Paragraf 3 (Episode 3 - Reveal, Accountability, and Payoff): Reveal the truth, reverse the power dynamic (status reversal), hold antagonist accountable, deliver memorable emotional payoff victory.

OUTPUT WAJIB FORMAT JSON VALID (Tanpa teks tambahan di luar JSON):
{{
  "suggested_premise": "Episode 1 (Hook & Humiliation): ...\\n\\nEpisode 2 (Conflict & Mystery): ...\\n\\nEpisode 3 (Reveal & Payoff): ...",
  "suggested_character": "Karakter 1 - [Nama Protagonis] (Seed {seed_main}): [Deskripsi rupa & pakaian].\\nKarakter 2 - [Nama Antagonis] (Seed {seed_2}): [Deskripsi rupa & pakaian].\\nKarakter 3 - [Nama Pendukung] (Seed {seed_3}): [Deskripsi rupa & pakaian].",
  "character_seed": {seed_main}
}}
"""
    else:
        prompt = f"""
Anda adalah Sutradara & Head Storywriter Hollywood Berprestasi Internasional.
Tugas Anda adalah merancang KONSEP PREMIS FILM SINEMATIK YANG SANGAT KREATIF DAN 100% RELEVAN DENGAN TEMA USER (2-3 Paragraf Detail):
{local_realism_instruction}

{user_prompt}

WAJIB RANCANG DENGAN DETAIL DAN RELEVAN:
1. **Premis Cerita Epik & Relevan (2-3 Paragraf Lengkap)**:
   - Paragraf 1: Latar dunia sinematik, atmosfer visual, tokoh utama, dan peristiwa pemicu konflik yang relevan dengan tema.
   - Paragraf 2: Perjalanan dan pencarian, tantangan terbesar/misteri, serta titik balik klimaks sinematik.
2. **Matrix Karakter Detail**:
   - Daftarkan 2 s/d 4 Karakter dengan Nama, Usia, Peran, Ciri Fisik Spesifik, Jubah/Pakaian, dan Seed ID unik (Tokoh 1 Seed {seed_main}, Tokoh 2 Seed {seed_2}, Tokoh 3 Seed {seed_3}).

OUTPUT WAJIB FORMAT JSON VALID (Tanpa teks tambahan di luar JSON):
{{
  "suggested_premise": "Paragraf 1 latar & peristiwa pemicu epik...\\n\\nParagraf 2 perjalanan, misteri, & klimaks sinematik...",
  "suggested_character": "Karakter 1 - [Nama] (Seed {seed_main}): [Deskripsi rupa & pakaian].\\nKarakter 2 - [Nama] (Seed {seed_2}): [Deskripsi rupa & pakaian].\\nKarakter 3 - [Nama] (Seed {seed_3}): [Deskripsi rupa & pakaian].",
  "character_seed": {seed_main}
}}
"""

    try:
        result = generate_text(prompt, json_output=True)
        parsed = json.loads(_extract_json_text(result.text))
        if parsed.get("suggested_premise"):
            parsed["generated_via"] = result.provider
            return parsed
    except Exception as ex:
        log.warning("Auto-suggest provider AI gagal: %s", ex)

    # Every API key is spent — try the local web2api bridge before the canned concept.
    web_txt = _call_web2api(prompt)
    if web_txt:
        try:
            parsed = json.loads(_extract_json_text(web_txt))
            if parsed.get("suggested_premise"):
                log.info("Auto-suggest berhasil via fallback Web2API!")
                return parsed
        except Exception as ex:
            log.warning("Fallback Web2API mengembalikan JSON auto-suggest tidak valid: %s", ex)

    # Fail-safe rich concept generator if quota is momentarily exhausted
    log.warning("Menjalankan fail-safe rich concept generator karena API key rate-limited...")
    r_seed = random.randint(100000, 999999)
    r_seed2 = random.randint(100000, 999999)
    r_seed3 = random.randint(100000, 999999)
    base_theme = theme if theme.strip() else "Petualangan Penjelajah Angkasa di Peradaban Kuno Berpantulan Kristal Neon"
    fallback_premise = f"Di lanskap sinematik bertema {base_theme}, sebuah perjalanan epik dimulai saat dua tokoh utama menemukan petunjuk kuno yang tersimpan di puncak perbatasan dua samudera. Perjalanan ini menguji keberanian, kesetiaan, dan takdir spiritual yang selama ini tersembunyi di balik kabut legenda.\n\nDalam atmosfer mistis penuh kilauan cahaya sinematik dan debu kosmik, para tokoh berhadapan dengan misteri kuno dan keputusan besar yang akan mengubah takdir peradaban mereka selamanya."
    return {
        "suggested_premise": fallback_premise,
        "suggested_character": f"Tokoh 1 - Utama (Seed {r_seed}): Sosok karismatik berpakaian jubah linen sinematik kuno.\nTokoh 2 - Pendamping (Seed {r_seed2}): Pemuda pembawa obor bertengger jubah perak.\nTokoh 3 - Penjaga Kuno (Seed {r_seed3}): Sosok bijak bermata zamrud berpakaian hijau gelap.",
        "character_seed": r_seed
    }


def generate_youtube_metadata(film_title: str, premise: str) -> Dict[str, Any]:
    """Generate readable, keyword-led YouTube metadata with theme-aware hashtags."""
    prompt = f"""
Anda adalah YouTube SEO Specialist & Content Strategist Terkemuka.
Berdasarkan judul film "{film_title}" dan premis cerita: "{premise}", rancangkan kit publikasi YouTube lengkap:

1. **3 Pilihan Judul SEO Natural (Ideal 60-90 Karakter termasuk hashtag)**:
   - Gunakan kapitalisasi normal yang nyaman dibaca; DILARANG menulis seluruh judul dengan HURUF KAPITAL.
   - Letakkan keyword pencarian utama dekat awal judul, lalu tambahkan hook spesifik yang menarik tanpa terasa spam.
   - Wajib akhiri setiap judul dengan 1-2 hashtag populer yang benar-benar relevan dengan tema/karakter video.
2. **Deskripsi YouTube (3 Paragraf Struktur Rapi)**:
   - Paragraf 1: Hook pembuka & rangkuman cerita film.
   - Paragraf 2: Penjelasan teknologi AI sinematik yang digunakan.
   - Paragraf 3: Target penonton & ajakan.
   - Diakhiri dengan Call to Action (CTA Subscribe & Like) dan 5 Hashtag relevan.
3. **Prompt Thumbnail YouTube (Midjourney/Flux/Flow Prompt Bahasa Inggris)**:
   - Deskripsi visual thumbnail resolusi tinggi 16:9 yang eye-catching dengan teks bercahaya.
4. **10 Tag Kata Kunci Long-Tail**:
   - 10 frase kata kunci (3-4 kata) yang dipisahkan oleh koma.

OUTPUT WAJIB FORMAT JSON VALID:
{{
  "titles": [
    "Judul SEO natural 1 #TemaUtama #Karakter",
    "Judul SEO natural 2 #TemaUtama #Karakter",
    "Judul SEO natural 3 #TemaUtama #Karakter"
  ],
  "description": "Paragraf 1...\\n\\nParagraf 2...\\n\\nParagraf 3...\\n\\n👉 Subscribe & Like...\\n\\n#Hashtag1 #Hashtag2",
  "thumbnail_prompt": "High-impact 16:9 YouTube thumbnail prompt in English...",
  "tags": "kata kunci 1, kata kunci 2, kata kunci 3, kata kunci 4, kata kunci 5, kata kunci 6, kata kunci 7, kata kunci 8, kata kunci 9, kata kunci 10"
}}
"""
    try:
        result = generate_text(prompt, json_output=True)
        parsed = json.loads(_extract_json_text(result.text))
        from .youtube_seo import normalize_seo_titles
        parsed["titles"] = normalize_seo_titles(parsed.get("titles"), film_title)
        parsed["generated_via"] = result.provider
        return parsed
    except Exception as ex:
        log.warning("Gagal generate metadata YouTube dari provider AI: %s", ex)
        web_txt = _call_web2api(prompt)
        if web_txt:
            try:
                parsed = json.loads(_extract_json_text(web_txt))
                if parsed.get("titles"):
                    from .youtube_seo import normalize_seo_titles
                    parsed["titles"] = normalize_seo_titles(parsed.get("titles"), film_title)
                    log.info("Metadata YouTube berhasil via fallback Web2API!")
                    return parsed
            except Exception as w_ex:
                log.warning("Fallback Web2API mengembalikan JSON metadata tidak valid: %s", w_ex)
        fallback = {
            "titles": [
                f"{film_title}: Pertarungan sinematik dengan alur paling menegangkan",
                f"{film_title}: Siapa yang akan memenangkan pertarungan luar biasa ini?",
                f"Saksikan {film_title}, kisah aksi sinematik yang penuh kejutan"
            ],
            "description": f"Saksikan film AI sinematik {film_title}. Cerita ini menceritakan tentang {premise}.\n\nDibuat secara otomatis menggunakan Gemini 3.6 Flash dan Google Flow Omni.\n\nJangan lupa Like, Comment, dan Subscribe untuk konten AI sinematik lainnya!\n\n#FilmAI #GoogleFlow #Gemini36Flash #AIVideoGenerator #TutorialAI",
            "thumbnail_prompt": f"Dramatic cinematic movie thumbnail for {film_title}, 16:9 aspect ratio, 8k resolution, glowing neon title text, highly detailed photorealistic character.",
            "tags": "cara buat film ai, tutorial google flow omni, generate video ai konsisten, karakter ai tetap konsisten, buat film ai 10 menit, gemini 36 flash storyboard, ai video generator gratis, tutorial ai sinematik indonesia, multi angle kamera ai, workflow otomatisasi film ai"
        }
        from .youtube_seo import normalize_seo_titles, theme_hashtags
        fallback["titles"] = normalize_seo_titles(fallback["titles"], film_title)
        fallback["description"] = fallback["description"].rsplit("\n\n", 1)[0] + "\n\n" + " ".join(theme_hashtags(film_title, limit=5))
        return fallback


def generate_storyboard(
    premise: str,
    image_paths: List[str] = None,
    scene_count: int = 4,
    aspect_ratio: str = "landscape",
    character_info: str = "",
    custom_instructions: str = "",
    character_seed: Optional[int] = None,
    microdrama_mode: bool = False,
    ugc_mode: bool = False,
    target_country: str = "",
    dracin_theme: str = "",
    target_total_duration: Optional[int] = None,
    fixed_scene_duration: Optional[int] = None,
    children_mode: bool = False,
    script_mode: bool = False,
    affiliate_config: Optional[Dict[str, Any]] = None,
    target_lang: str = "",
) -> Dict[str, Any]:
    """Generate multi-scene structured storyboard JSON using the configured AI providers."""

    image_paths = image_paths or []
    affiliate_config = dict(affiliate_config or {})
    scene_count = max(1, min(60, int(scene_count or 4)))
    cfg = settings.get_settings()
    seed = character_seed or random.randint(100000, 999999)

    # Load reference images for Gemini Vision analysis
    pil_images = []
    for p in image_paths:
        try:
            if Path(p).exists():
                pil_images.append(Image.open(p))
        except Exception as ex:
            log.warning("Gagal memuat gambar referensi %s: %s", p, ex)

    microdrama_rules = f"""
ATURAN SPECIAL MICRODRAMA PRODUCTION AI (MASTER SYSTEM PROMPT PDF):
1. **Vertical Short-Form 3-Episode Arc Formula**:
   - Adegan Awal: Episode 1 Hook & Humiliation (Injustice, Betrayal, Loss, Cliffhanger).
   - Adegan Tengah: Episode 2 Conflict & Mystery (Pressure Increases, Antagonist Stronger, Protagonist Secret).
   - Adegan Akhir: Episode 3 Reveal, Accountability & Payoff (Status Reversal, Antagonist Accountable, Emotional Victory).
2. **Core Microdrama Style**: Dramatic, Emotional, Fast-paced, Curiosity-driven, Addictive, Subtitle-friendly.
3. **Advanced Continuity Lock**: Wajib mempertahankan posisi karakter, pakaian, gaya rambut, aksesoris, dan lighting antar adegan!
4. **Negative Constraints**: No character redesign, no wardrobe change, no extra limbs, no unreadable lip movement.
5. **Tema Dracin**: {dracin_theme.strip() or f"Pilih salah satu tema dracin populer paling relate berikut: {', '.join(DRACIN_THEME_POOL)}"}
""" if microdrama_mode else ""

    ugc_rules = f"""
ATURAN TEMPLATE PROMPT STORYBOARD VIDEO UGC AESTHETIC SANGAT MAHAL:
1. **Jumlah Adegan Mengikuti Input Pengguna (WAJIB TEPAT {scene_count} Scene)**:
   - Buat persis {scene_count} objek di array `scenes`; dilarang mengurangi menjadi 3–4 scene.
   - Setiap scene adalah satu video tersendiri dengan durasi yang dipilih pengguna. Bagikan alur cerita
     secara mulus ke seluruh {scene_count} scene tanpa mempercepat atau melompati perkembangan cerita.

2. **Kesan Sinematik SANGAT MAHAL & EKSKLUSIF (High-End Luxury Vibe)**:
   - Master Style Wajib: `cinematic UGC aesthetic, clean infographic storyboard, TikTok/Reels format, premium lifestyle photography, realistic lighting, smooth scene transition, consistent character face, ultra detailed, soft depth of field, modern luxury atmosphere, camera iPhone 16 Pro cinematic quality`.
   - Sentuhan Kemewahan ("Mahal"): Sertakan detail arsitektur penthouse/mansion modern mewah, lantai marmer reflektif, lampu gantung kristal, perabotan desainer, tekstur kain sutra/linen halus, dan pencahayaan studio alami yang sangat elegan.

3. **Smart Aesthetic Add-On (Disesuaikan 100% dengan Tema Cerita)**:
   - Girly Aesthetic Add-On (`pastel aesthetic, luxury lifestyle mood, cinematic bokeh lights, realistic skin texture, soft shadows, glossy lighting, premium social media content, smooth motion blur, high fashion composition, realistic environment details`) HANYA dipakai jika temanya sesuai (misal: beauty, girly, baking, skincare, cute morning routine).
   - Untuk tema lain, gunakan add-on aesthetic yang 100% RELEVAN (misal: `corporate executive luxury, sleek architectural interior, modern professional mood, sharp 8k detail` untuk Working Girl; `scenic vacation aesthetic, vibrant golden hour, luxury travel vibe` untuk Travel Vlog; `modest elegant aesthetic, warm ambient lighting, peaceful spiritual atmosphere` untuk Muslimah Lifestyle).
   - Pilihan Add-On harus selalu serasi dengan konteks cerita agar kesan visualnya tetap terasa MAHAL dan natural.

4. **Text Overlay Aesthetic**: Sertakan field "text_overlay" (Bahasa {target_lang} pendek ala TikTok/Reels caption, max 6 kata) untuk setiap adegan.
5. **Karakter Utama**: karakter utama wanita/pria dengan rupa & seed konsisten, outfit sesuai aktivitas, ekspresi natural candid, luxury lifestyle aesthetic.
""" if ugc_mode else ""

    children_visual_rules = """
GAYA VISUAL WAJIB (MODE CERITA ANAK):
Setiap `prompt_for_flow` WAJIB diawali/menyisipkan gaya ini: soft 3D cartoon animation, preschool
animated series style, cute anthropomorphic animal characters, big friendly eyes, rounded chunky
proportions, bright cheerful colours, soft even lighting, simple readable background, wholesome happy mood.
DILARANG: photorealistic, cinematic chiaroscuro, dark moody lighting, harsh shadows, film grain,
anamorphic lens, teal-and-orange grading, human child characters.
`shot_type` cukup sederhana (Wide Shot / Medium Shot / Close Up) dan gerakan kamera lembut & pelan.
""" if children_mode else ""
    action_density_rules = CHILDREN_ACTION_RULES if children_mode else ADULT_ACTION_RULES
    local_realism_rules = build_local_realism_rules(target_country) if target_country else ""
    target_lang = target_lang or "Indonesia"

    script_mode_rules = f"""
MODE SCRIPT SENDIRI — FORMATTER TEKNIS SAJA (PRIORITAS TERTINGGI):
Naskah di bawah adalah karya final pengguna. DILARANG mengubah alur, dialog, urutan kejadian,
hubungan karakter, twist, lokasi, atau akhir cerita. Jangan menambah konflik, tokoh, dialog,
kejadian, maupun ending baru. Tugas Anda HANYA:
1. Membagi naskah secara berurutan menjadi tepat {scene_count} scene render.
2. Menyalin dialog asli secara VERBATIM ke field `dialogue` dan `prompt_for_flow`.
3. Mengubah arahan visual menjadi prompt teknis Bahasa Inggris untuk Google Flow—kamera, blocking,
   pencahayaan, kontinuitas, dan durasi—tanpa menulis ulang isi cerita.
4. Jika satu bagian terlalu panjang, pecah secara kronologis; jangan meringkas atau membuang kejadian.

NASKAH ASLI YANG WAJIB DIPERTAHANKAN:
--- MULAI NASKAH ---
{premise}
--- SELESAI NASKAH ---
""" if script_mode else ""

    affiliate_rules = f"""
MODE ADEGAN AFFILIATE OPSIONAL (WAJIB MENYATU DENGAN CERITA):
- Produk: {affiliate_config.get('name') or 'Produk pengguna'}
- Manfaat: {affiliate_config.get('benefits') or '-'}
- CTA: {affiliate_config.get('cta') or '-'}
- Gaya promosi: {affiliate_config.get('style') or 'soft_selling'}
- Posisi: {affiliate_config.get('scene_position') or 'auto di tengah cerita'}
Integrasikan produk sebagai properti/aktivitas/solusi yang logis dalam konflik yang sedang berlangsung;
tidak boleh terasa seperti iklan yang ditempel. Produk tidak boleh mengubah plot utama, hubungan karakter,
twist, atau ending. Scene sebelum affiliate harus mengantar penggunaannya dan scene setelahnya wajib
melanjutkan konflik utama. Tandai HANYA scene promosi dengan `"affiliate_scene": true`; scene lain false.
Pertahankan bentuk, kemasan, warna, label, dan proporsi produk dari gambar referensi yang dilampirkan.
""" if affiliate_config.get("enabled") else ""

    if fixed_scene_duration:
        # User asked for one fixed clip length, so the film length stays predictable:
        # scene_count x fixed_scene_duration.
        fixed = int(fixed_scene_duration)
        duration_rules = f"""ATURAN DURASI PER ADEGAN (WAJIB):
1. SELURUH adegan WAJIB memakai "duration" yang SAMA, yaitu tepat **{fixed} detik**. Tanpa kecuali.
   Jangan memvariasikan durasi antar adegan pada mode ini.
2. Total durasi film = {scene_count} adegan x {fixed} detik = **{scene_count * fixed} detik**.
3. Isi setiap adegan supaya benar-benar PENUH selama {fixed} detik: rancang aksi bertingkat
   (aksi awal -> perkembangan -> titik balik) agar tidak ada waktu kosong atau gerakan mengambang.
   Untuk durasi 10 detik tulis eksplisit: 0-3 detik aksi pertama, 3-7 detik counter-action/dialog balasan,
   7-10 detik reveal/keputusan/impact. Jika ada percakapan, wajib sedikitnya dua giliran bicara pendek.
4. Panjang narasi/dialog menyesuaikan {fixed} detik (patokan: sekitar {int(fixed * 2.8)}-{int(fixed * 3.2)} kata).
5. Awali `prompt_for_flow` dengan frasa: A {fixed}-second ...
"""
    else:
        # Varied pacing averages ~7s per scene, so a target total is only reachable inside
        # [scene_count x 4, scene_count x 10]. Clamp it instead of asking for the impossible.
        budget_rule = ""
        if target_total_duration:
            lo, hi = scene_count * 4, scene_count * 10
            budget = max(lo, min(int(target_total_duration), hi))
            budget_rule = f"""
6. **TARGET TOTAL DURASI (WAJIB DIPENUHI)**: Jumlah seluruh nilai "duration" dari {scene_count} adegan
   HARUS menghasilkan total **{budget} detik** (toleransi maksimal +-4 detik).
   Sebelum menutup JSON, JUMLAHKAN dulu semua "duration" dan pastikan hasilnya {budget}.
   Rata-rata per adegan di target ini sekitar {budget / scene_count:.1f} detik."""
        duration_rules = f"""ATURAN DURASI PER ADEGAN (WAJIB — INI MENENTUKAN RITME FILM):
1. Setiap adegan WAJIB mengisi "duration" dengan SALAH SATU angka ini saja: 4, 6, 8, atau 10 (detik).
   Google Flow HANYA mendukung 4 nilai tersebut; angka lain (3, 5, 7, 12) akan ditolak sistem.
2. Tentukan durasi dari BOBOT NARATIF adegan, jangan disamaratakan:
   - **4 detik** -> potongan cepat: hook, reaksi kaget, cutaway detail benda, punchline, cliffhanger.
   - **6 detik** -> aksi ringkas: dialog satu kalimat, perpindahan tempat, penegasan ekspresi.
   - **8 detik** -> adegan berisi: dialog dua arah, pengungkapan informasi, eskalasi konflik.
   - **10 detik** -> HANYA untuk muatan dramatis terberat: klimaks, konfrontasi penuh, pengungkapan rahasia.
     Durasi 10 detik BUKAN alasan memperlambat — justru harus memuat aksi paling padat.
3. VARIASIKAN ritmenya; jangan semua adegan sama panjang.
4. Panjang narasi/dialog proporsional: 4 detik ~8-10 kata, 6 detik ~12-15, 8 detik ~18-22, 10 detik ~25-30.
5. Awali `prompt_for_flow` dengan durasi yang sesuai (contoh: "A 4-second ...", "A 8-second ...").{budget_rule}"""

    elegant_rules = """
6. **Premium "Elegant & Expensive" Production Value (Wajib di Setiap Scene)**: Ini yang membedakan hasil murahan vs High-End Studio Look. Setiap `prompt_for_flow` WAJIB menyisipkan minimal 3 elemen berikut secara eksplisit:
   - **Lensa Sinema**: sebutkan jenis lensa spesifik (misal `35mm anamorphic lens`, `85mm portrait lens, shallow depth of field`, `24mm wide-angle establishing lens`) — jangan generik.
   - **Color Grading Premium**: sebutkan gaya grading (misal `teal-and-orange cinematic color grade`, `desaturated Nordic noir palette`, `warm cinematic color grade`, `high-contrast chiaroscuro`).
   - **Production & Costume Design Detail**: sebutkan tekstur kain, material, detail set/prop mewah (misal `heavy embroidered silk fabric catching light`, `polished marble floor reflections`, `aged brass ornamental details`) — bukan cuma "baju bagus".
   - **Lighting Setup Sinematik Bernama**: gunakan istilah tata cahaya profesional (misal `Rembrandt lighting`, `three-point studio lighting`, `volumetric god-rays`, `soft rim-light backlighting silhouette`).
   - Hindari kata generik murahan seperti "beautiful", "high quality", "detailed" tanpa spesifik teknis di atas.
""" if not ugc_mode and not children_mode else ""

    system_prompt = f"""
Anda adalah Sutradara Film AI Sinematik Kelas Dunia & Visual Director untuk Google Flow Omni Flash.
Tugas Anda adalah meracik **STORYBOARD SINEMATIK KONSISTEN BANYAK KARAKTER & DYNAMIC MULTI-ANGLE CAMERA ({scene_count} ADEGAN/SCENE)**.

BAHASA OUTPUT UTAMA: {target_lang} (Semua ringkasan aksi, narasi voiceover, teks overlay, dan dialog WAJIB DITULIS DALAM BAHASA {target_lang} SECARA MUTLAK, MESKIPUN PREMIS AWAL DALAM BAHASA LAIN!)

{duration_rules}

{action_density_rules}

{microdrama_rules}
{ugc_rules}
{local_realism_rules}
{POLICY_SAFE_RULES}
{children_visual_rules}
{script_mode_rules}
{affiliate_rules}

ATURAN UTAMA DYNAMIC MULTI-ANGLE & MULTI-CHARACTER STABILITY:
1. **Multi-Character Seed Matrix (Wajib)**: Dukung sampai 10 karakter berbeda dengan menyebutkan Seed ID unik masing-masing (misal: Main Hero Seed `{seed}`, Companion Seed `{seed+101}`, Rival Seed `{seed+202}`). Pertahankan ciri visual wajah dan baju di setiap adegan!
2. **Dynamic Multi-Angle Camera Choreography (Wajib 100% Variatif Di Setiap Scene)**:
   - WAJIB gunakan sudut & gerakan kamera yang BERBEDA-BEDA untuk SETIAP adegan!
   - Rotasi bervariasi: `Wide Master Establishing Tracking Shot`, `Extreme Low-Angle Dynamic Hero Shot`, `Over-the-Shoulder (OTS) Medium Close-Up`, `High-Angle Birdseye Drone View`, `Dutch-Angle High Action Tracking`, `Slow Push-in Tight Close-Up`.
   - Di dalam `prompt_for_flow` SETIAP adegan, WAJIB secara eksplisit diawali dengan klausa tipe kamera sinematik tersebut! (contoh: "A 10-second Over-The-Shoulder Close-Up Shot...", "A 10-second Low Angle Dynamic Tracking Shot...").
3. **Seamless Visual Continuation Antarvideo (Wajib)**: Adegan $N+1$ melanjutkan posisi fisik, properti,
   pakaian, waktu, dan lokasi logis dari adegan $N$. Susun lokasi dalam blok 2-4 adegan berurutan; jangan
   memindahkan tokoh bolak-balik ke lokasi jauh pada setiap adegan. Jika cerita memang harus pindah lokasi,
   adegan sebelum/sesudahnya WAJIB menunjukkan jembatan visual yang masuk akal (keluar pintu, masuk kendaraan,
   tiba di lobi/gerbang), bukan teleportasi atau lompatan waktu mendadak.
3a. **Tiga Sampai Lima Shot Dalam Satu Video 10 Detik**: Pilih berdasarkan isi, bukan acak buta: 3 shot
   untuk dialog/emosi (0-3.3s, 3.3-6.6s, 6.6-10s), 4 shot untuk drama normal (0-2.5s, 2.5-5s,
   5-7.5s, 7.5-10s), dan 5 shot untuk aksi/perang/kejaran/konflik cepat (0-2s, 2-4s, 4-6s, 6-8s,
   8-10s). Semua shot adalah sudut kamera berbeda dari SATU kejadian berantai di SATU lokasi dan waktu
   kontinu—bukan adegan cerita terpisah. Setiap beat wajib mengandung minimal dua aksi fisik terkait.
4. **Flow Prompt Professional**: Setiap `prompt_for_flow` ditulis dalam Bahasa Inggris yang murni visual, mendetail (Karakter & Seed IDs + Multi-Angle Camera Shot + Aksi Tokoh + Studio 8K Lighting).
4a. **AKSI HARUS TERJADI DI DALAM KLIP (Wajib)**: `prompt_for_flow` WAJIB mendeskripsikan gerakan yang benar-benar
   berlangsung selama klip, bukan pose diam atau tablo. Tuliskan progresi jelas memakai penanda urutan waktu
   seperti "begins by...", "then...", "and finally..." sehingga terlihat perubahan dari awal ke akhir klip.
   Contoh BENAR: "begins gripping the envelope, then slams it onto the table, and finally turns away in tears."
   Contoh SALAH: "stands in the ballroom looking sad" (statis, tidak ada perubahan — DILARANG).
   Sertakan kata kerja gerak eksplisit (slams, snatches, shoves, storms out, collapses, spins around, lunges). Jika UGC Mode aktif, akhiri prompt dengan Aesthetic Add-On yang 100% cocok dengan tema (Girly/Pastel untuk Beauty, Corporate Luxury untuk Working Girl, Travel Vacation untuk Travel, dll.).
4b. **BAHASA AUDIO/DIALOG VIDEO (WAJIB)**: Jika karakter berbicara, WAJIB tulis dialog ASLI dalam bahasa {target_lang} di dalam `prompt_for_flow`. (TERJEMAHKAN KE {target_lang} SECARA MUTLAK!).
4c. **Tanpa Logo/Watermark (Wajib)**: Dilarang ada logo/watermark di `prompt_for_flow`.
5. **Time Range Timestamp Wajib**: Sertakan field "time_range".
6. **ATURAN MUTLAK BAHASA OUTPUT**: SELURUH ACTION SUMMARY, NARRATION, TEXT OVERLAY, DAN NAMA KARAKTER HARUS 100% DALAM BAHASA {target_lang} DAN BERGAYA NEGARA {target_country or target_lang}. JANGAN GUNAKAN NAMA INDONESIA ATAU TEKS INDONESIA SAMA SEKALI, MESKIPUN PREMISNYA INDONESIA! TRANSLATE EVERYTHING TO {target_lang}!
{elegant_rules}

PARAMETIK REQUEST (WAJIB 100% PATUH & RELEVAN):
- Tema / Premis Utama: {premise}
- ATURAN KHUSUS TEMA: SELURUH adegan HARUS 100% menceritakan premis di atas!
- Jumlah Adegan: {scene_count} scene
- Character Seed Main: {seed}
- Deskripsi Karakter: {character_info or "Otomatis rancang karakter-karakter yang 100% cocok dengan tema"}
- Catatan Tambahan: {custom_instructions or "Tidak ada"}

7. **Character Registry (Wajib)**: Daftarkan SETIAP karakter yang muncul. WAJIB GUNAKAN NAMA LOKAL NEGARA {target_country or target_lang} UNTUK NAMA MEREKA. JIKA PREMIS MEMAKAI NAMA INDONESIA (MISAL SINTA/RATNA/BUDI) TAPI TARGET BUKAN INDONESIA, ANDA WAJIB MENGGANTINYA MENJADI NAMA {target_country or target_lang}! Field "description" WAJIB sedetail mungkin...
   Field "visual_signature" WAJIB berisi kombinasi permanen yang unik dan mudah terlihat: warna/siluet pakaian,
   satu aksesori khas, serta rambut/usia/ciri wajah. Tidak boleh ada dua karakter dengan warna dominan,
   aksesori, siluet, dan ciri wajah yang mudah tertukar. Signature ini tidak boleh berubah antaradegan.
   Jika daftar aktor spesifik memberikan `source_actor_id`, salin ID tersebut PERSIS ke karakter yang sesuai;
   jangan menukar, menerjemahkan, atau mengarang ID baru.
8. **Character Tagging Per Adegan (Wajib)**: Di setiap scene, isi "characters_in_scene" dengan daftar "id" karakter.
9. **Speaker Lock (Wajib)**: Jika ada ucapan, isi array "dialogue" dengan speaker_id, kalimat persis, dan posisi
   layar. Hanya karakter tersebut yang boleh menggerakkan bibir saat kalimatnya; semua non-speaker menutup mulut
   dan hanya bereaksi secara fisik. Jangan pernah memindahkan dialog atau suara ke wajah lain.
10. **State Continuity (Wajib)**: Isi "start_state" dan "end_state" dengan posisi tubuh, tangan, properti,
   arah pandang, dan lokasi persis. start_state adegan N+1 harus melanjutkan end_state adegan N kecuali ada
   transisi visual eksplisit.

OUTPUT WAJIB FORMAT JSON VALID (Tanpa markdown tambahan di luar JSON):
{{
  "film_title": "Judul Film / Cerita",
  "genre_style": "Gaya Visual & Mood Sinematik",
  "art_direction": "Mood board produksi premium",
  "character_seed": {seed},
  "consistent_characters": "Deskripsi Lengkap Karakter-Karakter",
  "characters": [
    {{
      "id": 1,
      "name": "Nama Karakter",
      "source_actor_id": "ID aktor persis dari daftar aktor spesifik, atau kosong jika bukan aktor tersimpan",
      "seed": {seed},
      "description": "Deskripsi visual lengkap",
      "visual_signature": "Kombinasi pakaian, aksesori, rambut/usia/ciri wajah yang permanen dan unik"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "affiliate_scene": false,
      "time_range": "0:00–0:02",
      "title": "Judul Adegan 1 (misal Opening Activity)",
      "action_summary": "Ringkasan aksi adegan (WAJIB DITULIS DALAM BAHASA {target_lang} SECARA KESELURUHAN)",
      "shot_type": "Framing baku, pilih SATU: Extreme Wide Shot / Wide Shot / Medium Shot / Medium Close Up / Close Up / Extreme Close Up / Over-The-Shoulder / Point of View",
      "characters_in_scene": [1],
      "dialogue": [{{"speaker_id": 1, "line": "Kalimat persis", "screen_position": "left/center/right"}}],
      "start_state": "Posisi tubuh, tangan, properti, arah pandang, dan lokasi pada frame awal",
      "end_state": "Posisi tubuh, tangan, properti, arah pandang, dan lokasi pada frame akhir",
      "prompt_for_flow": "Detailed English video prompt for Google Flow ending with Girly Aesthetic Add-On: pastel aesthetic, luxury lifestyle mood, cinematic bokeh lights, realistic skin texture, soft shadows, glossy lighting, premium social media content, smooth motion blur, high fashion composition, realistic environment details",
      "text_overlay": "WAJIB DIISI di semua mode: teks overlay pendek (WAJIB DITULIS DALAM BAHASA {target_lang}, maks 6 kata) yang muncul di layar",
      "camera_movement": "Pergerakan kamera saja, terpisah dari shot_type (misal: Slow push-in, Handheld tracking, Static locked-off)",
      "lighting_mood": "Mood pencahayaan (misal: Soft natural lighting, cinematic bokeh lights)",
      "narration_id": "Teks Narasi Voiceover (WAJIB DITULIS DALAM BAHASA {target_lang}, JANGAN INDONESIA JIKA BUKAN INDONESIA)",
      "narration_en": "English Voiceover Narration Text",
      "duration": 4
    }}
  ]
}}
"""

    user_contents = [system_prompt, f"Ide Cerita / Tema: {premise}"]
    user_contents.extend(pil_images)

    affiliate_images = []
    for path in affiliate_config.get("reference_paths") or []:
        try:
            if Path(path).exists():
                affiliate_images.append(Image.open(path))
        except Exception as ex:
            log.warning("Gagal memuat referensi produk affiliate %s: %s", path, ex)
    if affiliate_images:
        user_contents.append("Gambar berikut adalah referensi produk affiliate, bukan referensi wajah karakter.")
        user_contents.extend(affiliate_images)

    last_err = None
    try:
        # Gemini receives reference images; OpenAI-compatible fallbacks retain the
        # complete textual direction when their adapter drops local PIL objects.
        result = generate_text(user_contents, json_output=True)
        text_resp = _extract_json_text(result.text)
        storyboard = json.loads(text_resp)
        actual_scene_count = len(storyboard.get("scenes") or [])
        if actual_scene_count != scene_count:
            raise ValueError(
                f"Provider menghasilkan {actual_scene_count} scene, seharusnya tepat {scene_count} scene."
            )
        storyboard["raw_response"] = text_resp
        storyboard["characters"] = ensure_unique_character_signatures(storyboard.get("characters") or [])
        storyboard["character_seed"] = seed
        storyboard["children_mode"] = children_mode
        storyboard["script_mode"] = script_mode
        if script_mode:
            storyboard["source_script"] = premise
        if affiliate_config.get("enabled"):
            storyboard["affiliate_product"] = affiliate_config
        storyboard["generated_via"] = result.provider
        storyboard["generated_model"] = result.model
        return storyboard
    except Exception as ex:
        last_err = ex
        log.warning("Semua provider cloud gagal membuat storyboard: %s", ex)

    # Every API key/model combination is spent — try the local web2api bridge before giving up.
    web_txt = _call_web2api("\n\n".join(str(c) for c in user_contents), dropped_images=len(pil_images))
    if web_txt:
        try:
            storyboard = json.loads(_extract_json_text(web_txt))
            actual_scene_count = len(storyboard.get("scenes") or [])
            if actual_scene_count != scene_count:
                raise ValueError(
                    f"Fallback menghasilkan {actual_scene_count} scene, seharusnya tepat {scene_count} scene."
                )
            storyboard["raw_response"] = web_txt
            storyboard["characters"] = ensure_unique_character_signatures(storyboard.get("characters") or [])
            storyboard["character_seed"] = seed
            storyboard["children_mode"] = children_mode
            storyboard["script_mode"] = script_mode
            if script_mode:
                storyboard["source_script"] = premise
            if affiliate_config.get("enabled"):
                storyboard["affiliate_product"] = affiliate_config
            storyboard["generated_via"] = "web2api_fallback"
            log.info("Storyboard berhasil dibuat via fallback Web2API (%d adegan, seed %d)!",
                     len(storyboard.get("scenes", [])), seed)
            return storyboard
        except Exception as ex:
            log.warning("Fallback Web2API mengembalikan JSON storyboard tidak valid: %s", ex)

    raise RuntimeError(f"Gagal generate storyboard dari seluruh provider AI: {last_err}")


def regenerate_single_scene(
    film_title: str,
    scene_number: int,
    scene_title: str,
    consistent_characters: str,
    genre_style: str,
    target_lang: str = "Indonesia"
) -> Dict[str, Any]:
    """Regenerate prompt and action for a single scene using configured providers."""
    target_lang = target_lang or "Indonesia"

    prompt = f"""
Anda adalah Sutradara Film AI Sinematik Kelas Dunia.
Rancangkan ULANG HANYA ADEGAN {scene_number} untuk film "{film_title}" dengan variasi visual baru yang lebih spektakuler, dramatis, dan memukau!

INFO Latar Film:
- Judul Film: {film_title}
- Judul Adegan: {scene_title}
- Mood / Style: {genre_style}
- Karakter & Seeds: {consistent_characters}
- Bahasa Utama: {target_lang}

WAJIB HASILKAN VARIANT BARU ADEGAN {scene_number} (10 DETIK):
1. Gerakan Kamera Baru (misal: Low Angle Hero Tracking, Dutch Angle Action, Over-The-Shoulder Close Up).
2. Ringkasan Aksi Baru dalam bahasa {target_lang}.
3. Narasi Dubbing Voiceover 10 Detik (Bahasa {target_lang} & English). Jika ada yang berbicara, WAJIB terjemahkan ke bahasa {target_lang} di dalam prompt_for_flow.
4. Detailed English 10s Video Prompt for Google Flow (mencantumkan Seeds Karakter + Kamera 10s + Aksi + 8k Lighting).
   -> Sisipkan dialog dalam tanda kutip `speaking angrily in natural {target_lang}: "..."` jika karakter berbicara.

OUTPUT WAJIB FORMAT JSON VALID (Tanpa teks lain di luar JSON):
{{
  "scene_number": {scene_number},
  "title": "{scene_title}",
  "action_summary": "Ringkasan aksi variasi baru (WAJIB DITULIS DALAM BAHASA {target_lang} SECARA MUTLAK!)",
  "prompt_for_flow": "Detailed English 10s video prompt for Google Flow with character seeds, camera shot, cinematic lighting. Include speaking dialog in {target_lang} if any.",
  "camera_movement": "Sudut & Gerakan Kamera Baru (10s)",
  "lighting_mood": "Mood lighting baru",
  "narration_id": "Teks Narasi Voiceover (WAJIB DITULIS DALAM BAHASA {target_lang}, JANGAN INDONESIA JIKA BUKAN INDONESIA)",
  "narration_en": "English Voiceover Narration Text (10s)"
}}
"""

    last_err = None
    try:
        result = generate_text(prompt, json_output=True)
        parsed = json.loads(_extract_json_text(result.text))
        if parsed.get("prompt_for_flow"):
            parsed["generated_via"] = result.provider
            return parsed
    except Exception as ex:
        last_err = ex
        log.warning("Regenerate scene via provider AI gagal: %s", ex)

    web_txt = _call_web2api(prompt)
    if web_txt:
        try:
            parsed = json.loads(_extract_json_text(web_txt))
            if parsed.get("prompt_for_flow"):
                log.info("Regenerate Scene %d berhasil via fallback Web2API!", scene_number)
                return parsed
        except Exception as ex:
            log.warning("Fallback Web2API mengembalikan JSON adegan tidak valid: %s", ex)

    raise RuntimeError(f"Gagal regenerate adegan: {last_err}")


def generate_music_video_storyboard(lyrics: str, audio_duration: float, scene_count: int, aspect_ratio: str, character_info: str, image_paths: List[str] = None, target_lang: str = "Indonesia") -> Dict[str, Any]:
    """Generates a cinematic music video storyboard mapped precisely to audio duration and lyrics."""
    model_name = settings.get_settings().get("gemini_model") or "gemini-3.6-flash"
    models_to_try = [
        model_name,
        "gemini-3.6-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash"
    ]

    seed = random.randint(100000, 999999)

    prompt = f"""
Anda adalah seorang Music Video Director profesional.
Tugas Anda adalah merancang storyboard video musik yang memukau secara visual berdasarkan lirik atau tema musik.

- Durasi Total Musik: {audio_duration} detik
- Target Jumlah Adegan: {scene_count} (masing-masing adegan berdurasi ~10 detik)
- Lirik Lagu ATAU Suasana Musik Instrumen:
{lyrics}

ATURAN UTAMA:
1. Rancang alur cerita/visual yang dibagi ke dalam {scene_count} adegan secara merata.
2. Jika input berupa lirik, masukkan potongan lirik ke dalam field `narration_id` untuk dijadikan subtitle dalam bahasa {target_lang}. Jika lirik asing, TERJEMAHKAN ke bahasa {target_lang}. Jika instrumen, isi dengan narasi pendek bahasa {target_lang}.
3. Rancang visual (prompt_for_flow) yang mencerminkan suasana, emosi, dan makna musik berdasarkan teks di atas.
4. Aspect ratio: {aspect_ratio}.
5. Jika ada tokoh manusia, pastikan karakternya konsisten menggunakan sistem Seed:
   - Character Seed Utama: {seed}
   - Karakter Info / Referensi Tambahan: {character_info}
6. Gaya visual: cinematic music video, highly aesthetic, emotional grading, 8k resolution.
7. SANGAT PENTING: Karakter TIDAK BOLEH bernyanyi, lip-sync, berbicara, atau menggerakkan bibir mengikuti lirik. Visual hanya berupa adegan dramatis/sinematik yang bisu. Karakter mengekspresikan makna lirik HANYA melalui ekspresi wajah, tatapan mata, bahasa tubuh, dan sinematografi. Jangan pernah memasukkan instruksi "singing", "lip-sync", atau "speaking" di dalam `prompt_for_flow`.
8. Semua `prompt_for_flow` WAJIB melarang logo stasiun TV, channel bug, watermark, logo sponsor/platform,
   ticker, lower-third, dan branded overlay di setiap frame.

OUTPUT WAJIB FORMAT JSON VALID (Tanpa markdown tambahan di luar JSON):
{{
  "film_title": "Music Video",
  "genre_style": "Cinematic Music Video",
  "art_direction": "Music Video Art Direction",
  "character_seed": {seed},
  "consistent_characters": "Deskripsi Karakter",
  "characters": [
    {{
      "id": 1,
      "name": "Nama Karakter Utama",
      "source_actor_id": "ID aktor persis dari daftar aktor spesifik, atau kosong",
      "seed": {seed},
      "description": "Deskripsi visual karakter"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "time_range": "0:00-0:10",
      "title": "Potongan Lirik/Suasana",
      "action_summary": "Terjemahan/visualisasi dari lirik",
      "shot_type": "Wide Shot / Close Up",
      "characters_in_scene": [1],
      "prompt_for_flow": "Detailed English video prompt for Google Flow... (wajib gunakan {seed})",
      "text_overlay": "Lirik yang sedang dinyanyikan",
      "camera_movement": "Gerakan kamera",
      "lighting_mood": "Mood lighting",
      "narration_id": "",
      "narration_en": "",
      "duration": 10
    }}
  ]
}}

HANYA KEMBALIKAN JSON VALID!
"""

    last_err = None
    image_paths = image_paths or []
    pil_images = []
    for p in image_paths:
        try:
            if Path(p).exists():
                pil_images.append(Image.open(p))
        except Exception as ex:
            log.warning("Gagal memuat gambar referensi MV %s: %s", p, ex)

    last_err = None
    try:
        result = generate_text(pil_images + [prompt], json_output=True)
        parsed = json.loads(_extract_json_text(result.text))
        parsed["character_seed"] = seed
        parsed["generated_via"] = result.provider
        if "scenes" in parsed:
            for scene in parsed["scenes"]:
                scene["duration"] = 10.0
                if "narration_id" not in scene:
                    scene["narration_id"] = scene.get("action_summary", "")
        return parsed
    except Exception as ex:
        last_err = ex
        log.warning("Generate MV via provider AI gagal: %s", ex)

    # fallback
    web_txt = _call_web2api(prompt)
    if web_txt:
        try:
            parsed = json.loads(_extract_json_text(web_txt))
            parsed["character_seed"] = seed
            if "scenes" in parsed:
                for s in parsed["scenes"]:
                    s["duration"] = 10.0
                    if "narration_id" not in s:
                        s["narration_id"] = s.get("action_summary", "")
            return parsed
        except Exception as ex:
            log.warning("Fallback Web2API MV gagal: %s", ex)

    raise RuntimeError(f"Gagal merancang Music Video Storyboard: {last_err}")
