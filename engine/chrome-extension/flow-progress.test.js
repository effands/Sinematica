const assert = require('node:assert/strict');
const test = require('node:test');

function formatTaskProgressMessage(requestId, stage, message, extra = {}) {
  return {
    type: 'task_progress',
    id: requestId,
    stage: stage || 'PROGRESS',
    message: message || '',
    timestamp: Date.now(),
    percent: typeof extra.percent === 'number' ? extra.percent : undefined,
    ...extra,
  };
}

test('formatTaskProgressMessage builds standard progress payload', () => {
  const msg = formatTaskProgressMessage('req_123', 'TYPING_PROMPT', 'Mengetik prompt...', { percent: 25 });
  assert.equal(msg.type, 'task_progress');
  assert.equal(msg.id, 'req_123');
  assert.equal(msg.stage, 'TYPING_PROMPT');
  assert.equal(msg.message, 'Mengetik prompt...');
  assert.equal(msg.percent, 25);
  assert.equal(typeof msg.timestamp, 'number');
});

test('formatTaskProgressMessage supports extra metadata and stage defaults', () => {
  const msg = formatTaskProgressMessage('req_456', null, 'Memproses...', { customKey: 'val1' });
  assert.equal(msg.stage, 'PROGRESS');
  assert.equal(msg.customKey, 'val1');
});
