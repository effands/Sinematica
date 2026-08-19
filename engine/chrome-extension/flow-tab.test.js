const assert = require('node:assert/strict');
const test = require('node:test');

const { ensureFlowTab, readinessState } = require('./flow-tab.js');

test('creates a Chrome window when tabs.create has no current window', async () => {
  const calls = [];
  const chromeApi = {
    tabs: {
      query: async () => [],
      create: async () => { throw new Error('No current window'); },
      get: async () => ({ id: 91, status: 'complete', url: 'https://labs.google/fx/tools/flow' }),
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
  assert.deepEqual(calls, [{ url: 'https://labs.google/fx/tools/flow', focused: false }]);
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
