import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from omniflash.bridge import ExtensionBridge

def test_bridge_progress_listener():
    bridge = ExtensionBridge()
    captured_events = []

    def on_progress(msg):
        captured_events.append(msg)

    bridge.add_progress_listener(on_progress)

    progress_msg = {
        "type": "task_progress",
        "id": "req_test_123",
        "stage": "TYPING_PROMPT",
        "message": "Mengetik prompt...",
        "percent": 30,
        "timestamp": 1234567890
    }

    bridge.handle_message(json.dumps(progress_msg), ws=None)

    assert len(captured_events) == 1
    assert captured_events[0]["stage"] == "TYPING_PROMPT"
    assert captured_events[0]["message"] == "Mengetik prompt..."
    assert captured_events[0]["percent"] == 30

    bridge.remove_progress_listener(on_progress)
    bridge.handle_message(json.dumps(progress_msg), ws=None)

    assert len(captured_events) == 1  # Not called after removal
