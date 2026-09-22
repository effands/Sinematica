document.addEventListener('DOMContentLoaded', async () => {
  const data = await chrome.storage.local.get(['instanceName', 'flowKey', 'currentProjectId', 'lastKnownCredits', 'serverPort']);
  const profileInput = document.getElementById('profileNameInput');
  const portInput = document.getElementById('serverPortInput');
  const authStatus = document.getElementById('authStatus');
  const projIdLabel = document.getElementById('projIdLabel');
  const creditsRow = document.getElementById('creditsRow');
  const creditsLabel = document.getElementById('creditsLabel');

  const activePort = data.serverPort || '8888';
  if (portInput) portInput.value = activePort;

  if (profileInput && data.instanceName) profileInput.value = data.instanceName;

  let hasFlowTab = false;
  try {
    const allTabs = await chrome.tabs.query({});
    hasFlowTab = allTabs.some(t => {
      try {
        const u = new URL(t.url || t.pendingUrl || '');
        return u.hostname === 'flow.google.com' || (u.hostname === 'labs.google' && u.pathname.includes('/flow'));
      } catch {
        return false;
      }
    });
  } catch (_) {}

  if (authStatus) {
    if (hasFlowTab || data.flowKey || data.currentProjectId) {
      authStatus.textContent = 'Sesi Siap';
      authStatus.className = 'badge badge-green';
    } else {
      authStatus.textContent = 'Belum Buka Tab';
      authStatus.className = 'badge badge-red';
    }
  }

  if (projIdLabel && data.currentProjectId) {
    projIdLabel.textContent = data.currentProjectId;
  }

  if (creditsRow && creditsLabel && data.lastKnownCredits !== undefined && data.lastKnownCredits !== null) {
    creditsRow.style.display = 'flex';
    creditsLabel.textContent = `${data.lastKnownCredits} Kredit`;
  }

  // Ping backend on active port
  try {
    const res = await fetch(`http://127.0.0.1:${activePort}/api/status`);
    if (res.ok) {
      const serverStatus = document.getElementById('serverStatus');
      if (serverStatus) {
        serverStatus.textContent = `Aktif (${activePort})`;
        serverStatus.className = 'badge badge-green';
      }
    }
  } catch (_) {}

  const saveBtn = document.getElementById('saveBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const name = profileInput?.value?.trim() || '';
      const port = portInput?.value?.trim() || '8888';

      await chrome.storage.local.set({ instanceName: name, serverPort: port });
      alert(`Pengaturan tersimpan! Port: ${port}. Memperbarui koneksi extension...`);
      chrome.runtime.reload();
    });
  }
});
