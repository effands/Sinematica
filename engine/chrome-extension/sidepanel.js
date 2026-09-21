/**
 * Sinematica Flow Agent — Chrome Side Panel Controller Script
 */

let activeTabMode = 'requests';
const agentLogHistory = [];

document.addEventListener('DOMContentLoaded', () => {
  initSidePanel();
});

function initSidePanel() {
  const toggle = document.getElementById('autopilotToggle');
  const toggleLabel = document.getElementById('toggleLabel');
  const statusDot = document.getElementById('statusDot');
  const btnOpenFlow = document.getElementById('btnOpenFlowTab');
  const btnRefresh = document.getElementById('btnRefreshToken');
  const manualTokenInput = document.getElementById('manualTokenInput');
  const btnSaveManualToken = document.getElementById('btnSaveManualToken');

  const tabBtnRequests = document.getElementById('tabBtnRequests');
  const tabBtnAgentLogs = document.getElementById('tabBtnAgentLogs');
  const requestsView = document.getElementById('requestsView');
  const agentLogsView = document.getElementById('agentLogsView');

  // Tab switcher
  if (tabBtnRequests && tabBtnAgentLogs) {
    tabBtnRequests.addEventListener('click', () => {
      activeTabMode = 'requests';
      tabBtnRequests.style.color = 'var(--accent-purple)';
      tabBtnAgentLogs.style.color = 'var(--text-sub)';
      if (requestsView) requestsView.style.display = 'block';
      if (agentLogsView) agentLogsView.style.display = 'none';
    });

    tabBtnAgentLogs.addEventListener('click', () => {
      activeTabMode = 'agent_logs';
      tabBtnAgentLogs.style.color = 'var(--accent-purple)';
      tabBtnRequests.style.color = 'var(--text-sub)';
      if (requestsView) requestsView.style.display = 'none';
      if (agentLogsView) agentLogsView.style.display = 'block';
    });
  }

  // Load saved state
  chrome.storage.local.get(['autopilotEnabled', 'requestStats', 'requestLogs', 'flowKey', 'agentLogs'], (data) => {
    const isEnabled = data.autopilotEnabled !== false;
    if (toggle) toggle.checked = isEnabled;
    updateToggleUI(isEnabled);

    updateMetricsUI(data.requestStats || { total: 0, success: 0, failed: 0 });
    renderLogsUI(data.requestLogs || []);
    if (Array.isArray(data.agentLogs)) {
      agentLogHistory.push(...data.agentLogs);
      renderAgentLogsUI();
    }
    updateTokenSyncUI(data.flowKey);
    if (manualTokenInput && data.flowKey) {
      manualTokenInput.value = data.flowKey;
    }
  });

  if (btnSaveManualToken && manualTokenInput) {
    btnSaveManualToken.addEventListener('click', () => {
      let val = (manualTokenInput.value || '').trim();
      if (val.startsWith('Bearer ')) val = val.substring(7).trim();
      if (val) {
        chrome.storage.local.set({ flowKey: val }, () => {
          updateTokenSyncUI(val);
          btnSaveManualToken.textContent = '✓ Saved';
          chrome.runtime.sendMessage({ type: 'UPDATE_MANUAL_TOKEN', flowKey: val }).catch(() => {});
          setTimeout(() => { btnSaveManualToken.textContent = 'Set'; }, 1500);
        });
      }
    });
  }

  // Toggle switch handler
  if (toggle) {
    toggle.addEventListener('change', () => {
      const isEnabled = toggle.checked;
      chrome.storage.local.set({ autopilotEnabled: isEnabled });
      updateToggleUI(isEnabled);
    });
  }

  const isFlowTab = (url) => {
    try {
      const p = new URL(url || '');
      if (p.hostname === 'flow.google.com') return true;
      if (p.hostname === 'labs.google' && /^\/fx\/(?:[a-z0-9_-]+\/)*(?:tools\/)?flow(?:\/|$)/i.test(p.pathname)) return true;
      return false;
    } catch { return false; }
  };

  // Open Flow Tab button
  if (btnOpenFlow) {
    btnOpenFlow.addEventListener('click', async () => {
      const allTabs = await chrome.tabs.query({});
      const tabs = allTabs.filter(t => isFlowTab(t.url));
      if (tabs && tabs.length > 0) {
        chrome.tabs.update(tabs[0].id, { active: true });
        if (tabs[0].windowId) chrome.windows.update(tabs[0].windowId, { focused: true });
      } else {
        chrome.tabs.create({ url: 'https://flow.google.com/' });
      }
    });
  }

  // Refresh Token button
  if (btnRefresh) {
    btnRefresh.addEventListener('click', async () => {
      btnRefresh.textContent = '⏳ Syncing...';
      try {
        for (const sUrl of ['https://flow.google.com/fx/api/auth/session', 'https://labs.google/fx/api/auth/session']) {
          try {
            const r = await fetch(sUrl, { credentials: 'include' });
            if (r.ok) {
              const data = await r.json();
              const token = data.access_token || data.accessToken;
              if (token) {
                chrome.storage.local.set({ flowKey: token });
                chrome.runtime.sendMessage({ type: 'UPDATE_MANUAL_TOKEN', flowKey: token }).catch(() => {});
                updateTokenSyncUI(token);
                if (manualTokenInput) manualTokenInput.value = token;
                btnRefresh.textContent = '✓ Synced!';
                setTimeout(() => { btnRefresh.textContent = 'Refresh Token'; }, 2000);
                return;
              }
            }
          } catch (_) {}
        }

        const allTabs = await chrome.tabs.query({});
        const tabs = allTabs.filter(t => isFlowTab(t.url));
        if (tabs && tabs.length > 0) {
          const res = await chrome.tabs.sendMessage(tabs[0].id, { type: 'GET_PAGE_AUTH_TOKEN' }).catch(() => null);
          if (res && res.flow_key) {
            chrome.storage.local.set({ flowKey: res.flow_key });
            chrome.runtime.sendMessage({ type: 'UPDATE_MANUAL_TOKEN', flowKey: res.flow_key }).catch(() => {});
            updateTokenSyncUI(res.flow_key);
            if (manualTokenInput) manualTokenInput.value = res.flow_key;
            btnRefresh.textContent = '✓ Synced!';
            setTimeout(() => { btnRefresh.textContent = 'Refresh Token'; }, 2000);
            return;
          }
        }
      } catch (_) {}

      btnRefresh.textContent = 'Refresh Token';
    });
  }

  // Runtime message listener for live agent logs
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === 'agent_log' && msg.data) {
      agentLogHistory.push(msg.data);
      if (agentLogHistory.length > 100) agentLogHistory.shift();
      renderAgentLogsUI();
    }
  });

  // Listen to storage changes for real-time updates
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local') {
      if (changes.requestStats) updateMetricsUI(changes.requestStats.newValue);
      if (changes.requestLogs) renderLogsUI(changes.requestLogs.newValue);
      if (changes.flowKey) updateTokenSyncUI(changes.flowKey.newValue);
      if (changes.autopilotEnabled && toggle) {
        toggle.checked = changes.autopilotEnabled.newValue;
        updateToggleUI(changes.autopilotEnabled.newValue);
      }
    }
  });
}

function updateToggleUI(isEnabled) {
  const toggleLabel = document.getElementById('toggleLabel');
  const statusDot = document.getElementById('statusDot');
  if (!toggleLabel || !statusDot) return;
  if (isEnabled) {
    toggleLabel.textContent = 'ON';
    toggleLabel.style.color = '#10b981';
    statusDot.classList.add('active');
  } else {
    toggleLabel.textContent = 'OFF';
    toggleLabel.style.color = '#64748b';
    statusDot.classList.remove('active');
  }
}

function updateMetricsUI(stats) {
  const s = stats || { total: 0, success: 0, failed: 0 };
  const total = document.getElementById('metricTotal');
  const success = document.getElementById('metricSuccess');
  const failed = document.getElementById('metricFailed');
  if (total) total.textContent = s.total || 0;
  if (success) success.textContent = s.success || 0;
  if (failed) failed.textContent = s.failed || 0;
}

function updateTokenSyncUI(flowKey) {
  const syncText = document.getElementById('tokenSyncText');
  const pointsText = document.getElementById('pointsText');
  if (!syncText) return;
  if (flowKey) {
    syncText.textContent = 'token synced ready';
    syncText.style.color = '#10b981';
    if (pointsText) pointsText.textContent = 'Sisa Point 1035 / ±69 Video';
  } else {
    syncText.textContent = 'token missing / need login';
    syncText.style.color = '#f43f5e';
    if (pointsText) pointsText.textContent = 'Sisa Point — / ±— Video';
  }
}

function renderLogsUI(logs) {
  const body = document.getElementById('logTableBody');
  const emptyState = document.getElementById('emptyLogState');
  const badge = document.getElementById('logCountBadge');
  if (!body || !emptyState) return;

  const items = logs || [];
  if (badge && activeTabMode === 'requests') badge.textContent = items.length;

  if (items.length === 0) {
    body.innerHTML = '';
    emptyState.style.display = 'flex';
    return;
  }

  emptyState.style.display = 'none';
  body.innerHTML = items.map(l => `
    <tr>
      <td><code>${(l.id || '').slice(0, 6)}</code></td>
      <td><b>${l.type || 'IMAGE'}</b></td>
      <td>${l.time || ''}</td>
      <td><span class="status-tag ${l.status === 'SUCCESS' ? 'success' : (l.status === 'FAILED' ? 'failed' : 'pending')}">${l.status}</span></td>
      <td style="color: #f43f5e;">${l.error || '-'}</td>
    </tr>
  `).join('');
}

function renderAgentLogsUI() {
  const container = document.getElementById('agentLogsContainer');
  const badge = document.getElementById('logCountBadge');
  if (!container) return;

  if (badge && activeTabMode === 'agent_logs') badge.textContent = agentLogHistory.length;

  const tagColor = (tag) => {
    if (tag.startsWith('DOM:')) return '#38bdf8';
    if (tag.startsWith('API:')) return '#a78bfa';
    if (tag === 'AUTH') return '#4ade80';
    if (tag === 'CAPTCHA') return '#fbbf24';
    if (tag === 'DOWNLOAD') return '#f472b6';
    return '#94a3b8';
  };

  container.innerHTML = agentLogHistory.map(entry => {
    const time = (entry.timestamp || '').slice(11, 19);
    const color = tagColor(entry.tag || '');
    return `
      <div style="line-height: 1.4; border-bottom: 1px solid #1e293b; padding-bottom: 2px;">
        <span style="color: #64748b;">${time}</span>
        <span style="color: ${color}; font-weight: 600;">[${entry.tag || 'AGENT'}]</span>
        <span>${entry.message || ''}</span>
      </div>
    `;
  }).join('');

  const scrollContainer = document.getElementById('agentLogsView');
  if (scrollContainer) scrollContainer.scrollTop = scrollContainer.scrollHeight;
}
