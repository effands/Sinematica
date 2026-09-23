# Interaction Blocking Overhaul & Storyboard Ingredient Attachment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide 100% airtight user interaction blocking during Flow automation, guarantee complete unblocking/cleanup when tasks finish or disconnect, and ensure storyboard images and character references are reliably attached into Google Flow's prompt composer as Ingredients.

**Architecture:**
1. Global capture-phase event interceptors on `window` and `document` combined with a top-level `#sinematica-interaction-blocker` overlay (`z-index: 2147483646`) to block clicks, typing, and scrolling across all elements including Angular CDK popovers.
2. Robust `unblockUserInteraction()` cleanup lifecycle wired into task `finally` blocks, WebSocket disconnects (`onclose`, `onerror`), extension lifecycle events, and safety timeouts.
3. Multi-strategy `findAddIngredientTrigger` and asset item matching in `background.js` to ensure the `+` button in `flow-prompt-box` is always detected and storyboard images + character sheets are attached to the prompt.

**Tech Stack:** JavaScript (Chrome MV3 Extension, Web APIs, DOM Mutation/Event Simulation), Python 3.14 (FastAPI, pytest, omniflash).

**Spec:** `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md`

## Global Constraints

- User interaction must be completely blocked (no clicks, scrolls, or keystrokes) while automation runs.
- When automation ends (success, failure, cancellation, or disconnect), all blockers and fake cursors must be completely removed immediately.
- Storyboard image and character reference IDs must be attached to the prompt composer as Ingredients.
- 100% test pass rate across Node.js (`node --test engine/chrome-extension/*.test.js`) and pytest (`pytest tests/`).

---

### Task 1: Implement Airtight Interaction Blocker and Guaranteed Unblocker

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js:90-220,1800-1920`
- Modify: `engine/chrome-extension/background.js:1450-1600,2050-2150,2700-2850`
- Create: `engine/chrome-extension/flow-interaction-blocker.test.js`

**Interfaces:**
- Consumes: Window/Document DOM events and extension task lifecycle.
- Produces: `blockUserInteraction()`, `unblockUserInteraction()`, and lifecycle hooks that guarantee clean unblocking.

- [ ] **Step 1: Write unit tests for blocker and unblocker in `flow-interaction-blocker.test.js`**
- [ ] **Step 2: Run test to verify initial status**
- [ ] **Step 3: Implement `blockUserInteraction()` and `unblockUserInteraction()` in `flow-executor.js` and `background.js`**
- [ ] **Step 4: Wire unblocker into `finally` blocks and WebSocket disconnect handlers**
- [ ] **Step 5: Run tests to verify passing**

---

### Task 2: Implement Multi-Strategy Add Ingredient Trigger & Attachment in `background.js`

**Files:**
- Modify: `engine/chrome-extension/background.js:975-1085,1675-1815`
- Test: `engine/chrome-extension/flow-video-ingredients.test.js`

**Interfaces:**
- Consumes: Reference media IDs (storyboard image, character sheets).
- Produces: Reliable attachment of all ingredient references into `flow-prompt-box`.

- [ ] **Step 1: Write unit tests in `flow-video-ingredients.test.js` for `findAddIngredientTrigger` and multi-item attachment**
- [ ] **Step 2: Update `addFlowIngredients` and trigger discovery in `background.js`**
- [ ] **Step 3: Run Node.js tests to verify**

---

### Task 3: Comprehensive Test Suite Verification

**Files:**
- Test: `engine/chrome-extension/*.test.js`
- Test: `tests/`

- [ ] **Step 1: Run all Node.js Chrome extension unit tests**
- [ ] **Step 2: Run all Pytest backend test suites**

---
