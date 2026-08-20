"""Consistent, restrained score direction for independently generated Flow scenes."""

from typing import Any, Mapping


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
    if any(term in context for term in (
        "perang", "battle", "war", "serbu", "attack", "fight", "pasukan", "clash"
    )):
        return "restrained war percussion and low dramatic pulses"
    if any(term in context for term in ("sedih", "cry", "menangis", "grief", "kehilangan")):
        return "a gentle emotional variation with sparse sustained notes"
    if any(term in context for term in ("klimaks", "reveal", "terungkap", "confront")):
        return "a controlled rise in tension without becoming loud"
    return "a calm, unobtrusive variation matched to the scene emotion"


def apply_scene_audio_direction(
    prompt: str,
    scene: Mapping[str, Any],
    storyboard: Mapping[str, Any],
    *,
    music_video: bool = False,
) -> str:
    """Append audio instructions that Flow must observe for one generated clip."""
    if "AUDIO DIRECTION:" in (prompt or ""):
        return prompt
    if music_video:
        direction = (
            "AUDIO DIRECTION: This is a narrative music-video visual. The character never sings, "
            "no lip-sync, no speaking performance, and mouth movements must not follow lyrics or rhythm. "
            "Use natural closed-mouth acting, physical action, and facial emotion only; the original master "
            "song will replace this clip audio during final editing."
        )
    else:
        direction = (
            "AUDIO DIRECTION: Keep a low-volume cinematic underscore continuous throughout the entire "
            f"clip using {_score_palette(storyboard)}; never drop to awkward silence and never restart the "
            f"music abruptly. For this scene use {_scene_intensity(scene)}. Keep the score subtle under "
            "natural ambience and sound effects so dialogue remains clearly audible; raise it only slightly "
            "for a climax or impact."
        )
    return f"{(prompt or '').strip()}\n\n{direction}".strip()


def resolve_master_music_track(
    storyboard: Mapping[str, Any], settings: Mapping[str, Any]
) -> str | None:
    """Prefer the track uploaded with this storyboard over any legacy global setting."""
    return storyboard.get("music_track_path") or settings.get("music_track_path")
