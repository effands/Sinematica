# Rencana Implementasi: Perombakan Ekstensi Chrome Sinematica Flow Agent (Trusted DOM & Synthetic DataTransfer)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merombak total mesin otomasi ekstensi Chrome Sinematica agar kompatibel dengan Google Flow terbaru menggunakan manipulasi input file terpercaya (Synthetic `DataTransfer` ClipboardEvent Paste), parsing Google Boq RPC, form validation `composed: true`, dan klik hardware `chrome.debugger`.

**Architecture:** Arsitektur terpisah antara MAIN World (`flow-network-parser.js`, `flow-interceptor.js`) untuk parsing jaringan Boq dan token sesi, ISOLATED World (`flow-executor.js`, `content.js`) untuk manipulasi DOM dan injeksi file, serta Service Worker (`background.js`) untuk router WebSocket Fleet Sinematica dan `chrome.debugger` native click dispatcher.

**Tech Stack:** JavaScript (ES6+, Web Extensions Manifest V3, Chrome Debugger API, ProseMirror DOM Manipulation, DataTransfer/ClipboardEvent API, Node.js Native Test Runner, Python FastAPI/Pytest).

## Global Constraints
- Seluruh dependensi dieksekusi menggunakan environment lokal `.venv` di dalam folder proyek Sinematica.
- Protokol WebSocket backend `ws://127.0.0.1:8888/ws/agent` dan format event `agent_log`, `execute_task`, `task_response` harus 100% kompatibel tanpa regresi.
- Setiap generasi video scene wajib mengunci setting `Output count: x1`.
- Pengujian menggunakan `node --test` untuk ekstensi dan `pytest` untuk backend Python.
- Verifikasi visual langsung dilakukan menggunakan browser automation (`browser-skill`).

---

### Task 1: Manifest V3 Permissions & Resource Declarations

**Files:**
- Modify: `engine/chrome-extension/manifest.json`
- Test: `engine/chrome-extension/manifest.test.js`

**Interfaces:**
- Consumes: Manifest V3 specification
- Produces: Web accessible resources (`flow-network-parser.js`, `flow-interceptor.js`, `flow-executor.js`), MAIN execution world registration, `debugger` permission

- [ ] **Step 1: Tulis tes unit untuk memeriksa izin dan deklarasi manifest**

```javascript
// engine/chrome-extension/manifest.test.js
const { describe, it } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

describe('Manifest V3 Declarations', () => {
  it('should include debugger, storage, scripting permissions and MAIN world content scripts', () => {
    const manifestPath = path.join(__dirname, 'manifest.json');
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

    assert.ok(manifest.permissions.includes('debugger'));
    assert.ok(manifest.permissions.includes('scripting'));
    assert.ok(manifest.permissions.includes('storage'));

    const mainWorldScript = manifest.content_scripts.find((cs) => cs.world === 'MAIN');
    assert.ok(mainWorldScript);
    assert.ok(mainWorldScript.js.includes('flow-network-parser.js'));
    assert.ok(mainWorldScript.js.includes('flow-interceptor.js'));
  });
});
```

- [ ] **Step 2: Jalankan tes untuk memverifikasi kegagalan jika ada field yang kurang**

Run: `node --test engine/chrome-extension/manifest.test.js`

- [ ] **Step 3: Perbarui manifest.json agar memiliki entri dan izin lengkap**

```json
{
  "manifest_version": 3,
  "name": "Sinematica Flow Agent",
  "version": "1.6.0",
  "description": "Multi-Profile Google Flow Video Automation Agent for Sinematica AI",
  "icons": {
    "16": "icon16.png",
    "48": "icon48.png",
    "128": "icon128.png"
  },
  "permissions": [
    "storage",
    "cookies",
    "alarms",
    "tabs",
    "windows",
    "webRequest",
    "scripting",
    "declarativeNetRequest",
    "sidePanel",
    "debugger"
  ],
  "host_permissions": [
    "https://labs.google/*",
    "https://flow.google.com/*",
    "https://aisandbox-pa.googleapis.com/*",
    "https://aisandbox-pa.sandbox.googleapis.com/*",
    "https://storage.googleapis.com/*",
    "http://127.0.0.1:*/*",
    "http://localhost:*/*",
    "<all_urls>"
  ],
  "declarative_net_request": {
    "rule_resources": [
      {
        "id": "referer_rules",
        "enabled": true,
        "path": "rules.json"
      }
    ]
  },
  "side_panel": {
    "default_path": "sidepanel.html"
  },
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [
    {
      "matches": [
        "https://flow.google.com/*",
        "https://labs.google/*"
      ],
      "js": [
        "flow-network-parser.js",
        "flow-interceptor.js"
      ],
      "run_at": "document_start",
      "world": "MAIN"
    },
    {
      "matches": [
        "https://flow.google.com/*",
        "https://labs.google/*"
      ],
      "js": [
        "flow-network-parser.js",
        "flow-executor.js",
        "content.js"
      ],
      "run_at": "document_start"
    }
  ],
  "web_accessible_resources": [
    {
      "resources": [
        "flow-network-parser.js",
        "flow-interceptor.js",
        "flow-executor.js",
        "flow-logger.js",
        "flow-project.js",
        "flow-composer-editor.js",
        "flow-composer-config.js",
        "flow-composer-ingredients.js",
        "flow-watcher.js",
        "flow-recaptcha.js",
        "flow-api-client.js"
      ],
      "matches": [
        "https://labs.google/*",
        "https://flow.google.com/*"
      ]
    }
  ],
  "action": {
    "default_popup": "popup.html",
    "default_title": "Sinematica Flow Agent",
    "default_icon": {
      "16": "icon16.png",
      "48": "icon48.png",
      "128": "icon128.png"
    }
  }
}
```

- [ ] **Step 4: Jalankan tes unit manifest kembali**

Run: `node --test engine/chrome-extension/manifest.test.js`
Expected: PASS

- [ ] **Step 5: Commit perubahan manifest**

```bash
git add engine/chrome-extension/manifest.json engine/chrome-extension/manifest.test.js
git commit -m "feat(extension): update Manifest V3 configuration and permissions"
```

---

### Task 2: Google Boq batchexecute RPC Network Parser

**Files:**
- Modify: `engine/chrome-extension/flow-network-parser.js`
- Test: `engine/chrome-extension/flow-network-parser.test.js`

**Interfaces:**
- Consumes: Raw HTTP response strings, Boq `wrb.fr` envelopes
- Produces: `decodeBoqResponse(rawText)`, `parseGoogleFlowResponse(url, status, text, req)`, `buildBoqUploadImagePayload(params)`

- [ ] **Step 1: Tulis tes unit untuk decoding respons Boq batchexecute dan payload builder**

- [ ] **Step 2: Jalankan tes untuk memverifikasi fungsionalitas parser**

Run: `node --test engine/chrome-extension/flow-network-parser.test.js`

- [ ] **Step 3: Implementasikan logika parser Boq RPC lengkap di flow-network-parser.js**

Mendukung decoding `)]}'\n` format, ekstraksi media URL, resource ID, serta pemetaan event status (`GENERATING_VIDEO`, `VIDEO_READY`, `ERROR`).

- [ ] **Step 4: Jalankan pengujian parser**

Run: `node --test engine/chrome-extension/flow-network-parser.test.js`
Expected: PASS (seluruh test case lulus)

- [ ] **Step 5: Commit modul parser**

```bash
git add engine/chrome-extension/flow-network-parser.js engine/chrome-extension/flow-network-parser.test.js
git commit -m "feat(extension): implement Boq batchexecute RPC decoder and payload generator"
```

---

### Task 3: Main-World Network Interceptor & Session Token Sniffer

**Files:**
- Modify: `engine/chrome-extension/flow-interceptor.js`
- Test: `engine/chrome-extension/flow-interceptor.test.js`

**Interfaces:**
- Consumes: `window.fetch`, `window.XMLHttpRequest`, `window.WIZ_global_data`
- Produces: Event bridge `window.postMessage` ke Isolated World, `window.__sinematica_uploadImageDirect`

- [ ] **Step 1: Tulis tes unit untuk mock fetch/XHR interception dan session token extraction**

- [ ] **Step 2: Jalankan tes unit interceptor**

Run: `node --test engine/chrome-extension/flow-interceptor.test.js`

- [ ] **Step 3: Implementasikan monkey-patching aman pada fetch & XHR di flow-interceptor.js**

Menangkap `WIZ_global_data` (`FdrFJe`, `SNlM0e`), mengekstrak Project ID dari URL, dan meneruskan event decoded ke content script.

- [ ] **Step 4: Jalankan kembali tes unit interceptor**

Run: `node --test engine/chrome-extension/flow-interceptor.test.js`
Expected: PASS

- [ ] **Step 5: Commit modul interceptor**

```bash
git add engine/chrome-extension/flow-interceptor.js engine/chrome-extension/flow-interceptor.test.js
git commit -m "feat(extension): update MAIN-world network interceptor and session extraction"
```

---

### Task 4: Trusted File Manipulation & Synthetic DataTransfer Upload

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js`
- Test: `engine/chrome-extension/flow-executor.test.js`

**Interfaces:**
- Consumes: Base64 image payload, `b64toBlob`, `File`, `DataTransfer`, `ClipboardEvent`
- Produces: `uploadMultipleImages(imagesList, projectId, timeoutMs)` dengan synthetic paste & file input fallback

- [ ] **Step 1: Tulis tes unit untuk manipulasi DataTransfer, konversi Base64 ke Blob, dan pembentukan ClipboardEvent**

- [ ] **Step 2: Jalankan tes untuk memverifikasi perilaku upload handler**

Run: `node --test engine/chrome-extension/flow-executor.test.js`

- [ ] **Step 3: Implementasikan alur upload terpercaya di flow-executor.js**

1. Ubah Base64 menjadi Blob dan File resmi.
2. Buat `DataTransfer` dan inject via `ClipboardEvent('paste', { clipboardData, composed: true, bubbles: true })` ke `.ProseMirror`.
3. Fallback: Pasang ke `input[type="file"].files` dan dispatch `change` event.
4. Pantau kemunculan tile media hingga upload 100%.

- [ ] **Step 4: Jalankan tes unit executor**

Run: `node --test engine/chrome-extension/flow-executor.test.js`
Expected: PASS

- [ ] **Step 5: Commit modul file upload**

```bash
git add engine/chrome-extension/flow-executor.js engine/chrome-extension/flow-executor.test.js
git commit -m "feat(extension): implement trusted synthetic DataTransfer upload mechanism"
```

---

### Task 5: Angular Material MDC Settings Popover & Output Count x1 Lock

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js`
- Test: `engine/chrome-extension/flow-composer.test.js`

**Interfaces:**
- Consumes: Target ratio (`9:16` / `16:9`), target count (`1`)
- Produces: `configureOptimalAffiliateVideoSettings(options)` / `configureSettings(options)`

- [ ] **Step 1: Tulis tes unit untuk pemilihan toggle popover Angular Material**

- [ ] **Step 2: Jalankan tes unit composer**

Run: `node --test engine/chrome-extension/flow-composer.test.js`

- [ ] **Step 3: Perbarui flow-executor.js untuk menavigasi popover settings flow.google.com**

1. Klik tombol settings trigger.
2. Toggle Mode $\rightarrow$ Video.
3. Toggle Video Type $\rightarrow$ Frames.
4. Toggle Aspect Ratio $\rightarrow$ 9:16 / 16:9.
5. **Kunci Output Count $\rightarrow$ x1**.
6. Tutup popover secara aman.

- [ ] **Step 4: Jalankan tes unit**

Run: `node --test engine/chrome-extension/flow-composer.test.js`
Expected: PASS

- [ ] **Step 5: Commit update settings popover**

```bash
git add engine/chrome-extension/flow-executor.js engine/chrome-extension/flow-composer.test.js
git commit -m "feat(extension): robust Angular Material settings popover and x1 output locking"
```

---

### Task 6: Start Frame Slot Attachment, Composed Input Typing, & Generate Trigger

**Files:**
- Modify: `engine/chrome-extension/flow-executor.js`
- Modify: `engine/chrome-extension/content.js`
- Test: `engine/chrome-extension/flow-image-generation.test.js`

**Interfaces:**
- Consumes: `motionPrompt`, `startImageId` / `mediaId`
- Produces: `attachFrameToStartSlot`, `simulateInput` (dengan `composed: true`), `triggerVideoRender`, `monitorVideoRender`

- [ ] **Step 1: Tulis tes unit untuk simulasi pengetikan composed dan pemicuan render**

- [ ] **Step 2: Jalankan tes untuk memverifikasi logika**

Run: `node --test engine/chrome-extension/flow-image-generation.test.js`

- [ ] **Step 3: Implementasikan logika Start Frame, pengetikan teks, dan pemantauan status video**

1. Pasang storyboard frame ke slot Start.
2. Ketik prompt adegan dengan event `InputEvent` `composed: true`.
3. Klik tombol `<flow-generate-icon-button>` (dengan fallback MouseEvents).
4. Monitor tile progress hingga selesai 100% atau auto-retry jika gagal.

- [ ] **Step 4: Jalankan seluruh test suite Node.js ekstensi**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: Seluruh tes lulus (100% pass)

- [ ] **Step 5: Commit implementasi start frame dan submit trigger**

```bash
git add engine/chrome-extension/flow-executor.js engine/chrome-extension/content.js engine/chrome-extension/flow-image-generation.test.js
git commit -m "feat(extension): implement Start frame slotting, composed typing, and render trigger"
```

---

### Task 7: Background Service Worker WebSocket Router & CDP Hardware Click Bridge

**Files:**
- Modify: `engine/chrome-extension/background.js`
- Test: `tests/test_bridge_execute_task.py` (via `.venv/bin/pytest`)

**Interfaces:**
- Consumes: WebSocket connection `ws://127.0.0.1:8888/ws/agent`, `chrome.debugger`
- Produces: Hardware click via `Input.dispatchMouseEvent`, perutean pesan `execute_task` $\rightarrow$ `task_response`

- [ ] **Step 1: Jalankan pytest pada test suite backend untuk melihat baseline saat ini**

Run: `.venv/bin/pytest tests/test_bridge_execute_task.py`

- [ ] **Step 2: Perbarui background.js untuk mendukung delegasi native click CDP dan penanganan tugas video**

Mendukung `chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', ...)` untuk klik `isTrusted: true` saat diminta oleh executor.

- [ ] **Step 3: Jalankan pengujian integrasi WebSocket backend**

Run: `.venv/bin/pytest tests/`
Expected: 283+ passed (100% pass)

- [ ] **Step 4: Commit pembaruan background service worker**

```bash
git add engine/chrome-extension/background.js
git commit -m "feat(extension): support CDP hardware click bridge and robust task routing"
```

---

### Task 8: End-to-End Verification Menggunakan Browser Skill

**Files:**
- Test Runner: `scripts/test_e2e_generation.py`
- Launcher: `./test_generation.sh`

**Interfaces:**
- Consumes: Running Sinematica backend, Chrome with new extension loaded
- Produces: Validated E2E Scene generation video file

- [ ] **Step 1: Jalankan validasi sintaks seluruh file JavaScript ekstensi**

Run: `node --check engine/chrome-extension/*.js`
Expected: Tidak ada syntax error.

- [ ] **Step 2: Jalankan seluruh test suite Node.js ekstensi**

Run: `node --test engine/chrome-extension/*.test.js`
Expected: 49+ tests passed.

- [ ] **Step 3: Jalankan seluruh test suite Python backend**

Run: `.venv/bin/pytest tests/`
Expected: 283+ tests passed.

- [ ] **Step 4: Jalankan verifikasi browser skill**

Gunakan browser skill untuk membuka Google Flow, memvalidasi DOM elemen editor, upload paste, dan tombol generasi video.

- [ ] **Step 5: Commit akhir dan finalisasi dokumentasi**

```bash
git add .
git commit -m "chore: complete Google Flow extension trusted DOM overhaul"
```
