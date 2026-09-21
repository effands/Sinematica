/**
 * Sinematica Flow Agent — reCAPTCHA Enterprise Handler
 * Maps generation actions and manages reCAPTCHA execution in page world.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.FlowRecaptcha = factory().FlowRecaptcha;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DEFAULT_SITE_KEY = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';

  const FlowRecaptcha = {
    DEFAULT_SITE_KEY,

    resolveActionName(endpoint = '') {
      const ep = String(endpoint || '').toLowerCase();
      if (ep.includes('batchgenerateimages') || ep.includes('flowmedia')) {
        return 'IMAGE_GENERATION';
      }
      return 'VIDEO_GENERATION';
    }
  };

  return { FlowRecaptcha };
});
