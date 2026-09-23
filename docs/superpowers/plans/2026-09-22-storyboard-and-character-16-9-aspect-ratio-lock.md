# Storyboard & Character 16:9 Landscape Aspect Ratio Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure character seeds, storyboard images, prompts, and video renders strictly respect and enforce the 16:9 landscape aspect ratio when 16:9 is selected or configured.

**Architecture:** Standardize aspect ratio handling end-to-end across backend prompt engineering (`backend/gemini_storyboard.py`), job execution & character caching (`backend/jobs_executor.py`), API router request contracts (`backend/routers/`), frontend dashboard selectors (`frontend/app.js`), and Chrome extension DOM settings automation (`engine/chrome-extension/background.js`).

**Tech Stack:** Python 3 (FastAPI, pytest), JavaScript ES2022 (Node.js test runner, Chrome MV3 Extension), HTML5/CSS3.

## Global Constraints
- Preserve all existing 283 Python unit tests and 55 Node.js extension unit tests.
- Maintain full backward compatibility for portrait (9:16) when explicitly selected.
- Ensure zero loss of character reference consistency across scene transitions.

---

### Task 1: Backend Storyboard Generator Aspect Ratio Injection & Return Guarantee

**Files:**
- Modify: `backend/gemini_storyboard.py:1890-2320`
- Test: `tests/test_storyboard_aspect_ratio.py`

**Interfaces:**
- Consumes: `generate_storyboard(..., aspect_ratio="landscape", ...)`
- Produces: `storyboard["aspect_ratio"] == "landscape"`

- [ ] **Step 1: Write test to verify aspect ratio persistence in generated storyboard**
- [ ] **Step 2: Update system prompt and return dict in `backend/gemini_storyboard.py`**
- [ ] **Step 3: Run pytest to verify passes**

---

### Task 2: Job Executor & Character Seed Aspect Ratio Lock

**Files:**
- Modify: `backend/jobs_executor.py`
- Test: `tests/test_character_aspect_lock.py`

**Interfaces:**
- Consumes: `execute_storyboard_job(..., aspect_ratio="landscape", ...)`
- Produces: Character seed requests and storyboard images dispatched with `aspect="landscape"` (16:9)

- [ ] **Step 1: Write test for character generator aspect ratio parameter**
- [ ] **Step 2: Update `backend/jobs_executor.py` to pass `aspect=aspect_ratio` dynamically**
- [ ] **Step 3: Run pytest to verify passes**

---

### Task 3: Frontend Aspect Ratio Selection & Job Dispatch Consistency

**Files:**
- Modify: `frontend/app.js`

**Interfaces:**
- Consumes: User selection from `#aspectSelect`
- Produces: Outgoing JSON payloads with explicit `aspect_ratio: "landscape"` or `"portrait"`

- [ ] **Step 1: Ensure `currentStoryboard.aspect_ratio` is updated on change and saved into jobs**
- [ ] **Step 2: Run frontend and backend regression tests**

---

### Task 4: Chrome Extension DOM Setting Selector Verification

**Files:**
- Modify: `engine/chrome-extension/background.js`

**Interfaces:**
- Consumes: `requestedRatio` / `requestedAspectRatio`
- Produces: Clicks `'16:9'` toggle in Google Flow settings popover

- [ ] **Step 1: Verify `16:9` ratio toggle matching in `background.js`**
- [ ] **Step 2: Run extension unit tests (`node --test engine/chrome-extension/*.test.js`)**

