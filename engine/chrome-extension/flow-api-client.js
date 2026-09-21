/**
 * Sinematica Flow Agent — Native API Client
 * Formats API endpoints, parameters, and headers for Google Flow requests.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.FlowApiClient = factory().FlowApiClient;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const FlowApiClient = {
    buildRequestUrl(endpoint, apiKey, projectId) {
      let target = endpoint || '';
      if (projectId && target.includes('/projects/')) {
        target = target.replace(/projects\/[^/]+/i, `projects/${projectId}`);
      }
      let baseUrl = target.startsWith('http') ? target : `https://aisandbox-pa.googleapis.com${target}`;
      if (apiKey && !baseUrl.includes('key=')) {
        baseUrl += (baseUrl.includes('?') ? '&' : '?') + `key=${apiKey}`;
      }
      return baseUrl;
    }
  };

  return { FlowApiClient };
});
