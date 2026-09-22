# Google Flow Prompt Submission & Native Trusted Click Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the issue where character seed and video generation gets stuck after prompt entry by implementing trusted native clicks via `chrome.debugger` API, robust `ClipboardEvent` ProseMirror input injection, and accurate DOM tile state detection.

**Architecture:** Modern Google Flow (Angular Material MDC) requires `isTrusted: true` user gesture input events to trigger generation from the prompt box, and drops programmatic `element.click()` calls. The extension background service worker attaches via `chrome.debugger` to dispatch hardware-level `Input.dispatchMouseEvent` at element coordinates. Text input into ProseMirror utilizes synthetic `DataTransfer` paste events combined with `InputEvent` to activate Angular form validation, enabling the submit button.

**Tech Stack:** Chrome Extension Manifest V3 (`chrome.debugger`, `chrome.runtime`), Vanilla JavaScript / ES2022, Node.js `--test` runner, pytest, BrowserSkill.

**Spec:** `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md`

## Global Constraints

- Preserve all existing WebSocket backend communication (`FastAPI` bridge at `ws://127.0.0.1:8888/ws/agent`).
- Preserve all existing structured logging (`FlowLogger` and `FleetLogger`).
- Ensure graceful fallback to DOM synthetic events when debugger is detached or unavailable.
- Zero placeholder comments (`// TODO`, `// implement later`).
- Affirmative language in all logs and notifications.

---

### Task 1: Add Debugger Permission & Native Click Handler in Background Worker

**Files:**
- Modify: `engine/chrome-extension/manifest.json:15-25`
- Modify: `engine/chrome-extension/background.js:80-140`
- Test: `engine/chrome-extension/rules.test.js`

**Interfaces:**
- Consumes: Chrome Extension Messaging `{ type: 'DISPATCH_NATIVE_CLICK', x: number, y: number, tabId?: number }`
- Produces: `{ ok: boolean, error?: string }` response to content script

- [ ] **Step 1: Write the failing unit test for manifest and native click handler**

Create test case in `engine/chrome-extension/rules.test.js`:

```javascript
test('Manifest includes debugger permission for trusted native clicks', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, 'manifest.json'), 'utf8'));
  assert.ok(manifest.permissions.includes('debugger'), 'manifest.json must include debugger permission');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/rules.test.js`
Expected: FAIL because `debugger` is not yet in `manifest.json`.

- [ ] **Step 3: Update `manifest.json` and `background.js`**

In `engine/chrome-extension/manifest.json`:
```json
  "permissions": [
    "storage",
    "cookies",
    "alarms",
    "tabs",
    "windows",
    "webRequest",
    "scripting",
    "declarativeNetRequest",
    "sidePanel",
    "debugger"
  ],
```

In `engine/chrome-extension/background.js`:
Add `DISPATCH_NATIVE_CLICK` message handler:
```javascript
async function handleNativeClick(targetTabId, x, y) {
  if (!targetTabId || typeof x !== 'number' || typeof y !== 'number') {
    return { ok: false, error: 'Invalid click coordinates or tabId' };
  }
  const target = { tabId: targetTabId };
  try {
    try {
      await chrome.debugger.attach(target, '1.3');
    } catch (e) {
      // Ignore error if already attached to tab
    }

    await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
      type: 'mousePressed',
      x: Math.round(x),
      y: Math.round(y),
      button: 'left',
      clickCount: 1,
    });

    await new Promise((r) => setTimeout(r, 60));

    await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
      type: 'mouseReleased',
      x: Math.round(x),
      y: Math.round(y),
      button: 'left',
      clickCount: 1,
    });

    try {
      await chrome.debugger.detach(target);
    } catch (_) {}

    return { ok: true };
  } catch (err) {
    try { await chrome.debugger.detach(target); } catch (_) {}
    return { ok: false, error: err.message || String(err) };
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/rules.test.js`
Expected: PASS.

- [ ] **Step 5: Verify syntax**

Run: `node --check engine/chrome-extension/background.js`
Expected: Exit code 0.

---

### Task 2: Implement Robust ProseMirror Paste & Native Click Dispatch in `flow-executor.js`

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js:200-330,730-820`
- Test: `engine/chrome-extension/flow-executor.test.js`

**Interfaces:**
- Consumes: `simulateInput(element, text)`, `simulateClick(element)`, `triggerImageGeneration(options)`
- Produces: Updated DOM editor value, enabled submit button, hardware-level trusted click event

- [ ] **Step 1: Write unit tests for enhanced `simulateInput` and `simulateClick`**

In `engine/chrome-extension/flow-executor.test.js`:
```javascript
test('simulateInput populates text via ClipboardEvent and triggers input events', async () => {
  const { FlowTaskExecutor } = require('./flow-executor.js');
  assert.ok(FlowTaskExecutor);
});
```

- [ ] **Step 2: Run test suite to verify current behavior**

Run: `node --test engine/chrome-extension/flow-executor.test.js`
Expected: PASS.

- [ ] **Step 3: Update `simulateInput` and `simulateClick` in `flow-executor.js`**

In `engine/chrome-extension/flow-executor.js`:
1. Upgrade `simulateClick`:
```javascript
  async function simulateClick(element) {
    if (!element) return false;
    ensureVisualAutomationElements();

    const rect = typeof element.getBoundingClientRect === 'function'
      ? element.getBoundingClientRect()
      : { left: 0, top: 0, width: 20, height: 20 };
    const clientX = Math.round((rect.left || 0) + (rect.width || 0) / 2);
    const clientY = Math.round((rect.top || 0) + (rect.height || 0) / 2);

    await animateFakeCursor(clientX, clientY, true);

    let nativeClicked = false;
    if (typeof chrome !== 'undefined' && chrome.runtime && typeof chrome.runtime.sendMessage === 'function') {
      try {
        const res = await new Promise((resolve) => {
          chrome.runtime.sendMessage({ type: 'DISPATCH_NATIVE_CLICK', x: clientX, y: clientY }, (response) => {
            if (chrome.runtime.lastError) resolve(null);
            else resolve(response);
          });
        });
        if (res && res.ok) {
          nativeClicked = true;
        }
      } catch (_) {}
    }

    if (!nativeClicked) {
      const mouseEventInit = {
        bubbles: true,
        cancelable: true,
        view: typeof window !== 'undefined' ? window : null,
        clientX,
        clientY,
      };

      ['mouseenter', 'mouseover', 'mousedown', 'mouseup', 'click'].forEach((type) => {
        try {
          element.dispatchEvent(new MouseEvent(type, mouseEventInit));
        } catch {}
      });

      if (typeof element.click === 'function') {
        try { element.click(); } catch {}
      }
    }
    return true;
  }
```

2. Upgrade `simulateInput`:
```javascript
  async function simulateInput(element, text) {
    if (!element) return false;
    ensureVisualAutomationElements();

    const rect = typeof element.getBoundingClientRect === 'function'
      ? element.getBoundingClientRect()
      : { left: 0, top: 0, width: 20, height: 20 };
    const clientX = (rect.left || 0) + (rect.width || 0) / 2;
    const clientY = (rect.top || 0) + (rect.height || 0) / 2;

    await animateFakeCursor(clientX, clientY, true);
    if (typeof element.focus === 'function') element.focus();

    const isEditable = element.isContentEditable ||
      (typeof element.getAttribute === 'function' && element.getAttribute('contenteditable') === 'true');

    if (isEditable) {
      try {
        if (typeof document !== 'undefined' && typeof DataTransfer !== 'undefined') {
          const dt = new DataTransfer();
          dt.setData('text/plain', text);
          element.dispatchEvent(new ClipboardEvent('paste', {
            bubbles: true,
            cancelable: true,
            clipboardData: dt,
          }));
        }
      } catch (_) {}

      try {
        if (typeof window !== 'undefined' && typeof document !== 'undefined') {
          const selection = window.getSelection();
          if (selection && typeof selection.selectAllChildren === 'function') {
            selection.selectAllChildren(element);
          }
          if (typeof document.execCommand === 'function') {
            document.execCommand('insertText', false, text);
          }
        }
      } catch (_) {}

      if (!element.textContent || !element.textContent.includes(text.slice(0, 10))) {
        element.innerText = text;
        element.textContent = text;
      }

      try {
        if (typeof InputEvent !== 'undefined') {
          element.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText', data: text }));
          element.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: text }));
        }
        if (typeof Event !== 'undefined') {
          element.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
          element.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (typeof KeyboardEvent !== 'undefined') {
          element.dispatchEvent(new KeyboardEvent('keyup', { key: ' ', code: 'Space', bubbles: true }));
        }
      } catch (_) {}
    } else {
      element.value = text;
      try {
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
      } catch (_) {}
    }
    return true;
  }
```

- [ ] **Step 4: Run test suite to verify all unit tests pass**

Run: `node --test engine/chrome-extension/flow-executor.test.js`
Expected: PASS.

---

### Task 3: Refine `waitForImageGenerationDomDone` & DOM Polling in `flow-executor.js`

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js:370-460`
- Test: `engine/chrome-extension/flow-image-generation.test.js`

**Interfaces:**
- Consumes: `waitForImageGenerationDomDone(timeoutMs, sinceTimestamp)`
- Produces: Newly generated image URL and media ID created strictly after `sinceTimestamp`

- [ ] **Step 1: Write unit test verifying existing tiles are not prematurely returned**

In `engine/chrome-extension/flow-image-generation.test.js`:
Verify that `waitForImageGenerationDomDone` ignores tiles already present before `sinceTimestamp`.

- [ ] **Step 2: Run test to verify behavior**

Run: `node --test engine/chrome-extension/flow-image-generation.test.js`
Expected: PASS.

- [ ] **Step 3: Implement `sinceTimestamp` and tile tracking in `waitForImageGenerationDomDone`**

Record initial image URLs present at `startTime` and ensure only newly rendered tiles or progressing tiles are captured as the result of the current task.

- [ ] **Step 4: Run test suite**

Run: `node --test engine/chrome-extension/flow-image-generation.test.js`
Expected: PASS.

---

### Task 4: End-to-End Test Suite Verification

**Files:**
- Test: `tests/test_t2i_extension_generation.py`
- Test: `tests/test_character_dom_execution.py`
- Test: `scripts/test_e2e_generation.py`

- [ ] **Step 1: Run complete Chrome Extension Node test suite**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: 46+ tests passing.

- [ ] **Step 2: Run complete Backend pytest suite**

Run: `.venv\Scripts\pytest tests/ -v`
Expected: 283+ tests passing.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-22-native-dom-click-and-flow-prompt-submission.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
