# Google Flow Extension Modularization and Structured Logging Architecture

## Goal

Refactor the Sinematica Google Flow Chrome Extension from a monolithic background service worker into focused, single-responsibility modules. Implement a comprehensive multi-channel structured logging engine that provides observability across the Chrome Extension runtime, the browser Side Panel, and the Sinematica Backend dashboard terminal. Add automated project lifecycle management including auto-creation capabilities.

## High-Level Architecture

The automation subsystem separates concerns across distinct modules running inside the Chrome Extension MV3 runtime (service worker, injected world, and content scripts), coordinated with the Python FastAPI backend via WebSockets.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Sinematica Backend (FastAPI)                    │
│   - BridgeManager / Fleet Pool                                         │
│   - Execution Terminal WebSocket Broadcaster                           │
│   - Persistent Log Writer (data/logs/flow_fleet_YYYY-MM-DD.log)        │
└──────────────────────────────────▲─────────────────────────────────────┘
                                   │ WebSocket (ws://127.0.0.1:8888/ws/agent)
┌──────────────────────────────────▼─────────────────────────────────────┐
│                   Chrome Extension (background.js)                     │
│                Orchestrator & WebSocket Message Router                 │
├─────────────────┬──────────────────┬─────────────────┬─────────────────┤
│ flow-logger.js  │ flow-project.js  │ flow-auth.js    │ flow-tab.js     │
│ (Multi-Channel) │ (Project Mgmt)   │ (OAuth / Session│ (Tab Lifecycle) │
├─────────────────┼──────────────────┼─────────────────┼─────────────────┤
│ flow-recaptcha  │ flow-api-client  │ flow-watcher.js │ media-capture   │
│ (Enterprise)    │ (Native Proxy)   │ (DOM & Poller)  │ (Streaming MP4) │
├─────────────────┴──────────────────┴─────────────────┴─────────────────┤
│                     Flow Composer DOM Automation                       │
│ ┌───────────────────────┬────────────────────────────────────────────┐ │
│ │ flow-composer-editor  │ Input text, React event dispatch           │ │
│ │ flow-composer-config  │ Mode, aspect ratio, duration, output count │ │
│ │ flow-composer-ingred  │ Ingredients modal, asset picker, attach    │ │
│ └───────────────────────┴────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Module Specifications

### 1. Centralized Structured Logger (`flow-logger.js`)

Provides unified logging across all extension components with structured data fields and multi-channel distribution.

#### Data Schema
Every log entry adheres to the following JSON structure:
```json
{
  "timestamp": "2026-09-22T12:34:56.789Z",
  "level": "INFO",
  "tag": "DOM:EDITOR",
  "message": "Prompt injected and verified in composer editor",
  "instance_id": "profile-a1b2c3",
  "project_id": "aaa1ca86-92ee-4436-b4d5-ace19f4481c9",
  "meta": {
    "prompt_length": 142,
    "char_count_verified": true
  }
}
```

#### Supported Tags & Log Levels
* `[PROJECT]` — Project URL parsing, active ID detection, and project creation status.
* `[AUTH]` — OAuth token sniffing, session cookie status, token expiry, and refresh notifications.
* `[CAPTCHA]` — reCAPTCHA Enterprise execution, action name, solve duration, and error codes.
* `[DOM:EDITOR]` — Focus actions, text injection via `insertText`, React synthetic event dispatch, and content verification.
* `[DOM:CONFIG]` — Mode toggles (Image/Video), aspect ratio selection (9:16, 16:9), duration (4s–10s), and single output (`x1`).
* `[DOM:INGREDIENTS]` — Modal triggers, asset searches by media UUID, tile selections, and attachment confirmations.
* `[TRIGGER]` — Generate button validation (`Start generation`), button state checks, and click dispatches.
* `[WATCHER]` — DOM image observer events, new thumbnail detections, and video poll status percentages.
* `[API:PROXY]` — HTTP requests sent to `aisandbox-pa.googleapis.com`, response status codes, and timing.
* `[DOWNLOAD]` — Signed URL resolution, stream initiation, chunk transmissions, and completion checks.
* `[WS:BRIDGE]` — WebSocket connection lifecycle, heartbeats, and message routing.

#### Output Channels
1. **Browser DevTools Console**: Formatted visual output with color-coded category badges.
2. **Side Panel Live View**: Real-time log list rendered inside `sidepanel.html` with category filters and search.
3. **In-Memory Ring Buffer**: Stores the last 200 log entries in memory and persists the latest 50 to `chrome.storage.local`.
4. **Backend WebSocket Stream**: Sends `{ type: "agent_log", data: logEntry }` to the FastAPI server for central collection and terminal viewing.

---

### 2. Project Lifecycle Manager (`flow-project.js`)

Manages Google Flow project discovery, validation, navigation, and automated creation.

#### Interfaces & Responsibilities
* `detectProjectId(tabs: Tab[]) -> string | null`: Extracts the UUID from active or background Flow URLs matching `https://flow.google.com/project/[0-9a-f-]{36}`.
* `ensureActiveProject(tabId: number, preferredProjectId?: string) -> Promise<string>`: Validates that the active tab is positioned on a valid project composer root (`/project/<id>`). If the tab is on an asset edit URL (`/project/<id>/edit/<asset_id>`), navigates the tab back to the project root.
* `createProject(tabId: number) -> Promise<string>`: Automates project creation when no existing project is available:
  1. Navigates to `https://flow.google.com/`.
  2. Clicks the "New Project" / "Create Project" button in the Flow UI.
  3. Waits for navigation to `https://flow.google.com/project/<new_uuid>`.
  4. Returns the newly created project UUID and persists it in storage.

---

### 3. Composer DOM Automation Modules

Separates the large DOM scripts previously embedded in `background.js` into modular scripts executed in the page's `MAIN` world.

#### A. Editor Automation (`flow-composer-editor.js`)
* `focusAndClearEditor(doc: Document) -> boolean`: Focuses the `[contenteditable="true"]` element and clears stale content.
* `injectPromptText(doc: Document, text: string) -> Promise<boolean>`:
  * Uses `document.execCommand('selectAll', false)` followed by `document.execCommand('insertText', false, text)`.
  * Emits standard `beforeinput` and `input` events with `inputType: 'insertText'` to synchronize React internal state.
  * Verifies that the editor's inner text matches the requested prompt.
* `waitForEditorReady(doc: Document, timeoutMs?: number) -> Promise<boolean>`: Polls until the editor is enabled and the text is stabilized.

#### B. Configuration Automation (`flow-composer-config.js`)
* `openSettingsPanel(doc: Document) -> Promise<boolean>`: Clicks the settings trigger button (`button[aria-label="Settings trigger"]`) if the settings panel is not open.
* `applyGenerationMode(doc: Document, mode: 'image' | 'video') -> Promise<boolean>`: Selects the target mode toggle and confirms the selection state.
* `applyAspectRatio(doc: Document, ratio: string) -> Promise<boolean>`: Maps API aspect ratio enums (`VIDEO_ASPECT_RATIO_PORTRAIT`, `IMAGE_ASPECT_RATIO_LANDSCAPE`, etc.) to Flow UI labels (`9:16`, `16:9`, `4:3`, `3:4`, `1:1`) and clicks the corresponding control.
* `applyDuration(doc: Document, durationSeconds: number) -> Promise<boolean>`: Clicks the matching duration button (`4s`, `6s`, `8s`, `10s`).
* `applySingleOutput(doc: Document) -> Promise<boolean>`: Enforces the `x1` single generation setting.
* `closeSettingsPanel(doc: Document) -> Promise<void>`: Sends an `Escape` key event to close the configuration overlay.

#### C. Ingredients Modal Automation (`flow-composer-ingredients.js`)
* `openIngredientsPicker(doc: Document) -> Promise<boolean>`: Clicks the "Add ingredients" trigger button.
* `findAssetByMediaId(doc: Document, mediaId: string) -> Element | null`: Scans DOM attributes (`data-media-id`, `data-asset-id`, serialized tile HTML) for the exact media UUID.
* `searchAndSelectAsset(doc: Document, mediaId: string) -> Promise<boolean>`: Uses the asset search filter if the tile is not immediately visible, selects the matching tile, and clicks "Add to prompt".
* `attachIngredientsList(doc: Document, mediaIds: string[]) -> Promise<{ added: number, missing: string[] }>`: Loops through the requested reference IDs, reopening the picker per asset, and validates that all references are attached.

---

### 4. Watcher & Observer (`flow-watcher.js`)

Monitors generation progress and detects completion artifacts.

#### Capabilities
* `observeNewImage(doc: Document, initialImages: Set<string>, timeoutMs: number) -> Promise<string>`:
  * Watches for newly added `<img>` elements whose source matches trusted Google Flow CDN hosts (`flow-content.google`, `googleusercontent.com`, `storage.googleapis.com`, `gstatic.com`).
  * Resolves with the image URL when available.
* `pollVideoGeneration(bridge, mediaId: string, projectId: string, onProgress: (pct: number) => void) -> Promise<VideoResult>`:
  * Executes periodic status checks with incremental percentage calculations.
  * Emits progress events to the logger and WebSocket bridge.

---

### 5. API Client & reCAPTCHA Handler (`flow-api-client.js` & `flow-recaptcha.js`)

* `flow-recaptcha.js`:
  * Detects active enterprise site keys from `window.___grecaptcha_cfg`.
  * Executes `window.grecaptcha.enterprise.execute(siteKey, { action })` with configured action names (`IMAGE_GENERATION`, `VIDEO_GENERATION`).
  * Implements bounded retry logic for transient solver failures.
* `flow-api-client.js`:
  * Formats outgoing payloads with `clientContext`, `projectId`, and `recaptchaContext`.
  * Injects active OAuth Bearer tokens into request headers.
  * Handles worker fetch fallback for CORS-isolated endpoints.

---

### 6. Background Service Worker (`background.js`)

Acts as a clean coordinator:
* Manages WebSocket connection lifecycle (`connectWebSocket`, `reconnect`).
* Routes incoming messages (`api_request`, `trpc_request`, `download_request`, `ping`) directly to their respective domain modules.
* Dispatches registration states and heartbeat alarms.

---

## Backend & UI Logging Integration

### Backend Stream Processing (`backend/bridge_manager.py` & `backend/routers/status.py`)
* Receives `agent_log` WebSocket messages from connected extension instances.
* Writes log lines to `data/logs/flow_fleet_YYYY-MM-DD.log`.
* Broadcasts log records to connected frontend web dashboard clients for live viewing in the **Execution Terminal** tab.

### Frontend Terminal UI
* Renders real-time fleet events with tag-specific color coding.
* Offers filtering by Chrome Profile instance and log level (`INFO`, `WARN`, `ERROR`).

---

## Testing & Verification Plan

1. **Unit Tests (Node.js)**:
   * `engine/chrome-extension/flow-logger.test.js`: Validates formatting, ring buffer trimming, tag filtering, and serialization.
   * `engine/chrome-extension/flow-project.test.js`: Tests project UUID extraction, URL pattern matching, and fallback handling.
   * `engine/chrome-extension/flow-composer-editor.test.js`: Tests input injection, React synthetic event simulation, and text validation.
   * `engine/chrome-extension/flow-composer-config.test.js`: Tests aspect ratio, duration, and mode selection mappings.
   * `engine/chrome-extension/flow-composer-ingredients.test.js`: Tests asset node resolution and multi-item reference attachment.
2. **Backend Unit Tests (Python)**:
   * `tests/test_fleet_logger.py`: Verifies log ingestion via WebSocket, file persistence, and terminal broadcast.
3. **Integration Verification**:
   * Run full test suite (`python -m unittest discover` and `node --test`).
   * Verify extension syntax with `node --check`.
   * Perform smoke test in browser with active Chrome profiles.

---

## Non-Goals

* Modification of video encoding or FFmpeg concatenation logic in `film_stitcher.py`.
* Third-party captcha solver integration; reCAPTCHA remains solved directly in the authenticated browser context.
