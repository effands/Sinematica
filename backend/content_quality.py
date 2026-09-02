"""Shared creative-brief and realism rules for storyboard and render stages."""

from typing import Any, Dict, Optional
from pathlib import Path

BRIEF_KEYS = ("background", "result", "audience", "product_value", "execution", "constraints")


def normalize_creative_brief(raw: Optional[Dict[str, Any]], *, premise: str, aspect_ratio: str,
                             target_country: str = "", target_lang: str = "", scene_count: int = 0,
                             duration_seconds: Optional[int] = None) -> Dict[str, str]:
    source = raw if isinstance(raw, dict) else {}
    brief = {key: str(source.get(key) or "").strip() for key in BRIEF_KEYS}
    brief["background"] = brief["background"] or premise.strip()
    brief["result"] = brief["result"] or (f"Storyboard video {aspect_ratio}, {scene_count} scene" + (f", sekitar {duration_seconds} detik" if duration_seconds else ""))
    brief["audience"] = brief["audience"] or f"Audiens {target_country or 'sesuai konteks cerita'}; bahasa {target_lang or 'sesuai target'}"
    brief["product_value"] = brief["product_value"] or "Tidak ada produk; fokus pada nilai cerita."
    brief["execution"] = brief["execution"] or "AI menentukan hook, tone, alur, dan CTA yang paling alami dari premis."
    brief["constraints"] = brief["constraints"] or "Jaga kontinuitas, hindari klaim tanpa bukti, artefak AI, dan editing berlebihan."
    return brief


def build_creative_brief_prompt(brief: Dict[str, str]) -> str:
    return """
B.R.I.E.F — SUMBER KEBENARAN KREATIF (WAJIB):
- Background: {background}
- Result: {result}
- Intended Audience: {audience}
- Product / Pain Point / USP: {product_value}
- Execution (angle, tone, hook, pesan, CTA): {execution}
- Final Constraints: {constraints}
Semua hook, script, storyboard, dialog, visual, audio, CTA, dan metadata harus diturunkan dari brief ini.
Jika ada konflik, Final Constraints mengalahkan asumsi AI. Jangan mengarang klaim produk. Untuk konten produk,
mulai dari konteks/pain point manusia, demonstrasikan hanya 1-2 manfaat paling relevan, lalu hadirkan CTA secara wajar.
""".format(**brief).strip()


def build_five_realism_prompt(visual_style: str = "live_action") -> str:
    visual = ("kulit bertekstur alami (pori, detail halus, sedikit asimetri), rambut dan kain fisikal, warna kulit wajar, pencahayaan konsisten, tanpa wajah lilin/beauty-filter atau artefak AI" if visual_style == "live_action" else "anatomi, material, garis, shading, dan proporsi harus autentik serta konsisten dengan medium terpilih; tanpa artefak atau pergantian gaya")
    return f"""
LIMA PARAMETER REALISM — AUDIT SETIAP SCENE SEBELUM JSON:
1. Visual Realism: {visual}.
2. Character Consistency: wajah/model, usia, tubuh, rambut, outfit, aksesori, produk, dan lingkungan terkunci; perubahan hanya melalui aksi yang terlihat.
3. Story Realism: setiap scene punya konteks, tujuan, sebab-akibat, dan reaksi; dialog singkat seperti manusia berbicara, bukan membaca iklan atau menjelaskan hal yang sudah terlihat.
4. Motion Realism: berat tubuh, momentum, kontak tangan-properti, kedipan, napas, tatapan, ekspresi, dan inersia kamera wajar; tanpa gerak melayang, patah, morphing, atau glitch.
5. Humanization: sisipkan micro-pause/napas/keraguan alami bila relevan, room tone dan ambient sound lokasi, intonasi sesuai emosi, serta editing/camera movement yang tertahan.
Prompt scene harus menyebut bukti visual/audio konkret, bukan sekadar kata 'realistic'.
""".strip()


def build_render_realism_guard(storyboard: Dict[str, Any]) -> str:
    environment = str(storyboard.get("environment_direction") or storyboard.get("ugc_environment") or "").strip()
    environment_lock = f" MASTER ENVIRONMENT LOCK: {environment}. Keep layout, time, light direction, materials and recurring objects stable." if environment and environment != "auto" else ""
    lighting = str(storyboard.get("lighting_direction") or storyboard.get("ugc_lighting") or "").strip()
    lighting_lock = f" MASTER LIGHTING LOCK: {lighting}. Preserve motivated source direction, softness, colour temperature, exposure and product reflections." if lighting and lighting != "auto" else ""
    return "\n\nREALISM & HUMANIZATION LOCK (REASSERT AFTER REWRITE): " + build_five_realism_prompt(str(storyboard.get("visual_style") or "live_action")).replace("\n", " ") + environment_lock + lighting_lock


def build_scene_blueprint_guard(scene: Dict[str, Any]) -> str:
    fields = [
        ("purpose", scene.get("scene_purpose")), ("activity", scene.get("activity") or scene.get("action_summary")),
        ("expression", scene.get("expression")), ("composition", scene.get("visual_composition")),
        ("transition", scene.get("transition_bridge")),
    ]
    values = [f"{label}: {str(value).strip()}" for label, value in fields if str(value or "").strip()]
    return "\n\nSTORYBOARD BLUEPRINT LOCK: " + "; ".join(values) + ". Execute these directions visibly; do not replace them with random coverage." if values else ""


def audit_reference_asset(path: str, asset_type: str = "character") -> Dict[str, Any]:
    """Record objective input-quality signals without pretending to detect faces/logos."""
    from PIL import Image, ImageFilter, ImageStat

    source = Path(path)
    report: Dict[str, Any] = {"path": str(source), "asset_type": asset_type, "status": "needs_review", "issues": []}
    try:
        with Image.open(source) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            sample = rgb.copy()
            sample.thumbnail((480, 480))
            brightness = sum(ImageStat.Stat(sample.convert("L")).mean)
            edge_detail = sum(ImageStat.Stat(sample.convert("L").filter(ImageFilter.FIND_EDGES)).mean)
            issues = []
            if width * height < 1_000_000 or min(width, height) < 720:
                issues.append("low_resolution")
            if brightness < 48:
                issues.append("underexposed")
            elif brightness > 218:
                issues.append("overexposed")
            if edge_detail < 7:
                issues.append("possible_blur_or_low_detail")
            report.update({
                "width": width, "height": height,
                "brightness": round(brightness, 1), "edge_detail": round(edge_detail, 1),
                "issues": issues, "status": "production_ready" if not issues else "needs_improvement",
                "manual_checks": (["face_clear", "natural_expression", "no_occlusion"] if asset_type == "character" else ["logo_clear", "label_legible", "package_not_cropped"]),
            })
    except Exception as exc:
        report["issues"] = ["unreadable_image"]
        report["error"] = str(exc)
    return report
