const assert = require('node:assert/strict');
const test = require('node:test');

const { FlowLogger } = require('./flow-logger.js');

test('FlowLogger formats log entries with timestamp, tag, level and metadata', () => {
  const sent = [];
  const logger = FlowLogger.createLogger({
    instanceId: 'profile-test',
    projectId: 'proj-123',
    wsSender: (payload) => sent.push(payload),
  });

  const entry = logger.info('DOM:EDITOR', 'Editor text verified', { charCount: 42 });

  assert.equal(entry.level, 'INFO');
  assert.equal(entry.tag, 'DOM:EDITOR');
  assert.equal(entry.message, 'Editor text verified');
  assert.equal(entry.instance_id, 'profile-test');
  assert.equal(entry.project_id, 'proj-123');
  assert.equal(entry.meta.charCount, 42);
  assert.ok(entry.timestamp);

  assert.equal(sent.length, 1);
  assert.equal(sent[0].type, 'agent_log');
  assert.deepEqual(sent[0].data, entry);
});

test('FlowLogger maintains a ring buffer capped at maximum entries', () => {
  const logger = FlowLogger.createLogger({ maxEntries: 5 });
  for (let i = 1; i <= 8; i++) {
    logger.info('TEST', `Message ${i}`);
  }
  const recent = logger.getRecentLogs();
  assert.equal(recent.length, 5);
  assert.equal(recent[0].message, 'Message 4');
  assert.equal(recent[4].message, 'Message 8');
});

test('FlowLogger respects log level filtering', () => {
  const logger = FlowLogger.createLogger({ minLevel: 'WARN' });
  const debugEntry = logger.debug('TAG', 'Debug msg');
  const infoEntry = logger.info('TAG', 'Info msg');
  const warnEntry = logger.warn('TAG', 'Warn msg');
  const errorEntry = logger.error('TAG', 'Error msg');

  assert.equal(debugEntry, null);
  assert.equal(infoEntry, null);
  assert.notEqual(warnEntry, null);
  assert.notEqual(errorEntry, null);
  assert.equal(logger.getRecentLogs().length, 2);
});

test('FlowLogger notifies registered listeners', () => {
  const logger = FlowLogger.createLogger();
  const received = [];
  const listener = (entry) => received.push(entry);

  logger.addListener(listener);
  logger.info('AUTH', 'OAuth token captured');
  assert.equal(received.length, 1);
  assert.equal(received[0].tag, 'AUTH');

  logger.removeListener(listener);
  logger.info('AUTH', 'Second message');
  assert.equal(received.length, 1);
});
