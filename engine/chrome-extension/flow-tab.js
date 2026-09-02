(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.FlowTab = api;
})(typeof self !== 'undefined' ? self : globalThis, function () {
  const FLOW_URL = 'https://labs.google/fx/tools/flow';
  const defaultWait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  async function waitForTabComplete(chromeApi, tab, wait = defaultWait) {
    let current = tab;
    for (let attempt = 0; attempt < 20; attempt++) {
      if (current && current.status === 'complete') return current;
      await wait(250);
      current = await chromeApi.tabs.get(tab.id).catch(() => null);
      if (!current) throw new Error('FLOW_TAB_CLOSED');
    }
    throw new Error('FLOW_TAB_LOAD_TIMEOUT');
  }

  async function findExistingFlowTab(chromeApi) {
    const tabs = await chromeApi.tabs.query({ url: '*://labs.google/*' });
    const flowTabs = (tabs || []).filter(item => /\/fx\/tools\/flow(?:\/|$)/i.test(item.url || ''));
    const candidates = flowTabs.length ? flowTabs : (tabs || []);
    return candidates.find(item => item.active && item.currentWindow)
      || candidates.find(item => item.active)
      || [...candidates].sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0))[0]
      || null;
  }

  async function ensureFlowTab(chromeApi, options = {}) {
    const wait = options.wait || defaultWait;
    let tab = await findExistingFlowTab(chromeApi);
    if (!tab) {
      try {
        tab = await chromeApi.tabs.create({ url: FLOW_URL, active: false });
      } catch (error) {
        if (!String(error).includes('No current window')) throw error;
        const createdWindow = await chromeApi.windows.create({ url: FLOW_URL, focused: false });
        tab = createdWindow && createdWindow.tabs && createdWindow.tabs[0];
      }
    }
    if (!tab) throw new Error('NO_FLOW_WINDOW');
    return waitForTabComplete(chromeApi, tab, wait);
  }

  function readinessState({ tab, flowKey, projectId }) {
    if (!tab) return { ready: false, error: 'NO_FLOW_WINDOW' };
    if (tab.status !== 'complete') return { ready: false, error: 'FLOW_TAB_LOADING' };
    if (!flowKey) return { ready: false, error: 'FLOW_LOGIN_REQUIRED' };
    if (!projectId) return { ready: false, error: 'FLOW_PROJECT_REQUIRED' };
    return { ready: true, error: null };
  }

  return { ensureFlowTab, findExistingFlowTab, readinessState, waitForTabComplete };
});
