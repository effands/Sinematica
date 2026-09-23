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
    dataset: {},
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
  };
  return el;
}

test('Dual generation: Scene 2 does not fail when 1 card fails while companion card is actively rendering at 18%', async () => {
  // Setup Canvas state:
  // Scene 1: completed video (already seen)
  const scene1VideoTile = createMockElement('flow-video-tile', {
    attributes: { 'data-media-id': 'scene_01_media' },
    children: [createMockElement('div', { className: 'mobile-play-badge' })],
    innerText: 'play_arrow Scene 1 Finished',
  });

  // Scene 2 Card A: Failed error tile
  const scene2FailedTile = createMockElement('flow-error-tile', {
    attributes: { 'data-media-id': 'scene_02_failed_tile' },
    innerText: 'Gagal\nMaaf, video ini gagal dibuat.\nAnda tidak perlu menggunakan kredit untuk pembuatan ini.',
    children: [
      createMockElement('button', {
        attributes: { 'aria-label': 'Hapus' },
        children: [createMockElement('mat-icon', { innerText: 'delete' })]
      })
    ]
  });

  // Scene 2 Card B: Actively rendering at 18%
  const scene2RenderingTile = createMockElement('flow-video-tile', {
    attributes: { 'data-media-id': 'scene_02_rendering_tile' },
    innerText: '18% Generating video...',
  });

  let canvasTiles = [scene1VideoTile, scene2FailedTile, scene2RenderingTile];

  const fakeDocument = {
    querySelectorAll: (sel) => {
      if (sel.includes('flow-video-tile') || sel.includes('flow-grid-tile-container') || sel.includes('flow-error-tile')) {
        return canvasTiles;
      }
      return [];
    },
    querySelector: (sel) => {
      if (sel.includes('flow-error-tile')) return scene2FailedTile;
      return null;
    }
  };

  const oldDoc = global.document;
  global.document = fakeDocument;

  const progressEvents = [];
  const executor = new FlowTaskExecutor({
    onProgress: (p) => progressEvents.push(p)
  });

  // Seed with Scene 1's already claimed URL
  executor._seenVideoUrls = new Set(['https://flow-content.google/videos/scene_01.mp4']);

  // Simulate video completion after 1.5 seconds by transforming the rendering tile into a completed tile
  setTimeout(() => {
    const freshVidTag = createMockElement('video', {
      attributes: { src: 'https://flow-content.google/videos/scene_02_completed.mp4' }
    });
    freshVidTag.currentSrc = 'https://flow-content.google/videos/scene_02_completed.mp4';
    const scene2CompletedTile = createMockElement('flow-video-tile', {
      attributes: { 'data-media-id': 'scene_02_completed_tile' },
      children: [createMockElement('div', { className: 'mobile-play-badge' }), freshVidTag],
      innerText: 'play_arrow Scene 2 Completed',
    });
    // Replace rendering tile with completed tile in canvas
    canvasTiles = [scene1VideoTile, scene2FailedTile, scene2CompletedTile];
  }, 1200);

  try {
    const result = await executor.monitorVideoRender(10000, Date.now(), 2);
    assert.ok(result, 'Result should be returned');
    assert.ok(result.video, 'Video object must be present');
    assert.strictEqual(result.video.url, 'https://flow-content.google/videos/scene_02_completed.mp4');
    assert.notStrictEqual(result.video.url, 'https://flow-content.google/videos/scene_01.mp4');
    assert.ok(executor._seenVideoUrls.has('https://flow-content.google/videos/scene_02_completed.mp4'));
  } finally {
    global.document = oldDoc;
  }
});
