"""Safe, neutral character-sheet fallback for Flow policy rejections."""

import re


def is_unsafe_generation_error(error) -> bool:
    return "PUBLIC_ERROR_UNSAFE_GENERATION" in str(error or "").upper()


def alternate_character_seed(seed) -> int:
    try:
        base = int(seed)
    except (TypeError, ValueError):
        base = sum(ord(char) for char in str(seed or "character"))
    return (base + 7919) % 1_000_000 or 7919


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
    minimal_reinterpretation: bool = False,
) -> str:
    """Create an original, non-action identity sheet without the rejected proper name."""
    if minimal_reinterpretation:
        visual_traits = (
            "An original adult Indonesian fitness trainer with a tall athletic build, warm brown "
            "skin, short neat black hair, a calm friendly expression, and loose charcoal sportswear."
        )
    elif distinct_reinterpretation:
        visual_traits = (
            "A towering mineral-skinned fantasy guardian with an extremely powerful athletic "
            "build, broad jaw, short dark hair, heavy hands, calm expression, and rugged charcoal "
            "training trousers. Use a fresh slate-blue and charcoal colour palette and an original silhouette."
        )
    else:
        visual_traits = _remove_character_name(description, character_name)
    if not visual_traits:
        visual_traits = "A distinctive cinematic hero with a clearly recognizable silhouette and wardrobe."

    prompt = f"""Create a clean studio identity sheet for an original fictional adult character.
Internal consistency seed: {seed}.
Visual traits to preserve: {visual_traits}

Show one full-body front view, one side view, one back view, and three calm facial-expression close-ups on a plain warm-beige studio background. Use relaxed standing poses and soft editorial lighting. Preserve the same face, body proportions, hairstyle, skin colour, clothing silhouette, colour palette, accessories, and distinctive physical marks across every panel. Keep the page clean, peaceful, text-free, and suitable for a general audience."""

    if has_references:
        prompt += (
            "\n\nThe attached reference images are visual guidance for identity consistency. "
            "Reinterpret them as an original unbranded fictional character while preserving the "
            "visible face, proportions, wardrobe colours, and distinctive physical traits."
        )
    return prompt
