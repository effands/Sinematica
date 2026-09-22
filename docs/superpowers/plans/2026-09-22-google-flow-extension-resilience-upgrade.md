# Google Flow Extension Resilience Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Sinematica Chrome Extension with Google Flow Boq batchexecute RPC parsing, MAIN-world network interception, synthetic `DataTransfer` multi-image pasting, and robust Angular Material `flow-toggles` automation from the reference extension while keeping the existing Sinematica WebSocket backend workflow, fleet logger, and sidepanel architecture 100% intact.

**Architecture:** 
- `flow-network-parser.js`: Parses Google Boq `batchexecute` envelopes (`wrb.fr`) and standard REST APIs into unified high-level status events (`IMAGE_READY`, `VIDEO_READY`, `PROJECT_CREATED`, `REFERENCE_IMAGE_UPLOADED`, `ERROR`, `PROFILE_UPDATED`), and builds Boq RPC payloads.
- `flow-interceptor.js`: Runs in `world: "MAIN"`, intercepts `window.fetch` and `XMLHttpRequest` non-intrusively, extracts `window.WIZ_global_data` session tokens (`FdrFJe`, `SNlM0e`, `cfb2h`), supports direct in-page Boq RPC dispatch, and bridges events to content script via `window.postMessage`.
- `flow-executor.js`: Executes UI tasks via synthetic `ClipboardEvent` / `DataTransfer` file paste, ProseMirror `beforeinput`/`input` simulation, Angular Material `flow-toggles` selection (Mode, Aspect Ratio, Count, Duration, Model), visual cursor animation, failed tile auto-retry, and HTML5 video last-frame extraction.
- `content.js`: Bridges main-world RPC events to the background service worker and instantiates the task executor.
- `background.js`: Maintains the WebSocket bridge (`ws://127.0.0.1:8888/ws/agent`), routes `api_request`, `trpc_request`, and `download_request`, emits multi-channel structured logs via `FlowLogger`, and delegates automation tasks to the upgraded executor.

**Tech Stack:** Chrome Extension Manifest V3 (MV3), JavaScript (ES2022/CommonJS UMD), Node.js native test runner (`node:test`, `node:assert/strict`), HTML5 Canvas/Video API.

**Spec:** `docs/superpowers/specs/2026-09-22-flow-video-generation-and-end-to-end-architecture.md` and reference implementation in `ziqva-google-flow-extension`.

## Global Constraints
- Strictly preserve the existing Sinematica workflow: WebSocket connection to `ws://127.0.0.1:8888/ws/agent`, backend request formats (`api_request`, `trpc_request`, `download_request`), `FlowLogger` multi-channel structured logging, and side panel UI.
- All new extension JavaScript files must support UMD export (`module.exports` for Node.js unit tests, `window` / `globalThis` for browser MAIN and isolated worlds).
- Zero external runtime npm dependencies for the extension.

---

### Task 1: Boq Batchexecute & Network Response Parser (`flow-network-parser.js`)

**Files:**
- Create: `engine/chrome-extension/flow-network-parser.js`
- Test: `engine/chrome-extension/flow-network-parser.test.js`

**Interfaces:**
- Produces: `FlowNetworkParser` with methods:
  - `decodeBoqResponse(rawText: string): Array<{ rpcId: string, data: any, raw: any }>`
  - `parseGoogleFlowResponse(url: string, statusCode: number, rawResponseText: string|object, requestInfo?: object): object|null`
  - `extractProjectIdFromUrl(url: string): string|null`
  - `buildBoqUploadImagePayload(params: object): Array<any>`
  - `buildBoqImagePayload(params: object): Array<any>`
  - `buildBoqVideoPayload(params: object): Array<any>`
  - `buildBoqCheckStatusPayload(operationNames: string|string[]): Array<any>`
  - `parseBoqUploadImageResponse(rawResponse: any, defaultName?: string, fallbackMediaId?: string, fallbackProjectId?: string): object`
  - `parseBoqVideoGenResponse(rawResponse: any, prompt?: string): Array<object>`

- [ ] **Step 1: Write the failing test**

Create `engine/chrome-extension/flow-network-parser.test.js`:
```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowNetworkParser } = require('./flow-network-parser.js');

test('FlowNetworkParser decodes chunked Boq batchexecute response envelopes', () => {
  const mockBoqChunked = `)]}'\n124\n[["wrb.fr","ogiZ0b","[[null,[null,\\"flowMedia/img_123\\",null,\\"https://flow-content.google/image/test.png\\"]]]",null,null,null,"generic"]]`;
  const decoded = FlowNetworkParser.decodeBoqResponse(mockBoqChunked);
  assert.equal(decoded.length, 1);
  assert.equal(decoded[0].rpcId, 'ogiZ0b');
  assert.ok(Array.isArray(decoded[0].data));
});

test('FlowNetworkParser translates Boq image generation to IMAGE_READY event', () => {
  const mockBoq = `)]}'\n[["wrb.fr","ogiZ0b","[[null,[null,\\"flowMedia/img_abc\\",null,\\"https://flow-content.google/image/test.png\\"]]]",null,null,null,"generic"]]`;
  const event = FlowNetworkParser.parseGoogleFlowResponse('https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute', 200, mockBoq);
  assert.ok(event);
  assert.equal(event.type, 'IMAGE_READY');
  assert.equal(event.rpcId, 'ogiZ0b');
  assert.equal(event.imageUrls[0], 'https://flow-content.google/image/test.png');
});

test('FlowNetworkParser translates Boq video generation to VIDEO_READY event', () => {
  const mockBoq = `)]}'\n[["wrb.fr","eb1hJf","[[null,[null,\\"operations/op_999\\",null,\\"https://flow-content.google/video/test.mp4\\"]]]",null,null,null,"generic"]]`;
  const event = FlowNetworkParser.parseGoogleFlowResponse('https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute', 200, mockBoq);
  assert.ok(event);
  assert.equal(event.type, 'VIDEO_READY');
  assert.equal(event.videoUrls[0], 'https://flow-content.google/video/test.mp4');
});

test('FlowNetworkParser builds valid Boq video and image payloads', () => {
  const imgPayload = FlowNetworkParser.buildBoqImagePayload({ prompt: 'cinematic product', aspectRatio: 2, count: 1 });
  assert.ok(Array.isArray(imgPayload));
  assert.equal(imgPayload[1].length, 1);

  const vidPayload = FlowNetworkParser.buildBoqVideoPayload({ prompt: '360 rotation', aspectRatio: 1, count: 1, startImageMediaId: 'asset-123' });
  assert.ok(Array.isArray(vidPayload));
  assert.equal(vidPayload[0].length, 1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/flow-network-parser.test.js`
Expected: FAIL with `Cannot find module './flow-network-parser.js'`

- [ ] **Step 3: Implement `flow-network-parser.js`**

Create `engine/chrome-extension/flow-network-parser.js` with full Boq decoding, recursive payload scanning, REST endpoint matching, and payload builders.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-network-parser.test.js`
Expected: PASS (all 4 tests pass)

---

### Task 2: Main-World Network Interceptor & Direct RPC Bridge (`flow-interceptor.js`)

**Files:**
- Create: `engine/chrome-extension/flow-interceptor.js`
- Test: `engine/chrome-extension/flow-interceptor.test.js`

**Interfaces:**
- Consumes: `FlowNetworkParser` (from Task 1)
- Produces:
  - Non-intrusive monkey-patching of `window.fetch` and `XMLHttpRequest`.
  - Extraction of `window.WIZ_global_data` (`FdrFJe`, `SNlM0e`, `cfb2h`).
  - `window.postMessage` bridge emitting `{ source: 'FLOW_INTERCEPTOR', event, timestamp }`.
  - Main-world direct RPC dispatch methods (`uploadImageDirect`, `generateImageDirect`, `generateVideoDirect`, `getMediaDownloadUrlDirect`, `executeBatchexecuteRpc`).

- [ ] **Step 1: Write the failing test**

Create `engine/chrome-extension/flow-interceptor.test.js` mocking browser environment (`window`, `fetch`, `postMessage`):
```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowNetworkParser } = require('./flow-network-parser.js');

test('FlowInterceptor extracts WIZ_global_data session parameters correctly', () => {
  const mockWiz = {
    FdrFJe: 'mock_sid_123',
    SNlM0e: 'mock_at_token',
    cfb2h: 'boq_labs-ai-sandbox-frontend_20260903.13_p0',
  };
  globalThis.window = { WIZ_global_data: mockWiz, location: { pathname: '/fx/tools/flow' } };
  globalThis.document = { querySelectorAll: () => [] };

  const { getWizSessionData } = require('./flow-interceptor.js');
  const session = getWizSessionData();
  assert.equal(session.fsid, 'mock_sid_123');
  assert.equal(session.at, 'mock_at_token');
  assert.equal(session.bl, 'boq_labs-ai-sandbox-frontend_20260903.13_p0');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/flow-interceptor.test.js`
Expected: FAIL with `Cannot find module './flow-interceptor.js'`

- [ ] **Step 3: Implement `flow-interceptor.js`**

Implement `flow-interceptor.js` with non-blocking fetch/XHR listeners, `getWizSessionData`, `executeBatchexecuteRpc`, and `postMessage` event routing.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-interceptor.test.js`
Expected: PASS

---

### Task 3: Modular Flow Task Executor (`flow-executor.js`)

**Files:**
- Create: `engine/chrome-extension/flow-executor.js`
- Test: `engine/chrome-extension/flow-executor.test.js`

**Interfaces:**
- Produces: `FlowTaskExecutor` class with:
  - `ensureProject(): Promise<boolean>`
  - `ensureAgentOff(): Promise<boolean>`
  - `configureImageSettings(options): Promise<boolean>`
  - `configureOptimalAffiliateVideoSettings(options): Promise<boolean>`
  - `uploadMultipleImages(imagesInput, projectId, timeoutMs): Promise<Array<object>>`
  - `fillPrompt(promptText): Promise<boolean>`
  - `triggerImageGeneration(options): Promise<boolean>`
  - `triggerVideoRender(promptText): Promise<boolean>`
  - `attachFrameToStartSlot(frameData, timeoutMs): Promise<boolean>`
  - `attachGeneratedImageToPrompt(imageAsset): Promise<boolean>`
  - `extractLastFrameFromVideoUrl(videoUrl): Promise<object|null>`
  - `execute(taskPayload): Promise<object>`
  - `abort(taskId): void`
  - Helper functions: `simulateClick(el)`, `simulateInput(el, text)`, `b64toBlob(b64, type)`

- [ ] **Step 1: Write the failing test**

Create `engine/chrome-extension/flow-executor.test.js`:
```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowTaskExecutor, simulateClick, simulateInput, b64toBlob } = require('./flow-executor.js');

test('FlowTaskExecutor normalizes images input format correctly', () => {
  const executor = new FlowTaskExecutor();
  const rawList = [
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    { base64: 'abc12345', mimeType: 'image/jpeg', name: 'product.jpg' }
  ];
  const normalized = executor.normalizeImagesList(rawList);
  assert.equal(normalized.length, 2);
  assert.equal(normalized[0].mimeType, 'image/png');
  assert.equal(normalized[1].fileName, 'product.jpg');
  assert.equal(normalized[1].base64Data, 'abc12345');
});

test('b64toBlob converts base64 string to Blob', () => {
  const b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
  const blob = b64toBlob(b64, 'image/png');
  assert.ok(blob);
  assert.equal(blob.type, 'image/png');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/flow-executor.test.js`
Expected: FAIL with `Cannot find module './flow-executor.js'`

- [ ] **Step 3: Implement `flow-executor.js`**

Implement `flow-executor.js` with:
- Synthetic `DataTransfer` paste onto `.ProseMirror` and `input[type="file"]`.
- `simulateInput` with `beforeinput`, `input`, and `execCommand`.
- `flow-toggles` Angular Material selectors for mode, aspect ratio, count, and duration.
- Visual cursor animation + user interaction blocker overlay.
- Auto-retry on failed tiles.
- Video last-frame extraction using HTML5 video and canvas.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-executor.test.js`
Expected: PASS

---

### Task 4: Update Content Script (`content.js`) and Manifest (`manifest.json`)

**Files:**
- Modify: `engine/chrome-extension/manifest.json`
- Modify: `engine/chrome-extension/content.js`

**Interfaces:**
- `manifest.json`:
  - Declare `flow-network-parser.js` and `flow-interceptor.js` under `content_scripts` with `"world": "MAIN"`, `"run_at": "document_start"`.
  - Declare `flow-executor.js` and `content.js` under `content_scripts` with isolated world, `"run_at": "document_start"`.
  - Include all new scripts in `web_accessible_resources`.
- `content.js`:
  - Listens to `window.postMessage` from `flow-interceptor.js`.
  - Bridges RPC requests between isolated world and MAIN world.
  - Instantiates `FlowTaskExecutor` and handles `EXECUTE_FLOW_TASK`, `CANCEL_FLOW_TASK`, `GET_PAGE_AUTH_TOKEN`, and `GET_CAPTCHA`.

- [ ] **Step 1: Update `manifest.json`**

Configure `manifest.json` with MAIN world content scripts and web accessible resources.

- [ ] **Step 2: Update `content.js`**

Wire up `dispatchMainWorldRpc`, executor lifecycle, message listeners, and fallback script injector.

- [ ] **Step 3: Verify manifest syntax and content script loads cleanly**

Run: `node --check engine/chrome-extension/content.js`
Expected: PASS (no syntax errors)

---

### Task 5: Integrate with Background Service Worker (`background.js`)

**Files:**
- Modify: `engine/chrome-extension/background.js`

**Interfaces:**
- Consumes: `FlowNetworkParser`, `FlowTaskExecutor`, `FlowLogger`, `FlowTab`, `FlowApiClient`
- Maintains:
  - WebSocket connection to `ws://127.0.0.1:8888/ws/agent`.
  - Structured logging via `FlowLogger`.
  - Handling of `api_request`, `trpc_request`, `download_request`, `ping`/`pong`.
  - Routing of UI automation tasks to `content.js` via `EXECUTE_FLOW_TASK`.

- [ ] **Step 1: Update `background.js`**

Import `flow-network-parser.js` and `flow-executor.js` via `importScripts`, update DOM fallback routines to utilize the upgraded executor logic, and ensure all existing message handling and WebSocket protocols remain 100% operational.

- [ ] **Step 2: Verify syntax of `background.js`**

Run: `node --check engine/chrome-extension/background.js`
Expected: PASS

---

### Task 6: Comprehensive Verification & Regression Test Suite

**Files:**
- Test: `engine/chrome-extension/*.test.js`
- Test: `backend/` pytest suite

- [ ] **Step 1: Run all extension node tests**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: PASS (all tests pass)

- [ ] **Step 2: Run all backend pytest tests**

Run: `pytest tests/ backend/ -q`
Expected: PASS

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-22-google-flow-extension-resilience-upgrade.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.
