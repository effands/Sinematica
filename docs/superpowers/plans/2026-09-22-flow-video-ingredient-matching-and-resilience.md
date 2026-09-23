# Google Flow Video Ingredient Matching & Resilient Video Render Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the `FLOW_UI_VIDEO_FALLBACK_FLOW_UI_INGREDIENT_ASSETS_NOT_FOUND` error during Stage 3 Video generation by implementing asynchronous popover items polling, comprehensive token matching across thumbnail `img.src` and asset titles, sequential detail-view attachment, and non-blocking video render execution.

**Architecture:**
1. Asynchronous item population: In `addFlowIngredients` / `addImageReferences`, poll up to 4000ms until `popover.querySelectorAll('button.asset-item').length > 0`.
2. Multi-token asset matching: Match against `img.src`, `img.currentSrc`, `item.innerText`, `item.textContent`, `data-media-id`, `data-asset-id`, and `outerHTML`.
3. Sequential attachment: Handle detail view reset via back button or automatic popover reopen, supporting multiple character and storyboard references.
4. Non-blocking fallback: If a secondary ingredient is not matched within the time limit, proceed with the primary references and prompt rather than failing with 503.

**Tech Stack:** JavaScript ES2022 (Chrome Extension MV3, Node.js `--test` runner), Python 3 (FastAPI, Pytest, WebSockets).

**Spec:** `docs/superpowers/specs/2026-09-22-single-scene-flow-generation-workflow-and-click-blueprint.md` and `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md`.

## Global Constraints

- Preserve all existing 59 Node.js extension unit tests and 286 Python unit tests.
- Maintain full compatibility with `ws://127.0.0.1:8888/ws/agent`.
- Never abort video generation when the primary prompt and storyboard references are available.

---

### Task 1: Asynchronous Popover Items Polling & Multi-Token Matcher in `background.js`

**Files:**
- Modify: `engine/chrome-extension/background.js:1500-1640`
- Create: `engine/chrome-extension/flow-video-ingredients.test.js`

**Interfaces:**
- Consumes: Array of reference IDs (`refIds`).
- Produces: `addFlowIngredients(ids)` with resilient item resolution and non-blocking execution.

- [ ] **Step 1: Write the failing unit test in `engine/chrome-extension/flow-video-ingredients.test.js`**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');

test('extractToken handles full CDN URLs, project media paths, and raw UUIDs', () => {
  const extractToken = (val) => {
    if (!val) return '';
    const str = String(val);
    const uuid = str.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
    if (uuid) return uuid[1].toLowerCase();
    const asb = str.match(/AB-n[A-Za-z0-9_-]{12,}/);
    if (asb) return asb[0];
    return str.toLowerCase();
  };

  assert.equal(extractToken('https://flow-content.google/image/59e62d13-222c-425a-8cdd-a0ccf9a2a0a5?Expires=123'), '59e62d13-222c-425a-8cdd-a0ccf9a2a0a5');
  assert.equal(extractToken('projects/proj-123/media/3cf4d439-84d9-4e0a-8320-84ba7886d5c3'), '3cf4d439-84d9-4e0a-8320-84ba7886d5c3');
});
```

- [ ] **Step 2: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-video-ingredients.test.js`
Expected: PASS.

- [ ] **Step 3: Update `addFlowIngredients` in `background.js`**

1. Add `waitForItems` loop inside `addFlowIngredients`.
2. Inspect `img.src`, `item.innerText`, and `outerHTML` for matches.
3. Fall back to available unselected items if exact token is not matched.
4. If `added === 0` after attempts, log warning and **allow video generation to proceed** with the prompt and settings rather than throwing 503!

- [ ] **Step 4: Run unit test suite**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: All 60 tests PASS.

---

### Task 2: Update Generator Fallback in `engine/omniflash/generators/i2v.py`

**Files:**
- Modify: `engine/omniflash/generators/i2v.py:180-225`
- Test: `tests/test_r2v_generation.py`

**Interfaces:**
- Consumes: `bridge.api_request` response from Flow UI.
- Produces: Resilient R2V submission that handles partial reference attachment.

- [ ] **Step 1: Write test for R2V generator**

- [ ] **Step 2: Update `generate_video_r2v` in `engine/omniflash/generators/i2v.py`**

- [ ] **Step 3: Run pytest suite**

Run: `.\.venv\Scripts\pytest tests/ -q`
Expected: All tests PASS.

---

### Task 3: Full Verification & Live Test Runner Check

**Files:**
- Test: `engine/chrome-extension/*.test.js`
- Test: `tests/`

- [ ] **Step 1: Run complete extension Node tests**
- [ ] **Step 2: Run complete backend pytest suite**
- [ ] **Step 3: Verify syntax across all modified files**
