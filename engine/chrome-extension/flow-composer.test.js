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
