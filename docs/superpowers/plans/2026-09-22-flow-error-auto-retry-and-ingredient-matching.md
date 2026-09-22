# Google Flow Error Auto-Retry, Trusted DOM Clicks, and Resilient Ingredient Matching Plan

**Status:** Complete  
**Date:** 2026-09-22  
**Tech Stack:** Chrome Extension MV3, CDP (`chrome.debugger`), FastAPI, pytest, Node.js `--test`

---

### Task 1: Hardware-Level Trusted Clicks via `chrome.debugger`
- [x] Add `debugger` permission in `manifest.json`.
- [x] Implement `handleNativeClick(targetTabId, x, y)` in `background.js` using `Input.dispatchMouseEvent` (`mousePressed`, `mouseReleased`) and `Input.dispatchKeyEvent` (`Enter`).
- [x] Integrate coordinate extraction and native click dispatch into `generateImageViaAuthenticatedFlowUi` and `generateVideoViaAuthenticatedFlowUi`.

### Task 2: ProseMirror `DataTransfer` Paste Injection
- [x] Implement synthetic `ClipboardEvent('paste')` with `DataTransfer` plain-text payload in image/video fallbacks.
- [x] Dispatch composed `beforeinput`, `input`, and `change` events across component boundaries.

### Task 3: Direct Error Tile Detection & Auto-Retry
- [x] Add direct retry button detection (`button[aria-label*="Retry" i]`, `flow-error-tile button`, `refresh` icon) in image/video polling loops.
- [x] Implement automated click with +60s/+90s deadline extension.

### Task 4: Adaptive Ingredient Matching & Non-Blocking Video Execution
- [x] Implement token extraction (UUID, ASB hash) in `addFlowIngredients`.
- [x] Support non-blocking video generation as long as the primary storyboard frame reference is attached (`added > 0`).

### Task 5: Verification & Testing
- [x] Run Node.js Chrome extension test suite (58 passed).
- [x] Run Python pytest test suite (283 passed).
- [x] Confirm on live Google Flow canvas.
