import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.character_reference_flow import resolve_character_reference_paths


def test_character_references_resolves_existing_paths(tmp_path):
    img = tmp_path / "char1.png"
    img.write_text("dummy")

    storyboard = {
        "character_references": {
            "actor-1": {"paths": [str(img)], "name": "Akira"}
        }
    }
    char = {"source_actor_id": "actor-1", "name": "Akira"}
    paths = resolve_character_reference_paths(char, storyboard)
    assert paths == [str(img)]
