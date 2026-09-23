# Fix Google Flow Submit Button Trigger, Mode Verification, and Asset URL Validation

## Problem Summary
1. **Submit Button Trigger Failure in `flow-executor.js` & `background.js`**:
   - `findGenerateButton` / `findStartButton` fails to match the circular right arrow submit button when it contains SVG icons or alternative aria-labels (`Start`, `Submit`, `Send`, `Mulai`, `arrow_forward`, `arrow_right`).
   - If the button is not found within the wait loop, `flow-executor.js` quietly bypasses click execution without throwing or falling back, leaving the prompt filled and the submit button unclicked.
   - Dispatch of Angular events during prompt typing must include comprehensive input events, change events, and direct click dispatch with `window.__sinematicaAllowNativeInput = true` and `Enter` key execution on the ProseMirror editor.

2. **Google Static Bar UI Icons False Positive (`ssl.gstatic.com/gb/...`)**:
   - `FlowWatcher.isTrustedMediaUrl` and `imgIsUsable` allowed `.gstatic.com` domains.
   - `ssl.gstatic.com/gb/images/ring/...` (Google Bar avatar icon) was mistakenly captured as the generated character sheet and saved into cache.
   - Generated images and videos are hosted on `flow-content.google`, `*.googleusercontent.com`, `storage.googleapis.com`, `flow.google.com`, or blob/data URLs. Static resources from `gstatic.com` must be strictly excluded.

3. **`waitForImageGenerationDomDone` Media URL Filtering**:
   - Image tile polling must validate that detected images match genuine Google Flow generated media URLs rather than UI icons or account avatars.

---

## Proposed Changes

### 1. `engine/chrome-extension/flow-watcher.js` & `flow-watcher.test.js`
- Update `isTrustedMediaUrl` to strictly exclude any `gstatic.com` URLs (such as `ssl.gstatic.com/gb/images/ring/...`, `gstatic.com/images/icons/...`) and only trust genuine generated media hosts (`flow-content.google`, `*.googleusercontent.com`, `storage.googleapis.com`, `flow.google.com`, `blob:`, `data:`).

### 2. `engine/chrome-extension/flow-executor.js`
- Enhance `findGenerateButton()` in both `triggerImageGeneration()` and `triggerVideoRender()`:
  - Match direct selector: `flow-generate-icon-button button, button.generate-icon-button, button[aria-label*="Start" i], button[aria-label*="Generate" i], button[aria-label*="Submit" i], button[aria-label*="Send" i], button[aria-label*="Mulai" i], button[aria-label*="Buat" i], button[aria-label*="Hasilkan" i]`.
  - Check prompt-box buttons with broad regex matching `/arrow|start|generate|submit|send|buat|mulai|hasilkan/i` and elements containing `mat-icon` or `svg`.
  - Add fallback selecting the last visible button inside `flow-prompt-box` that is not an upload/sidebar/settings button.
- In `triggerImageGeneration()` and `triggerVideoRender()`:
  - Ensure `window.__sinematicaAllowNativeInput = true` before dispatching clicks.
  - Dispatch full event chain: `pointerdown`, `mousedown`, `pointerup`, `mouseup`, `click`, and `button.click()`.
  - Dispatch `Enter` key on the `.ProseMirror` editor as secondary execution guarantee.
  - If no button is found after timeout, throw an explicit actionable error.
- In `waitForImageGenerationDomDone()`:
  - Filter `loadedTiles` using `isGeneratedMediaUrl()` to ignore any static UI icons.

### 3. `engine/chrome-extension/background.js`
- Enhance `imgIsUsable()`:
  - Exclude `.gstatic.com`, `/gb/`, `/ring/`, `/icons/`, `/avatar/`, and UI assets.
  - Validate against trusted media hosts.
- Align `findStartButton()` in `generateImageViaAuthenticatedFlowUi` and `triggerAuthenticatedVideoRender` to match `flow-executor.js`.

### 4. Automated Tests
- Update `flow-watcher.test.js` to verify exclusion of `gstatic.com` avatar/UI icons.
- Update `flow-generate-button-safety.test.js` to test all variants of submit buttons (SVG arrow, aria-label="Start", Send, Submit, last button in promptBox).
- Update `flow-image-generation.test.js` to verify `waitForImageGenerationDomDone` ignores `gstatic.com` icons.
- Run `node --test engine/chrome-extension/*.test.js` and `pytest tests/`.
