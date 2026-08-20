(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.StoryboardHistorySelection = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function normalizeSelectedIndexes(indexes, historyLength) {
    const limit = Math.max(0, Number(historyLength) || 0);
    return [...new Set(Array.from(indexes || []).map(Number))]
      .filter(index => Number.isInteger(index) && index >= 0 && index < limit)
      .sort((a, b) => a - b);
  }

  function removeSelectedHistory(history, indexes) {
    const source = Array.isArray(history) ? history : [];
    const selected = new Set(normalizeSelectedIndexes(indexes, source.length));
    return source.filter((_, index) => !selected.has(index));
  }

  return { normalizeSelectedIndexes, removeSelectedHistory };
});
