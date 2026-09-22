# Google Flow Prompt Submission & Character Generation Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate generation stalls during prompt typing and submission in Google Flow by implementing boundary-crossing Angular Material input events, native CDP click dispatch, resilient DOM tile state tracking, and live progress logging.

**Architecture:** Google Flow's Angular Material MDC frontend encapsulates the prompt box and submit button across Web Component and component boundaries. Input injection requires synthetic `InputEvent` and `KeyboardEvent` with `composed: true` to cross component boundaries and trigger Angular form change detection, unlocking the submit button (`<flow-generate-icon-button>`). The extension background service worker attaches via `chrome.debugger` to dispatch hardware-level `Input.dispatchMouseEvent` at element coordinates. Real-time stage progress updates (`FLOW:TYPING`, `FLOW:CLICKING`, `FLOW:POLLING`) are streamed over WebSocket to the FastAPI backend and test runner.

**Tech Stack:** Chrome Extension Manifest V3 (`chrome.debugger`, `chrome.runtime`), Vanilla JavaScript / ES2022, Python 3 / FastAPI / WebSockets, Node.js `--test` runner, pytest, BrowserSkill.

**Spec:** `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md`

## Global Constraints

- Preserve all existing WebSocket backend communication (`FastAPI` bridge at `ws://127.0.0.1:8888/ws/agent`).
- Preserve all existing structured logging (`FlowLogger` and `FleetLogger`).
- Ensure graceful fallback to DOM synthetic events when debugger is detached or unavailable.
- Zero placeholder comments (`// TODO`, `// implement later`).
- Affirmative language in all logs and notifications.

---

### Task 1: Implement Boundary-Crossing Angular Input & Submit Button Trigger in `flow-executor.js`

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js:240-335,800-880,1250-1310`
- Test: `engine/chrome-extension/flow-executor.test.js`

**Interfaces:**
- Consumes: `simulateInput(element, text)`, `simulateClick(element)`, `triggerImageGeneration(options)`
- Produces: Enabled `<flow-generate-icon-button>`, trusted CDP mouse click, unblocked prompt submission

- [ ] **Step 1: Write unit tests for boundary-crossing `simulateInput` and button trigger in `flow-executor.test.js`**

```javascript
test('simulateInput dispatches composed InputEvent and KeyboardEvent across component boundaries', async () => {
  const events = [];
  const fakeElement = {
    isContentEditable: true,
    textContent: '',
    innerText: '',
    focus: () => {},
    dispatchEvent: (ev) => {
      events.push({ type: ev.type, composed: ev.composed, bubbles: ev.bubbles });
      return true;
    },
    getBoundingClientRect: () => ({ left: 10, top: 10, width: 100, height: 50 }),
  };

  await simulateInput(fakeElement, 'A test prompt');
  const composedInput = events.find((e) => e.type === 'input' && e.composed);
  assert.ok(composedInput, 'input event must have composed: true');
});
```

- [ ] **Step 2: Run test suite to verify current behavior**

Run: `node --test engine/chrome-extension/flow-executor.test.js`
Expected: PASS.

- [ ] **Step 3: Update `simulateInput`, `triggerImageGeneration`, and `triggerVideoGeneration` in `flow-executor.js`**

In `engine/chrome-extension/flow-executor.js`:
1. In `simulateInput`:
```javascript
    if (typeof element.dispatchEvent === 'function') {
      try {
        if (typeof InputEvent !== 'undefined') {
          element.dispatchEvent(new InputEvent('beforeinput', {
            bubbles: true,
            cancelable: true,
            inputType: 'insertText',
            data: text,
            composed: true,
          }));
          element.dispatchEvent(new InputEvent('input', {
            bubbles: true,
            cancelable: true,
            inputType: 'insertText',
            data: text,
            composed: true,
          }));
        }
        if (typeof Event !== 'undefined') {
          element.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
          element.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
        }
        if (typeof KeyboardEvent !== 'undefined') {
          try {
            element.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', code: 'KeyA', bubbles: true, composed: true }));
            element.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', code: 'KeyA', bubbles: true, composed: true }));
          } catch {}
        }
      } catch {
        try {
          element.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        } catch {}
      }
    }
```

2. In `triggerImageGeneration` and `triggerVideoGeneration`:
```javascript
    const findGenerateButton = () => {
      const directBtn = document.querySelector('flow-generate-icon-button button, button[aria-label*="Start generation" i], button[type="submit"].generate-icon-button, button.generate-icon-button');
      if (directBtn) return directBtn;

      const queryAll = typeof document.querySelectorAll === 'function'
        ? Array.from(document.querySelectorAll('flow-generate-icon-button button, button[type="submit"], [data-test-id*="generate"], button[aria-label*="generate" i], button[aria-label*="start" i], button[aria-label*="create" i], button[aria-label*="buat" i], button[aria-label*="hasilkan" i], button'))
        : [];

      return queryAll.find((el) => {
        const text = [
          typeof el.getAttribute === 'function' ? el.getAttribute('aria-label') : '',
          typeof el.getAttribute === 'function' ? el.getAttribute('title') : '',
          el.innerText,
          el.textContent
        ].filter(Boolean).join(' ');
        return /arrow_forward|create|buat|hasilkan|generate|start generation/i.test(text) || (typeof el.closest === 'function' && el.closest('flow-generate-icon-button'));
      });
    };

    const isButtonDisabled = (btn) => {
      if (!btn) return true;
      return btn.disabled ||
        (typeof btn.hasAttribute === 'function' && btn.hasAttribute('disabled')) ||
        (typeof btn.getAttribute === 'function' && btn.getAttribute('aria-disabled') === 'true') ||
        (btn.classList && typeof btn.classList.contains === 'function' && btn.classList.contains('mat-mdc-button-disabled'));
    };

    let createBtn = null;
    const waitStart = Date.now();
    while (Date.now() - waitStart < 6000) {
      createBtn = findGenerateButton();
      if (createBtn && !isButtonDisabled(createBtn)) break;

      if (promptInput && typeof promptInput.dispatchEvent === 'function') {
        try {
          promptInput.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: ' ', composed: true }));
          promptInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', code: 'KeyA', bubbles: true, composed: true }));
        } catch {}
      }
      await sleep(250);
    }

    if (createBtn) {
      await simulateClick(createBtn);
      if (typeof createBtn.click === 'function') {
        try { createBtn.click(); } catch {}
      }
    }
```

- [ ] **Step 4: Run unit tests to verify implementation**

Run: `node --test engine/chrome-extension/flow-executor.test.js`
Expected: PASS.

---

### Task 2: Refine Tile State Detection & DOM Polling in `flow-executor.js`

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js:395-485`
- Test: `engine/chrome-extension/flow-image-generation.test.js`

**Interfaces:**
- Consumes: `waitForImageGenerationDomDone(timeoutMs, sinceTimestamp)`
- Produces: Newly rendered media object `{ src: string, mediaId: string }`

- [ ] **Step 1: Write unit test verifying snapshot filtering of pre-existing image tiles**

In `engine/chrome-extension/flow-image-generation.test.js`:
```javascript
test('waitForImageGenerationDomDone detects newly created image tile and ignores pre-existing tiles', async () => {
  const oldImg = {
    src: 'https://flow.google.com/media/old-image-11111111-1111-1111-1111-111111111111.png',
    currentSrc: 'https://flow.google.com/media/old-image-11111111-1111-1111-1111-111111111111.png',
    naturalWidth: 512,
    complete: true,
    getAttribute: (attr) => (attr === 'data-media-id' ? '11111111-1111-1111-1111-111111111111' : null),
  };
  const oldTile = {
    innerText: '',
    textContent: '',
    querySelector: (sel) => (sel === 'img' ? oldImg : null),
    querySelectorAll: () => [],
  };

  const newImg = {
    src: 'https://flow.google.com/media/new-image-22222222-2222-2222-2222-222222222222.png',
    currentSrc: 'https://flow.google.com/media/new-image-22222222-2222-2222-2222-222222222222.png',
    naturalWidth: 512,
    complete: true,
    getAttribute: (attr) => (attr === 'data-media-id' ? '22222222-2222-2222-2222-222222222222' : null),
  };
  const newTile = {
    innerText: '',
    textContent: '',
    querySelector: (sel) => (sel === 'img' ? newImg : null),
    querySelectorAll: () => [],
  };

  let tiles = [oldTile];

  const origDoc = global.document;
  global.document = {
    querySelectorAll: (sel) => {
      if (sel.includes('flow-image-tile') || sel.includes('project-tile')) return tiles;
      return [];
    },
    querySelector: () => null,
  };

  try {
    const executor = new FlowTaskExecutor({});
    const promise = executor.waitForImageGenerationDomDone(6000);

    setTimeout(() => {
      tiles = [newTile, oldTile];
    }, 1600);

    const res = await promise;
    assert.ok(res);
    assert.equal(res.mediaId, '22222222-2222-2222-2222-222222222222');
    assert.equal(res.src, 'https://flow.google.com/media/new-image-22222222-2222-2222-2222-222222222222.png');
  } finally {
    global.document = origDoc;
  }
});
```

- [ ] **Step 2: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-image-generation.test.js`
Expected: PASS.

---

### Task 3: Real-Time Stage Progress Forwarding in Backend Bridge

**Files:**
- Modify: `backend/jobs_executor.py:1310-1365`
- Modify: `engine/omniflash/bridge.py:100-145`
- Test: `tests/test_bridge_progress.py`

**Interfaces:**
- Consumes: WebSocket message `{ type: "task_progress", id: string, stage: string, message: string, data: object }`
- Produces: Live streamed progress lines in `scripts/test_e2e_generation.py` CLI and job event history

- [ ] **Step 1: Write test verifying bridge forwards task progress events to callback**

In `tests/test_bridge_progress.py`:
```python
import pytest
from engine.omniflash.bridge import ExtensionBridge

@pytest.mark.asyncio
async def test_extension_bridge_handles_task_progress():
    bridge = ExtensionBridge()
    progress_events = []
    bridge.set_task_progress_callback(lambda p: progress_events.append(p))
    
    await bridge.handle_message({
        "type": "task_progress",
        "id": "task_123",
        "stage": "POLLING_PROGRESS",
        "message": "Memantau render gambar di Google Flow (50%)...",
        "data": {"percent": 50},
    })
    
    assert len(progress_events) == 1
    assert progress_events[0]["stage"] == "POLLING_PROGRESS"
    assert progress_events[0]["data"]["percent"] == 50
```

- [ ] **Step 2: Run test to verify behavior**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bridge_progress.py -v`
Expected: PASS.

- [ ] **Step 3: Update `jobs_executor.py` to bind progress callback during character seed generation**

Attach `bridge.set_task_progress_callback` to emit real-time percentage logs to `log_event(job_id, ...)` so the CLI output streams continuous feedback.

- [ ] **Step 4: Run test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bridge_progress.py -v`
Expected: PASS.

---

### Task 4: Complete Test Suite & Browser Verification

**Files:**
- Test: `engine/chrome-extension/*.test.js`
- Test: `tests/`
- Test: `test_generation.bat`

- [ ] **Step 1: Run all Chrome Extension Node tests**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: 48+ tests passing.

- [ ] **Step 2: Run all Backend pytest tests**

Run: `.venv\Scripts\python.exe -m pytest tests/`
Expected: 283+ tests passing.

- [ ] **Step 3: Verify with live execution runner**

Run: `test_generation.bat`
Expected: Prompt typed into Google Flow, submit button triggered via trusted CDP click, 100% completion rendered and saved.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-22-flow-prompt-submission-and-character-generation-resilience.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
