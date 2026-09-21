/**
 * Sinematica Flow Agent — Flow Project Manager
 * Manages project URL detection, validation, active project extraction, and composer URLs.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.FlowProject = factory().FlowProject;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const PROJECT_UUID_REGEX = /project\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;

  const FlowProject = {
    detectProjectIdFromUrl(url) {
      if (!url || typeof url !== 'string') return null;
      const match = url.match(PROJECT_UUID_REGEX);
      return match ? match[1] : null;
    },

    extractActiveProjectId(tabs = []) {
      if (!Array.isArray(tabs) || !tabs.length) return null;

      const ordered = [...tabs].sort((a, b) => {
        if (!!a.active !== !b.active) return a.active ? -1 : 1;
        return (b.lastAccessed || 0) - (a.lastAccessed || 0);
      });

      for (const tab of ordered) {
        const id = this.detectProjectIdFromUrl(tab.url || tab.pendingUrl || '');
        if (id) return id;
      }
      return null;
    },

    isProjectComposerUrl(url, projectId) {
      if (!url || !projectId) return false;
      try {
        const parsed = new URL(url);
        if (parsed.hostname !== 'flow.google.com') return false;
        const normalizedPath = parsed.pathname.replace(/\/$/, '');
        return normalizedPath === `/project/${projectId}`;
      } catch (_) {
        return false;
      }
    },

    buildProjectUrl(projectId) {
      return `https://flow.google.com/project/${encodeURIComponent(projectId)}`;
    }
  };

  return { FlowProject };
});
