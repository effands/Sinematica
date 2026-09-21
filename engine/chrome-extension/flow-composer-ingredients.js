/**
 * Sinematica Flow Agent — Composer Ingredients Picker Automation
 * Extracts reference media UUIDs and handles asset selection.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.FlowComposerIngredients = factory().FlowComposerIngredients;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const FlowComposerIngredients = {
    normalizeText(value) {
      return String(value || '').toLowerCase().replace(/[\s_-]/g, '');
    },

    collectReferenceIds(requestBody) {
      const referenceIds = [];
      const extract = (val, key = '') => {
        if (Array.isArray(val)) return val.forEach(item => extract(item, key));
        if (!val || typeof val !== 'object') {
          if (typeof val === 'string' && (key === 'mediaId' || key === 'referenceId')) referenceIds.push(val);
          if (typeof val === 'string' && key === 'name') {
            const m = val.match(/\/media\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i);
            if (m) referenceIds.push(m[1]);
          }
          return;
        }
        Object.entries(val).forEach(([k, v]) => extract(v, k));
      };
      extract(requestBody);
      return Array.from(new Set(referenceIds));
    }
  };

  return { FlowComposerIngredients };
});
