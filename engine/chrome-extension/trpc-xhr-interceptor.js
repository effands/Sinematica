(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FlowTrpcXhr = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  function forwardTrpcXhrResponse(xhr, forward) {
    const url = xhr.__sniffUrl || '';
    if (!url.includes('/fx/api/trpc/') || xhr.status < 200 || xhr.status >= 300) return false;
    if (xhr.responseType && xhr.responseType !== 'text') return false;
    const body = xhr.responseText || '';
    if (!body) return false;
    forward({ url, body });
    return true;
  }

  return { forwardTrpcXhrResponse };
});
