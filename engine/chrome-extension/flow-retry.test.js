const test = require('node:test');
const assert = require('node:assert/strict');
const { isFlowErrorCard, findRetryButtonInCard, FlowTaskExecutor } = require('./flow-executor.js');

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
      if (selector.includes('coba lagi') || selector.includes('Retry') || selector.includes('refresh') || selector.includes('try again')) {
        return this.children.find(c => {
          const aria = (c.getAttribute && c.getAttribute('aria-label')) || '';
          const title = (c.getAttribute && c.getAttribute('title')) || '';
          return /coba lagi|retry|try again|refresh/i.test(aria) || /coba lagi|retry|try again/i.test(title);
        }) || null;
      }
      if (selector.includes('mat-icon')) {
        return this.children.find(c => c.tagName === 'MAT-ICON') || null;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === 'button') {
        return this.children.filter(c => c.tagName === 'BUTTON');
      }
      return [];
    },
    click() {
      if (this.onclick) this.onclick();
    }
  };
  return el;
}

test('isFlowErrorCard detects Indonesian error card formats', () => {
  const errorTile = createMockElement('flow-error-tile', {
    innerText: 'warning\nGagal\nMaaf, video ini gagal dibuat.\nAnda tidak perlu menggunakan kredit untuk pembuatan ini.\nrefresh\nundo\ndelete_forever'
  });
  const videoTile = createMockElement('flow-video-tile', {
    children: [errorTile],
    innerText: errorTile.innerText
  });
  const gridContainer = createMockElement('flow-grid-tile-container', {
    children: [videoTile],
    innerText: errorTile.innerText
  });

  assert.strictEqual(isFlowErrorCard(gridContainer), true, 'Grid container with error tile should be recognized');
  assert.strictEqual(isFlowErrorCard(videoTile), true, 'flow-video-tile with error should be recognized');
  assert.strictEqual(isFlowErrorCard(errorTile), true, 'flow-error-tile should be recognized directly');

  // Policy safety error card format (as seen in Image #2)
  const policyTile = createMockElement('flow-error-tile', {
    innerText: 'Gagal\nPerintah ini mungkin melanggar kebijakan kami tentang pembuatan konten berbahaya. Coba perintah lain atau kirim masukan.\nAnda tidak perlu menggunakan kredit untuk pembuatan ini.'
  });
  assert.strictEqual(isFlowErrorCard(policyTile), true, 'Policy safety violation card should be recognized as error');
});

test('isFlowErrorCard detects English error card formats', () => {
  const errorTile = createMockElement('flow-error-tile', {
    innerText: 'warning\nFailed\nSorry, this video failed to generate.\nYou will not be charged credits for this generation.\nrefresh\nundo\ndelete_forever'
  });
  const gridContainer = createMockElement('flow-grid-tile-container', {
    children: [errorTile],
    innerText: errorTile.innerText
  });

  assert.strictEqual(isFlowErrorCard(gridContainer), true, 'English error card should be recognized');
  assert.strictEqual(isFlowErrorCard(errorTile), true, 'English flow-error-tile should be recognized');

  // English policy violation card format
  const policyEn = createMockElement('flow-error-tile', {
    innerText: 'Failed\nThis prompt may violate our policies on harmful content. Try another prompt or send feedback.\nYou will not be charged credits for this generation.'
  });
  assert.strictEqual(isFlowErrorCard(policyEn), true, 'English policy violation card should be recognized as error');
});

test('findRetryButtonInCard discovers Retry / Coba lagi button across Indonesian, English, and icon formats', () => {
  // Indonesian with aria-label
  const btnId = createMockElement('button', {
    attributes: { 'aria-label': 'Coba lagi' },
    children: [createMockElement('mat-icon', { innerText: 'refresh' })]
  });
  const cardId = createMockElement('flow-error-tile', {
    children: [btnId]
  });
  const foundId = findRetryButtonInCard(cardId);
  assert.ok(foundId, 'Should find Indonesian retry button');
  assert.strictEqual(foundId.getAttribute('aria-label'), 'Coba lagi');

  // English with aria-label
  const btnEn = createMockElement('button', {
    attributes: { 'aria-label': 'Retry' },
    children: [createMockElement('mat-icon', { innerText: 'refresh' })]
  });
  const cardEn = createMockElement('flow-error-tile', {
    children: [btnEn]
  });
  const foundEn = findRetryButtonInCard(cardEn);
  assert.ok(foundEn, 'Should find English retry button');
  assert.strictEqual(foundEn.getAttribute('aria-label'), 'Retry');

  // Mat-icon refresh without explicit aria-label
  const iconMat = createMockElement('mat-icon', { innerText: 'refresh' });
  const btnMat = createMockElement('button', {
    children: [iconMat]
  });
  const cardMat = createMockElement('flow-error-tile', {
    children: [btnMat]
  });
  const foundMat = findRetryButtonInCard(cardMat);
  assert.ok(foundMat, 'Should find button containing mat-icon refresh');

  // Footer with 3 buttons: [Retry] [Feedback] [Delete]
  const retryButton = createMockElement('button', {
    attributes: { 'aria-label': 'Coba lagi' },
    children: [createMockElement('mat-icon', { innerText: 'refresh' })]
  });
  const feedbackButton = createMockElement('button', {
    attributes: { 'aria-label': 'Kirim masukan' },
    children: [createMockElement('mat-icon', { innerText: 'feedback' })]
  });
  const deleteButton = createMockElement('button', {
    attributes: { 'aria-label': 'Hapus' },
    children: [createMockElement('mat-icon', { innerText: 'delete' })]
  });
  const multiButtonCard = createMockElement('flow-error-tile', {
    children: [retryButton, feedbackButton, deleteButton]
  });
  const selectedBtn = findRetryButtonInCard(multiButtonCard);
  assert.strictEqual(selectedBtn, retryButton, 'Should choose retry button and avoid delete/feedback buttons');
});

test('monitorVideoRender auto-retries max 2 times on failed tiles before throwing error', async () => {
  const retryBtn = createMockElement('button', {
    attributes: { 'aria-label': 'Coba lagi' },
    children: [createMockElement('mat-icon', { innerText: 'refresh' })]
  });
  let clickCount = 0;
  retryBtn.onclick = () => {
    clickCount++;
  };

  const errorTile = createMockElement('flow-error-tile', {
    innerText: 'Gagal\nPerintah ini mungkin melanggar kebijakan kami tentang pembuatan konten berbahaya.',
    children: [retryBtn]
  });

  const allTiles = [errorTile];

  const fakeDocument = {
    querySelectorAll: (sel) => {
      if (sel.includes('flow-video-tile') || sel.includes('flow-grid-tile-container') || sel.includes('flow-error-tile')) {
        return allTiles;
      }
      return [];
    },
    querySelector: (sel) => {
      if (sel.includes('flow-error-tile')) return errorTile;
      return null;
    }
  };

  const oldDoc = global.document;
  global.document = fakeDocument;

  const progressEvents = [];
  const executor = new FlowTaskExecutor({
    onProgress: (p) => progressEvents.push(p),
  });

  try {
    let errorCaught = null;
    try {
      await executor.monitorVideoRender(12000, 0, 2);
    } catch (err) {
      errorCaught = err;
    }

    assert.ok(clickCount >= 1 && clickCount <= 2, `Retry click count should be within max 2 retries (was: ${clickCount})`);
    const retryEvents = progressEvents.filter((p) => p.stage === 'VIDEO_RETRY');
    assert.ok(retryEvents.length >= 1, 'Should emit VIDEO_RETRY progress events');
    assert.ok(retryEvents[0].message.includes('Retry otomatis (Percobaan 1/2)'), 'Progress message should state attempt 1/2');
    assert.ok(errorCaught && errorCaught.message.includes('FLOW_GENERATION_FAILED_AFTER_RETRIES'), 'Should throw error when max retries exceeded');
  } finally {
    global.document = oldDoc;
  }
});
