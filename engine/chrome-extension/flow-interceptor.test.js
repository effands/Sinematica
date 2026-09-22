const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowNetworkParser } = require('./flow-network-parser.js');

test('FlowInterceptor extracts WIZ_global_data session parameters correctly', () => {
  const mockWiz = {
    FdrFJe: 'mock_sid_123',
    SNlM0e: 'mock_at_token',
    cfb2h: 'boq_labs-ai-sandbox-frontend_20260903.13_p0',
  };
  globalThis.window = {
    WIZ_global_data: mockWiz,
    location: { pathname: '/fx/tools/flow', href: 'https://flow.google.com/fx/tools/flow' },
    addEventListener: () => {},
    removeEventListener: () => {},
    postMessage: () => {},
  };
  globalThis.document = {
    querySelectorAll: () => [],
  };
  globalThis.FlowNetworkParser = FlowNetworkParser;

  const { getWizSessionData } = require('./flow-interceptor.js');
  const session = getWizSessionData();
  assert.equal(session.fsid, 'mock_sid_123');
  assert.equal(session.at, 'mock_at_token');
  assert.equal(session.bl, 'boq_labs-ai-sandbox-frontend_20260903.13_p0');
});
