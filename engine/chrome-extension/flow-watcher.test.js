const assert = require('node:assert/strict');
const test = require('node:test');

const { FlowWatcher } = require('./flow-watcher.js');
const { FlowRecaptcha } = require('./flow-recaptcha.js');
const { FlowApiClient } = require('./flow-api-client.js');

test('FlowWatcher verifies Google Flow CDN hosts and excludes non-media URLs', () => {
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://flow-content.google/asset.png'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://lh3.googleusercontent.com/img=w500'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://storage.googleapis.com/flow-bucket/v.mp4'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('blob:https://flow.google.com/123-abc'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://ssl.gstatic.com/gb/images/ring/pr_32px_asknjuyerc.png'), false);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://www.gstatic.com/images/branding/googlelogo/svg/googlelogo_clr_74x24px.svg'), false);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://malicious-site.com/image.png'), false);
  assert.equal(FlowWatcher.isTrustedMediaUrl('http://malicious-site.com/asset.png'), false);
  assert.equal(FlowWatcher.isTrustedMediaUrl(''), false);
});

test('FlowRecaptcha maps endpoint patterns to proper reCAPTCHA enterprise actions', () => {
  assert.equal(FlowRecaptcha.resolveActionName('/v1/video:batchAsyncGenerateVideoStartImage'), 'VIDEO_GENERATION');
  assert.equal(FlowRecaptcha.resolveActionName('/v1/flowMedia:batchGenerateImages'), 'IMAGE_GENERATION');
  assert.equal(FlowRecaptcha.resolveActionName('/v1/projects/123/flowMedia:batchGenerateImages'), 'IMAGE_GENERATION');
  assert.equal(FlowRecaptcha.resolveActionName(''), 'VIDEO_GENERATION');
});

test('FlowApiClient correctly replaces projectId and formats target URLs', () => {
  const endpoint = '/v1/projects/old-proj-id/flowMedia:batchGenerateImages';
  const resolved = FlowApiClient.buildRequestUrl(endpoint, 'API_KEY_123', 'new-proj-456');
  assert.ok(resolved.includes('/projects/new-proj-456/flowMedia:batchGenerateImages'));
  assert.ok(resolved.includes('key=API_KEY_123'));

  const fullUrl = 'https://aisandbox-pa.googleapis.com/v1/credits';
  const resolvedFull = FlowApiClient.buildRequestUrl(fullUrl, 'KEY_456');
  assert.equal(resolvedFull, 'https://aisandbox-pa.googleapis.com/v1/credits?key=KEY_456');
});
