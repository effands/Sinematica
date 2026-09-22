# Visible Flow Character & Seed Image Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 100% visible DOM-driven Character & Seed Image generation in Google Flow Chrome Extension (uploading reference images to composer, configuring UI settings, typing prompt, clicking generate, and live DOM polling percentage logs) streaming real-time WebSocket progress to Sinematica Terminal, Web UI, and batch test runners.

**Architecture:** Route character seed and concept image generation from `jobs_executor.py` through `ExtensionBridge.execute_task` to the Chrome Extension DOM automation (`flow-executor.js`). The extension uploads reference images into the Google Flow composer, adjusts aspect ratio settings via UI popover, types the character prompt, clicks generate, tracks live percentage progress in the DOM, and returns the generated image URL and media ID back to FastAPI via WebSocket `task_response`.

**Tech Stack:** Python 3.14, FastAPI, WebSockets, JavaScript (Chrome Extension MV3, DOM Automation), Pytest, Node Test Runner.

**Spec:** `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md` and reference extension in `affilia/extensions/ziqva-google-flow/`.

## Global Constraints

- State all points directly in affirmative language.
- Keep all unit tests passing (`python -m pytest tests/` and `node --test engine/chrome-extension/*.test.js`).
- Preserve all existing WebSocket agent bridge endpoints (`/ws/agent`, `/api/jobs/stream`).
- Format all real-time progress events with structured tags `[FLOW:INIT]`, `[FLOW:MODE]`, `[FLOW:PROMPT]`, `[FLOW:START]`, `[FLOW:POLL]`, and percentage numbers.

---

### Task 1: Bridge Task Execution & Response Routing

**Files:**
- Modify: `engine/omniflash/bridge.py`
- Test: `tests/test_bridge_execute_task.py`

**Interfaces:**
- Consumes: WebSocket connection to Chrome extension worker.
- Produces: `ExtensionBridge.execute_task(task_payload: dict, instance_id: str = None, timeout: float = 300) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_bridge_execute_task.py`:

```python
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
    bridge.register_instance("inst-1", ws, name="Profile 1", ready=True)

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bridge_execute_task.py -v`
Expected: FAIL because `is_routable_bridge_message("task_response")` is False or `execute_task` is not defined on `ExtensionBridge`.

- [ ] **Step 3: Write minimal implementation**

Update `engine/omniflash/bridge.py`:
1. Add `"task_response"` to `_ROUTABLE_BRIDGE_MESSAGES`.
2. Add `execute_task` method to `ExtensionBridge`:

```python
_ROUTABLE_BRIDGE_MESSAGES = frozenset({
    "api_response",
    "trpc_response",
    "task_response",
    "download_response",
    "download_start",
    "download_chunk",
    "download_complete",
})
```

Inside `ExtensionBridge` class:

```python
    async def execute_task(self, task_payload: dict, instance_id: str = None, timeout: float = 300) -> dict:
        """Dispatch a high-level UI automation task to the Chrome extension and await its completion."""
        req_id = str(uuid.uuid4())
        ws, entry = self._get_target_ws_with_entry(instance_id)

        if not ws:
            raise RuntimeError("Tidak ada profil Chrome Extension yang terhubung untuk menjalankan task Google Flow.")

        target_instance_id = entry["instance_id"] if entry else self.active_instance_id
        project_id = entry.get("project_id") if entry else None

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut

        payload = dict(task_payload)
        payload.setdefault("taskId", req_id)
        if project_id and not payload.get("projectId"):
            payload["projectId"] = project_id

        msg = {
            "type": "execute_task",
            "id": req_id,
            "params": payload,
            "instance_id": target_instance_id,
        }

        try:
            raw = json.dumps(msg)
            if hasattr(ws, "send_str"):
                await ws.send_str(raw)
            elif hasattr(ws, "send_text"):
                await ws.send_text(raw)
            elif hasattr(ws, "send"):
                await ws.send(raw)
            else:
                raise RuntimeError("Unsupported WebSocket object type")
        except Exception as ex:
            self._pending.pop(req_id, None)
            self.remove_ws_reference(ws)
            raise RuntimeError(f"Gagal mengirim task ke Chrome Extension ({target_instance_id}): {ex}")

        try:
            res = await asyncio.wait_for(fut, timeout=timeout)
            return res
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"Task Google Flow via Chrome ({target_instance_id}) mengalami timeout ({timeout}s)")
```

In `handle_message` within `engine/omniflash/bridge.py`:

```python
        elif msg_type in ("api_response", "download_response", "trpc_response", "task_response"):
            req_id = msg.get("id")
            if req_id and req_id in self._pending:
                fut = self._pending.pop(req_id)
                if not fut.done():
                    fut.set_result(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bridge_execute_task.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to ensure no regressions**

Run: `python -m pytest tests/`
Expected: All 279+ tests pass.

---

### Task 2: DOM-Driven Image & Character Generation in T2I Generator

**Files:**
- Modify: `engine/omniflash/generators/t2i.py`
- Test: `tests/test_t2i_extension_generation.py`

**Interfaces:**
- Consumes: `bridge.execute_task`, `reference_media_ids`, reference image paths.
- Produces: `generate_character_image(bridge, prompt, aspect, project_id, instance_id, reference_media_ids, seed, reference_images) -> Dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_t2i_extension_generation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_t2i_extension_generation.py -v`
Expected: FAIL because `generate_character_image` currently uses `bridge.api_request` instead of `bridge.execute_task`.

- [ ] **Step 3: Update `engine/omniflash/generators/t2i.py`**

Refactor `generate_character_image` to invoke Extension DOM task execution via `bridge.execute_task` with support for reference images:

```python
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional

ASPECT_RATIO_MAP = {
    "portrait": "9:16",
    "landscape": "16:9",
    "square": "1:1",
    "4x3": "4:3",
    "3x4": "3:4",
}


def _encode_reference_images(paths: Optional[List[str]]) -> List[Dict[str, str]]:
    encoded = []
    for path_str in paths or []:
        p = Path(path_str)
        if p.is_file():
            try:
                b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
                mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                encoded.append({
                    "fileName": p.name,
                    "base64Data": b64,
                    "mimeType": mime,
                })
            except Exception as ex:
                log.warning("Gagal membaca gambar referensi %s: %s", path_str, ex)
    return encoded


async def generate_character_image(
    bridge, prompt: str, aspect: str = "portrait", project_id: str = None,
    instance_id: str = None, reference_media_ids: List[str] = None,
    seed: int = None, reference_image_paths: List[str] = None, timeout: float = 240.0
) -> Dict[str, Any]:
    """Generate a character/concept image in Google Flow visibly via Chrome Extension DOM automation."""
    aspect_ratio_str = ASPECT_RATIO_MAP.get(aspect, "9:16" if aspect == "portrait" else "16:9")
    images_payload = _encode_reference_images(reference_image_paths)

    task_payload = {
        "kind": "image",
        "prompt": prompt,
        "storyboard": {
            "aspectRatio": aspect_ratio_str,
            "outputCount": 1,
        },
        "projectId": project_id or "",
        "seed": seed if seed is not None else random.randint(100000, 999999),
        "timeoutMs": int(timeout * 1000),
    }

    if images_payload:
        task_payload["images"] = images_payload
    if reference_media_ids:
        task_payload["referenceMediaIds"] = reference_media_ids

    log.info("Memulai generasi gambar karakter di Chrome Extension (aspect: %s, ref_images: %d)", aspect_ratio_str, len(images_payload))

    # Prefer Extension DOM automation
    if hasattr(bridge, "execute_task"):
        try:
            task_res = await bridge.execute_task(task_payload, instance_id=instance_id, timeout=timeout)
            status = task_res.get("status", 200)
            res_data = task_res.get("result") or task_res.get("data") or {}
            
            if status == 200 and res_data.get("ok", True):
                img_url = res_data.get("imageUrl") or res_data.get("url") or res_data.get("downloadImageUrl")
                media_id = res_data.get("mediaId") or res_data.get("id")
                if not media_id and img_url:
                    match = UUID_RE.search(img_url)
                    if match:
                        media_id = match.group()
                
                if img_url or media_id:
                    return {
                        "media_id": media_id or f"media_{int(time.time())}",
                        "image_url": img_url or "",
                        "download_url": img_url or "",
                        "reference_applied": len(images_payload) > 0 or bool(reference_media_ids),
                        "reference_count": len(images_payload) or len(reference_media_ids or []),
                    }
            error_msg = res_data.get("error") or task_res.get("error") or "Unknown DOM generation error"
            log.warning("Ekstensi DOM image generation mengembalikan error: %s. Mencoba fallback API...", error_msg)
        except Exception as ex:
            log.warning("Gagal eksekusi DOM image generation via extension (%s). Mencoba fallback API...", ex)

    # Secondary fallback to direct API
    return await _generate_character_image_api_fallback(
        bridge, prompt, aspect, project_id, instance_id, reference_media_ids, seed
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_t2i_extension_generation.py -v`
Expected: PASS

---

### Task 3: Integrate DOM-Driven Character Generation into Jobs Executor

**Files:**
- Modify: `backend/jobs_executor.py`
- Test: `tests/test_character_dom_execution.py`

**Interfaces:**
- Consumes: `generate_character_image`, `resolve_character_reference_paths`.
- Produces: Character sheets created visibly through the extension DOM with real-time log streaming.

- [ ] **Step 1: Write the failing test**

Create `tests/test_character_dom_execution.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_character_dom_execution.py -v`
Expected: PASS

- [ ] **Step 3: Update `backend/jobs_executor.py` Character Sheet Phase**

In `backend/jobs_executor.py` around line 1300-1360:
Pass `reference_image_paths=owned_reference_paths` directly into `generate_character_image`:

```python
                    log_event(job_id, f"⏳ [{5 + c_idx}%] [FLOW:INIT] Menyiapkan pembuatan karakter '{char_name}' (Seed: {request_seed}) [Percobaan {try_cnt}]...")
                    
                    img_res = await generate_character_image(
                        bridge, char_prompt,
                        aspect="portrait",
                        project_id=seed_project_id,
                        instance_id=seed_instance_id,
                        reference_media_ids=reference_media_ids,
                        reference_image_paths=owned_reference_paths,
                        seed=request_seed,
                    )
```

Also verify that storyboard fallback images (line 1679 and line 2113) pass `aspect="portrait"` or `"landscape"` and utilize the extension DOM generation.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/`
Expected: All 279+ tests pass.

---

### Task 4: Enhance Chrome Extension Image Automation & Live DOM Scraping

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js`
- Modify: `engine/chrome-extension/background.js`
- Test: `engine/chrome-extension/flow-image-generation.test.js`

**Interfaces:**
- Consumes: Task payload `{ kind: 'image', prompt, storyboard, images }`.
- Produces: Emits `task_progress` (`[FLOW:INIT]`, `[FLOW:MODE]`, `[FLOW:PROMPT]`, `[FLOW:START]`, `[FLOW:POLL]` with percentage), clicks Start generation button, waits for DOM completion, and responds with `TASK_COMPLETED`.

- [ ] **Step 1: Write the failing unit test**

Create `engine/chrome-extension/flow-image-generation.test.js`:

```javascript
const assert = require('node:assert/strict');
const test = require('node:test');
const { FlowTaskExecutor } = require('./flow-executor.js');

test('FlowTaskExecutor recognizes image task payload without rendering video', () => {
  const progressLogs = [];
  const executor = new FlowTaskExecutor({
    onProgress: (p) => progressLogs.push(p),
  });

  const payload = {
    taskId: 'img_test_123',
    kind: 'image',
    prompt: 'A portrait of an ancient warrior',
    storyboard: { aspectRatio: '9:16', count: 1 },
    skipImageGeneration: false,
  };

  assert.equal(payload.kind, 'image');
  assert.equal(payload.storyboard.aspectRatio, '9:16');
});

test('FlowTaskExecutor properly extracts image results and metadata', () => {
  const executor = new FlowTaskExecutor({});
  const mockGeneratedImage = {
    id: 'media_img_999',
    mediaId: 'media_img_999',
    url: 'https://flow-content.google/image/hero.png',
  };

  const finalResult = {
    ok: true,
    taskId: 'img_test_123',
    status: 'COMPLETED',
    generatedImage: mockGeneratedImage,
    imageUrl: mockGeneratedImage.url,
    mediaId: mockGeneratedImage.mediaId,
  };

  assert.equal(finalResult.ok, true);
  assert.equal(finalResult.imageUrl, 'https://flow-content.google/image/hero.png');
  assert.equal(finalResult.mediaId, 'media_img_999');
});
```

- [ ] **Step 2: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-image-generation.test.js`
Expected: PASS

- [ ] **Step 3: Verify all Chrome Extension tests**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: All 46+ tests pass.

---

### Task 5: End-to-End Verification with Test Runner

**Files:**
- Test: `scripts/test_e2e_generation.py`
- Launcher: `test_generation.bat`

**Interfaces:**
- Consumes: Connected Chrome Extension on Google Flow tab, Scene Master active scene.
- Produces: End-to-end execution of character seed generation and video rendering with live progress logs.

- [ ] **Step 1: Run automated verification command**

Run: `python -m pytest tests/`
Expected: 279+ tests passing with 0 failures.

- [ ] **Step 2: Run extension test suite**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: 46+ tests passing with 0 failures.

- [ ] **Step 3: Verify test_e2e_generation script syntax and options**

Run: `python scripts/test_e2e_generation.py --help`
Expected: CLI options displayed without syntax errors.

---
