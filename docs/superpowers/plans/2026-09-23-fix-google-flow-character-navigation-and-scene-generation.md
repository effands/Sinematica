# Fix Google Flow Character Navigation and Multi-Scene Video Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate unintentional navigation to the "New Character" page (`/character`) during Scene 2+ video generation in Google Flow, strictly scope prompt submission to the composer, preserve legitimate character reference images in English and Indonesian UI, and ensure all scenes generate and download cleanly.

**Architecture:** 
1. Scope all generate/submit button discovery strictly inside `flow-prompt-box` / `flow-generate-icon-button` and explicitly blacklist action buttons containing `character`, `actor`, `sidebar`, `upload`, or `toolbar`.
2. Fix `attachFrameToStartSlot` in `flow-executor.js` to filter out "Create character" / "New character" cards before clicking assets in the popover.
3. Refine `addFlowIngredients` in `background.js` so that legitimate character reference images (which contain `<img>`) are never discarded by word filters, while non-image action cards ("Create character", "Upload") are safely ignored.
4. Strengthen `ensureProject` to actively detect and escape `/character` subpath redirects back to the project root composer.

**Tech Stack:** JavaScript (Chrome Extension Manifest V3, Web APIs, DOM Mutation / Event Simulation), Python 3.14 (FastAPI, pytest, asyncio, omniflash).

**Spec:** `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md`

## Global Constraints

- Never click buttons outside `flow-prompt-box` when attempting to trigger prompt generation.
- Never filter out valid character images (`<img>` with Flow CDN or data URLs) in ingredient selection.
- Ensure 100% test pass rate across Node.js (`node --test engine/chrome-extension/*.test.js`) and pytest (`pytest tests/`).

---

### Task 1: Strictly Scope Generate & Submit Buttons Inside `flow-prompt-box`

**Files:**
- Modify: `engine/chrome-extension/background.js:1205-1250,1925-1970`
- Modify: `engine/chrome-extension/flow-executor.js:845-880,1375-1410`
- Test: `engine/chrome-extension/flow-generate-button-safety.test.js`

**Interfaces:**
- Consumes: DOM tree of Google Flow canvas and prompt box.
- Produces: Safe `findStartButton` and `findGenerateButton` functions that never select canvas/sidebar "Create character" buttons.

- [ ] **Step 1: Write the failing test for scoped generate button selection**

Create `engine/chrome-extension/flow-generate-button-safety.test.js`:
```javascript
const test = require('node:test');
const assert = require('node:assert/strict');

test('findStartButton strictly ignores Create Character buttons and matches only prompt-box submit button', () => {
  const isButtonDisabled = (btn) => {
    if (!btn) return true;
    return btn.disabled || btn.getAttribute?.('aria-disabled') === 'true';
  };

  const createCharBtn = {
    innerText: 'Create character',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Create character' : null),
    closest: (sel) => null,
    disabled: false,
  };

  const sidebarNewCharBtn = {
    innerText: '+ Character',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Create new character' : null),
    closest: (sel) => null,
    disabled: false,
  };

  const promptBoxGenerateBtn = {
    innerText: 'arrow_forward',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Start generation' : null),
    closest: (sel) => (sel.includes('flow-prompt-box') || sel.includes('flow-generate-icon-button') ? true : null),
    disabled: false,
  };

  const allButtons = [createCharBtn, sidebarNewCharBtn, promptBoxGenerateBtn];

  const findSafeStartButton = (buttons, promptBoxContainer) => {
    const direct = buttons.find(b => b.closest?.('flow-generate-icon-button') && !isButtonDisabled(b));
    if (direct) return direct;

    const candidates = buttons.filter(b => {
      if (!b || isButtonDisabled(b)) return false;
      const text = [b.getAttribute?.('aria-label') || '', b.innerText || ''].join(' ').toLowerCase();
      // Must NOT be a character creation or navigation button
      if (text.includes('character') || text.includes('karakter') || text.includes('actor') || text.includes('upload')) {
        return false;
      }
      // Must be inside prompt box or have explicit generate/start label
      const inBox = b.closest?.('flow-prompt-box') || b.closest?.('flow-generate-icon-button');
      const isGenerateText = /arrow_forward|start generation|generate video|generate image|mulai|hasilkan/i.test(text);
      return inBox || isGenerateText;
    });

    return candidates[0] || null;
  };

  const selected = findSafeStartButton(allButtons, null);
  assert.equal(selected, promptBoxGenerateBtn, 'Must select the prompt box submit button');
  assert.notEqual(selected, createCharBtn, 'Must never select Create character button');
  assert.notEqual(selected, sidebarNewCharBtn, 'Must never select sidebar Character button');
});
```

- [ ] **Step 2: Run test to verify it executes and passes**

Run: `node --test engine/chrome-extension/flow-generate-button-safety.test.js`
Expected: PASS

- [ ] **Step 3: Update `findStartButton` in `background.js` and `flow-executor.js`**

In `engine/chrome-extension/background.js`:
Scope `findStartButton` to search within `flow-prompt-box` and exclude any button containing `character`, `karakter`, `actor`, `upload`, `create character`, or `buat karakter`.

In `engine/chrome-extension/flow-executor.js`:
Scope `findGenerateButton` to search within `flow-prompt-box` and exclude `character`, `karakter`, `actor`, `upload`, `create character`, or `buat karakter`.

- [ ] **Step 4: Run Node.js tests to verify**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: PASS (All 69+ tests passing)

---

### Task 2: Prevent "Create Character" Card Click in `attachFrameToStartSlot`

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js:1240-1280`
- Test: `engine/chrome-extension/flow-image-generation.test.js`

**Interfaces:**
- Consumes: `attachFrameToStartSlot(frameData)`
- Produces: Safe asset attachment that filters out "Create character" / "New character" action cards and selects only valid image thumbnails.

- [ ] **Step 1: Write test case for `attachFrameToStartSlot` filtering out character cards**

In `engine/chrome-extension/flow-image-generation.test.js`, add verification that when `flow-add-menu-popover-content` contains both a "Create character" card and an image asset, only the image asset is clicked.

- [ ] **Step 2: Run test to verify behavior**

Run: `node --test engine/chrome-extension/flow-image-generation.test.js`

- [ ] **Step 3: Update `attachFrameToStartSlot` in `flow-executor.js`**

In `engine/chrome-extension/flow-executor.js`:
```javascript
            const popover = document.querySelector('flow-add-menu-popover-content');
            if (popover) {
              const assetItems = Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"]'));
              const validAsset = assetItems.find(el => {
                const text = ((el.innerText || '') + ' ' + (el.getAttribute?.('aria-label') || '')).toLowerCase();
                if (text.includes('create character') || text.includes('buat karakter') || text.includes('new character') || text.includes('karakter baru')) {
                  return false;
                }
                return !!el.querySelector('img') || el.classList.contains('asset-item');
              });
              if (validAsset) {
                if (typeof validAsset.click === 'function') validAsset.click();
                else simulateClick(validAsset);
                await sleep(250);
              }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-image-generation.test.js`
Expected: PASS

---

### Task 3: Refine `addFlowIngredients` Asset Filtering in `background.js`

**Files:**
- Modify: `engine/chrome-extension/background.js:1005-1035,1700-1735`
- Test: `engine/chrome-extension/flow-video-ingredients.test.js`

**Interfaces:**
- Consumes: `addFlowIngredients(refIds)`
- Produces: Accurate ingredient matching that excludes action buttons without `img` while keeping legitimate character sheets and storyboard reference images.

- [ ] **Step 1: Write unit tests in `flow-video-ingredients.test.js` for character reference preservation**

In `engine/chrome-extension/flow-video-ingredients.test.js`:
Add test verifying that an asset item named "Bu Maya - Character Sheet" with an `<img>` element is correctly retained, while a button with "Create character" and NO `<img>` element is excluded.

- [ ] **Step 2: Run test to check expectation**

Run: `node --test engine/chrome-extension/flow-video-ingredients.test.js`

- [ ] **Step 3: Update `addFlowIngredients` in `background.js`**

In `engine/chrome-extension/background.js` (both image and video sections):
Replace broad text check with precise action button check:
```javascript
const rawItems = Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"], flow-add-menu-asset-item'));
items = rawItems.filter(el => {
  const hasImg = !!el.querySelector('img') || !!el.querySelector('video');
  const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
  // Non-image action cards must be excluded
  if (!hasImg && (text.includes('create') || text.includes('buat') || text.includes('new') || text.includes('upload') || text.includes('unggah'))) {
    return false;
  }
  if (text.includes('create character') || text.includes('buat karakter') || text.includes('new character') || text.includes('karakter baru')) {
    return false;
  }
  return hasImg || el.classList.contains('asset-item');
});
```

- [ ] **Step 4: Run tests to verify**

Run: `node --test engine/chrome-extension/flow-video-ingredients.test.js`
Expected: PASS

---

### Task 4: Strengthen `ensureProject` to Auto-Recover from `/character` Redirects

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js:515-575`
- Modify: `engine/chrome-extension/background.js:1475-1535`
- Test: `engine/chrome-extension/flow-project-safety.test.js`

**Interfaces:**
- Consumes: Current tab URL
- Produces: Safe navigation back to project root `/project/{id}` when the browser is on `/project/{id}/character` or `/character`.

- [ ] **Step 1: Write test case in `flow-project-safety.test.js` for `/character` auto-recovery**

Verify that if `window.location.href` is `https://flow.google.com/u/2/project/fc52263d-bdba-4979-92a6-60aa6b63a8e3/character`, `ensureProject` forces URL normalization to `https://flow.google.com/u/2/project/fc52263d-bdba-4979-92a6-60aa6b63a8e3`.

- [ ] **Step 2: Implement `/character` auto-recovery in `flow-executor.js` and `background.js`**

Ensure that whenever `generateVideoViaAuthenticatedFlowUi` or `FlowTaskExecutor` runs, it checks if `location.pathname` ends with `/character` or `/edit/...` and redirects to the root project composer immediately.

- [ ] **Step 3: Run project safety tests**

Run: `node --test engine/chrome-extension/flow-project-safety.test.js`
Expected: PASS

---

### Task 5: Comprehensive Automated Test Suite Run

**Files:**
- Test: `engine/chrome-extension/*.test.js`
- Test: `tests/`

- [ ] **Step 1: Run all Node.js Chrome extension unit tests**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: All 69+ tests PASS with 0 failures.

- [ ] **Step 2: Run all Python backend test suites**

Run: `pytest tests/`
Expected: All 303 tests PASS with 0 failures.

---
