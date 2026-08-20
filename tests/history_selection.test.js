const test = require('node:test');
const assert = require('node:assert/strict');

const { normalizeSelectedIndexes, removeSelectedHistory } = require('../frontend/history_selection.js');

test('select all normalizes every visible history index', () => {
  assert.deepEqual(normalizeSelectedIndexes([2, 0, 1, 1, 9], 3), [0, 1, 2]);
});

test('bulk delete removes only selected storyboard entries', () => {
  const history = [{ title: 'A' }, { title: 'B' }, { title: 'C' }];
  assert.deepEqual(removeSelectedHistory(history, [0, 2]), [{ title: 'B' }]);
});

test('bulk delete does not mutate the original history array', () => {
  const history = [{ title: 'A' }, { title: 'B' }];
  removeSelectedHistory(history, [1]);
  assert.equal(history.length, 2);
});
