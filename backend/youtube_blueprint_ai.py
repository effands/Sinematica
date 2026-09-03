"""AI-powered idea and blueprint generator for YouTube Blueprint Studio."""

import json
import logging
from typing import Any, Dict, Optional

from .text_generation import generate_text

log = logging.getLogger("sinematica.youtube_blueprint_ai")


def _extract_json_text(raw: str) -> str:
    """Extract clean JSON text even if wrapped in markdown fences."""
    text = (raw or "").strip()
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return text


def suggest_youtube_blueprint(
    topic: str = "",
    format_type: str = "cinematic_storytelling",
    market: str = "United States",
    language: str = "Native US English",
) -> Dict[str, Any]:
    """Generate a comprehensive, evidence-first YouTube production blueprint from a topic or idea."""
    topic_context = f'Topik / Ide Utama: "{topic.strip()}"' if topic and topic.strip() else "Topik: Buat satu konsep video YouTube viral, berbobot tinggi, dan berdaya saing tinggi yang sedang tren."

    brand_map = {
        "cinematic_storytelling": "cinematic_deep_dive",
        "ambience": "immersive_audio",
        "shorts": "cinematic_deep_dive",
    }
    recommended_brand = brand_map.get(format_type, "cinematic_deep_dive")

    prompt = f"""
Anda adalah Chief YouTube Content Strategist & Production Director kelas dunia.
Tugas Anda adalah merancang BLUEPRINT PRODUKSI YOUTUBE LENGKAP & EVIDENCE-FIRST (berkualitas tinggi, orisinal, dan siap produksi).

KONTEKS REQUEST:
- {topic_context}
- Format Video: {format_type} (Pilihan: cinematic_storytelling, ambience, shorts)
- Target Market / Negara: {market or "United States"}
- Bahasa & Varian: {language or "Native US English"}

PANDUAN EVIDENCE-FIRST:
1. Micro-Niche & Audience: Sangat spesifik (bukan umum seperti finance/gaming), jelaskan usia, kebutuhan emosional, dan pain point audiens.
2. Hook / Cold Open: 3 detik pertama langsung ke poin tanpa bumper klise.
3. Competitor Gap & Original Angle: Jelaskan apa yang dilewatkan kreator lain dan apa nilai tambah unik video ini.
4. Retention Contract: Macro open loop yang kuat dan payoff tuntas sebelum next-view bridge.
5. 7 Modul Super: Sertakan tesis editorial, content moat, tata kelola lisensi, audit audio & lokalisasi, ledger kontinuitas, dan register risiko.

OUTPUT WAJIB FORMAT JSON VALID (HANYA JSON, TANPA PENJELASAN DI LUAR JSON):
{{
  "format": "{format_type}",
  "market": "{market or 'United States'}",
  "language": "{language or 'Native US English'}",
  "micro_niche": "Micro-niche spesifik dan bertarget",
  "core_audience": "Profil demografis, situasi hidup, dan motivasi penonton",
  "channel_promise": "Janji nilai yang konsisten didapat penonton",
  "demand_evidence": "Bukti data pencarian, pertanyaan hangat, dan volume minat nyata",
  "competitor_gap": "Kelemahan/kekosongan konten kompetitor yang dieksploitasi",
  "original_angle": "Sudut pandang segar, data unik, atau narasi diferensiasi",
  "hook_cold_open": "Kalimat hook pembuka 0-3 detik pertama yang mematikan",
  "macro_open_loop": "Pertanyaan misteri/tantangan utama yang mengikat retensi",
  "payoff_next_view": "Klimaks jawaban tuntas + jembatan rekomendasi video berikutnya",
  "brand_architecture": "{recommended_brand}",
  "colors": "Kombinasi 2 warna primer estetik (misal: Deep Midnight Navy + Burnished Gold)",
  "font": "Font signature berlisensi yang bersih dan berkarakter (misal: Montserrat + Cinzel)",
  "main_keyword": "Keyword utama bervolume tinggi",
  "relevant_keywords": "3-5 keyword turunan dipisahkan koma",
  "long_tail_intent": "Pertanyaan panjang / intent spesifik pencarian audiens",
  "sources_and_licensing": "Daftar sumber primer/jurnal, hak footage, aset audio berlisensi, dan batasan klaim",
  "editorial_thesis": "Opini/wawasan intelektual khas channel terhadap topik ini",
  "content_moat": "Faktor keunikan produksi/analisis yang membuat konten sulit ditiru kompetitor",
  "fleet_governance": "Peran tim: Lead Researcher, Scriptwriter, Visual Artist, Sound Designer, Fact-Checker",
  "production_cost": 35,
  "ai_disclosure": "review_required",
  "human_contribution": "Riset mendalam data historis/ilmiah, kurasi sudut pandang, penulisan script orisinal, dan audio mastering",
  "localization_qa": "Adaptasi idiom budaya lokal, terminologi native, satuan metrik/imperial, dan tone kesopanan",
  "audio_qa": "Sound design berlapis: room tone kontinu, foley kontekstual, musik ducked saat voiceover, master -14 LUFS",
  "continuity_ledger": "Catatan lock aset visual, palet warna adegan, pencahayaan konsisten, dan properti penting",
  "loop_ledger": "Daftar open loop 1, 2, 3 dibuka berurutan dan ditutup tepat di 80-95% durasi",
  "risk_register": "Mitigasi copyright klaim, verifikasi keakuratan fakta, kepatuhan terms platform, dan disclaimers"
}}
"""

    try:
        res = generate_text(prompt, json_output=True)
        raw_json = _extract_json_text(res.text)
        data = json.loads(raw_json)
        return data
    except Exception as ex:
        log.error("Gagal generate YouTube blueprint via AI: %s", ex)
        raise RuntimeError(f"Gagal generate YouTube blueprint via AI: {ex}") from ex
