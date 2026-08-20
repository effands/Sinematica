/**
 * Sinematica AI Studio — Main Frontend SPA Application Logic
 */

let currentStoryboard = null;
let currentJobId = null;
let pollTimer = null;
let selectedRefFiles = [];
let selectedRenderClips = []; // ordered {job_id, filename, label} picked from Gallery for Auto Render

// Groups terminal log lines into a small set of colors: error/warning (from backend level),
// success (completion messages), profile (Chrome worker actions), or default system info.
function logLineCategory(l) {
  if (l.level === 'error') return 'error';
  if (l.level === 'warning') return 'warning';
  if (/✅|🎬|selesai 100%/.test(l.message)) return 'success';
  if (l.profile && l.profile !== 'System') return 'profile';
  return 'info';
}

document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initStatusPolling();
  initFleetTestPrompt();
  initDropzone();
  initStoryboardForm();
  initGallery();
  initSettingsModal();
  initSeoKitModal();
  initStoryboardHistoryModal();
  renderHistoryTab();
  initCustomAlertModal();
  loadLastStoryboard();
  initAspectRatioDefault();
});

function initAspectRatioDefault() {
  const select = document.getElementById('aspectSelect');
  const checkbox = document.getElementById('aspectDefaultCheckbox');
  if (!select || !checkbox) return;

  const storageKey = 'sinematica_default_aspect_ratio';
  const saved = localStorage.getItem(storageKey);
  if (saved === 'portrait' || saved === 'landscape') {
    select.value = saved;
    checkbox.checked = true;
  }

  checkbox.addEventListener('change', () => {
    if (checkbox.checked) {
      localStorage.setItem(storageKey, select.value);
      showToast(`Default video diatur ke ${select.value === 'portrait' ? 'Short 9:16' : 'Landscape 16:9'}.`, 'success');
    } else {
      localStorage.removeItem(storageKey);
      showToast('Default aspect ratio dinonaktifkan.', 'info');
    }
  });

  select.addEventListener('change', () => {
    if (checkbox.checked) localStorage.setItem(storageKey, select.value);
  });
}

// Toast Notifications Helper
function showToast(message, type = 'info', title = '') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-item toast-${type}`;

  const icons = {
    info: '💡',
    success: '✅',
    warning: '⚠️',
    error: '❌'
  };

  toast.innerHTML = `
    <div style="font-size: 18px;">${icons[type] || '✨'}</div>
    <div style="flex: 1;">
      ${title ? `<div style="font-weight: bold; font-size: 13px; margin-bottom: 2px;">${title}</div>` : ''}
      <div style="font-size: 12px; color: var(--text-secondary);">${message}</div>
    </div>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Custom Alert Modal Helper
function showCustomAlert(message, title = 'Informasi Studio', icon = '✨') {
  const modal = document.getElementById('customAlertModal');
  const titleEl = document.getElementById('customAlertTitle');
  const msgEl = document.getElementById('customAlertMsg');
  const iconEl = document.getElementById('customAlertIcon');

  if (!modal) return;
  titleEl.textContent = title;
  msgEl.textContent = message;
  iconEl.textContent = icon;

  modal.classList.add('active');
}

function initCustomAlertModal() {
  const modal = document.getElementById('customAlertModal');
  const okBtn = document.getElementById('customAlertOkBtn');
  if (okBtn && modal) {
    okBtn.addEventListener('click', () => modal.classList.remove('active'));
  }
}

// Custom Confirm Modal Helper (Replaces native browser confirm popup)
function showCustomConfirm(title, message, confirmBtnText = 'Ya, Hapus', icon = '🗑️', onConfirm = null) {
  const modal = document.getElementById('customConfirmModal');
  if (!modal) return;

  document.getElementById('customConfirmTitle').textContent = title;
  document.getElementById('customConfirmMsg').textContent = message;
  document.getElementById('customConfirmIcon').textContent = icon;

  const actionBtn = document.getElementById('customConfirmActionBtn');
  const cancelBtn = document.getElementById('customConfirmCancelBtn');
  actionBtn.textContent = confirmBtnText;

  modal.classList.add('active');

  const cleanup = () => {
    modal.classList.remove('active');
    actionBtn.onclick = null;
    cancelBtn.onclick = null;
  };

  actionBtn.onclick = () => {
    cleanup();
    if (typeof onConfirm === 'function') onConfirm();
  };

  cancelBtn.onclick = () => {
    cleanup();
  };
}

// Custom Prompt Modal Helper (Replaces native browser prompt popup)
function showCustomPrompt(title, label, defaultValue = '', onSave = null) {
  const modal = document.getElementById('customPromptModal');
  if (!modal) return;

  document.getElementById('customPromptTitle').textContent = title;
  document.getElementById('customPromptLabel').textContent = label;
  const inputEl = document.getElementById('customPromptInput');
  inputEl.value = defaultValue;

  modal.classList.add('active');
  setTimeout(() => inputEl.focus(), 100);

  const saveBtn = document.getElementById('customPromptSaveBtn');
  const cancelBtn = document.getElementById('customPromptCancelBtn');

  const cleanup = () => {
    modal.classList.remove('active');
    saveBtn.onclick = null;
    cancelBtn.onclick = null;
  };

  saveBtn.onclick = () => {
    const val = inputEl.value.trim();
    cleanup();
    if (val && typeof onSave === 'function') onSave(val);
  };

  cancelBtn.onclick = () => {
    cleanup();
  };
}

// Cute AI Loading Overlay Helper
function showCuteAiLoading(title = '🤖 Gemini AI Memuat Ide...', message = 'Sedang meracik alur cerita sinematik...') {
  const modal = document.getElementById('aiCuteLoadingModal');
  const titleEl = document.getElementById('aiCuteLoadingTitle');
  const msgEl = document.getElementById('aiCuteLoadingMsg');

  if (titleEl) titleEl.textContent = title;
  if (msgEl) msgEl.textContent = message;
  if (modal) modal.classList.add('active');
}

function hideCuteAiLoading() {
  const modal = document.getElementById('aiCuteLoadingModal');
  if (modal) modal.classList.remove('active');
}

function seoStorageKey(jobId) {
  return `sinematica_seo_kit_${jobId}`;
}

function bindSeoCopyActions(body, kit) {
  body.querySelector('#btnCopyDescription')?.addEventListener('click', () => {
    navigator.clipboard.writeText(kit.description || '');
    showToast('Deskripsi YouTube berhasil di-copy!', 'success');
  });
  body.querySelectorAll('.btn-copy-seo-title').forEach(btn => {
    // Upgrade cached SEO HTML that still contains the old clipboard emoji.
    btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path></svg>';
    btn.addEventListener('click', () => {
      const title = (kit.seo_titles || [])[Number(btn.getAttribute('data-index'))] || '';
      navigator.clipboard.writeText(title);
      showToast('Judul SEO berhasil di-copy!', 'success');
    });
  });
  body.querySelector('#btnCopyThumbPrompt')?.addEventListener('click', () => {
    navigator.clipboard.writeText(kit.thumbnail_prompt || '');
    showToast('Prompt thumbnail berhasil di-copy!', 'success');
  });
  body.querySelector('#btnCopyTags')?.addEventListener('click', () => {
    navigator.clipboard.writeText(kit.tags_csv || '');
    showToast('10 Tags kata kunci berhasil di-copy!', 'success');
  });
}

function initSeoKitModal() {
  const modal = document.getElementById('seoKitModal');
  const closeBtn = document.getElementById('closeSeoModalBtn');

  if (closeBtn && modal) {
    closeBtn.addEventListener('click', () => modal.classList.remove('active'));
  }

  document.addEventListener('click', async (e) => {
    if (e.target && (e.target.classList.contains('btn-generate-seo') || e.target.classList.contains('btn-regenerate-seo'))) {
      const filmTitle = e.target.getAttribute('data-title') || 'Film Sinematik';
      const jobId = e.target.getAttribute('data-jobid') || '';
      const body = document.getElementById('seoModalBody');
      modal.classList.add('active');

      body.innerHTML = `
        <div class="seo-loading-state">
          <div class="seo-loader-orbit" aria-hidden="true">
            <span class="seo-loader-wand">🪄</span>
          </div>
          <h4>Meracik YouTube SEO & Marketing Kit<span class="seo-loading-dots"></span></h4>
          <p id="seoLoadingStatus">AI sedang membaca judul dan premis film</p>
          <div class="seo-loading-track"><span></span></div>
          <small id="seoLoadingElapsed">Berjalan 0 detik</small>
        </div>
      `;

      const loadingStartedAt = Date.now();
      const loadingMessages = [
        'AI sedang membaca judul dan premis film',
        'Menganalisis kata kunci dan daya tarik penonton',
        'Merancang judul, deskripsi, thumbnail, dan tags',
        'Merapikan hasil SEO agar siap disalin'
      ];
      let loadingStep = 0;
      const loadingTimer = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - loadingStartedAt) / 1000);
        const elapsedEl = document.getElementById('seoLoadingElapsed');
        const statusEl = document.getElementById('seoLoadingStatus');
        if (elapsedEl) elapsedEl.textContent = `Berjalan ${elapsed} detik`;
        if (statusEl && elapsed > 0 && elapsed % 4 === 0) {
          loadingStep = (loadingStep + 1) % loadingMessages.length;
          statusEl.textContent = loadingMessages[loadingStep];
        }
      }, 1000);

      try {
        const res = await fetch('/api/storyboard/seo_kit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: filmTitle,
            premise: currentStoryboard ? currentStoryboard.genre_style : filmTitle
          })
        });

        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail;
          const message = Array.isArray(detail)
            ? detail.map(item => item.msg || JSON.stringify(item)).join('; ')
            : (typeof detail === 'object' && detail !== null ? JSON.stringify(detail) : detail);
          throw new Error(message || 'Gagal generate SEO kit');
        }

        const rawKit = data.seo_kit || {};
        const kit = {
          ...rawKit,
          seo_titles: rawKit.seo_titles || rawKit.titles || [],
          tags_csv: rawKit.tags_csv || rawKit.tags || ''
        };

        window.clearInterval(loadingTimer);

        body.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <h4 style="color: var(--neon-cyan); font-size: 14px; margin-bottom: 8px;">🎯 3 Pilihan Judul YouTube SEO Natural:</h4>
              <ol style="margin: 0; padding-left: 20px; font-size: 13px; color: var(--text-primary); line-height: 1.6;">
                ${(kit.seo_titles || []).map((t, index) => `
                  <li class="seo-title-row">
                    <span><b>${escapeHtml(t)}</b> <span style="font-size: 11px; color: var(--text-muted);">(${t.length} kar)</span></span>
                    <button type="button" class="btn-copy-seo-title" data-index="${index}" title="Salin judul ${index + 1}" aria-label="Salin judul ${index + 1}">
                      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path></svg>
                    </button>
                  </li>
                `).join('')}
              </ol>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <h4 style="color: var(--neon-cyan); font-size: 14px; margin: 0;">📝 Deskripsi Video (3 Paragraf + CTA & Hashtags):</h4>
                <button type="button" class="btn-secondary" id="btnCopyDescription" style="padding: 3px 8px; font-size: 11px;">📋 Copy Deskripsi</button>
              </div>
              <textarea id="seoDescriptionText" readonly style="width: 100%; height: 120px; background: rgba(0,0,0,0.5); border: 1px solid var(--glass-border); color: var(--text-secondary); border-radius: 6px; padding: 8px; font-size: 12px;">${kit.description || ''}</textarea>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <h4 style="color: var(--neon-cyan); font-size: 14px; margin: 0;">🖼️ Prompt Thumbnail YouTube 16:9:</h4>
                <button type="button" class="btn-secondary" id="btnCopyThumbPrompt" style="padding: 3px 8px; font-size: 11px;">📋 Copy Prompt</button>
              </div>
              <p style="font-size: 12px; color: var(--text-primary); background: rgba(0,0,0,0.5); padding: 8px; border-radius: 6px; margin: 0;" id="seoThumbText">${kit.thumbnail_prompt || '-'}</p>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <h4 style="color: var(--neon-cyan); font-size: 14px; margin: 0;">🏷️ 10 Long-Tail Tags (Siap Copy Pisah Koma):</h4>
                <button type="button" class="btn-primary" id="btnCopyTags" style="padding: 3px 10px; font-size: 11px;">📋 Copy All 10 Tags</button>
              </div>
              <input type="text" readonly id="seoTagsText" value="${kit.tags_csv || ''}" style="width: 100%; background: rgba(0,0,0,0.5); border: 1px solid var(--glass-border); color: var(--neon-green); border-radius: 6px; padding: 8px; font-size: 12px;" />
            </div>
          </div>
        `;

        bindSeoCopyActions(body, kit);
        if (jobId) {
          localStorage.setItem(seoStorageKey(jobId), JSON.stringify({ kit, html: body.innerHTML }));
          refreshGallery();
        }

      } catch (err) {
        window.clearInterval(loadingTimer);
        body.innerHTML = `<div style="color: #f43f5e; padding: 20px; text-align: center;">Gagal generate SEO kit: ${err.message}</div>`;
      }
    }

    if (e.target && e.target.classList.contains('btn-view-seo')) {
      const jobId = e.target.getAttribute('data-jobid') || '';
      const saved = JSON.parse(localStorage.getItem(seoStorageKey(jobId)) || 'null');
      if (!saved?.kit || !saved?.html) return;
      const body = document.getElementById('seoModalBody');
      body.innerHTML = saved.html;
      modal.classList.add('active');
      bindSeoCopyActions(body, saved.kit);
    }
  });
}

function saveStoryboardToHistory(sb) {
  if (!sb) return;
  try {
    localStorage.setItem('sinematica_last_storyboard', JSON.stringify(sb));

    let history = JSON.parse(localStorage.getItem('sinematica_storyboard_history') || '[]');
    sb._timestamp = new Date().toLocaleString('id-ID');
    history = history.filter(h => h.film_title !== sb.film_title);
    history.unshift(sb);
    if (history.length > 20) history = history.slice(0, 20);
    localStorage.setItem('sinematica_storyboard_history', JSON.stringify(history));
  } catch (err) {
    console.warn('Gagal menyimpan storyboard ke history:', err);
  }
}

function loadLastStoryboard() {
  try {
    const saved = localStorage.getItem('sinematica_last_storyboard');
    if (saved) {
      currentStoryboard = JSON.parse(saved);
      renderStoryboardResult(currentStoryboard);
      const btnSend = document.getElementById('btnSendToExecution');
      if (btnSend) btnSend.disabled = false;
      console.log('Restored last storyboard from localStorage!');
    }
  } catch (err) {
    console.warn('Gagal memuat storyboard terakhir:', err);
  }
}

function initStoryboardHistoryModal() {
  const modal = document.getElementById('storyboardHistoryModal');
  const openBtn = document.getElementById('btnOpenHistoryModalBtn');
  const closeBtn = document.getElementById('closeHistoryModalBtn');

  if (closeBtn && modal) {
    closeBtn.addEventListener('click', () => modal.classList.remove('active'));
  }

  if (openBtn) {
    openBtn.addEventListener('click', () => {
      const navItem = document.querySelector('.nav-item[data-tab="tab-history"]');
      if (navItem) navItem.click();
    });
  }
}

function renderHistoryTab() {
  const container = document.getElementById('historyTabBody');
  if (!container) return;

  let history = [];
  try {
    history = JSON.parse(localStorage.getItem('sinematica_storyboard_history') || '[]');
  } catch (_) {}

  if (history.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="padding: 60px 20px;">
        <div class="empty-icon" style="font-size: 48px; margin-bottom: 12px;">📜</div>
        <h4 style="color: #ffffff; font-size: 18px; margin-bottom: 6px;">Belum Ada Riwayat Storyboard Tersimpan</h4>
        <p style="color: var(--text-muted); font-size: 13px; max-width: 360px; margin: 0 auto;">Rancang storyboard baru di tab AI Storyboard untuk otomatis menyimpannya ke koleksi Scene Master studio ini.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 24px;">
      ${history.map((item, idx) => `
        <div class="history-item-card" style="position: relative; background: linear-gradient(145deg, rgba(12, 18, 36, 0.85), rgba(20, 29, 54, 0.75)); border: 1px solid rgba(56, 189, 248, 0.25); padding: 24px; border-radius: 18px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35); display: flex; flex-direction: column; justify-content: space-between; transition: all 0.3s ease; height: 100%;">
          
          <!-- Floating Top-Right Delete X Icon Button -->
          <button type="button" class="btn-delete-history-tab-item" data-index="${idx}" title="Hapus dari Riwayat" style="position: absolute; top: 16px; right: 16px; width: 30px; height: 30px; border-radius: 50%; background: rgba(244, 63, 94, 0.15); border: 1px solid rgba(244, 63, 94, 0.4); color: #f43f5e; font-size: 13px; font-weight: 800; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
            ✕
          </button>

          <div>
            <!-- Header: Title & Badges -->
            <div style="margin-bottom: 14px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 12px; padding-right: 36px;">
              <h4 style="color: #ffffff; font-size: 17px; font-weight: 800; margin: 0 0 8px 0; font-family: var(--font-heading); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.film_title || 'Film Sinematik')}">🎬 ${escapeHtml(item.film_title || 'Film Sinematik')}</h4>
              
              <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <span style="font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8;">${item.aspect_ratio === 'portrait' ? '📱 Short 9:16' : '🖥️ Landscape 16:9'}</span>
                <span style="font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc;">🎬 ${(item.scenes || []).length} Scene (${(item.scenes || []).length * 10}s)</span>
                <span style="font-size: 11px; color: var(--text-muted); padding: 4px 10px; border-radius: 20px; background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.1);">📅 ${item._timestamp || 'Tersimpan'}</span>
              </div>
            </div>

            <!-- Clamped Character Description Box -->
            <div style="background: rgba(4, 7, 16, 0.6); padding: 12px 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 18px;">
              <span style="font-size: 11px; font-weight: 800; color: var(--neon-cyan); display: block; margin-bottom: 4px;">👤 KARAKTER & SEEDS:</span>
              <p style="font-size: 12px; color: var(--text-secondary); margin: 0; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(item.consistent_characters || '-')}">
                ${escapeHtml(item.consistent_characters || 'Deskripsi karakter otomatis oleh AI...')}
              </p>
              <small style="display: block; font-size: 11px; color: #34d399; margin-top: 6px; font-weight: 700;">🌱 Seed Karakter: ${item.character_seed || 'Auto'}</small>
            </div>
          </div>

          <!-- Footer Actions Row: 100% Full Width Open Button -->
          <div style="margin-top: auto; border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 14px;">
            <button type="button" class="btn-primary load-history-tab-btn" data-index="${idx}" style="width: 100%; padding: 12px; font-size: 14px; border-radius: 12px; font-weight: 800; background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(168, 85, 247, 0.25)); border: 1px solid var(--neon-cyan); color: #ffffff; cursor: pointer; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.25); transition: all 0.3s; display: flex; align-items: center; justify-content: center; gap: 8px;">
              <span>📂</span> Buka & Eksekusi di Studio
            </button>
          </div>
        </div>
      `).join('')}
    </div>
  `;

  container.querySelectorAll('.btn-delete-history-tab-item').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.getAttribute('data-index'));
      showCustomConfirm(
        'Hapus Riwayat Storyboard',
        'Apakah Anda yakin ingin menghapus storyboard ini dari riwayat tersimpan?',
        'Ya, Hapus',
        '🗑️',
        () => {
          try {
            let h = JSON.parse(localStorage.getItem('sinematica_storyboard_history') || '[]');
            h.splice(idx, 1);
            localStorage.setItem('sinematica_storyboard_history', JSON.stringify(h));
            showToast('Item berhasil dihapus dari riwayat!', 'success');
            renderHistoryTab();
          } catch (err) {
            showToast('Gagal menghapus riwayat: ' + err.message, 'error');
          }
        }
      );
    });
  });

  container.querySelectorAll('.load-history-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const index = parseInt(btn.getAttribute('data-index'));
      const selectedSb = history[index];
      if (selectedSb) {
        currentStoryboard = selectedSb;
        localStorage.setItem('sinematica_last_storyboard', JSON.stringify(selectedSb));
        renderStoryboardResult(selectedSb);
        showToast(`Storyboard "${selectedSb.film_title || 'Film'}" dimuat ke Studio!`, 'success');
        document.querySelector('.nav-item[data-tab="tab-storyboard"]').click();
      }
    });
  });
}

function initFleetTestPrompt() {
  const testBtn = document.getElementById('testSeedPromptBtn');
  const refreshBtn = document.getElementById('refreshFleetBtn');

  const checkCreditsBtn = document.getElementById('checkCreditsFleetBtn');
  if (refreshBtn) refreshBtn.addEventListener('click', fetchFleetStatus);
  if (checkCreditsBtn) checkCreditsBtn.addEventListener('click', fetchFleetCredits);

  if (testBtn) {
    testBtn.addEventListener('click', () => {
      showCustomPrompt(
        'Tes Prompt Seed Karakter ke Google Flow',
        'Ketikkan prompt gambar seed karakter yang ingin dikirim ke Flow:',
        'A handsome wise scholar character portrait, cinematic lighting, 8k',
        async (userPrompt) => {
          testBtn.disabled = true;
          testBtn.textContent = '⏳ Mengirim Prompt ke Flow...';
          showToast('Mengirim request gambar seed ke Google Flow...', 'info', 'Google Flow Bridge');

          try {
            const res = await fetch('/api/fleet/test_prompt', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ prompt: userPrompt })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Gagal generate gambar');

            showCustomAlert(
              `✨ Status: ${data.message}\n\nProfil: ${data.profile_used}\nSeed: ${data.seed_used}\nURL Hasil: ${data.seed_image_url || 'Sukses!'}`,
              '🎉 Hasil Tes Google Flow Extension',
              '🎨'
            );
            showToast('Prompt seed karakter berhasil dikirim & diproses di Google Flow!', 'success');
          } catch (err) {
            showCustomAlert(err.message, 'Gagal Tes Google Flow', '❌');
          } finally {
            testBtn.disabled = false;
            testBtn.textContent = '🧪 Tes Kirim Prompt Seed Karakter ke Flow';
          }
        }
      );
    });
  }
}

// Navigation Tab Switching
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const pages = document.querySelectorAll('.tab-page');
  const pageTitle = document.getElementById('pageTitle');
  const pageSubtitle = document.getElementById('pageSubtitle');

  const pageMeta = {
    'tab-fleet': {
      title: 'Chrome Multi-Account Fleet Manager',
      sub: 'Kelola dan pantau status koneksi extension akun Google Flow di Chrome'
    },
    'tab-storyboard': {
      title: 'Gemini 3.6 Flash Storyboard Studio',
      sub: 'Susun alur adegan dan prompt konsistensi karakter dari gambar referensi'
    },
    'tab-history': {
      title: 'Scene Master Studio',
      sub: 'Kelola, tinjau, muat kembali, atau hapus seluruh storyboard adegan tersimpan'
    },
    'tab-execution': {
      title: 'Live Multi-Flow Video Execution Terminal',
      sub: 'Pantau proses render adegan video secara otomatis di Google Flow'
    },
    'tab-gallery': {
      title: 'Interactive Video Gallery & Film Director',
      sub: 'Kelola adegan video, atur urutan cerita, dan gabungkan menjadi film sinematik utuh'
    },
    'tab-settings': {
      title: 'Sinematica Studio Settings',
      sub: 'Kelola Gemini API Key, model AI engine, Google Flow Project ID, dan template seed'
    }
  };

  document.addEventListener('click', (e) => {
    const navBtn = e.target.closest('.nav-item');
    if (!navBtn) return;

    const targetId = navBtn.getAttribute('data-tab');
    if (!targetId) return;

    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));

    navBtn.classList.add('active');
    const targetPage = document.getElementById(targetId);
    if (targetPage) targetPage.classList.add('active');

    if (pageMeta[targetId]) {
      if (pageTitle) pageTitle.textContent = pageMeta[targetId].title;
      if (pageSubtitle) pageSubtitle.textContent = pageMeta[targetId].sub;
    }

    if (targetId === 'tab-fleet') fetchFleetStatus();
    if (targetId === 'tab-history') renderHistoryTab();
    if (targetId === 'tab-gallery') refreshGallery();
    if (targetId === 'tab-settings') loadSettingsTab();
  });
}

// Status & Fleet Polling
function initStatusPolling() {
  fetchFleetStatus();
  setInterval(fetchFleetStatus, 5000);
}

let fleetCreditsMap = {};

async function fetchFleetCredits() {
  const checkBtn = document.getElementById('checkCreditsFleetBtn');
  if (checkBtn) {
    checkBtn.disabled = true;
    checkBtn.innerHTML = '⌛ Memeriksa Kuota...';
  }
  try {
    const res = await fetch('/api/fleet_credits');
    if (res.ok) {
      const data = await res.json();
      fleetCreditsMap = data.credits || {};
      fetchFleetStatus();
    }
  } catch (err) {
    console.warn('Gagal mengambil credits fleet:', err);
  } finally {
    if (checkBtn) {
      checkBtn.disabled = false;
      checkBtn.innerHTML = '⚡ Cek Sisa Kuota Flow';
    }
  }
}

async function fetchFleetStatus() {
  try {
    const res = await fetch('/api/fleet');
    if (!res.ok) throw new Error('Backend Offline');
    const data = await res.json();

    const serverPill = document.getElementById('serverPill');
    const fleetPill = document.getElementById('fleetPill');
    const fleetCountBadge = document.getElementById('fleetCountBadge');
    const fleetGrid = document.getElementById('fleetGrid');

    const currentPort = window.location.port || '8888';
    serverPill.innerHTML = `<span class="dot green"></span> Backend: Online (${currentPort})`;

    const profiles = data.profiles || [];
    const readyProfiles = profiles.filter(p => p.connected && p.logged_in && p.ready !== false);

    fleetCountBadge.textContent = readyProfiles.length;
    fleetPill.innerHTML = `<span class="dot ${readyProfiles.length > 0 ? 'green' : 'red'}"></span> Fleet: ${readyProfiles.length} Profile Ready`;

    if (profiles.length === 0) {
      fleetGrid.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔌</div>
          <h4>Belum Ada Profil Chrome Terhubung</h4>
          <p>Muat unpacked extension <code>engine/chrome-extension</code> di Chrome (chrome://extensions) dan login di labs.google/fx/tools/flow</p>
        </div>
      `;
      return;
    }

    fleetGrid.innerHTML = profiles.map(p => {
      const credData = fleetCreditsMap[p.instance_id];
      const isReady = p.connected && p.logged_in && p.ready !== false;
      let credText = isReady ? '⚡ Unlimited' : (p.readiness_error || 'Belum Siap');
      let credBadgeColor = isReady ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.1)';
      let credBorder = isReady ? 'rgba(16, 185, 129, 0.4)' : 'rgba(244, 63, 94, 0.3)';
      let credTextColor = isReady ? '#34d399' : '#f43f5e';

      if (credData) {
        if (credData.success) {
          credText = `⚡ ${credData.credits}`;
          credTextColor = '#34d399';
          credBadgeColor = 'rgba(16, 185, 129, 0.12)';
          credBorder = 'rgba(16, 185, 129, 0.4)';
        } else {
          credText = credData.credits || 'Gagal Cek Kuota';
          credTextColor = '#f43f5e';
          credBadgeColor = 'rgba(244, 63, 94, 0.1)';
          credBorder = 'rgba(244, 63, 94, 0.3)';
        }
      }

      return `
        <div class="profile-card" style="position: relative; background: rgba(12, 18, 36, 0.85); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; padding: 18px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;">
          <div class="profile-header" style="display: flex; justify-content: space-between; align-items: center;">
            <span class="profile-title" style="font-weight: 800; font-size: 15px; color: #ffffff;">💻 ${p.name || p.instance_id}</span>
            <span class="badge-status ${isReady ? 'badge-ready' : 'badge-noauth'}">
              ${isReady ? 'Ready & Logged In' : (p.readiness_error || 'Need Flow Window/Login')}
            </span>
          </div>
          <div style="font-size: 12px; color: var(--text-muted); display: flex; flex-direction: column; gap: 4px;">
            <p style="margin:0;">Instance ID: <code style="color: var(--neon-cyan);">${p.instance_id}</code></p>
            <p style="margin:0;">Project ID: <code style="color: var(--text-secondary);">${p.project_id || 'Auto-detect'}</code></p>
          </div>
          <div style="background: ${credBadgeColor}; border: 1px solid ${credBorder}; border-radius: 10px; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
            <span style="font-size: 12px; font-weight: 700; color: #ffffff;">💳 Sisa Kuota Flow:</span>
            <span style="font-size: 13px; font-weight: 800; color: ${credTextColor};" id="cred-${p.instance_id}">${credText}</span>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    document.getElementById('serverPill').innerHTML = '<span class="dot red"></span> Backend: Offline';
    document.getElementById('fleetPill').innerHTML = '<span class="dot red"></span> Fleet: Offline';
  }
}

// Reference Image Dropzone
function initDropzone() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('refImageInput');

  dropzone.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', (e) => {
    selectedRefFiles = Array.from(e.target.files);
    renderImagePreviews();
  });

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = 'var(--accent-cyan)';
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = 'var(--glass-border)';
    if (e.dataTransfer.files.length) {
      selectedRefFiles = Array.from(e.dataTransfer.files);
      renderImagePreviews();
    }
  });
}

function renderImagePreviews() {
  const list = document.getElementById('refImageList');
  list.innerHTML = '';

  selectedRefFiles.forEach(file => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = document.createElement('img');
      img.src = e.target.result;
      img.className = 'img-thumb';
      list.appendChild(img);
    };
    reader.readAsDataURL(file);
  });
}

// Gemini Storyboard Form
function initStoryboardForm() {
  const form = document.getElementById('storyboardForm');
  const btnSend = document.getElementById('btnSendToExecution');

  // Microdrama & UGC Lifestyle are alternate style presets — keep them mutually exclusive
  const chkMicro = document.getElementById('chkMicrodramaMode');
  const chkUgc = document.getElementById('chkUgcMode');
  const chkChildren = document.getElementById('chkChildrenMode');
  const chkScript = document.getElementById('chkScriptMode');
  const modeBoxes = [chkMicro, chkUgc, chkChildren].filter(Boolean);
  modeBoxes.forEach(box => {
    box.addEventListener('change', () => {
      // The three story modes carry conflicting rule sets, so only one may be active.
      if (box.checked) modeBoxes.forEach(other => { if (other !== box) other.checked = false; });
    });
  });

  if (chkScript) {
    chkScript.addEventListener('change', () => {
      const label = document.getElementById('premiseInputLabel');
      const input = document.getElementById('premiseInput');
      const hint = document.getElementById('scriptModeHint');
      const autoButton = document.getElementById('autoSuggestBtn');
      if (chkScript.checked) {
        if (label) label.textContent = '📄 Script Lengkap (alur & dialog tidak diubah):';
        if (input) {
          input.rows = 14;
          input.placeholder = 'Tempel script lengkap di sini: episode, lokasi, aksi, karakter, dan dialog...';
        }
        if (hint) hint.style.display = 'block';
        if (autoButton) autoButton.disabled = true;
        const submit = document.getElementById('generateStoryboardBtn');
        if (submit) submit.innerHTML = '📄 Format Script & Buat Storyboard Render';
      } else {
        if (label) label.textContent = '📝 Tema Singkat / Ide Utama Film (Bahasa Indonesia):';
        if (input) {
          input.rows = 5;
          input.placeholder = 'Ketik tema singkat di sini (contoh: Kisah petualangan pendekar wanita di kota cyberpunk berhujan neon)...';
        }
        if (hint) hint.style.display = 'none';
        if (autoButton) autoButton.disabled = false;
        const submit = document.getElementById('generateStoryboardBtn');
        if (submit) submit.innerHTML = '✨ Generate AI Storyboard (Gemini 3.6 Flash)';
      }
    });
  }

  const presetSelect = document.getElementById('durationPresetSelect');
  const sceneInput = document.getElementById('sceneCountInput');
  const durationSelect = document.getElementById('durationPerSceneSelect');
  const totalLabel = document.getElementById('totalDurationLabel');

  function updateTotalDuration() {
    const scenes = parseInt(sceneInput.value) || 1;
    const isAuto = durationSelect.value === 'auto';
    // In Auto mode each scene picks its own 4/6/8/10s, so only a range can be shown.
    const dur = isAuto ? 7 : (parseInt(durationSelect.value) || 10);
    const fmt = (t) => {
      const m = Math.floor(t / 60), sc = t % 60;
      return m > 0 ? `${m} Menit ${sc > 0 ? sc + ' Detik' : ''}`.trim() : `${t} Detik`;
    };
    if (isAuto) {
      totalLabel.textContent = `Estimasi Durasi Film: ${fmt(scenes * 4)} – ${fmt(scenes * 10)} (${scenes} Scene, ritme diatur AI per adegan)`;
    } else {
      totalLabel.textContent = `Total Durasi Film: ${fmt(scenes * dur)} (${scenes} Scene x ${dur}s)`;
    }
  }

  if (presetSelect) {
    presetSelect.addEventListener('change', () => {
      const val = presetSelect.value;
      if (val !== 'custom') {
        const totalSecs = parseInt(val);
        const dur = durationSelect.value === 'auto' ? 7 : (parseInt(durationSelect.value) || 10);
        const scenes = Math.round(totalSecs / dur);
        sceneInput.value = scenes > 0 ? scenes : 1;
        updateTotalDuration();
      }
    });
  }

  if (sceneInput) sceneInput.addEventListener('input', updateTotalDuration);
  if (durationSelect) durationSelect.addEventListener('change', updateTotalDuration);
  updateTotalDuration();

  const genreCatalog = document.getElementById('genreCatalogSelect');
  const btnRandomGenre = document.getElementById('btnRandomGenrePreset');

  if (genreCatalog) {
    genreCatalog.addEventListener('change', () => {
      const val = genreCatalog.value;
      if (val) {
        const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
        if (premiseInput) {
          premiseInput.value = val;

          const selectedOpt = genreCatalog.options[genreCatalog.selectedIndex];
          const isUgcPreset = selectedOpt && selectedOpt.getAttribute('data-ugc') === 'true';
          const isMicroPreset = selectedOpt && selectedOpt.getAttribute('data-micro') === 'true';
          const isChildrenPreset = selectedOpt && selectedOpt.getAttribute('data-children') === 'true';
          const chkChildrenEl = document.getElementById('chkChildrenMode');
          if (chkChildrenEl) chkChildrenEl.checked = !!isChildrenPreset;
          const chkUgc = document.getElementById('chkUgcMode');
          const chkMicro = document.getElementById('chkMicrodramaMode');
          if (chkUgc) {
            chkUgc.checked = !!isUgcPreset && !isChildrenPreset;
            if (isUgcPreset && chkMicro) chkMicro.checked = false;
          }
          if (isChildrenPreset && chkMicro) chkMicro.checked = false;
          if (chkMicro && isMicroPreset && !isChildrenPreset) {
            chkMicro.checked = true;
            if (chkUgc) chkUgc.checked = false;
          }

          showToast('Preset tema dipilih! Meracik konsep AI...', 'info');
          const autoBtn = document.getElementById('autoSuggestBtn') || document.getElementById('btnAutoSuggestConcept');
          if (autoBtn) autoBtn.click();
        }
      }
    });
  }

  if (btnRandomGenre) {
    btnRandomGenre.addEventListener('click', () => {
      if (genreCatalog) {
        const options = Array.from(genreCatalog.querySelectorAll('option')).filter(o => o.value);
        if (options.length) {
          const randomOpt = options[Math.floor(Math.random() * options.length)];
          genreCatalog.value = randomOpt.value;
          genreCatalog.dispatchEvent(new Event('change'));
        }
      }
    });
  }

  const autoSuggestBtn = document.getElementById('autoSuggestBtn') || document.getElementById('btnAutoSuggestConcept');
  if (autoSuggestBtn) {
    autoSuggestBtn.addEventListener('click', async () => {
      const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
      const currentText = premiseInput ? premiseInput.value.trim() : '';

      autoSuggestBtn.disabled = true;
      autoSuggestBtn.textContent = '🪄 Memuat Ide AI...';

      const isMicrodrama = document.getElementById('chkMicrodramaMode') ? document.getElementById('chkMicrodramaMode').checked : false;

      try {
        showCuteAiLoading(
          isMicrodrama ? '📱 Gemini AI Meracik Microdrama...' : '🤖 Gemini AI Memuat Ide...',
          isMicrodrama ? 'Sedang merancang formula 3-episode Microdrama / Dracin (Hook, Conflict, & Payoff)...' : 'Sedang meracik alur cerita sinematik super dramatis & konsistensi karakter...'
        );

        const targetCountryEl = document.getElementById('targetCountryInput');
        const targetCountry = targetCountryEl ? targetCountryEl.value.trim() : '';
        const dracinThemeEl = document.getElementById('dracinThemeSelect');
        const dracinTheme = dracinThemeEl ? dracinThemeEl.value : '';

        let res, data;
        if (currentText) {
          res = await fetch('/api/storyboard/suggest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: currentText, microdrama_mode: isMicrodrama, target_country: targetCountry, dracin_theme: dracinTheme })
          });
        } else {
          res = await fetch(`/api/storyboard/auto_concept?microdrama_mode=${isMicrodrama}&target_country=${encodeURIComponent(targetCountry)}&dracin_theme=${encodeURIComponent(dracinTheme)}`);
        }

        data = await res.json();
        const suggested = data.concept || (data.suggestion && data.suggestion.suggested_premise);

        if (suggested && premiseInput) {
          premiseInput.value = suggested;
          showToast('Ide konsep sinematik berhasil dimuat dengan Gemini AI!', 'success');
        }

        if (data.suggestion) {
          const seedInput = document.getElementById('characterSeedInput') || document.getElementById('characterSeed');
          if (seedInput && data.suggestion.character_seed) seedInput.value = data.suggestion.character_seed;

          const charText = data.suggestion.suggested_character || data.suggestion.character_info || data.suggestion.suggested_characters;
          const charInput = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
          if (charInput && charText) charInput.value = charText;
        }

      } catch (err) {
        showToast('Gagal memuat ide konsep: ' + err.message, 'error');
      } finally {
        hideCuteAiLoading();
        autoSuggestBtn.disabled = false;
        autoSuggestBtn.textContent = '🪄 Auto Concept AI';
      }
    });
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
    const theme = premiseInput ? premiseInput.value.trim() : '';

    const sceneCount = sceneInput ? (parseInt(sceneInput.value) || 4) : 4;

    const aspectSelect = document.getElementById('aspectSelect') || document.getElementById('aspectRatioSelect') || document.getElementById('settingAspectRatio');
    const aspectRatio = aspectSelect ? aspectSelect.value : 'landscape';

    const seedEl = document.getElementById('characterSeedInput') || document.getElementById('characterSeed');
    const seed = seedEl ? seedEl.value.trim() : '';

    const charEl = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
    const consistentChar = charEl ? charEl.value.trim() : '';

    if (!theme) {
      showToast('Harap isi Tema / Ide Utama Film!', 'warning');
      return;
    }

    const isMicro = document.getElementById('chkMicrodramaMode') ? document.getElementById('chkMicrodramaMode').checked : false;
    const isUgc = document.getElementById('chkUgcMode') ? document.getElementById('chkUgcMode').checked : false;
    const isChildren = document.getElementById('chkChildrenMode') ? document.getElementById('chkChildrenMode').checked : false;
    const isScriptMode = chkScript ? chkScript.checked : false;

    const targetCountryEl = document.getElementById('targetCountryInput');
    const targetCountry = targetCountryEl ? targetCountryEl.value.trim() : '';

    const dracinThemeEl = document.getElementById('dracinThemeSelect');
    const dracinTheme = dracinThemeEl ? dracinThemeEl.value : '';

    const durModeEl = document.getElementById('durationPerSceneSelect');
    const durMode = durModeEl ? durModeEl.value : '10';

    const actorCheckboxes = document.querySelectorAll('#actorSelectionList_storyboard input[type="checkbox"]:checked');
    const actorIds = Array.from(actorCheckboxes).map(cb => cb.value).join(',');

    const formData = new FormData();
    formData.append('actor_ids', actorIds);
    formData.append('premise', theme);
    formData.append('scene_count', sceneCount);
    formData.append('aspect_ratio', aspectRatio);
    formData.append('microdrama_mode', isMicro);
    formData.append('ugc_mode', isUgc);
    formData.append('children_mode', isChildren);
    formData.append('script_mode', isScriptMode);
    if (seed) formData.append('character_seed', seed);
    if (consistentChar) formData.append('character_info', consistentChar);
    if (targetCountry) formData.append('target_country', targetCountry);
    if (dracinTheme) formData.append('dracin_theme', dracinTheme);
    // Tell the storyboard writer which pacing the user picked, so scene durations
    // match what will actually be rendered instead of drifting.
    if (durMode === 'auto') {
      formData.append('target_total_duration', String(sceneCount * 7));
    } else {
      formData.append('fixed_scene_duration', durMode);
    }

    selectedRefFiles.forEach(f => formData.append('reference_images', f));

    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.innerHTML = isScriptMode
      ? '⚙️ Memformat Script Tanpa Mengubah Cerita...'
      : '⚡ Generating Storyboard (Gemini 3.6 Flash)...';

    try {
      showCuteAiLoading(
        isScriptMode ? '📄 Memformat Script untuk Render...' : '🎬 Generating Storyboard Sinematik...',
        isScriptMode
          ? `Membagi script menjadi ${sceneCount} adegan teknis tanpa mengubah alur atau dialog...`
          : `Sedang meracik ${sceneCount} adegan dengan multi-angle camera & seed karakter konsisten...`
      );

      showToast('Merancang alur adegan dan prompt sinematik dengan Gemini 3.6 Flash...', 'info', 'Gemini AI Studio');
      const res = await fetch('/api/storyboard/generate', {
        method: 'POST',
        body: formData
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal generate storyboard');

      currentStoryboard = data.storyboard;
      // Remember how this storyboard was made so "Regenerate Storyboard" can reproduce the
      // exact same setup from any tab, without depending on the form still being filled in.
      currentStoryboard.aspect_ratio = aspectRatio;
      currentStoryboard.premise = theme;
      currentStoryboard.scene_count = sceneCount;
      currentStoryboard.character_info = consistentChar;
      currentStoryboard.target_country = targetCountry;
      currentStoryboard.dracin_theme = dracinTheme;
      currentStoryboard.duration_mode = durMode;
      currentStoryboard.microdrama_mode = isMicro;
      currentStoryboard.ugc_mode = isUgc;
      currentStoryboard.children_mode = isChildren;
      currentStoryboard.script_mode = isScriptMode;
      if (data.reference_images && data.reference_images.length) {
        currentStoryboard._theme_image_path = data.reference_images[0];
      }

      saveStoryboardToHistory(currentStoryboard);
      renderStoryboardResult(currentStoryboard);
      if (btnSend) btnSend.disabled = false;
      showToast('AI Storyboard adegan berhasil dibuat! Membuka Scene Master...', 'success');

      const sceneMasterNav = document.querySelector('.nav-item[data-tab="tab-history"]');
      if (sceneMasterNav) sceneMasterNav.click();

    } catch (err) {
      showCustomAlert(err.message, 'Gagal Generate Storyboard', '❌');
    } finally {
      hideCuteAiLoading();
      btn.disabled = false;
      btn.innerHTML = isScriptMode
        ? '📄 Format Script & Buat Storyboard Render'
        : '✨ Generate AI Storyboard (Gemini 3.6 Flash)';
    }
  });

  if (btnSend) {
    btnSend.disabled = false; // Always enabled for user interaction!
    btnSend.addEventListener('click', async () => {
      if (!currentStoryboard) {
        const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
        if (premiseInput && premiseInput.value.trim()) {
          showToast('Merancang Storyboard terlebih dahulu sebelum dikirim ke Flow...', 'info');
          form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
          return;
        } else {
          showToast('Harap masukkan Tema Film terlebih dahulu!', 'warning');
          return;
        }
      }

      const aspectEl = document.getElementById('aspectSelect') || document.getElementById('settingAspectRatio');
      const aspect = (currentStoryboard && currentStoryboard.aspect_ratio) || (aspectEl ? aspectEl.value : 'landscape');
      const durSel = document.getElementById('durationPerSceneSelect').value;
      const isAutoDur = durSel === 'auto';
      const durPerScene = isAutoDur ? 10 : (parseInt(durSel) || 10);

      try {
        showToast('Mendaftarkan Job Eksekusi ke Google Flow...', 'info');
        const res = await fetch('/api/jobs/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            storyboard: currentStoryboard,
            theme_image_path: currentStoryboard._theme_image_path || null,
            aspect_ratio: aspect,
            duration: durPerScene,
            force_uniform_duration: !isAutoDur
          })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Gagal membuat job eksekusi');

        currentJobId = data.job_id;
        showToast(`Job ${currentJobId} didaftarkan! Mengalihkan ke Live Terminal...`, 'success');

        const stopBtn = document.getElementById('btnStopExecution');
        if (stopBtn) stopBtn.style.display = 'block';

        document.querySelector('.nav-item[data-tab="tab-execution"]').click();
        startJobPolling(currentJobId);

      } catch (err) {
        showCustomAlert(err.message, 'Gagal Memulai Eksekusi', '❌');
      }
    });
  }

  const stopExecutionBtn = document.getElementById('btnStopExecution');
  if (stopExecutionBtn) {
    stopExecutionBtn.addEventListener('click', () => {
      if (!currentJobId) return;
      showCustomConfirm(
        'Stop Eksekusi Video',
        'Apakah Anda yakin ingin menghentikan proses render video yang sedang berjalan?',
        '🛑 Stop Sekarang',
        '🛑',
        async () => {
          try {
            const res = await fetch(`/api/jobs/${currentJobId}/cancel`, { method: 'POST' });
            const data = await res.json();
            showToast(data.message || 'Job berhasil dihentikan!', 'warning');
            stopExecutionBtn.style.display = 'none';
            document.getElementById('executionStatusText').textContent = '🛑 Eksekusi dibatalkan oleh pengguna.';
          } catch (err) {
            showToast('Gagal menghentikan job: ' + err.message, 'error');
          }
        }
      );
    });
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

let previewPlaylist = [];
let previewIndex = 0;

function showPreviewAt(i) {
  if (!previewPlaylist.length) return;
  // Wrap around so the last scene leads back to the first instead of dead-ending.
  previewIndex = (i + previewPlaylist.length) % previewPlaylist.length;
  const item = previewPlaylist[previewIndex];
  const overlay = document.getElementById('videoPreviewOverlay');
  if (!overlay || !item) return;

  const many = previewPlaylist.length > 1;
  overlay.querySelector('#videoPreviewTitle').textContent =
    (item.label || 'Preview Adegan') + (many ? `  (${previewIndex + 1}/${previewPlaylist.length})` : '');
  overlay.querySelector('#videoPreviewDownload').href = item.url;
  overlay.querySelector('#videoPreviewPlayer').src = item.url;
  overlay.querySelector('#videoPreviewPrev').style.visibility = many ? 'visible' : 'hidden';
  overlay.querySelector('#videoPreviewNext').style.visibility = many ? 'visible' : 'hidden';
}

function openVideoPreview(url, label, playlist, index) {
  let overlay = document.getElementById('videoPreviewOverlay');

  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'videoPreviewOverlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;display:none;align-items:center;justify-content:center;background:rgba(2,4,10,0.9);backdrop-filter:blur(6px);padding:24px;';
    const navBtn = 'cursor:pointer;flex-shrink:0;user-select:none;width:44px;height:64px;display:flex;align-items:center;justify-content:center;font-size:30px;font-weight:800;color:#fff;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.2);border-radius:12px;transition:background 0.2s;';
    overlay.innerHTML = `
      <div style="position:relative;display:flex;flex-direction:column;gap:10px;max-width:min(92vw,900px);">
        <div style="display:flex;align-items:center;gap:12px;">
          <span id="videoPreviewTitle" style="font-size:14px;font-weight:800;color:var(--neon-cyan);"></span>
          <a id="videoPreviewDownload" download class="btn-secondary" style="margin-left:auto;text-decoration:none;font-size:12px;padding:6px 12px;">⬇️ Download</a>
          <span id="videoPreviewClose" role="button" style="cursor:pointer;font-size:12px;font-weight:800;color:#fff;background:rgba(244,63,94,0.25);border:1px solid rgba(244,63,94,0.5);border-radius:8px;padding:6px 12px;">✕ Tutup</span>
        </div>
        <div style="display:flex;align-items:center;justify-content:center;gap:12px;">
          <span id="videoPreviewPrev" role="button" title="Adegan sebelumnya (←)" style="${navBtn}">‹</span>
          <video id="videoPreviewPlayer" controls autoplay playsinline style="max-width:100%;max-height:78vh;border-radius:12px;background:#000;"></video>
          <span id="videoPreviewNext" role="button" title="Adegan berikutnya (→)" style="${navBtn}">›</span>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    // Stop playback on close so audio does not keep running behind the dashboard.
    const closePreview = () => {
      const player = document.getElementById('videoPreviewPlayer');
      try {
        player.pause();
        player.removeAttribute('src');
        player.load();
      } catch (_) {}
      overlay.style.display = 'none';
    };

    const prevEl = overlay.querySelector('#videoPreviewPrev');
    const nextEl = overlay.querySelector('#videoPreviewNext');
    [prevEl, nextEl].forEach(el => {
      el.addEventListener('mouseenter', () => { el.style.background = 'rgba(56,189,248,0.25)'; });
      el.addEventListener('mouseleave', () => { el.style.background = 'rgba(255,255,255,0.08)'; });
    });
    prevEl.addEventListener('click', (e) => { e.stopPropagation(); showPreviewAt(previewIndex - 1); });
    nextEl.addEventListener('click', (e) => { e.stopPropagation(); showPreviewAt(previewIndex + 1); });

    overlay.addEventListener('click', (e) => { if (e.target === overlay) closePreview(); });
    overlay.querySelector('#videoPreviewClose').addEventListener('click', closePreview);
    document.addEventListener('keydown', (e) => {
      if (overlay.style.display !== 'flex') return;
      if (e.key === 'Escape') closePreview();
      else if (e.key === 'ArrowLeft') showPreviewAt(previewIndex - 1);
      else if (e.key === 'ArrowRight') showPreviewAt(previewIndex + 1);
    });
  }

  previewPlaylist = (Array.isArray(playlist) && playlist.length) ? playlist : [{ url, label }];
  overlay.style.display = 'flex';
  showPreviewAt(typeof index === 'number' && index >= 0 ? index : 0);
}

// Shared cell styling for the per-scene storyboard breakdown table.
const SB_LABEL_CELL = 'display:flex;align-items:flex-start;gap:6px;padding:10px 12px;background:rgba(4,7,16,0.75);border-bottom:1px solid rgba(255,255,255,0.08);border-right:1px solid rgba(255,255,255,0.08);font-size:11px;font-weight:800;letter-spacing:0.4px;color:var(--text-secondary);white-space:nowrap;';
const SB_VALUE_CELL = 'padding:8px 10px;background:rgba(8,12,24,0.4);border-bottom:1px solid rgba(255,255,255,0.08);';
const SB_INPUT = 'width:100%;box-sizing:border-box;background:transparent;border:none;outline:none;font-size:13px;line-height:1.5;padding:2px 0;font-family:inherit;';

function renderStoryboardResult(storyboard) {
  currentStoryboard = storyboard;
  const btnSend = document.getElementById('btnSendToExecution');
  if (btnSend) btnSend.disabled = false;

  // Keep the aspect ratio dropdown in sync with the storyboard actually loaded,
  // so what the user sees matches what gets sent to Flow.
  const aspectSelectEl = document.getElementById('aspectSelect') || document.getElementById('settingAspectRatio');
  if (aspectSelectEl && storyboard && storyboard.aspect_ratio) {
    aspectSelectEl.value = storyboard.aspect_ratio;
  }

  const container = document.getElementById('storyboardOutput');
  if (!container) return;

  const scenes = storyboard.scenes || [];

  let html = `
    <div style="margin-bottom: 24px; padding: 24px; background: linear-gradient(145deg, rgba(8, 14, 28, 0.9), rgba(16, 25, 48, 0.8)); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
      
      <!-- Row 1: Judul Film & Action Buttons -->
      <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 18px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 280px;">
          <label style="font-size: 12px; color: var(--neon-cyan); font-weight: 800; display: block; margin-bottom: 6px; letter-spacing: 0.5px;">🎬 JUDUL FILM (EDITABLE):</label>
          <input type="text" id="editFilmTitle" value="${escapeHtml(storyboard.film_title || 'Film Sinematik')}" style="width: 100%; font-size: 18px; font-weight: 800; color: #ffffff; background: rgba(4, 7, 16, 0.85); border: 1px solid var(--neon-cyan); border-radius: 10px; padding: 10px 16px; font-family: var(--font-heading); box-shadow: 0 0 15px rgba(56, 189, 248, 0.2);" />
        </div>

        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); padding: 8px 16px; border-radius: 20px; font-size: 12px; font-weight: 700;">🌱 Seed: ${storyboard.character_seed || 'Auto'}</span>
          <span title="Rasio ini yang akan dipakai saat Kirim & Eksekusi ke Flow" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); padding: 8px 16px; border-radius: 20px; font-size: 12px; font-weight: 700;">${storyboard.aspect_ratio === 'portrait' ? '📱 Portrait 9:16' : '🖥️ Landscape 16:9'}</span>
          <button type="button" class="btn-secondary" id="btnFullRegenerate" style="padding: 9px 16px; font-size: 12px; font-weight: 700; border-color: var(--neon-purple); color: #e9d5ff; border-radius: 10px; height: 40px; cursor: pointer;">🎲 Regenerate Storyboard</button>
          <button type="button" class="btn-secondary" id="btnCopyAllPrompts" style="padding: 9px 16px; font-size: 12px; font-weight: 700; border-color: var(--neon-cyan); color: var(--neon-cyan); border-radius: 10px; height: 40px; cursor: pointer;">📋 Copy All Prompts</button>
        </div>
      </div>

      <!-- Row 2: Mood Visual & Karakter -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
        <div style="background: rgba(4, 7, 16, 0.5); padding: 12px 14px; border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08);">
          <label style="font-size: 12px; color: var(--text-secondary); font-weight: 700; display: block; margin-bottom: 6px;">🎨 Mood Visual & Style:</label>
          <input type="text" id="editGenreStyle" value="${escapeHtml(storyboard.genre_style || '')}" style="width: 100%; font-size: 13px; color: #ffffff; background: rgba(4, 7, 16, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 8px 12px;" />
        </div>

        <div style="background: rgba(4, 7, 16, 0.5); padding: 12px 14px; border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08);">
          <label style="font-size: 12px; color: var(--text-secondary); font-weight: 700; display: block; margin-bottom: 6px;">👤 Karakter & Seeds Konsisten:</label>
          <input type="text" id="editConsistentCharacters" value="${escapeHtml(storyboard.consistent_characters || '')}" style="width: 100%; font-size: 13px; color: #ffffff; background: rgba(4, 7, 16, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 8px 12px;" />
        </div>
      </div>
    </div>
  `;

  scenes.forEach((sc, idx) => {
    const dur = sc.duration || 10;
    const isUgc = sc.time_range || (currentStoryboard && currentStoryboard.ugc_mode);
    const stepDur = isUgc ? 2 : dur;
    const durOf = (s) => {
      const d = parseInt(s && s.duration);
      return (d && d > 0) ? d : stepDur;
    };
    const startS = (storyboard.scenes || []).slice(0, idx).reduce((a, s) => a + durOf(s), 0);
    const endS = startS + durOf(sc);
    const fmt = s => `${Math.floor(s/60)}:${(s%60).toString().padStart(2,'0')}`;
    const timeRangeStr = sc.time_range || `${fmt(startS)}–${fmt(endS)}`;

    html += `
      <div class="scene-item-card" style="margin-bottom: 22px; padding: 22px; background: linear-gradient(145deg, rgba(12, 18, 36, 0.8), rgba(20, 29, 54, 0.7)); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 16px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3); transition: all 0.3s;">
        
        <!-- Header Bar -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); padding-bottom: 12px;">
          <div style="display: flex; align-items: center; gap: 12px; flex: 1; min-width: 300px;">
            <span style="background: linear-gradient(135deg, var(--neon-cyan), var(--neon-purple)); color: #ffffff; font-weight: 800; font-size: 13px; padding: 6px 14px; border-radius: 20px; white-space: nowrap; box-shadow: 0 4px 12px rgba(56, 189, 248, 0.3);">
              Adegan ${sc.scene_number || (idx + 1)} (${timeRangeStr})
            </span>
            <input type="text" class="edit-sc-title" data-idx="${idx}" value="${escapeHtml(sc.title || '')}" placeholder="Judul Adegan..." style="flex: 1; font-size: 15px; font-weight: 800; color: #ffffff; background: rgba(4, 7, 16, 0.7); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 8px 14px;" />
          </div>

          <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
            <select class="edit-sc-duration" data-idx="${idx}" title="Durasi klip adegan ini (Google Flow hanya mendukung 4/6/8/10 detik)" style="font-size: 12px; font-weight: 700; color: #fbbf24; background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.35); border-radius: 8px; padding: 6px 10px;">
              ${[4, 6, 8, 10].map(d => `<option value="${d}" ${durOf(sc) === d ? 'selected' : ''}>⏱️ ${d}s</option>`).join('')}
            </select>
            <button type="button" class="btn-secondary btn-regen-single-scene" data-idx="${idx}" data-scnum="${sc.scene_number || (idx + 1)}" style="padding: 6px 14px; font-size: 12px; font-weight: 700; border-color: rgba(236, 72, 153, 0.5); color: #f9a8d4; border-radius: 8px; cursor: pointer;">🎲 Regenerate</button>
          </div>
        </div>

        <!-- Storyboard breakdown table: one labelled row per field, like a production sheet -->
        <div style="display: grid; grid-template-columns: 132px 1fr; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 10px; overflow: hidden;">

          <div style="${SB_LABEL_CELL}">🎬 SHOT TYPE</div>
          <div style="${SB_VALUE_CELL}">
            <input type="text" class="edit-sc-shottype" data-idx="${idx}" value="${escapeHtml(sc.shot_type || '')}" placeholder="Close Up / Medium Shot / Wide Shot / OTS..." style="${SB_INPUT} color: #c4b5fd; font-weight: 700;" />
          </div>

          <div style="${SB_LABEL_CELL}">🎥 CAMERA</div>
          <div style="${SB_VALUE_CELL}">
            <input type="text" class="edit-sc-camera" data-idx="${idx}" value="${escapeHtml(sc.camera_movement || '')}" placeholder="Slow push-in / Handheld tracking / Static..." style="${SB_INPUT} color: var(--neon-cyan);" />
          </div>

          <div style="${SB_LABEL_CELL}">📝 ACTION</div>
          <div style="${SB_VALUE_CELL}">
            <textarea class="edit-sc-action" data-idx="${idx}" rows="2" placeholder="Ringkasan aksi adegan dalam Bahasa Indonesia..." style="${SB_INPUT} color: #e2e8f0; resize: vertical;">${sc.action_summary || ''}</textarea>
          </div>

          <div style="${SB_LABEL_CELL}">🎙️ VO</div>
          <div style="${SB_VALUE_CELL}">
            <textarea class="edit-sc-vo" data-idx="${idx}" rows="2" placeholder="Narasi dubbing Bahasa Indonesia (dipakai untuk subtitle SRT)..." style="${SB_INPUT} color: #a7f3d0; font-style: italic; resize: vertical;">${sc.narration_id || sc.voiceover_script || ''}</textarea>
          </div>

          <div style="${SB_LABEL_CELL}">💬 TEXT OVERLAY</div>
          <div style="${SB_VALUE_CELL}">
            <input type="text" class="edit-sc-overlay" data-idx="${idx}" value="${escapeHtml(sc.text_overlay || '')}" placeholder="Teks pendek di layar (maks 6 kata)..." style="${SB_INPUT} color: #fbbf24; font-weight: 700;" />
          </div>

          <div style="${SB_LABEL_CELL} border-bottom: none;">⚡ FLOW PROMPT</div>
          <div style="${SB_VALUE_CELL} border-bottom: none;">
            <textarea class="edit-sc-prompt" data-idx="${idx}" rows="4" style="${SB_INPUT} font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace; font-size: 12px; line-height: 1.6; color: #38bdf8; resize: vertical;">${sc.prompt_for_flow || ''}</textarea>
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;

  bindStoryboardLiveEditing();
}

function bindStoryboardLiveEditing() {
  if (!currentStoryboard) return;

  const titleEl = document.getElementById('editFilmTitle');
  if (titleEl) titleEl.addEventListener('input', (e) => currentStoryboard.film_title = e.target.value);

  const genreEl = document.getElementById('editGenreStyle');
  if (genreEl) genreEl.addEventListener('input', (e) => currentStoryboard.genre_style = e.target.value);

  const charEl = document.getElementById('editConsistentCharacters');
  if (charEl) charEl.addEventListener('input', (e) => currentStoryboard.consistent_characters = e.target.value);

  document.querySelectorAll('.edit-sc-title').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].title = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-camera').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].camera_movement = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-shottype').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].shot_type = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-duration').forEach(el => {
    el.addEventListener('change', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (!currentStoryboard.scenes[idx]) return;
      currentStoryboard.scenes[idx].duration = parseInt(e.target.value) || 10;
      saveStoryboardToHistory(currentStoryboard);
      renderStoryboardResult(currentStoryboard); // refresh the cumulative timeline labels
    });
  });

  document.querySelectorAll('.edit-sc-action').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].action_summary = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-vo').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) {
        // Holds narration only — the text overlay has its own field, otherwise its label
        // would leak into narration_id and end up printed in the SRT subtitles.
        currentStoryboard.scenes[idx].narration_id = e.target.value;
        currentStoryboard.scenes[idx].voiceover_script = e.target.value;
      }
    });
  });

  document.querySelectorAll('.edit-sc-overlay').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].text_overlay = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-prompt').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) {
        currentStoryboard.scenes[idx].prompt_for_flow = e.target.value;
        currentStoryboard.scenes[idx].prompt = e.target.value;
      }
    });
  });

  // Copy all prompts button
  const btnCopy = document.getElementById('btnCopyAllPrompts');
  if (btnCopy) {
    btnCopy.addEventListener('click', () => {
      const allPrompts = (currentStoryboard.scenes || []).map((s, i) => `Adegan ${i + 1}: ${s.title}\nFlow Prompt: ${s.prompt_for_flow}`).join('\n\n');
      navigator.clipboard.writeText(allPrompts);
      showToast('Seluruh prompt adegan berhasil di-copy ke clipboard!', 'success');
    });
  }

  // Full Regenerate Storyboard button
  const btnFullRegenerate = document.getElementById('btnFullRegenerate');
  if (btnFullRegenerate) {
    btnFullRegenerate.addEventListener('click', () => {
      const form = document.getElementById('storyboardForm');
      if (!form) return;
      if (!currentStoryboard) {
        showToast('Belum ada storyboard yang dimuat untuk di-regenerate.', 'warning');
        return;
      }

      // This button can be pressed from Scene Master, where the storyboard form is not on
      // screen and may be empty. Restore every generation parameter from the storyboard
      // itself so the regenerate reproduces the same setup instead of failing validation.
      const setVal = (ids, value) => {
        if (value === undefined || value === null || value === '') return;
        for (const id of ids) {
          const el = document.getElementById(id);
          if (el) { el.value = value; return; }
        }
      };
      const setChecked = (id, value) => {
        const el = document.getElementById(id);
        if (el && typeof value === 'boolean') el.checked = value;
      };

      // Older storyboards were saved before the premise was recorded — rebuild one from
      // whatever the storyboard does carry so the button still works on them.
      let premise = currentStoryboard.premise;
      if (!premise || !String(premise).trim()) {
        const bits = [currentStoryboard.film_title, currentStoryboard.genre_style, currentStoryboard.consistent_characters]
          .filter(Boolean).join('. ');
        const firstAction = (currentStoryboard.scenes || []).map(s => s.action_summary).filter(Boolean)[0] || '';
        premise = [bits, firstAction].filter(Boolean).join(' ').trim();
      }

      if (!premise) {
        showToast('Storyboard ini tidak menyimpan tema. Isi Tema / Ide Utama Film di tab AI Storyboard dulu.', 'warning');
        document.querySelector('.nav-item[data-tab="tab-storyboard"]')?.click();
        return;
      }

      setVal(['premiseInput', 'themeInput'], premise);
      setVal(['aspectSelect', 'aspectRatioSelect', 'settingAspectRatio'], currentStoryboard.aspect_ratio);
      setVal(['sceneCountInput'], currentStoryboard.scene_count);
      setVal(['characterInfoInput', 'consistentCharacterInput', 'characterInfo'],
             currentStoryboard.character_info || currentStoryboard.consistent_characters);
      setVal(['characterSeedInput', 'characterSeed'], currentStoryboard.character_seed);
      setVal(['targetCountryInput'], currentStoryboard.target_country);
      setVal(['dracinThemeSelect'], currentStoryboard.dracin_theme);
      setVal(['durationPerSceneSelect'], currentStoryboard.duration_mode);
      setChecked('chkMicrodramaMode', currentStoryboard.microdrama_mode);
      setChecked('chkUgcMode', currentStoryboard.ugc_mode);
      setChecked('chkChildrenMode', currentStoryboard.children_mode);
      setChecked('chkScriptMode', currentStoryboard.script_mode);
      document.getElementById('chkScriptMode')?.dispatchEvent(new Event('change'));

      form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
      showToast('Memulai regenerate full storyboard baru...', 'info');
    });
  }

  // Single Scene Regenerate button
  document.querySelectorAll('.btn-regen-single-scene').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const idx = parseInt(btn.getAttribute('data-idx'));
      const scNum = parseInt(btn.getAttribute('data-scnum'));
      const sc = currentStoryboard.scenes[idx];
      if (!sc) return;

      btn.disabled = true;
      btn.textContent = '⏳ Regenerating...';

      try {
        showToast(`Regenerating varian baru Adegan ${scNum} dengan Gemini AI...`, 'info');
        const res = await fetch('/api/storyboard/regenerate_scene', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            film_title: currentStoryboard.film_title || 'Film Sinematik',
            scene_number: scNum,
            scene_title: sc.title || `Adegan ${scNum}`,
            consistent_characters: currentStoryboard.consistent_characters || '',
            genre_style: currentStoryboard.genre_style || ''
          })
        });

        const data = await res.json();
        if (!res.ok || !data.scene) throw new Error(data.detail || 'Gagal regenerate adegan');

        const newSc = data.scene;
        sc.action_summary = newSc.action_summary || sc.action_summary;
        sc.prompt_for_flow = newSc.prompt_for_flow || sc.prompt_for_flow;
        sc.prompt = newSc.prompt_for_flow || sc.prompt;
        sc.camera_movement = newSc.camera_movement || sc.camera_movement;
        if (newSc.narration_id) {
          sc.narration_id = newSc.narration_id;
          sc.voiceover_script = newSc.narration_id;
        }

        renderStoryboardResult(currentStoryboard);
        saveStoryboardToHistory(currentStoryboard);
        showToast(`Adegan ${scNum} berhasil di-regenerate dengan prompt & aksi baru!`, 'success');

      } catch (err) {
        showToast(`Gagal regenerate adegan ${scNum}: ${err.message}`, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = '🎲 Regenerate Adegan Ini';
      }
    });
  });
}

// Execution Terminal Polling
function startJobPolling(jobId) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => pollJobStatus(jobId), 3000);
  pollJobStatus(jobId);
}

async function pollJobStatus(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) return;

    const data = await res.json();
    const job = data.job;
    const logs = data.logs || [];

    const timingText = job.processing_duration ? ` — Waktu proses: ${job.processing_duration}` : '';
    const sizeText = job.output_size_display ? ` — Ukuran: ${job.output_size_display}` : '';
    document.getElementById('executionStatusText').textContent = `Job ${job.job_id} — Status: ${job.status.toUpperCase()}${timingText}${sizeText}`;

    const stopBtn = document.getElementById('btnStopExecution');
    if (stopBtn) {
      if (job.status === 'processing') {
        stopBtn.style.display = 'block';
      } else {
        stopBtn.style.display = 'none';
      }
    }

    const total = job.total_scenes || 1;
    const current = job.scenes ? job.scenes.filter(s => s.status === 'completed').length : 0;

    document.getElementById('jobProgressBadge').textContent = `${current} / ${total} Adegan Selesai`;
    document.getElementById('jobProgressBar').style.width = `${Math.round((current / total) * 100)}%`;

    // Render live scene cards
    const grid = document.getElementById('scenesLiveGrid');
    grid.innerHTML = (job.scenes || []).map(sc => `
      <div class="scene-item-card">
        <div class="scene-header">
          <span>Adegan ${sc.scene_number}: ${sc.title}</span>
          <span class="badge-status ${sc.status === 'completed' ? 'badge-ready' : 'badge-noauth'}">
            ${sc.status.toUpperCase()} (${sc.profile_used || 'Worker'})
          </span>
        </div>
        <p style="font-size: 13px;">${sc.prompt}</p>
        ${sc.relative_url ? `
        <div style="display: flex; align-items: center; gap: 10px; margin-top: 10px; padding: 8px 12px; border-radius: 8px; background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.35);">
          <span style="font-size: 14px;">✅</span>
          <span style="font-size: 12px; font-weight: 700; color: #4ade80;">Video tersimpan${sc.video_path ? ` — ${sc.video_path.split(/[\\/]/).pop()}` : ''}</span>
          <span style="font-size: 11px; color: var(--text-muted); margin-left: auto;">Tonton di tab Video Gallery</span>
        </div>` : ''}
        ${sc.status === 'failed' ? `
        <div style="display: flex; align-items: flex-start; gap: 10px; margin-top: 10px; padding: 8px 12px; border-radius: 8px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.35);">
          <span style="font-size: 14px;">❌</span>
          <span style="font-size: 12px; font-weight: 600; color: #f87171;">${sc.error ? String(sc.error).slice(0, 220) : 'Render adegan gagal.'}</span>
        </div>` : ''}
      </div>
    `).join('');

    // Update Terminal Logs
    const logBody = document.getElementById('terminalLogBody');
    logBody.innerHTML = logs.map(l => `
      <div class="log-line ${logLineCategory(l)}">[${l.timestamp}] [${l.profile}] ${l.message}</div>
    `).join('');
    logBody.scrollTop = logBody.scrollHeight;

    if (job.status === 'completed' || job.status === 'completed_partial' || job.status === 'failed' || job.status === 'cancelled') {
      clearInterval(pollTimer);
      if (job.status === 'completed') {
        showToast('Film sinematik berhasil digabungkan!', 'success', 'Render Selesai');
      }
    }

  } catch (err) {
    console.error('Job polling error:', err);
  }
}

document.getElementById('clearLogBtn').addEventListener('click', () => {
  document.getElementById('terminalLogBody').innerHTML = '';
});

const copyLogBtn = document.getElementById('copyLogBtn');
if (copyLogBtn) {
  copyLogBtn.addEventListener('click', () => {
    const logBody = document.getElementById('terminalLogBody');
    if (!logBody) return;
    const text = logBody.innerText || logBody.textContent;
    if (!text.trim()) {
      showToast('Belum ada log di terminal untuk disalin.', 'warning');
      return;
    }
    navigator.clipboard.writeText(text).then(() => {
      showToast('📋 Seluruh log terminal berhasil disalin ke clipboard! Siap ditempel.', 'success');
    }).catch(err => {
      showToast('Gagal menyalin log: ' + err.message, 'error');
    });
  });
}

// Gallery & Sequencer Studio
function initGallery() {
  const refreshBtn = document.getElementById('refreshGalleryBtn');
  const selectAllCb = document.getElementById('gallerySelectAllCheckbox');
  const deleteSelectedBtn = document.getElementById('deleteSelectedGalleryBtn');

  if (refreshBtn) refreshBtn.addEventListener('click', refreshGallery);

  if (selectAllCb) {
    selectAllCb.addEventListener('change', () => {
      const checkboxes = document.querySelectorAll('.gallery-item-checkbox');
      checkboxes.forEach(cb => cb.checked = selectAllCb.checked);
      updateGalleryDeleteSelectedButton();
    });
  }

  if (deleteSelectedBtn) {
    deleteSelectedBtn.addEventListener('click', () => {
      const selected = Array.from(document.querySelectorAll('.gallery-item-checkbox:checked')).map(cb => cb.getAttribute('data-jobid'));
      if (!selected.length) return;

      showCustomConfirm(
        'Hapus Pilihan Massal',
        `Apakah Anda yakin ingin menghapus ${selected.length} job yang dipilih secara permanen?`,
        `Ya, Hapus ${selected.length} Item`,
        '🗑️',
        async () => {
          try {
            const res = await fetch('/api/gallery/batch_delete', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ job_ids: selected })
            });
            const data = await res.json();
            showToast(data.message || 'Job berhasil dihapus!', 'success');
            refreshGallery();
          } catch (err) {
            showToast('Gagal menghapus job: ' + err.message, 'error');
          }
        }
      );
    });
  }

  const clearBtn = document.getElementById('autoRenderClearBtn');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      selectedRenderClips = [];
      document.querySelectorAll('.clip-render-checkbox:checked').forEach(cb => cb.checked = false);
      updateAutoRenderBar();
    });
  }

  const autoRenderBtn = document.getElementById('autoRenderBtn');
  if (autoRenderBtn) {
    autoRenderBtn.addEventListener('click', async () => {
      if (selectedRenderClips.length < 1) return;
      const transition = document.getElementById('autoRenderTransition').value;

      autoRenderBtn.disabled = true;
      autoRenderBtn.textContent = '⏳ Merender...';
      try {
        const res = await fetch('/api/gallery/render_selection', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            clips: selectedRenderClips.map(r => ({ job_id: r.job_id, filename: r.filename })),
            transition,
            title: `Sequencer Custom (${selectedRenderClips.length} klip)`
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Gagal render.');

        showToast('🎬 Video hasil pilihan berhasil digabungkan! Cek di bagian atas Galeri.', 'success');
        selectedRenderClips = [];
        updateAutoRenderBar();
        refreshGallery();
      } catch (err) {
        showToast('Gagal auto-render: ' + err.message, 'error');
      } finally {
        autoRenderBtn.disabled = false;
        autoRenderBtn.textContent = '🚀 Auto Render Klip Terpilih';
      }
    });
  }
}

function updateAutoRenderBar() {
  const bar = document.getElementById('autoRenderBar');
  const countEl = document.getElementById('autoRenderCount');
  if (!bar || !countEl) return;

  if (selectedRenderClips.length > 0) {
    bar.style.display = 'flex';
    countEl.textContent = `🎬 ${selectedRenderClips.length} klip dipilih (urutan sesuai klik)`;
  } else {
    bar.style.display = 'none';
  }
}

function updateGalleryDeleteSelectedButton() {
  const selected = document.querySelectorAll('.gallery-item-checkbox:checked');
  const btn = document.getElementById('deleteSelectedGalleryBtn');
  const selectAllCb = document.getElementById('gallerySelectAllCheckbox');
  const allCbs = document.querySelectorAll('.gallery-item-checkbox');

  if (btn) {
    btn.disabled = selected.length === 0;
    btn.textContent = `🗑️ Hapus Pilihan (${selected.length})`;
  }
  if (selectAllCb && allCbs.length > 0) {
    selectAllCb.checked = selected.length === allCbs.length;
  }
}

async function refreshGallery() {
  try {
    const res = await fetch('/api/gallery');
    if (!res.ok) return;
    const data = await res.json();

    const container = document.getElementById('galleryContainer');
    const items = data.gallery || [];
    const galleryPrompts = new Map(items.map(item => [String(item.job_id), item.initial_prompt || '']));
    const selectAllCb = document.getElementById('gallerySelectAllCheckbox');
    if (selectAllCb) selectAllCb.checked = false;
    updateGalleryDeleteSelectedButton();

    if (items.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🎥</div>
          <h4>Belum Ada Hasil Video di Galeri</h4>
          <p>Jalankan job pembuatan video di tab Storyboard untuk mulai menghasilkan klip adegan.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = `<div class="gallery-grid">` + items.map(item => `
      <div class="film-card" style="position: relative;">
        <!-- Header Row 1: Title, Checkbox & Quick Edit/Delete Actions -->
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 8px;">
          <div style="display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0;">
            <input type="checkbox" class="gallery-item-checkbox" data-jobid="${item.job_id}" style="cursor: pointer; width: 16px; height: 16px; flex-shrink: 0;" />
            <h4 class="film-card-title" title="${escapeHtml(item.title || 'Film Sinematik')}" style="margin: 0; font-size: 15px; font-weight: bold; color: var(--neon-cyan); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(item.title || 'Film Sinematik')}</h4>
          </div>
          <div style="display: flex; gap: 6px; align-items: center; flex-shrink: 0;">
            <span role="button" class="icon-action-btn btn-edit-single-job" data-jobid="${item.job_id}" data-title="${escapeHtml(item.title || 'Film Sinematik')}" title="Edit Judul Film" style="background: rgba(255, 255, 255, 0.08) !important; border: 1px solid rgba(255, 255, 255, 0.15) !important; color: #ffffff !important; display: inline-flex !important; align-items: center !important; justify-content: center !important; width: 28px !important; height: 28px !important; border-radius: 6px !important; cursor: pointer !important;">✏️</span>
            <span role="button" class="icon-action-btn icon-action-btn-danger btn-delete-single-job" data-jobid="${item.job_id}" title="Hapus Item Galeri" style="background: rgba(244, 63, 94, 0.2) !important; border: 1px solid rgba(244, 63, 94, 0.4) !important; color: #ffffff !important; display: inline-flex !important; align-items: center !important; justify-content: center !important; width: 28px !important; height: 28px !important; border-radius: 6px !important; cursor: pointer !important;">🗑️</span>
          </div>
        </div>

        <!-- Header Row 2: Badges & Timestamp -->
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.08);">
          <span class="badge-status badge-ready" style="font-size: 10px; padding: 2px 7px; background: rgba(56, 189, 248, 0.15); border-color: rgba(56, 189, 248, 0.3); color: #38bdf8;">${item.aspect_ratio === 'portrait' ? '📱 Short 9:16' : '🖥️ Landscape 16:9'}</span>
          <span class="badge-status ${item.status === 'completed' ? 'badge-ready' : 'badge-noauth'}" style="font-size: 10px; padding: 2px 7px;">${(item.status || 'UNKNOWN').toUpperCase()}</span>
          ${item.total_duration != null ? `<span class="gallery-meta-chip">🎞️ ${Number(item.total_duration)}s</span>` : ''}
          ${item.output_size_display ? `<span class="gallery-meta-chip">💾 ${escapeHtml(item.output_size_display)}</span>` : ''}
          ${item.processing_duration ? `<span class="gallery-meta-chip">⏱️ ${escapeHtml(item.processing_duration)}</span>` : ''}
          <span style="font-size: 11px; color: var(--text-muted); margin-left: auto;">📅 ${item.created_at_formatted || 'Tersimpan'}</span>
        </div>

        <div class="gallery-idea-box">
          <div class="gallery-idea-heading">
            <span>💡 Prompt / Ide Awal</span>
            <button type="button" class="btn-copy-gallery-prompt" data-jobid="${item.job_id}" ${item.initial_prompt ? '' : 'disabled'}>📋 Salin</button>
          </div>
          <p title="${escapeHtml(item.initial_prompt || '')}">${escapeHtml(item.initial_prompt || 'Ide awal belum tersimpan untuk video lama ini.')}</p>
        </div>

        ${item.cinematic_film_url ? `
          <div style="margin-bottom: 12px; background: rgba(52, 211, 153, 0.1); padding: 12px; border-radius: 8px; border: 1px solid rgba(52, 211, 153, 0.3);">
            <b style="color: var(--neon-green); font-size: 13px;">🎬 Full Cinematic Movie:</b>
            <video src="${item.cinematic_film_url}" controls preload="metadata" style="margin-top: 6px; width: 100%; max-height: 300px; object-fit: contain; background: #000; border-radius: 8px;"></video>
            <div style="display: flex; gap: 8px; margin-top: 10px;">
              <a href="${item.cinematic_film_url}" download class="btn-primary" style="flex: 1; text-align: center; text-decoration: none; font-size: 13px;">⬇️ Download Movie MP4</a>
              ${item.srt_subtitles_url ? `<a href="${item.srt_subtitles_url}" download class="btn-secondary" style="text-align: center; text-decoration: none; font-size: 13px;">💬 Subtitle SRT</a>` : ''}
            </div>
            ${localStorage.getItem(seoStorageKey(item.job_id)) ? `
              <div class="gallery-seo-actions">
                <button type="button" class="btn-secondary btn-view-seo" data-jobid="${item.job_id}">👁️ View SEO</button>
                <button type="button" class="btn-secondary btn-regenerate-seo" data-jobid="${item.job_id}" data-title="${escapeHtml(item.title || 'Film Sinematik')}">🔄 Regenerate</button>
              </div>
            ` : `
              <button type="button" class="btn-secondary btn-generate-seo" data-jobid="${item.job_id}" data-title="${escapeHtml(item.title || 'Film Sinematik')}" style="margin-top: 10px; width: 100%; border-color: var(--neon-purple); color: #e9d5ff; font-size: 13px;">🚀 Generate YouTube SEO Kit (Judul, Deskripsi, Thumbnail & Tags)</button>
            `}
          </div>
        ` : ''}

        <h5 style="margin-top: 14px; font-size: 13px; color: var(--neon-cyan);">🎞️ Klip Adegan (${(item.clips || []).length} Scene) — klik untuk preview:</h5>
        <div class="gallery-clips-grid" style="--clip-row-height: ${item.aspect_ratio === 'portrait' ? '172px' : '96px'};">
          ${(item.clips || []).map((c, i) => `
            <div class="clip-thumb" data-url="${c.url}" data-label="${escapeHtml(item.title || 'Film')} — Adegan ${i + 1}" title="Klik untuk preview Adegan ${i + 1}"
                 style="position: relative; cursor: pointer; border: 1px solid var(--glass-border); border-radius: 8px; overflow: hidden; background: #04070f; aspect-ratio: ${item.aspect_ratio === 'portrait' ? '9 / 16' : '16 / 9'};">
              <video src="${c.url}#t=0.5" preload="metadata" muted playsinline style="width: 100%; height: 100%; object-fit: cover; pointer-events: none;"></video>
              <div style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.6));">
                <span style="font-size: 18px; opacity: 0.9;">▶️</span>
              </div>
              <input type="checkbox" class="clip-render-checkbox" data-jobid="${item.job_id}" data-filename="${c.filename}" data-url="${c.url}" data-label="${item.title || 'Film'} - Adegan ${i + 1}"
                     title="Pilih untuk digabung di Sequencer" style="position: absolute; top: 5px; left: 5px; cursor: pointer; width: 14px; height: 14px; z-index: 2;" />
              <span style="position: absolute; bottom: 4px; left: 6px; font-size: 10px; font-weight: 800; color: #fff; text-shadow: 0 1px 4px #000;">Adegan ${i + 1}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('') + `</div>`;

    // Thumbnail opens the preview; the sequencer checkbox on top of it must not.
    container.querySelectorAll('.clip-thumb').forEach(thumb => {
      thumb.addEventListener('click', (e) => {
        if (e.target.classList.contains('clip-render-checkbox')) return;
        // Scenes of the same film become the playlist, so ‹ › steps through that film only.
        const siblings = [...thumb.parentElement.querySelectorAll('.clip-thumb')];
        const playlist = siblings.map(t => ({
          url: t.getAttribute('data-url'),
          label: t.getAttribute('data-label')
        }));
        openVideoPreview(thumb.getAttribute('data-url'), thumb.getAttribute('data-label'),
                         playlist, siblings.indexOf(thumb));
      });
    });

    // Attach listeners for single job edit, deletion and checkbox change
    container.querySelectorAll('.gallery-item-checkbox').forEach(cb => {
      cb.addEventListener('change', updateGalleryDeleteSelectedButton);
    });

    container.querySelectorAll('.btn-copy-gallery-prompt').forEach(btn => {
      btn.addEventListener('click', async () => {
        const prompt = galleryPrompts.get(String(btn.getAttribute('data-jobid'))) || '';
        if (!prompt) return;
        await navigator.clipboard.writeText(prompt);
        showToast('Prompt / ide awal berhasil disalin!', 'success');
      });
    });

    // Auto Render sequencer: clip selection preserves click order across jobs
    container.querySelectorAll('.clip-render-checkbox').forEach(cb => {
      const isSelected = selectedRenderClips.some(r => r.job_id === cb.getAttribute('data-jobid') && r.filename === cb.getAttribute('data-filename'));
      cb.checked = isSelected;
      cb.addEventListener('change', () => {
        const ref = { job_id: cb.getAttribute('data-jobid'), filename: cb.getAttribute('data-filename'), label: cb.getAttribute('data-label') };
        if (cb.checked) {
          selectedRenderClips.push(ref);
        } else {
          selectedRenderClips = selectedRenderClips.filter(r => !(r.job_id === ref.job_id && r.filename === ref.filename));
        }
        updateAutoRenderBar();
      });
    });

    container.querySelectorAll('.btn-edit-single-job').forEach(btn => {
      btn.addEventListener('click', () => {
        const jobId = btn.getAttribute('data-jobid');
        const currentTitle = btn.getAttribute('data-title');

        showCustomPrompt(
          'Ubah Judul Film Sinematik',
          'Ketikkan judul baru untuk film ini:',
          currentTitle,
          async (newTitle) => {
            if (!newTitle || newTitle === currentTitle) return;
            try {
              const res = await fetch(`/api/gallery/${jobId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
              });
              const data = await res.json();
              showToast(data.message || 'Judul film berhasil diperbarui!', 'success');
              refreshGallery();
            } catch (err) {
              showToast('Gagal memperbarui judul film: ' + err.message, 'error');
            }
          }
        );
      });
    });

    container.querySelectorAll('.btn-delete-single-job').forEach(btn => {
      btn.addEventListener('click', () => {
        const jobId = btn.getAttribute('data-jobid');
        if (!jobId) return;

        showCustomConfirm(
          'Hapus Item Galeri',
          'Apakah Anda yakin ingin menghapus item galeri film ini secara permanen?',
          'Ya, Hapus',
          '🗑️',
          async () => {
            try {
              const res = await fetch(`/api/gallery/${jobId}`, { method: 'DELETE' });
              const data = await res.json();
              showToast(data.message || 'Job berhasil dihapus!', 'success');
              refreshGallery();
            } catch (err) {
              showToast('Gagal menghapus job: ' + err.message, 'error');
            }
          }
        );
      });
    });

    updateAutoRenderBar();
  } catch (err) {
    console.error('Gallery refresh error:', err);
  }
}

// Studio Settings Dashboard Tab
const DEFAULT_V41_TEMPLATE = `CHARACTER SHEET MASTER PROMPT V4.1

Studio Portfolio Edition
Clean • Elegant • Professional • AI Optimized

Create a clean, elegant, studio-quality Character Sheet for {char_name} (Character Seed: {char_seed}): {char_desc}.

Transform the subject into a consistent original character design while preserving the overall appearance, proportions, hairstyle, outfit style, silhouette, and recognizable visual language.

The layout should resemble a professional concept art portfolio page with generous white space, minimal typography, thin divider lines, and a balanced editorial composition.

LAYOUT:
Large "CHARACTER SHEET" title | Character Name: {char_name} | Soft beige or warm white background | Thin black divider lines | Minimal editorial typography | Spacious composition | Balanced margins | Professional portfolio presentation.

TURNAROUND:
Front View | Side View | Back View
Use identical character proportions, hairstyle, clothing design, silhouette, and visual appearance across all three views.

FACIAL EXPRESSIONS:
Three close-up portraits only: Neutral, Smile, Thoughtful. Expressions should modify only facial muscles while maintaining the same character appearance.

DYNAMIC POSES:
Three natural full-body poses only: Walking, Standing, Sitting. Keep body proportions, clothing behavior, hairstyle, and overall design consistent.

REFERENCE PORTRAIT:
One clean portrait showing the definitive appearance of {char_name}. Centered composition. Natural expression. Soft studio lighting.

CONSISTENCY:
Maintain a single coherent character design across every panel. Keep consistent: Facial structure | Hairstyle | Body proportions | Clothing construction | Accessories | Colors | Silhouette | Fabric behavior | Visual style.

RENDER STYLE:
Ultra photorealistic | Editorial fashion photography | Premium concept art | Soft studio lighting | Clean shadows | High detail | Natural skin texture | Accurate anatomy | Realistic fabric | Elegant presentation | Minimalistic portfolio design.

NEGATIVE PROMPT:
Busy layout, cluttered composition, excessive annotations, technical blueprint, production diagram, material callouts, color palette, measurement chart, camera reference, lighting reference, oversized text, crowded design, duplicate panels, inconsistent character design, different hairstyle, different clothing, different proportions, low quality, blurry textures, AI artifacts, cartoon style, anime style, painterly rendering, distorted anatomy.`;

async function loadSettingsTab() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    const s = data.settings || {};
    const keys = s.gemini_api_keys && s.gemini_api_keys.length ? s.gemini_api_keys : (s.gemini_api_key ? [s.gemini_api_key] : []);
    
    const keyTabEl = document.getElementById('settingGeminiKeyTab') || document.getElementById('settingGeminiKey');
    if (keyTabEl && keys.length) keyTabEl.value = keys.join('\n');

    const modelTabEl = document.getElementById('settingGeminiModelTab') || document.getElementById('settingGeminiModel');
    if (modelTabEl && s.gemini_model) modelTabEl.value = s.gemini_model;

    const providerRadio = document.querySelector(`input[name="defaultTextProvider"][value="${s.default_text_provider || 'gemini'}"]`);
    if (providerRadio) providerRadio.checked = true;
    const openAIKeys = s.openai_api_keys?.length ? s.openai_api_keys : (s.openai_api_key ? [s.openai_api_key] : []);
    const deepSeekKeys = s.deepseek_api_keys?.length ? s.deepseek_api_keys : (s.deepseek_api_key ? [s.deepseek_api_key] : []);
    const xaiKeys = s.xai_api_keys?.length ? s.xai_api_keys : (s.xai_api_key ? [s.xai_api_key] : []);
    const openAIKeyEl = document.getElementById('settingOpenAIKeyTab');
    const deepSeekKeyEl = document.getElementById('settingDeepSeekKeyTab');
    const xaiKeyEl = document.getElementById('settingXAIKeyTab');
    if (openAIKeyEl) openAIKeyEl.value = openAIKeys.join('\n');
    if (deepSeekKeyEl) deepSeekKeyEl.value = deepSeekKeys.join('\n');
    if (xaiKeyEl) xaiKeyEl.value = xaiKeys.join('\n');
    const openAIModelEl = document.getElementById('settingOpenAIModelTab');
    const deepSeekModelEl = document.getElementById('settingDeepSeekModelTab');
    const xaiModelEl = document.getElementById('settingXAIModelTab');
    const xaiBaseUrlEl = document.getElementById('settingXAIBaseUrlTab');
    if (openAIModelEl) openAIModelEl.value = s.openai_model || 'gpt-4.1-mini';
    if (deepSeekModelEl) deepSeekModelEl.value = s.deepseek_model || 'deepseek-chat';
    if (xaiModelEl) xaiModelEl.value = s.xai_model || 'grok-4.3';
    if (xaiBaseUrlEl) xaiBaseUrlEl.value = s.xai_base_url || 'https://api.x.ai/v1';

    const projTabEl = document.getElementById('settingFlowProjectIdTab') || document.getElementById('settingFlowProjectId');
    if (projTabEl && (s.default_flow_project_id || s.flow_project_id)) {
      projTabEl.value = s.default_flow_project_id || s.flow_project_id;
    }
    
    const enableTabCb = document.getElementById('settingEnableSeedImageTab') || document.getElementById('settingEnableSeedImage');
    if (enableTabCb) enableTabCb.checked = s.enable_character_seed_image !== false;

    const templateTabArea = document.getElementById('settingSeedTemplateTab') || document.getElementById('settingSeedTemplate');
    if (templateTabArea) templateTabArea.value = s.character_seed_template || DEFAULT_V41_TEMPLATE;
  } catch (err) {
    console.error('Gagal memuat settings tab:', err);
  }
}

function initSettingsModal() {
  initSettingsTab();
}

function initSettingsTab() {
  const saveBtn = document.getElementById('saveSettingsTabBtn') || document.getElementById('saveSettingsBtn');
  const testBtn = document.getElementById('testGeminiKeyTabBtn') || document.getElementById('testGeminiKeyBtn');
  const resetBtn = document.getElementById('resetSeedTemplateTabBtn') || document.getElementById('resetSeedTemplateBtn');
  const openAITestBtn = document.getElementById('testOpenAIKeyTabBtn');
  const deepSeekTestBtn = document.getElementById('testDeepSeekKeyTabBtn');
  const xaiTestBtn = document.getElementById('testXAIKeyTabBtn');

  const statusLabels = {
    valid: '✅ Valid & terhubung',
    quota_limited: '⚠️ Valid, tetapi kuota habis/terbatas',
    invalid: '❌ API key tidak sah',
    unreachable: '🌐 Tidak dapat terhubung',
    model_unavailable: '🧩 Key dikenali, tetapi model belum aktif/dibeli di workspace ini'
  };

  async function testProviderKeys(provider, keyElement, modelElement, button, resultElement, baseUrlElement = null) {
    const rawKeys = keyElement?.value.trim() || '';
    if (!rawKeys) return showToast(`Harap masukkan API key ${provider}!`, 'warning');
    const oldText = button.textContent;
    const keyCount = rawKeys.split(/[\n,]+/).map(key => key.trim()).filter(Boolean).length;
    const startedAt = Date.now();
    button.disabled = true;
    button.textContent = `⏳ Menguji ${provider}... 0s`;
    if (resultElement) resultElement.textContent = `Menguji ${keyCount} key secara paralel...`;
    const progressTimer = window.setInterval(() => {
      button.textContent = `⏳ Menguji ${provider}... ${Math.floor((Date.now() - startedAt) / 1000)}s`;
    }, 1000);
    try {
      const response = await fetch('/api/settings/test_ai_keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          api_keys: rawKeys,
          model: modelElement?.value || null,
          base_url: baseUrlElement?.value?.trim() || null
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Pengujian gagal');
      const summary = data.results.map(item => {
        const diagnostic = item.detail ? `<br><small style="color:var(--text-muted)">HTTP ${item.http_status || '-'} — ${escapeHtml(item.detail)}</small>` : '';
        return `Key #${item.index} (${item.key_preview}): ${statusLabels[item.status] || item.status}${diagnostic}`;
      }).join('<br>');
      if (resultElement) resultElement.innerHTML = summary;
      const validCount = data.results.filter(item => item.status === 'valid').length;
      showToast(`${provider}: ${validCount}/${data.results.length} key valid`, validCount ? 'success' : 'warning');
    } catch (error) {
      if (resultElement) resultElement.textContent = `❌ ${error.message}`;
      showToast(`Gagal menguji ${provider}: ${error.message}`, 'error');
    } finally {
      window.clearInterval(progressTimer);
      button.disabled = false;
      button.textContent = oldText;
    }
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      const templateArea = document.getElementById('settingSeedTemplateTab') || document.getElementById('settingSeedTemplate');
      if (templateArea) {
        templateArea.value = DEFAULT_V41_TEMPLATE;
        showToast('Template Character Sheet V4.1 di-reset ke default!', 'info');
      }
    });
  }

  if (testBtn) {
    testBtn.addEventListener('click', async () => {
      const keyEl = document.getElementById('settingGeminiKeyTab') || document.getElementById('settingGeminiKey');
      const modelEl = document.getElementById('settingGeminiModelTab') || document.getElementById('settingGeminiModel');
      await testProviderKeys('gemini', keyEl, modelEl, testBtn, document.getElementById('testGeminiKeyResult'));
    });
  }

  if (openAITestBtn) openAITestBtn.addEventListener('click', () => testProviderKeys(
    'openai', document.getElementById('settingOpenAIKeyTab'), document.getElementById('settingOpenAIModelTab'),
    openAITestBtn, document.getElementById('testOpenAIKeyResult')));
  if (deepSeekTestBtn) deepSeekTestBtn.addEventListener('click', () => testProviderKeys(
    'deepseek', document.getElementById('settingDeepSeekKeyTab'), document.getElementById('settingDeepSeekModelTab'),
    deepSeekTestBtn, document.getElementById('testDeepSeekKeyResult')));
  if (xaiTestBtn) xaiTestBtn.addEventListener('click', () => testProviderKeys(
    'xai', document.getElementById('settingXAIKeyTab'), document.getElementById('settingXAIModelTab'),
    xaiTestBtn, document.getElementById('testXAIKeyResult'), document.getElementById('settingXAIBaseUrlTab')));

  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const keyEl = document.getElementById('settingGeminiKeyTab') || document.getElementById('settingGeminiKey');
      const modelEl = document.getElementById('settingGeminiModelTab') || document.getElementById('settingGeminiModel');
      const projEl = document.getElementById('settingFlowProjectIdTab') || document.getElementById('settingFlowProjectId');
      const enableEl = document.getElementById('settingEnableSeedImageTab') || document.getElementById('settingEnableSeedImage');
      const templateEl = document.getElementById('settingSeedTemplateTab') || document.getElementById('settingSeedTemplate');
      const defaultProviderEl = document.querySelector('input[name="defaultTextProvider"]:checked');
      const openAIKeyEl = document.getElementById('settingOpenAIKeyTab');
      const deepSeekKeyEl = document.getElementById('settingDeepSeekKeyTab');
      const openAIModelEl = document.getElementById('settingOpenAIModelTab');
      const deepSeekModelEl = document.getElementById('settingDeepSeekModelTab');
      const xaiKeyEl = document.getElementById('settingXAIKeyTab');
      const xaiModelEl = document.getElementById('settingXAIModelTab');
      const xaiBaseUrlEl = document.getElementById('settingXAIBaseUrlTab');

      const rawKeys = keyEl ? keyEl.value.trim() : '';
      const model = modelEl ? modelEl.value : 'gemini-2.5-flash';
      const projId = projEl ? projEl.value.trim() : '';
      const enableSeed = enableEl ? enableEl.checked : true;
      const seedTemplate = templateEl ? templateEl.value : DEFAULT_V41_TEMPLATE;

      const keyArray = rawKeys.split(/[\n,]+/).map(k => k.trim()).filter(Boolean);

      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            gemini_api_keys: keyArray,
            gemini_model: model,
            openai_api_keys: (openAIKeyEl?.value || '').split(/[\n,]+/).map(k => k.trim()).filter(Boolean),
            openai_model: openAIModelEl?.value.trim() || 'gpt-4.1-mini',
            deepseek_api_keys: (deepSeekKeyEl?.value || '').split(/[\n,]+/).map(k => k.trim()).filter(Boolean),
            deepseek_model: deepSeekModelEl?.value.trim() || 'deepseek-chat',
            xai_api_keys: (xaiKeyEl?.value || '').split(/[\n,]+/).map(k => k.trim()).filter(Boolean),
            xai_model: xaiModelEl?.value.trim() || 'grok-4.3',
            xai_base_url: xaiBaseUrlEl?.value.trim() || 'https://api.x.ai/v1',
            default_text_provider: defaultProviderEl?.value || 'gemini',
            default_flow_project_id: projId,
            enable_character_seed_image: enableSeed,
            character_seed_template: seedTemplate
          })
        });

        const data = await res.json();
        if (!res.ok || data.detail) throw new Error(data.detail || 'Gagal menyimpan pengaturan');
        showToast('Pengaturan studio berhasil disimpan ke server!', 'success');
      } catch (err) {
        showToast('Gagal menyimpan pengaturan: ' + err.message, 'error');
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const mvForm = document.getElementById('mvForm');
  if (mvForm) {
    mvForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const audioFile = document.getElementById('mvAudioFile').files[0];
      const lyrics = document.getElementById('mvLyrics').value;
      const aspect = document.getElementById('mvAspectRatio').value;
      const charInfo = document.getElementById('mvCharacterInfo').value;
      const btn = document.getElementById('btnGenerateMV');
      
      if (!audioFile) {
        showToast('Pilih file audio lagu terlebih dahulu.', 'error');
        return;
      }
      
      btn.disabled = true;
      btn.innerHTML = '<span class="icon">⏳</span> Menganalisa Lagu & Generating MV Storyboard...';
      
      try {
        const actorCheckboxes = document.querySelectorAll('#actorSelectionList_mv input[type="checkbox"]:checked');
        const actorIds = Array.from(actorCheckboxes).map(cb => cb.value).join(',');
        
        const formData = new FormData();
        formData.append('actor_ids', actorIds);
        formData.append('audio_file', audioFile);
        formData.append('lyrics', lyrics);
        formData.append('aspect_ratio', aspect);
        formData.append('character_info', charInfo);
        
        const res = await fetch('/api/storyboard/generate-mv', {
          method: 'POST',
          body: formData
        });
        
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.detail || 'Gagal generate MV storyboard');
        
        // Auto-save the generated MV storyboard to Scene Master so it is not lost
        if (data.storyboard) {
          saveStoryboardToHistory(data.storyboard);
          // Optionally set it as current so the Scene Master studio panel displays it
          if (typeof currentStoryboard !== 'undefined') currentStoryboard = data.storyboard;
        }
        
        showToast('Music Video Storyboard berhasil di-generate! Memulai proses render...', 'success');
        
        const executeRes = await fetch('/api/jobs/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            storyboard: data.storyboard,
            aspect_ratio: aspect,
            force_uniform_duration: true
          })
        });
        
        const execData = await executeRes.json();
        if(execData.success) {
            showToast('Proses render Music Video dimulai!', 'success');
            document.querySelector('[data-tab="tab-execution"]').click();
            
            startJobPolling(execData.job_id);
        } else {
            throw new Error(execData.detail || 'Gagal memulai job');
        }
      } catch (err) {
        showToast(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="icon">✨</span> Generate MV Storyboard';
      }
    });
  }
  
  // Actor Registry Logic
  const MAX_ACTOR_REFERENCE_IMAGES = 4;
  let selectedActorReferenceFiles = [];
  let actorPreviewUrls = [];

  const actorImagesInput = document.getElementById('actorImages');
  const actorImagePreview = document.getElementById('actorImagePreview');
  const actorImageCount = document.getElementById('actorImageCount');

  const renderActorImagePreview = () => {
      actorPreviewUrls.forEach(url => URL.revokeObjectURL(url));
      actorPreviewUrls = [];
      if (actorImageCount) actorImageCount.textContent = `${selectedActorReferenceFiles.length}/${MAX_ACTOR_REFERENCE_IMAGES}`;
      if (!actorImagePreview) return;
      actorImagePreview.innerHTML = selectedActorReferenceFiles.map((file, index) => {
          const url = URL.createObjectURL(file);
          actorPreviewUrls.push(url);
          return `<div class="actor-reference-preview-item">
              <img src="${url}" alt="Referensi ${index + 1}">
              ${index === 0 ? '<span class="actor-reference-primary">Utama</span>' : ''}
              <button type="button" class="actor-reference-remove" data-index="${index}" title="Hapus gambar">×</button>
          </div>`;
      }).join('');
  };

  if (actorImagesInput) {
      actorImagesInput.addEventListener('change', () => {
          const chosen = Array.from(actorImagesInput.files || []);
          if (chosen.length > MAX_ACTOR_REFERENCE_IMAGES) {
              showToast(`Maksimal ${MAX_ACTOR_REFERENCE_IMAGES} gambar untuk satu karakter.`, 'warning');
          }
          selectedActorReferenceFiles = chosen.slice(0, MAX_ACTOR_REFERENCE_IMAGES);
          renderActorImagePreview();
      });
  }
  if (actorImagePreview) {
      actorImagePreview.addEventListener('click', (event) => {
          const button = event.target.closest('.actor-reference-remove');
          if (!button) return;
          selectedActorReferenceFiles.splice(Number(button.dataset.index), 1);
          if (actorImagesInput) actorImagesInput.value = '';
          renderActorImagePreview();
      });
  }

  const fetchActors = async () => {
      try {
          const res = await fetch('/api/actors');
          const data = await res.json();
          if (data.success) {
              renderActors(data.actors);
              renderActorCheckboxes(data.actors);
          }
      } catch (err) {
          console.error("Gagal load aktor:", err);
      }
  };
  
  const renderActors = (actors) => {
      const grid = document.getElementById('actorsGrid');
      if (!grid) return;
      grid.innerHTML = '';
      
      if (actors.length === 0) {
          grid.innerHTML = '<div class="empty-state"><h4>Belum Ada Aktor</h4><p>Daftarkan wajah baru untuk menggunakannya di storyboard.</p></div>';
          return;
      }
      
      actors.forEach(actor => {
          const actorImages = (actor.images && actor.images.length)
              ? actor.images
              : (actor.image_url ? [{ url: actor.image_url, primary: true }] : []);
          const primaryImage = actorImages[0] ? actorImages[0].url : '';
          const secondaryImages = actorImages.slice(1, 4);
          const card = document.createElement('div');
          card.style = "background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column;";
          card.innerHTML = `
            <img src="${primaryImage}" alt="${actor.name}" style="width: 100%; height: 200px; object-fit: cover;">
            ${secondaryImages.length ? `<div class="actor-card-reference-strip">${secondaryImages.map((image, index) =>
                `<img src="${image.url}" alt="Referensi ${index + 2} ${actor.name}">`).join('')}</div>` : ''}
            <div style="padding: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #fff;">${actor.name}</h4>
                <span class="actor-reference-count">${actorImages.length} Referensi</span>
                <p style="margin: 0 0 12px 0; color: #aaa; font-size: 13px; min-height: 40px;">${actor.description}</p>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-family: monospace;">Seed: ${actor.seed}</span>
                    <button class="btn-secondary" onclick="deleteActor('${actor.id}')" style="padding: 4px 10px; font-size: 12px; border-color: #ef4444; color: #ef4444;">Hapus</button>
                </div>
            </div>
          `;
          grid.appendChild(card);
      });
  };
  
  const renderActorCheckboxes = (actors) => {
      const containerSB = document.getElementById('actorSelectionList_storyboard');
      const containerMV = document.getElementById('actorSelectionList_mv');
      
      let html = '';
      if (actors.length === 0) {
          html = '<span style="color: #aaa; font-size: 13px;">Belum ada aktor tersimpan.</span>';
      } else {
          actors.forEach(actor => {
              html += `
              <label style="display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.3); padding: 6px 12px; border-radius: 20px; cursor: pointer;">
                  <input type="checkbox" value="${actor.id}" style="accent-color: #38bdf8;">
                  <img src="${(actor.images && actor.images[0] ? actor.images[0].url : actor.image_url)}" style="width: 20px; height: 20px; border-radius: 50%; object-fit: cover;">
                  <span style="color: #fff; font-size: 13px;">${actor.name}</span>
              </label>
              `;
          });
      }
      
      if (containerSB) containerSB.innerHTML = html;
      if (containerMV) containerMV.innerHTML = html;
  };
  
  window.deleteActor = async (actorId) => {
      if(!confirm("Yakin ingin menghapus aktor ini?")) return;
      try {
          const res = await fetch('/api/actors/' + actorId, { method: 'DELETE' });
          if(res.ok) {
              showToast("Aktor berhasil dihapus!", "success");
              fetchActors();
          }
      } catch (err) {
          showToast("Gagal menghapus aktor", "error");
      }
  };
  
  const addActorForm = document.getElementById('addActorForm');
  if (addActorForm) {
      addActorForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          const name = document.getElementById('actorName').value;
          const desc = document.getElementById('actorDesc').value;
          const seed = document.getElementById('actorSeed').value;
          if(!selectedActorReferenceFiles.length) return showToast("Minimal satu gambar referensi karakter wajib diunggah", "error");
          
          const formData = new FormData();
          formData.append('name', name);
          formData.append('description', desc);
          selectedActorReferenceFiles.forEach(image => formData.append('image_files', image));
          if (seed) formData.append('seed', parseInt(seed));
          
          try {
              const res = await fetch('/api/actors', { method: 'POST', body: formData });
              if (res.ok) {
                  showToast("Aktor berhasil didaftarkan!", "success");
                  document.getElementById('addActorModal').classList.remove('active');
                  addActorForm.reset();
                  selectedActorReferenceFiles = [];
                  renderActorImagePreview();
                  fetchActors();
              }
          } catch(err) {
              showToast("Gagal mendaftarkan aktor", "error");
          }
      });
  }
  
  // Initial load
  fetchActors();
});
