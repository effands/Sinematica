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

test('FlowTaskExecutor tracks progress notifications', () => {
  const progressLogs = [];
  const executor = new FlowTaskExecutor({
    onProgress: (p) => progressLogs.push(p)
  });
  executor.notifyProgress('INIT', 'Starting...');
  assert.equal(progressLogs.length, 1);
  assert.equal(progressLogs[0].stage, 'INIT');
});

test('simulateInput dispatches composed InputEvent and KeyboardEvent across component boundaries', async () => {
  const events = [];
  const fakeElement = {
    isContentEditable: true,
    textContent: '',
    innerText: '',
    focus: () => {},
    dispatchEvent: (ev) => {
      events.push({ type: ev.type, composed: ev.composed, bubbles: ev.bubbles });
      return true;
    },
    getBoundingClientRect: () => ({ left: 10, top: 10, width: 100, height: 50 }),
  };

  await simulateInput(fakeElement, 'A test prompt');
  const composedInput = events.find((e) => e.type === 'input' && e.composed);
  assert.ok(composedInput, 'input event must have composed: true');
});

test('uploadMultipleImages creates File instances and dispatches composed paste event', async () => {
  const dispatchedEvents = [];
  const fakePrompt = {
    focus: () => {},
    dispatchEvent: (ev) => {
      dispatchedEvents.push(ev);
      return true;
    },
  };

  globalThis.document = {
    querySelector: (sel) => {
      if (sel.includes('ProseMirror') || sel.includes('contenteditable')) return fakePrompt;
      return null;
    },
    querySelectorAll: () => [
      {
        innerText: 'test_storyboard.png',
        querySelector: (sel) => (sel === 'img' ? { src: 'https://flow-content.google/image/11111111-2222-3333-4444-555555555555' } : null),
        getAttribute: () => 'flowMedia/test_storyboard.png',
      }
    ],
  };

  globalThis.ClipboardEvent = class MockClipboardEvent {
    constructor(type, init) {
      this.type = type;
      this.bubbles = init.bubbles;
      this.composed = init.composed;
      this.clipboardData = init.clipboardData;
    }
  };

  globalThis.DataTransfer = class MockDataTransfer {
    constructor() {
      this.items = {
        add: (f) => this.files.push(f),
      };
      this.files = [];
    }
  };

  const executor = new FlowTaskExecutor();
  const res = await executor.uploadMultipleImages([
    { fileName: 'test_storyboard.png', base64Data: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', mimeType: 'image/png' }
  ], 'test-proj', 5000);

  const pasteEvt = dispatchedEvents.find((e) => e.type === 'paste');
  assert.ok(pasteEvt, 'paste event should be dispatched');
  assert.equal(pasteEvt.composed, true);
  assert.equal(res.length, 1);
  assert.equal(res[0].fileName, 'test_storyboard.png');
});


