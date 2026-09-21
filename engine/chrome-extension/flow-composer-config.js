/**
 * Sinematica Flow Agent — Composer Config Automation
 * Maps and applies aspect ratio, duration, and output configuration.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.FlowComposerConfig = factory().FlowComposerConfig;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const FlowComposerConfig = {
    mapAspectRatio(ratioEnum) {
      const r = String(ratioEnum || '').toUpperCase();
      if (r.includes('PORTRAIT') || r === '9:16') return '9:16';
      if (r.includes('LANDSCAPE') || r === '16:9') return '16:9';
      if (r.includes('4_3') || r === '4:3') return '4:3';
      if (r.includes('3_4') || r === '3:4') return '3:4';
      if (r.includes('SQUARE') || r === '1:1') return '1:1';
      return null;
    },

    mapDuration(durationInput) {
      const str = String(durationInput || '');
      const match = str.match(/(\d+)\s*s?$/i);
      return match ? `${match[1]}s` : null;
    }
  };

  return { FlowComposerConfig };
});
