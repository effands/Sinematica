/**
 * Sinematica Flow Agent — Chrome Side Panel Controller Script
 */

let activeTabMode = 'requests';
const agentLogHistory = [];

document.addEventListener('DOMContentLoaded', () => {
  initSidePanel();
});

function isFlowTab(url) {
  try {
    const p = new URL(url || '');
    if (p.hostname === 'flow.google.com' || p.hostname === 'www.flow.google.com') return true;
    if (p.hostname === 'labs.google' && /^\/fx\/(?:[a-z0-9_-]+\/)*(?:tools\/)?flow(?:\/|$)/i.test(p.pathname)) return true;
    return false;
  } catch {
    return false;
  }
}

function initSidePanel() {
  const toggle = document.getElementById('autopilotToggle');
  const toggleLabel = document.getElementById('toggleLabel');
  const statusDot = document.getElementById('statusDot');
  const btnOpenFlow = document.getElementById('btnOpenFlowTab');
  const btnSyncSession = document.getElementById('btnSyncSession') || document.getElementById('btnRefreshToken');

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
  chrome.storage.local.get(['autopilotEnabled', 'requestStats', 'requestLogs', 'flowKey', 'currentProjectId', 'lastKnownCredits', 'agentLogs'], (data) => {
    const isEnabled = data.autopilotEnabled !== false;
    if (toggle) toggle.checked = isEnabled;
    updateToggleUI(isEnabled);

    updateMetricsUI(data.requestStats || { total: 0, success: 0, failed: 0 });
    renderLogsUI(data.requestLogs || []);
    if (Array.isArray(data.agentLogs)) {
      agentLogHistory.push(...data.agentLogs);
      renderAgentLogsUI();
    }
    updateSessionStatusUI(data);
  });

  // Toggle switch handler
  if (toggle) {
    toggle.addEventListener('change', () => {
      const isEnabled = toggle.checked;
      chrome.storage.local.set({ autopilotEnabled: isEnabled });
      updateToggleUI(isEnabled);
    });
  }

  // Open Flow Tab button
  if (btnOpenFlow) {
    btnOpenFlow.addEventListener('click', async () => {
      const allTabs = await chrome.tabs.query({});
      const tabs = allTabs.filter(t => isFlowTab(t.url || t.pendingUrl));
      if (tabs && tabs.length > 0) {
        chrome.tabs.update(tabs[0].id, { active: true });
        if (tabs[0].windowId) chrome.windows.update(tabs[0].windowId, { focused: true });
      } else {
        chrome.tabs.create({ url: 'https://flow.google.com/' });
      }
      setTimeout(() => {
        chrome.storage.local.get(['flowKey', 'currentProjectId', 'lastKnownCredits'], (d) => {
          updateSessionStatusUI(d);
        });
      }, 1000);
    });
  }

  // Sync Session / Flow Tab button
  if (btnSyncSession) {
    btnSyncSession.addEventListener('click', async () => {
      btnSyncSession.textContent = '⏳ Syncing...';
      try {
        const allTabs = await chrome.tabs.query({});
        const flowTabs = allTabs.filter(t => isFlowTab(t.url || t.pendingUrl));
        if (flowTabs.length > 0) {
          const activeTab = flowTabs.find(t => t.active) || flowTabs[0];
          const match = (activeTab.url || activeTab.pendingUrl || '').match(/project\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
          if (match && match[1]) {
            chrome.storage.local.set({ currentProjectId: match[1] });
          }
          chrome.tabs.sendMessage(activeTab.id, { type: 'GET_PAGE_AUTH_TOKEN' }).catch(() => null);
          btnSyncSession.textContent = '✓ Synced!';
        } else {
          btnSyncSession.textContent = 'Tab Tidak Ada';
        }
      } catch (_) {
        btnSyncSession.textContent = '✓ Checked';
      }

      chrome.storage.local.get(['flowKey', 'currentProjectId', 'lastKnownCredits'], (d) => {
        updateSessionStatusUI(d);
      });

      setTimeout(() => {
        btnSyncSession.textContent = 'Sync Flow Tab';
      }, 2000);
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
      if (changes.autopilotEnabled && toggle) {
        toggle.checked = changes.autopilotEnabled.newValue;
        updateToggleUI(changes.autopilotEnabled.newValue);
      }
      if (changes.flowKey || changes.currentProjectId || changes.lastKnownCredits) {
        chrome.storage.local.get(['flowKey', 'currentProjectId', 'lastKnownCredits'], (data) => {
          updateSessionStatusUI(data);
        });
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

async function updateSessionStatusUI(data = {}) {
  const sessionStatusText = document.getElementById('sessionStatusText') || document.getElementById('tokenSyncText');
  const sessionPulse = document.getElementById('sessionPulse');
  const pointsText = document.getElementById('pointsText');
  if (!sessionStatusText) return;

  const currentProjectId = data.currentProjectId || null;
  const lastKnownCredits = (data.lastKnownCredits !== undefined && data.lastKnownCredits !== null) ? Number(data.lastKnownCredits) : null;
  const flowKey = data.flowKey || null;

  let hasFlowTab = false;
  try {
    const allTabs = await chrome.tabs.query({});
    hasFlowTab = allTabs.some(t => isFlowTab(t.url || t.pendingUrl));
  } catch (_) {}

  if (hasFlowTab || flowKey || currentProjectId) {
    sessionStatusText.textContent = 'Flow Session: Ready';
    sessionStatusText.style.color = 'var(--success-color)';
    if (sessionPulse) {
      sessionPulse.className = 'pulse-green';
    }

    if (pointsText) {
      if (lastKnownCredits !== null && Number.isFinite(lastKnownCredits)) {
        const estVideos = Math.floor(lastKnownCredits / 15);
        pointsText.textContent = `Kredit: ${lastKnownCredits} / ±${estVideos} Video`;
      } else if (currentProjectId) {
        const shortProj = currentProjectId.length > 8 ? currentProjectId.slice(0, 8) + '...' : currentProjectId;
        pointsText.textContent = `Proyek: ${shortProj}`;
      } else {
        pointsText.textContent = 'Sesi Terhubung';
      }
    }
  } else {
    sessionStatusText.textContent = 'Flow Tab: Belum Terbuka';
    sessionStatusText.style.color = '#f59e0b';
    if (sessionPulse) {
      sessionPulse.className = 'pulse-amber';
    }
    if (pointsText) {
      pointsText.textContent = 'Klik Open Flow Tab';
    }
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

  if (agentLogHistory.length === 0) {
    container.innerHTML = '<div style="color: #64748b; font-style: italic; padding: 8px;">No agent activity yet...</div>';
    return;
  }

  container.innerHTML = agentLogHistory.map(entry => {
    const levelColor = entry.level === 'ERROR' ? '#f43f5e'
      : entry.level === 'WARN' ? '#f59e0b'
      : entry.level === 'DEBUG' ? '#94a3b8' : '#38bdf8';

    const tagBadge = `<span style="background: rgba(255,255,255,0.08); padding: 1px 4px; border-radius: 4px; font-weight: 600; color: ${levelColor};">${entry.tag}</span>`;
    const metaStr = (entry.meta && Object.keys(entry.meta).length > 0)
      ? `<span style="color: #64748b; margin-left: 4px;">${JSON.stringify(entry.meta)}</span>`
      : '';

    return `
      <div style="line-height: 1.4; word-break: break-all;">
        <span style="color: #475569;">[${entry.time || ''}]</span>
        ${tagBadge}
        <span style="color: #e2e8f0; margin-left: 4px;">${escapeHtml(entry.msg || '')}</span>
        ${metaStr}
      </div>
    `;
  }).join('');

  const parent = container.parentElement;
  if (parent) parent.scrollTop = parent.scrollHeight;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
