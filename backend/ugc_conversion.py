"""Deterministic conversion brief helpers for UGC affiliate storyboards."""

from __future__ import annotations

from typing import Any, Mapping


HOOK_TYPES = {"pattern_interrupt", "problem", "curiosity_gap", "bold_claim", "relatable"}
AWARENESS_LEVELS = {"unaware", "problem_aware", "solution_aware", "product_aware"}
OBJECTIVES = {"product_click", "checkout", "purchase", "dm", "lead"}


def _text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def normalize_conversion_brief(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    hook_type = _text(source.get("hook_type"), 40).lower()
    awareness = _text(source.get("awareness_level"), 40).lower()
    objective = _text(source.get("objective"), 40).lower()
    variants = source.get("variant_count", 3)
    try:
        variants = max(1, min(5, int(variants)))
    except (TypeError, ValueError):
        variants = 3
    return {
        "enabled": bool(source.get("enabled")),
        "audience": _text(source.get("audience")),
        "objective": objective if objective in OBJECTIVES else "product_click",
        "why_now": _text(source.get("why_now")),
        "awareness_level": awareness if awareness in AWARENESS_LEVELS else "problem_aware",
        "hook_type": hook_type if hook_type in HOOK_TYPES else "problem",
        "hook": _text(source.get("hook")),
        "angle": _text(source.get("angle")),
        "problem": _text(source.get("problem")),
        "agitate": _text(source.get("agitate")),
        "solution": _text(source.get("solution")),
        "proof": _text(source.get("proof")),
        "cta": _text(source.get("cta")),
        "variant_count": variants,
        "test_variable": _text(source.get("test_variable"), 40) or "hook",
    }


def conversion_brief_issues(brief: Mapping[str, Any]) -> list[str]:
    if not brief.get("enabled"):
        return []
    issues = []
    for key, label in (
        ("audience", "audiens spesifik"), ("hook", "hook 3 detik"),
        ("problem", "problem"), ("solution", "solution/manfaat"),
        ("proof", "proof yang dapat ditampilkan"), ("cta", "CTA"),
    ):
        if not _text(brief.get(key)):
            issues.append(f"Belum ada {label}.")
    if not _text(brief.get("why_now")):
        issues.append("Alasan bertindak sekarang belum diisi; jangan mengarang urgensi atau stok.")
    return issues


def build_conversion_prompt(raw: Mapping[str, Any] | None) -> str:
    brief = normalize_conversion_brief(raw)
    if not brief["enabled"]:
        return ""
    return f"""
UGC AFFILIATE CONVERSION SYSTEM — PRIORITAS TINGGI:
- Audiens tunggal: {brief['audience'] or 'belum ditentukan'}.
- Objective terukur: {brief['objective']}. Alasan bertindak sekarang: {brief['why_now'] or 'tidak ada; jangan mengarang urgensi'}.
- Awareness: {brief['awareness_level']}. Sesuaikan pesan: unaware=edukasi/cerita; problem-aware=solusi dan harapan;
  solution-aware=diferensiasi yang terbukti; product-aware=proof, penawaran sah, dan CTA.
- Hook 0–3 detik: tipe {brief['hook_type']}; kalimat: {brief['hook'] or 'buat berdasarkan problem tanpa clickbait'}.
- Angle utama: {brief['angle'] or 'solusi/keinginan audiens, bukan daftar fitur'}.
- PAS: Problem={brief['problem'] or '-'}; Agitate={brief['agitate'] or '-'}; Solution={brief['solution'] or '-'}.
- Proof wajib terlihat atau terdengar dan tidak boleh direkayasa: {brief['proof'] or 'demo penggunaan yang dapat diamati'}.
- CTA: {brief['cta'] or 'ajakan jelas tanpa urgensi palsu'}.
- Struktur waktu wajib: Hook → Problem → Solution → Proof → CTA. Tidak ada logo, salam, atau intro sebelum hook.
- Setiap beat harus punya fungsi konversi dan perubahan visual. Untuk short-form, gunakan perubahan visual bermakna
  sekitar tiap 2–3 detik tanpa jump cut acak. Tuntaskan open loop sebelum CTA.
- Klaim kesehatan, hasil, harga, diskon, stok, bonus, testimoni, dan before-after hanya boleh dipakai bila diberikan
  pengguna atau terbukti dari aset. Jangan menjamin hasil, membuat testimoni fiktif, atau menciptakan urgensi palsu.
- Buat {brief['variant_count']} hipotesis variasi; ubah HANYA `{brief['test_variable']}` per variasi. Isi utama, produk,
  offer, durasi, dan variabel lain tetap agar hasil uji dapat dibandingkan.
""".strip()


def calculate_funnel_metrics(raw: Mapping[str, Any] | None) -> dict[str, float | None]:
    source = raw if isinstance(raw, Mapping) else {}
    def number(key: str) -> float:
        try:
            return max(0.0, float(source.get(key) or 0))
        except (TypeError, ValueError):
            return 0.0
    impressions, three_second, completed = number("impressions"), number("three_second_views"), number("completed_views")
    clicks, purchases = number("clicks"), number("purchases")
    spend, revenue = number("spend"), number("revenue")
    ratio = lambda part, whole: round(part / whole * 100, 2) if whole > 0 else None
    return {
        "hook_rate": ratio(three_second, impressions),
        "hold_rate": ratio(completed, three_second),
        "ctr": ratio(clicks, impressions),
        "cvr": ratio(purchases, clicks),
        "roas": round(revenue / spend, 2) if spend > 0 else None,
    }
