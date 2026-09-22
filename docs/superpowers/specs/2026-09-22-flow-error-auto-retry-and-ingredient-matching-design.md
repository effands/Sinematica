# Google Flow Error Auto-Retry, Trusted DOM Clicks, and Resilient Ingredient Matching Design

**Date:** 2026-09-22  
**Status:** Approved & Implemented  
**Scope:** `engine/chrome-extension/`, `backend/jobs_executor.py`, `frontend/app.js`  
**Related Specs:** `docs/superpowers/specs/2026-09-22-google-flow-extension-trusted-dom-redesign.md`, `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md`

---

## 1. Executive Summary

During automated end-to-end video production runs in Google Flow (Omni Flash / Gemini 3.6 Flash fleet), three critical execution blockers were identified and resolved:

1. **Angular Material MDC Synthetic Click Drops (`isTrusted: false`)**: Programmatic DOM `.click()` and synthetic `MouseEvent` events on the *Start generation* button were dropped by Angular event listeners without submitting prompts.
2. **Google Flow Soft-Fail Error Cards ("Failed: We noticed some unusual activity")**: When Google Flow rate-limiting or challenge heuristics triggered a soft failure, the extension polling loop failed to identify the error card, leaving the automation stuck until a 90-second timeout.
3. **Video Ingredient Popover Token Mismatches (`FLOW_UI_INGREDIENTS_INCOMPLETE`)**: The reference ingredient picker in Google Flow uses dynamic CDN URLs (`lh3.googleusercontent.com` and `flow-content.google`) rather than plain UUIDs. When secondary character references failed exact string lookup, video generation was aborted prematurely instead of proceeding with the primary storyboard frame.

---

## 2. Architecture & Components

- **Backend (FastAPI / Jobs Executor)**:
  - `create_and_register_job()`: Synchronously registers job state before kicking off async workers to prevent 404 race conditions during frontend polling.
  - Full 3-stage pipeline lifecycle: Tahap 1 (Character Casting Sheets) -> Tahap 2 (Storyboard Scene Images) -> Tahap 3 (Video R2V Render).
- **Chrome Extension Agent (MV3)**:
  - `chrome.debugger` (`1.3` CDP protocol): Dispatches hardware-level `Input.dispatchMouseEvent` and `Input.dispatchKeyEvent` with authentic `isTrusted: true` flag.
  - `ProseMirror DataTransfer Injection`: Synthetic paste event with full `ClipboardEvent` payload.
  - `Direct Retry Finder`: Instant detection of Google Flow `<flow-error-tile>` and `button[aria-label="Retry"]` with automatic click and +60s/+90s polling deadline extension.
  - `Adaptive addFlowIngredients()`: Token extraction (UUID, ASB CDN tokens) and non-blocking fallback (`added > 0`) so video rendering proceeds with the primary storyboard frame.
- **Frontend Dashboard**:
  - Resilient polling with 3-attempt grace period and automatic fallback recovery.

---

## 3. Verification & Results

- **Test Suite Results**:
  - Node.js Unit Tests: 58 passed, 0 failed.
  - Python Pytest Suite: 283 passed, 0 failed.
- **Live Flow Canvas Confirmation**:
  - 3 Character Master Contact Sheets generated & cached.
  - 6 Scene Storyboard Images generated & cached.
  - Auto-retry triggered and verified on live Google Flow canvas.
