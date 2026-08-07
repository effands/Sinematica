document.addEventListener('DOMContentLoaded', async () => {
  const data = await chrome.storage.local.get(['instanceName', 'flowKey', 'projectId', 'serverPort']);
  const profileInput = document.getElementById('profileNameInput');
  const portInput = document.getElementById('serverPortInput');
  const authStatus = document.getElementById('authStatus');
  const projIdLabel = document.getElementById('projIdLabel');

  const activePort = data.serverPort || '8888';
  portInput.value = activePort;

  if (data.instanceName) profileInput.value = data.instanceName;
  if (data.flowKey) {
    authStatus.textContent = 'Terhubung';
    authStatus.className = 'badge badge-green';
  }
  if (data.projectId) {
    projIdLabel.textContent = data.projectId;
  }

  // Ping backend on active port
  try {
    const res = await fetch(`http://127.0.0.1:${activePort}/api/status`);
    if (res.ok) {
      document.getElementById('serverStatus').textContent = `Aktif (${activePort})`;
      document.getElementById('serverStatus').className = 'badge badge-green';
    }
  } catch (_) {}

  document.getElementById('saveBtn').addEventListener('click', async () => {
    const name = profileInput.value.trim();
    const port = portInput.value.trim() || '8080';

    await chrome.storage.local.set({ instanceName: name, serverPort: port });
    alert(`Pengaturan tersimpan! Port: ${port}. Memperbarui koneksi extension...`);
    chrome.runtime.reload();
  });
});
