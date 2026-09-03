const assert = require('node:assert/strict');
const test = require('node:test');

const { ensureFlowTab, isFlowUrl, isTrustedFlowRequestUrl, readinessState } = require('./flow-tab.js');
const { findExistingFlowTab } = require('./flow-tab.js');

test('recognizes both legacy, localized, and current Google Flow URLs', () => {
  assert.equal(isFlowUrl('https://labs.google/fx/tools/flow/project/abc'), true);
  assert.equal(isFlowUrl('https://labs.google/fx/flow'), true);
  assert.equal(isFlowUrl('https://labs.google/fx/id/tools/flow/project/81aa0e61-0a4c-4fed-b089-d4e2e54e06f8'), true);
  assert.equal(isFlowUrl('https://labs.google/fx/en/tools/flow'), true);
  assert.equal(isFlowUrl('https://flow.google.com/project/abc'), true);
  assert.equal(isFlowUrl('https://labs.google/fx/tools/image-fx'), false);
  assert.equal(isFlowUrl('https://labs.google/fx/id/tools/image-fx'), false);
  assert.equal(isFlowUrl('https://example.com/flow.google.com'), false);
});

test('allows trusted Flow API URLs without treating them as visible Flow tabs', () => {
  assert.equal(
    isTrustedFlowRequestUrl('https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?batch=1'),
    true,
  );
  assert.equal(
    isTrustedFlowRequestUrl('https://flow.google.com/api/trpc/media.getMediaUrlRedirect'),
    true,
  );
  assert.equal(isTrustedFlowRequestUrl('http://labs.google/fx/api/trpc/test'), false);
  assert.equal(isTrustedFlowRequestUrl('https://labs.google.evil.example/fx/api/trpc/test'), false);
  assert.equal(
    isFlowUrl('https://labs.google/fx/api/trpc/media.getMediaUrlRedirect'),
    false,
  );
});

test('readiness probe never creates a tab or window for a dormant profile', async () => {
  let createCalls = 0;
  const chromeApi = {
    tabs: {
      query: async () => [],
      create: async () => { createCalls++; },
    },
    windows: {
      create: async () => { createCalls++; },
    },
  };

  const tab = await findExistingFlowTab(chromeApi);

  assert.equal(tab, null);
  assert.equal(createCalls, 0);
});

test('creates a Chrome window when tabs.create has no current window', async () => {
  const calls = [];
  const chromeApi = {
    tabs: {
      query: async () => [],
      create: async () => { throw new Error('No current window'); },
      get: async () => ({ id: 91, status: 'complete', url: 'https://flow.google.com/' }),
    },
    windows: {
      create: async (options) => {
        calls.push(options);
        return { tabs: [{ id: 91, status: 'complete', url: options.url }] };
      },
    },
  };

  const tab = await ensureFlowTab(chromeApi, { wait: async () => {} });

  assert.equal(tab.id, 91);
  assert.deepEqual(calls, [{ url: 'https://flow.google.com/', focused: false }]);
});

test('requires a loaded Flow tab, login token, and project before ready', () => {
  assert.deepEqual(
    readinessState({ tab: null, flowKey: 'token', projectId: 'project' }),
    { ready: false, error: 'NO_FLOW_WINDOW' },
  );
  assert.deepEqual(
    readinessState({ tab: { status: 'complete' }, flowKey: null, projectId: 'project' }),
    { ready: false, error: 'FLOW_LOGIN_REQUIRED' },
  );
  assert.deepEqual(
    readinessState({ tab: { status: 'complete' }, flowKey: 'token', projectId: 'project' }),
    { ready: true, error: null },
  );
});
