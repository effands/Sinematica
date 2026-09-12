from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_executor_has_global_storyboard_phase_before_video_phase():
    source = (ROOT / "backend" / "jobs_executor.py").read_text(encoding="utf-8")

    storyboard_phase = source.index("storyboard_prebuilt")
    storyboard_complete = source.index("selesai sebagai 1 Image", storyboard_phase)
    video_phase = source.index("# Step 3: Render each scene video", storyboard_phase)
    video_submit = source.index("generate_video_r2v", video_phase)

    assert storyboard_phase < storyboard_complete < video_phase < video_submit
    assert "TAHAP 2/3" in source[storyboard_phase:video_phase]
    assert "TAHAP 3/3" in source[video_phase:]


def test_storyboard_phase_keeps_profile_rotation_for_quota_failures():
    source = (ROOT / "backend" / "jobs_executor.py").read_text(encoding="utf-8")
    storyboard_phase = source.index("storyboard_prebuilt")
    video_phase = source.index("# Step 3: Render each scene video", storyboard_phase)
    phase = source[storyboard_phase:video_phase]

    assert "sb_candidates" in phase
    assert "is_flow_quota_error" in phase
    assert "quota_exhausted" in phase


def test_storyboard_generation_does_not_auto_submit_video_from_frontend():
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "Storyboard selesai sebagai Image" in source
    assert "setTimeout(() => {\n          if (currentStoryboard && !btnSend.disabled) btnSend.click();" not in source


def test_failover_rekeys_storyboard_and_continuity_per_scene_and_profile():
    source = (ROOT / "backend" / "jobs_executor.py").read_text(encoding="utf-8")

    assert "storyboard_media_by_profile: Dict[Tuple[int, Any], str]" in source
    assert "storyboard_media_by_profile[(sb_idx, profile_key" in source
    assert "storyboard_media_by_profile.get(\n                        (idx, profile_key" in source
    assert "continuity_local_path" in source
    assert "profile_continuity_id" in source


def test_saved_textless_character_template_is_migrated_to_named_sheet_contract():
    source = (ROOT / "backend" / "settings.py").read_text(encoding="utf-8")

    assert '"CHARACTER CONTACT SHEET" in char_template' in source
    assert '"{char_name}" not in char_template' in source
    assert "exact character name: {char_name}" in source


def test_character_sheet_failures_retry_with_rewritten_prompts_before_stage_two():
    source = (ROOT / "backend" / "jobs_executor.py").read_text(encoding="utf-8")
    character_phase = source[source.index("max_character_attempts = max(12"):
                              source.index("# Stage 2: Build every scene storyboard")]

    assert "max_character_attempts = max(12" in character_phase
    assert "Menulis ulang prompt otomatis" in character_phase
    assert "build_safe_character_seed_prompt" in character_phase
    assert "missing_seeds" in character_phase
    assert source.index('job_state["status"] = "waiting_for_reference"', source.index("missing_seeds")) < source.index("# Stage 2: Build every scene storyboard")


def test_identity_and_storyboard_stages_cannot_be_disabled_by_legacy_toggles():
    source = (ROOT / "backend" / "jobs_executor.py").read_text(encoding="utf-8")
    assert 'enable_seed_image = True' in source
    assert 'enable_scene_storyboard_image = True' in source


def test_restart_does_not_resurrect_stale_processing_spinner():
    source = (ROOT / "backend" / "jobs_executor.py").read_text(encoding="utf-8")
    start = source.index("def _load_history(")
    end = source.index("\n\n_load_history()", start)
    load_phase = source[start:end]
    assert 'item.get("status") == "processing"' in load_phase
    assert 'item["status"] = "interrupted"' in load_phase


def test_storyboard_reuses_same_profile_character_media_without_reupload():
    source = (ROOT / "backend" / "jobs_executor.py").read_text(encoding="utf-8")
    phase = source[source.index("same_origin_storyboard_profile"):source.index("# The legacy inline storyboard block", source.index("same_origin_storyboard_profile"))]
    assert "sb_character_media_ids = character_media_ids" in phase
    assert "ensure_character_media_for_profile" in phase


def test_video_reuses_durable_storyboard_media_on_same_profile_resume():
    source = (ROOT / "backend" / "jobs_executor.py").read_text(encoding="utf-8")
    video_phase = source[source.index("# Step 3: Render each scene video"):]
    assert 'storyboard_prebuilt.get(idx, {}).get("media_id")' in video_phase
    assert 'sc.get("storyboard_media_id")' in video_phase
