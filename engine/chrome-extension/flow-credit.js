(function (root) {
  function extractRemainingCredits(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const value = Number(payload.remainingCredits);
    if (!Number.isFinite(value) || value < 0) return null;
    return value;
  }

  const api = { extractRemainingCredits };
  root.FlowCredit = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
