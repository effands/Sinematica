"""Safe, neutral character-sheet fallback for Flow policy rejections."""

import re


def is_unsafe_generation_error(error) -> bool:
    return "PUBLIC_ERROR_UNSAFE_GENERATION" in str(error or "").upper()


def _remove_character_name(text: str, character_name: str) -> str:
    cleaned = str(text or "")
    name = str(character_name or "").strip()
    base_name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    for alias in sorted({name, base_name}, key=len, reverse=True):
        if alias:
            cleaned = re.sub(re.escape(alias), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip(" ,.;:-")


def build_safe_character_seed_prompt(
    character_name: str,
    description: str,
    seed,
    *,
    has_references: bool = False,
    distinct_reinterpretation: bool = False,
) -> str:
    """Create an original, non-action identity sheet without the rejected proper name."""
    if distinct_reinterpretation:
        visual_traits = (
            "A towering mineral-skinned fantasy guardian with an extremely powerful athletic "
            "build, broad jaw, short dark hair, heavy hands, calm expression, and rugged charcoal "
            "training trousers. Use a fresh slate-blue and charcoal colour palette and an original silhouette."
        )
    else:
        visual_traits = _remove_character_name(description, character_name)
    if not visual_traits:
        visual_traits = "A distinctive cinematic hero with a clearly recognizable silhouette and wardrobe."

    prompt = f"""Create an ORIGINAL, UNBRANDED character reference sheet for a fictional screen character.
Internal consistency seed: {seed}.
Visual traits to preserve: {visual_traits}

Show one full-body front view, one side view, one back view, and three neutral facial-expression close-ups on a clean studio background. Use calm neutral standing poses only. Preserve the same face, body proportions, hairstyle, skin colour, clothing silhouette, colour palette, accessories, and distinctive physical marks across every panel. No combat, attack, destruction, injury, threatening pose, weapons, copyrighted name, franchise logo, brand mark, text overlay, watermark, or character-sheet title."""

    if has_references:
        prompt += (
            "\n\nThe attached reference images are visual guidance for identity consistency. "
            "Reinterpret them as an original unbranded fictional character while preserving the "
            "visible face, proportions, wardrobe colours, and distinctive physical traits."
        )
    return prompt
