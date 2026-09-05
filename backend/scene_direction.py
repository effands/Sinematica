"""Stable character identity, speaker ownership, and per-clip shot direction."""

from copy import deepcopy
from typing import Any, Dict, List
import re


_SIGNATURES = (
    "crimson outer garment, angular collar, and a jade pendant",
    "cobalt-blue outer garment, rounded collar, and a silver hairpin",
    "emerald-green outer garment, high collar, and a dark leather wrist cuff",
    "ivory outer garment, asymmetric lapel, and round spectacles",
    "deep-violet outer garment, structured shoulders, and a small gold brooch",
    "amber outer garment, narrow lapel, and a carved wooden bracelet",
    "charcoal outer garment, broad collar, and a red signet ring",
    "teal outer garment, pleated sleeves, and a pearl drop earring",
    "rust-orange outer garment, wrapped collar, and a black stone pendant",
    "white-and-navy outer garment, straight collar, and a brass wristwatch",
)

_ACTION_WORDS = (
    "war", "battle", "fight", "chase", "attack", "ambush", "explosion", "combat",
    "perang", "bertempur", "bertarung", "berkelahi", "menyerbu", "penyerbuan",
    "mengejar", "kejar", "serangan", "ledakan", "baku tembak",
)
_EMOTIONAL_WORDS = (
    "cry", "cries", "weeps", "whisper", "confess", "grief", "heartbreak", "farewell",
    "menangis", "berbisik", "mengaku", "sedih", "patah hati", "perpisahan", "haru",
)

_NO_BRANDING_GUARD = (
    "NO BROADCAST BRANDING: no TV station logo, channel bug, network emblem, watermark, sponsor logo, "
    "platform mark, corner badge, news ticker, lower-third, or branded overlay anywhere in any frame."
)


def apply_no_branding_direction(prompt: str) -> str:
    """Keep generated frames free of television and platform branding."""
    text = (prompt or "").strip()
    if "NO BROADCAST BRANDING:" in text:
        return text
    return f"{text}\n\n{_NO_BRANDING_GUARD}".strip()


def choose_shot_count(scene: Dict[str, Any], prompt: str = "") -> int:
    """Choose 3, 4, or 5 shots from story energy, never by blind randomness."""
    text = " ".join(str(scene.get(k) or "") for k in ("title", "action_summary", "dialogue"))
    text = f"{text} {prompt}".lower()
    # Door/contact actions need readable continuous coverage even in a tense scene.
    if re.search(r"\b(?:door|doorway|pintu|gerbang)\b", text):
        return 3
    if contains_story_terms(text, _ACTION_WORDS):
        return 5
    speech_present = bool(scene.get("dialogue")) or any(
        marker in text for marker in ('"', "speaks", "speaking", "says", "shouts", "berkata", "berbicara")
    )
    if contains_story_terms(text, _EMOTIONAL_WORDS) or speech_present:
        return 3
    return 4


def contains_story_terms(text: str, terms) -> bool:
    """Match complete words/phrases; wardrobe and forward are not war scenes."""
    return any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I) for term in terms)


def timeline_markers(count: int) -> List[str]:
    markers = {
        3: ["0-3.3 seconds", "3.3-6.6 seconds", "6.6-10 seconds"],
        4: ["0-2.5 seconds", "2.5-5 seconds", "5-7.5 seconds", "7.5-10 seconds"],
        5: ["0-2 seconds", "2-4 seconds", "4-6 seconds", "6-8 seconds", "8-10 seconds"],
    }
    return markers[count]


def ensure_unique_character_signatures(characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Give every registry entry a stable, non-interchangeable visual signature."""
    result = deepcopy(characters or [])
    used = set()
    for index, character in enumerate(result):
        signature = str(character.get("visual_signature") or "").strip()
        if not signature or signature.casefold() in used:
            signature = _SIGNATURES[index % len(_SIGNATURES)]
            if signature.casefold() in used:
                signature = f"{signature}, identity variant {index + 1}"
        used.add(signature.casefold())
        character["visual_signature"] = signature
        description = str(character.get("description") or character.get("desc") or "").strip()
        if signature.casefold() not in description.casefold():
            description = f"{description} Permanent visual signature: {signature}.".strip()
        character["description"] = description
    return result


def build_character_wardrobe_lock(scene: Dict[str, Any], characters: List[Dict[str, Any]]) -> str:
    """Bind wardrobe/signature ownership to each character present in a scene."""
    if not characters:
        return ""
    tags = {str(tag) for tag in (scene.get("characters_in_scene") or [])}
    scene_text = " ".join(str(scene.get(k) or "") for k in ("title", "activity", "action_summary", "prompt_for_flow", "narration_id")).casefold()
    lines = []
    for character in characters or []:
        cid = str(character.get("id") or "")
        name = str(character.get("name") or "").strip()
        if tags and cid not in tags and name.casefold() not in tags:
            continue
        if not tags and name and name.casefold() not in scene_text:
            continue
        signature = str(character.get("visual_signature") or character.get("description") or character.get("desc") or "registered wardrobe and appearance").strip()
        if not name and not signature:
            continue
        lines.append(f"- {name or 'Registered character'} owns: {signature}")
    if not lines:
        return ""
    return (
        "CHARACTER WARDROBE OWNERSHIP LOCK — never swap clothing or identity between actors:\n"
        + "\n".join(lines)
        + "\nEach listed character keeps their own face, body, hairstyle, facial hair, outfit, shoes, jewellery, colour palette, and accessories in every shot. "
          "FACIAL HAIR OWNERSHIP: moustache, beard, goatee, sideburns, stubble density, eyebrow shape, hairline, scars, moles, glasses and other face-specific identifiers belong only to the character that owns them. Never transfer a moustache/beard/stubble pattern to another male actor, never erase it from its owner, and never duplicate one man's facial hair onto every man in the scene. "
          "Never put a woman's blouse/dress/skirt/hijab/jewellery on a male actor unless the story explicitly says cross-dressing, and never move a male character's suit/shirt/accessories onto a female actor. "
          "If two characters share a frame, separate them by their registered face identifiers, wardrobe, and visual signature before motion begins."
    )


def build_speaker_lock(scene: Dict[str, Any], characters: List[Dict[str, Any]]) -> str:
    """Bind each exact line to one named face; prevent dialogue-role swapping."""
    dialogue = scene.get("dialogue") or []
    if not isinstance(dialogue, list) or not dialogue:
        return ""
    by_id = {str(c.get("id")): c for c in characters or []}
    lines = []
    for turn in dialogue:
        if not isinstance(turn, dict) or not str(turn.get("line") or "").strip():
            continue
        character = by_id.get(str(turn.get("speaker_id"))) or {}
        name = character.get("name") or f"character {turn.get('speaker_id')}"
        signature = character.get("visual_signature") or character.get("description") or "registered appearance"
        position = turn.get("screen_position") or "the established screen position"
        exact_line = str(turn["line"]).replace('"', "'")
        lines.append(f'- {name} ({signature}), at {position}, alone speaks exactly: "{exact_line}"')
    if not lines:
        return ""
    return (
        "SPEAKER LOCK — preserve dialogue ownership across every cut:\n"
        + "\n".join(lines)
        + "\nDuring each line, all non-speakers keep their mouths closed and only react physically. "
          "Never transfer a line, voice, or lip movement to another face."
    )


def canonical_dialogue_lines(scene: Dict[str, Any]) -> List[str]:
    """Return the only spoken lines allowed in a rendered scene, in authored order."""
    dialogue = scene.get("dialogue") or []
    if not isinstance(dialogue, list):
        return []
    return [
        str(turn.get("line") or "").strip()
        for turn in dialogue if isinstance(turn, dict) and str(turn.get("line") or "").strip()
    ]


def enforce_spoken_language_lock(prompt: str, scene: Dict[str, Any], target_lang: str) -> str:
    """Remove invented quoted speech and make authored local-language dialogue authoritative."""
    text = str(prompt or "").strip()
    canonical = canonical_dialogue_lines(scene)
    allowed = {line.casefold() for line in canonical}

    if canonical:
        def replace_double(match):
            value = match.group(2).strip()
            return match.group(0) if value.casefold() in allowed else "[no additional spoken line]"

        def replace_single(match):
            value = match.group(1).strip()
            return match.group(0) if value.casefold() in allowed else "[no additional spoken line]"

        text = re.sub(r'(["“])([^"”\n]{1,240})(["”])', replace_double, text)
        text = re.sub(r"(?<!\w)'([^'\n]{2,240})'(?!\w)", replace_single, text)
        exact = "\n".join(f'- "{line.replace(chr(34), chr(39))}"' for line in canonical)
        rule = (
            f"SPOKEN LANGUAGE LOCK (HIGHEST AUDIO PRIORITY): all speech is natural {target_lang or 'target-language'} only. "
            "Ignore and do not vocalize any earlier placeholder, paraphrase, translation, or English speech. "
            "The ONLY permitted spoken lines, verbatim and in this order, are:\n" + exact
        )
    else:
        text = re.sub(r'(["“])([^"”\n]{1,240})(["”])', "[no spoken dialogue]", text)
        text = re.sub(r"(?<!\w)'([^'\n]{2,240})'(?!\w)", "[no spoken dialogue]", text)
        rule = (
            f"SPOKEN LANGUAGE LOCK (HIGHEST AUDIO PRIORITY): no improvised speech in any language. "
            f"If incidental human vocalization is unavoidable, it must be non-verbal and culturally natural for {target_lang or 'the target audience'}."
        )
    text = re.sub(r"\n\nSPOKEN LANGUAGE LOCK \(HIGHEST AUDIO PRIORITY\):[\s\S]*$", "", text).rstrip()
    return f"{text}\n\n{rule}".strip()
