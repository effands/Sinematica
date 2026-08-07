/**
 * Sinematica Flow Agent — Chrome Side Panel Controller Script
 */

document.addEventListener('DOMContentLoaded', () => {
  initSidePanel();
});

function initSidePanel() {
  const toggle = document.getElementById('autopilotToggle');
  const toggleLabel = document.getElementById('toggleLabel');
  const statusDot = document.getElementById('statusDot');
  const btnOpenFlow = document.getElementById('btnOpenFlowTab');
  const btnRefresh = document.getElementById('btnRefreshToken');

  // Load saved state
  chrome.storage.local.get(['autopilotEnabled', 'requestStats', 'requestLogs', 'flowKey'], (data) => {
    const isEnabled = data.autopilotEnabled !== false;
    toggle.checked = isEnabled;
    updateToggleUI(isEnabled);

    updateMetricsUI(data.requestStats || { total: 0, success: 0, failed: 0 });
    renderLogsUI(data.requestLogs || []);
    updateTokenSyncUI(data.flowKey);
  });

  // Toggle switch handler
  toggle.addEventListener('change', () => {
    const isEnabled = toggle.checked;
    chrome.storage.local.set({ autopilotEnabled: isEnabled });
    updateToggleUI(isEnabled);
  });

  // Open Flow Tab button
  btnOpenFlow.addEventListener('click', async () => {
    const allTabs = await chrome.tabs.query({});
    const tabs = allTabs.filter(t => t.url && t.url.includes('labs.google'));
    if (tabs && tabs.length > 0) {
      chrome.tabs.update(tabs[0].id, { active: true });
      if (tabs[0].windowId) chrome.windows.update(tabs[0].windowId, { focused: true });
    } else {
      chrome.tabs.create({ url: 'https://labs.google/fx/tools/flow' });
    }
  });

  // Refresh Token button
  btnRefresh.addEventListener('click', async () => {
    btnRefresh.textContent = '⏳ Syncing...';
    const allTabs = await chrome.tabs.query({});
    const tabs = allTabs.filter(t => t.url && t.url.includes('labs.google'));
    if (tabs && tabs.length > 0) {
      try {
        const res = await chrome.tabs.sendMessage(tabs[0].id, { type: 'GET_PAGE_AUTH_TOKEN' });
        if (res && res.flow_key) {
          chrome.storage.local.set({ flowKey: res.flow_key });
          updateTokenSyncUI(res.flow_key);
        }
      } catch (_) {}
    }
    setTimeout(() => {
      btnRefresh.textContent = 'Refresh Token';
    }, 1000);
  });

  // Listen to storage changes for real-time updates
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local') {
      if (changes.requestStats) updateMetricsUI(changes.requestStats.newValue);
      if (changes.requestLogs) renderLogsUI(changes.requestLogs.newValue);
      if (changes.flowKey) updateTokenSyncUI(changes.flowKey.newValue);
      if (changes.autopilotEnabled) {
        toggle.checked = changes.autopilotEnabled.newValue;
        updateToggleUI(changes.autopilotEnabled.newValue);
      }
    }
  });
}

function updateToggleUI(isEnabled) {
  const toggleLabel = document.getElementById('toggleLabel');
  const statusDot = document.getElementById('statusDot');
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
  document.getElementById('metricTotal').textContent = s.total || 0;
  document.getElementById('metricSuccess').textContent = s.success || 0;
  document.getElementById('metricFailed').textContent = s.failed || 0;
}

function updateTokenSyncUI(flowKey) {
  const syncText = document.getElementById('tokenSyncText');
  const pointsText = document.getElementById('pointsText');
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

  const items = logs || [];
  badge.textContent = items.length;

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
