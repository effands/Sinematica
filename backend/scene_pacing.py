"""Final prompt guards for dense, continuously moving Flow scenes."""

import json
import logging
import re
from typing import Any, Dict

from .scene_direction import choose_shot_count, timeline_markers
from .scene_direction import canonical_dialogue_lines, enforce_spoken_language_lock
from .scene_execution import build_physical_execution_guard


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


def _has_required_timeline(prompt: str, dialogue_required: bool, markers, canonical_lines=None) -> bool:
    lowered = (prompt or "").lower()
    if not all(marker in lowered for marker in markers):
        return False
    if "opening state:" not in lowered or "final continuity frame:" not in lowered:
        return False
    if dialogue_required:
        expected = [str(line).strip() for line in (canonical_lines or []) if str(line).strip()]
        if expected and not all(f'"{line}"' in prompt or f"'{line}'" in prompt for line in expected):
            return False
    return True


def rewrite_dense_prompt_with_ai(
    prompt: str,
    scene: Dict[str, Any],
    duration: int,
    *,
    children_mode: bool = False,
    target_lang: str = "",
    generator=None,
):
    """Rewrite the actual scene content into concrete beats via the configured primary AI."""
    if int(duration) != 10:
        return prompt, "unchanged"
    canonical_lines = canonical_dialogue_lines(scene)
    dialogue_required = bool(canonical_lines)
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
        f"The ONLY spoken lines are these exact {target_lang or 'target-language'} lines, in authored order: "
        + " | ".join(f'\"{line}\"' for line in canonical_lines)
        + ". Copy them verbatim; never translate, paraphrase, or invent another line."
        if canonical_lines else
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
- Duration remains exactly 10 seconds, structured as {count_word} SHOTS / mini-beats of ONE continuous event.
  These are timed coverage beats, not mandatory cuts: keep critical mechanism contact in one uninterrupted view.
- Use these literal timeline markers: {', '.join(f'`{m}:`' for m in markers)}.
- Name the framing explicitly. Change angle only when motivated and physically compatible with the action.
- Use one main action and at most two supporting actions over the clip. Allow natural listening and response
  beats with breathing and small weight shifts; do not force extra gestures or an arbitrary movement frequency.
- Begin with a sentence labelled `OPENING STATE:` that explicitly locks each visible character's screen
  position, body orientation, eyeline, active hand, held object and object orientation. For a continuation,
  derive this from the exact previous final state; never write only "continue seamlessly".
- Define any story-critical prop by unambiguous physical parts, material, colour, which hand holds it, and
  where a mark/engraving/hinge/handle is located. Do not let one noun refer ambiguously to two object parts.
- Preserve spatial cause-and-effect across cuts: state where an entering character starts and show the short
  movement into the next position. Never use a cut to teleport, mirror, or reset blocking.
- Lock every speaking character's eyeline and add `never looks into camera` unless the authored scene clearly
  requires direct address. Terms such as "forward" must name the actual person or object being faced.
- The final shot must end on a decision, reveal, interruption, reversal, or completed action, followed by a
  sentence labelled `FINAL CONTINUITY FRAME:` that records every visible character's position, posture,
  eyeline, active hand, held prop orientation, and emotional state for the next scene.
- Do a silent feasibility audit: fit physical movement and natural dialogue into the available seconds. Remove
  or combine low-priority actions instead of rushing, skipping contact, or overlapping dialogue.
- Resolve contradictions before writing: one coherent music direction, one motivated lighting setup, one
  meaning for every prop, and no decorative hero object that does not participate in this scene.
- Unless authored otherwise: no subtitles, captions, dialogue text, labels, or readable overlay text.
- Maintain strict continuity across cuts: identical faces, wardrobe, props, location, screen direction,
  and cause-and-effect. Never reset character positions without showing the movement.
- All shots remain in the SAME location and SAME continuous time window. Never jump rooms, buildings,
  cities, day/night, or story time inside this 10-second generation.
- Character action/dialogue is the main content. Camera, lighting, transitions, particles, facial holds,
  and visual effects are supporting details only and may not occupy a beat.
- No frozen tableaux, decorative montage or gratuitous slow motion. A meaningful pause or listening reaction is valid.
- {dialogue_instruction}
- {tone}
- Preserve character identities, clothes, location, visual style, target spoken language ({target_lang or 'as authored'}), and all safety constraints.

Scene title: {scene.get('title') or ''}
Action summary: {scene.get('action_summary') or ''}
Authored physical states and execution requirements (preserve these facts in the rewrite):
{build_physical_execution_guard(scene, prompt)}
{previous_context}
Original prompt:
{prompt}
"""
    try:
        result = generator(request, json_output=True)
        rewritten = str(_extract_json(result.text).get("prompt_for_flow") or "").strip()
        if _has_required_timeline(rewritten, dialogue_required, markers, canonical_lines):
            return enforce_spoken_language_lock(rewritten, scene, target_lang), result.provider
        log.warning("Provider %s returned a sparse 10-second rewrite; using local guard.", result.provider)
    except Exception as ex:
        log.warning("Dense scene rewrite failed; using local guard: %s", ex)
    return enforce_spoken_language_lock(densify_flow_prompt(prompt, scene, duration), scene, target_lang), "local-guard"


def densify_flow_prompt(prompt: str, scene: Dict[str, Any], duration: int) -> str:
    """Append an enforceable timeline so a long clip is not rendered as a held pose."""
    if int(duration) != 10:
        return prompt

    shot_count = choose_shot_count(scene, prompt)
    markers = timeline_markers(shot_count)
    angles = ("WIDE/MASTER", "OVER-THE-SHOULDER", "INSERT/DETAIL", "MEDIUM TRACKING", "CLOSE-UP/REACTION")
    selected = angles[:shot_count - 1] + (angles[-1],)
    beats = "; ".join(
        f"{marker} {angle} coverage beat: advance the authored action or show a natural listener response"
        for marker, angle in zip(markers, selected)
    )

    dialogue_rule = ""
    if has_dialogue(scene, prompt):
        dialogue_rule = (
            " Preserve only the authored speaking turns in order, with natural breaths and listening pauses; "
            "do not invent a second line, force fast speech or stretch syllables to fill the clip."
        )

    guard = (
        "OPENING STATE: Preserve the exact incoming character positions, body orientation, eyelines, active "
        "hands, and held-prop orientation; if any of these are unspecified, infer one physically coherent "
        "arrangement and keep it unchanged until visible movement changes it. "
        f"MANDATORY DENSE 10-SECOND {shot_count}-SHOT SEQUENCE: {beats}. The final shot must deliver a "
        "reveal, decision, impact, or motivated reaction. Keep critical contact in one continuous view; "
        f"all {shot_count} beats show ONE continuous event in the SAME location and SAME time window; they are "
        "camera-angle changes, not separate story scenes. Preserve identical faces, wardrobe, props, location, "
        "screen direction, and cause-and-effect. "
        "Use one main action and at most two supporting actions per clip; allow motivated listening, breaths "
        "and pauses. No frozen posing or unnecessary gestures. Define story-critical prop parts unambiguously and show "
        "where any engraving, hinge, handle, or mark is located. Keep eyelines attached to a named person or "
        "object; never use an ambiguous 'look forward' and never look into camera unless explicitly authored. "
        "No subtitles, captions, dialogue text, labels, or readable overlay text. "
        "FINAL CONTINUITY FRAME: end by recording each visible character's position, posture, eyeline, active "
        "hand, held-prop orientation, and emotional state for the next scene."
        + dialogue_rule
    )
    return f"{(prompt or '').strip()}\n\n{guard}{build_physical_execution_guard(scene, prompt)}".strip()


def should_try_gemini_storyboard_image(settings: Dict[str, Any]) -> bool:
    """Avoid a known-slow Gemini image attempt when another provider is explicitly primary."""
    return str(settings.get("default_text_provider") or "gemini").strip().lower() == "gemini"
