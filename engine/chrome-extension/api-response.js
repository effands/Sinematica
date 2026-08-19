(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FlowApiResponse = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
  }

  async function decodeApiResponse(response) {
    const contentType = (response.headers.get('content-type') || '').toLowerCase();
    if (contentType.startsWith('video/') || contentType === 'application/octet-stream') {
      return {
        data: arrayBufferToBase64(await response.arrayBuffer()),
        encoding: 'base64',
      };
    }

    const text = await response.text();
    try {
      return { data: JSON.parse(text), encoding: null };
    } catch {
      return { data: text, encoding: null };
    }
  }

  return { decodeApiResponse };
});
