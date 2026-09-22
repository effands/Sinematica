const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowNetworkParser } = require('./flow-network-parser.js');

test('FlowNetworkParser decodes chunked Boq batchexecute response envelopes', () => {
  const mockBoqChunked = `)]}'\n124\n[["wrb.fr","ogiZ0b","[[null,[null,\\"flowMedia/img_123\\",null,\\"https://flow-content.google/image/test.png\\"]]]",null,null,null,"generic"]]`;
  const decoded = FlowNetworkParser.decodeBoqResponse(mockBoqChunked);
  assert.equal(decoded.length, 1);
  assert.equal(decoded[0].rpcId, 'ogiZ0b');
  assert.ok(Array.isArray(decoded[0].data));
});

test('FlowNetworkParser translates Boq image generation to IMAGE_READY event', () => {
  const mockBoq = `)]}'\n[["wrb.fr","ogiZ0b","[[null,[null,\\"flowMedia/img_abc\\",null,\\"https://flow-content.google/image/test.png\\"]]]",null,null,null,"generic"]]`;
  const event = FlowNetworkParser.parseGoogleFlowResponse('https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute', 200, mockBoq);
  assert.ok(event);
  assert.equal(event.type, 'IMAGE_READY');
  assert.equal(event.rpcId, 'ogiZ0b');
  assert.equal(event.imageUrls[0], 'https://flow-content.google/image/test.png');
});

test('FlowNetworkParser translates Boq video generation to VIDEO_READY event', () => {
  const mockBoq = `)]}'\n[["wrb.fr","eb1hJf","[[null,[null,\\"operations/op_999\\",null,\\"https://flow-content.google/video/test.mp4\\"]]]",null,null,null,"generic"]]`;
  const event = FlowNetworkParser.parseGoogleFlowResponse('https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute', 200, mockBoq);
  assert.ok(event);
  assert.equal(event.type, 'VIDEO_READY');
  assert.equal(event.videoUrls[0], 'https://flow-content.google/video/test.mp4');
});

test('FlowNetworkParser builds valid Boq video and image payloads', () => {
  const imgPayload = FlowNetworkParser.buildBoqImagePayload({ prompt: 'cinematic product', aspectRatio: 2, count: 1 });
  assert.ok(Array.isArray(imgPayload));
  assert.equal(imgPayload[1].length, 1);

  const vidPayload = FlowNetworkParser.buildBoqVideoPayload({ prompt: '360 rotation', aspectRatio: 1, count: 1, startImageMediaId: 'asset-123' });
  assert.ok(Array.isArray(vidPayload));
  assert.equal(vidPayload[0].length, 1);
});

test('FlowNetworkParser parses error responses into friendly error messages', () => {
  const errRes = FlowNetworkParser.parseGoogleFlowResponse('https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute', 429, 'RESOURCE_EXHAUSTED');
  assert.ok(errRes);
  assert.equal(errRes.type, 'ERROR');
  assert.equal(errRes.errorCode, 'QUOTA_EXHAUSTED');
});

test('FlowNetworkParser extracts project ID from diverse URL formats', () => {
  const pid = FlowNetworkParser.extractProjectIdFromUrl('https://flow.google.com/project/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d');
  assert.equal(pid, 'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d');
});

test('FlowNetworkParser builds valid Boq upload image payload and parses response', () => {
  const payload = FlowNetworkParser.buildBoqUploadImagePayload({
    base64Data: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    mimeType: 'image/png',
    fileName: 'storyboard.png',
    projectId: '11111111-2222-3333-4444-555555555555'
  });
  assert.ok(Array.isArray(payload));
  assert.ok(payload.length >= 1);

  const mockUploadResp = [[null, ['flowMedia/uploaded_asset_123', null, 'https://flow-content.google/image/uploaded.png']]];
  const parsed = FlowNetworkParser.parseBoqUploadImageResponse(mockUploadResp, 'storyboard.png', 'fallback-id', '11111111-2222-3333-4444-555555555555');
  assert.ok(parsed);
  assert.equal(parsed.mediaId, 'flowMedia/uploaded_asset_123');
  assert.equal(parsed.imageUrl, 'https://flow-content.google/image/uploaded.png');
});

