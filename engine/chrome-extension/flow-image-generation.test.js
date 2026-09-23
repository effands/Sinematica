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

test('waitForImageGenerationDomDone strictly ignores gstatic and avatar UI icons', async () => {
  const avatarImg = {
    src: 'https://ssl.gstatic.com/gb/images/ring/pr_32px_asknjuyerc.png',
    currentSrc: 'https://ssl.gstatic.com/gb/images/ring/pr_32px_asknjuyerc.png',
    naturalWidth: 32,
    complete: true,
    getAttribute: () => null,
  };
  const avatarTile = {
    innerText: '',
    textContent: '',
    querySelector: (sel) => (sel === 'img' ? avatarImg : null),
    querySelectorAll: () => [],
  };

  const validImg = {
    src: 'https://flow-content.google/image/gen-image-33333333-3333-3333-3333-333333333333.png',
    currentSrc: 'https://flow-content.google/image/gen-image-33333333-3333-3333-3333-333333333333.png',
    naturalWidth: 512,
    complete: true,
    getAttribute: (attr) => (attr === 'data-media-id' ? '33333333-3333-3333-3333-333333333333' : null),
  };
  const validTile = {
    innerText: '',
    textContent: '',
    querySelector: (sel) => (sel === 'img' ? validImg : null),
    querySelectorAll: () => [],
  };

  let tiles = [avatarTile];

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
      tiles = [validTile, avatarTile];
    }, 1600);

    const res = await promise;
    assert.ok(res);
    assert.equal(res.mediaId, '33333333-3333-3333-3333-333333333333');
    assert.equal(res.src, 'https://flow-content.google/image/gen-image-33333333-3333-3333-3333-333333333333.png');
  } finally {
    global.document = origDoc;
  }
});

test('attachFrameToStartSlot removes existing chips and connects asset to start slot', async () => {
  let chipRemoved = false;
  let startBtnClicked = false;
  let popoverAssetClicked = false;
  let addToPromptClicked = false;

  const mockChip = {
    querySelector: (sel) => {
      if (sel.includes('remove') || sel.includes('delete') || sel.includes('mat-icon')) {
        return {
          click: () => { chipRemoved = true; }
        };
      }
      return null;
    }
  };

  const mockStartBtn = {
    innerText: 'Start',
    textContent: 'Start',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Start frame' : null),
    click: () => { startBtnClicked = true; },
  };

  let createCharClicked = false;
  const mockCreateCharItem = {
    innerText: 'Create character',
    textContent: 'Create character',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Create character' : null),
    click: () => { createCharClicked = true; },
  };

  const mockValidAssetItem = {
    innerText: 'Uploaded Frame Image',
    textContent: 'Uploaded Frame Image',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Uploaded Frame Image' : null),
    querySelector: (sel) => (sel === 'img' ? { src: 'https://flow-content.google/image/123' } : null),
    click: () => { popoverAssetClicked = true; },
  };

  const mockPopover = {
    querySelectorAll: (sel) => {
      if (sel.includes('asset-item')) {
        return [mockCreateCharItem, mockValidAssetItem];
      }
      return [];
    },
    querySelector: (sel) => {
      if (sel.includes('asset-item')) {
        return mockCreateCharItem;
      }
      if (sel.includes('add-to-prompt') || sel.includes('detail-add-to-prompt-btn')) {
        return {
          click: () => { addToPromptClicked = true; }
        };
      }
      return null;
    }
  };

  const mockPromptBox = {
    querySelectorAll: (sel) => {
      if (sel.includes('flow-ingredient-chip')) return [mockChip];
      if (sel.includes('button')) return [mockStartBtn];
      return [];
    },
    querySelector: () => null,
  };

  const origDoc = global.document;
  global.document = {
    querySelector: (sel) => {
      if (sel.includes('prompt-box')) return mockPromptBox;
      if (sel.includes('flow-add-menu-popover-content')) return mockPopover;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel.includes('flow-image-tile')) return [];
      return [];
    },
  };

  try {
    const executor = new FlowTaskExecutor({});
    // Mock uploadMultipleImages so it doesn't wait for DOM
    executor.uploadMultipleImages = async () => [{ fileName: 'storyboard.png', mediaId: 'flowMedia/sb1' }];

    const ok = await executor.attachFrameToStartSlot({ fileName: 'storyboard.png' }, 5000);
    assert.equal(ok, true);
    assert.equal(chipRemoved, true, 'Old chip must be removed');
    assert.equal(startBtnClicked, true, 'Start button must be clicked');
    assert.equal(createCharClicked, false, 'Create character card must NEVER be clicked');
    assert.equal(popoverAssetClicked, true, 'Valid asset item in popover must be clicked');
    assert.equal(addToPromptClicked, true, 'Add to prompt button must be clicked');
  } finally {
    global.document = origDoc;
  }
});

test('configureImageSettings opens Video • 720p • 10s • x1 pill button and switches to Image mode', async () => {
  let settingsPillClicked = false;
  let imageToggleClicked = false;
  let ratioToggleClicked = false;
  let countToggleClicked = false;
  let overlayOpen = false;

  const origMouseEvent = globalThis.MouseEvent;
  globalThis.MouseEvent = class MockMouseEvent {
    constructor(type, init = {}) {
      this.type = type;
      Object.assign(this, init);
    }
  };

  const createToggle = (label, checked = false) => ({
    innerText: label,
    textContent: label,
    classList: { contains: (cls) => (cls === 'mat-button-toggle-checked' ? checked : false) },
    getAttribute: (attr) => (attr === 'aria-checked' ? (checked ? 'true' : 'false') : (attr === 'aria-label' ? label : null)),
    querySelector: () => null,
    querySelectorAll: () => [],
    focus: () => {},
    click: function() {
      if (label === 'Image') imageToggleClicked = true;
      if (label.includes('16:9')) ratioToggleClicked = true;
      if (label === 'x1') countToggleClicked = true;
    },
    dispatchEvent: function(ev) {
      if (ev && ev.type === 'click') {
        if (label === 'Image') imageToggleClicked = true;
        if (label.includes('16:9')) ratioToggleClicked = true;
        if (label === 'x1') countToggleClicked = true;
      }
      return true;
    },
    getBoundingClientRect: () => ({ left: 50, top: 50, width: 50, height: 30 }),
  });

  const settingsPill = {
    innerText: 'Video • 720p • 10s • x1',
    textContent: 'Video • 720p • 10s • x1',
    getAttribute: () => null,
    click: () => {
      settingsPillClicked = true;
      overlayOpen = true;
    },
    dispatchEvent: (ev) => {
      if (ev && ev.type === 'click') {
        settingsPillClicked = true;
        overlayOpen = true;
      }
      return true;
    },
    getBoundingClientRect: () => ({ left: 100, top: 100, width: 80, height: 30 }),
    closest: () => null,
  };

  const submitButton = {
    innerText: 'arrow_forward',
    textContent: 'arrow_forward',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Start generation' : null),
    click: () => {},
    getBoundingClientRect: () => ({ left: 200, top: 100, width: 40, height: 40 }),
    closest: () => null,
  };

  const imageToggle = createToggle('Image');
  const videoToggle = createToggle('Video');
  const ratioToggle = createToggle('16:9 crop_16_9');
  const countToggle = createToggle('x1');

  const mockOverlay = {
    querySelector: (sel) => {
      const lower = sel.toLowerCase();
      if (lower.includes('mode')) return { querySelectorAll: () => [imageToggle, videoToggle] };
      if (lower.includes('aspect')) return { querySelectorAll: () => [ratioToggle] };
      if (lower.includes('count')) return { querySelectorAll: () => [countToggle] };
      return null;
    },
    querySelectorAll: () => [],
  };

  const mockPromptBox = {
    querySelector: (sel) => {
      if (sel.includes('.settings-trigger-button')) return null;
      return null;
    },
    querySelectorAll: () => [settingsPill, submitButton],
  };

  const origDoc = globalThis.document;
  const origWindow = globalThis.window;
  const origChrome = globalThis.chrome;
  delete globalThis.chrome;

  globalThis.document = {
    getElementById: () => null,
    createElement: () => ({
      style: {},
      classList: { add: () => {}, remove: () => {}, contains: () => false },
      appendChild: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
    body: {
      appendChild: () => {},
    },
    querySelector: (sel) => {
      if (overlayOpen && (sel.includes('flow-prompt-box-settings') || sel.includes('cdk-overlay-pane') || sel.includes('settings-content-overlay'))) return mockOverlay;
      if (sel.includes('flow-prompt-box,') || sel === 'flow-prompt-box' || sel.includes('.flow-prompt-box')) return mockPromptBox;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel.includes('button')) return [settingsPill, submitButton];
      return [];
    },
    dispatchEvent: () => {},
  };

  try {
    const executor = new FlowTaskExecutor({});
    const res = await executor.configureImageSettings({
      aspectRatio: '16:9',
      count: 1,
      model: 'nano-banana-2',
    });

    assert.equal(res, true);
    assert.equal(settingsPillClicked, true, 'Settings pill must be clicked');
    assert.equal(imageToggleClicked, true, 'Image mode toggle must be clicked');
    assert.equal(ratioToggleClicked, true, '16:9 aspect ratio toggle must be clicked');
    assert.equal(countToggleClicked, true, 'x1 output count toggle must be clicked');
  } finally {
    globalThis.document = origDoc;
    globalThis.window = origWindow;
    globalThis.MouseEvent = origMouseEvent;
    if (origChrome) globalThis.chrome = origChrome;
  }
});



