"""Final prompt guards for dense, continuously moving Flow scenes."""

import json
import logging
import re
from typing import Any, Dict

from .scene_direction import choose_shot_count, timeline_markers


log = logging.getLogger("sinematica.scene_pacing")


def has_dialogue(scene: Dict[str, Any], prompt: str = "") -> bool:
    """Return True when the scene contains spoken dialogue."""
    combined = " ".join(
        str(scene.get(key) or "")
        for key in ("dialogue", "dialog", "narration_id", "action_summary")
    ) + " " + (prompt or "")
    markers = (
        '"', "'", "speaks", "speaking", "says", "shouts", "whispers",
        "in indonesian:", "dialog", "berkata", "berbicara",
    )
    return any(marker in combined.lower() for marker in markers)


def _extract_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    return json.loads(text)


def _has_required_timeline(prompt: str, dialogue_required: bool, markers) -> bool:
    lowered = (prompt or "").lower()
    if not all(marker in lowered for marker in markers):
        return False
    if dialogue_required:
        quoted = re.findall(r'(["\']).+?\1', prompt or "")
        if len(quoted) < 2:
            return False
    return True


def rewrite_dense_prompt_with_ai(
    prompt: str,
    scene: Dict[str, Any],
    duration: int,
    *,
    children_mode: bool = False,
    generator=None,
):
    """Rewrite the actual scene content into concrete beats via the configured primary AI."""
    if int(duration) != 10:
        return prompt, "unchanged"
    dialogue_required = has_dialogue(scene, prompt)
    shot_count = choose_shot_count(scene, prompt)
    markers = timeline_markers(shot_count)
    count_word = {3: "THREE", 4: "FOUR", 5: "FIVE"}[shot_count]
    if generator is None:
        from .text_generation import generate_text
        generator = generate_text

    tone = (
        "Keep every action gentle, cheerful, safe for preschool children, and free of violence."
        if children_mode else
        "Keep the dramatic tone and character intent of the original scene."
    )
    dialogue_instruction = (
        "The original contains speech: write two short spoken lines in the original spoken language, "
        "one in beat 1 or 2 and a reply in the next beat. Put both exact lines in double quotes."
        if dialogue_required else
        "Do not invent dialogue; use three concrete physical story actions."
    )
    previous_context = ""
    if scene.get("previous_scene_title") or scene.get("previous_scene_action"):
        previous_context = f"""
Previous 10-second video:
- Title: {scene.get('previous_scene_title') or ''}
- Final action/location context: {scene.get('previous_scene_action') or ''}
- Previous visual prompt: {scene.get('previous_scene_prompt') or ''}
- Exact final physical state: {scene.get('previous_scene_end_state') or ''}
The new video must begin from a plausible continuation of that final physical situation. If the
story truly changes location, show an explicit exit/arrival/doorway/vehicle transition instead of
teleporting characters to a distant place.
"""

    request = f"""Rewrite this Google Flow video prompt. Return JSON only:
{{"prompt_for_flow":"..."}}

Hard requirements:
- Duration remains exactly 10 seconds, structured as {count_word} SHOTS / mini-beats connected by clean hard
  cuts or motivated match cuts. These are {shot_count} camera views of ONE continuous event, not separate story scenes.
- Use these literal timeline markers: {', '.join(f'`{m}:`' for m in markers)}.
- Every shot must use a visibly different framing/angle (for example: wide master, over-the-shoulder,
  insert/detail, close-up/reaction) and name that angle explicitly.
- Every shot must contain a different, specific character action that advances the same event.
- Put at least two linked physical actions in every beat. No static hold may last longer than 0.5 seconds.
- The final shot must end on a decision, reveal, interruption, reversal, or completed action.
- Maintain strict continuity across cuts: identical faces, wardrobe, props, location, screen direction,
  and cause-and-effect. Never reset character positions without showing the movement.
- All shots remain in the SAME location and SAME continuous time window. Never jump rooms, buildings,
  cities, day/night, or story time inside this 10-second generation.
- Character action/dialogue is the main content. Camera, lighting, transitions, particles, facial holds,
  and visual effects are supporting details only and may not occupy a beat.
- No idle staring, posing, slow motion, empty walking, reaction held for seconds, montage, or dead air.
- {dialogue_instruction}
- {tone}
- Preserve character identities, clothes, location, visual style, and all safety constraints.

Scene title: {scene.get('title') or ''}
Action summary: {scene.get('action_summary') or ''}
{previous_context}
Original prompt:
{prompt}
"""
    try:
        result = generator(request, json_output=True)
        rewritten = str(_extract_json(result.text).get("prompt_for_flow") or "").strip()
        if _has_required_timeline(rewritten, dialogue_required, markers):
            return rewritten, result.provider
        log.warning("Provider %s returned a sparse 10-second rewrite; using local guard.", result.provider)
    except Exception as ex:
        log.warning("Dense scene rewrite failed; using local guard: %s", ex)
    return densify_flow_prompt(prompt, scene, duration), "local-guard"


def densify_flow_prompt(prompt: str, scene: Dict[str, Any], duration: int) -> str:
    """Append an enforceable timeline so a long clip is not rendered as a held pose."""
    if int(duration) != 10:
        return prompt

    shot_count = choose_shot_count(scene, prompt)
    markers = timeline_markers(shot_count)
    angles = ("WIDE/MASTER", "OVER-THE-SHOULDER", "INSERT/DETAIL", "MEDIUM TRACKING", "CLOSE-UP/REACTION")
    selected = angles[:shot_count - 1] + (angles[-1],)
    beats = "; ".join(
        f"{marker} {angle} SHOT: perform two linked physical actions that advance the event"
        for marker, angle in zip(markers, selected)
    )

    dialogue_rule = ""
    if has_dialogue(scene, prompt):
        dialogue_rule = (
            " Dialogue pacing is mandatory: include at least two distinct short speaking turns "
            "from the characters, separated by a visible physical reaction or counter-action; "
            "do not stretch one line across the whole clip."
        )

    guard = (
        f"MANDATORY DENSE 10-SECOND {shot_count}-SHOT SEQUENCE: {beats}. The final shot must deliver a "
        "reveal, decision, impact, or sharp reaction and cut immediately. Connect shots with clean hard "
        f"cuts. All {shot_count} shots show ONE continuous event in the SAME location and SAME time window; they are "
        "camera-angle changes, not separate story scenes. Preserve identical faces, wardrobe, props, location, "
        "screen direction, and cause-and-effect. "
        "Keep hands, faces, bodies, props, and camera purposefully active across all shots. "
        "Use at least two linked physical actions in every beat. No static hold may last longer than 0.5 seconds. "
        "No silent staring, idle pauses, frozen posing, slow empty walking, prolonged establishing "
        "shots, or dead air. Do not use slow motion."
        + dialogue_rule
    )
    return f"{(prompt or '').strip()}\n\n{guard}".strip()


def should_try_gemini_storyboard_image(settings: Dict[str, Any]) -> bool:
    """Avoid a known-slow Gemini image attempt when another provider is explicitly primary."""
    return str(settings.get("default_text_provider") or "gemini").strip().lower() == "gemini"
