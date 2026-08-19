"""Pure helpers for carrying visual continuity between rendered scenes."""

from typing import Optional


def continuity_start_image(
    media_id: Optional[str], source_scene_number: Optional[int], current_scene_number: int
) -> Optional[str]:
    """Only an immediately preceding successful scene may seed the current scene."""
    if media_id and source_scene_number == current_scene_number - 1:
        return media_id
    return None


def build_continuity_prompt(prompt: str, continuity_media_id: Optional[str]) -> str:
    """Tell Flow to treat the supplied end frame as the literal next opening frame."""
    if not continuity_media_id:
        return prompt
    return (
        f"{prompt}\n\n"
        "SCENE CONTINUITY: Use the supplied image as the literal opening frame. "
        "Continue the same characters, exact faces, wardrobe, body positions, camera angle, "
        "lighting, location, and direction of motion from that frame. Begin with seamless "
        "motion from the previous scene; do not reset or redesign the shot."
    )
