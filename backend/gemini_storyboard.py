"""Sinematica Backend — Gemini 3.6 Flash Multi-Character & Multi-Angle Cinematic Storyboard Engine."""

import json
import logging
import random
import re
import threading
import requests
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from PIL import Image

from . import settings
from .scene_direction import ensure_unique_character_signatures
from .scene_execution import NATURAL_ACTION_RULES, DOOR_INTERACTION_RULES
from .text_generation import generate_text
from .content_quality import normalize_creative_brief, build_creative_brief_prompt, build_five_realism_prompt
from .cinematic_pacing import build_dynamic_narrative_rules, build_story_part_rules, detect_cinematic_archetype

log = logging.getLogger("sinematica.storyboard")

WEB2API_TIMEOUT = 180


def _complete_scene_fields(scene: Dict[str, Any], index: int, total: int) -> Dict[str, Any]:
    """Keep the editor usable when a provider omits optional-looking scene fields."""
    action = str(scene.get("action_summary") or scene.get("activity") or "Aksi adegan berlangsung").strip()
    title = str(scene.get("title") or f"Adegan {index}").strip()
    shot_type = str(scene.get("shot_type") or "Medium Shot").strip()
    camera = str(scene.get("camera_movement") or "Static locked-off").strip()

    if index == 1:
        purpose = "Hook / context"
    elif index == total:
        purpose = "Payoff / CTA"
    elif index <= max(2, total // 2):
        purpose = "Problem / development"
    else:
        purpose = "Escalation / proof"

    defaults = {
        "scene_purpose": purpose,
        "activity": action,
        "expression": "Ekspresi natural berubah mengikuti aksi dan konflik adegan",
        "visual_composition": f"{shot_type}; subjek utama dan properti aksi terbaca jelas dalam frame",
        "transition_bridge": "Arah pandang atau gerakan terakhir mengantar mulus ke adegan berikutnya",
        "shot_type": shot_type,
        "camera_movement": camera,
        "narration_id": action,
        "text_overlay": " ".join(title.split()[:6]),
    }
    for field, default in defaults.items():
        if not scene.get(field):
            scene[field] = default
    if not scene.get("shot_flow"):
        duration = max(1, int(scene.get("duration") or 10))
        split = max(1, duration // 3)
        scene["shot_flow"] = [
            {"time": f"0-{split}s", "angle": shot_type, "description": "Pembuka dan konteks aksi"},
            {"time": f"{split}-{min(duration, split * 2)}s", "angle": "Close Up", "description": "Detail aksi dan perubahan ekspresi"},
            {"time": f"{min(duration, split * 2)}-{duration}s", "angle": "Reaction / Final Look", "description": "Reaksi akhir dan jembatan transisi"},
        ]
    return scene


def _complete_storyboard_scene_fields(storyboard: Dict[str, Any]) -> Dict[str, Any]:
    scenes = storyboard.get("scenes") or []
    for index, scene in enumerate(scenes, 1):
        _complete_scene_fields(scene, index, len(scenes))
    return storyboard


def _scene_story_text(scene: Dict[str, Any]) -> str:
    dialogue_lines = []
    for item in scene.get("dialogue") or []:
        if isinstance(item, dict):
            dialogue_lines.append(str(item.get("line") or ""))
        else:
            dialogue_lines.append(str(item))
    fields = (
        scene.get("title"),
        scene.get("scene_purpose"),
        scene.get("activity"),
        scene.get("expression"),
        scene.get("action_summary"),
        scene.get("transition_bridge"),
        scene.get("narration_id"),
        scene.get("prompt_for_flow"),
        " ".join(dialogue_lines),
    )
    return " ".join(str(value or "") for value in fields).lower()


_CONFLICT_TERMS = (
    "konflik", "bertengkar", "pertikaian", "menolak", "ditolak", "menghina", "dihina",
    "ancaman", "mengancam", "rahasia", "terbongkar", "pengkhianatan", "berkhianat",
    "curiga", "tuduhan", "menuduh", "tekanan", "jebakan", "krisis", "masalah",
    "melawan", "konfrontasi", "bukti", "terdesak", "kehilangan", "ultimatum",
    "conflict", "refuse", "betray", "secret", "threat", "evidence", "crisis",
)
_ESCALATION_TERMS = (
    "semakin", "memuncak", "meningkat", "terdesak", "mendesak", "memburuk",
    "membongkar", "menemukan", "menantang", "menghadapi", "keputusan", "pilihan",
    "akibat", "konsekuensi", "menyodorkan", "mengungkap", "terungkap", "balasan",
    "rising", "complication", "pressure", "turning point", "reversal",
)
_CLIMAX_TERMS = (
    "klimaks", "puncak", "konfrontasi", "menghadapi", "mengalahkan", "menang",
    "kalah", "terbongkar", "pengakuan", "keputusan terakhir", "pertarungan",
    "ledakan emosi", "balas dendam", "membuktikan", "menentukan", "final clash",
    "climax", "confrontation", "decisive", "showdown",
)
_ENDING_TERMS = (
    "ending", "akhir", "resolusi", "selesai", "berakhir", "akibat", "konsekuensi",
    "bahagia", "sedih", "menangis lega", "memaafkan", "berpisah", "hukuman",
    "keadilan", "damai", "happy", "sad", "resolution", "aftermath", "payoff",
)
_HOOK_TERMS = (
    "hook", "penasaran", "pertanyaan", "rahasia", "anomali", "janji", "masalah",
    "kejutan", "bukti", "ancaman", "tujuan", "mencari", "menemukan", "curiosity",
    "cold open", "open loop", "promise",
)
_CHANGE_TERMS = (
    "berubah", "memutuskan", "keputusan", "menolak", "menerima", "mengambil",
    "memberi", "menyerahkan", "menemukan", "membongkar", "mengungkap", "terungkap",
    "kehilangan", "menyadari", "menghadapi", "menantang", "menolong", "mencoba",
    "gagal", "berhasil", "akibat", "konsekuensi", "tekanan", "reveal", "decision",
    "discovers", "chooses", "changes", "fails", "succeeds",
)
_PAYOFF_TERMS = _ENDING_TERMS + (
    "jawaban", "terjawab", "hasil", "pelajaran", "perayaan", "restu", "kebenaran",
    "terbayar", "cta", "call to action", "proof", "benefit", "celebration",
)
_FLAT_TERMS = (
    "berjalan pelan", "melihat ruangan", "mengamati suasana", "menatap kejauhan",
    "menikmati pemandangan", "duduk diam", "berdiri diam", "quietly walking",
    "looking around", "stands still", "walks slowly",
)


def _has_any(text: str, terms) -> bool:
    return any(term in text for term in terms)


def _is_complete_story_range(scene_offset: int, scene_count: int, total_scene_count: Optional[int]) -> bool:
    total = int(total_scene_count or scene_count or 0)
    return int(scene_offset or 0) <= 0 and int(scene_count or 0) >= total


def _normalize_story_part_request(
    requested_part_scene_count: int,
    story_total_scene_count: Optional[int],
    story_scene_offset: int,
) -> tuple[int, int, int]:
    """Return safe part counts and collapse accidental one/two-scene tails.

    A dangling final part of 1-2 scenes is almost always a UI/preset mismatch for this
    tool. It skips the complete-story audits and causes fake part endings, like a
    15-scene storyboard reporting total_scene_count=16. Longer totals such as
    40 scenes with a 20-scene part remain untouched.
    """
    requested = max(1, min(25, int(requested_part_scene_count or 4)))
    total = max(requested, min(2000, int(story_total_scene_count or requested)))
    offset = max(0, min(int(story_scene_offset or 0), total - 1))
    if offset == 0 and total > requested and (total - requested) <= 2:
        total = requested
    target = min(requested, total - offset)
    return total, offset, target


def _sync_creative_brief_result(
    creative_brief: Dict[str, Any],
    *,
    aspect_ratio: str,
    scene_count: int,
    duration_seconds: Optional[int],
) -> Dict[str, Any]:
    """Keep user-facing result metadata aligned with normalized engine counts."""
    brief = dict(creative_brief or {})
    default = f"Storyboard video {aspect_ratio}, {scene_count} scene" + (
        f", sekitar {duration_seconds} detik" if duration_seconds else ""
    )
    result = str(brief.get("result") or "").strip()
    if not result or re.search(r"\b\d+\s*scene\b", result, flags=re.IGNORECASE):
        brief["result"] = default
    return brief


def _story_parts_meta(
    *,
    story_part_number: int,
    story_scene_offset: int,
    target_scene_count: int,
    story_total_scene_count: int,
) -> Dict[str, Any]:
    generated = min(story_total_scene_count, story_scene_offset + target_scene_count)
    return {
        "part_number": max(1, int(story_part_number or 1)),
        "scene_offset": max(0, int(story_scene_offset or 0)),
        "part_scene_count": max(1, int(target_scene_count or 1)),
        "total_scene_count": max(1, int(story_total_scene_count or target_scene_count or 1)),
        "generated_scene_count": generated,
        "has_next_part": generated < max(1, int(story_total_scene_count or target_scene_count or 1)),
    }


_CONTINUATION_TERMS = (
    "belum", "namun", "tetapi", "tiba-tiba", "mendadak", "telepon", "pesan",
    "datang", "muncul", "menunggu", "ancaman", "tekanan", "pertanyaan",
    "rahasia baru", "jejak", "cliffhanger", "open loop", "berikutnya", "lanjut",
)


def _audit_story_part_boundary(
    storyboard: Dict[str, Any],
    *,
    children_mode: bool = False,
    script_mode: bool = False,
    story_scene_offset: int = 0,
    story_total_scene_count: Optional[int] = None,
    strict: bool = True,
) -> Dict[str, Any]:
    scenes = storyboard.get("scenes") or []
    total = len(scenes)
    if script_mode or total < 1:
        storyboard["story_part_boundary_audit"] = {"status": "skipped"}
        return storyboard
    global_total = int(story_total_scene_count or total or 0)
    generated = int(story_scene_offset or 0) + total
    has_next_part = generated < global_total
    final_text = _scene_story_text(scenes[-1])
    if not has_next_part:
        ok = _has_any(final_text, _PAYOFF_TERMS) or children_mode
        storyboard["story_part_boundary_audit"] = {"status": "passed" if ok else "failed", "final_payoff": ok, "has_next_part": False}
        if strict and not ok:
            raise ValueError("Storyboard ditolak sebelum render: part terakhir belum punya payoff/ending final yang jelas.")
        return storyboard

    looks_final = _has_any(final_text, _ENDING_TERMS) or "part 1 ending" in final_text or "part ending" in final_text
    leaves_open_loop = _has_any(final_text, _CONTINUATION_TERMS)
    ok = (not looks_final) or leaves_open_loop
    storyboard["story_part_boundary_audit"] = {
        "status": "passed" if ok else "failed",
        "has_next_part": True,
        "avoids_fake_ending": ok,
        "looks_final": looks_final,
        "leaves_open_loop": leaves_open_loop,
    }
    if strict and not ok:
        raise ValueError(
            "Storyboard ditolak sebelum render: part ini masih punya lanjutan, tetapi scene terakhir terasa seperti ending final. "
            "Buat cliffhanger, tekanan baru, atau keputusan belum selesai; jangan menutup konflik utama sebelum part terakhir."
        )
    return storyboard


def _audit_dramatic_arc(
    storyboard: Dict[str, Any],
    *,
    children_mode: bool = False,
    script_mode: bool = False,
    story_scene_offset: int = 0,
    story_total_scene_count: Optional[int] = None,
    strict: bool = True,
) -> Dict[str, Any]:
    """Fail cheap when a complete drama has no conflict, climax, or ending."""
    scenes = storyboard.get("scenes") or []
    total = len(scenes)
    is_complete_story = _is_complete_story_range(story_scene_offset, total, story_total_scene_count)
    if children_mode or script_mode or total < 3 or not is_complete_story:
        storyboard["dramatic_arc_audit"] = {"status": "skipped"}
        return storyboard

    thirds = [
        " ".join(_scene_story_text(scene) for scene in scenes[: max(1, int(total * 0.35))]),
        " ".join(_scene_story_text(scene) for scene in scenes[max(1, int(total * 0.25)): max(2, int(total * 0.75))]),
        " ".join(_scene_story_text(scene) for scene in scenes[max(0, int(total * 0.65)):]),
    ]
    final_scene_text = _scene_story_text(scenes[-1])
    whole = " ".join(thirds)
    findings = {
        "conflict": _has_any(thirds[0], _CONFLICT_TERMS) or _has_any(whole, _CONFLICT_TERMS),
        "escalation": _has_any(thirds[1], _ESCALATION_TERMS),
        "climax": _has_any(thirds[2], _CLIMAX_TERMS),
        "ending": _has_any(final_scene_text, _ENDING_TERMS),
    }
    storyboard["dramatic_arc_audit"] = {"status": "passed" if all(findings.values()) else "failed", **findings}
    if strict and not all(findings.values()):
        missing = ", ".join(key for key, ok in findings.items() if not ok)
        raise ValueError(
            "Storyboard ditolak sebelum render: alur terlalu datar, beat drama belum lengkap "
            f"({missing}). Generate ulang dengan konflik, eskalasi, klimaks, dan ending yang jelas."
        )
    return storyboard


def _audit_story_engagement_quality(
    storyboard: Dict[str, Any],
    *,
    children_mode: bool = False,
    script_mode: bool = False,
    story_scene_offset: int = 0,
    story_total_scene_count: Optional[int] = None,
    strict: bool = True,
) -> Dict[str, Any]:
    """Reject stories that are technically complete but not watchable."""
    scenes = storyboard.get("scenes") or []
    total = len(scenes)
    is_complete_story = _is_complete_story_range(story_scene_offset, total, story_total_scene_count)
    if script_mode or not is_complete_story or total < 1:
        storyboard["story_engagement_audit"] = {"status": "skipped"}
        return storyboard

    texts = [_scene_story_text(scene) for scene in scenes]
    first_text = " ".join(texts[: max(1, min(total, max(1, int(total * 0.30))))])
    final_text = texts[-1]
    whole = " ".join(texts)

    active_scene_count = sum(1 for text in texts if _has_any(text, _CHANGE_TERMS))
    flat_scene_count = sum(1 for text in texts if _has_any(text, _FLAT_TERMS) and not _has_any(text, _CHANGE_TERMS))
    purposes = [str(scene.get("scene_purpose") or "").strip().lower() for scene in scenes]
    repeated_purpose_count = len(purposes) - len(set(p for p in purposes if p))
    min_active = max(1, int(total * (0.55 if children_mode else 0.65)))

    findings = {
        "hook_or_question": _has_any(first_text, _HOOK_TERMS) or _has_any(whole, _HOOK_TERMS),
        "scene_progression": active_scene_count >= min_active,
        "low_flatness": flat_scene_count <= max(1, int(total * 0.20)),
        "payoff_or_ending": _has_any(final_text, _PAYOFF_TERMS),
    }
    if children_mode:
        # Kids content should still have curiosity, a gentle problem, attempts, and a warm payoff.
        findings["safe_child_progress"] = _has_any(whole, ("mencoba", "belajar", "menolong", "bergantian", "bersama", "berhasil", "pelajaran", "try", "learn", "help"))

    audit = {
        "status": "passed" if all(findings.values()) else "failed",
        "active_scene_count": active_scene_count,
        "flat_scene_count": flat_scene_count,
        "repeated_purpose_count": repeated_purpose_count,
        "purpose_variety": repeated_purpose_count <= max(1, int(total * 0.45)),
        **findings,
    }
    storyboard["story_engagement_audit"] = audit
    if strict and not all(findings.values()):
        missing = ", ".join(key for key, ok in findings.items() if not ok)
        raise ValueError(
            "Storyboard ditolak sebelum render: kualitas cerita belum cukup menarik "
            f"({missing}). Setiap durasi wajib punya hook, progres scene, sebab-akibat, dan payoff."
        )
    return storyboard


def _quality_audit_failures(storyboard: Dict[str, Any]) -> List[str]:
    failures = []
    for key in ("story_engagement_audit", "dramatic_arc_audit", "story_part_boundary_audit"):
        audit = storyboard.get(key) or {}
        if audit.get("status") == "failed":
            missing = [name for name, value in audit.items() if isinstance(value, bool) and not value]
            failures.extend(missing or [key])
    return list(dict.fromkeys(failures))


def _repair_storyboard_quality(
    storyboard: Dict[str, Any],
    *,
    premise: str,
    target_lang: str,
    scene_count: int,
    fixed_scene_duration: Optional[int],
    children_mode: bool,
    script_mode: bool,
    story_scene_offset: int,
    story_total_scene_count: int,
    generator=None,
) -> Dict[str, Any]:
    """Ask the text model to doctor a weak storyboard before giving up."""
    if script_mode:
        return storyboard
    generator = generator or generate_text
    first_pass = _complete_storyboard_scene_fields(storyboard)
    first_pass = _audit_story_engagement_quality(
        first_pass,
        children_mode=children_mode,
        script_mode=script_mode,
        story_scene_offset=story_scene_offset,
        story_total_scene_count=story_total_scene_count,
        strict=False,
    )
    first_pass = _audit_dramatic_arc(
        first_pass,
        children_mode=children_mode,
        script_mode=script_mode,
        story_scene_offset=story_scene_offset,
        story_total_scene_count=story_total_scene_count,
        strict=False,
    )
    first_pass = _audit_story_part_boundary(
        first_pass,
        children_mode=children_mode,
        script_mode=script_mode,
        story_scene_offset=story_scene_offset,
        story_total_scene_count=story_total_scene_count,
        strict=False,
    )
    failures = _quality_audit_failures(first_pass)
    if not failures:
        return first_pass

    scenes_payload = json.dumps(first_pass.get("scenes") or [], ensure_ascii=False)[:70000]
    characters_payload = json.dumps(first_pass.get("characters") or [], ensure_ascii=False)[:20000]
    mode_note = (
        "Konten anak: jangan menambah konflik dewasa, kekerasan, ancaman, atau rasa takut. Perbaiki dengan "
        "rasa penasaran, hambatan ringan, usaha mencoba, kerja sama, pembelajaran, dan payoff hangat."
        if children_mode else
        "Drama/cerita umum: wajib tambah hook, konflik, stakes, eskalasi, krisis, klimaks, dan ending yang terasa terbayar."
    )
    repair_prompt = f"""
Anda adalah script doctor dan editor retensi penonton.
Storyboard berikut jumlah scene-nya benar, tetapi audit kualitas menemukan kelemahan: {', '.join(failures)}.

TUGAS:
- Tulis ulang scene yang lemah saja secara kreatif, tapi pertahankan tepat {scene_count} scene.
- Jangan mengubah medium visual, jumlah scene, karakter utama, target bahasa, durasi scene, atau urutan besar premis.
- Setiap scene wajib punya sebab-akibat dari scene sebelumnya dan memaksa scene berikutnya.
- Scene pertama wajib memberi alasan menonton.
- Jika ini part terakhir/cerita lengkap, scene terakhir wajib memberi payoff/ending yang jelas.
- Jika masih ada part lanjutan, scene terakhir wajib menyisakan tekanan/open-loop/cliffhanger dan DILARANG terasa seperti ending final.
- Untuk 10 detik, jangan membuat adegan kosong. Isi dengan aksi, reaksi, bukti, dialog pendek, atau keputusan.
- {mode_note}

PREMIS:
{premise}

TARGET BAHASA: {target_lang}
FIXED DURATION: {fixed_scene_duration or 'ikuti duration yang sudah ada'}
KARAKTER:
{characters_payload}

SCENES SAAT INI:
{scenes_payload}

OUTPUT HANYA JSON VALID dengan struktur:
{{"film_title":"...", "logline":"...", "emotional_arc":"...", "characters":[...], "scenes":[...]}}
"""
    result = generator(repair_prompt, json_output=True)
    repaired = json.loads(_extract_json_text(result.text))
    if not repaired.get("characters"):
        repaired["characters"] = first_pass.get("characters") or []
    if not repaired.get("film_title"):
        repaired["film_title"] = first_pass.get("film_title") or "Film Sinematik"
    scenes = repaired.get("scenes") or []
    if len(scenes) != scene_count:
        raise ValueError(f"Repair storyboard menghasilkan {len(scenes)} scene, seharusnya {scene_count}.")
    for local_index, scene in enumerate(scenes, start=1):
        scene["scene_number"] = story_scene_offset + local_index
        if fixed_scene_duration:
            scene["duration"] = fixed_scene_duration
    return _complete_storyboard_scene_fields(repaired)


_children_variation_lock = threading.Lock()
_recent_children_variations: List[str] = []
_recent_auto_art_directions: List[str] = []
_CHILDREN_VARIATION_POOLS = {
    "hero": ["anak berang-berang", "anak kapibara", "anak tapir", "anak rusa", "anak rubah", "anak rakun", "anak koala", "anak panda merah", "boneka awan", "makhluk bintang mungil", "anak kura-kura", "anak landak", "anak alpaka", "anak burung hantu", "anak anjing laut"],
    "companion": ["sahabat yang teliti", "tetangga baru yang pemalu", "kakak sepupu yang ceria", "penolong kecil yang penuh ide", "teman yang suka bertanya", "kelompok tiga sahabat", "orang dewasa tepercaya yang lembut", "teman yang berbeda ukuran tubuh"],
    "setting": ["kebun komunitas", "pasar pagi mini", "perpustakaan pohon", "tepi kolam teratai", "dapur rumah yang hangat", "kelas seni", "taman selepas hujan", "stasiun kereta mainan", "pantai berpasir lembut", "festival lampion tanpa keramaian", "rumah kaca bunga", "jalur piknik di hutan", "bengkel mainan", "halaman sekolah", "perkemahan halaman rumah"],
    "object": ["layang-layang berbentuk daun", "kotak bekal warna-warni", "lonceng mungil", "payung bermotif bintang", "keranjang buah", "peta bergambar", "boneka kaus kaki", "biji tanaman", "pita warna", "kapal kertas", "kue berbentuk bulan", "balok pola"],
    "gentle_problem": ["benda penting terselip di tempat tak terduga", "urutan kegiatan tertukar", "dua teman menginginkan giliran yang sama", "percobaan pertama belum berhasil", "petunjuk sederhana disalahpahami", "cuaca mengubah rencana bermain", "satu bagian karya belum lengkap", "tokoh utama ragu meminta bantuan", "seorang teman baru belum tahu aturan permainan", "jumlah benda belum cocok"],
    "story_shape": ["mulai dari kejutan visual, coba dua cara berbeda, lalu temukan solusi bersama", "mulai dari pertanyaan sederhana, kumpulkan tiga petunjuk, lalu rayakan jawaban", "mulai dari kesalahan lucu, berhenti dan bernapas, lalu mencoba kembali dengan strategi baru", "mulai dari kebutuhan seorang teman, bergantian menawarkan ide, lalu berbagi hasilnya", "mulai dari permainan berulang, hadirkan satu perubahan, lalu tutup dengan ajakan anak menjawab"],
    "name_sound": ["dua suku kata dengan bunyi vokal berbeda", "nama pendek berawalan konsonan lembut", "nama lokal yang jarang dipakai di hasil sebelumnya", "nama fiktif ceria tanpa rima satu sama lain", "nama mudah diucapkan anak namun bukan Momo, Kiko, Bibo, Nino, Cici, Upi, Leo, atau Mika"],
}


def build_children_variation_packet() -> str:
    """Return a fresh creative constraint packet so repeated prompts diverge materially."""
    rng = random.SystemRandom()
    with _children_variation_lock:
        recent = set(_recent_children_variations)
        chosen = None
        for _ in range(30):
            candidate = {key: rng.choice(values) for key, values in _CHILDREN_VARIATION_POOLS.items()}
            signature = "|".join(candidate.values())
            if signature not in recent:
                chosen = (candidate, signature)
                break
        if chosen is None:
            candidate = {key: rng.choice(values) for key, values in _CHILDREN_VARIATION_POOLS.items()}
            chosen = (candidate, "|".join(candidate.values()))
        _recent_children_variations.append(chosen[1])
        del _recent_children_variations[:-20]

    values = chosen[0]
    token = f"KIDS-{rng.randrange(10000000, 99999999)}"
    return f"""
PAKET VARIASI CERITA ANAK — {token} (WAJIB MEMBUAT HASIL BARU):
- Bentuk tokoh utama: {values['hero']}.
- Dinamika pendamping: {values['companion']}.
- Lokasi dominan: {values['setting']}.
- Properti cerita: {values['object']}.
- Hambatan ringan: {values['gentle_problem']}.
- Bentuk alur: {values['story_shape']}.
- Pola nama: {values['name_sound']}.

ATURAN ANTI-KONTEN-BERULANG:
1. Nama yang tertulis dalam premis preset hanyalah placeholder, kecuali pengguna secara eksplisit meminta nama
   itu dipertahankan. Buat nama karakter baru yang natural untuk negara/bahasa target pada setiap generasi.
2. Semua karakter dalam satu cerita harus memiliki nama dengan bunyi awal dan akhir berbeda; jangan memakai
   pasangan nama berima atau mengulang nama contoh dari instruksi.
3. Gunakan paket di atas sebagai arah kreatif, tetapi pertahankan tujuan belajar/tema utama pengguna.
4. Jangan menyalin judul, urutan kejadian, lokasi, properti, dialog, hook, atau resolusi dari cerita anak generik
   yang pernah dibuat. Variasikan sedikitnya lima unsur tersebut pada setiap hasil.
5. Token variasi adalah penanda internal; jangan tampilkan token ini di judul, dialog, narasi, atau output JSON.
"""


_AUTO_ART_POOLS = {
    "palette": [
        "saffron, dusty turquoise, warm ivory, and charcoal accents", "mulberry, antique rose, parchment cream, and muted brass",
        "sage green, apricot, cloud blue, and walnut brown", "cobalt, coral, pale sand, and ink navy",
        "lavender grey, moss green, butter yellow, and soft aubergine", "terracotta, celadon, rice-paper white, and deep indigo",
        "peacock teal, marigold, warm stone, and oxblood accents", "sea-glass mint, shell pink, sky grey, and cocoa brown",
        "plum, copper, smoky blue, and linen beige", "forest green, persimmon, pale gold, and midnight blue",
        "cherry red, powder blue, oatmeal, and graphite", "orchid, jade, pale peach, and espresso brown",
    ],
    "lighting": [
        "window light filtered through patterned curtains with soft bounced fill", "cool overcast daylight with warm practical lamps inside the frame",
        "late-afternoon side light broken by leaves, with gentle moving shadows", "diffused skylight plus a restrained coloured rim from the environment",
        "soft dawn light with pearly highlights and low-contrast shadows", "lantern-like practical pools of light with readable faces and backgrounds",
        "bright open shade with crisp colour separation and subtle reflected light", "post-rain daylight with soft reflections rather than a generic blue grade",
    ],
    "materials": [
        "woven rattan, glazed ceramic, linen, and lightly weathered wood", "translucent paper, brushed metal, frosted glass, and natural cotton",
        "painted timber, knitted fabric, matte clay, and polished river stone", "terrazzo, pleated fabric, bamboo, and enamelled metal",
        "recycled paper, cork, canvas, and hand-painted ceramic", "velvet accents, dark wood, aged brass, and textured plaster",
        "clear acrylic, pale plywood, soft felt, and powder-coated metal", "woven grass, raw silk, carved wood, and coloured glass",
    ],
    "hero_object": [
        "an unusual folding map with symbol-based markings", "a hand-built keepsake box with movable compartments",
        "a patterned umbrella with one distinctive repaired panel", "a small ceramic token with a unique silhouette",
        "a fabric satchel containing three story-relevant tools", "a modular picture card set with tactile shapes",
        "a wind-up object whose motion reveals a clue", "a translucent container whose contents visibly change",
        "a woven basket with a precise object count", "a handmade paper model that transforms during the story",
        "a ribbon spool used as a visual continuity marker", "a pocket-sized lantern with a recognisable cutout pattern",
    ],
    "motif": [
        "circles gradually becoming complete", "diagonal lines becoming level and calm", "reflections revealing information before dialogue does",
        "repeated leaf shapes guiding the eye", "small-to-large scale progression", "paired objects separating and reuniting",
        "shadows changing from fragmented to unified", "one accent colour moving between characters",
        "open and closed shapes marking decisions", "three recurring textures signalling story stages",
    ],
}


def build_auto_art_direction(children_mode: bool = False) -> Dict[str, str]:
    """Generate a non-repeating AI art-direction seed that remains stable for one storyboard."""
    rng = random.SystemRandom()
    with _children_variation_lock:
        recent = set(_recent_auto_art_directions)
        chosen = None
        for _ in range(30):
            candidate = {key: rng.choice(values) for key, values in _AUTO_ART_POOLS.items()}
            signature = "|".join(candidate.values())
            if signature not in recent:
                chosen = (candidate, signature)
                break
        if chosen is None:
            candidate = {key: rng.choice(values) for key, values in _AUTO_ART_POOLS.items()}
            chosen = (candidate, "|".join(candidate.values()))
        _recent_auto_art_directions.append(chosen[1])
        del _recent_auto_art_directions[:-30]
    result = chosen[0]
    result["mode"] = "child-safe playful art direction" if children_mode else "niche-aware cinematic art direction"
    result["token"] = f"ART-{rng.randrange(10000000, 99999999)}"
    return result


def format_auto_art_direction(direction: Dict[str, str]) -> str:
    return (
        f"AUTO AI ART DIRECTION {direction['token']}: {direction['mode']}; "
        f"candidate palette: {direction['palette']}; candidate lighting: {direction['lighting']}; "
        f"material language: {direction['materials']}; story-driving hero object: {direction['hero_object']}; "
        f"recurring visual motif: {direction['motif']}."
    )


ADULT_ACTION_RULES = """ATURAN KEPADATAN AKSI SINEMATIK (WAJIB — INI YANG MEMBUAT CERITA HIDUP & MENGIKAT):
1. **Setiap adegan WAJIB mengubah situasi.** Di akhir adegan harus ada sesuatu yang berbeda dari awalnya:
   informasi baru terbongkar, tensi/hubungan bergeser, keputusan diambil, atau anomali baru terungkap.
   Jika sebuah adegan bisa dihapus tanpa mengubah cerita, adegan itu SALAH dan harus dirancang ulang.
2. **DILARANG adegan statis / kosong tanpa makna.** Tokoh berjalan, menatap ke kejauhan, atau berada di ruangan
   TIDAK boleh hampa. Aktivitas semacam itu wajib memuat ketegangan terselubung, pencarian petunjuk, atau subteks emosi.
3. **Mulai dari aksi termotivasi (start with intent, end with impact).** Buang basa-basi kosong. Setiap adegan
   memiliki tujuan dramatis yang jelas dan dipotong tepat setelah titik reaksi atau perubahannya.
3a. **Khusus adegan 10 detik, gunakan 4–6 variasi sudut kamera bertimestamp (Multi-Angle Shot Progression):**
   Rancang 4 hingga 6 perubahan angle sinematik bertahap (seperti Low Angle Close Up -> Medium Wide -> Over-The-Shoulder / Macro Detail -> Medium Close -> Wide Ending Shot).
   Setiap sub-shot memuat framing dan aksi fisik berbeda agar visual video tidak monoton di satu angle saja.
   Isi rincian ini di field `shot_flow` dan rangkai instruksi transisi kameranya ke dalam `prompt_for_flow`.
   Jika ada dialog, wajib minimal DUA giliran bicara pendek yang dipisahkan reaksi fisik/counter-action.
4. **Adegan pembuka (Scene 1) memicu rasa penasaran & empati**:
   - Untuk cerita multi-scene (>= 5 scene), bangun suasana atmosferik, interaksi wajar, dan ketegangan halus/misteri (DILARANG langsung teriak/menampar tanpa konteks).
   - Untuk cerita ultra-pendek (1-4 scene), gunakan hook instan / in medias res yang memikat.
5. **Maksimal SATU establishing shot** di seluruh film, itu pun wajib memuat aksi dramatis/subjek penting di dalamnya.
6. Field `action_summary` WAJIB memuat kata kerja aksi konkret dan ekspresif (misal: menatap dingin, menyembunyikan surat, menyodorkan kontrak, melangkah menantang, membongkar bukti, merangkul haru, berbisik tegas) — bukan kata kerja pasif hampa seperti "berada di kamar" atau "menikmati pemandangan"."""

CHILDREN_ACTION_RULES = """ATURAN CERITA ANAK (WAJIB — MENGGANTIKAN ATURAN KONFLIK DEWASA):
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
   Beri nama sederhana yang mudah diingat dan diucapkan anak. Jangan memakai daftar nama contoh yang sama
   berulang kali; nama wajib dibuat segar dan berbeda pada setiap generasi."""

BATTLE_VS_RULES = """ATURAN KHUSUS ANIME / SUPERHERO BATTLE VS (WAJIB):
1. Gunakan karakter, kostum, simbol, kekuatan, transformasi, dan nama jurus yang 100% orisinal. Dilarang meniru,
   menyebut, atau membuat versi mirip karakter/franchise anime, manga, komik, film superhero, atau game terkenal.
2. Sebelum menulis scene, buat battle matrix untuk setiap petarung: sumber kekuatan, gaya gerak, warna aura,
   keunggulan, keterbatasan, pertahanan, jurus dasar, counter, dan SATU ultimate signature move bernama unik.
3. Struktur duel harus berkembang: entrance/aura reveal -> demonstrasi kemampuan A -> balasan kemampuan B ->
   counter dan adaptasi -> jurus andalan masing-masing -> final clash -> aftermath dan hasil yang jelas.
4. Setiap petarung wajib mendapat momen unggul dan memakai kekuatan secara berbeda. Jangan membuat satu tokoh
   hanya diam menerima serangan. Kemenangan ditentukan strategi, timing, penguasaan medan, atau kerja sama.
5. Setiap jurus harus terlihat sebagai aksi berurutan yang dapat dirender: posisi awal, gerakan tubuh/tangan,
   bentuk dan lintasan energi, interaksi dengan lingkungan, respons lawan, counter, serta posisi akhir.
6. Pertahankan warna dan geometri efek masing-masing agar mudah dibedakan. Efek energi tidak boleh berubah warna,
   bentuk, atau sumber tanpa transformasi yang diperlihatkan. Nama jurus hanya di dialog/narasi, jangan minta Flow
   merender tulisan di layar.
7. Duel wajib spektakuler tetapi non-lethal: tanpa darah, luka, kematian, pemenggalan, penusukan, atau kehancuran
   massal. Gunakan arena aman, shield impact, energy deflection, ring-out, kehabisan energi, atau menyerah sportif.
8. Akhir harus menjelaskan pemenang atau hasil seri secara visual dan logis, lalu tutup dengan sikap saling hormat
   atau ancaman pertandingan ulang—bukan kemenangan mendadak tanpa sebab."""

POLICY_SAFE_RULES = """
ATURAN WAJIB LOLOS FILTER KEBIJAKAN & MODERASI GOOGLE FLOW (JANGAN DILANGGAR):
Google Flow (Veo 2 & Imagen) SANGAT KETAT terhadap visual kekerasan, bahaya, dan tokoh nyata. Pelanggaran memicu penolakan (UNSAFE_GENERATION / DANGER_FILTER / PROMINENT_PEOPLE).

1. **KEKERASAN, SENJATA & PERTEMPURAN (Cegah UNSAFE_GENERATION)**:
   - DILARANG menampilkan: darah (blood/bleeding), luka menganga (wounds/gore), senjata api aktif (guns/rifles shooting), penusukan (stabbing), pembunuhan (killing/murder/death), mayat (corpse), pemenggalan, atau kehancuran brutal (devastation/massacre/burning town).
   - CARA MENGGAMBARKAN AKSI & BATTLE CINEMATIC: Gunakan metafora sinematik PG-13 yang megah:
     * Alih-alih "menembak/menusuk musuh": gunakan "intense non-lethal martial standoff, swift disarming technique, deflection of glowing energy aura, dramatic defensive stance in pouring rain".
     * Alih-alih "desa hancur terbakar/devastation": gunakan "dramatic stormy atmosphere, windswept dusty terrain, dark cinematic storm clouds gathering over the landscape".
     * Alih-alih "perang berdarah": gunakan "epic dramatic face-off between two determined factions, intense stare-down, cloaks fluttering in the howling wind".
     * Alih-alih "kematian/mayat": gunakan "dramatic surrender, falling to knees in emotional defeat, dropping weapon to the ground, heavy breathing".

2. **BAHAYA, PENGORBANAN & SELF-HARM (Cegah DANGER_FILTER)**:
   - DILARANG menggambarkan: aksi bunuh diri, mengorbankan nyawa hingga tewas (fatal sacrifice/dying), melompat ke jurang/api, racun (poison), gantung diri, terbakar hidup-hidup, atau adegan kecelakaan maut.
   - CARA MENGGAMBARKAN PENGORBANAN / REDEMPTION:
     * Gunakan "noble act of stepping forward to shield a companion with outstretched arms, powerful emotional redemption, heartfelt tearful embrace, golden sunlight breaking through the dark clouds".

3. **APARAT, PEJABAT & SERAGAM NEGARA (Cegah REPUTATIONAL / GOV FILTER)**:
   - DILARANG menyebut `police`, `police officer`, `polisi`, seragam kepolisian resmi, `military army`, `tentara`, `judge`, `prosecutor`, atau pejabat pemerintah nyata.
   - GANTI DENGAN peran fiktif/swasta: `security officer`, `private investigator`, `guard`, `family lawyer`, `estate administrator`, `community leader`.

4. **NAMA TOKOH PUBLIK & MEREK ASLI (Cegah PROMINENT_PEOPLE)**:
   - DILARANG memakai nama selebriti, politisi, tokoh sejarah modern, presiden, atau figur terkenal.
   - Gunakan nama karakter fiktif orisinal (misal: "Mateo", "Lin Xue", "Joko", "Sari", "Bagus", "Elena").
   - DILARANG menyebut nama rumah sakit, sekolah, bank, atau brand komersial nyata. Ciptakan nama institusi fiktif.

5. **DOKUMEN RESMI NEGARA**:
   - Hindari KTP, paspor, lambang negara resmi. Sebut generik: `a sealed confidential dossier` atau `an official stamped envelope`.

Intensitas emosi, drama, ketegangan, dan sinematografi WAJIB tetap maksimal dan menegangkan, namun 100% bersih dari kata kunci terlarang!
"""


def sanitize_prompt_for_policy(prompt_for_flow: str, rejection_reason: str = "", scene_title: str = "") -> Optional[str]:
    """Rewrite a video prompt that Google Flow rejected so the scene can be retried.

    Keeps the dramatic beat, characters, seeds, camera work, and lighting intact, and only
    swaps out whatever tends to trip Flow's policy filters. Returns the rewritten English
    prompt, or None when no model could produce one.
    """
    reason_upper = str(rejection_reason or "").upper()
    specific_guidance = ""
    if "UNSAFE_GENERATION" in reason_upper:
        specific_guidance = """
PETUNJUK KHUSUS UNSAFE_GENERATION:
- Hapus semua kata atau visual pertempuran berdarah, penembakan, penusukan, senjata api, mayat, kehancuran ('devastation/massacre/battle/blood/wound/kill').
- Tulis ulang sebagai ketegangan dramatis tanpa kekerasan fisik: 'intense non-violent standoff, cinematic pouring rain, windswept confrontation, swift disarm movement, emotional stare-down'.
"""
    elif "DANGER_FILTER" in reason_upper:
        specific_guidance = """
PETUNJUK KHUSUS DANGER_FILTER:
- Hapus semua konsep pengorbanan mematikan ('sacrifice life/death/suicide/fatal wound'), melompat ke bahaya, api membakar orang, atau racun.
- Tulis ulang sebagai penebusan emosional / perlindungan: 'noble act of stepping forward to shield a friend, emotional redemption, tearful heartfelt gaze, protective stance in golden dawn light'.
"""
    elif "PROMINENT_PEOPLE" in reason_upper:
        specific_guidance = """
PETUNJUK KHUSUS PROMINENT_PEOPLE:
- Hapus nama atau jabatan yang menyerupai tokoh publik, selebriti, atau pejabat nyata.
- Gunakan karakter fiktif murni dengan wajah generik non-selebriti.
"""

    prompt = f"""
Anda adalah Script Doctor spesialis lolos moderasi konten Google Flow (AI video generator).

Sebuah prompt video DITOLAK oleh Google Flow.
Judul adegan: "{scene_title or 'Adegan'}"
Alasan penolakan dari Google: "{rejection_reason or 'PUBLIC_ERROR_REPUTATIONAL'}"

PROMPT YANG DITOLAK:
\"\"\"{prompt_for_flow}\"\"\"

{POLICY_SAFE_RULES}
{specific_guidance}

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

COUNTRY_LANGUAGE_MAP = {
    "Indonesia": "Indonesia", "Malaysia": "Melayu", "Singapore": "Inggris",
    "Thailand": "Thailand", "Vietnam": "Vietnam", "Philippines": "Tagalog",
    "Japan": "Jepang", "South Korea": "Korea", "China": "Mandarin",
    "Taiwan": "Mandarin", "Saudi Arabia": "Arab", "United Arab Emirates": "Arab",
    "Qatar": "Arab", "Egypt": "Arab", "Turkey": "Turki", "Iran": "Persia",
    "India": "Hindi", "Pakistan": "Urdu", "Bangladesh": "Bengali",
    "United States": "Inggris", "United Kingdom": "Inggris", "France": "Prancis",
    "Germany": "Jerman", "Italy": "Italia", "Spain": "Spanyol", "Russia": "Rusia",
    "Brazil": "Portugis", "Mexico": "Spanyol", "Argentina": "Spanyol",
    "Canada": "Inggris", "South Africa": "Inggris", "Nigeria": "Inggris",
    "Kenya": "Inggris", "Morocco": "Arab", "Australia": "Inggris",
    "New Zealand": "Inggris",
}


def resolve_target_language(target_country: str = "", target_lang: str = "") -> str:
    """Use an explicit language, otherwise infer the country's primary content language."""
    explicit = (target_lang or "").strip()
    if explicit:
        return explicit
    return COUNTRY_LANGUAGE_MAP.get((target_country or "").strip(), "Indonesia")


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


def build_children_localization_rules(target_country: str = "", target_lang: str = "") -> str:
    """Localize early-learning stories without changing their learning objective."""
    country = (target_country or "").strip() or "audiens internasional"
    language = (target_lang or "").strip() or resolve_target_language(target_country, "")
    return f"""
ATURAN LOKALISASI EDUKASI ANAK (WAJIB):
1. Pertahankan tujuan belajar dan kelompok usia pada premis; jangan menaikkan kompleksitas bahasa atau konflik.
2. Semua narasi, dialog, lagu pendek, pengulangan, label angka/huruf, dan teks layar harus natural dalam bahasa {language}; jangan menyisakan bahasa Indonesia bila targetnya berbeda.
3. Sesuaikan nama karakter, sapaan, makanan, permainan, benda sekolah, rumah, cuaca, musim, rambu, arah lalu lintas, dan kebiasaan sehari-hari agar familier bagi anak di {country}.
4. Untuk konsep huruf, bunyi, rima, atau berhitung, adaptasikan contoh katanya—jangan menerjemahkan secara harfiah jika bunyi/polanya rusak dalam bahasa {language}.
5. Gunakan representasi keluarga dan komunitas yang hangat serta beragam. Hindari karikatur, token budaya, stereotip, simbol politik, dan klaim bahwa satu kebiasaan mewakili semua warga {country}.
6. Dialog toddler maksimal 3–6 kata per giliran dan memakai pengulangan; dialog prasekolah maksimal 8–12 kata per giliran dengan satu gagasan konkret.
7. Setiap adegan hanya mengajarkan satu langkah kecil, memberi contoh visual, lalu mengajak anak mengulang atau menjawab. Koreksi kesalahan dengan lembut tanpa mempermalukan.
"""


def auto_suggest_details(theme: str = "", microdrama_mode: bool = False, children_mode: bool = False, target_country: str = "", dracin_theme: str = "", target_lang: str = "", series_mode: bool = False) -> Dict[str, Any]:
    """Auto-suggest character matrix, creative cinematic premise, and seeds using Gemini AI."""
    seed_main = random.randint(100000, 999999)
    seed_2 = random.randint(100000, 999999)
    seed_3 = random.randint(100000, 999999)

    target_lang = resolve_target_language(target_country, target_lang)
    auto_concept_token = f"CONCEPT-{random.SystemRandom().randrange(10000000, 99999999)}"
    user_prompt = f"""TEMA UTAMA PENGGUNA (WAJIB DIIKUTI SECARA KETAT & SETIA): "{theme}"

PETUNJUK BAHASA & TEMA:
1. Pahami tema dari pengguna dalam BAHASA APAPUN (Bahasa Indonesia, Inggris, Arab, Jepang, dll).
2. Anda HARUS merancang cerita yang 100% SESUAI DENGAN TEMA TERSEBUT. Jangan pernah membelokkan tema (Misal: Jika pengguna memasukkan tentang 'Bahaya Rokok', WAJIB merancang film drama medis/sosial sinematik tentang bahaya merokok dan dampaknya, BUKAN sci-fi alien/cyberpunk yang tidak relevan).
3. Berikan `suggested_premise` dan `suggested_character` sepenuhnya dalam bahasa {target_lang}, termasuk nama lokal, dialog, dan istilah sosial yang natural untuk {target_country or 'audiens target'}.""" if theme.strip() else f"""
MODE AUTO AI — {auto_concept_token}:
Buat satu niche dan konsep baru dalam bahasa {target_lang}. Pilih secara kreatif dari drama sosial, misteri benda,
komedi situasi, petualangan lokal, slice of life, profesi unik, sejarah alternatif aman, fantasi orisinal, edukasi,
keluarga, persahabatan, perjalanan, atau gabungan dua niche yang cocok. Jangan memakai premis contoh/template yang
umum, nama karakter lama, CEO menyamar, pewaris rahasia, balas dendam konglomerat, artefak purba, atau kerajaan
langit kecuali pengguna memilih genre itu secara eksplisit. Token hanya internal dan tidak boleh muncul di output.
"""

    dracin_theme_instruction = f"""
TEMA DRACIN WAJIB DIPAKAI: "{dracin_theme}"
Rancang cerita mengikuti premis tema dracin populer ini secara 100% setia, jangan menyimpang ke tema lain.""" if dracin_theme.strip() else f"""
PILIH SATU TEMA DRACIN POPULER BERIKUT (yang paling relate dengan tema/premis pengguna jika ada, atau pilih bebas jika premis kosong):
{chr(10).join('- ' + t for t in DRACIN_THEME_POOL)}"""

    local_realism_instruction = build_local_realism_rules(target_country)

    if series_mode:
        series_seed = format_auto_art_direction(build_auto_art_direction(False))
        prompt = f"""
Anda adalah Head Writer dan Series Bible Designer untuk drama serial premium.
{build_local_realism_rules(target_country)}
{user_prompt}
{series_seed}

MODE AUTO AI DRAMA SERIES (WAJIB BUKAN TEMPLATE):
1. Pilih satu kombinasi genre yang segar dan relevan bagi audiens {target_country or 'target'}, misalnya drama
   keluarga + misteri profesi, romance + dilema etika, workplace + rahasia komunitas, legal fiktif + persahabatan,
   slice of life + teka-teki benda, atau thriller sosial aman. Hindari otomatis memakai CEO, pewaris, pernikahan
   kontrak, amnesia, bayi tertukar, balas dendam konglomerat, dan pasangan kaya-miskin.
2. Rancang engine serial yang dapat menghasilkan banyak episode: lokasi utama berulang, pekerjaan/aktivitas rutin,
   pertanyaan musim, konflik relasi, rahasia bertahap, serta object/motif yang kembali dengan fungsi berbeda.
3. Konsep yang ditulis adalah EPISODE PILOT: cold open kuat, pengenalan ensemble melalui aksi, A-plot selesai
   sebagian, B-plot mulai bergerak, perubahan hubungan, reveal akhir, dan cliffhanger yang membuka episode kedua.
4. Buat 3-5 karakter dengan nama baru, tujuan pribadi, kontradiksi, hubungan antartokoh, ciri visual permanen,
   dan informasi yang hanya diketahui sebagian karakter. Jangan membuat tokoh sekadar baik/jahat.
5. Jangan menuntaskan misteri musim di pilot. Setiap pengungkapan harus menimbulkan pertanyaan baru yang spesifik.
6. Semua nama, institusi, lokasi mikro, profesi, benda penting, dan konflik harus orisinal serta natural dalam
   bahasa {target_lang}. Token ART/CONCEPT hanya internal dan tidak boleh muncul di output.

OUTPUT JSON VALID:
{{
  "suggested_premise": "Judul serial sementara; engine serial; premis episode pilot 3 paragraf berisi cold open, A/B plot, reveal dan cliffhanger episode berikutnya",
  "suggested_character": "Karakter 1 - [Nama] (Seed {seed_main}): [peran, tujuan, kontradiksi, relasi, rupa].\\nKarakter 2 - [Nama] (Seed {seed_2}): [...].\\nKarakter 3 - [Nama] (Seed {seed_3}): [...].",
  "character_seed": {seed_main}
}}
"""
    elif children_mode:
        children_variation = build_children_variation_packet()
        art_variation = format_auto_art_direction(build_auto_art_direction(True))
        prompt = f"""
Anda adalah kreator serial anak yang merancang konsep episode BARU, aman, lokal, dan tidak template.
{build_children_localization_rules(target_country, target_lang)}
{user_prompt}
{children_variation}
{art_variation}

WAJIB:
1. Pilih satu tujuan belajar atau sosial-emosional yang konkret dan berbeda-beda: bahasa, angka, pola, sains,
   kreativitas, kemandirian, empati, kerja sama, keselamatan, kebiasaan sehat, musik, alam, atau pemecahan masalah.
2. Tokoh adalah hewan/boneka/makhluk lucu orisinal. Nama, spesies, lokasi, object utama, aktivitas, hook, kesalahan
   lucu, cara mencoba, dan payoff harus baru. Object wajib menggerakkan alur, bukan sekadar dekorasi.
3. Jangan menyalin premis preset katalog. Jangan otomatis memakai taman, bola hilang, wortel, pelangi, menara balok,
   atau nama Momo/Kiko/Bibo/Nino/Cici/Upi/Leo/Mika.
4. Buat premis 2-3 paragraf dengan konflik ringan, tiga langkah visual, partisipasi anak, dan akhir bahagia.

OUTPUT JSON VALID:
{{
  "suggested_premise": "Premis anak baru 2-3 paragraf dalam bahasa {target_lang}",
  "suggested_character": "Karakter 1 - [Nama baru] (Seed {seed_main}): [spesies, warna, pakaian, ciri].\\nKarakter 2 - [Nama baru] (Seed {seed_2}): [detail berbeda].",
  "character_seed": {seed_main}
}}
"""
    elif microdrama_mode:
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
    if children_mode:
        base_theme = theme if theme.strip() else "dua sahabat hewan membuat alat penakar hujan dari wadah bening dan belajar membandingkan tinggi air"
        fallback_premise = f"Dalam episode baru tentang {base_theme}, dua tokoh dengan nama baru menemukan pertanyaan sederhana dari perubahan di sekitar mereka. Mereka mengamati, menghitung, dan mencoba dua cara menggunakan benda buatan tangan yang menjadi bagian penting dari permainan.\n\nPercobaan pertama belum tepat, lalu mereka saling mendengarkan dan memperbaikinya bersama. Hasil akhirnya terlihat jelas, dapat diikuti anak, dan ditutup dengan ajakan menjawab singkat serta perayaan yang hangat."
    else:
        base_theme = theme if theme.strip() else "seorang perawat tanaman malam menemukan pola aneh pada pesanan bunga yang menghubungkan tiga keluarga di kota pesisir"
        fallback_premise = f"Di lingkungan lokal bertema {base_theme}, tokoh utama menemukan benda sehari-hari yang tidak berada pada tempat semestinya. Ia mengikuti rangkaian petunjuk konkret sambil menghadapi pilihan yang mengubah hubungannya dengan orang-orang di sekitarnya.\n\nSetiap temuan membalik pemahamannya tentang masalah awal. Pada klimaks, fungsi sebenarnya dari benda tersebut terbuka melalui tindakan visual, dan tokoh menyelesaikan konflik dengan keputusan yang meninggalkan perubahan nyata pada komunitasnya."
    fallback_characters = (
        f"Karakter 1 - Luma (Seed {r_seed}): Anak kapibara mungil berbaju biru awan dengan kantong alat ukur.\n"
        f"Karakter 2 - Tavi (Seed {r_seed2}): Anak burung hantu cokelat muda berkacamata hijau dengan kartu gambar."
        if children_mode else
        f"Tokoh 1 - Utama (Seed {r_seed}): Sosok lokal dengan pakaian dan profesi yang relevan dengan niche.\n"
        f"Tokoh 2 - Pendamping (Seed {r_seed2}): Sosok dengan siluet, warna pakaian, dan motivasi yang berbeda.\n"
        f"Tokoh 3 - Penggerak Konflik (Seed {r_seed3}): Sosok orisinal dengan properti cerita yang khas."
    )
    return {
        "suggested_premise": fallback_premise,
        "suggested_character": fallback_characters,
        "character_seed": r_seed
    }


def generate_youtube_metadata(
    film_title: str,
    premise: str,
    target_lang: str = "Indonesia",
    target_country: str = "",
    aspect_ratio: str = "landscape",
    storyboard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate accurate YouTube packaging based on official metadata guidance."""
    thumbnail_ratio = "9:16" if str(aspect_ratio).lower() in {"portrait", "9:16", "vertical"} else "16:9"
    prompt = f"""
Anda adalah YouTube SEO Specialist & Content Strategist Terkemuka.
Berdasarkan judul film "{film_title}" dan premis cerita: "{premise}", rancangkan kit publikasi YouTube lengkap:

SUMBER KEBENARAN:
- Teks di atas berisi ringkasan storyboard aktual beserta karakter dan urutan adegannya.
- Baca SELURUH adegan sebelum menulis metadata. Ambil keyword dari tokoh utama, tujuan, konflik, titik balik,
  pelajaran, dan payoff yang benar-benar tampak di storyboard.
- Dilarang menambah tokoh, peristiwa, genre, kemampuan, lokasi, atau twist yang tidak ada di storyboard.
- Judul dan dua baris pertama deskripsi harus mencerminkan hook serta payoff terkuat dari storyboard, bukan
  frasa generik seperti "kisah luar biasa", "petualangan seru", atau "konflik yang mengubah segalanya".
- Tags harus berupa kombinasi keyword utama, nama tokoh aktual, topik/masalah aktual, format konten, dan variasi
  pencarian long-tail yang masuk akal. Jangan mengisi tags dengan nama teknologi pembuat video kecuali memang
  isi videonya membahas teknologi tersebut.

BAHASA DAN PASAR TARGET (WAJIB):
- Bahasa output: {target_lang}
- Negara/audiens: {target_country or 'internasional'}
- Judul, deskripsi, CTA, hashtag, dan tag kata kunci WAJIB 100% ditulis natural dalam bahasa {target_lang}.
- Gunakan kosakata pencarian dan gaya judul yang natural bagi penonton {target_country or target_lang}; jangan menerjemahkan secara kaku.
- DILARANG memakai Bahasa Indonesia kecuali target_lang memang Indonesia.
- Hanya `thumbnail_prompt` yang tetap ditulis dalam Bahasa Inggris untuk generator gambar.

1. **3 Pilihan Judul Akurat dan Menarik (target 70-100 karakter, maksimal mutlak 100 karakter)**:
   - Gunakan kapitalisasi normal yang nyaman dibaca; DILARANG menulis seluruh judul dengan HURUF KAPITAL.
   - Letakkan satu keyword utama secara natural dekat awal dan jelaskan konflik atau nilai spesifik video.
   - Buat tiga sudut berbeda: searchable, curiosity-driven, dan story/emotion-driven.
   - Harus akurat terhadap isi; dilarang clickbait menyesatkan, klaim palsu, spam, dan keyword stuffing.
   - Akhiri setiap judul dengan 1-2 hashtag paling relevan. Panjang judul BESERTA hashtag tidak boleh melebihi 100 karakter.
2. **Deskripsi YouTube Unik**:
   - Dua baris pertama langsung menjelaskan konflik atau nilai utama dengan keyword utama secara natural karena bagian ini terlihat sebelum Show more.
   - Berikutnya rangkum alur tanpa membocorkan semua kejutan, lalu CTA singkat yang relevan.
   - Jangan mengarang link, kredit, chapter, nama channel, atau teknologi produksi yang tidak disebutkan input.
   - Akhiri dengan tepat 3 hashtag yang langsung terkait isi video.
3. **Prompt Thumbnail / Cover YouTube (Midjourney/Flux/Flow Prompt Bahasa Inggris)**:
   - Video sumber berformat {thumbnail_ratio}. Prompt cover WAJIB memakai komposisi {thumbnail_ratio}, bukan rasio lain.
   - Satu subjek utama, emosi jelas, konflik mudah dibaca, kontras kuat, dan teks thumbnail maksimal 2-4 kata.
   - Thumbnail harus memenuhi janji judul dan tidak menyesatkan.
4. **Hashtag**: tepat 3 hashtag tanpa spasi, spesifik, dan relevan.
5. **Tag Kata Kunci Backend YouTube**:
   - 8-12 tag dipisahkan koma. Prioritaskan topik utama, variasi pencarian natural, nama karakter penting, dan variasi ejaan yang mungkin salah.
   - Jangan memakai #, jangan mengulang frasa, dan jangan memasukkan viral/trending tanpa alasan. Tags hanya pendukung discovery.
6. **Komentar Tersemat (Pinned Comment)**:
   - 1 pertanyaan diskusi menarik yang relevan dengan dilema atau pesan film untuk disematkan di kolom komentar guna memicu engagement dan diskusi penonton.

OUTPUT WAJIB FORMAT JSON VALID:
{{
  "titles": [
    "Judul searchable yang akurat",
    "Judul curiosity-driven yang akurat",
    "Judul story/emotion-driven yang akurat"
  ],
  "description": "Dua baris pembuka yang kuat...\\n\\nRingkasan unik...\\n\\nCTA singkat...\\n\\n#Hashtag1 #Hashtag2 #Hashtag3",
  "pinned_comment": "Pertanyaan pancingan diskusi yang relevan...",
  "thumbnail_prompt": "High-impact {thumbnail_ratio} YouTube cover prompt in English...",
  "hashtags": ["#Hashtag1", "#Hashtag2", "#Hashtag3"],
  "tags": "topik utama, variasi pencarian, nama karakter, variasi ejaan"
}}
"""
    from .youtube_seo import normalize_youtube_seo_kit

    try:
        result = generate_text(prompt, json_output=True)
        parsed = json.loads(_extract_json_text(result.text))
        if str(target_lang).strip().lower() in {"korea", "korean", "한국어"}:
            language_sample = " ".join([
                *[str(item) for item in (parsed.get("titles") or parsed.get("seo_titles") or [])],
                str(parsed.get("description") or ""),
            ])
            if len(re.findall(r"[\uac00-\ud7af]", language_sample)) < 10:
                raise ValueError("Provider SEO tidak mematuhi bahasa Korea; mencoba provider berikutnya.")
        parsed["generated_via"] = result.provider
        parsed["target_lang"] = target_lang
        parsed["target_country"] = target_country
        return normalize_youtube_seo_kit(parsed, film_title, premise, aspect_ratio=aspect_ratio, storyboard=storyboard)
    except Exception as ex:
        log.warning("Gagal generate metadata YouTube dari provider AI: %s", ex)
        web_txt = _call_web2api(prompt)
        if web_txt:
            try:
                parsed = json.loads(_extract_json_text(web_txt))
                if parsed:
                    if str(target_lang).strip().lower() in {"korea", "korean", "한국어"}:
                        language_sample = " ".join([
                            *[str(item) for item in (parsed.get("titles") or parsed.get("seo_titles") or [])],
                            str(parsed.get("description") or ""),
                        ])
                        if len(re.findall(r"[\uac00-\ud7af]", language_sample)) < 10:
                            raise ValueError("Fallback SEO tidak menghasilkan bahasa Korea.")
                    parsed["target_lang"] = target_lang
                    parsed["target_country"] = target_country
                    log.info("Metadata YouTube berhasil via fallback Web2API!")
                    return normalize_youtube_seo_kit(parsed, film_title, premise, aspect_ratio=aspect_ratio)
            except Exception as w_ex:
                log.warning("Fallback Web2API mengembalikan JSON metadata tidak valid: %s", w_ex)
        is_korean = str(target_lang).strip().lower() in {"korea", "korean", "한국어"}
        if is_korean:
            fallback_titles = [
                f"{film_title} | 두 전설의 충돌, 마지막 순간 드러난 진짜 승자는? #애니메이션 #단편영화",
                f"{film_title}에서 무슨 일이 벌어졌나? 운명을 바꾼 차원의 대결 #AI영화 #액션",
                f"두 영웅이 맞선 순간, 예상 못한 선택이 세상을 바꿨다 | {film_title} #스토리",
            ]
            fallback_description = (
                f"{film_title}: {premise}\n"
                "등장인물들의 운명을 바꾸는 갈등과 선택을 끝까지 확인해 보세요.\n\n"
                "가장 인상 깊었던 장면을 댓글로 남겨 주세요.\n\n"
                "#AI영화 #단편영화 #스토리"
            )
            fallback_hashtags = ["#AI영화", "#단편영화", "#스토리"]
            fallback_tags = f"{film_title}, {film_title} 전체 영상, {film_title} 이야기, AI 영화, 단편 영화, 한국어 이야기"
        else:
            fallback_titles = [
                f"{film_title}: Pertarungan sinematik dengan alur paling menegangkan",
                f"{film_title}: Siapa yang akan memenangkan pertarungan luar biasa ini?",
                f"Saksikan {film_title}, kisah aksi sinematik yang penuh kejutan",
            ]
            fallback_description = f"{film_title} menghadirkan {premise}.\nIkuti konflik utama dan keputusan yang mengubah perjalanan para karakternya.\n\nTonton sampai akhir, lalu bagikan pendapatmu tentang momen yang paling berkesan.\n\n#FilmAI #CeritaAI #FilmPendek"
            fallback_hashtags = ["#FilmAI", "#CeritaAI", "#FilmPendek"]
            fallback_tags = f"{film_title}, {film_title} full video, {film_title} cerita, film pendek ai, cerita sinematik ai, film ai indonesia"
        fallback = {
            "titles": [
                *fallback_titles
            ],
            "description": fallback_description,
            "hashtags": fallback_hashtags,
            "thumbnail_prompt": f"Dramatic cinematic cover for {film_title}, {thumbnail_ratio} aspect ratio, strong focal subject, readable composition, highly detailed character.",
            "tags": fallback_tags,
            "target_lang": target_lang,
            "target_country": target_country,
        }
        return normalize_youtube_seo_kit(fallback, film_title, premise, aspect_ratio=aspect_ratio)


def _extend_storyboard_scenes(
    storyboard: Dict[str, Any],
    target_count: int,
    premise: str,
    target_lang: str = "Indonesia",
    seed: int = 100000,
    fixed_scene_duration: Optional[int] = None,
    generator=None,
) -> Dict[str, Any]:
    """Seamlessly generate remaining scenes when an AI provider returns fewer scenes than requested."""
    if generator is None:
        generator = generate_text

    scenes = storyboard.get("scenes") or []
    if len(scenes) >= target_count or not scenes:
        return storyboard

    max_attempts = 4
    attempt = 0
    while len(scenes) < target_count and attempt < max_attempts:
        attempt += 1
        missing_count = target_count - len(scenes)
        batch_size = min(missing_count, 20)
        start_idx = len(scenes) + 1
        end_idx = len(scenes) + batch_size
        last_scene = scenes[-1]
        film_title = storyboard.get("film_title") or "Film Sinematik"

        continuation_prompt = f"""
Anda adalah Sutradara Film AI Sinematik Kelas Dunia.
Lanjutkan pembuatan adegan untuk film "{film_title}".
Saat ini sudah ada {len(scenes)} adegan. Anda WAJIB menghasilkan TEPAT {batch_size} adegan berikutnya (Scene {start_idx} sampai Scene {end_idx}) untuk melengkapi target {target_count} scene.

KONTEKS CERITA:
- Premis: {premise}
- Bahasa Utama: {target_lang}
- Karakter & Seeds: {json.dumps(storyboard.get('characters', []), ensure_ascii=False)}
- Adegan Terakhir Saat Ini (Scene {len(scenes)}):
  * Judul: {last_scene.get('title')}
  * Aksi: {last_scene.get('action_summary')}
  * End State: {last_scene.get('end_state')}
  * Prompt Terakhir: {last_scene.get('prompt_for_flow')}

TUGAS MUTLAK:
Hasilkan TEPAT {batch_size} adegan berikutnya (Scene {start_idx} s/d {end_idx}) yang melanjutkan alur cerita dari Scene {len(scenes)} menuju resolusi/klimaks.
Pertahankan format JSON LENGKAP yang identik. Setiap scene WAJIB mengisi semua field berikut dan tidak boleh
mengosongkannya: scene_number, title, scene_purpose, activity, expression, visual_composition,
transition_bridge, shot_type, camera_movement, action_summary, narration_id, text_overlay,
prompt_for_flow, shot_flow (3-6 shot bertimestamp), audio_blueprint, dialogue,
characters_in_scene, start_state, end_state, lighting_mood, dan duration.

OUTPUT WAJIB FORMAT JSON VALID (HANYA JSON):
{{
  "scenes": [
    ... {batch_size} objek adegan berurutan ...
  ]
}}
"""
        try:
            res = generator(continuation_prompt, json_output=True)
            parsed = json.loads(_extract_json_text(res.text))
            new_scenes = parsed.get("scenes") or []
            if not new_scenes:
                break
            for s in new_scenes:
                s["scene_number"] = len(scenes) + 1
                scenes.append(s)
                if len(scenes) >= target_count:
                    break
        except Exception as err:
            log.warning("Gagal melanjutkan batch scene (attempt %d): %s", attempt, err)
            break

    # Re-calculate cumulative time_range and clamp
    scenes = scenes[:target_count]
    cum_sec = 0
    for idx, s in enumerate(scenes, 1):
        s["scene_number"] = idx
        dur = int(s.get("duration") or (fixed_scene_duration or 10))
        start_m, start_s = divmod(cum_sec, 60)
        end_m, end_s = divmod(cum_sec + dur, 60)
        s["time_range"] = f"{start_m}:{start_s:02d}–{end_m}:{end_s:02d}"
        cum_sec += dur

    storyboard["scenes"] = scenes
    return _complete_storyboard_scene_fields(storyboard)


def _normalize_duration_seconds(value):
    """Accept numeric values and UI labels such as '10 seconds' safely."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return max(1, int(value))
    import re
    match = re.search(r"\d+(?:[.,]\d+)?", str(value))
    if not match:
        raise ValueError(f"Durasi tidak valid: {value!r}. Gunakan angka detik, misalnya 10.")
    return max(1, int(float(match.group(0).replace(',', '.'))))


def generate_storyboard(
    premise: str,
    image_paths: List[str] = None,
    scene_count: int = 4,
    aspect_ratio: str = "landscape",
    character_info: str = "",
    custom_instructions: str = "",
    creative_brief: Optional[Dict[str, Any]] = None,
    character_seed: Optional[int] = None,
    microdrama_mode: bool = False,
    ugc_mode: bool = False,
    ugc_variant: str = "realism",
    ugc_platform: str = "TikTok",
    ugc_tone: str = "Natural, fresh, friendly",
    ugc_emotional_arc: str = "",
    ugc_environment: str = "auto",
    ugc_lighting: str = "auto",
    ugc_conversion_brief: Optional[Dict[str, Any]] = None,
    target_country: str = "",
    dracin_theme: str = "",
    target_total_duration: Optional[int] = None,
    fixed_scene_duration: Optional[int] = None,
    children_mode: bool = False,
    visual_style: str = "live_action",
    visual_vibe: str = "none",
    lighting_style: str = "none",
    color_palette: str = "none",
    script_mode: bool = False,
    affiliate_config: Optional[Dict[str, Any]] = None,
    target_lang: str = "",
    story_total_scene_count: Optional[int] = None,
    story_scene_offset: int = 0,
    story_part_number: int = 1,
    previous_part_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate multi-scene structured storyboard JSON using the configured AI providers."""

    fixed_scene_duration = _normalize_duration_seconds(fixed_scene_duration)
    target_total_duration = _normalize_duration_seconds(target_total_duration)

    image_paths = image_paths or []
    affiliate_config = dict(affiliate_config or {})
    requested_part_scene_count = max(1, min(25, int(scene_count or 4)))
    story_total_scene_count, story_scene_offset, target_scene_count = _normalize_story_part_request(
        requested_part_scene_count,
        story_total_scene_count,
        story_scene_offset,
    )
    scene_count = target_scene_count
    cfg = settings.get_settings()
    seed = character_seed or random.randint(100000, 999999)
    estimated_duration = target_total_duration or ((fixed_scene_duration or 10) * story_total_scene_count)
    creative_brief = dict(creative_brief or {})
    from .ugc_conversion import build_conversion_prompt, normalize_conversion_brief
    ugc_conversion_brief = normalize_conversion_brief(ugc_conversion_brief)
    conversion_rules = build_conversion_prompt(ugc_conversion_brief) if ugc_mode and affiliate_config.get("enabled") else ""
    if affiliate_config.get("enabled") and not str(creative_brief.get("product_value") or "").strip():
        creative_brief["product_value"] = (
            f"Produk: {affiliate_config.get('name') or 'produk referensi'}. "
            f"Manfaat/USP yang diizinkan: {affiliate_config.get('benefits') or 'analisis dari konteks dan visual tanpa mengarang klaim'}. "
            f"CTA: {affiliate_config.get('cta') or 'ajakan natural sesuai alur'}."
        )
    creative_brief = normalize_creative_brief(
        creative_brief, premise=premise, aspect_ratio=aspect_ratio,
        target_country=target_country, target_lang=target_lang,
        scene_count=story_total_scene_count, duration_seconds=estimated_duration,
    )
    creative_brief = _sync_creative_brief_result(
        creative_brief,
        aspect_ratio=aspect_ratio,
        scene_count=story_total_scene_count,
        duration_seconds=estimated_duration,
    )
    creative_brief_rules = build_creative_brief_prompt(creative_brief)
    visual_style_contracts = {
        "live_action": "LIVE-ACTION CINEMATIC PHOTOGRAPHY: real human actors, natural skin pores, realistic hair and fabric, physically based lighting. Never cartoon, anime, illustration, cel shading, or stylized 3D.",
        "3d_cartoon": "STYLIZED 3D ANIMATION: consistent sculpted 3D characters, rounded modeled forms, physically based 3D materials, feature-animation lighting. Never live-action humans, photoreal photography, 2D drawing, anime, or cel animation.",
        "2d_animation": "HAND-DRAWN 2D ANIMATION: consistent line art, flat graphic shapes, controlled cel shading, painted 2D backgrounds, fixed model-sheet proportions. Never live-action photography, realistic skin pores, 3D render, clay, or photorealism.",
        "anime_2d": "2D ANIME PRODUCTION STYLE: consistent anime model sheets, clean ink lines, cel shading, expressive anime faces, painted 2D backgrounds. Never live-action photography, photoreal skin, western 3D cartoon, clay, or realistic CGI.",
        "toy_brick": "ORIGINAL TOY-BRICK 3D ANIMATION: interlocking plastic-brick environments, original block-figure characters, simple cylindrical heads and claw-like hands, glossy molded plastic materials, stop-motion-inspired movement. Never use LEGO logos, branded sets, licensed minifigures, live-action humans, 2D drawing, or photoreal skin.",
        "line_character": "MINIMALIST LINE-CHARACTER ANIMATION: consistent clean monoline characters, simple geometric bodies, sparse flat colour accents, white or restrained backgrounds, precise readable silhouettes. Never photorealism, 3D volume, textured skin, painterly shading, or style changes between scenes.",
        "claymation": "HANDCRAFTED CLAYMATION STOP-MOTION: consistent sculpted clay puppets, visible handmade fingerprints, miniature practical sets, tactile clay surfaces, frame-by-frame stop-motion movement. Never live-action actors, smooth CGI plastic, 2D illustration, or photoreal skin.",
        "storybook_watercolor": "WATERCOLOR STORYBOOK ANIMATION: consistent hand-painted watercolor characters, soft pigment blooms, textured cold-press paper, delicate ink contours, layered storybook backgrounds. Never live-action photography, 3D CGI, plastic materials, anime cel shading, or photorealism.",
        "paper_cutout": "PAPER-CUTOUT ANIMATION: layered hand-cut paper characters, visible paper fibres, hinged flat limbs, collage scenery, soft tabletop shadows, consistent stop-motion cutout construction. Never live-action humans, 3D CGI characters, clay, or photoreal skin.",
        "pixel_art": "CINEMATIC PIXEL-ART ANIMATION: one consistent pixel grid, deliberate limited colour palette, crisp pixel silhouettes, detailed retro-game backgrounds, sprite-consistent character proportions. Never smooth vector lines, live action, 3D rendering, anti-aliased photorealism, or mixed pixel resolutions.",
        "comic_book": "CINEMATIC COMIC-BOOK ANIMATION: consistent graphic-novel character design, bold ink contours, controlled halftone shading, dramatic panel-like compositions, limited print-inspired palette. Never live-action photography, 3D CGI, watercolor, or model redesign between scenes.",
    }
    default_visual_style = "3d_cartoon" if children_mode else "live_action"
    visual_style = visual_style if visual_style in visual_style_contracts else default_visual_style
    visual_style_contract = visual_style_contracts.get(visual_style, visual_style_contracts["live_action"])
    five_realism_rules = build_five_realism_prompt(visual_style)
    finishing_maps = {
        "vibe": {
            "none": "", "pro_cinematic": "polished professional cinematic production design, premium YouTube storytelling finish",
            "clean_commercial": "clean commercial art direction, uncluttered composition, highly readable subject separation",
            "documentary": "grounded observational documentary mood, authentic environments, restrained production design",
            "sci_fi": "original futuristic science-fiction production design, coherent technology language, no licensed franchises",
            "ugc_natural": "authentic creator-led UGC mood, natural smartphone immediacy, candid everyday staging",
            "korean_drama": "refined Korean drama mood, elegant emotional framing, polished romantic television finish",
            "microdrama": "fast-paced short-form microdrama staging, expressive reactions, clear visual story beats",
            "kids_colorful": "cheerful child-friendly energy, playful production design, bright readable visual storytelling",
            "cozy_lifestyle": "warm intimate lifestyle mood, relaxed domestic staging, inviting tactile comfort",
            "luxury_premium": "high-end luxury editorial finish, refined materials, elegant restrained composition",
            "dark_thriller": "mysterious suspense-thriller atmosphere, controlled shadows, tense but clearly readable staging",
        },
        "lighting": {
            "none": "", "soft_light": "soft diffused key light with gentle shadows", "golden_hour": "warm golden-hour directional light",
            "volumetric": "controlled volumetric light shafts and atmospheric depth", "chiaroscuro": "dramatic chiaroscuro key-to-fill contrast",
            "low_key": "low-key cinematic lighting with readable faces", "backlight": "strong rim backlight with clear silhouettes",
            "rainy": "overcast rainy ambience with wet-surface reflections",
        },
        "color": {
            "none": "", "warm": "cohesive warm amber colour palette", "cool": "cohesive cool blue-cyan colour palette",
            "vibrant": "controlled vibrant saturation with protected skin and character colours", "pastel": "soft cohesive pastel palette",
            "earthy": "natural earthy ochre, olive and brown palette", "complementary": "controlled complementary colour harmony",
            "teal_orange": "cinematic teal-and-orange palette with consistent grading",
        },
    }
    visual_vibe = visual_vibe if visual_vibe in finishing_maps["vibe"] else "none"
    lighting_style = lighting_style if lighting_style in finishing_maps["lighting"] else "none"
    color_palette = color_palette if color_palette in finishing_maps["color"] else "none"
    auto_art_direction = build_auto_art_direction(children_mode)
    effective_auto_direction = dict(auto_art_direction)
    if visual_vibe != "none":
        effective_auto_direction["mode"] = "support the manually selected vibe without replacing it"
    if lighting_style != "none":
        effective_auto_direction["lighting"] = "the manually selected lighting above is authoritative"
    if color_palette != "none":
        effective_auto_direction["palette"] = "the manually selected colour palette above is authoritative"
    auto_art_direction_text = format_auto_art_direction(effective_auto_direction)
    manual_finishing = "; ".join(filter(None, (
        finishing_maps["vibe"][visual_vibe], finishing_maps["lighting"][lighting_style], finishing_maps["color"][color_palette]
    )))
    auto_fields = []
    if visual_vibe == "none":
        auto_fields.append("AI must infer a niche-appropriate mood from the premise")
    if lighting_style == "none":
        auto_fields.append(f"use/adapt this lighting direction: {auto_art_direction['lighting']}")
    if color_palette == "none":
        auto_fields.append(f"use/adapt this non-template palette: {auto_art_direction['palette']}")
    finishing_contract = "; ".join(filter(None, [manual_finishing, *auto_fields]))

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

    requested_ugc_variant = str(ugc_variant or "realism").lower()
    ugc_variant = requested_ugc_variant if requested_ugc_variant in {"realism", "commercial", "raw_amateur"} else "realism"
    ugc_style_contracts = {
        "commercial": "premium commercial advertising: deliberate art direction, controlled studio/location lighting, elegant product hero composition, precise dolly or locked camera, refined but believable materials",
        "realism": "creator-made UGC realism: plausible smartphone capture, available natural light, minor handheld inertia, candid framing, lived-in location, natural pauses and imperfect-but-intentional human delivery",
        "raw_amateur": "raw amateur smartphone footage captured by an untrained person inside the real activity: accidental reactive framing, short unstable walking motion, footsteps and hand tremor, hesitant starts/stops, wrist rotation, late reframing, autofocus hunting, focus breathing, motion blur, partial occlusion, exposure pumping and uneven shot energy; socially alive ambient chatter and human presence; never polished, cinematic, centered, stabilized, symmetrical, glossy or commercially staged",
    }
    ugc_style_contract = ugc_style_contracts[ugc_variant]
    environment_presets = {
        "home_window": "a believable lived-in home beside a daylight window",
        "bathroom_vanity": "a clean but naturally used bathroom vanity",
        "modern_kitchen": "a functional modern kitchen with activity-relevant props",
        "work_desk": "a lived-in work desk with laptop and context-appropriate objects",
        "cafe_terrace": "an urban cafe terrace with plausible ambient activity",
        "tropical_beach": "a tropical beach appropriate for genuine outdoor product use",
        "poolside": "a poolside setting appropriate for water or sun exposure",
        "minimal_studio": "a neutral minimal studio with restrained production design",
        "premium_podium": "a premium product podium with controlled commercial lighting",
    }
    environment_direction = environment_presets.get(str(ugc_environment), str(ugc_environment or "auto"))
    if environment_direction == "auto":
        environment_direction = (
            "AI must recommend one contextually necessary location by reading the product, pain point, audience, "
            "usage moment, tone and platform. Prefer a place where the creator would genuinely use the product; "
            "avoid generic luxury rooms, random beaches, empty studios, or the same template location across niches"
        )
    lighting_presets = {
        "natural_window": "soft natural window light with believable falloff and protected skin highlights",
        "hard_window": "hard directional window sunlight with physically consistent crisp shadows",
        "phone_flash": "direct phone-camera flash with realistic falloff, restrained specular highlights and ambient background exposure",
        "cafe_window": "soft cafe window key light mixed naturally with warm practical ambience",
        "overcast": "soft overcast daylight with broad shadowless illumination and natural skin tone",
        "store_light": "credible convenience-store practical fluorescent light with controlled mixed colour temperature",
        "night_street": "motivated night street lighting from storefronts and street lamps with readable faces",
        "golden_hour": "low warm golden-hour sunlight with consistent direction and natural exposure rolloff",
        "softbox_commercial": "controlled commercial softbox key, subtle fill and product-separating rim light",
    }
    lighting_direction = lighting_presets.get(str(ugc_lighting), str(ugc_lighting or "auto"))
    if lighting_direction == "auto":
        lighting_direction = (
            "AI must choose a physically plausible lighting setup derived from the selected environment, time of day, "
            "product material, skin tone and production mode; name its source, direction, softness, colour temperature "
            "and exposure behavior. Do not use glossy beauty light or dramatic neon unless context requires it"
        )
    ugc_rules = f"""
UGC / AFFILIATE PRODUCTION BOARD — {ugc_variant.upper()}:
- JUMLAH OUTPUT WAJIB TEPAT {scene_count} Scene; jangan menambah, mengurangi, atau menggabungkan scene.
- Platform: {ugc_platform}; tone: {ugc_tone}; emotional arc: {ugc_emotional_arc or 'problem → curiosity → try → visible proof → relief → natural CTA'}.
- Environment direction: {environment_direction}. Establish a master environment ledger (layout, time of day,
  light direction, key materials and 2-4 recurring objects). Keep it stable across connected scenes; location
  changes require a visible transition and a narrative reason.
- Lighting direction: {lighting_direction}. Manual lighting is authoritative. Keep key-light direction, practical
  sources, colour temperature, shadow softness, skin exposure and product reflections continuous between shots.
- Produce exactly {scene_count} scenes. Every scene requires one `scene_purpose`, one visible `activity`, a
  specific `expression`, `visual_composition`, `shot_type`, `camera_movement`, and a `transition_bridge` that
  motivates the next scene. Random beauty shots without narrative function are forbidden.
- Style contract: {ugc_style_contract}. Do not force luxury interiors, pastel beauty styling, or cinematic
  decoration when the product, audience, location, or selected mode does not justify it.
- Use a complete content arc: contextual hook/pain point → product appears through motivated action → clear
  handling or application → visible/sensible benefit evidence → honest reaction → CTA. Do not claim results
  that cannot be shown or supported by the supplied brief.
- Separate references conceptually: Character Master controls identity; Product Master controls packaging and
  scale; Environment Reference controls place/light only. Never borrow a face from an environment image or
  redesign product text/logo from imagination.
- Dialogue/VO must sound spoken, fit the duration, and follow the emotional state. Add breaths or micro-pauses
  only where natural. Product close-ups must follow a hand action or gaze cue, not appear as an unrelated insert.
- Viral mechanics are a repeatable test structure, not a guarantee: make the first 3 seconds an immediate visual
  or spoken hook, focus on one clear message and one primary emotion (surprise, relatability, curiosity, humour,
  or frustration), and remove greetings or slow introductions. Build the idea from WHO + DOING WHAT + WHERE,
  then connect the product to the exact moment it is naturally needed. Show evidence before the CTA.
- For `raw_amateur`, use pure environmental/participant smartphone POV. No visible presenter performing to camera,
  no narrator, voice-over, subtitles, captions, labels, logos or generated on-screen text unless explicitly requested.
  Preserve raw ambient sound: background conversation, murmurs, brief reactions, laughter, breathing, footsteps,
  cloth/handling noise and location activity. Every cut should retain at least one believable amateur flaw, but the
  subject and product action must remain understandable. Never imitate a trailer, documentary crew or travel ad.
- Fill top-level `logline`, `platform`, `video_type`, `tone`, `visual_notes`, `emotional_arc`, and
  `reference_plan`. Text overlay remains an editing instruction and is never rendered by the video model.
""" if ugc_mode else ""

    target_lang = resolve_target_language(target_country, target_lang)
    children_visual_rules = """
GAYA VISUAL WAJIB (MODE CERITA ANAK):
Setiap `prompt_for_flow` WAJIB diawali/menyisipkan gaya ini: soft 3D cartoon animation, preschool
animated series style, cute anthropomorphic animal characters, big friendly eyes, rounded chunky
proportions, bright cheerful colours, soft even lighting, simple readable background, wholesome happy mood.
DILARANG: photorealistic, cinematic chiaroscuro, dark moody lighting, harsh shadows, film grain,
anamorphic lens, teal-and-orange grading, human child characters.
`shot_type` cukup sederhana (Wide Shot / Medium Shot / Close Up) dan gerakan kamera lembut & pelan.
""" if children_mode else ""
    if children_mode:
        action_density_rules = CHILDREN_ACTION_RULES
    else:
        action_density_rules = build_dynamic_narrative_rules(
            scene_count=story_total_scene_count,
            genre=dracin_theme or visual_style or "",
            premise=premise,
            target_country=target_country,
            is_children=False,
            is_microdrama=microdrama_mode,
        )
    story_part_rules = build_story_part_rules(
        scene_offset=story_scene_offset,
        part_scene_count=scene_count,
        total_scene_count=story_total_scene_count,
        part_number=story_part_number,
        previous_context=previous_part_context,
    )
    premise_lower = str(premise or "").lower()
    reading_mode = children_mode and any(token in premise_lower for token in (
        "belajar membaca", "pembaca pemula", "bunyi awal", "huruf vokal", "suku kata",
        "kata dua suku", "kata berima", "kata yang sering", "kalimat pendek", "pemahaman bacaan",
        "urutan cerita", "membaca dengan ekspresi", "arti kata",
    ))
    reading_rules = f"""
MODE LITERASI / BELAJAR MEMBACA (WAJIB):
- Tentukan satu tingkat yang jelas: kesadaran bunyi → hubungan huruf-bunyi → suku kata/kata → kalimat → pemahaman. Jangan mencampur terlalu banyak target dalam satu video.
- Fonik, contoh kata, struktur kalimat, rima, dan pengucapan wajib mengikuti bahasa target {target_lang}; jangan menerapkan aturan fonik bahasa Indonesia atau Inggris secara universal.
- Gunakan pola `model → anak meniru/menjawab → jeda tunggu → bukti visual → pengulangan dengan variasi`. Beri jeda jawab yang nyata, bukan langsung membocorkan jawaban.
- Maksimal 1–3 unit bacaan baru per scene. Mulut speaker terlihat saat memodelkan bunyi; pengucapan lambat namun natural, tanpa nyanyian atau intonasi robotik kecuali premis meminta lagu.
- Huruf/kata/kalimat lengkap adalah `text_overlay` untuk editing, bukan teks yang diminta dirender oleh model video. `prompt_for_flow` memakai kartu dengan bentuk/simbol sederhana dan melarang generated text.
- Setiap scene mengisi tujuan belajar yang dapat diamati pada `scene_purpose`, bukan hanya hiburan. Akhiri dengan cek pemahaman singkat dan dorongan positif tanpa mempermalukan kesalahan.
""" if reading_mode else ""
    battle_vs_mode = (
        not children_mode
        and bool(re.search(r"\b(?:battle|duel|versus|vs)\b", premise_lower))
        and any(token in premise_lower for token in ("anime", "superhero", "pahlawan", "mecha", "ninja", "jurus"))
    )
    battle_vs_rules = BATTLE_VS_RULES if battle_vs_mode else ""
    # Children's mode uses anthropomorphic animals, so human ethnicity/skin-tone rules would
    # conflict with its visual contract. Its country adaptation is handled below instead.
    local_realism_rules = build_local_realism_rules(target_country) if target_country and not children_mode else ""
    children_localization_rules = build_children_localization_rules(target_country, target_lang) if children_mode else ""
    children_variation_rules = build_children_variation_packet() if children_mode and not script_mode else ""

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

    char_desc_instruction = (
        f"{character_info}\n(CATATAN PENTING: Jika nama karakter, busana, atau ciri etnis di atas masih berupa nama/budaya negara lain yang tidak cocok dengan target negara '{target_country}', Anda WAJIB mengadaptasikan nama, etnisitas, warna kulit, dan busana mereka agar 100% otentik masyarakat lokal '{target_country}'!)"
        if character_info and target_country and target_country.lower() != "indonesia"
        else (character_info or f"Otomatis rancang karakter-karakter lokal yang 100% otentik dengan budaya dan etnis '{target_country or 'internasional'}'")
    )

    system_prompt = f"""
Anda adalah Sutradara Film AI Sinematik Kelas Dunia & Visual Director untuk Google Flow Omni Flash.
Tugas Anda adalah meracik **STORYBOARD SINEMATIK KONSISTEN BANYAK KARAKTER & DYNAMIC MULTI-ANGLE CAMERA ({scene_count} ADEGAN/SCENE)**.

BAHASA OUTPUT UTAMA: {target_lang} (Semua ringkasan aksi, narasi voiceover, teks overlay, dan dialog WAJIB DITULIS DALAM BAHASA {target_lang} SECARA MUTLAK, MESKIPUN PREMIS AWAL DALAM BAHASA LAIN!)

{duration_rules}

{action_density_rules}
{story_part_rules}
{battle_vs_rules}

{microdrama_rules}
{ugc_rules}
{local_realism_rules}
{children_localization_rules}
{children_variation_rules}
{reading_rules}
{POLICY_SAFE_RULES}
{children_visual_rules}
VISUAL STYLE LOCK — PRIORITAS TERTINGGI, WAJIB SAMA DI SEMUA SCENE:
{visual_style_contract}
FINISHING LOOK LOCK: {finishing_contract}.
{auto_art_direction_text}
AUTO/MULTI CREATIVE RULES:
- "Auto" is active AI direction, never an empty/default setting. Adapt the candidate art direction to the niche
  and premise while keeping it recognisably different from generic teal-orange, rainbow, or beige templates.
- The hero object must cause, reveal, solve, measure, or visually track an event. Do not add decorative props
  with no story function. Give recurring objects exact colour, material, count, condition, and position.
- Build 2-4 supporting objects that are specific to each location and culture; vary their shapes/materials while
  maintaining the object ledger across scenes. Do not reuse the same generic phone, envelope, coffee cup, sofa,
  luxury lobby, classroom, or garden setup unless the premise genuinely requires it.
- Keep one master palette for continuity, but vary colour dominance by location/scene and reserve one accent colour
  for reveals or payoff. Manual Vibe/Lighting/Color choices override the corresponding Auto suggestion.
- Never print the internal ART token in titles, dialogue, narration, overlays, or generated visuals.
Salin kontrak gaya ini secara eksplisit ke awal SETIAP `prompt_for_flow`. Dilarang mengganti medium,
rendering technique, bentuk anatomi, material, atau jenis karakter di tengah film.
{creative_brief_rules}
{five_realism_rules}
{script_mode_rules}
{affiliate_rules}
{conversion_rules}

ATURAN UTAMA DYNAMIC MULTI-ANGLE & MULTI-CHARACTER STABILITY:
ATURAN GERAK FISIK DAN AKTING (mengalahkan tuntutan variasi kamera):
{NATURAL_ACTION_RULES}
Untuk adegan yang memang melibatkan pintu, isi interaction_plan berdasarkan tata ruang; jangan tambahkan
aksi pintu pada scene lain. Terapkan urutan berikut hanya pada operasi yang diminta:
{DOOR_INTERACTION_RULES}
CHARACTER BIBLE: Tetapkan role protagonis/antagonis/pendukung (atau peran non-konflik untuk cerita anak),
motivasi, hubungan, bahasa tubuh, rentang ekspresi, serta identitas fisik lengkap per tokoh. Antagonis tidak
harus selalu berteriak atau berwajah marah; tampilkan tujuan dan tekanan melalui akting yang bernuansa.
Deskripsi harus bisa dipakai membuat sheet: usia, bentuk wajah/mata/hidung/rahang, rambut, postur, proporsi,
warna kulit, potongan/warna/lapisan pakaian, sepatu dan lokasi aksesori. Hormati wajah referensi pengguna.
1. **Multi-Character Seed Matrix (Wajib)**: Dukung sampai 10 karakter berbeda dengan menyebutkan Seed ID unik masing-masing (misal: Main Hero Seed `{seed}`, Companion Seed `{seed+101}`, Rival Seed `{seed+202}`). Pertahankan ciri visual wajah dan baju di setiap adegan!
2. **Dynamic Multi-Angle Camera Choreography (Wajib 100% Variatif Di Setiap Scene)**:
   - Variasikan coverage bila termotivasi; kontinuitas kontak tangan, pintu dan tubuh lebih penting daripada variasi!
   - Rotasi bervariasi: `Wide Master Establishing Tracking Shot`, `Extreme Low-Angle Dynamic Hero Shot`, `Over-the-Shoulder (OTS) Medium Close-Up`, `High-Angle Birdseye Drone View`, `Dutch-Angle High Action Tracking`, `Slow Push-in Tight Close-Up`.
   - Di dalam `prompt_for_flow` SETIAP adegan, WAJIB secara eksplisit diawali dengan klausa tipe kamera sinematik tersebut! (contoh: "A 10-second Over-The-Shoulder Close-Up Shot...", "A 10-second Low Angle Dynamic Tracking Shot...").
3. **Seamless Visual Continuation Antarvideo (Wajib)**: Adegan $N+1$ melanjutkan posisi fisik, properti,
   pakaian, waktu, dan lokasi logis dari adegan $N$. Susun lokasi dalam blok 2-4 adegan berurutan; jangan
   memindahkan tokoh bolak-balik ke lokasi jauh pada setiap adegan. Jika cerita memang harus pindah lokasi,
   adegan sebelum/sesudahnya WAJIB menunjukkan jembatan visual yang masuk akal (keluar pintu, masuk kendaraan,
   tiba di lobi/gerbang), bukan teleportasi atau lompatan waktu mendadak.
3a. **Kepadatan Shot Mengikuti Isi, Bukan Dipaksakan**: Untuk konten anak/edukasi gunakan satu pengambilan
   kontinu atau 1-3 beat kamera agar aksi mudah dibaca. Untuk dialog/emosi gunakan maksimal 3 shot; drama normal
   3-4 shot; hanya aksi/perang/kejaran cepat yang boleh 4-5 shot. Semua coverage harus merekam SATU kejadian
   berantai di SATU lokasi dan waktu kontinu—bukan beberapa adegan cerita yang dijejalkan ke satu klip.
4. **Flow Prompt Professional**: Setiap `prompt_for_flow` ditulis dalam Bahasa Inggris yang murni visual, mendetail (Karakter & Seed IDs + Multi-Angle Camera Shot + Aksi Tokoh + Studio 8K Lighting).
4a. **AKSI HARUS TERJADI DI DALAM KLIP (Wajib)**: `prompt_for_flow` WAJIB mendeskripsikan gerakan yang benar-benar
   berlangsung selama klip, bukan pose diam atau tablo. Tuliskan progresi jelas memakai penanda urutan waktu
   seperti "begins by...", "then...", "and finally..." sehingga terlihat perubahan dari awal ke akhir klip.
   Contoh BENAR: "begins clutching the sealed letter, slowly steps closer to the mahogany desk, and locks eyes with an unwavering cold stare before turning away."
   Contoh SALAH: "stands in the ballroom looking sad" (statis, tidak ada perubahan — DILARANG).
   Sertakan kata kerja gerak eksplisit yang termotivasi (steps closer, sets down firmly, turns away, unrolls scroll, grips tightly, confronts, retreats, slams, snatches, shoves, collapses, lunges). Jika UGC Mode aktif, akhiri prompt dengan Aesthetic Add-On yang 100% cocok dengan tema (Girly/Pastel untuk Beauty, Corporate Luxury untuk Working Girl, Travel Vacation untuk Travel, dll.).
4b. **BAHASA AUDIO/DIALOG VIDEO (WAJIB)**: Jika karakter berbicara, WAJIB tulis dialog ASLI dalam bahasa {target_lang} di dalam `prompt_for_flow`. (TERJEMAHKAN KE {target_lang} SECARA MUTLAK!).
4c. **Tanpa Logo/Watermark (Wajib)**: Dilarang ada logo/watermark di `prompt_for_flow`.
4d. **FLOW PROMPT BLUEPRINT — DETAIL YANG DAPAT DIEKSEKUSI (WAJIB)**:
   Setiap `prompt_for_flow` harus berupa satu paragraf produksi lengkap, bukan kumpulan kata sifat generik.
   Susun isinya dalam urutan berikut:
   a) **Continuity opening**: untuk scene pertama jelaskan lokasi dan blocking awal; untuk scene berikutnya WAJIB
      mulai dengan `Continue seamlessly/directly from the previous scene...` lalu sebutkan benda, posisi,
      pose, arah pandang, cahaya, dan tata lokasi yang harus sama dari `end_state` sebelumnya.
   b) **Full identity lock**: tulis ulang deskripsi fisik, warna, pakaian, aksesori, skala tubuh, dan ciri permanen
      SETIAP karakter yang tampak. Nama/seed saja tidak cukup dan frasa kabur seperti `same character` dilarang.
   c) **Ordered visible actions**: jelaskan aksi nyata secara kronologis memakai `Begin with...`, `then...`,
      `during the final second...`, dan `End with...`. Sebutkan tangan/kaki/properti yang bergerak, siapa bereaksi,
      dan apa yang berubah; jangan hanya menulis emosi, pose, tema, atau ringkasan cerita.
   d) **Exact final frame**: kalimat `End with...` WAJIB menetapkan posisi akhir karakter, tangan, arah pandang,
      properti yang tetap/muncul/terbuka, serta komposisi frame. Isi ini harus sama secara faktual dengan `end_state`
      dan menjadi bahan pembuka scene berikutnya.
   e) **Production lock**: tutup dengan medium/style yang dipilih, lighting spesifik, palet warna, bentuk/anatomi,
      aspect composition, framing/lensa atau gerak kamera, dan kualitas gerak yang relevan.
   f) **Scene-specific negatives**: tulis larangan konkret yang mencegah kegagalan scene, misalnya `no extra
      characters`, `no object disappearance`, `no location change`, `no character redesign`, `stable anatomy`,
      `no malformed text`; tambahkan larangan sensitif sesuai tema. Jangan mengandalkan `high quality` atau `8K`.
   Panjang target setiap `prompt_for_flow` adalah 130–220 kata bahasa Inggris. Detail harus spesifik untuk scene
   tersebut; dilarang memakai paragraf template identik pada semua scene. Untuk konten anak/edukasi prioritaskan
   satu kejadian kontinu, gerakan sederhana yang terbaca, dan 1–3 beat kamera; jangan memaksakan lima cut cepat.
4e. **OBJECT LEDGER (Wajib)**: Properti persisten (kartu, kotak, tas, makanan, kendaraan, senjata, produk,
   posisi pintu/meja, dan sebagainya) harus memiliki jumlah, status, urutan, dan posisi yang konsisten. Jika pada
   akhir scene ada lima kartu dengan dua terbuka, prompt scene berikutnya harus menyebut dua tetap terbuka dan
   tiga tetap tertutup. Tidak boleh muncul, hilang, berpindah, atau berubah warna tanpa aksi visual.
4f. **SCRIPT DOCTOR & DRAMATIC FUNCTION (Wajib)**: Audit seluruh cerita sebelum menulis JSON. Setiap scene
   harus memiliki SATU fungsi utama yang jelas (hook, eskalasi, pengungkapan, konsekuensi, klimaks, atau resolusi),
   satu aksi utama, maksimal dua aksi pendukung, reaksi emosional yang terlihat, dan final frame yang kuat.
   Perbaiki kontradiksi hubungan, jabatan, motivasi, kepemilikan, bukti, dan urutan informasi tanpa mengubah premis.
   Informasi penting harus diperkenalkan sebelum dipakai; pengungkapan membutuhkan sebab/bukti/reaksi; hindari
   pengulangan dialog, permintaan maaf, atau rekonsiliasi yang tidak mengembangkan cerita. Jangan menulis pikiran
   abstrak yang tidak dapat difilmkan melalui aksi, ekspresi, dialog, atau properti.
4f-1. **DIALOG MERAKYAT & SAPAAN RELASIONAL (Wajib untuk drama)**: Dialog harus terdengar seperti orang nyata
   dari negara, daerah, kelas sosial, usia, dan hubungan yang ditetapkan—bukan bahasa buku, pidato, atau terjemahan
   literal. Gunakan sapaan relasional secara luwes dan secukupnya. Untuk konteks Indonesia, pilih sesuai hubungan:
   `Mas`, `Mbak`, `Kak`, `Dek`, `Bang`, `Bu`, `Pak`, `Nak`, `Sayang`, nama kecil, atau panggilan keluarga; jangan
   memakai semuanya sekaligus dan jangan memakai panggilan intim pada relasi yang tidak pantas. Negara lain wajib
   memakai padanan lokal yang natural. Variasikan kalimat pendek, elipsis, respons setengah kalimat, penegasan,
   dan subteks emosional tanpa membuat maksud cerita kabur. Setiap panggilan harus konsisten dengan umur, status,
   kedekatan, konflik, dan perkembangan relasi antaradegan.
4g. **DIALOG, AUDIO & LIP-SYNC LOCK (Wajib)**: Total dialog scene harus realistis untuk durasinya (10 detik
   maksimal sekitar 18–22 kata; skala proporsional untuk durasi lain). Dialog dalam `prompt_for_flow` harus sama
   persis dengan `dialogue.line`, tetap dalam bahasa {target_lang}, dan tidak boleh menambah ucapan baru. Hanya
   speaker aktif yang menggerakkan bibir; karakter lain menutup mulut dan bereaksi secara fisik. Jangan tumpuk
   dialog dengan narasi bila waktunya tidak cukup. Minta natural {target_lang} pronunciation, accurate lip-sync,
   clean dialogue, subtle room tone/SFX, dan musik tidak menutupi suara bila audio memang dipakai. Tulis dialog
   seperti percakapan manusia sehari-hari yang ringkas, kontekstual, dan emosional—bukan narasi penjelas, slogan,
   bahasa iklan, atau kalimat formal kaku. Arahkan native conversational delivery dengan variasi tempo, tekanan,
   jeda mikro, napas halus, reaksi lawan bicara, serta intonasi sesuai usia dan relasi karakter; larang suara datar,
   ritme robotik, announcer voice, synthetic smoothness, dan over-enunciation bergaya AI.
4g-1. **TULIS UNTUK DIDENGAR (Wajib)**: Pecah dialog menjadi kalimat pendek yang dapat diucapkan dalam satu napas.
   Gunakan koma, titik, elipsis, atau tanda tanya secara wajar untuk mengarahkan jeda dan intonasi; jangan menaruh
   tanda baca berlebihan. Kata penting mendapat tekanan melalui susunan kalimat dan konteks emosi, bukan huruf kapital.
   Baca secara mental: bila kalimat sulit diucapkan keras tanpa tersandung atau kehabisan napas, tulis ulang.
4g-2. **FIVE-LAYER AUDIO BLUEPRINT (Wajib setiap scene)**: Isi `audio_blueprint` dengan: (1) voice performance—
   emosi, tempo, intonasi, jeda, napas, aksen dan jarak mic; (2) ambience lokasi yang kontinu; (3) foley/SFX yang
   menyebut aksi dan frame kontak pemicunya; (4) musik/mood yang pelan serta ducking saat bicara; (5) prioritas mix
   dan kontinuitas loudness. SFX harus sinkron dengan aksi terlihat. Akustik/reverb mengikuti ukuran ruang, posisi
   karakter, dan jarak kamera. Jangan membuat ruang hampa, suara generik, napas palsu berlebihan, atau musik menutup dialog.
4h. **CAMERA FEASIBILITY & SCREEN DIRECTION (Wajib)**: Maksimal satu gerakan kamera utama per scene,
   halus dan masuk akal dalam durasi. Pertahankan posisi kiri/kanan, eyeline match, serta arah gerak antarscene.
   Gunakan wide untuk ruang/relasi, medium untuk interaksi/konflik, close-up untuk emosi, dan insert untuk bukti.
   Hindari Dutch angle, sudden zoom, random cuts, dan gerakan kamera bertentangan tanpa alasan dramatik. Variasikan
   gerak antarscene secara termotivasi: slow push-in untuk tekanan emosi, pull-back untuk isolasi/reveal, pan/tilt
   mengikuti perpindahan, lateral tracking/handheld follow untuk aksi, orbit pendek untuk perubahan relasi, dan rack
   focus untuk memindahkan perhatian. Semua gerak memiliki inertia, parallax, easing, titik mulai/akhir, dan alasan
   dramatik; bukan digital zoom acak atau gerakan mekanis kaku.
4h-1. **SPATIAL BLOCKING & ORIENTASI BENDA (Wajib)**: Untuk pintu, mobil, kursi, meja, tangga, dan properti,
   nyatakan sisi kiri/kanan frame dan sisi fisik objek, arah hadap, tangan aktif, posisi handle/engsel, arah bukaan,
   jalur tubuh, serta urutan kontak. Contoh masuk mobil: mendekati sisi pintu yang benar → tangan tertentu meraih
   handle → pintu berayun ke arah benar → tubuh pivot dan masuk → kaki terakhir masuk → pintu menutup. Pertahankan
   screen direction dan jangan mirror, teleport, berpindah pintu, menembus benda, atau membalik posisi antar-shot.
4h-2. **EMOTIONAL MACRO COVERAGE (Wajib namun selektif)**: Setiap scene drama memilih 1–2 detail yang paling
   bermakna—mata/kedipan/air mata, bibir dan rahang saat bicara, helai rambut, telinga/leher saat menoleh, atau
   jari/tangan saat menggenggam/melepas properti. Gunakan close-up, extreme close-up, insert, atau macro dengan
   fokus, anatomi, skin texture, lighting, dan arah layar stabil. Jangan memasukkan semua bagian tubuh sekaligus;
   detail harus menambah emosi, informasi, atau sebab-akibat, bukan sekadar dekorasi.
4i. **NO GENERATED TEXT (Wajib)**: `text_overlay` adalah panduan editing terpisah (2–5 kata), bukan teks yang
   dirender Flow. Jangan meminta tulisan overlay dalam `prompt_for_flow`; selalu larang subtitles, captions,
   watermark, logo, serta automatically generated on-screen text. Jika cerita memerlukan kartu/surat/ponsel,
   prioritaskan simbol atau bentuk visual sederhana dan hindari teks AI yang mudah rusak.
4j. **POST-PRODUCTION MATCH & ARTIFACT PREVENTION (Wajib)**: Tetapkan satu scene sebagai color reference lalu
   pertahankan white balance, exposure, contrast, skin tone, arah/softness cahaya, dan grade yang sama untuk blok
   lokasi/waktu yang sama. Jangan menutup mismatch dengan filter ekstrem. Di setiap prompt, sederhanakan gerak
   tangan dekat kamera, pertahankan lima jari dan kontak benda yang terbaca, stabilkan wajah/bibir/rambut/tepi
   produk, tekstur kain/kulit, shadow direction, serta geometri latar. Larang flicker, warping, texture melting,
   ghosting, lipsync drift, object morphing, dan inconsistent light. Tiga detik pertama mendapat prioritas QC tertinggi.
5. **Time Range Timestamp Wajib**: Sertakan field "time_range".
6. **ATURAN MUTLAK BAHASA OUTPUT**: SELURUH ACTION SUMMARY, NARRATION, TEXT OVERLAY, DAN NAMA KARAKTER HARUS 100% DALAM BAHASA {target_lang} DAN BERGAYA NEGARA {target_country or target_lang}. JANGAN GUNAKAN NAMA INDONESIA ATAU TEKS INDONESIA SAMA SEKALI, MESKIPUN PREMISNYA INDONESIA! TRANSLATE EVERYTHING TO {target_lang}!
{elegant_rules}

PARAMETIK REQUEST (WAJIB 100% PATUH & RELEVAN):
- Tema / Premis Utama: {premise}
- ATURAN KHUSUS TEMA: SELURUH adegan HARUS 100% menceritakan premis di atas!
- Jumlah Adegan: {scene_count} scene
- Character Seed Main: {seed}
- Deskripsi Karakter: {char_desc_instruction}
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
11. **Speaker Presence Lock (Wajib)**: Setiap `speaker_id` harus terdaftar di `characters` DAN hadir di
   `characters_in_scene`. Karakter yang tidak tercantum tidak boleh terlihat, berbicara, atau melakukan aksi penting.
12. **Timeline Arithmetic (Wajib)**: Hitung `time_range` dari jumlah kumulatif duration. Tidak boleh ada jeda,
   tumpang tindih, atau timestamp perkiraan. `scene_count` harus sama dengan panjang array `scenes`.
13. **Final Internal Audit Sebelum Output**: Verifikasi jumlah/urutan scene, duration dan time_range, ID karakter,
   kehadiran speaker, budget dialog, logika hubungan, object ledger, sambungan start/end state, bahasa, style lock,
   rasio, serta validitas JSON. Perbaiki diam-diam sebelum mengembalikan object.

OUTPUT WAJIB FORMAT JSON VALID (Tanpa markdown tambahan di luar JSON):
{{
  "film_title": "Judul Film / Cerita",
  "logline": "Satu kalimat: karakter + konteks + masalah + peran produk/tujuan cerita",
  "platform": "{ugc_platform if ugc_mode else 'Platform sesuai brief'}",
  "video_type": "{'Commercial Premium' if ugc_mode and ugc_variant == 'commercial' else 'Raw Amateur Smartphone' if ugc_mode and ugc_variant == 'raw_amateur' else 'UGC Review' if ugc_mode else 'Story Content'}",
  "tone": "{ugc_tone if ugc_mode else 'Tone sesuai brief'}",
  "visual_notes": "Cahaya, lokasi, warna dominan, tekstur, dan aturan pacing yang spesifik",
  "environment_direction": "Lokasi terpilih + alasan relevansinya, layout, waktu, arah cahaya, material, dan recurring objects",
  "lighting_direction": "Sumber, arah, softness, colour temperature, exposure, skin tone, dan product reflections",
  "emotional_arc": "{ugc_emotional_arc or 'Perubahan emosi dari hook sampai payoff'}",
  "conversion_brief": {json.dumps(ugc_conversion_brief, ensure_ascii=False)},
  "conversion_hypotheses": [{{"variant": "A", "changed_variable": "Hanya satu variabel", "hypothesis": "Alasan terukur", "hook": "Kalimat hook", "angle": "Angle", "cta": "CTA"}}],
  "reference_plan": {{"character_master": "identity only", "product_master": "packaging and scale only", "environment_reference": "location and light only"}},
  "postproduction_plan": {{"color_reference_scene": 1, "match_order": "white balance then exposure then restrained grade", "artifact_priority": "first 3 seconds; hands, mouth, face, hair and product edges", "audio_review": "ambience continuity, selective foley, lipsync onset and headphone check"}},
  "genre_style": "Gaya Visual & Mood Sinematik",
  "art_direction": "Mood board produksi premium",
  "visual_style": "{visual_style}",
  "visual_vibe": "{visual_vibe}",
  "lighting_style": "{lighting_style}",
  "color_palette": "{color_palette}",
  "realism_audit": {{
    "visual_realism": "Bukti medium, cahaya, anatomi/material, dan detail bebas artefak",
    "character_consistency": "Lock wajah/model, outfit, produk, properti, dan lingkungan",
    "story_realism": "Konteks, tujuan, sebab-akibat, dan dialog natural",
    "motion_realism": "Gerak tubuh, kontak objek, tatapan, ekspresi, dan kamera wajar",
    "humanization": "Jeda, napas, intonasi, ambient sound, dan editing tertahan"
  }},
  "character_seed": {seed},
  "consistent_characters": "Deskripsi Lengkap Karakter-Karakter",
  "characters": [
    {{
      "id": 1,
      "name": "Nama Karakter",
      "source_actor_id": "ID aktor persis dari daftar aktor spesifik, atau kosong jika bukan aktor tersimpan",
      "seed": {seed},
      "description": "Deskripsi visual lengkap",
      "visual_signature": "Kombinasi pakaian, aksesori, rambut/usia/ciri wajah yang permanen dan unik",
      "role": "protagonis / antagonis / pendukung / mentor / peran sesuai cerita",
      "motivation": "Tujuan konkret, hambatan dan alasan bertindak",
      "body_language": "Postur dasar, kebiasaan gerak dan respons saat tertekan yang natural",
      "expression_range": "Netral, menyimak, emosi tertahan, dan reaksi intens sesuai karakter",
      "vocal_signature": "Identitas timbre, usia vokal dan aksen konsisten; pitch, ritme, napas dan volume fleksibel sesuai emosi",
      "relationship_to_others": "Hubungan, tingkat keakraban, status sosial, dan sapaan natural kepada karakter lain"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "affiliate_scene": false,
      "time_range": "0:00–0:02",
      "title": "Judul Adegan 1 (misal Opening Activity)",
      "scene_purpose": "Hook / context / problem / product reveal / demonstration / proof / payoff / CTA",
      "conversion_beat": "hook / problem / solution / proof / cta",
      "activity": "Aktivitas fisik tunggal yang benar-benar dilakukan model",
      "expression": "Ekspresi awal, pemicu, lalu perubahan ekspresi yang terlihat",
      "visual_composition": "Posisi model, produk, foreground/background, eyeline, dan ruang negatif",
      "spatial_continuity": "Kiri/kanan frame, arah hadap/gerak, tangan aktif, orientasi dan urutan kontak pintu/kendaraan/properti",
      "interaction_plan": {{"object": "Properti aktif saja, kosong bila tidak ada", "initial_state": "Keadaan dan orientasi awal", "actor_side": "Sisi fisik aktor dan kamera", "active_hand": "Tangan yang dipakai", "mechanism": "Engsel/handle/arah ayun atau geser bila relevan", "contact_sequence": "Jangkau, genggam, gerak, ruang bebas tubuh, pelepasan sesuai aksi", "final_state": "Keadaan akhir yang terlihat"}},
      "shot_flow": [
        {{"time": "0-2s", "angle": "Low Angle Close Up", "description": "Aksi pembuka karakter dan ekspresi natural"}},
        {{"time": "2-4s", "angle": "Medium Wide Shot", "description": "Interaksi dengan ruang dan lingkungan sekitar"}},
        {{"time": "4-6s", "angle": "Over-The-Shoulder / Macro Detail", "description": "Fokus objek atau detail aksi tangan/mata"}},
        {{"time": "6-8s", "angle": "Medium Close / Dynamic Reaction", "description": "Puncak reaksi emosi atau titik balik situasi"}},
        {{"time": "8-10s", "angle": "Wide Shot / Final Look", "description": "Resolusi akhir adegan sebelum berganti scene"}}
      ],
      "emotional_detail": "Satu atau dua detail close-up/macro yang bermakna beserta pemicu dan fungsi emosionalnya",
      "audio_blueprint": {{
        "voice_performance": "Emosi, intonasi, tempo, jeda, napas, aksen lokal, jarak dan arah suara",
        "ambience": "Room tone/lingkungan spesifik yang kontinu dan berubah hanya jika lokasi berubah",
        "foley_sfx": "Cue suara benda/tubuh yang sinkron tepat dengan kontak atau gerakan terlihat",
        "music": "Mood musik rendah dan titik ducking saat dialog, atau none untuk raw amateur",
        "mix": "Voice depan; ambience 15–25%; musik 10–20% dan ducked; foley jelas hanya saat aksi"
      }},
      "transition_bridge": "Aksi, arah pandang, properti, atau match cut yang mengantar scene berikutnya",
      "action_summary": "Ringkasan aksi adegan (WAJIB DITULIS DALAM BAHASA {target_lang} SECARA KESELURUHAN)",
      "shot_type": "Framing baku, pilih SATU: Extreme Wide Shot / Wide Shot / Medium Shot / Medium Close Up / Close Up / Extreme Close Up / Over-The-Shoulder / Point of View",
      "characters_in_scene": [1],
      "dialogue": [{{"speaker_id": 1, "line": "Kalimat persis", "screen_position": "left/center/right"}}],
      "start_state": "Posisi tubuh, tangan, properti, arah pandang, dan lokasi pada frame awal",
      "end_state": "Posisi tubuh, tangan, properti, arah pandang, dan lokasi pada frame akhir",
      "prompt_for_flow": "English production paragraph: explicit opening state, visible identity and wardrobe, one main action with readable physical contact, motivated coverage, natural exact dialogue, and final continuity frame. Retain one continuous view during door/contact operations; no forced cut count or constant gestures.",
      "text_overlay": "Panduan teks editing 2-5 kata dalam bahasa {target_lang}; jangan minta Flow merender teks ini di dalam prompt_for_flow",
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
        result = generate_text(user_contents, json_output=True)
        text_resp = _extract_json_text(result.text)
        storyboard = json.loads(text_resp)
        actual_scene_count = len(storyboard.get("scenes") or [])
        if 0 < actual_scene_count < target_scene_count:
            log.info(
                "Model menghasilkan %d dari %d scene. Melanjutkan sisa scene secara otomatis...",
                actual_scene_count, target_scene_count
            )
            storyboard = _extend_storyboard_scenes(
                storyboard=storyboard,
                target_count=target_scene_count,
                premise=premise,
                target_lang=target_lang,
                seed=seed,
                fixed_scene_duration=fixed_scene_duration,
            )
            actual_scene_count = len(storyboard.get("scenes") or [])

        if actual_scene_count > target_scene_count:
            storyboard["scenes"] = (storyboard.get("scenes") or [])[:target_scene_count]
            actual_scene_count = len(storyboard.get("scenes") or [])

        if actual_scene_count != target_scene_count:
            raise ValueError(
                f"Provider menghasilkan {actual_scene_count} scene, seharusnya tepat {target_scene_count} scene."
            )
        for local_index, scene in enumerate(storyboard.get("scenes") or [], start=1):
            scene["scene_number"] = story_scene_offset + local_index
        storyboard = _complete_storyboard_scene_fields(storyboard)
        storyboard = _repair_storyboard_quality(
            storyboard,
            premise=premise,
            target_lang=target_lang,
            scene_count=target_scene_count,
            fixed_scene_duration=fixed_scene_duration,
            children_mode=children_mode,
            script_mode=script_mode,
            story_scene_offset=story_scene_offset,
            story_total_scene_count=story_total_scene_count,
        )
        storyboard = _audit_story_engagement_quality(
            storyboard,
            children_mode=children_mode,
            script_mode=script_mode,
            story_scene_offset=story_scene_offset,
            story_total_scene_count=story_total_scene_count,
        )
        storyboard = _audit_dramatic_arc(
            storyboard,
            children_mode=children_mode,
            script_mode=script_mode,
            story_scene_offset=story_scene_offset,
            story_total_scene_count=story_total_scene_count,
        )
        storyboard = _audit_story_part_boundary(
            storyboard,
            children_mode=children_mode,
            script_mode=script_mode,
            story_scene_offset=story_scene_offset,
            story_total_scene_count=story_total_scene_count,
        )
        storyboard["raw_response"] = text_resp
        storyboard["characters"] = ensure_unique_character_signatures(storyboard.get("characters") or [])
        storyboard["character_seed"] = seed
        storyboard["children_mode"] = children_mode
        storyboard["visual_style"] = visual_style
        storyboard["visual_vibe"] = visual_vibe
        storyboard["lighting_style"] = lighting_style
        storyboard["color_palette"] = color_palette
        storyboard["auto_art_direction"] = auto_art_direction_text
        storyboard["target_lang"] = target_lang
        storyboard["target_country"] = target_country
        storyboard["script_mode"] = script_mode
        storyboard["ugc_variant"] = ugc_variant
        storyboard["ugc_platform"] = ugc_platform
        storyboard["ugc_tone"] = ugc_tone
        storyboard["ugc_environment"] = ugc_environment
        storyboard["ugc_lighting"] = ugc_lighting
        storyboard["ugc_conversion_brief"] = ugc_conversion_brief
        storyboard["creative_brief"] = creative_brief
        storyboard["realism_framework"] = "visual, character consistency, story, motion, audio, humanization"
        if script_mode:
            storyboard["source_script"] = premise
        if affiliate_config.get("enabled"):
            storyboard["affiliate_product"] = affiliate_config
        storyboard["generated_via"] = result.provider
        storyboard["generated_model"] = result.model
        storyboard["story_parts"] = _story_parts_meta(
            story_part_number=story_part_number,
            story_scene_offset=story_scene_offset,
            target_scene_count=target_scene_count,
            story_total_scene_count=story_total_scene_count,
        )
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
            if 0 < actual_scene_count < target_scene_count:
                storyboard = _extend_storyboard_scenes(
                    storyboard=storyboard,
                    target_count=target_scene_count,
                    premise=premise,
                    target_lang=target_lang,
                    seed=seed,
                    fixed_scene_duration=fixed_scene_duration,
                )
                actual_scene_count = len(storyboard.get("scenes") or [])

            if actual_scene_count > target_scene_count:
                storyboard["scenes"] = (storyboard.get("scenes") or [])[:target_scene_count]
                actual_scene_count = len(storyboard.get("scenes") or [])

            if actual_scene_count != target_scene_count:
                raise ValueError(
                    f"Fallback menghasilkan {actual_scene_count} scene, seharusnya tepat {target_scene_count} scene."
                )
            for local_index, scene in enumerate(storyboard.get("scenes") or [], start=1):
                scene["scene_number"] = story_scene_offset + local_index
            storyboard = _complete_storyboard_scene_fields(storyboard)
            storyboard = _repair_storyboard_quality(
                storyboard,
                premise=premise,
                target_lang=target_lang,
                scene_count=target_scene_count,
                fixed_scene_duration=fixed_scene_duration,
                children_mode=children_mode,
                script_mode=script_mode,
                story_scene_offset=story_scene_offset,
                story_total_scene_count=story_total_scene_count,
            )
            storyboard = _audit_story_engagement_quality(
                storyboard,
                children_mode=children_mode,
                script_mode=script_mode,
                story_scene_offset=story_scene_offset,
                story_total_scene_count=story_total_scene_count,
            )
            storyboard = _audit_dramatic_arc(
                storyboard,
                children_mode=children_mode,
                script_mode=script_mode,
                story_scene_offset=story_scene_offset,
                story_total_scene_count=story_total_scene_count,
            )
            storyboard = _audit_story_part_boundary(
                storyboard,
                children_mode=children_mode,
                script_mode=script_mode,
                story_scene_offset=story_scene_offset,
                story_total_scene_count=story_total_scene_count,
            )
            storyboard["raw_response"] = web_txt
            storyboard["characters"] = ensure_unique_character_signatures(storyboard.get("characters") or [])
            storyboard["character_seed"] = seed
            storyboard["children_mode"] = children_mode
            storyboard["visual_style"] = visual_style
            storyboard["visual_vibe"] = visual_vibe
            storyboard["lighting_style"] = lighting_style
            storyboard["color_palette"] = color_palette
            storyboard["auto_art_direction"] = auto_art_direction_text
            storyboard["target_lang"] = target_lang
            storyboard["target_country"] = target_country
            storyboard["script_mode"] = script_mode
            storyboard["ugc_variant"] = ugc_variant
            storyboard["ugc_platform"] = ugc_platform
            storyboard["ugc_tone"] = ugc_tone
            storyboard["ugc_environment"] = ugc_environment
            storyboard["ugc_lighting"] = ugc_lighting
            storyboard["ugc_conversion_brief"] = ugc_conversion_brief
            storyboard["creative_brief"] = creative_brief
            storyboard["realism_framework"] = "visual, character consistency, story, motion, audio, humanization"
            if script_mode:
                storyboard["source_script"] = premise
            if affiliate_config.get("enabled"):
                storyboard["affiliate_product"] = affiliate_config
            storyboard["generated_via"] = "web2api_fallback"
            storyboard["story_parts"] = _story_parts_meta(
                story_part_number=story_part_number,
                story_scene_offset=story_scene_offset,
                target_scene_count=target_scene_count,
                story_total_scene_count=story_total_scene_count,
            )
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
5. `prompt_for_flow` wajib 130–220 kata dan berupa satu paragraf produksi yang konkret dengan urutan:
   - pembuka lokasi, blocking, dan kondisi properti;
   - deskripsi fisik, pakaian, aksesori, skala, serta ciri permanen setiap karakter yang tampil (nama/seed saja tidak cukup);
   - aksi kronologis memakai `Begin with...`, `then...`, `during the final second...`, dan `End with...`;
   - frame akhir yang menetapkan posisi tubuh, tangan, arah pandang, dan status semua properti;
   - style/medium, lighting, palet, aspect composition, framing/lensa, dan camera movement;
   - larangan spesifik seperti no extra characters, no object disappearance, no location change, no character redesign,
     stable anatomy, no malformed text. Jangan mengganti detail konkret dengan kata generik `high quality` atau `8K`.
6. Jika adegan merupakan kelanjutan, awali dengan `Continue seamlessly from the previous scene` dan pertahankan
   object ledger secara eksplisit: jumlah, urutan, status terbuka/tertutup, warna, dan posisi properti tidak berubah
   kecuali perubahan tersebut benar-benar diperlihatkan di dalam klip.

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
