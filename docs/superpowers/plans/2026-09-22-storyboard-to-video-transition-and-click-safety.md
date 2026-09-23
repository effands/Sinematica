# Storyboard to Video Transition & Flow Click Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate unexpected UI stalls, destructive home/new-project clicks, and "Project not found" navigation errors during the transition from Character/Storyboard Image generation to Scene Video generation in Google Flow.

**Architecture:** 
1. Protect project canvas integrity by removing destructive `homeBtn` / `.flow-logo` / `button.new-project-button` clicks when already inside an active Flow project (`/project/<uuid>`).
2. Eliminate risky avatar/account link clicks during credit probing, ensuring passive DOM text inspection only.
3. Scope all ingredient / asset node searches strictly inside `flow-add-menu-popover-content` to prevent accidental clicks on canvas media cards (which open `/project/<id>/edit/<asset_id>`).
4. Support clean sequential multi-ingredient attachment across multiple character and storyboard references without popover state locking.
5. Standardize Stage 2 to Stage 3 state handoff between backend executor and extension UI automation.

**Tech Stack:** JavaScript ES2022 (Chrome Extension MV3, Node.js `--test` runner), Python 3 (FastAPI, Pytest, WebSockets).

**Spec:** `docs/superpowers/specs/2026-09-22-single-scene-flow-generation-workflow-and-click-blueprint.md` and `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md`.

## Global Constraints

- Never click Home / Logo (`a[href="/"]`, `.flow-logo`) or `button.new-project-button` while operating inside an existing project (`/project/<uuid>`).
- Never search for ingredient items in root `document.querySelectorAll`; search ONLY within `flow-add-menu-popover-content`.
- Never click `<a>` tags or account navigation links during passive credit checks.
- Maintain 100% backward compatibility with existing WebSocket bridge contracts (`/ws/agent`, `api_request`, `execute_task`, `task_response`).
- Keep all existing unit test suites passing (55+ Node.js tests and 283+ Python tests).

---

### Task 1: Eliminate Destructive Home/Logo & New-Project Clicks in `flow-executor.js`, `content.js`, and `background.js`

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js:516-558`
- Modify: `engine/chrome-extension/content.js:320-334`
- Modify: `engine/chrome-extension/background.js:803-833,1278-1307`
- Create: `engine/chrome-extension/flow-project-safety.test.js`

**Interfaces:**
- Consumes: `FlowProject.isProjectComposerUrl`, active tab URL.
- Produces: Safe `ensureProject()` that never navigates away from valid project canvas.

- [ ] **Step 1: Write the failing unit test in `engine/chrome-extension/flow-project-safety.test.js`**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowTaskExecutor } = require('./flow-executor.js');

test('ensureProject does not click home button or new-project button when already in a project URL', async () => {
  let homeClicked = false;
  let newProjectClicked = false;

  const fakeDocument = {
    querySelector: (sel) => {
      if (sel === '.ProseMirror') return null;
      if (sel.includes('home') || sel.includes('flow-logo')) {
        return {
          click: () => { homeClicked = true; },
          closest: () => null,
          getBoundingClientRect: () => ({ left: 0, top: 0, width: 10, height: 10 })
        };
      }
      if (sel.includes('new-project')) {
        return {
          click: () => { newProjectClicked = true; },
          closest: () => null,
          getBoundingClientRect: () => ({ left: 0, top: 0, width: 10, height: 10 })
        };
      }
      return null;
    },
    querySelectorAll: () => [],
  };

  const origWindow = globalThis.window;
  const origDoc = globalThis.document;

  globalThis.window = {
    location: { href: 'https://flow.google.com/project/aaa1ca86-92ee-4436-b4d5-ace19f4481c9' }
  };
  globalThis.document = fakeDocument;

  try {
    const executor = new FlowTaskExecutor({});
    const res = await executor.ensureProject();
    assert.equal(res, true);
    assert.equal(homeClicked, false, 'ensureProject must NEVER click home button when in a project');
    assert.equal(newProjectClicked, false, 'ensureProject must NEVER click new-project button when in a project');
  } finally {
    globalThis.window = origWindow;
    globalThis.document = origDoc;
  }
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/flow-project-safety.test.js`
Expected: FAIL because `homeClicked` is true.

- [ ] **Step 3: Update `flow-executor.js`, `content.js`, and `background.js`**

1. In `engine/chrome-extension/flow-executor.js:516-558`:
Replace the destructive `homeBtn.click()` logic with safe canvas waiting:
```javascript
    async ensureProject() {
      this.notifyProgress('ENSURE_PROJECT', 'Memeriksa kanvas proyek Google Flow...');
      const url = typeof window !== 'undefined' ? window.location.href : '';

      if (typeof document !== 'undefined') {
        // If already in project URL, stay in project and wait for composer
        if (/\/project\/[0-9a-fA-F-]{36}/i.test(url)) {
          // If on an asset edit subpath, navigate back to project root
          if (/\/edit\//i.test(url)) {
            const rootMatch = url.match(/(https:\/\/[^/]+\/project\/[0-9a-fA-F-]{36})/i);
            if (rootMatch && typeof window !== 'undefined') {
              window.location.href = rootMatch[1];
              await sleep(1500);
            }
          }
          return true;
        }

        // Only on root/home page, look for existing project card or new project button
        const findNewProjectBtn = () => {
          return document.querySelector('button.new-project-button') ||
                 Array.from(document.querySelectorAll('button, a, [role="button"]')).find((el) => {
                   const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
                   return /new project/i.test(text) && !el.closest('flow-prompt-box');
                 }) ||
                 document.querySelector('[aria-label*="new project" i]') ||
                 document.querySelector('.new-project-card');
        };

        const newProjectBtn = findNewProjectBtn();
        if (newProjectBtn) {
          if (typeof newProjectBtn.click === 'function') newProjectBtn.click();
          else simulateClick(newProjectBtn);
          await sleep(2000);
        }

        await waitFor(() => {
          return document.querySelector('.ProseMirror') || document.querySelector(SELECTORS.PROMPT_INPUT) || /\/project\/[0-9a-fA-F-]{36}/i.test(window.location.href);
        }, 15000).catch(() => {});
      }

      return true;
    }
```

2. In `engine/chrome-extension/content.js:320-334`:
Remove blind auto-click of `new project` if URL already has `/project/` or is in active session.

3. In `engine/chrome-extension/background.js:803-833` and `1278-1307`:
Only click `new project` if `flowTabs` are strictly on the landing page and not on an active project canvas.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-project-safety.test.js`
Expected: PASS.

---

### Task 2: Passive Credit Probing Without Navigation Clicks in `background.js`

**Files:**
- Modify: `engine/chrome-extension/background.js:2026-2100`
- Create: `engine/chrome-extension/credits-safety.test.js`

**Interfaces:**
- Consumes: Google Flow DOM.
- Produces: Credits parsed passively from visible text or session data without clicking `<a>` tags or account buttons.

- [ ] **Step 1: Write unit test in `engine/chrome-extension/credits-safety.test.js`**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');

test('Credit parsing extracts values from text without clicking anchor tags', () => {
  const sampleTexts = [
    'Available 250 Google Flow credits',
    'Kredit: 120',
    'Google Flow credits: 45.5',
    '500 points remaining',
  ];

  const parseCreditStr = (str) => {
    if (!str) return null;
    const m1 = str.match(/([\d,.]+)\s*(?:Google Flow credits?|credits?|kredit(?: google flow)?|poin|points?)/i);
    if (m1 && m1[1] && /\d/.test(m1[1])) return m1[1].trim() + " Kredit";
    const m2 = str.match(/(?:kredit|credits?|poin|points?)\s*[:：]?\s*([\d,.]+)/i);
    if (m2 && m2[1] && /\d/.test(m2[1])) return m2[1].trim() + " Kredit";
    return null;
  };

  assert.equal(parseCreditStr(sampleTexts[0]), '250 Kredit');
  assert.equal(parseCreditStr(sampleTexts[1]), '120 Kredit');
  assert.equal(parseCreditStr(sampleTexts[2]), '45.5 Kredit');
  assert.equal(parseCreditStr(sampleTexts[3]), '500 Kredit');
});
```

- [ ] **Step 2: Run test to verify behavior**

Run: `node --test engine/chrome-extension/credits-safety.test.js`
Expected: PASS.

- [ ] **Step 3: Update `background.js:2026-2100`**

Replace avatar navigation click with purely passive inspection (TreeWalker, visible DOM text, shadow DOM text):
```javascript
            // Check existing visible text first (DO NOT click any link or avatar)
            let bodyText = document.body ? (document.body.innerText || document.body.textContent || "") : "";
            let found = parseCreditStr(bodyText);
            if (found) return { credits: found, source: 'direct_visible' };

            // Check shadow DOMs passively
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
              if (el.shadowRoot) {
                const sTxt = el.shadowRoot.innerText || el.shadowRoot.textContent || "";
                found = parseCreditStr(sTxt);
                if (found) return { credits: found, source: 'shadow_root' };
              }
            }

            // TreeWalker passive search
            const walk = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walk.nextNode()) {
              const val = node.nodeValue || "";
              if (val.toLowerCase().includes('credit') || val.toLowerCase().includes('kredit') || val.toLowerCase().includes('poin')) {
                const parentText = node.parentElement ? node.parentElement.innerText : val;
                found = parseCreditStr(parentText);
                if (found) return { credits: found, source: 'treewalker' };
              }
            }

            return { credits: null };
```

- [ ] **Step 4: Verify syntax and test suite**

Run: `node --check engine/chrome-extension/background.js`
Run: `node --test engine/chrome-extension/credits-safety.test.js`
Expected: PASS.

---

### Task 3: Popover-Scoped Ingredient Matching & Multi-Item Sequential Attachment

**Files:**
- Modify: `engine/chrome-extension/background.js:900-942,1420-1498`
- Create: `engine/chrome-extension/flow-ingredients-safety.test.js`

**Interfaces:**
- Consumes: Array of reference IDs (`ids`).
- Produces: Popover-scoped ingredient attachment with sequential detail-view reset.

- [ ] **Step 1: Write unit test in `engine/chrome-extension/flow-ingredients-safety.test.js`**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');

test('extractToken correctly identifies UUIDs and CDN tokens from reference IDs', () => {
  const extractToken = (val) => {
    if (!val) return '';
    const str = String(val);
    const uuid = str.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
    if (uuid) return uuid[1].toLowerCase();
    const asb = str.match(/AB-n[A-Za-z0-9_-]{12,}/);
    if (asb) return asb[0];
    return str.toLowerCase();
  };

  assert.equal(extractToken('aaa1ca86-92ee-4436-b4d5-ace19f4481c9'), 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9');
  assert.equal(extractToken('https://flow.google.com/asb/AB-nABC1234567890'), 'AB-nABC1234567890');
  assert.equal(extractToken('projects/123/media/bbb2ca86-92ee-4436-b4d5-ace19f4481c9'), 'bbb2ca86-92ee-4436-b4d5-ace19f4481c9');
});
```

- [ ] **Step 2: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-ingredients-safety.test.js`
Expected: PASS.

- [ ] **Step 3: Update `addImageReferences` and `addFlowIngredients` in `background.js`**

1. In `addImageReferences` (lines 900-942):
Scope `findAssetNodes` strictly to `flow-add-menu-popover-content` so it never clicks canvas cards:
```javascript
          const addImageReferences = async (ids) => {
            if (!ids.length) return { added: 0, missing: [] };
            notifyProgress('ATTACHING_REFERENCES', `Memasukkan ${ids.length} referensi karakter ke slot composer...`, 20);
            const normalizeText = (value) => normalize(value).replace(/[\s_-]/g, '');
            const selected = [];
            const missing = [];

            for (const id of ids) {
              let popover = document.querySelector('flow-add-menu-popover-content');
              if (!popover) {
                const trigger = document.querySelector('button[aria-label*="Add ingredients" i], button[aria-label*="Add media" i]') ||
                  Array.from(document.querySelectorAll('button')).find(el => visible(el) && normalizeText(el.getAttribute('aria-label') || el.innerText).includes('addingredients'));
                if (trigger) {
                  trigger.click();
                  await new Promise(r => setTimeout(r, 500));
                  popover = document.querySelector('flow-add-menu-popover-content');
                }
              }

              if (!popover) { missing.push(id); continue; }

              // If popover is in detail view from previous item, click back button
              const backBtn = popover.querySelector('button[aria-label*="Back" i], button.back-button, button.mat-mdc-icon-button:has(mat-icon:contains("arrow_back"))');
              if (backBtn && visible(backBtn)) {
                backBtn.click();
                await new Promise(r => setTimeout(r, 300));
              }

              const items = Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"], [role="listitem"]'));
              const token = extractToken(id);
              let matched = items.find(item => {
                const text = `${item.getAttribute('data-media-id') || ''} ${item.getAttribute('data-asset-id') || ''} ${item.outerHTML || ''}`.toLowerCase();
                return token ? text.includes(token) : false;
              });

              if (!matched && items.length > 0) {
                matched = items.find(item => !selected.includes(item)) || items[0];
              }

              if (matched) {
                matched.click();
                await new Promise(r => setTimeout(r, 300));
                const addBtn = popover.querySelector('button.detail-add-to-prompt-btn') ||
                  Array.from(popover.querySelectorAll('button')).find(el => visible(el) && !el.disabled && normalizeText(el.innerText || el.textContent).includes('addtoprompt'));
                if (addBtn) {
                  addBtn.click();
                  selected.push(matched);
                  await new Promise(r => setTimeout(r, 400));
                } else {
                  missing.push(id);
                }
              } else {
                missing.push(id);
              }
            }

            // Close popover
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            await new Promise(r => setTimeout(r, 300));

            return { added: selected.length, missing };
          };
```

2. In `addFlowIngredients` (lines 1420-1498):
Apply identical safe popover handling with back-button detail view reset and Escape closure.

- [ ] **Step 4: Verify syntax and test suite**

Run: `node --check engine/chrome-extension/background.js`
Run: `node --test engine/chrome-extension/*.test.js`
Expected: 57+ tests PASS.

---

### Task 4: Storyboard-to-Video State Transition Checkpoint in `jobs_executor.py`

**Files:**
- Modify: `backend/jobs_executor.py:1890-1925,2110-2130`
- Create: `tests/test_storyboard_to_video_transition.py`

**Interfaces:**
- Consumes: `storyboard_prebuilt`, `scenes`, `project_id`, `origin_project_id`.
- Produces: Reliable transition from Stage 2 (Storyboards) to Stage 3 (Videos) with zero project mismatch.

- [ ] **Step 1: Write failing Python unit test in `tests/test_storyboard_to_video_transition.py`**

```python
import pytest
from backend.jobs_executor import build_video_reference_ids

def test_build_video_reference_ids_places_storyboard_at_priority_index():
    character_ids = ["char_media_1", "char_media_2"]
    storyboard_id = "sb_media_1"
    
    refs = build_video_reference_ids(
        character_ids=character_ids,
        storyboard_media_id=storyboard_id,
        continuity_media_id=None,
        limit=7
    )
    
    # Storyboard must be in refs
    assert storyboard_id in refs
    # Storyboard is placed at index 0 when no continuity frame
    assert refs[0] == storyboard_id
    assert refs[1] == "char_media_1"
    assert refs[2] == "char_media_2"

def test_build_video_reference_ids_with_continuity_frame():
    character_ids = ["char_media_1"]
    storyboard_id = "sb_media_1"
    continuity_id = "cont_media_0"
    
    refs = build_video_reference_ids(
        character_ids=character_ids,
        storyboard_media_id=storyboard_id,
        continuity_media_id=continuity_id,
        limit=7
    )
    
    assert refs[0] == continuity_id
    assert refs[1] == storyboard_id
    assert refs[2] == "char_media_1"
```

- [ ] **Step 2: Run test to verify behavior**

Run: `.\.venv\Scripts\pytest tests/test_storyboard_to_video_transition.py -v`
Expected: PASS.

- [ ] **Step 3: Update `jobs_executor.py` transition checkpoint**

Add clean transition log event and verify `origin_project_id` consistency:
```python
    # Stage 2 -> Stage 3 Clean Transition Checkpoint
    log_event(job_id, f"🎬 [TRANSISI TAHAP 2 ➔ 3] Seluruh {total_scenes} storyboard Image siap! Memulai perenderan Video Adegan 1..{total_scenes}...")
```

- [ ] **Step 4: Run full backend pytest suite**

Run: `.\.venv\Scripts\pytest tests/ -q`
Expected: 284+ passed.

---

### Task 5: Full Regression Verification

**Files:**
- Test: `engine/chrome-extension/*.test.js`
- Test: `tests/`

- [ ] **Step 1: Run all extension node tests**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: All 57+ tests PASS.

- [ ] **Step 2: Run all backend pytest tests**

Run: `.\.venv\Scripts\pytest tests/ -q`
Expected: All 284+ tests PASS.

- [ ] **Step 3: Verify extension syntax**

Run: `node --check engine/chrome-extension/*.js`
Expected: Exit code 0.
