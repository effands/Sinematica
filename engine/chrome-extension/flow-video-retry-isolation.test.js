const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowTaskExecutor, isFlowErrorCard, findRetryButtonInCard } = require('./flow-executor.js');

function createMockElement(tag, { className = '', innerText = '', attributes = {}, children = [] } = {}) {
  const el = {
    tagName: tag.toUpperCase(),
    className,
    innerText,
    textContent: innerText,
    attributes: { ...attributes },
    children: [...children],
    classList: {
      contains(c) {
        return (className || '').split(/\s+/).includes(c);
      }
    },
    getAttribute(name) {
      return this.attributes[name] || null;
    },
    setAttribute(name, val) {
      this.attributes[name] = String(val);
    },
    dataset: {},
    querySelector(selector) {
      if (selector.includes('flow-error-tile')) {
        return this.children.find(c => c.tagName === 'FLOW-ERROR-TILE') || null;
      }
      if (selector.includes('mat-icon')) {
        return this.children.find(c => c.tagName === 'MAT-ICON') || null;
      }
      if (selector.includes('.mobile-play-badge') || selector.includes('Play')) {
        return this.children.find(c => (c.getAttribute && c.getAttribute('aria-label') === 'Play') || c.className === 'mobile-play-badge') || null;
      }
      if (selector.includes('video')) {
        return this.children.find(c => c.tagName === 'VIDEO') || null;
      }
      if (selector.includes('button')) {
        return this.children.find(c => c.tagName === 'BUTTON') || null;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector.includes('button')) {
        return this.children.filter(c => c.tagName === 'BUTTON');
      }
      if (selector.includes('video')) {
        return this.children.filter(c => c.tagName === 'VIDEO');
      }
      return [];
    },
    click() {
      if (this.onclick) this.onclick();
    },
    dispatchEvent(evt) {
      if (evt && evt.type === 'click' && this.onclick) {
        this.onclick(evt);
      }
      return true;
    }
  };
  return el;
}

test('Scene 2 generation strictly isolates Scene 1 baseline and clicks Retry on policy error cards', async () => {
  // 1. Setup pre-existing Scene 1 video tile on the canvas
  const scene1PlayBadge = createMockElement('div', { className: 'mobile-play-badge' });
  const scene1VideoTile = createMockElement('flow-video-tile', {
    attributes: { 'data-media-id': 'scene_01_media_id' },
    children: [scene1PlayBadge],
    innerText: 'play_arrow Scene 1 Completed'
  });

  // 2. Setup Scene 2 error tile (policy safety warning matching Google Flow)
  let retryClickedCount = 0;
  const retryBtn = createMockElement('button', {
    attributes: { 'aria-label': 'Coba lagi', 'title': 'Coba lagi' },
    children: [createMockElement('mat-icon', { innerText: 'refresh' })]
  });
  retryBtn.onclick = () => {
    retryClickedCount++;
  };

  const feedbackBtn = createMockElement('button', {
    attributes: { 'aria-label': 'Kirim masukan' },
    children: [createMockElement('mat-icon', { innerText: 'feedback' })]
  });
  const deleteBtn = createMockElement('button', {
    attributes: { 'aria-label': 'Hapus' },
    children: [createMockElement('mat-icon', { innerText: 'delete' })]
  });

  const scene2ErrorTile = createMockElement('flow-error-tile', {
    attributes: { 'data-media-id': 'scene_02_error_id' },
    innerText: 'Gagal\nPerintah ini mungkin melanggar kebijakan kami tentang pembuatan konten berbahaya. Coba perintah lain atau kirim masukan.\nAnda tidak perlu menggunakan kredit untuk pembuatan ini.',
    children: [retryBtn, feedbackBtn, deleteBtn]
  });

  const canvasTiles = [scene1VideoTile, scene2ErrorTile];

  // 3. Setup mock document with interaction blocker
  const blocker = createMockElement('div', { className: 'sinematica-interaction-blocker' });
  blocker.id = 'sinematica-interaction-blocker';

  const fakeDocument = {
    getElementById: (id) => {
      if (id === 'sinematica-interaction-blocker') return blocker;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel.includes('flow-video-tile') || sel.includes('flow-grid-tile-container') || sel.includes('flow-error-tile')) {
        return canvasTiles;
      }
      return [];
    },
    querySelector: (sel) => {
      if (sel.includes('flow-error-tile')) return scene2ErrorTile;
      if (sel.includes('#sinematica-interaction-blocker')) return blocker;
      return null;
    },
    documentElement: {
      dataset: {}
    }
  };

  const oldDoc = global.document;
  global.document = fakeDocument;

  const progressList = [];
  const executor = new FlowTaskExecutor({
    onProgress: (p) => progressList.push(p)
  });

  // Pre-seed seen video URLs with Scene 1's URL to verify deduplication
  executor._seenVideoUrls = new Set(['https://flow-content.google/videos/scene_01.mp4']);

  try {
    let thrownError = null;
    try {
      await executor.monitorVideoRender(12000, Date.now(), 2);
    } catch (err) {
      thrownError = err;
    }

    // Verify retry was attempted up to 2 times
    assert.strictEqual(retryClickedCount, 2, 'Should attempt to click retry button 2 times on the error card');

    // Verify progress events emitted
    const retryEvents = progressList.filter(p => p.stage === 'VIDEO_RETRY');
    assert.strictEqual(retryEvents.length, 2, 'Should emit 2 VIDEO_RETRY progress events');
    assert.ok(retryEvents[0].message.includes('Percobaan 1/2'), 'First retry notification should state attempt 1/2');
    assert.ok(retryEvents[1].message.includes('Percobaan 2/2'), 'Second retry notification should state attempt 2/2');

    // Verify Scene 1 video URL was NEVER returned as Scene 2's result
    assert.ok(thrownError, 'Must throw error when Scene 2 fails after 2 retries');
    assert.ok(
      thrownError.message.includes('FLOW_GENERATION_FAILED_AFTER_RETRIES'),
      `Error must be FLOW_GENERATION_FAILED_AFTER_RETRIES, got: ${thrownError.message}`
    );
  } finally {
    global.document = oldDoc;
  }
});
