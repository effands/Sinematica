const assert = require('node:assert/strict');
const test = require('node:test');

const { FlowWatcher } = require('./flow-watcher.js');
const { FlowRecaptcha } = require('./flow-recaptcha.js');
const { FlowApiClient } = require('./flow-api-client.js');

test('FlowWatcher verifies Google Flow CDN hosts and excludes non-media URLs', () => {
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://flow-content.google/asset.png'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://lh3.googleusercontent.com/img=w500'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://storage.googleapis.com/flow-bucket/v.mp4'), true);
  assert.equal(FlowWatcher.isTrustedMediaUrl('https://malicious-site.com/image.png'), false);
  assert.equal(FlowWatcher.isTrustedMediaUrl('http://flow-content.google/asset.png'), false);
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
