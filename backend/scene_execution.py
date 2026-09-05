"""Physical staging and character performance shared by planning and rendering."""

import json
import re


NATURAL_ACTION_RULES = """NATURAL ACTION AND SPEECH:
Use one main physical action and at most two supporting actions per clip. Keep real weight transfer,
grip, contact, resistance and release readable. Listening, thinking, blinking and breathing are valid
acting; allow motivated pauses instead of demanding constant movement. Never add gestures just to fill time.
Speak only the authored lines, with natural conversational timing, changing pitch and scene-specific emotion.
Do not force two speaking turns, a shout, a whisper, or a theatrical voice when the scene does not need it.
Keep the critical hand-object contact in one continuous shot; cut before the reach or after release, not
in the middle of the mechanism. Secondary actions may occur within one view; every beat need not be a cut.
If the duration is tight, simplify supporting movement rather than speed up speech or hide an incomplete action.
""".strip()


DOOR_INTERACTION_RULES = """DOOR / VEHICLE CONTACT CONTINUITY:
Resolve the exact physical door (vehicle left/right and front/rear seat, or house room/threshold), actor
inside/outside, fixed hinge side, handle side, swing direction or sliding track, opening angle, active hand,
feet and camera side from the authored layout/reference. Physical left/right is not the same as screen left/right.
Do not assume every car is left-hand drive; use the established vehicle. Never mirror a door or change hinges at a cut.
Only perform the requested operation, never add entry/exit just because a door is visible.
OPEN: establish door state -> reach the correct handle -> fingers grip -> latch releases -> door moves around
the fixed hinge (or along its track) with resistance -> actor clears the opening before crossing the threshold.
CLOSE: establish actor and door on the same correct side -> use the reachable inner pull or outer panel -> clear
body, feet and clothing from the sweep -> push/pull along the same hinge arc -> latch contact -> release the hand.
For car entry, seat hips and bring both legs inside before pulling the interior handle to close; for exit,
open first, place feet on the ground, move fully outside, then close from outside if requested.
Show the hand, relevant door edge and body clearance together in a stable medium/three-quarter view through
contact and closure. Never pass a hand through glass, swap grips off-screen, close through a body, let a door
detach, or teleport the actor inside. End with the actual open/closed state; latch sound follows visible contact.
""".strip()


def scene_execution_context(scene):
    def readable(value):
        # Quoted JSON values are otherwise mistaken for invented dialogue by the
        # spoken-language filter. Physical facts must survive that filter intact.
        if isinstance(value, dict):
            return '; '.join(f'{key}: {readable(item)}' for key, item in value.items() if item)
        if isinstance(value, list):
            return '; '.join(readable(item) for item in value if item)
        return str(value)
    fields = (
        ('OPENING STATE', 'start_state'), ('FINAL CONTINUITY FRAME', 'end_state'),
        ('BLOCKING', 'spatial_continuity'), ('PROP / MECHANISM FACTS', 'interaction_plan'),
    )
    lines = []
    for label, field in fields:
        value = scene.get(field)
        if value:
            rendered = readable(value)
            lines.append(f"{label}: {rendered}")
    return '\n'.join(lines)


def build_physical_execution_guard(scene, prompt=''):
    context = scene_execution_context(scene)
    text = ' '.join(str(scene.get(k) or '') for k in (
        'activity', 'action_summary', 'prompt_for_flow', 'interaction_plan', 'start_state', 'end_state',
        'spatial_continuity',
    )) + ' ' + prompt
    door = bool(re.search(r'\b(?:door|doorway|pintu|gerbang)\b', text, re.I))
    return '\n\n' + '\n'.join(part for part in (
        context, NATURAL_ACTION_RULES, DOOR_INTERACTION_RULES if door else '',
    ) if part)


def character_sheet_description(character):
    """Carry authored role/acting/identity into custom and default sheet templates."""
    parts = [str(character.get('description') or character.get('desc') or '').strip()]
    for key, label in (
        ('role', 'Narrative role'), ('motivation', 'Motivation'), ('relationship_to_others', 'Relationships'),
        ('visual_signature', 'Distinctive identity'), ('body_language', 'Body language'),
        ('expression_range', 'Expression range'),
    ):
        if character.get(key):
            value = character[key]
            parts.append(f"{label}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}.")
    parts.append(
        "CHARACTER SHEET PERFORMANCE: Keep the same face, age, proportions, hairline, eyes, nose, jaw, "
        "skin tone, outfit construction, shoes and accessory placement in every view. Show readable hands "
        "and one full-body stance. Use the established panel layout; include neutral, listening and restrained "
        "emotional responses across the portraits without changing identity. Express the authored protagonist, "
        "antagonist or supporting role through posture, gaze and believable acting, not permanent scowling, "
        "exaggerated evil anatomy or a compulsory smile. Do not infer moral role from skin tone, scars or disability. "
        "Keep role and motivation as acting directions, not extra printed story paragraphs. "
        "Existing reference images take priority over invented facial details; never borrow another character's traits."
    )
    return '\n'.join(filter(None, parts))
