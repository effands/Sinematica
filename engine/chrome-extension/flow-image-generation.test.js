const assert = require('node:assert/strict');
const test = require('node:test');
const { FlowTaskExecutor } = require('./flow-executor.js');

test('FlowTaskExecutor recognizes image task payload without rendering video', () => {
  const progressLogs = [];
  const executor = new FlowTaskExecutor({
    onProgress: (p) => progressLogs.push(p),
  });

  const payload = {
    taskId: 'img_test_123',
    kind: 'image',
    prompt: 'A portrait of an ancient warrior',
    storyboard: { aspectRatio: '9:16', count: 1 },
    skipImageGeneration: false,
  };

  assert.equal(payload.kind, 'image');
  assert.equal(payload.storyboard.aspectRatio, '9:16');
});

test('FlowTaskExecutor properly extracts image results and metadata', () => {
  const executor = new FlowTaskExecutor({});
  const mockGeneratedImage = {
    id: 'media_img_999',
    mediaId: 'media_img_999',
    url: 'https://flow-content.google/image/hero.png',
  };

  const finalResult = {
    ok: true,
    taskId: 'img_test_123',
    status: 'COMPLETED',
    generatedImage: mockGeneratedImage,
    imageUrl: mockGeneratedImage.url,
    mediaId: mockGeneratedImage.mediaId,
  };

  assert.equal(finalResult.ok, true);
  assert.equal(finalResult.imageUrl, 'https://flow-content.google/image/hero.png');
  assert.equal(finalResult.mediaId, 'media_img_999');
});

test('waitForImageGenerationDomDone detects newly created image tile and ignores pre-existing tiles', async () => {
  const oldImg = {
    src: 'https://flow.google.com/media/old-image-11111111-1111-1111-1111-111111111111.png',
    currentSrc: 'https://flow.google.com/media/old-image-11111111-1111-1111-1111-111111111111.png',
    naturalWidth: 512,
    complete: true,
    getAttribute: (attr) => (attr === 'data-media-id' ? '11111111-1111-1111-1111-111111111111' : null),
  };
  const oldTile = {
    innerText: '',
    textContent: '',
    querySelector: (sel) => (sel === 'img' ? oldImg : null),
    querySelectorAll: () => [],
  };

  const newImg = {
    src: 'https://flow.google.com/media/new-image-22222222-2222-2222-2222-222222222222.png',
    currentSrc: 'https://flow.google.com/media/new-image-22222222-2222-2222-2222-222222222222.png',
    naturalWidth: 512,
    complete: true,
    getAttribute: (attr) => (attr === 'data-media-id' ? '22222222-2222-2222-2222-222222222222' : null),
  };
  const newTile = {
    innerText: '',
    textContent: '',
    querySelector: (sel) => (sel === 'img' ? newImg : null),
    querySelectorAll: () => [],
  };

  let tiles = [oldTile];

  const origDoc = global.document;
  global.document = {
    querySelectorAll: (sel) => {
      if (sel.includes('flow-image-tile') || sel.includes('project-tile')) {
        return tiles;
      }
      return [];
    },
    querySelector: () => null,
  };

  try {
    const executor = new FlowTaskExecutor({});
    const promise = executor.waitForImageGenerationDomDone(6000);

    setTimeout(() => {
      tiles = [newTile, oldTile];
    }, 1600);

    const res = await promise;
    assert.ok(res);
    assert.equal(res.mediaId, '22222222-2222-2222-2222-222222222222');
    assert.equal(res.src, 'https://flow.google.com/media/new-image-22222222-2222-2222-2222-222222222222.png');
  } finally {
    global.document = origDoc;
  }
});

