import asyncio
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from omniflash.bridge import ExtensionBridge, is_routable_bridge_message


class DummyWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.closed = False

    async def send_text(self, text: str):
        self.sent_messages.append(text)

    async def send_str(self, text: str):
        self.sent_messages.append(text)


def test_task_response_is_routable():
    assert is_routable_bridge_message("task_response") is True


@pytest.mark.anyio
async def test_bridge_execute_task_success():
    bridge = ExtensionBridge()
    ws = DummyWebSocket()
    bridge.register_instance("inst-1", ws, instance_name="Profile 1", ready=True)

    task_payload = {
        "kind": "image",
        "prompt": "Cinematic character portrait",
        "storyboard": {"aspectRatio": "9:16", "outputCount": 1},
    }

    async def complete_task_later():
        await asyncio.sleep(0.05)
        assert len(ws.sent_messages) == 1
        sent = json.loads(ws.sent_messages[0])
        assert sent["type"] in ("agent_task", "execute_task", "flow_task")
        req_id = sent["id"]

        response = {
            "type": "task_response",
            "id": req_id,
            "status": 200,
            "result": {
                "ok": True,
                "imageUrl": "https://flow-content.google/image/test-char.png",
                "mediaId": "media-char-123",
            },
        }
        bridge.handle_message(json.dumps(response), ws=ws, instance_id="inst-1")

    asyncio.create_task(complete_task_later())

    res = await bridge.execute_task(task_payload, instance_id="inst-1", timeout=5.0)
    assert res.get("status") == 200
    assert res.get("result", {}).get("imageUrl") == "https://flow-content.google/image/test-char.png"
