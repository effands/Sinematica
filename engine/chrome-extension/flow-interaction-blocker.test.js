const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowTaskExecutor } = require('./flow-executor.js');

test('blockUserInteraction installs blocker overlay and fake cursor, and unblockUserInteraction cleans them up completely', async () => {
  const elements = new Map();
  const eventListeners = [];

  const fakeDocument = {
    getElementById: (id) => elements.get(id) || null,
    createElement: (tag) => {
      const el = {
        tagName: tag.toUpperCase(),
        id: '',
        style: {},
        classList: {
          classes: new Set(),
          add(c) { this.classes.add(c); },
          remove(c) { this.classes.delete(c); },
          contains(c) { return this.classes.has(c); },
        },
        innerHTML: '',
        appendChild(child) { this.children = this.children || []; this.children.push(child); },
        remove() {
          if (this.id) elements.delete(this.id);
        },
        parentNode: {
          removeChild(child) {
            if (child.id) elements.delete(child.id);
          }
        },
        addEventListener(type, fn, opts) {
          eventListeners.push({ target: 'element', type, fn, opts });
        },
        removeEventListener(type, fn, opts) {
          const idx = eventListeners.findIndex(e => e.type === type && e.fn === fn);
          if (idx >= 0) eventListeners.splice(idx, 1);
        }
      };
      return el;
    },
    body: {
      style: {},
      appendChild(child) {
        if (child.id) elements.set(child.id, child);
      }
    },
    documentElement: {
      style: {},
      appendChild(child) {
        if (child.id) elements.set(child.id, child);
      }
    },
    addEventListener: (type, fn, opts) => {
      eventListeners.push({ target: 'document', type, fn, opts });
    },
    removeEventListener: (type, fn, opts) => {
      const idx = eventListeners.findIndex(e => e.target === 'document' && e.type === type && e.fn === fn);
      if (idx >= 0) eventListeners.splice(idx, 1);
    }
  };

  const origDoc = globalThis.document;
  const origWindow = globalThis.window;
  const origMouseEvent = globalThis.MouseEvent;
  const origPointerEvent = globalThis.PointerEvent;

  globalThis.MouseEvent = class MockMouseEvent {
    constructor(type, init = {}) {
      this.type = type;
      this.bubbles = init.bubbles ?? true;
      this.cancelable = init.cancelable ?? true;
      this.__sinematicaSynthetic = init.__sinematicaSynthetic;
      this.isTrusted = false;
    }
  };
  globalThis.PointerEvent = class MockPointerEvent extends globalThis.MouseEvent {};

  globalThis.document = fakeDocument;
  globalThis.window = {
    addEventListener: (type, fn, opts) => {
      eventListeners.push({ target: 'window', type, fn, opts });
    },
    removeEventListener: (type, fn, opts) => {
      const idx = eventListeners.findIndex(e => e.target === 'window' && e.type === type && e.fn === fn);
      if (idx >= 0) eventListeners.splice(idx, 1);
    }
  };

  try {
    const executor = new FlowTaskExecutor({});
    
    // 1. Block interaction
    executor.blockUserInteraction();
    assert.ok(fakeDocument.getElementById('sinematica-interaction-blocker'), 'Blocker overlay must be created');
    assert.ok(fakeDocument.getElementById('sinematica-fake-cursor'), 'Fake cursor must be created');
    assert.ok(eventListeners.length > 0, 'Capture event listeners must be installed');

    // 2. Unblock interaction
    executor.unblockUserInteraction();
    assert.equal(fakeDocument.getElementById('sinematica-interaction-blocker'), null, 'Blocker overlay must be removed');
    assert.equal(fakeDocument.getElementById('sinematica-fake-cursor'), null, 'Fake cursor must be removed');

    // 3. Test abort unblocks
    executor.blockUserInteraction();
    assert.ok(fakeDocument.getElementById('sinematica-interaction-blocker'), 'Blocker overlay created before abort');
    executor.abort('task_123');
    assert.equal(fakeDocument.getElementById('sinematica-interaction-blocker'), null, 'Blocker overlay must be removed on abort');

    // 4. Test execute finally unblocks on error
    executor.ensureProject = async () => { throw new Error('Simulated test failure'); };
    await assert.rejects(async () => {
      await executor.execute({ taskId: 'task_err', storyboard: {} });
    });
    assert.equal(fakeDocument.getElementById('sinematica-interaction-blocker'), null, 'Blocker overlay must be removed in finally block on error');

    // 5. Test blocker event filtering
    executor.blockUserInteraction();
    const clickListener = eventListeners.find(l => l.type === 'click')?.fn;
    assert.ok(clickListener, 'Click listener should be registered');

    // Physical user event should be stopped
    let userEventStopped = false;
    let userEventPrevented = false;
    const physicalEvent = {
      isTrusted: true,
      stopImmediatePropagation: () => { userEventStopped = true; },
      stopPropagation: () => { userEventStopped = true; },
      preventDefault: () => { userEventPrevented = true; },
    };
    clickListener(physicalEvent);
    assert.equal(userEventStopped, true, 'Physical user event should be stopped');
    assert.equal(userEventPrevented, true, 'Physical user event should be prevented');

    // Synthetic automation event should be allowed
    let syntheticStopped = false;
    let syntheticPrevented = false;
    const syntheticEvent = {
      isTrusted: false,
      stopImmediatePropagation: () => { syntheticStopped = true; },
      stopPropagation: () => { syntheticStopped = true; },
      preventDefault: () => { syntheticPrevented = true; },
    };
    clickListener(syntheticEvent);
    assert.equal(syntheticStopped, false, 'Synthetic automation event must not be stopped');
    assert.equal(syntheticPrevented, false, 'Synthetic automation event must not be prevented');

    // Native CDP automation event with allow flag should be allowed
    globalThis.window.__sinematicaAllowNativeInput = true;
    let nativeStopped = false;
    let nativePrevented = false;
    const nativeEvent = {
      isTrusted: true,
      stopImmediatePropagation: () => { nativeStopped = true; },
      stopPropagation: () => { nativeStopped = true; },
      preventDefault: () => { nativePrevented = true; },
    };
    clickListener(nativeEvent);
    assert.equal(nativeStopped, false, 'Native CDP event with allow flag must not be stopped');
    assert.equal(nativePrevented, false, 'Native CDP event with allow flag must not be prevented');
    globalThis.window.__sinematicaAllowNativeInput = false;

    // 6. Test simulateClick and simulateInput during blocked interaction
    const fakeButton = {
      tagName: 'BUTTON',
      clicked: false,
      dispatchedEvents: [],
      getBoundingClientRect: () => ({ left: 100, top: 200, width: 50, height: 30 }),
      scrollIntoView: () => {},
      click() { this.clicked = true; },
      dispatchEvent(e) { this.dispatchedEvents.push(e); return true; },
      querySelector: () => null,
    };

    const pointerEventsTransitions = [];
    const blockerEl = fakeDocument.getElementById('sinematica-interaction-blocker');
    if (blockerEl) {
      let currentPE = blockerEl.style.pointerEvents;
      Object.defineProperty(blockerEl.style, 'pointerEvents', {
        get() { return currentPE; },
        set(val) {
          pointerEventsTransitions.push(val);
          currentPE = val;
        },
        configurable: true,
      });
    }

    const { simulateClick, simulateInput } = require('./flow-executor.js');
    await simulateClick(fakeButton);

    assert.equal(fakeButton.clicked, true, 'simulateClick must trigger click on button even when blocked');
    assert.ok(fakeButton.dispatchedEvents.some(e => e.type === 'click'), 'simulateClick must dispatch click event');
    assert.ok(pointerEventsTransitions.includes('none'), 'pointer-events must toggle to none during automation click');
    assert.equal(blockerEl.style.pointerEvents, 'auto', 'pointer-events must restore to auto after automation click');

    executor.unblockUserInteraction();
  } finally {
    globalThis.document = origDoc;
    globalThis.window = origWindow;
    globalThis.MouseEvent = origMouseEvent;
    globalThis.PointerEvent = origPointerEvent;
  }
});
