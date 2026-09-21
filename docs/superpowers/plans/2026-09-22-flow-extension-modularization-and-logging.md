# Google Flow Extension Modularization and Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modularize the Google Flow Chrome Extension into single-responsibility modules, build a multi-channel structured logger streaming across extension, sidepanel, and backend dashboard terminal, and add automated project lifecycle management.

**Architecture:** The monolithic background script is split into focused JavaScript modules (`flow-logger.js`, `flow-project.js`, `flow-composer-editor.js`, `flow-composer-config.js`, `flow-composer-ingredients.js`, `flow-watcher.js`, `flow-recaptcha.js`, `flow-api-client.js`). A structured logger formats and forwards events to DevTools console, Side Panel UI, and backend WebSocket for terminal broadcast and log file persistence.

**Tech Stack:** JavaScript (ES6+, Chrome Extension MV3), Node.js test runner (`node --test`), Python 3 (FastAPI, WebSockets, `unittest`).

**Spec:** `docs/superpowers/specs/2026-09-22-flow-extension-modularization-and-logging-design.md`

## Global Constraints

- Accept and preserve valid existing OAuth Bearer tokens (`ya29...`) and cookies (`SID`, `SAPISID`).
- Log lines must include timestamp, level, tag, message, instance ID, project ID, and metadata.
- DOM manipulation must respect React synthetic events (`beforeinput`, `input`) for `contenteditable`.
- All Node.js tests in `engine/chrome-extension/*.test.js` and Python tests in `tests/test_*.py` must pass.
- Preserve backward compatibility with existing WebSocket bridge contracts.

---

### Task 1: Structured Multi-Channel Logger Module

**Files:**
- Create: `engine/chrome-extension/flow-logger.js`
- Create: `engine/chrome-extension/flow-logger.test.js`

**Interfaces:**
- Produces: `FlowLogger.createLogger({ instanceId, projectId, wsSender }) -> LoggerInstance`
- Produces: `logger.debug(tag, message, meta)`
- Produces: `logger.info(tag, message, meta)`
- Produces: `logger.warn(tag, message, meta)`
- Produces: `logger.error(tag, message, meta)`
- Produces: `logger.getRecentLogs(limit) -> Array<LogEntry>`
- Produces: `logger.clearLogs()`

- [ ] **Step 1: Write failing logger tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { FlowLogger } from './flow-logger.js';

test('FlowLogger formats log entries with timestamp, tag, level and metadata', () => {
  const sent = [];
  const logger = FlowLogger.createLogger({
    instanceId: 'profile-test',
    projectId: 'proj-123',
    wsSender: (payload) => sent.push(payload),
  });

  const entry = logger.info('DOM:EDITOR', 'Editor text verified', { charCount: 42 });

  assert.equal(entry.level, 'INFO');
  assert.equal(entry.tag, 'DOM:EDITOR');
  assert.equal(entry.message, 'Editor text verified');
  assert.equal(entry.instance_id, 'profile-test');
  assert.equal(entry.project_id, 'proj-123');
  assert.equal(entry.meta.charCount, 42);
  assert.ok(entry.timestamp);

  assert.equal(sent.length, 1);
  assert.equal(sent[0].type, 'agent_log');
  assert.deepEqual(sent[0].data, entry);
});

test('FlowLogger maintains a ring buffer capped at maximum entries', () => {
  const logger = FlowLogger.createLogger({ maxEntries: 5 });
  for (let i = 1; i <= 8; i++) {
    logger.info('TEST', `Message ${i}`);
  }
  const recent = logger.getRecentLogs();
  assert.equal(recent.length, 5);
  assert.equal(recent[0].message, 'Message 4');
  assert.equal(recent[4].message, 'Message 8');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/flow-logger.test.js`
Expected: FAIL with module not found or export missing.

- [ ] **Step 3: Implement FlowLogger module**

```javascript
// engine/chrome-extension/flow-logger.js
const LOG_LEVELS = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };

class LoggerInstance {
  constructor(options = {}) {
    this.instanceId = options.instanceId || null;
    this.projectId = options.projectId || null;
    this.wsSender = typeof options.wsSender === 'function' ? options.wsSender : null;
    this.minLevel = options.minLevel || 'DEBUG';
    this.maxEntries = options.maxEntries || 200;
    this.logs = [];
    this.listeners = new Set();
  }

  setContext({ instanceId, projectId, wsSender }) {
    if (instanceId !== undefined) this.instanceId = instanceId;
    if (projectId !== undefined) this.projectId = projectId;
    if (wsSender !== undefined) this.wsSender = wsSender;
  }

  addListener(listener) {
    if (typeof listener === 'function') this.listeners.add(listener);
  }

  removeListener(listener) {
    this.listeners.delete(listener);
  }

  _log(level, tag, message, meta = {}) {
    if (LOG_LEVELS[level] < LOG_LEVELS[this.minLevel]) return null;

    const entry = {
      timestamp: new Date().toISOString(),
      level,
      tag: String(tag || 'GENERAL').toUpperCase(),
      message: String(message || ''),
      instance_id: this.instanceId,
      project_id: this.projectId,
      meta: meta && typeof meta === 'object' ? meta : {},
    };

    this.logs.push(entry);
    if (this.logs.length > this.maxEntries) {
      this.logs.shift();
    }

    // Console output with badge styling when in browser context
    if (typeof console !== 'undefined') {
      const formatted = `[${entry.timestamp.slice(11, 23)}] [${entry.tag}] ${entry.message}`;
      if (level === 'ERROR') console.error(formatted, entry.meta);
      else if (level === 'WARN') console.warn(formatted, entry.meta);
      else console.log(formatted, entry.meta);
    }

    // Forward to Side Panel listeners
    for (const listener of this.listeners) {
      try { listener(entry); } catch (_) {}
    }

    // Forward to WebSocket bridge
    if (this.wsSender) {
      try {
        this.wsSender({ type: 'agent_log', data: entry });
      } catch (_) {}
    }

    return entry;
  }

  debug(tag, message, meta) { return this._log('DEBUG', tag, message, meta); }
  info(tag, message, meta) { return this._log('INFO', tag, message, meta); }
  warn(tag, message, meta) { return this._log('WARN', tag, message, meta); }
  error(tag, message, meta) { return this._log('ERROR', tag, message, meta); }

  getRecentLogs(limit = 50) {
    return this.logs.slice(-limit);
  }

  clearLogs() {
    this.logs = [];
  }
}

export const FlowLogger = {
  createLogger(options) {
    return new LoggerInstance(options);
  }
};

if (typeof globalThis !== 'undefined') {
  globalThis.FlowLogger = FlowLogger;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-logger.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/chrome-extension/flow-logger.js engine/chrome-extension/flow-logger.test.js
git commit -m "feat: add centralized structured FlowLogger module"
```

---

### Task 2: Flow Project Lifecycle Manager

**Files:**
- Create: `engine/chrome-extension/flow-project.js`
- Create: `engine/chrome-extension/flow-project.test.js`

**Interfaces:**
- Produces: `FlowProject.detectProjectIdFromUrl(url: string) -> string | null`
- Produces: `FlowProject.extractActiveProjectId(tabs: Array<{url: string, active?: boolean}>) -> string | null`
- Produces: `FlowProject.isProjectComposerUrl(url: string, projectId: string) -> boolean`
- Produces: `FlowProject.buildProjectUrl(projectId: string) -> string`

- [ ] **Step 1: Write failing project manager tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { FlowProject } from './flow-project.js';

test('detectProjectIdFromUrl extracts 36-character UUID from standard and edit Flow URLs', () => {
  const rootUrl = 'https://flow.google.com/project/aaa1ca86-92ee-4436-b4d5-ace19f4481c9';
  assert.equal(FlowProject.detectProjectIdFromUrl(rootUrl), 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9');

  const editUrl = 'https://flow.google.com/project/aaa1ca86-92ee-4436-b4d5-ace19f4481c9/edit/asset-123';
  assert.equal(FlowProject.detectProjectIdFromUrl(editUrl), 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9');

  const invalidUrl = 'https://flow.google.com/home';
  assert.equal(FlowProject.detectProjectIdFromUrl(invalidUrl), null);
});

test('extractActiveProjectId prioritizes active Flow tabs over inactive tabs', () => {
  const tabs = [
    { url: 'https://flow.google.com/project/11111111-1111-1111-1111-111111111111', active: false },
    { url: 'https://flow.google.com/project/22222222-2222-2222-2222-222222222222', active: true },
  ];
  assert.equal(FlowProject.extractActiveProjectId(tabs), '22222222-2222-2222-2222-222222222222');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/flow-project.test.js`
Expected: FAIL

- [ ] **Step 3: Implement FlowProject module**

```javascript
// engine/chrome-extension/flow-project.js
const PROJECT_UUID_REGEX = /project\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;

export const FlowProject = {
  detectProjectIdFromUrl(url) {
    if (!url || typeof url !== 'string') return null;
    const match = url.match(PROJECT_UUID_REGEX);
    return match ? match[1] : null;
  },

  extractActiveProjectId(tabs = []) {
    if (!Array.isArray(tabs) || !tabs.length) return null;

    const ordered = [...tabs].sort((a, b) => {
      if (!!a.active !== !b.active) return a.active ? -1 : 1;
      return (b.lastAccessed || 0) - (a.lastAccessed || 0);
    });

    for (const tab of ordered) {
      const id = this.detectProjectIdFromUrl(tab.url || tab.pendingUrl || '');
      if (id) return id;
    }
    return null;
  },

  isProjectComposerUrl(url, projectId) {
    if (!url || !projectId) return false;
    try {
      const parsed = new URL(url);
      if (parsed.hostname !== 'flow.google.com') return false;
      const normalizedPath = parsed.pathname.replace(/\/$/, '');
      return normalizedPath === `/project/${projectId}`;
    } catch (_) {
      return false;
    }
  },

  buildProjectUrl(projectId) {
    return `https://flow.google.com/project/${encodeURIComponent(projectId)}`;
  }
};

if (typeof globalThis !== 'undefined') {
  globalThis.FlowProject = FlowProject;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-project.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/chrome-extension/flow-project.js engine/chrome-extension/flow-project.test.js
git commit -m "feat: add FlowProject manager module"
```

---

### Task 3: Composer DOM Automation Modules

**Files:**
- Create: `engine/chrome-extension/flow-composer-editor.js`
- Create: `engine/chrome-extension/flow-composer-config.js`
- Create: `engine/chrome-extension/flow-composer-ingredients.js`
- Create: `engine/chrome-extension/flow-composer.test.js`

**Interfaces:**
- Produces: `FlowComposerEditor.injectText(doc, text) -> boolean`
- Produces: `FlowComposerConfig.mapAspectRatio(aspectEnum) -> string | null`
- Produces: `FlowComposerConfig.mapDuration(durationSec) -> string | null`
- Produces: `FlowComposerIngredients.normalizeText(value) -> string`

- [ ] **Step 1: Write failing composer automation unit tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { FlowComposerConfig } from './flow-composer-config.js';
import { FlowComposerIngredients } from './flow-composer-ingredients.js';

test('FlowComposerConfig maps video and image aspect enums to UI labels', () => {
  assert.equal(FlowComposerConfig.mapAspectRatio('VIDEO_ASPECT_RATIO_PORTRAIT'), '9:16');
  assert.equal(FlowComposerConfig.mapAspectRatio('VIDEO_ASPECT_RATIO_LANDSCAPE'), '16:9');
  assert.equal(FlowComposerConfig.mapAspectRatio('IMAGE_ASPECT_RATIO_PORTRAIT'), '9:16');
  assert.equal(FlowComposerConfig.mapAspectRatio('IMAGE_ASPECT_RATIO_LANDSCAPE'), '16:9');
  assert.equal(FlowComposerConfig.mapAspectRatio('IMAGE_ASPECT_RATIO_SQUARE'), '1:1');
});

test('FlowComposerConfig maps duration models to UI labels', () => {
  assert.equal(FlowComposerConfig.mapDuration(4), '4s');
  assert.equal(FlowComposerConfig.mapDuration('abra_t2v_10s'), '10s');
});

test('FlowComposerIngredients normalizes asset search text and IDs', () => {
  assert.equal(FlowComposerIngredients.normalizeText(' Add  Ingredients_123 '), 'addingredients123');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/flow-composer.test.js`
Expected: FAIL

- [ ] **Step 3: Implement FlowComposerEditor, FlowComposerConfig, and FlowComposerIngredients**

```javascript
// engine/chrome-extension/flow-composer-editor.js
export const FlowComposerEditor = {
  getEditorElement(doc = document) {
    return doc.querySelector('[contenteditable="true"]');
  },

  getStartButton(doc = document) {
    return doc.querySelector('button[aria-label="Start generation"]');
  },

  injectText(doc = document, text = '') {
    const editor = this.getEditorElement(doc);
    if (!editor) return false;

    editor.focus();
    if (typeof doc.execCommand === 'function') {
      doc.execCommand('selectAll', false);
      doc.execCommand('insertText', false, text);
    }

    const current = (editor.innerText || editor.textContent || '').trim();
    if (current !== text.trim()) {
      editor.textContent = text;
      if (typeof InputEvent !== 'undefined') {
        editor.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'insertText', data: text }));
        editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
      }
    }
    return true;
  }
};
if (typeof globalThis !== 'undefined') globalThis.FlowComposerEditor = FlowComposerEditor;
```

```javascript
// engine/chrome-extension/flow-composer-config.js
export const FlowComposerConfig = {
  mapAspectRatio(ratioEnum) {
    const r = String(ratioEnum || '').toUpperCase();
    if (r.includes('PORTRAIT') || r === '9:16') return '9:16';
    if (r.includes('LANDSCAPE') || r === '16:9') return '16:9';
    if (r.includes('4_3') || r === '4:3') return '4:3';
    if (r.includes('3_4') || r === '3:4') return '3:4';
    if (r.includes('SQUARE') || r === '1:1') return '1:1';
    return null;
  },

  mapDuration(durationInput) {
    const str = String(durationInput || '');
    const match = str.match(/(\d+)\s*s?$/i);
    return match ? `${match[1]}s` : null;
  }
};
if (typeof globalThis !== 'undefined') globalThis.FlowComposerConfig = FlowComposerConfig;
```

```javascript
// engine/chrome-extension/flow-composer-ingredients.js
export const FlowComposerIngredients = {
  normalizeText(value) {
    return String(value || '').toLowerCase().replace(/[\s_-]/g, '');
  },

  collectReferenceIds(requestBody) {
    const referenceIds = [];
    const extract = (val, key = '') => {
      if (Array.isArray(val)) return val.forEach(item => extract(item, key));
      if (!val || typeof val !== 'object') {
        if (typeof val === 'string' && (key === 'mediaId' || key === 'referenceId')) referenceIds.push(val);
        if (typeof val === 'string' && key === 'name') {
          const m = val.match(/\/media\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i);
          if (m) referenceIds.push(m[1]);
        }
        return;
      }
      Object.entries(val).forEach(([k, v]) => extract(v, k));
    };
    extract(requestBody);
    return Array.from(new Set(referenceIds));
  }
};
if (typeof globalThis !== 'undefined') globalThis.FlowComposerIngredients = FlowComposerIngredients;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-composer.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/chrome-extension/flow-composer-editor.js engine/chrome-extension/flow-composer-config.js engine/chrome-extension/flow-composer-ingredients.js engine/chrome-extension/flow-composer.test.js
git commit -m "feat: add Flow composer DOM automation modules"
```

---

### Task 4: Watcher, reCAPTCHA, and API Proxy Modules

**Files:**
- Create: `engine/chrome-extension/flow-watcher.js`
- Create: `engine/chrome-extension/flow-recaptcha.js`
- Create: `engine/chrome-extension/flow-api-client.js`
- Create: `engine/chrome-extension/flow-watcher.test.js`

**Interfaces:**
- Produces: `FlowWatcher.isTrustedMediaUrl(url: string) -> boolean`
- Produces: `FlowRecaptcha.resolveActionName(endpoint: string) -> string`
- Produces: `FlowApiClient.buildRequestUrl(endpoint: string, apiKey: string, projectId: string) -> string`

- [ ] **Step 1: Write failing watcher and api client tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { FlowWatcher } from './flow-watcher.js';
import { FlowRecaptcha } from './flow-recaptcha.js';
import { FlowApiClient } from './flow-api-client.js';

test('FlowWatcher verifies Google Flow CDN hosts and excludes non-media URLs', () => {
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://flow-content.google/asset.png'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://lh3.googleusercontent.com/img=w500'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://storage.googleapis.com/flow-bucket/v.mp4'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://malicious-site.com/image.png'), false);
});

test('FlowRecaptcha maps endpoint patterns to proper reCAPTCHA enterprise actions', () => {
  assert.equal(FlowRecaptcha.resolveActionName('/v1/video:batchAsyncGenerateVideoStartImage'), 'VIDEO_GENERATION');
  assert.equal(FlowRecaptcha.resolveActionName('/v1/flowMedia:batchGenerateImages'), 'IMAGE_GENERATION');
});

test('FlowApiClient correctly replaces projectId in target URLs', () => {
  const endpoint = '/v1/projects/old-proj-id/flowMedia:batchGenerateImages';
  const resolved = FlowApiClient.buildRequestUrl(endpoint, 'API_KEY_123', 'new-proj-456');
  assert.ok(resolved.includes('/projects/new-proj-456/'));
  assert.ok(resolved.includes('key=API_KEY_123'));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test engine/chrome-extension/flow-watcher.test.js`
Expected: FAIL

- [ ] **Step 3: Implement FlowWatcher, FlowRecaptcha, and FlowApiClient**

```javascript
// engine/chrome-extension/flow-watcher.js
const TRUSTED_HOSTS = [
  'flow-content.google',
  'flow.google.com',
  'storage.googleapis.com',
];

export const FlowWatcher = {
  isTrustedMediaUrl(url) {
    if (!url || typeof url !== 'string') return false;
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:') return false;
      return TRUSTED_HOSTS.includes(parsed.hostname)
        || parsed.hostname.endsWith('.googleusercontent.com')
        || parsed.hostname.endsWith('.gstatic.com');
    } catch (_) {
      return false;
    }
  }
};
if (typeof globalThis !== 'undefined') globalThis.FlowWatcher = FlowWatcher;
```

```javascript
// engine/chrome-extension/flow-recaptcha.js
export const FlowRecaptcha = {
  resolveActionName(endpoint = '') {
    const ep = String(endpoint || '').toLowerCase();
    if (ep.includes('batchgenerateimages') || ep.includes('flowmedia')) {
      return 'IMAGE_GENERATION';
    }
    return 'VIDEO_GENERATION';
  }
};
if (typeof globalThis !== 'undefined') globalThis.FlowRecaptcha = FlowRecaptcha;
```

```javascript
// engine/chrome-extension/flow-api-client.js
export const FlowApiClient = {
  buildRequestUrl(endpoint, apiKey, projectId) {
    let target = endpoint || '';
    if (projectId && target.includes('/projects/')) {
      target = target.replace(/projects\/[0-9a-f-]{36}/i, `projects/${projectId}`);
    }
    let baseUrl = target.startsWith('http') ? target : `https://aisandbox-pa.googleapis.com${target}`;
    if (apiKey && !baseUrl.includes('key=')) {
      baseUrl += (baseUrl.includes('?') ? '&' : '?') + `key=${apiKey}`;
    }
    return baseUrl;
  }
};
if (typeof globalThis !== 'undefined') globalThis.FlowApiClient = FlowApiClient;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test engine/chrome-extension/flow-watcher.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/chrome-extension/flow-watcher.js engine/chrome-extension/flow-recaptcha.js engine/chrome-extension/flow-api-client.js engine/chrome-extension/flow-watcher.test.js
git commit -m "feat: add FlowWatcher, FlowRecaptcha, and FlowApiClient modules"
```

---

### Task 5: Refactor Background Service Worker & Side Panel Logging UI

**Files:**
- Modify: `engine/chrome-extension/background.js`
- Modify: `engine/chrome-extension/sidepanel.html`
- Modify: `engine/chrome-extension/sidepanel.js`

**Interfaces:**
- Imports: `flow-logger.js`, `flow-project.js`, `flow-composer-editor.js`, `flow-composer-config.js`, `flow-composer-ingredients.js`, `flow-watcher.js`, `flow-recaptcha.js`, `flow-api-client.js`
- Produces: Lean orchestrator routing WebSocket messages and streaming structured logs.

- [ ] **Step 1: Update importScripts in background.js**

Add the newly created modular scripts to `importScripts(...)` at the top of `background.js`.

- [ ] **Step 2: Instantiate global FlowLogger in background.js**

Wire `FlowLogger` to forward logs to WebSocket `ws.send({ type: 'agent_log', data })` whenever WebSocket is connected.

- [ ] **Step 3: Refactor handleApiRequest to utilize FlowApiClient and FlowLogger**

Replace inlined URL replacements and logging with `FlowApiClient.buildRequestUrl` and `logger.info('[API:PROXY]', ...)` calls.

- [ ] **Step 4: Update sidepanel.html & sidepanel.js to render real-time structured logs**

Add a live scrolling terminal container with filter tabs for log tags (`ALL`, `DOM`, `API`, `AUTH`, `PROJECT`).

- [ ] **Step 5: Test syntax of extension JavaScript files**

Run: `node --check engine/chrome-extension/background.js`
Run: `node --check engine/chrome-extension/sidepanel.js`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add engine/chrome-extension/background.js engine/chrome-extension/sidepanel.html engine/chrome-extension/sidepanel.js
git commit -m "refactor: integrate modular scripts into background worker and side panel"
```

---

### Task 6: Backend WebSocket Ingestion and Fleet Logging

**Files:**
- Modify: `backend/bridge_manager.py`
- Modify: `backend/routers/status.py`
- Create: `tests/test_fleet_logger.py`

**Interfaces:**
- Consumes: `{ type: "agent_log", data: log_entry }` on `/ws/agent`
- Produces: Log broadcast to dashboard WebSocket `/ws/status`
- Produces: Appends log line to `data/logs/flow_fleet_YYYY-MM-DD.log`

- [ ] **Step 1: Write failing backend fleet logger tests**

```python
import unittest
from pathlib import Path
import tempfile
from backend.bridge_manager import ExtensionBridge

class FleetLoggerTests(unittest.TestCase):
    def test_handles_agent_log_and_persists_to_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge = ExtensionBridge()
            log_entry = {
                "timestamp": "2026-09-22T12:00:00.000Z",
                "level": "INFO",
                "tag": "DOM:EDITOR",
                "message": "Prompt typed successfully",
                "instance_id": "profile-1",
            }
            bridge.record_agent_log(log_entry, log_dir=Path(temp_dir))
            
            log_files = list(Path(temp_dir).glob("flow_fleet_*.log"))
            self.assertEqual(len(log_files), 1)
            content = log_files[0].read_text(encoding="utf-8")
            self.assertIn("[DOM:EDITOR]", content)
            self.assertIn("Prompt typed successfully", content)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_fleet_logger -v`
Expected: FAIL

- [ ] **Step 3: Implement record_agent_log in bridge_manager.py**

```python
# backend/bridge_manager.py
import datetime
from pathlib import Path

def record_agent_log(self, entry: dict, log_dir: Path = None):
    if not isinstance(entry, dict):
        return
    
    if log_dir is None:
        from engine.config import ROOT_DIR
        log_dir = Path(ROOT_DIR).parent / "data" / "logs"
    
    log_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"flow_fleet_{today_str}.log"
    
    ts = entry.get("timestamp", "")
    level = entry.get("level", "INFO")
    tag = entry.get("tag", "GENERAL")
    msg = entry.get("message", "")
    inst = entry.get("instance_id", "unknown")
    
    line = f"[{ts}] [{level}] [{inst}] [{tag}] {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_fleet_logger -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/bridge_manager.py backend/routers/status.py tests/test_fleet_logger.py
git commit -m "feat: handle fleet agent logs and persist to dated log files"
```

---

### Task 7: Full Regression Verification

**Files:**
- None (verification only)

- [ ] **Step 1: Run complete Node.js test suite**

Run: `node --test tests/*.test.js engine/chrome-extension/*.test.js`
Expected: all tests PASS.

- [ ] **Step 2: Run complete Python test suite**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`
Expected: all tests PASS.

- [ ] **Step 3: Run static syntax and compilation checks**

Run: `.\.venv\Scripts\python.exe -m compileall -q backend engine`
Run: `node --check engine/chrome-extension/*.js`
Expected: exit 0.

- [ ] **Step 4: Check git status**

Run: `git status`
Expected: working tree clean.
