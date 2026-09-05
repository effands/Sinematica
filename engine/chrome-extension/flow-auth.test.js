const assert = require('node:assert/strict');
const test = require('node:test');
const { sessionToken, recoverSession } = require('./flow-auth.js');
const fs = require('node:fs');
const vm = require('node:vm');

function probeHarness(recoverSession, executeScript = async () => [{ result: null }]) {
  const source = fs.readFileSync(require.resolve('./background.js'), 'utf8');
  const start = source.indexOf('async function _probeTokenFromTab');
  const end = source.indexOf('// ─── Native Main World API Request Proxy', start);
  const saved = [];
  const context = vm.createContext({
    flowKey: null, sessionRecovery: null, lastSessionRecoveryAt: 0,
    FlowAuth: { recoverSession },
    chrome: { scripting: { executeScript }, storage: { local: { set: v => saved.push(v) } } },
    notifyTokenCaptured() {}, console,
  });
  vm.runInContext(source.slice(start, end), context);
  return { context, saved, probe: id => context._probeTokenFromTab(id) };
}

test('background recovers idle Flow login and persists it for registration', async () => {
  const h = probeHarness(async () => 'recovered-token');
  assert.equal(await h.probe(12), 'recovered-token');
  assert.equal(h.saved[0].flowKey, 'recovered-token');
});

test('background falls back even when page storage injection fails', async () => {
  const h = probeHarness(async () => 'recovered-token', async () => { throw Error('injection'); });
  assert.equal(await h.probe(12), 'recovered-token');
});

test('storage probe preserves dots and other valid token characters', async () => {
  const token = 'ya29.part-one.part_two~tail';
  const h = probeHarness(async () => { throw Error('unnecessary session request'); }, async ({ func }) => {
    const storage = { length: 1, key: () => 'session', getItem: () => JSON.stringify({ access_token: token }) };
    const result = vm.runInNewContext(`(${func.toString()})()`, {
      localStorage: storage, sessionStorage: { length: 0 },
    });
    return [{ result }];
  });
  assert.equal(await h.probe(12), token);
});

test('late storage probe cannot overwrite a newly captured network token', async () => {
  let finishProbe;
  const h = probeHarness(async () => null, () => new Promise(resolve => { finishProbe = resolve; }));
  const result = h.probe(12);
  h.context.flowKey = 'fresh-network-token';
  finishProbe([{ result: 'old-storage-token' }]);
  assert.equal(await result, 'fresh-network-token');
  assert.equal(h.saved.length, 0);
});

test('failed session recovery is throttled between registration refreshes', async () => {
  let calls = 0;
  const h = probeHarness(async () => { calls++; return null; });
  assert.equal(await h.probe(12), null);
  assert.equal(await h.probe(12), null);
  assert.equal(calls, 1);
});

test('background coalesces concurrent probes and preserves a fresh captured token', async () => {
  let resolveSession;
  let calls = 0;
  const h = probeHarness(() => {
    calls++;
    return new Promise(resolve => { resolveSession = resolve; });
  });
  const one = h.probe(12);
  const two = h.probe(12);
  await new Promise(resolve => setImmediate(resolve));
  h.context.flowKey = 'new-network-token';
  resolveSession('older-session-token');
  assert.deepEqual(await Promise.all([one, two]), ['new-network-token', 'new-network-token']);
  assert.equal(calls, 1);
  assert.equal(h.saved.length, 0);
});

test('accepts session access tokens without depending on a Google prefix', () => {
  assert.equal(sessionToken({ access_token: 'new.token-format' }), 'new.token-format');
  assert.equal(sessionToken({ accessToken: 'another-token' }), 'another-token');
});

test('rejects absent, expired, erroneous, and malformed sessions', () => {
  for (const value of [null, {}, { user: {} }, { access_token: 'bad token' },
    { access_token: 'token', expires: '2020-01-01T00:00:00Z' },
    { access_token: 'token', error: 'RefreshAccessTokenError' }]) {
    assert.equal(sessionToken(value), null);
  }
});

test('recovers using existing cookies without sending captured authorization', async () => {
  const token = await recoverSession(async (url, options) => {
    assert.equal(url, 'https://labs.google/fx/api/auth/session');
    assert.equal(options.credentials, 'include');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.redirect, 'error');
    assert.equal(options.headers, undefined);
    return { ok: true, json: async () => ({ access_token: 'session-token' }) };
  });
  assert.equal(token, 'session-token');
});

test('network errors, login responses and invalid JSON do not mark a profile ready', async () => {
  for (const fetchImpl of [
    async () => { throw new Error('network'); },
    async () => ({ ok: false }),
    async () => ({ ok: true, json: async () => { throw new Error('HTML'); } }),
    async () => ({ ok: true, json: async () => ({}) }),
  ]) assert.equal(await recoverSession(fetchImpl), null);
});
