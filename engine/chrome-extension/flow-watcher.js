/**
 * Sinematica Flow Agent — Generation Watcher & Media Host Validator
 * Validates media URLs and monitors image/video generation status.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.FlowWatcher = factory().FlowWatcher;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const TRUSTED_HOSTS = [
    'flow-content.google',
    'flow.google.com',
    'storage.googleapis.com',
  ];

  const FlowWatcher = {
    isTrustedMediaUrl(url) {
      if (!url || typeof url !== 'string') return false;
      if (url.startsWith('blob:') || url.startsWith('data:image/')) return true;
      if (url.includes('avatar') || url.includes('logo') || url.includes('icon') || url.includes('svg') || url.includes('profile_photo') || url.includes('ring') || url.includes('/gb/')) {
        return false;
      }
      try {
        const parsed = new URL(url);
        if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return false;
        if (parsed.hostname.endsWith('.gstatic.com')) return false;
        return TRUSTED_HOSTS.includes(parsed.hostname)
          || parsed.hostname.endsWith('.googleusercontent.com');
      } catch (_) {
        return false;
      }
    }
  };

  return { FlowWatcher };
});
