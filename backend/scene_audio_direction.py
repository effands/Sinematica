"""Consistent, restrained score direction for independently generated Flow scenes."""

from typing import Any, Mapping
from .scene_direction import contains_story_terms


def _score_palette(storyboard: Mapping[str, Any]) -> str:
    context = " ".join(str(storyboard.get(key) or "") for key in (
        "film_title", "genre_style", "art_direction", "premise"
    )).lower()
    if any(term in context for term in (
        "china", "chinese", "kerajaan", "dinasti", "wuxia", "xianxia", "istana"
    )):
        return "the same Chinese cinematic orchestra palette with subtle erhu, guzheng, and strings"
    if any(term in context for term in ("horror", "horor", "thriller", "misteri")):
        return "the same restrained dark cinematic palette with low strings and soft atmospheric drones"
    if any(term in context for term in ("romance", "romantis", "cinta")):
        return "the same warm cinematic palette with soft piano and restrained strings"
    return "the same restrained cinematic orchestral palette and recurring leitmotif"


def _scene_intensity(scene: Mapping[str, Any]) -> str:
    context = " ".join(str(scene.get(key) or "") for key in (
        "title", "action_summary", "prompt_for_flow"
    )).lower()
    if contains_story_terms(context, (
        "perang", "battle", "war", "serbu", "attack", "fight", "pasukan", "clash"
    )):
        return "restrained war percussion and low dramatic pulses"
    if any(term in context for term in ("sedih", "cry", "menangis", "grief", "kehilangan")):
        return "a gentle emotional variation with sparse sustained notes"
    if any(term in context for term in ("klimaks", "reveal", "terungkap", "confront")):
        return "a controlled rise in tension without becoming loud"
    return "a calm, unobtrusive variation matched to the scene emotion"


def _scene_music_direction(scene: Mapping[str, Any]) -> str:
    """Prefer the authored scene music so the generic intensity cannot contradict it."""
    blueprint = scene.get("audio_blueprint") or {}
    if isinstance(blueprint, Mapping):
        explicit = str(blueprint.get("music") or "").strip()
        if explicit:
            return explicit
    return _scene_intensity(scene)


def _has_spoken_dialogue(scene: Mapping[str, Any]) -> bool:
    dialogue = scene.get("dialogue") or []
    return isinstance(dialogue, list) and any(
        isinstance(turn, Mapping) and str(turn.get("line") or "").strip()
        for turn in dialogue
    )


def _natural_dialogue_direction(scene: Mapping[str, Any]) -> str:
    if not _has_spoken_dialogue(scene):
        return ""
    return (
        " DIALOGUE PERFORMANCE: Treat every exact scripted line as a real conversation captured on location, "
        "not as narration, dubbing, advertising copy, or text being read aloud. Use a native, everyday speaking "
        "voice appropriate to the character's age, personality, relationship, social setting, and immediate "
        "emotion. Vary pitch, pace, emphasis, and sentence endings naturally; include subtle breaths, tiny "
        "pre-speech hesitation, and believable emotional imperfection without adding, removing, or changing any "
        "scripted words. Avoid flat cadence, evenly spaced syllables, exaggerated theatrical delivery, announcer "
        "voice, synthetic smoothness, robotic rhythm, and AI-style over-enunciation. Each listener reacts during "
        "the speaker's line with natural eye focus, blinking, breathing, and small facial or body responses, then "
        "answers after a brief conversational beat. Keep voices spatially grounded in the room, with consistent "
        "identity and volume across cuts, precise but non-mechanical lip-sync, and no overlapping dialogue unless "
        "the authored scene explicitly requests an interruption."
    )


def _infer_foley(scene: Mapping[str, Any]) -> str:
    context = " ".join(str(scene.get(key) or "") for key in (
        "activity", "action_summary", "prompt_for_flow", "start_state", "end_state"
    )).lower()
    cues = []
    cue_map = (
        (("pintu", "door", "mobil", "car"), "handle click, hinge movement, door weight and latch closure synchronized to hand contact"),
        (("jalan", "melangkah", "walk", "step", "lari", "run"), "surface-specific footsteps synchronized to weight shifts"),
        (("kain", "baju", "dress", "shirt", "coat", "fabric"), "subtle clothing rustle synchronized to body movement"),
        (("tuang", "pour", "gelas", "cup", "kopi", "coffee", "air", "water"), "container handling and liquid sound synchronized to the visible pour"),
        (("kemasan", "package", "botol", "bottle", "tutup", "cap", "produk", "product"), "small packaging, cap, grip and surface-contact sounds synchronized exactly to product handling"),
        (("ponsel", "phone", "ketik", "type", "keyboard"), "quiet device taps or keyboard clicks synchronized to finger contact"),
    )
    for terms, cue in cue_map:
        if contains_story_terms(context, terms) and cue not in cues:
            cues.append(cue)
    return "; ".join(cues[:3]) or "only physically motivated contact sounds synchronized to visible actions"


def _audio_blueprint_direction(scene: Mapping[str, Any]) -> str:
    blueprint = scene.get("audio_blueprint") or {}
    if not isinstance(blueprint, Mapping):
        blueprint = {}
    ambience = str(blueprint.get("ambience") or "continuous location-specific room tone with no empty digital silence").strip()
    foley = str(blueprint.get("foley_sfx") or _infer_foley(scene)).strip()
    voice = str(blueprint.get("voice_performance") or "emotion-led conversational delivery with human prosody").strip()
    music = str(blueprint.get("music") or "restrained support only; automatically duck beneath every spoken line").strip()
    mix = str(blueprint.get("mix") or "voice foreground; ambience subtle and continuous; foley momentary and action-synced; music lowest under speech").strip()
    return (
        " AUDIO REALISM BLUEPRINT (FIVE LAYERS): "
        f"1 VOICE — {voice}; preserve voice identity, native accent, mouth timing and spatial distance across cuts. "
        f"2 AMBIENCE — {ambience}; match room size, location, camera distance and acoustic perspective continuously. "
        f"3 FOLEY/SFX — {foley}; every transient begins on the exact visible contact frame, never early or late. "
        f"4 MUSIC — {music}; no abrupt restart at cuts and no masking consonants or emotion. "
        f"5 MIX/MASTER — {mix}; prevent clipping, pumping, harsh sibilance and large loudness jumps. "
        "Never create the Silent Uncanny Valley: no breathless wall-to-wall speech, sterile empty room, generic "
        "sound effect, mismatched reverb, detached off-screen voice, or lip-sync drift."
    )


def _character_voice_locks(scene: Mapping[str, Any], storyboard: Mapping[str, Any]) -> str:
    """Lock each speaker's vocal timbre, age, pitch, and accent so Google Flow audio does not drift between scenes."""
    dialogue = scene.get("dialogue") or []
    if not isinstance(dialogue, list) or not dialogue:
        return ""
    characters = storyboard.get("characters") or []
    char_map = {}
    for c in characters:
        if isinstance(c, Mapping):
            if c.get("id") is not None:
                char_map[c.get("id")] = c
                char_map[str(c.get("id"))] = c
            if c.get("name"):
                char_map[str(c.get("name")).lower().strip()] = c

    voice_locks = []
    seen = set()
    for turn in dialogue:
        if not isinstance(turn, Mapping):
            continue
        speaker_id = turn.get("speaker_id")
        char = char_map.get(speaker_id) or char_map.get(str(speaker_id).lower().strip())
        c_name = char.get("name") if char else f"Character {speaker_id}"
        if c_name in seen:
            continue
        seen.add(c_name)

        vocal_sig = str((char or {}).get("vocal_signature") or "").strip()
        if not vocal_sig:
            c_desc = str((char or {}).get("description") or "").lower()
            if contains_story_terms(c_desc, ["wanita", "perempuan", "female", "girl", "woman", "ibu", "gadis", "she"]):
                vocal_sig = "Natural feminine voice appropriate to the character's established age, native accent, conversational cadence"
            elif contains_story_terms(c_desc, ["pria", "laki", "male", "man", "bapak", "pemuda", "he"]):
                vocal_sig = "Natural masculine voice appropriate to the character's established age, native accent, conversational cadence"
            else:
                vocal_sig = "Clear authentic native conversational voice with consistent acoustic timbre"

        voice_locks.append(
            f"VOICE IDENTITY LOCK ({c_name}): Voice timbre MUST remain strictly locked to '{vocal_sig}'. "
            "Preserve recognizable timbre, vocal age and native accent across scenes, while allowing pitch, "
            "tempo, breaths and volume to vary naturally with the immediate emotion. Never freeze intonation "
            "or force identical syllable timing; restraint and soft speech are valid, even for an antagonist."
        )

    if not voice_locks:
        return ""
    return " " + " ".join(voice_locks)


def apply_scene_audio_direction(
    prompt: str,
    scene: Mapping[str, Any],
    storyboard: Mapping[str, Any],
    *,
    music_video: bool = False,
) -> str:
    """Append audio instructions that Flow must observe for one generated clip."""
    if "AUDIO REALISM BLUEPRINT (FIVE LAYERS)" in (prompt or ""):
        return prompt
    if music_video:
        direction = (
            "AUDIO DIRECTION: This is a narrative music-video visual. The character never sings, "
            "no lip-sync, no speaking performance, and mouth movements must not follow lyrics or rhythm. "
            "Use natural closed-mouth acting, physical action, and facial emotion only; the original master "
            "song will replace this clip audio during final editing."
        )
    elif str(storyboard.get("ugc_variant") or "").lower() == "raw_amateur":
        direction = (
            "AUDIO DIRECTION — RAW AMATEUR SMARTPHONE: no score, cinematic underscore, narrator, voice-over, "
            "or polished studio mix. Preserve socially alive location sound: casual background conversation, "
            "murmurs, brief reactions, laughter, breathing, footsteps, clothing and handling noise, room tone, "
            "and activity-specific ambience. Dialogue must feel incidental and locally recorded rather than "
            "performed for an advertisement; keep natural distance, small level variation, and believable phone-"
            "microphone perspective without making the words unintelligible."
            + _natural_dialogue_direction(scene)
            + _character_voice_locks(scene, storyboard)
        )
    else:
        blueprint = scene.get("audio_blueprint") or {}
        explicit_music = isinstance(blueprint, Mapping) and bool(str(blueprint.get("music") or "").strip())
        music_direction = (
            f"Follow the authored scene music exactly: {_scene_music_direction(scene)}. "
            "If it requests no music, keep only location sound and dialogue. Otherwise maintain continuity "
            "across cuts and duck music under speech. "
            if explicit_music else
            "Keep a low-volume cinematic underscore continuous throughout the entire "
            f"clip using {_score_palette(storyboard)}; never restart music abruptly. "
            f"For this scene use {_scene_intensity(scene)}. "
        )
        direction = (
            "AUDIO DIRECTION: " + music_direction + "Keep the score subtle under "
            "natural ambience and sound effects so dialogue remains clearly audible; raise it only slightly "
            "for a climax or impact."
            + _natural_dialogue_direction(scene)
            + _character_voice_locks(scene, storyboard)
        )
    return f"{(prompt or '').strip()}\n\n{direction}{_audio_blueprint_direction(scene)}".strip()


def resolve_master_music_track(
    storyboard: Mapping[str, Any], settings: Mapping[str, Any]
) -> str | None:
    """Prefer the track uploaded with this storyboard over any legacy global setting."""
    return storyboard.get("music_track_path") or settings.get("music_track_path")
