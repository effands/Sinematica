"""Validation helpers for mandatory character anchor generation."""

from typing import Any, Mapping


def missing_character_seeds(
    characters: list[Mapping[str, Any]], media_by_character: Mapping[Any, str]
) -> list[str]:
    """Return character names that have no generated anchor media ID."""
    missing = []
    for index, character in enumerate(characters, start=1):
        character_id = character.get("id", index)
        name = str(character.get("name") or f"Karakter {character_id}").strip()
        media_id = (
            media_by_character.get(character_id)
            or media_by_character.get(str(character_id))
            or media_by_character.get(name)
            or media_by_character.get(name.lower())
        )
        if not media_id:
            missing.append(name)
    return missing
