(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.FlowAuth = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  // The legacy Flow client still exposes its authenticated NextAuth session here.
  // Use the extension's existing host permission; never copy cookies into headers.
  const SESSION_URL = 'https://labs.google/fx/api/auth/session';

  function sessionToken(session, now = Date.now()) {
    if (!session || typeof session !== 'object') return null;
    if (session.error) return null;
    if (session.expires) {
      const expires = Date.parse(session.expires);
      if (!Number.isFinite(expires) || expires <= now) return null;
    }
    const token = session.access_token ?? session.accessToken;
    return typeof token === 'string' && token.length > 0 && !/\s/.test(token)
      ? token : null;
  }

  async function recoverSession(fetchImpl = fetch) {
    try {
      const response = await fetchImpl(SESSION_URL, {
        credentials: 'include', cache: 'no-store', redirect: 'error',
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) return null;
      return sessionToken(await response.json());
    } catch (_) {
      return null;
    }
  }

  return { sessionToken, recoverSession };
});
