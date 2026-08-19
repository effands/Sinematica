(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FlowTrpcResponse = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function isMediaRedirect(response) {
    const url = response?.url || '';
    const contentType = response?.headers?.get?.('content-type') || '';
    return Boolean(
      response?.redirected &&
      (/^video\//i.test(contentType) || /(?:flow-content\.google\/video\/|\.mp4(?:[?#]|$))/i.test(url))
    );
  }

  async function decodeTrpcResponse(response) {
    if (isMediaRedirect(response)) {
      // Do not consume the MP4 body in the extension. Python downloads the
      // signed final URL directly and verifies its expected media ID.
      return { data: { url: response.url }, responseUrl: response.url };
    }
    try {
      return { data: await response.json(), responseUrl: response.url || '' };
    } catch (error) {
      // If Google changed the redirect URL/Content-Type and our regex missed it,
      // response.json() will crash on binary MP4 bytes. Return the URL instead.
      if (response.url) {
        return { data: { url: response.url }, responseUrl: response.url };
      }
      throw error;
    }
  }

  return { isMediaRedirect, decodeTrpcResponse };
});
