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

test('FlowInterceptor exposes direct methods on window and responds to ENSURE_PROJECT message', async () => {
  let postedMessage = null;
  const mockWindow = {
    WIZ_global_data: { FdrFJe: 'sid_1', SNlM0e: 'token_1', cfb2h: 'build_1' },
    location: { pathname: '/project/abcd-1234-efgh', href: 'https://flow.google.com/project/abcd-1234-efgh' },
    addEventListener: (type, handler) => {
      if (type === 'message') mockWindow._msgHandler = handler;
    },
    removeEventListener: () => {},
    postMessage: (data) => {
      postedMessage = data;
    },
    FlowNetworkParser,
  };
  globalThis.window = mockWindow;
  globalThis.document = { querySelectorAll: () => [] };

  delete require.cache[require.resolve('./flow-interceptor.js')];
  require('./flow-interceptor.js');

  assert.equal(typeof mockWindow.__sinematica_uploadImageDirect, 'function');
  assert.equal(typeof mockWindow.__sinematica_generateVideoDirect, 'function');
  assert.equal(typeof mockWindow.__sinematica_getMediaDownloadUrlDirect, 'function');

  // Test ENSURE_PROJECT dispatch
  await mockWindow._msgHandler({
    source: mockWindow,
    data: {
      source: 'SINEMATICA_CONTENT_SCRIPT',
      action: 'ENSURE_PROJECT',
      requestId: 'req_123',
    }
  });

  assert.ok(postedMessage);
  assert.equal(postedMessage.requestId, 'req_123');
  assert.equal(postedMessage.ok, true);
  assert.equal(postedMessage.result.projectId, 'abcd-1234-efgh');
});

