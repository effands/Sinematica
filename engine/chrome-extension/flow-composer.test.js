const assert = require('node:assert/strict');
const test = require('node:test');

const { FlowComposerConfig } = require('./flow-composer-config.js');
const { FlowComposerIngredients } = require('./flow-composer-ingredients.js');
const { FlowComposerEditor } = require('./flow-composer-editor.js');

test('FlowComposerConfig maps video and image aspect enums to UI labels', () => {
  assert.equal(FlowComposerConfig.mapAspectRatio('VIDEO_ASPECT_RATIO_PORTRAIT'), '9:16');
  assert.equal(FlowComposerConfig.mapAspectRatio('VIDEO_ASPECT_RATIO_LANDSCAPE'), '16:9');
  assert.equal(FlowComposerConfig.mapAspectRatio('IMAGE_ASPECT_RATIO_PORTRAIT'), '9:16');
  assert.equal(FlowComposerConfig.mapAspectRatio('IMAGE_ASPECT_RATIO_LANDSCAPE'), '16:9');
  assert.equal(FlowComposerConfig.mapAspectRatio('IMAGE_ASPECT_RATIO_4_3'), '4:3');
  assert.equal(FlowComposerConfig.mapAspectRatio('IMAGE_ASPECT_RATIO_3_4'), '3:4');
  assert.equal(FlowComposerConfig.mapAspectRatio('IMAGE_ASPECT_RATIO_SQUARE'), '1:1');
  assert.equal(FlowComposerConfig.mapAspectRatio('unknown'), null);
});

test('FlowComposerConfig maps duration models to UI labels', () => {
  assert.equal(FlowComposerConfig.mapDuration(4), '4s');
  assert.equal(FlowComposerConfig.mapDuration(6), '6s');
  assert.equal(FlowComposerConfig.mapDuration(8), '8s');
  assert.equal(FlowComposerConfig.mapDuration(10), '10s');
  assert.equal(FlowComposerConfig.mapDuration('abra_t2v_10s'), '10s');
  assert.equal(FlowComposerConfig.mapDuration('invalid'), null);
});

test('FlowComposerIngredients normalizes asset search text and IDs', () => {
  assert.equal(FlowComposerIngredients.normalizeText(' Add  Ingredients_123 '), 'addingredients123');
});

test('FlowComposerIngredients collects reference IDs from nested request bodies', () => {
  const body = {
    requests: [
      {
        imageInputs: [
          { name: 'projects/123/media/aaa1ca86-92ee-4436-b4d5-ace19f4481c9' },
          { mediaId: 'bbb2ca86-92ee-4436-b4d5-ace19f4481c9' },
        ]
      }
    ]
  };
  const ids = FlowComposerIngredients.collectReferenceIds(body);
  assert.equal(ids.length, 2);
  assert.ok(ids.includes('aaa1ca86-92ee-4436-b4d5-ace19f4481c9'));
  assert.ok(ids.includes('bbb2ca86-92ee-4436-b4d5-ace19f4481c9'));
});

test('FlowComposerEditor validates empty and null documents safely', () => {
  assert.equal(FlowComposerEditor.injectText(null, 'test'), false);
  const mockDoc = {
    querySelector: () => null,
  };
  assert.equal(FlowComposerEditor.injectText(mockDoc, 'test'), false);
});

test('configureOptimalAffiliateVideoSettings selects video, ratio, and x1 count', async () => {
  const { FlowTaskExecutor } = require('./flow-executor.js');
  const clickedElements = [];

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
    getAttribute: (attr) => (attr === 'aria-checked' ? (checked ? 'true' : 'false') : null),
    querySelector: () => null,
    querySelectorAll: () => [],
    focus: () => {},
    click: function() {
      clickedElements.push(label);
    },
    dispatchEvent: (ev) => {
      if (ev.type === 'click') clickedElements.push(label);
      return true;
    },
    getBoundingClientRect: () => ({ left: 10, top: 10, width: 50, height: 20 }),
  });

  const fakeOverlay = {
    querySelectorAll: () => [],
    querySelector: (sel) => {
      if (sel.includes('Mode')) {
        return {
          querySelectorAll: () => [createToggle('Image'), createToggle('Video')],
        };
      }
      if (sel.includes('Video type')) {
        return {
          querySelectorAll: () => [createToggle('Frames'), createToggle('Ingredients')],
        };
      }
      if (sel.includes('Aspect ratio')) {
        return {
          querySelectorAll: () => [createToggle('16:9'), createToggle('9:16')],
        };
      }
      if (sel.includes('Output count') || sel.includes('Count')) {
        return {
          querySelectorAll: () => [createToggle('x1'), createToggle('x2'), createToggle('x4')],
        };
      }
      return null;
    },
  };

  globalThis.document = {
    querySelector: (sel) => {
      if (sel.includes('settings') || sel.includes('flow-prompt-box-settings')) return fakeOverlay;
      return null;
    },
    querySelectorAll: () => [],
    dispatchEvent: () => {},
    body: fakeOverlay,
  };

  const executor = new FlowTaskExecutor();
  const ok = await executor.configureOptimalAffiliateVideoSettings({
    subTab: 'Frames',
    aspectRatio: '9:16',
    outputCount: 1,
  });

  assert.equal(ok, true);
  assert.ok(clickedElements.includes('Video'), 'Video toggle must be clicked');
  assert.ok(clickedElements.includes('Frames'), 'Frames toggle must be clicked');
  assert.ok(clickedElements.includes('9:16'), '9:16 ratio toggle must be clicked');
  assert.ok(clickedElements.includes('x1'), 'x1 count toggle must be clicked');
});

