# Multi-Lingual Google Flow UI Settings & Ingredients Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the `FLOW_UI_VIDEO_FALLBACK_FLOW_UI_VIDEO_MODE_CONTROL_MISSING` and `FLOW_UI_VIDEO_SETTINGS_NOT_APPLIED` errors by supporting multi-lingual UI labels (English, Indonesian, etc.) across settings trigger buttons, mode toggles, duration tokens (`8s` vs `8 dtk`), and ingredient categories (`Ingredients` vs `Bahan`).

**Architecture:**
1. CSS-Class First & Multi-Lingual Attribute Selectors:
   - Settings trigger: `button.settings-trigger-button, button[aria-label*="Settings" i], button[aria-label*="setelan" i]`
   - Add ingredients trigger: `button.add-menu-trigger, button[aria-label*="Add ingredients" i], button[aria-label*="Tambahkan bahan" i]`
   - Mode toggles: `video`, `image`, `gambar`
   - Video types: `ingredients`, `bahan`, `ingredient`, `frames`, `frame`
   - Durations: Map `8s` to both `8s`, `8 dtk`, `8`, `8sec`
   - Aspect ratio: Map `16:9` to `16:9`, `crop_16_9`
2. Popover Tab & Asset Matching:
   - Match both `image` and `gambar` tabs in asset popovers.
   - Match both desktop popover detail view (`flow-add-menu-popover-content`) and mobile overlay (`flow-mobile-add-menu`).
3. Non-breaking validation:
   - Validate settings application gracefully by inspecting toggle state across classes, attributes, and button child nodes.

**Tech Stack:** JavaScript ES2022 (Chrome Extension MV3, Node.js `--test` runner), Python 3 (FastAPI, Pytest, WebSockets).

**Spec:** `docs/superpowers/specs/2026-09-22-single-scene-flow-generation-workflow-and-click-blueprint.md` and `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md`.

## Global Constraints

- Never rely exclusively on English `aria-label` strings; always combine with CSS class names and multi-lingual fallbacks.
- Keep all unit tests passing (61+ Node.js tests and 286+ Python tests).
- Zero placeholders (`// TODO`).

---

### Task 1: Multi-Lingual Settings Trigger & Toggle Selectors in `background.js`

**Files:**
- Modify: `engine/chrome-extension/background.js:900-1150,1420-1680`
- Create: `engine/chrome-extension/multilingual-ui.test.js`

**Interfaces:**
- Consumes: Target settings (`mode`, `aspectRatio`, `duration`, `outputCount`).
- Produces: Resilient settings application across English, Indonesian, and localized Google Flow UIs.

- [ ] **Step 1: Write unit test in `engine/chrome-extension/multilingual-ui.test.js`**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');

test('Multi-lingual label finder matches English, Indonesian, and icon-prefixed tokens', () => {
  const normalize = (value) => (value || '').toLowerCase().trim();
  
  const matchToggle = (elementText, needle) => {
    const normText = normalize(elementText);
    const normNeedle = normalize(needle);
    const parts = normText.split(/[\s\n\r_-]+/);
    
    // Direct or part match
    if (parts.includes(normNeedle) || normText === normNeedle) return true;
    
    // Multi-lingual synonyms
    if (normNeedle === 'video') return parts.includes('video') || normText.includes('videocam');
    if (normNeedle === 'image') return parts.includes('image') || parts.includes('gambar') || normText.includes('image');
    if (normNeedle === 'ingredients') return parts.includes('ingredients') || parts.includes('bahan') || parts.includes('ingredient');
    if (normNeedle === 'frames') return parts.includes('frames') || parts.includes('frame') || parts.includes('bingkai');
    if (/^\d+s$/.test(normNeedle)) {
      const secNum = normNeedle.replace('s', '');
      return parts.includes(normNeedle) || parts.includes(`${secNum}s`) || parts.includes(`${secNum}dtk`) || parts.includes(secNum) || normText.includes(`${secNum} dtk`);
    }
    if (normNeedle === '16:9') return normText.includes('16:9') || parts.includes('16:9');
    if (normNeedle === '9:16') return normText.includes('9:16') || parts.includes('9:16');
    if (normNeedle === 'x1') return normText.includes('x1') || parts.includes('x1') || parts.includes('1');
    return false;
  };

  // English tests
  assert.equal(matchToggle('videocam\nVideo', 'video'), true);
  assert.equal(matchToggle('image\nImage', 'image'), true);
  assert.equal(matchToggle('chrome_extension\nIngredients', 'ingredients'), true);
  assert.equal(matchToggle('8s', '8s'), true);

  // Indonesian tests
  assert.equal(matchToggle('image\nGambar', 'image'), true);
  assert.equal(matchToggle('chrome_extension\nBahan', 'ingredients'), true);
  assert.equal(matchToggle('crop_free\nFrame', 'frames'), true);
  assert.equal(matchToggle('8 dtk', '8s'), true);
  assert.equal(matchToggle('10 dtk', '10s'), true);
  assert.equal(matchToggle('crop_16_9\n16:9', '16:9'), true);
  assert.equal(matchToggle('crop_9_16\n9:16', '9:16'), true);
});
```

- [ ] **Step 2: Run test to verify it passes**

Run: `node --test engine/chrome-extension/multilingual-ui.test.js`
Expected: PASS.

- [ ] **Step 3: Update `findLabelNode`, `selectedExact`, `clickExactEventually`, and `settings` button selectors in `background.js`**

Update lines in `generateImageViaAuthenticatedFlowUi` and `generateVideoViaAuthenticatedFlowUi` to use the multi-lingual matcher and class-based settings button trigger.

- [ ] **Step 4: Run all extension node tests**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: All tests PASS.

---

### Task 2: Multi-Lingual Popover Tab & Asset Selection in `background.js`

**Files:**
- Modify: `engine/chrome-extension/background.js:930-1030,1500-1630`
- Test: `engine/chrome-extension/flow-ingredients-safety.test.js`

**Interfaces:**
- Consumes: `ids` array.
- Produces: Popover navigation supporting `Images`, `Gambar`, `Semua`, `All` tabs and auto-attaching.

- [ ] **Step 1: Update tab and popover search in `background.js`**
- [ ] **Step 2: Run test suite**

Run: `node --test engine/chrome-extension/*.test.js; .\.venv\Scripts\pytest tests/ -q`
Expected: All tests PASS.

---

### Task 3: Full End-to-End Verification with Browser Skill

**Files:**
- Test: Live browser tab validation

- [ ] **Step 1: Run browser automation to verify settings toggle in Indonesian**
- [ ] **Step 2: Confirm complete test suite is 100% green**
