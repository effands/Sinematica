from backend.content_quality import audit_reference_asset, build_creative_brief_prompt, build_five_realism_prompt, build_scene_blueprint_guard, normalize_creative_brief


def test_empty_brief_is_completed_from_production_context():
    brief = normalize_creative_brief({}, premise="Review acne patch", aspect_ratio="portrait", target_country="Indonesia", target_lang="Indonesia", scene_count=3, duration_seconds=15)
    assert brief["background"] == "Review acne patch"
    assert "portrait" in brief["result"] and "15 detik" in brief["result"]


def test_brief_prompt_preserves_constraints_and_usp():
    brief = normalize_creative_brief({"product_value": "Tipis dan melindungi jerawat", "constraints": "Tanpa hard selling"}, premise="UGC skincare", aspect_ratio="portrait")
    prompt = build_creative_brief_prompt(brief)
    assert "Tipis dan melindungi jerawat" in prompt
    assert "Tanpa hard selling" in prompt
    assert "1-2 manfaat" in prompt


def test_realism_rules_are_medium_aware():
    live = build_five_realism_prompt("live_action")
    anime = build_five_realism_prompt("anime_2d")
    assert "pori" in live and "pori" not in anime
    assert "Character Consistency" in anime and "micro-pause" in anime
    assert "momentum" in live


def test_unreadable_asset_is_flagged_instead_of_crashing(tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_text("not an image", encoding="utf-8")
    report = audit_reference_asset(str(broken), "product")
    assert report["status"] == "needs_review"
    assert "unreadable_image" in report["issues"]


def test_scene_blueprint_survives_final_prompt_rewrite():
    guard = build_scene_blueprint_guard({
        "scene_purpose": "product proof",
        "expression": "ragu menjadi lega",
        "spatial_continuity": "Maya di kiri mobil, tangan kanan pada handle pintu kiri",
        "emotional_detail": "macro jari melepaskan handle setelah pintu tertutup",
        "transition_bridge": "tatapan turun ke produk",
    })
    assert "product proof" in guard
    assert "ragu menjadi lega" in guard
    assert "random coverage" in guard
    assert "same correct side" in guard
    assert "never mirror" in guard
    assert "natural inertia" in guard
    assert "macro inserts" in guard
