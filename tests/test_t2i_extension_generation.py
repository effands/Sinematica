import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock
import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from omniflash.generators.t2i import generate_character_image


@pytest.mark.anyio
async def test_generate_character_image_dispatches_extension_task():
    dummy_bridge = AsyncMock()
    dummy_bridge.execute_task = AsyncMock(return_value={
        "status": 200,
        "result": {
            "ok": True,
            "imageUrl": "https://flow-content.google/image/hero-portrait.png",
            "mediaId": "hero-media-uuid",
        }
    })

    res = await generate_character_image(
        bridge=dummy_bridge,
        prompt="Studio character sheet portrait of Hero",
        aspect="portrait",
        project_id="proj-123",
        instance_id="inst-1",
        seed=654321,
    )

    assert dummy_bridge.execute_task.called
    call_args = dummy_bridge.execute_task.call_args[0]
    task_payload = call_args[0]
    assert task_payload["kind"] == "image"
    assert "Hero" in task_payload["prompt"]
    assert task_payload["storyboard"]["aspectRatio"] == "9:16"
    assert res["media_id"] == "hero-media-uuid"
    assert res["image_url"] == "https://flow-content.google/image/hero-portrait.png"


@pytest.mark.anyio
async def test_generate_character_image_includes_reference_images(tmp_path):
    dummy_bridge = AsyncMock()
    dummy_bridge.execute_task = AsyncMock(return_value={
        "status": 200,
        "result": {
            "ok": True,
            "imageUrl": "https://flow-content.google/image/ref-output.png",
            "mediaId": "ref-output-id",
        }
    })

    sample_img = tmp_path / "ref_actor.png"
    sample_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest")

    res = await generate_character_image(
        bridge=dummy_bridge,
        prompt="Character with reference",
        aspect="landscape",
        reference_image_paths=[str(sample_img)],
    )

    task_payload = dummy_bridge.execute_task.call_args[0][0]
    assert len(task_payload.get("images", [])) == 1
    assert task_payload["images"][0]["fileName"] == "ref_actor.png"
    assert task_payload["storyboard"]["aspectRatio"] == "16:9"
    assert res["media_id"] == "ref-output-id"
