(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.FlowGenerationCount = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const handled = new WeakSet();

  function hasVideoCountContext(element) {
    let current = element;
    for (let depth = 0; current && depth < 7; depth += 1, current = current.parentElement) {
      const text = String(current.textContent || '');
      if (/\bx1\b/i.test(text) && /\bx2\b/i.test(text) && /\bx3\b/i.test(text)
          && /\bx4\b/i.test(text) && /video/i.test(text) && /credits?/i.test(text)) {
        return true;
      }
    }
    return false;
  }

  function enforceSingleVideoOutput(rootNode) {
    if (!rootNode?.querySelectorAll) return false;
    const buttons = rootNode.querySelectorAll('button, [role="button"]');
    for (const button of buttons) {
      if (String(button.textContent || '').trim().toLowerCase() !== 'x1') continue;
      if (!hasVideoCountContext(button)) continue;
      if (handled.has(button)) return true;
      handled.add(button);
      button.click();
      return true;
    }
    return false;
  }

  return { enforceSingleVideoOutput };
});
