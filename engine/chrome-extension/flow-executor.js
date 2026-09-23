/**
 * Sinematica Flow Agent - Task Flow Executor
 * Automates project initialization, multi-image reference upload (synthetic DataTransfer & In-Page RPC),
 * prompt typing, image generation trigger, video settings configuration, video render trigger,
 * background render progress monitoring, and safe video delivery back to Sinematica.
 */

(function (global) {
  'use strict';

  const FRIENDLY_STEPS = {
    INIT: 'Menyiapkan sesi Google Flow...',
    ENSURE_PROJECT: 'Membuka atau membuat proyek baru di Google Flow...',
    CONFIGURING_MODE: 'Mengatur rasio aspek dan mode potret (9:16)...',
    UPLOADING_IMAGE: 'Mengunggah gambar referensi produk ke Google Flow...',
    UPLOADING_MULTI_IMAGES: 'Mengunggah beberapa gambar referensi produk ke Google Flow secara bersamaan...',
    IMAGE_UPLOADED: 'Semua gambar produk berhasil diunggah ke slot aset Google Flow.',
    ATTACHING_REFERENCE: 'Memasukkan gambar referensi ke dalam prompt komposisi...',
    TYPING_PROMPT: 'Mengisi teks prompt AI otomatis...',
    TRIGGERING_GENERATION: 'Menjalankan pembuatan gambar awal...',
    WAITING_IMAGE: 'Menunggu hasil generasi gambar awal dari Google Flow...',
    IMAGE_READY: 'Gambar awal berhasil dibuat!',
    POLLING_PROGRESS: 'Memantau render gambar/video di Google Flow...',
    DELIVERING_IMAGE: 'Mengirimkan hasil gambar karakter dan metadata ke Sinematica...',
    ATTACHING_IMAGE_TO_VIDEO: 'Menyambungkan gambar hasil generasi sebagai referensi video...',
    CONFIGURING_VIDEO: 'Mengatur opsi video affiliator optimal (9:16 potret, Veo/Omni, durasi terbaik)...',
    TYPING_VIDEO_PROMPT: 'Mengisi prompt gerakan video affiliator...',
    TRIGGERING_VIDEO: 'Menjalankan render video di Google Flow...',
    RENDERING_VIDEO: 'Sedang memproses render video di Google Flow...',
    VIDEO_READY: 'Video affiliator selesai dirender dan siap diunduh!',
    DELIVERING_VIDEO: 'Mengirimkan hasil video dan metadata ke Sinematica...',
    COMPLETED: 'Video affiliator berhasil dibuat dan diterima di Sinematica!',
    FAILED: 'Terjadi kendala pada alur otomasi Google Flow.',
  };

  const SELECTORS = {
    PROMPT_INPUT: '.ProseMirror, [role="textbox"], [contenteditable="true"], textarea',
    ADD_MEDIA_BUTTONS: 'button, [role="button"]',
    CREATE_BUTTONS: 'button, [role="button"], a',
    SETTINGS_PILL: 'button, [role="button"], div[role="button"]',
  };

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function waitFor(predicate, timeoutMs = 30000, pollIntervalMs = 500) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      function check() {
        try {
          const res = predicate();
          if (res) return resolve(res);
        } catch (e) {
          // ignore predicate error and keep polling
        }
        if (Date.now() - start > timeoutMs) {
          return reject(new Error(`Timeout waiting for condition after ${timeoutMs}ms`));
        }
        setTimeout(check, pollIntervalMs);
      }
      check();
    });
  }

  function b64toBlob(b64Data, contentType) {
    if (typeof b64Data !== 'string') return null;
    let clean = b64Data;
    if (clean.includes('base64,')) {
      clean = clean.split('base64,')[1];
    }
    clean = clean.trim();

    if (typeof atob === 'undefined' && typeof Buffer !== 'undefined') {
      const buf = Buffer.from(clean, 'base64');
      return typeof Blob !== 'undefined' ? new Blob([buf], { type: contentType }) : { type: contentType, size: buf.length };
    }

    const byteCharacters = typeof atob === 'function' ? atob(clean) : '';
    const byteArrays = [];
    for (let offset = 0; offset < byteCharacters.length; offset += 512) {
      const slice = byteCharacters.slice(offset, offset + 512);
      const byteNumbers = new Array(slice.length);
      for (let i = 0; i < slice.length; i++) {
        byteNumbers[i] = slice.charCodeAt(i);
      }
      byteArrays.push(new Uint8Array(byteNumbers));
    }
    return typeof Blob !== 'undefined' ? new Blob(byteArrays, { type: contentType }) : { type: contentType };
  }

  const BLOCKED_EVENT_TYPES = [
    'click',
    'dblclick',
    'mousedown',
    'mouseup',
    'pointerdown',
    'pointerup',
    'pointermove',
    'contextmenu',
    'keydown',
    'keyup',
    'keypress',
    'wheel',
    'touchstart',
    'touchend',
    'touchmove',
    'selectstart',
    'dragstart',
  ];

  function isFlowErrorCard(element) {
    if (!element) return false;
    const tagName = (element.tagName || '').toLowerCase();
    if (tagName === 'flow-error-tile' || (element.classList && (element.classList.contains('error-tile') || element.classList.contains('flow-error-tile')))) {
      return true;
    }
    if (element.querySelector && element.querySelector('flow-error-tile, .error-tile, [class*="error-tile"]')) {
      return true;
    }
    const text = (element.innerText || element.textContent || '').toLowerCase();
    return (
      text.includes('gagal') ||
      text.includes('gagal dibuat') ||
      text.includes('maaf, video ini gagal') ||
      text.includes('maaf, gambar ini gagal') ||
      text.includes('tidak perlu menggunakan kredit') ||
      text.includes('kebijakan') ||
      text.includes('policy') ||
      text.includes('melanggar') ||
      text.includes('violate') ||
      text.includes('berbahaya') ||
      text.includes('harmful') ||
      text.includes('coba perintah lain') ||
      text.includes('try another prompt') ||
      text.includes('tokoh berpengaruh') ||
      text.includes('public figure') ||
      text.includes('kesalahan pembuatan') ||
      text.includes('failed to generate') ||
      text.includes('generation failed') ||
      text.includes('video failed') ||
      text.includes('image failed') ||
      text.includes('sorry, this video failed') ||
      text.includes('sorry, this image failed') ||
      text.includes('will not be charged') ||
      text.includes('were not charged') ||
      text.includes('not need to use credits') ||
      text.includes('could not generate')
    );
  }

  function findRetryButtonInCard(card) {
    if (!card) return null;
    return card.querySelector(
      'button[aria-label*="coba lagi" i], button[aria-label*="retry" i], button[aria-label*="try again" i], button[aria-label*="refresh" i], button[aria-label*="ulang" i], button[title*="coba lagi" i], button[title*="retry" i], button[title*="try again" i]'
    ) || Array.from(card.querySelectorAll('button')).find((b) => {
      const text = (b.innerText || b.getAttribute('aria-label') || b.title || '').toLowerCase();
      const matIconText = (b.querySelector('mat-icon, .mat-icon, i, span')?.innerText || '').toLowerCase();
      return (
        text.includes('retry') ||
        text.includes('refresh') ||
        text.includes('coba lagi') ||
        text.includes('try again') ||
        text.includes('ulang') ||
        matIconText.includes('refresh') ||
        matIconText.includes('replay') ||
        matIconText.includes('retry') ||
        matIconText.includes('redo') ||
        matIconText.includes('cached') ||
        matIconText.includes('autorenew') ||
        matIconText.includes('sync') ||
        matIconText.includes('restart_alt') ||
        matIconText.includes('loop')
      );
    }) || Array.from(card.querySelectorAll('button')).find((b) => {
      const txt = (b.innerText || b.getAttribute('aria-label') || b.title || '').toLowerCase();
      const matIcon = (b.querySelector('mat-icon, .mat-icon, i, span')?.innerText || '').toLowerCase();
      const isDelete = txt.includes('delete') || txt.includes('hapus') || txt.includes('trash') || matIcon.includes('delete') || matIcon.includes('trash');
      const isFeedback = txt.includes('feedback') || txt.includes('masukan') || txt.includes('lapor') || matIcon.includes('feedback') || matIcon.includes('chat') || matIcon.includes('flag') || matIcon.includes('comment');
      return !isDelete && !isFeedback;
    }) || card.querySelector('button');
  }

  let isInteractionBlocked = false;
  const activeBlockerListeners = [];

  function isAllowInput() {
    if (typeof document !== 'undefined' && document.documentElement && document.documentElement.dataset && document.documentElement.dataset.sinematicaAllowInput === 'true') {
      return true;
    }
    if (typeof window !== 'undefined' && (window.__sinematicaAllowNativeInput || window.__sinematicaAllowInput)) {
      return true;
    }
    if (typeof globalThis !== 'undefined' && (globalThis.__sinematicaAllowNativeInput || globalThis.__sinematicaAllowInput)) {
      return true;
    }
    return false;
  }

  function setAllowInput(allow) {
    if (typeof document !== 'undefined' && document.documentElement && document.documentElement.dataset) {
      if (allow) {
        document.documentElement.dataset.sinematicaAllowInput = 'true';
      } else {
        delete document.documentElement.dataset.sinematicaAllowInput;
      }
    }
    if (typeof window !== 'undefined') {
      window.__sinematicaAllowNativeInput = Boolean(allow);
      window.__sinematicaAllowInput = Boolean(allow);
    }
    if (typeof globalThis !== 'undefined') {
      globalThis.__sinematicaAllowNativeInput = Boolean(allow);
      globalThis.__sinematicaAllowInput = Boolean(allow);
    }
    const blocker = typeof document !== 'undefined' && typeof document.getElementById === 'function'
      ? document.getElementById('sinematica-interaction-blocker')
      : null;
    if (blocker && blocker.style) {
      if (typeof blocker.style.setProperty === 'function') {
        blocker.style.setProperty('pointer-events', allow ? 'none' : 'auto', 'important');
      } else {
        blocker.style.pointerEvents = allow ? 'none' : 'auto';
      }
    }
  }

  const BLOCKED_KEY_TYPES = ['keydown', 'keyup', 'keypress'];

  function blockKeyListener(e) {
    if (!isInteractionBlocked) return;
    if (isAllowInput()) return;
    if (e && (e.__sinematicaSynthetic || !e.isTrusted)) return;
    try {
      if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
      if (typeof e.stopPropagation === 'function') e.stopPropagation();
      if (typeof e.preventDefault === 'function') e.preventDefault();
    } catch (_) {}
    return false;
  }

  function blockUserInteraction() {
    isInteractionBlocked = true;
    if (typeof document === 'undefined') return;

    let blocker = typeof document.getElementById === 'function' ? document.getElementById('sinematica-interaction-blocker') : null;
    if (!blocker && typeof document.createElement === 'function') {
      blocker = document.createElement('div');
      blocker.id = 'sinematica-interaction-blocker';
      blocker.style.cssText = [
        'position: fixed',
        'top: 0',
        'left: 0',
        'width: 100vw',
        'height: 100vh',
        'z-index: 2147483646',
        'background: transparent',
        'cursor: wait',
        'user-select: none',
        '-webkit-user-select: none',
        'touch-action: none',
        'pointer-events: auto',
      ].join('; ');

      const blockPointerEvent = (e) => {
        if (isAllowInput()) return;
        if (e && (e.__sinematicaSynthetic || !e.isTrusted)) return;
        try {
          e.stopPropagation();
          e.preventDefault();
        } catch (_) {}
      };

      const POINTER_BLOCK_TYPES = ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click', 'dblclick', 'contextmenu', 'touchstart', 'touchend', 'touchmove', 'wheel'];
      POINTER_BLOCK_TYPES.forEach((type) => {
        try { blocker.addEventListener(type, blockPointerEvent, true); } catch (_) {}
      });

      const parent = document.body || document.documentElement;
      if (parent && typeof parent.appendChild === 'function') {
        parent.appendChild(blocker);
      }
    }

    let fakeCursor = typeof document.getElementById === 'function' ? document.getElementById('sinematica-fake-cursor') : null;
    if (!fakeCursor && typeof document.createElement === 'function') {
      fakeCursor = document.createElement('div');
      fakeCursor.id = 'sinematica-fake-cursor';
      fakeCursor.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5.5 2.5L22.5 10.5L14.5 13.5L11.5 21.5L5.5 2.5Z" fill="#0a84ff" stroke="white" stroke-width="2" stroke-linejoin="round"/></svg>';
      fakeCursor.style.cssText = [
        'position: fixed',
        'top: 50vh',
        'left: 50vw',
        'z-index: 2147483647',
        'pointer-events: none',
        'transition: top 0.35s cubic-bezier(0.22, 1, 0.36, 1), left 0.35s cubic-bezier(0.22, 1, 0.36, 1), transform 0.15s ease',
        'transform-origin: top left',
        'width: 28px',
        'height: 28px',
        'margin-left: -4px',
        'margin-top: -4px',
      ].join('; ');
      const style = document.createElement('style');
      style.textContent = `
        @keyframes sinematicaClickRipple { 
          0% { transform: translate(-50%, -50%) scale(0.5); opacity: 0.8; }
          100% { transform: translate(-50%, -50%) scale(2); opacity: 0; }
        }
        #sinematica-fake-cursor.clicking::after {
          content: '';
          position: absolute;
          top: 2px;
          left: 2px;
          width: 24px;
          height: 24px;
          border-radius: 50%;
          background: rgba(10, 132, 255, 0.4);
          border: 2px solid #0a84ff;
          animation: sinematicaClickRipple 0.3s ease-out forwards;
          pointer-events: none;
        }
      `;
      fakeCursor.appendChild(style);
      const parent = document.body || document.documentElement;
      if (parent && typeof parent.appendChild === 'function') {
        parent.appendChild(fakeCursor);
      }
    }

    if (activeBlockerListeners.length === 0) {
      BLOCKED_KEY_TYPES.forEach((type) => {
        if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
          try { window.addEventListener(type, blockKeyListener, { capture: true, passive: false }); } catch (_) {}
        }
        activeBlockerListeners.push(type);
      });
    }
  }

  function unblockUserInteraction() {
    isInteractionBlocked = false;
    setAllowInput(false);

    if (activeBlockerListeners.length > 0) {
      activeBlockerListeners.forEach((type) => {
        if (typeof window !== 'undefined' && typeof window.removeEventListener === 'function') {
          try {
            window.removeEventListener(type, blockKeyListener, { capture: true, passive: false });
            window.removeEventListener(type, blockKeyListener, true);
            window.removeEventListener(type, blockKeyListener);
          } catch (_) {}
        }
      });
      activeBlockerListeners.length = 0;
    }

    if (typeof document !== 'undefined' && typeof document.getElementById === 'function') {
      const blocker = document.getElementById('sinematica-interaction-blocker');
      if (blocker) {
        if (typeof blocker.remove === 'function') {
          blocker.remove();
        } else if (blocker.parentNode && typeof blocker.parentNode.removeChild === 'function') {
          blocker.parentNode.removeChild(blocker);
        }
      }

      const fakeCursor = document.getElementById('sinematica-fake-cursor');
      if (fakeCursor) {
        if (typeof fakeCursor.remove === 'function') {
          fakeCursor.remove();
        } else if (fakeCursor.parentNode && typeof fakeCursor.parentNode.removeChild === 'function') {
          fakeCursor.parentNode.removeChild(fakeCursor);
        }
      }
    }
  }

  function ensureVisualAutomationElements() {
    blockUserInteraction();
  }

  async function animateFakeCursor(clientX, clientY, isClick = true) {
    if (typeof document === 'undefined' || typeof document.getElementById !== 'function') return;
    ensureVisualAutomationElements();
    const cursor = document.getElementById('sinematica-fake-cursor');
    if (!cursor) return;

    cursor.style.left = `${Math.round(clientX)}px`;
    cursor.style.top = `${Math.round(clientY)}px`;

    if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
      await new Promise((r) => setTimeout(r, 350));
    }

    if (isClick) {
      cursor.classList.add('clicking');
      if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
        await new Promise((r) => setTimeout(r, 180));
      }
      cursor.classList.remove('clicking');
    }
  }

  async function simulateClick(element) {
    if (!element) return false;
    ensureVisualAutomationElements();
    setAllowInput(true);
    try {
      try {
        if (typeof element.scrollIntoView === 'function') {
          element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        }
      } catch {}

      const rect = typeof element.getBoundingClientRect === 'function'
        ? element.getBoundingClientRect()
        : { left: 0, top: 0, width: 20, height: 20 };
      const clientX = Math.round((rect.left || 0) + (rect.width || 0) / 2);
      const clientY = Math.round((rect.top || 0) + (rect.height || 0) / 2);

      animateFakeCursor(clientX, clientY, true).catch(() => {});

      if (typeof element.focus === 'function') {
        try { element.focus(); } catch {}
      }

      const targets = [];
      const innerTarget = typeof element.querySelector === 'function'
        ? element.querySelector('.mat-mdc-button-touch-target, mat-icon, svg, button')
        : null;
      if (innerTarget && innerTarget !== element) {
        targets.push(innerTarget);
      }
      targets.push(element);
      if (element.parentElement && element.parentElement.tagName.toLowerCase().startsWith('flow-')) {
        targets.push(element.parentElement);
      }

      for (const target of targets) {
        const downInit = {
          bubbles: true,
          cancelable: true,
          composed: true,
          view: typeof window !== 'undefined' ? window : null,
          clientX,
          clientY,
          screenX: clientX,
          screenY: clientY,
          button: 0,
          buttons: 1,
          pressure: 0.5,
          isPrimary: true,
          pointerType: 'mouse',
          detail: 1,
          __sinematicaSynthetic: true,
        };

        const upInit = {
          ...downInit,
          buttons: 0,
          pressure: 0,
        };

        if (typeof PointerEvent !== 'undefined') {
          try { target.dispatchEvent(new PointerEvent('pointerover', upInit)); } catch {}
          try { target.dispatchEvent(new PointerEvent('pointerenter', upInit)); } catch {}
          try { target.dispatchEvent(new PointerEvent('pointerdown', downInit)); } catch {}
        }
        if (typeof MouseEvent !== 'undefined') {
          try { target.dispatchEvent(new MouseEvent('mouseover', upInit)); } catch {}
          try { target.dispatchEvent(new MouseEvent('mouseenter', upInit)); } catch {}
          try { target.dispatchEvent(new MouseEvent('mousedown', downInit)); } catch {}
        }
        if (typeof PointerEvent !== 'undefined') {
          try { target.dispatchEvent(new PointerEvent('pointerup', upInit)); } catch {}
        }
        if (typeof MouseEvent !== 'undefined') {
          try { target.dispatchEvent(new MouseEvent('mouseup', upInit)); } catch {}
          try { target.dispatchEvent(new MouseEvent('click', upInit)); } catch {}
        }
      }

      if (typeof element.click === 'function') {
        try {
          element.click();
        } catch {}
      }

      const form = typeof element.closest === 'function' ? element.closest('form') : null;
      if (form && typeof form.requestSubmit === 'function') {
        try { form.requestSubmit(element); } catch {}
      }

      if (typeof chrome !== 'undefined' && chrome.runtime && typeof chrome.runtime.sendMessage === 'function') {
        try {
          await new Promise((resolve) => {
            chrome.runtime.sendMessage({ type: 'DISPATCH_NATIVE_CLICK', x: clientX, y: clientY }, (response) => {
              if (chrome.runtime.lastError) resolve(null);
              else resolve(response);
            });
          });
        } catch (_) {}
      }

      if (typeof window !== 'undefined' && typeof window.setTimeout === 'function') {
        await new Promise((r) => setTimeout(r, 60));
      }
      return true;
    } finally {
      setAllowInput(false);
    }
  }

  async function simulateInput(element, text) {
    if (!element) return false;
    ensureVisualAutomationElements();
    setAllowInput(true);
    try {
      const rect = typeof element.getBoundingClientRect === 'function'
        ? element.getBoundingClientRect()
        : { left: 0, top: 0, width: 20, height: 20 };
      const clientX = (rect.left || 0) + (rect.width || 0) / 2;
      const clientY = (rect.top || 0) + (rect.height || 0) / 2;

      await animateFakeCursor(clientX, clientY, true);

      if (typeof element.focus === 'function') element.focus();

      const isEditable = element.isContentEditable ||
        (typeof element.getAttribute === 'function' && element.getAttribute('contenteditable') === 'true');

      if (isEditable) {
        try {
          if (typeof document !== 'undefined' && typeof DataTransfer !== 'undefined') {
            const dt = new DataTransfer();
            dt.setData('text/plain', text);
            element.dispatchEvent(new ClipboardEvent('paste', {
              bubbles: true,
              cancelable: true,
              composed: true,
              clipboardData: dt,
              __sinematicaSynthetic: true,
            }));
          }
        } catch (_) {}

        const hasChips = typeof element.querySelector === 'function' && !!element.querySelector('flow-media-chip, flow-ingredient-chip, [data-ingredient-id], .chip, img, [data-atom]');
        if (!hasChips) {
          try {
            if (typeof window !== 'undefined' && typeof document !== 'undefined') {
              const selection = window.getSelection();
              if (selection && typeof selection.selectAllChildren === 'function') {
                selection.selectAllChildren(element);
              } else if (selection) {
                const range = document.createRange();
                range.selectNodeContents(element);
                selection.removeAllRanges();
                selection.addRange(range);
              }
              if (typeof document.execCommand === 'function') {
                document.execCommand('insertText', false, text);
              }
            }
          } catch {}

          if (!element.textContent || !element.textContent.includes(text.slice(0, 10))) {
            element.innerText = text;
            element.textContent = text;
          }
        } else {
          try {
            if (typeof document !== 'undefined' && typeof document.execCommand === 'function') {
              document.execCommand('insertText', false, text);
            }
          } catch {}
        }

        if (typeof element.dispatchEvent === 'function') {
          try {
            if (typeof InputEvent !== 'undefined') {
              element.dispatchEvent(new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: text,
                composed: true,
                __sinematicaSynthetic: true,
              }));
              element.dispatchEvent(new InputEvent('input', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: text,
                composed: true,
                __sinematicaSynthetic: true,
              }));
            }
            if (typeof Event !== 'undefined') {
              element.dispatchEvent(new Event('input', { bubbles: true, composed: true, __sinematicaSynthetic: true }));
              element.dispatchEvent(new Event('change', { bubbles: true, composed: true, __sinematicaSynthetic: true }));
            }
            if (typeof KeyboardEvent !== 'undefined') {
              try {
                element.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', code: 'KeyA', bubbles: true, composed: true, __sinematicaSynthetic: true }));
                element.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', code: 'KeyA', bubbles: true, composed: true, __sinematicaSynthetic: true }));
              } catch {}
            }
          } catch {
            try {
              element.dispatchEvent(new Event('input', { bubbles: true, composed: true, __sinematicaSynthetic: true }));
            } catch {}
          }
        }
      } else {
        element.value = text;
        if (typeof element.dispatchEvent === 'function') {
          try {
            element.dispatchEvent(new Event('input', { bubbles: true, __sinematicaSynthetic: true }));
            element.dispatchEvent(new Event('change', { bubbles: true, __sinematicaSynthetic: true }));
          } catch {}
        }
      }
      return true;
    } finally {
      setAllowInput(false);
    }
  }

  class FlowTaskExecutor {
    constructor(options = {}) {
      this.onProgress = options.onProgress || (() => {});
      this.onCompleted = options.onCompleted || (() => {});
      this.onError = options.onError || (() => {});
      this.currentTaskId = null;
      this.isRunning = false;
      this.interceptedEvents = [];
    }

    notifyProgress(stage, message, extra = {}) {
      const friendly = FRIENDLY_STEPS[stage] || message || stage;
      this.onProgress({
        taskId: this.currentTaskId,
        stage,
        message: friendly,
        timestamp: Date.now(),
        ...extra,
      });
    }

    handleNetworkEvent(event) {
      if (!event || !event.type) return;
      this.interceptedEvents.push({ ...event, receivedAt: Date.now() });
    }

    async waitForNetworkEvent(eventType, timeoutMs = 180000, sinceTimestamp = 0) {
      const startTime = Date.now();
      const minTime = sinceTimestamp > 0 ? (sinceTimestamp - 10000) : (this.taskStartTime || startTime - 10000);

      while (Date.now() - startTime < timeoutMs) {
        if (this.isCancelled) {
          throw new Error('Task aborted');
        }

        const errEvent = this.interceptedEvents.find(
          (e) => (e.type === 'ERROR' || e.status === 'ERROR')
        );
        if (errEvent) {
          throw new Error(errEvent.friendlyMessage || errEvent.rawError || 'Google Flow API Error');
        }

        const match = this.interceptedEvents.find(
          (e) => (e.type === eventType || e.status === eventType) && (e.receivedAt || 0) >= minTime
        );
        if (match) return match;

        await sleep(50);
      }
      throw new Error(`Waktu tunggu respon ${eventType} telah habis (${timeoutMs / 1000}s).`);
    }

    async waitForImageGenerationDomDone(timeoutMs = 180000, sinceTimestamp = 0, maxRetries = 2) {
      if (typeof document === 'undefined') return true;
      const startTime = Date.now();
      let retryCount = 0;

      const isGeneratedMediaUrl = (url) => {
        if (!url || typeof url !== 'string') return false;
        if (url.startsWith('blob:') || url.startsWith('data:image/')) return true;
        if (url.includes('avatar') || url.includes('logo') || url.includes('icon') || url.includes('svg') || url.includes('profile_photo') || url.includes('ring') || url.includes('/gb/')) {
          return false;
        }
        try {
          const parsed = new URL(url);
          if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return false;
          if (parsed.hostname.endsWith('.gstatic.com')) return false;
          return parsed.hostname === 'flow-content.google'
            || parsed.hostname === 'flow.google.com'
            || parsed.hostname.endsWith('.googleusercontent.com')
            || parsed.hostname === 'storage.googleapis.com';
        } catch (_) {
          return false;
        }
      };

      const tileSelector = 'flow-image-tile, flow-image-card, flow-media-tile, flow-grid-tile-container, flow-tile-container, flow-scene-tile, [class*="project-tile"], [data-tile-type="image"]';

      // Track existing image sources present at the start of generation
      const initialImageSrcs = new Set();
      try {
        const initialTiles = Array.from(document.querySelectorAll(tileSelector));
        initialTiles.forEach((tile) => {
          const img = tile.querySelector('img');
          const src = img ? (img.currentSrc || img.src) : null;
          if (src && isGeneratedMediaUrl(src)) {
            initialImageSrcs.add(src);
          }
        });
      } catch (_) {}

      await sleep(1500);

      while (Date.now() - startTime < timeoutMs) {
        if (this.isCancelled) {
          throw new Error('Task aborted');
        }

        const imageTiles = Array.from(document.querySelectorAll(tileSelector));
        const loadedTiles = imageTiles.filter((tile) => {
          const isError = isFlowErrorCard(tile);
          const text = tile.innerText || tile.textContent || '';
          const isProgress = /\b\d{1,2}%\b/.test(text) || /generating/i.test(text);
          const img = tile.querySelector('img');
          const src = img ? (img.currentSrc || img.src) : null;
          return !isError && !isProgress && img && (img.naturalWidth > 0 || img.complete) && src && isGeneratedMediaUrl(src);
        });

        // Newly generated tiles (not present initially)
        const newLoadedTiles = loadedTiles.filter((tile) => {
          const img = tile.querySelector('img');
          const src = img ? (img.currentSrc || img.src) : null;
          return src && !initialImageSrcs.has(src);
        });

        const spinners = document.querySelectorAll('mat-spinner, .generating-spinner, [role="progressbar"], [aria-label*="generating" i], [aria-label*="loading" i]');
        const hasActiveGeneratingSpinner = Array.from(spinners).some((s) => s.offsetParent !== null || s.style.display !== 'none');

        const hasGeneratingProgressText = imageTiles.some((t) => {
          const text = t.innerText || t.textContent || '';
          return /\b\d{1,2}%\b/.test(text) || /generating/i.test(text);
        });

        for (const tile of imageTiles) {
          const text = tile.innerText || tile.textContent || '';
          const m = text.match(/\b(\d{1,2})%\b/);
          if (m && m[1] && m[1] !== this._lastReportedDomImagePct) {
            this._lastReportedDomImagePct = m[1];
            this.notifyProgress('POLLING_PROGRESS', `Memantau render gambar di Google Flow (${m[1]}%)...`, { percent: Number(m[1]) });
            break;
          }
        }

        const errorSelectors = [
          'flow-error-tile', '.error-tile', '.error-message', '.error-tile-content',
          'flow-image-tile:has(flow-error-tile)', 'flow-grid-tile-container:has(flow-error-tile)', 'flow-tile-container:has(flow-error-tile)',
          'flow-image-tile:has([class*="error"])', 'flow-grid-tile-container:has([class*="error"])', 'flow-tile-container:has([class*="error"])',
        ];
        let errorTile = document.querySelector(errorSelectors.join(', ')) ||
          imageTiles.find((t) => isFlowErrorCard(t)) || null;

        const effectiveLoaded = newLoadedTiles.length > 0 ? newLoadedTiles : (initialImageSrcs.size === 0 ? loadedTiles : []);

        if (!hasActiveGeneratingSpinner && !hasGeneratingProgressText && effectiveLoaded.length > 0) {
          if (errorTile) {
            const removeBtn = errorTile.querySelector('button[aria-label*="Remove" i], button[aria-label*="Delete" i], button[aria-label*="Hapus" i]');
            if (removeBtn) await simulateClick(removeBtn);
            else errorTile.remove();
          }

          const newestTile = effectiveLoaded[0];
          const newestImg = newestTile ? newestTile.querySelector('img') : null;
          let foundMediaId = newestImg ? (newestImg.getAttribute('data-media-id') || newestImg.getAttribute('data-id')) : null;
          const imgSrc = newestImg ? (newestImg.currentSrc || newestImg.src) : null;
          if (!foundMediaId && imgSrc) {
            const m = imgSrc.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
            if (m && m[1]) foundMediaId = m[1];
          }
          return {
            src: imgSrc,
            mediaId: foundMediaId || imgSrc,
          };
        }

        if (!hasActiveGeneratingSpinner && !hasGeneratingProgressText && errorTile && effectiveLoaded.length === 0) {
          const retryBtn = findRetryButtonInCard(errorTile);

          if (retryBtn) {
            if (retryCount < maxRetries) {
              retryCount++;
              this.notifyProgress('IMAGE_RETRY', `⚠️ Generasi gambar gagal di Google Flow ("Maaf, gambar gagal dibuat"). Menekan tombol Retry otomatis (Percobaan ${retryCount}/${maxRetries})...`);
              if (typeof retryBtn.click === 'function') retryBtn.click();
              await simulateClick(retryBtn);
              await sleep(4000);
              continue;
            } else if (!this._maxImageRetriesNotified) {
              this._maxImageRetriesNotified = true;
              this.notifyProgress('IMAGE_RETRY_MAX', `⛔ Telah mencapai batas maksimal ${maxRetries}x retry untuk gambar ini.`);
            }
          }
        }

        await sleep(1000);
      }
      return null;
    }

    async ensureProject() {
      this.notifyProgress('ENSURE_PROJECT', 'Memeriksa kanvas proyek Google Flow...');
      const url = typeof window !== 'undefined' ? window.location.href : '';

      if (typeof document !== 'undefined') {
        // If already in project URL, ensure we are on the project root composer (not /character, /edit, etc.)
        if (/\/project\/[0-9a-fA-F-]{36}/i.test(url)) {
          const rootMatch = url.match(/(https:\/\/[^/]+(?:\/u\/\d+)?\/project\/[0-9a-fA-F-]{36})/i);
          if (rootMatch && typeof window !== 'undefined') {
            try {
              const currentParsed = new URL(url);
              const rootParsed = new URL(rootMatch[1]);
              if (currentParsed.pathname.replace(/\/$/, '') !== rootParsed.pathname.replace(/\/$/, '')) {
                window.location.href = rootMatch[1];
                await sleep(2000);
              }
            } catch (_) {}
          }
          await waitFor(() => {
            return document.querySelector('.ProseMirror') || document.querySelector(SELECTORS.PROMPT_INPUT) || document.querySelector('[contenteditable="true"]');
          }, 8000).catch(() => {});
          return true;
        }

        // If we know the project ID from active state or storage, navigate directly
        const knownProjectId = this.currentProjectId || (typeof window !== 'undefined' && window.__sinematicaActiveProjectId);
        if (knownProjectId && /^[0-9a-fA-F-]{36}$/.test(knownProjectId)) {
          const userPrefix = url.match(/\/u\/(\d+)/i)?.[0] || '';
          if (typeof window !== 'undefined') {
            window.location.href = `https://flow.google.com${userPrefix}/project/${knownProjectId}`;
            await sleep(2000);
            await waitFor(() => {
              return document.querySelector('.ProseMirror') || document.querySelector(SELECTORS.PROMPT_INPUT) || document.querySelector('[contenteditable="true"]');
            }, 10000).catch(() => {});
            return true;
          }
        }

        // Only on root/home page, look for existing project card or new project button
        const findNewProjectBtn = () => {
          return document.querySelector('button.new-project-button') ||
                 Array.from(document.querySelectorAll('button, a, [role="button"], div')).find((el) => {
                   const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().toLowerCase();
                   return (text.includes('new project') || text.includes('project baru') || text.includes('proyek baru')) && !el.closest('flow-prompt-box');
                 }) ||
                 document.querySelector('[aria-label*="new project" i], [aria-label*="project baru" i]') ||
                 document.querySelector('.new-project-card, flow-project-card');
        };

        const newProjectBtn = findNewProjectBtn();
        if (newProjectBtn) {
          if (typeof newProjectBtn.click === 'function') newProjectBtn.click();
          else simulateClick(newProjectBtn);
          await sleep(2000);
        }

        await waitFor(() => {
          return document.querySelector('.ProseMirror') || document.querySelector(SELECTORS.PROMPT_INPUT) || /\/project\/[0-9a-fA-F-]{36}/i.test(window.location.href);
        }, 15000).catch(() => {});
      }

      return true;
    }

    normalizeImagesList(imagesInput) {
      if (!imagesInput) return [];
      const rawList = Array.isArray(imagesInput) ? imagesInput : [imagesInput];
      const result = [];

      for (let i = 0; i < rawList.length; i++) {
        const item = rawList[i];
        if (!item) continue;

        let base64Data = '';
        let mimeType = 'image/png';
        let fileName = `ref_${Date.now()}_${i + 1}.png`;

        if (typeof item === 'string') {
          if (item.startsWith('data:')) {
            const matches = item.match(/^data:([^;]+);base64,(.+)$/);
            if (matches) {
              mimeType = matches[1] || 'image/png';
              base64Data = matches[2];
            } else {
              base64Data = item.replace(/^data:[^;]+;base64,/, '');
            }
          } else if (item.startsWith('/') || item.includes(':\\')) {
            continue;
          } else {
            base64Data = item;
          }
        } else if (typeof item === 'object') {
          const rawB64 = item.base64 || item.imageData || item.data || item.base64Data || '';
          if (String(rawB64).startsWith('data:')) {
            const matches = String(rawB64).match(/^data:([^;]+);base64,(.+)$/);
            if (matches) {
              mimeType = matches[1] || item.mimeType || 'image/png';
              base64Data = matches[2];
            } else {
              base64Data = String(rawB64).replace(/^data:[^;]+;base64,/, '');
            }
          } else if (rawB64) {
            base64Data = String(rawB64);
          }
          mimeType = item.mimeType || item.type || mimeType;
          fileName = item.fileName || item.name || fileName;
        }

        if (base64Data) {
          result.push({
            base64Data,
            mimeType,
            fileName,
            index: i,
          });
        }
      }

      return result;
    }

    async callDirectRpc(action, payload, timeoutMs = 60000) {
      if (typeof window !== 'undefined' && typeof window.__sinematica_dispatchMainWorldRpc === 'function') {
        return await window.__sinematica_dispatchMainWorldRpc(action, payload, timeoutMs);
      }
      if (typeof window !== 'undefined' && typeof window.__sinematica_uploadImageDirect === 'function') {
        if (action === 'RPC_UPLOAD_IMAGE' || action === 'DISPATCH_INPAGE_UPLOAD') {
          return await window.__sinematica_uploadImageDirect(payload);
        } else if (action === 'RPC_GENERATE_IMAGE' && typeof window.__sinematica_generateImageDirect === 'function') {
          return await window.__sinematica_generateImageDirect(payload);
        } else if (action === 'RPC_GENERATE_VIDEO' && typeof window.__sinematica_generateVideoDirect === 'function') {
          return await window.__sinematica_generateVideoDirect(payload);
        } else if (action === 'RPC_GET_MEDIA_URL' && typeof window.__sinematica_getMediaDownloadUrlDirect === 'function') {
          return await window.__sinematica_getMediaDownloadUrlDirect(payload.mediaId);
        }
      }
      return null;
    }

    async uploadMultipleImages(imagesInput, projectId = '', timeoutMs = 45000) {
      const imagesList = this.normalizeImagesList(imagesInput);
      if (imagesList.length === 0) {
        return [];
      }

      const total = imagesList.length;
      this.notifyProgress(
        total > 1 ? 'UPLOADING_MULTI_IMAGES' : 'UPLOADING_IMAGE',
        `Mengunggah ${total} gambar produk referensi ke Google Flow...`,
        { totalImages: total, files: imagesList.map((x) => x.fileName) }
      );

      const prompt = await waitFor(() => {
        return document.querySelector(SELECTORS.PROMPT_INPUT);
      }, 15000);

      const clipboardData = typeof DataTransfer !== 'undefined' ? new DataTransfer() : { items: { add: () => {} }, files: [] };
      for (const img of imagesList) {
        const blob = b64toBlob(img.base64Data, img.mimeType);
        if (blob) {
          const file = typeof File !== 'undefined' ? new File([blob], img.fileName, { type: img.mimeType }) : null;
          if (file && clipboardData.items && typeof clipboardData.items.add === 'function') {
            clipboardData.items.add(file);
          }
        }
      }

      if (prompt && typeof ClipboardEvent !== 'undefined') {
        const pasteEvt = new ClipboardEvent('paste', {
          bubbles: true,
          cancelable: true,
          composed: true,
          clipboardData,
        });

        prompt.focus();
        prompt.dispatchEvent(pasteEvt);

        if (typeof prompt.dispatchEvent === 'function') {
          try {
            prompt.dispatchEvent(new Event('input', { bubbles: true }));
          } catch {}
        }
      }

      try {
        const fileInput = document.querySelector('input[type="file"]');
        if (fileInput && clipboardData.files && clipboardData.files.length > 0 && typeof DataTransfer !== 'undefined') {
          const dt = new DataTransfer();
          for (let i = 0; i < clipboardData.files.length; i++) {
            dt.items.add(clipboardData.files[i]);
          }
          fileInput.files = dt.files;
          fileInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
      } catch (e) {
        console.warn('[FlowTaskExecutor] file input fallback notice:', e);
      }

      await sleep(1500);

      const startTime = Date.now();
      const uploadedMap = new Map();

      while (Date.now() - startTime < timeoutMs) {
        if (this.isCancelled) {
          throw new Error('Task aborted');
        }

        const tiles = Array.from(document.querySelectorAll(
          'flow-image-tile, flow-ingredient-chip, .flow-ingredient-chip, [data-ingredient-id], flow-tile-container, [class*="tile"], [class*="chip"]'
        )).filter((el) => {
          const text = el.innerText || el.textContent || '';
          const hasImg = el.querySelector('img') !== null;
          return hasImg || imagesList.some((img) => text.includes(img.fileName));
        });

        const isStillUploadingDom = tiles.some((tile) => {
          const spinner = tile.querySelector('mat-spinner, [role="progressbar"], .spinner, [class*="loading"]');
          return spinner && (spinner.offsetParent !== null || spinner.style.display !== 'none');
        });

        for (const tile of tiles) {
          const text = tile.innerText || tile.textContent || '';
          const imgEl = tile.querySelector('img');
          const src = imgEl ? imgEl.src : null;

          for (const targetImg of imagesList) {
            if ((text.includes(targetImg.fileName) || tiles.length === total) && src) {
              const mediaIdMatch = src.match(/\/image\/([0-9a-fA-F-]{36})/);
              const mediaId = mediaIdMatch ? mediaIdMatch[1] : (tile.getAttribute('data-ingredient-id') || `flowMedia/${targetImg.fileName}`);
              uploadedMap.set(targetImg.fileName, {
                fileName: targetImg.fileName,
                displayName: targetImg.fileName,
                src,
                mediaId,
                projectId,
              });
            }
          }
        }

        const networkUploadEvents = this.interceptedEvents.filter(
          (e) => (e.type === 'REFERENCE_IMAGE_UPLOADED' || e.status === 'REFERENCE_IMAGE_UPLOADED') && e.receivedAt >= startTime
        );
        if (networkUploadEvents.length > 0) {
          networkUploadEvents.forEach((ev, idx) => {
            const matchedImg = imagesList[idx] || imagesList[0];
            if (matchedImg && !uploadedMap.has(matchedImg.fileName)) {
              uploadedMap.set(matchedImg.fileName, {
                fileName: matchedImg.fileName,
                displayName: matchedImg.fileName,
                src: ev.url || null,
                mediaId: ev.mediaId || `flowMedia/${matchedImg.fileName}`,
                projectId,
              });
            }
          });
        }

        if ((uploadedMap.size >= total || tiles.length >= total) && !isStillUploadingDom && Date.now() - startTime >= 2500) {
          break;
        }

        await sleep(600);
      }

      const finalUploaded = imagesList.map((img) => {
        return uploadedMap.get(img.fileName) || {
          fileName: img.fileName,
          displayName: img.fileName,
          mediaId: `flowMedia/${img.fileName}`,
          projectId,
        };
      });

      this.notifyProgress('IMAGE_UPLOADED', `Berhasil mengunggah ${finalUploaded.length} gambar produk ke slot aset Google Flow.`, {
        uploadedMedia: finalUploaded,
        uploadedMediaIds: finalUploaded.map((r) => r.mediaId),
      });

      return finalUploaded;
    }

    async fillPrompt(promptText) {
      this.notifyProgress('TYPING_PROMPT', 'Mengisi teks prompt AI otomatis...', { prompt: promptText });

      if (typeof document !== 'undefined') {
        const openOverlay = document.querySelector('flow-prompt-box-settings, .settings-content-overlay');
        if (openOverlay && typeof KeyboardEvent !== 'undefined') {
          try {
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
          } catch {}
          await sleep(200);
        }

        const promptInput = (typeof document.querySelector === 'function' ? (document.querySelector('.ProseMirror') || document.querySelector('[contenteditable="true"]') || document.querySelector('textarea')) : null) ||
          (typeof document.querySelectorAll === 'function' ? document.querySelectorAll('textarea, [contenteditable="true"]')[0] : null);

        if (promptInput) {
          await simulateInput(promptInput, promptText);
          await sleep(300);
        }
      }
      return true;
    }

    async triggerImageGeneration(options = {}) {
      const minDelay = Number(options?.minDelayMs ?? 5000);
      const maxDelay = Number(options?.maxDelayMs ?? 8000);
      const skipDelay = Boolean(options?.skipDelay);

      if (!skipDelay && maxDelay >= minDelay && minDelay > 0) {
        const randomDelay = Math.floor(Math.random() * (maxDelay - minDelay + 1)) + minDelay;
        const delaySec = (randomDelay / 1000).toFixed(1);
        this.notifyProgress('TRIGGERING_GENERATION', `Menunggu jeda acak ${delaySec} detik sebelum submit gambar...`, { delayMs: randomDelay });

        const start = Date.now();
        while (Date.now() - start < randomDelay) {
          if (this.isCancelled) throw new Error('Task aborted');
          await sleep(Math.min(200, randomDelay - (Date.now() - start)));
        }
      }

      this.notifyProgress('TRIGGERING_GENERATION', 'Menjalankan pembuatan gambar awal...');

      if (typeof document !== 'undefined') {
        if (typeof window !== 'undefined') {
          window.__sinematicaAllowNativeInput = true;
        }

        const promptInput = typeof document.querySelector === 'function'
          ? (document.querySelector('.ProseMirror') || document.querySelector('[contenteditable="true"]') || document.querySelector('textarea'))
          : null;

        const isButtonDisabled = (btn) => {
          if (!btn) return true;
          return btn.disabled ||
            (typeof btn.hasAttribute === 'function' && btn.hasAttribute('disabled')) ||
            (typeof btn.getAttribute === 'function' && btn.getAttribute('aria-disabled') === 'true') ||
            (btn.classList && typeof btn.classList.contains === 'function' && btn.classList.contains('mat-mdc-button-disabled'));
        };

        const findGenerateButton = () => {
          const directBtn = document.querySelector(
            'flow-generate-icon-button button, button.generate-icon-button, button[aria-label*="Start generation" i], button[aria-label*="Mulai pembuatan" i], button[aria-label*="Start" i], button[aria-label*="Generate" i], button[aria-label*="Submit" i], button[aria-label*="Send" i], button[aria-label*="Mulai" i], button[aria-label*="Buat" i], button[aria-label*="Hasilkan" i]'
          );
          if (directBtn && !isButtonDisabled(directBtn)) return directBtn;

          const promptBox = (typeof document.querySelector === 'function' ? document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') : null) || document;
          const queryAll = typeof promptBox.querySelectorAll === 'function'
            ? Array.from(promptBox.querySelectorAll(
                'flow-generate-icon-button button, button[type="submit"], [data-test-id*="generate"], button[aria-label*="generate" i], button[aria-label*="start" i], button[aria-label*="buat" i], button[aria-label*="mulai" i], button[aria-label*="hasilkan" i], button[aria-label*="submit" i], button[aria-label*="send" i], button'
              ))
            : [];

          const matched = queryAll.find((el) => {
            if (!el || isButtonDisabled(el)) return false;
            const text = [
              typeof el.getAttribute === 'function' ? el.getAttribute('aria-label') : '',
              typeof el.getAttribute === 'function' ? el.getAttribute('title') : '',
              el.innerText,
              el.textContent
            ].filter(Boolean).join(' ').toLowerCase();
            if (text.includes('character') || text.includes('karakter') || text.includes('actor') || text.includes('upload') || text.includes('unggah') || text.includes('sidebar') || text.includes('settings') || text.includes('pemicu setelan')) {
              return false;
            }
            const inComposer = (typeof el.closest === 'function' && (!!el.closest('flow-prompt-box') || !!el.closest('flow-generate-icon-button')));
            const isGenerateText = /arrow|start|generate|submit|send|buat|mulai|hasilkan/i.test(text) || !!(typeof el.querySelector === 'function' && el.querySelector('mat-icon, svg'));
            return inComposer && isGenerateText;
          });
          if (matched) return matched;

          // Fallback: Last non-sidebar, non-settings button inside prompt box
          const promptButtons = typeof promptBox.querySelectorAll === 'function'
            ? Array.from(promptBox.querySelectorAll('button')).filter((b) => {
                if (!b || isButtonDisabled(b)) return false;
                const txt = [b.getAttribute('aria-label') || '', b.innerText || '', b.textContent || ''].join(' ').toLowerCase();
                return !txt.includes('character') && !txt.includes('karakter') && !txt.includes('upload') && !txt.includes('unggah') && !txt.includes('sidebar') && !txt.includes('settings') && !txt.includes('pemicu setelan');
              })
            : [];
          if (promptButtons.length > 0) {
            return promptButtons[promptButtons.length - 1];
          }
          return null;
        };

        let createBtn = null;
        const waitStart = Date.now();
        while (Date.now() - waitStart < 6000) {
          createBtn = findGenerateButton();
          if (createBtn && !isButtonDisabled(createBtn)) break;

          if (promptInput && typeof promptInput.dispatchEvent === 'function') {
            try {
              promptInput.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText', data: ' ', composed: true }));
              promptInput.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: ' ', composed: true }));
              promptInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', code: 'KeyA', bubbles: true, composed: true }));
              promptInput.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
              promptInput.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            } catch {}
          }
          await sleep(250);
        }

        if (!createBtn) {
          createBtn = findGenerateButton();
        }

        if (createBtn) {
          await simulateClick(createBtn);
          await sleep(600);

          for (let attempt = 0; attempt < 3; attempt++) {
            const currentBtn = findGenerateButton();
            const isGeneratingNow = typeof document !== 'undefined' && !!document.querySelector('mat-spinner, .generating-spinner, [role="progressbar"], [aria-label*="generating" i]');
            if (!currentBtn || isButtonDisabled(currentBtn) || isGeneratingNow) {
              break;
            }
            await sleep(400);
            await simulateClick(currentBtn);
            await sleep(500);
          }
        }
      }

      this.notifyProgress('WAITING_IMAGE', 'Menunggu hasil generasi gambar awal dari Google Flow...');
      return true;
    }

    async ensureAgentOff() {
      if (typeof document === 'undefined') return true;

      try {
        const promptBox = (typeof document.querySelector === 'function' ? document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') : null) || document;
        const queryAll = typeof promptBox.querySelectorAll === 'function'
          ? Array.from(promptBox.querySelectorAll('button, [role="button"], mat-chip, div, span'))
          : (typeof document.querySelectorAll === 'function' ? Array.from(document.querySelectorAll('button, [role="button"], mat-chip, div, span')) : []);

        const agentChip = (typeof promptBox.querySelector === 'function' ? promptBox.querySelector('.agent-mode-chip, [aria-label*="agent" i]') : null) ||
          queryAll.find((el) => {
            const text = (el.innerText || el.textContent || '').trim();
            const aria = typeof el.getAttribute === 'function' ? (el.getAttribute('aria-label') || '').toLowerCase() : '';
            return /^agent$/i.test(text) || aria.includes('agent') || (el.className && typeof el.className === 'string' && el.className.includes('agent-mode-chip'));
          });

        if (agentChip) {
          const isPressed = (typeof agentChip.getAttribute === 'function' && agentChip.getAttribute('aria-pressed') === 'true') ||
            (agentChip.classList && typeof agentChip.classList.contains === 'function' && (agentChip.classList.contains('active') || agentChip.classList.contains('mat-mdc-chip-selected') || agentChip.classList.contains('selected')));

          if (isPressed) {
            this.notifyProgress('CONFIGURING_MODE', 'Mematikan Agent Mode agar generasi gambar konsisten...');
            await simulateClick(agentChip);
            await sleep(400);
          }
        }
      } catch (err) {
        console.warn('[FlowTaskExecutor] Failed to check/toggle agent mode chip:', err);
      }

      return true;
    }

    async configureImageSettings(storyboardOptions = {}) {
      const targetModel = String(storyboardOptions.model || 'nano-banana-2').toLowerCase().trim();
      const targetRatio = String(storyboardOptions.aspectRatio || '9:16').trim();
      const targetCount = Number(storyboardOptions.count || 1);

      this.notifyProgress('CONFIGURING_MODE', `Mengatur setting gambar Google Flow (${targetRatio}, ${storyboardOptions.model || 'Nano Banana 2'}, x${targetCount})...`, {
        storyboardOptions,
      });

      if (typeof document === 'undefined') return true;

      try {
        const promptBox = (typeof document.querySelector === 'function' ? document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') : null) || document;
        const promptButtons = typeof promptBox.querySelectorAll === 'function'
          ? Array.from(promptBox.querySelectorAll('button, [role="button"], div[role="button"]'))
          : [];

        let settingsTrigger = (typeof promptBox.querySelector === 'function' ? promptBox.querySelector('.settings-trigger-button, button[aria-label="Settings trigger"], button[aria-label*="Pemicu setelan" i], [data-test-id*="settings-trigger"]') : null) ||
          promptButtons.find((btn) => {
            const text = (btn.innerText || btn.textContent || '').trim();
            const aria = typeof btn.getAttribute === 'function' ? (btn.getAttribute('aria-label') || '') : '';
            return text.includes('•') || text.includes('·') || /720p|1080p|9:16|16:9|3:4|4:3|1:1|x1|x2|x4|banana|veo|video|image|gambar/i.test(text) ||
                   aria.toLowerCase().includes('settings trigger') || aria.toLowerCase().includes('pemicu setelan') || aria.toLowerCase().includes('settings') || aria.toLowerCase().includes('tune');
          });

        if (!settingsTrigger && promptButtons.length >= 2) {
          settingsTrigger = promptButtons[promptButtons.length - 2];
        }

        let overlay = document.querySelector('flow-prompt-box-settings, .settings-content-overlay');

        if (!overlay && settingsTrigger) {
          if (typeof settingsTrigger.click === 'function') {
            settingsTrigger.click();
          } else {
            simulateClick(settingsTrigger);
          }

          const openStart = Date.now();
          while (Date.now() - openStart < 1000) {
            overlay = document.querySelector('flow-prompt-box-settings, .settings-content-overlay');
            if (overlay) break;
            await sleep(100);
          }
        }

        if (!overlay) {
          overlay = document.querySelector('flow-prompt-box-settings, .settings-content-overlay, .cdk-overlay-pane, [role="dialog"]') || document.body;
        }

        if (overlay && typeof overlay.querySelectorAll === 'function') {
          const clickToggle = async (toggleElement) => {
            if (!toggleElement) return false;
            const isAlreadyChecked = (toggleElement.classList && typeof toggleElement.classList.contains === 'function' && toggleElement.classList.contains('mat-button-toggle-checked')) ||
              (typeof toggleElement.getAttribute === 'function' && toggleElement.getAttribute('aria-checked') === 'true') ||
              (typeof toggleElement.querySelector === 'function' && toggleElement.querySelector('button[aria-checked="true"]'));
            if (isAlreadyChecked) return true;

            const btn = (typeof toggleElement.querySelector === 'function' ? toggleElement.querySelector('button') : null) || toggleElement;
            await simulateClick(btn);
            return true;
          };

          const modeGroup = (typeof overlay.querySelector === 'function' ? (
            overlay.querySelector('flow-toggles[aria-label="Mode"]') ||
            overlay.querySelector('flow-toggles[aria-label*="Mode" i]') ||
            overlay.querySelector('mat-button-toggle-group')
          ) : null) || overlay;
          const modeToggles = typeof modeGroup?.querySelectorAll === 'function'
            ? Array.from(modeGroup.querySelectorAll('mat-button-toggle, button[role="radio"], button[role="tab"], .mat-button-toggle-button'))
            : [];
          const imageToggle = modeToggles.find((b) => {
            const text = (b.innerText || b.textContent || '').trim();
            const aria = typeof b.getAttribute === 'function' ? (b.getAttribute('aria-label') || '').toLowerCase() : '';
            return /^image$/i.test(text) || (/image|gambar/i.test(text) && !/video/i.test(text)) || aria.includes('image');
          }) || modeToggles[0];

          if (imageToggle) {
            await clickToggle(imageToggle);
            await sleep(250);
          }

          const ratioGroup = (typeof overlay.querySelector === 'function' ? (
            overlay.querySelector('flow-toggles[aria-label="Aspect ratio"]') ||
            overlay.querySelector('flow-toggles[aria-label*="Aspect" i]')
          ) : null) || overlay;
          const ratioToggles = typeof ratioGroup?.querySelectorAll === 'function'
            ? Array.from(ratioGroup.querySelectorAll('mat-button-toggle, button[role="radio"], button, .mat-button-toggle-button'))
            : [];
          const ratioToggle = ratioToggles.find((b) => {
            const text = (b.innerText || b.textContent || (typeof b.getAttribute === 'function' ? b.getAttribute('aria-label') : '') || '').trim();
            if (targetRatio === '16:9') {
              return text.includes('16:9') || /crop_16_9/i.test(text);
            } else if (targetRatio === '4:3') {
              return text.includes('4:3') || /4:3/i.test(text);
            } else if (targetRatio === '1:1') {
              return text.includes('1:1') || /1:1/i.test(text);
            } else if (targetRatio === '3:4') {
              return text.includes('3:4') || /3:4/i.test(text);
            }
            return text.includes('9:16') || /crop_9_16/i.test(text);
          });
          if (ratioToggle) {
            await clickToggle(ratioToggle);
            await sleep(250);
          }

          const countGroup = (typeof overlay.querySelector === 'function' ? (
            overlay.querySelector('flow-toggles[aria-label="Output count"]') ||
            overlay.querySelector('flow-toggles[aria-label*="count" i]')
          ) : null) || overlay;
          const countToggles = typeof countGroup?.querySelectorAll === 'function'
            ? Array.from(countGroup.querySelectorAll('mat-button-toggle, button[role="radio"], button, .mat-button-toggle-button'))
            : [];
          const targetStr = `x${targetCount}`;
          const countToggle = countToggles.find((b) => {
            const text = (b.innerText || b.textContent || '').trim();
            return text === targetStr || text.includes(targetStr) || (targetCount === 1 && (text === '1x' || text === '1'));
          });
          if (countToggle) {
            await clickToggle(countToggle);
            await sleep(250);
          }

          const closeOverlay = () => {
            if (typeof KeyboardEvent !== 'undefined') {
              try {
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
              } catch {}
            }
            const backdrop = document.querySelector('.cdk-overlay-backdrop');
            if (backdrop) {
              try { backdrop.click(); } catch {}
            }
          };

          closeOverlay();
          await sleep(300);
        }
      } catch (err) {
        console.warn('[FlowTaskExecutor] Error configuring image settings:', err);
      }

      return true;
    }

    async configureOptimalAffiliateVideoSettings(options = {}) {
      const subTab = options.subTab || 'Ingredients';
      this.notifyProgress('CONFIGURING_VIDEO', `Mengatur opsi video affiliator (Video, ${subTab}, Omni Flash 720p)...`, { options, subTab });

      if (typeof document !== 'undefined') {
        const promptBox = (typeof document.querySelector === 'function' ? document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') : null) || document;
        const promptButtons = typeof promptBox.querySelectorAll === 'function'
          ? Array.from(promptBox.querySelectorAll('button, [role="button"], div[role="button"]'))
          : [];

        let settingsTrigger = (typeof promptBox.querySelector === 'function' ? promptBox.querySelector('.settings-trigger-button, button[aria-label="Settings trigger"], button[aria-label*="Pemicu setelan" i], [data-test-id*="settings-trigger"]') : null) ||
          promptButtons.find((btn) => {
            const text = (btn.innerText || btn.textContent || '').trim();
            const aria = typeof btn.getAttribute === 'function' ? (btn.getAttribute('aria-label') || '') : '';
            return text.includes('•') || text.includes('·') || /720p|1080p|9:16|16:9|3:4|4:3|1:1|x1|x2|x4|banana|veo|video|image|gambar/i.test(text) ||
                   aria.toLowerCase().includes('settings trigger') || aria.toLowerCase().includes('pemicu setelan') || aria.toLowerCase().includes('settings') || aria.toLowerCase().includes('tune');
          });

        if (!settingsTrigger && promptButtons.length >= 2) {
          settingsTrigger = promptButtons[promptButtons.length - 2];
        }

        let overlay = document.querySelector('flow-prompt-box-settings, .settings-content-overlay');
        if (!overlay && settingsTrigger) {
          await simulateClick(settingsTrigger);

          const openStart = Date.now();
          while (Date.now() - openStart < 1000) {
            overlay = document.querySelector('flow-prompt-box-settings, .settings-content-overlay');
            if (overlay) break;
            await sleep(100);
          }
        }

        if (!overlay) {
          overlay = document.querySelector('flow-prompt-box-settings, .settings-content-overlay, .cdk-overlay-pane, [role="dialog"]') || document.body;
        }

        if (overlay && typeof overlay.querySelectorAll === 'function') {
          const clickToggle = async (toggleElement) => {
            if (!toggleElement) return false;
            const isAlreadyChecked = toggleElement.classList.contains('mat-button-toggle-checked') ||
              toggleElement.getAttribute('aria-checked') === 'true' ||
              toggleElement.querySelector('button[aria-checked="true"]');
            if (isAlreadyChecked) return true;

            const btn = (typeof toggleElement.querySelector === 'function' ? toggleElement.querySelector('button') : null) || toggleElement;
            await simulateClick(btn);
            return true;
          };

          const modeGroup = overlay.querySelector('flow-toggles[aria-label="Mode"]') || overlay;
          const modeToggles = Array.from(modeGroup.querySelectorAll('mat-button-toggle, button[role="radio"], button[role="tab"]'));
          const videoToggle = modeToggles.find((b) => {
            const text = (b.innerText || b.textContent || '').trim();
            const aria = typeof b.getAttribute === 'function' ? (b.getAttribute('aria-label') || '').toLowerCase() : '';
            return /^video$/i.test(text) || (/video/i.test(text) && !/image|gambar/i.test(text)) || aria.includes('video');
          }) || modeToggles[1];

          if (videoToggle) {
            await clickToggle(videoToggle);
            await sleep(300);
          }

          const typeGroup = overlay.querySelector('flow-toggles[aria-label="Video type"]') || overlay;
          const typeToggles = Array.from(typeGroup.querySelectorAll('mat-button-toggle, button[role="radio"], button[role="tab"]'));
          const isFrames = /frame/i.test(subTab);
          const targetToggle = typeToggles.find((b) => {
            const text = (b.innerText || b.textContent || '').trim();
            return isFrames ? /frame/i.test(text) : /ingredient/i.test(text);
          }) || (isFrames ? typeToggles[0] : typeToggles[1]);

          if (targetToggle) {
            await clickToggle(targetToggle);
            await sleep(350);
          }

          const targetRatio = options.aspectRatio === '16:9' ? '16:9' : '9:16';
          const ratioGroup = overlay.querySelector('flow-toggles[aria-label="Aspect ratio"]') || overlay;
          const ratioToggles = Array.from(ratioGroup.querySelectorAll('mat-button-toggle, button[role="radio"], button'));
          const ratioToggle = ratioToggles.find((b) => {
            const text = (b.innerText || b.textContent || (typeof b.getAttribute === 'function' ? b.getAttribute('aria-label') : '') || '').trim();
            return targetRatio === '16:9' ? /16:9|crop_16_9/i.test(text) : /9:16|crop_9_16/i.test(text);
          });
          if (ratioToggle) {
            await clickToggle(ratioToggle);
            await sleep(200);
          }

          // Output count: always lock to single output (x1)
          const countGroup = overlay.querySelector('flow-toggles[aria-label="Output count"], flow-toggles[aria-label="Count"]') || overlay;
          const countToggles = Array.from(countGroup.querySelectorAll('mat-button-toggle, button[role="radio"], button, .mat-button-toggle-button'));
          const countToggle = countToggles.find((b) => {
            const text = (b.innerText || b.textContent || (typeof b.getAttribute === 'function' ? b.getAttribute('aria-label') : '') || '').trim().toLowerCase();
            return text === 'x1' || text === '1x' || text === '1' || /\bx1\b/i.test(text);
          });
          if (countToggle) {
            await clickToggle(countToggle);
            await sleep(200);
          }

          const closeOverlay = () => {
            if (typeof KeyboardEvent !== 'undefined') {
              try {
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
              } catch {}
            }
            const backdrop = document.querySelector('.cdk-overlay-backdrop');
            if (backdrop) {
              try { backdrop.click(); } catch {}
            }
          };

          closeOverlay();
          await sleep(300);
        }
      }

      return true;
    }

    async attachFrameToStartSlot(frameData, timeoutMs = 30000) {
      if (typeof document === 'undefined') return true;
      this.notifyProgress('ATTACHING_START_FRAME', 'Mengunggah dan menyambungkan frame terakhir ke slot Start frame...');

      try {
        const promptBox = document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') || document;

        const existingChips = Array.from(promptBox.querySelectorAll('flow-ingredient-chip, [data-ingredient-id], .flow-ingredient-chip'));
        for (const chip of existingChips) {
          const removeBtn = chip.querySelector('button[aria-label*="remove" i], button[aria-label*="delete" i], mat-icon');
          if (removeBtn) {
            try {
              if (typeof removeBtn.click === 'function') removeBtn.click();
              else simulateClick(removeBtn);
              await sleep(150);
            } catch {}
          }
        }

        // 1. Upload extracted frame file using uploadMultipleImages to ensure it completes upload fully
        let uploadedFrameMedia = null;
        if (frameData) {
          const framePayload = Array.isArray(frameData) ? frameData : [frameData];
          this.notifyProgress('UPLOADING_IMAGE', 'Mengunggah berkas frame ke aset proyek Google Flow...');
          const uploadRes = await this.uploadMultipleImages(framePayload, '', timeoutMs);
          if (uploadRes && uploadRes.length > 0) {
            uploadedFrameMedia = uploadRes[0];
          }
          await sleep(600);
        }

        // 2. Add to prompt slot START ONLY (Exact once)
        let attached = false;
        try {
          const allButtons = Array.from(promptBox.querySelectorAll('button, [role="button"], div[role="button"]'));
          const startBtn = allButtons.find((btn) => {
            const text = (btn.innerText || btn.textContent || '').trim().toLowerCase();
            const aria = (typeof btn.getAttribute === 'function' ? (btn.getAttribute('aria-label') || '') : '').toLowerCase();
            return text === 'start' || aria.includes('start frame') || aria.includes('first frame') || text.includes('start');
          });

          // Method A: Click Start button -> popover opens -> select first asset -> click "Add to prompt"
          if (startBtn) {
            if (typeof startBtn.click === 'function') startBtn.click();
            else simulateClick(startBtn);
            await sleep(450);

            const popover = document.querySelector('flow-add-menu-popover-content');
            if (popover) {
              const assetItems = typeof popover.querySelectorAll === 'function'
                ? Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"]'))
                : (popover.querySelector('button.asset-item') ? [popover.querySelector('button.asset-item')] : []);

              const validAsset = assetItems.find((el) => {
                const text = [
                  el.innerText || '',
                  el.textContent || '',
                  typeof el.getAttribute === 'function' ? (el.getAttribute('aria-label') || '') : ''
                ].join(' ').toLowerCase();
                if (text.includes('create character') || text.includes('buat karakter') || text.includes('new character') || text.includes('karakter baru') || text.includes('upload new') || text.includes('unggah')) {
                  return false;
                }
                return (typeof el.querySelector === 'function' && !!el.querySelector('img')) || (el.classList && typeof el.classList.contains === 'function' && el.classList.contains('asset-item')) || assetItems.length === 1;
              }) || assetItems[0];

              if (validAsset) {
                if (typeof validAsset.click === 'function') validAsset.click();
                else simulateClick(validAsset);
                await sleep(250);
              }

              const addBtn = popover.querySelector('.detail-add-to-prompt-btn, button[class*="add-to-prompt"]');
              if (addBtn) {
                if (typeof addBtn.click === 'function') addBtn.click();
                else simulateClick(addBtn);
                await sleep(400);
                attached = true;
              }
            }
          }
        } catch (eMethodA) {
          console.warn('[FlowTaskExecutor] attachFrameToStartSlot Method A notice:', eMethodA);
        }

        // Method B: If not attached yet, click "Add to prompt" on the newest uploaded frame image tile (top-left tile)
        if (!attached) {
          try {
            const imageTiles = Array.from(document.querySelectorAll('flow-image-tile')).filter((tile) => {
              const isError = !!tile.querySelector('flow-error-tile') || /failed/i.test(tile.innerText || '');
              const img = tile.querySelector('img');
              return !isError && img && (img.naturalWidth > 0 || img.complete) && img.src && !img.src.startsWith('data:');
            });

            if (imageTiles.length > 0) {
              const targetTile = imageTiles[0];
              const moreBtn = targetTile.querySelector('button[aria-label="More options"], button[aria-label*="More" i]');
              if (moreBtn) {
                if (typeof moreBtn.click === 'function') moreBtn.click();
                else simulateClick(moreBtn);
                await sleep(350);

                const menuItems = Array.from(document.querySelectorAll('[role="menuitem"], .mat-mdc-menu-item'));
                const addToPromptItem = menuItems.find((m) => /add to prompt|start frame|set as start/i.test(m.innerText || ''));
                if (addToPromptItem) {
                  if (typeof addToPromptItem.click === 'function') addToPromptItem.click();
                  else simulateClick(addToPromptItem);
                  await sleep(400);
                  attached = true;
                } else if (typeof KeyboardEvent !== 'undefined') {
                  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
                }
              }
            }
          } catch (eMethodB) {
            console.warn('[FlowTaskExecutor] attachFrameToStartSlot Method B notice:', eMethodB);
          }
        }
      } catch (err) {
        console.warn('[FlowTaskExecutor] attachFrameToStartSlot error:', err);
      }

      return true;
    }

    async attachGeneratedImageToPrompt(imageAsset) {
      if (typeof document === 'undefined') return true;
      this.notifyProgress('ATTACHING_IMAGE_TO_VIDEO', 'Menyambungkan gambar hasil generasi sebagai referensi video...', { imageAsset });

      try {
        const imageTiles = Array.from(document.querySelectorAll('flow-image-tile')).filter((tile) => {
          const isError = !!tile.querySelector('flow-error-tile') || /failed/i.test(tile.innerText || '');
          const img = tile.querySelector('img');
          return !isError && img && (img.naturalWidth > 0 || img.complete) && img.src && !img.src.startsWith('data:');
        });

        if (imageTiles.length > 0) {
          const targetTile = imageTiles[0];
          const moreBtn = targetTile.querySelector('button[aria-label="More options"], button[aria-label*="More" i]');
          if (moreBtn) {
            if (typeof moreBtn.click === 'function') {
              moreBtn.click();
            } else {
              simulateClick(moreBtn);
            }
            await sleep(350);

            const menuItems = Array.from(document.querySelectorAll('[role="menuitem"], .mat-mdc-menu-item'));
            const addToPromptItem = menuItems.find((m) => /add to prompt/i.test(m.innerText || ''));
            if (addToPromptItem) {
              if (typeof addToPromptItem.click === 'function') {
                addToPromptItem.click();
              } else {
                simulateClick(addToPromptItem);
              }
              await sleep(400);
              return true;
            }

            if (typeof KeyboardEvent !== 'undefined') {
              try {
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
              } catch {}
            }
            await sleep(200);
          }
        }
      } catch (e) {
        console.warn('[FlowTaskExecutor] attachGeneratedImageToPrompt notice:', e);
      }

      return true;
    }

    async triggerVideoRender(videoPrompt) {
      this.notifyProgress('TRIGGERING_VIDEO', 'Menjalankan render video di Google Flow...');

      if (typeof document !== 'undefined') {
        if (typeof window !== 'undefined') {
          window.__sinematicaAllowNativeInput = true;
        }

        const promptInput = typeof document.querySelector === 'function'
          ? (document.querySelector('.ProseMirror') || document.querySelector('[contenteditable="true"]') || document.querySelector('textarea'))
          : null;

        const isButtonDisabled = (btn) => {
          if (!btn) return true;
          return btn.disabled ||
            (typeof btn.hasAttribute === 'function' && btn.hasAttribute('disabled')) ||
            (typeof btn.getAttribute === 'function' && btn.getAttribute('aria-disabled') === 'true') ||
            (btn.classList && typeof btn.classList.contains === 'function' && btn.classList.contains('mat-mdc-button-disabled'));
        };

        const findGenerateButton = () => {
          const directBtn = document.querySelector(
            'flow-generate-icon-button button, button.generate-icon-button, button[aria-label*="Start generation" i], button[aria-label*="Mulai pembuatan" i], button[aria-label*="Start" i], button[aria-label*="Generate" i], button[aria-label*="Submit" i], button[aria-label*="Send" i], button[aria-label*="Mulai" i], button[aria-label*="Buat" i], button[aria-label*="Hasilkan" i]'
          );
          if (directBtn && !isButtonDisabled(directBtn)) return directBtn;

          const promptBox = (typeof document.querySelector === 'function' ? document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') : null) || document;
          const queryAll = typeof promptBox.querySelectorAll === 'function'
            ? Array.from(promptBox.querySelectorAll(
                'flow-generate-icon-button button, button[type="submit"], [data-test-id*="generate"], button[aria-label*="generate" i], button[aria-label*="start" i], button[aria-label*="buat" i], button[aria-label*="mulai" i], button[aria-label*="hasilkan" i], button[aria-label*="submit" i], button[aria-label*="send" i], button'
              ))
            : [];

          const matched = queryAll.find((el) => {
            if (!el || isButtonDisabled(el)) return false;
            const text = [
              typeof el.getAttribute === 'function' ? el.getAttribute('aria-label') : '',
              typeof el.getAttribute === 'function' ? el.getAttribute('title') : '',
              el.innerText,
              el.textContent
            ].filter(Boolean).join(' ').toLowerCase();
            if (text.includes('character') || text.includes('karakter') || text.includes('actor') || text.includes('upload') || text.includes('unggah') || text.includes('sidebar') || text.includes('settings') || text.includes('pemicu setelan')) {
              return false;
            }
            const inComposer = (typeof el.closest === 'function' && (!!el.closest('flow-prompt-box') || !!el.closest('flow-generate-icon-button')));
            const isGenerateText = /arrow|start|generate|submit|send|buat|mulai|hasilkan/i.test(text) || !!(typeof el.querySelector === 'function' && el.querySelector('mat-icon, svg'));
            return inComposer && isGenerateText;
          });
          if (matched) return matched;

          // Fallback: Last non-sidebar, non-settings button inside prompt box
          const promptButtons = typeof promptBox.querySelectorAll === 'function'
            ? Array.from(promptBox.querySelectorAll('button')).filter((b) => {
                if (!b || isButtonDisabled(b)) return false;
                const txt = [b.getAttribute('aria-label') || '', b.innerText || '', b.textContent || ''].join(' ').toLowerCase();
                return !txt.includes('character') && !txt.includes('karakter') && !txt.includes('upload') && !txt.includes('unggah') && !txt.includes('sidebar') && !txt.includes('settings') && !txt.includes('pemicu setelan');
              })
            : [];
          if (promptButtons.length > 0) {
            return promptButtons[promptButtons.length - 1];
          }
          return null;
        };

        let createBtn = null;
        const waitStart = Date.now();
        while (Date.now() - waitStart < 6000) {
          createBtn = findGenerateButton();
          if (createBtn && !isButtonDisabled(createBtn)) break;

          if (promptInput && typeof promptInput.dispatchEvent === 'function') {
            try {
              promptInput.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText', data: ' ', composed: true }));
              promptInput.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: ' ', composed: true }));
              promptInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', code: 'KeyA', bubbles: true, composed: true }));
              promptInput.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
              promptInput.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            } catch {}
          }
          await sleep(250);
        }

        if (!createBtn) {
          createBtn = findGenerateButton();
        }

        if (createBtn) {
          await simulateClick(createBtn);
          await sleep(600);

          for (let attempt = 0; attempt < 3; attempt++) {
            const currentBtn = findGenerateButton();
            const isGeneratingNow = typeof document !== 'undefined' && !!document.querySelector('mat-spinner, .generating-spinner, [role="progressbar"], [aria-label*="generating" i], [aria-label*="rendering" i]');
            if (!currentBtn || isButtonDisabled(currentBtn) || isGeneratingNow) {
              break;
            }
            await sleep(400);
            await simulateClick(currentBtn);
            await sleep(500);
          }
        }
      }

      this.notifyProgress('RENDERING_VIDEO', 'Sedang memproses render video di Google Flow...');
      return true;
    }

    async extractLastFrameFromVideoUrl(videoUrl) {
      if (typeof document === 'undefined' || !videoUrl) return null;
      this.notifyProgress('EXTRACTING_LAST_FRAME', 'Mengunduh dan mengekstrak frame terakhir dari video sebelumnya...');

      return new Promise((resolve) => {
        try {
          const video = document.createElement('video');
          video.crossOrigin = 'anonymous';
          video.muted = true;
          video.playsInline = true;
          video.preload = 'auto';

          let resolved = false;
          const finish = (result) => {
            if (resolved) return;
            resolved = true;
            try {
              video.pause();
              video.removeAttribute('src');
              video.load();
            } catch (_) {}
            resolve(result);
          };

          const timeoutTimer = setTimeout(() => {
            console.warn('[FlowTaskExecutor] extractLastFrameFromVideoUrl timed out after 20s');
            finish(null);
          }, 20000);

          video.addEventListener('error', (e) => {
            console.warn('[FlowTaskExecutor] extractLastFrameFromVideoUrl video load error:', e);
            clearTimeout(timeoutTimer);
            finish(null);
          });

          video.addEventListener('loadedmetadata', () => {
            try {
              const dur = video.duration || 0;
              const seekTime = Math.max(0, dur - 0.15);
              video.currentTime = seekTime;
            } catch (err) {
              console.warn('[FlowTaskExecutor] seek error:', err);
              clearTimeout(timeoutTimer);
              finish(null);
            }
          });

          video.addEventListener('seeked', () => {
            try {
              const canvas = document.createElement('canvas');
              canvas.width = video.videoWidth || 720;
              canvas.height = video.videoHeight || 1280;
              const ctx = canvas.getContext('2d');
              if (ctx) {
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const dataUrl = canvas.toDataURL('image/png');
                const base64Data = dataUrl.replace(/^data:image\/\w+;base64,/, '');
                clearTimeout(timeoutTimer);
                this.notifyProgress('EXTRACTING_LAST_FRAME', 'Berhasil mengekstrak frame terakhir untuk referensi klip berikutnya.');
                finish({
                  base64: base64Data,
                  base64Data,
                  data: dataUrl,
                  mimeType: 'image/png',
                  fileName: `extracted_last_frame_${Date.now()}.png`,
                });
                return;
              }
            } catch (canvasErr) {
              console.warn('[FlowTaskExecutor] canvas extraction error:', canvasErr);
            }
            clearTimeout(timeoutTimer);
            finish(null);
          });

          video.src = videoUrl;
        } catch (e) {
          console.warn('[FlowTaskExecutor] extractLastFrameFromVideoUrl fatal error:', e);
          resolve(null);
        }
      });
    }

    async resolveTileVideoUrl(tile) {
      if (!tile || typeof document === 'undefined') return null;

      const directVid = tile.querySelector('video');
      const directSrc = directVid?.currentSrc || directVid?.src;
      if (directSrc && (directSrc.includes('flow-content') || directSrc.startsWith('http') || directSrc.startsWith('blob:'))) {
        return {
          videoUrl: directSrc,
          duration: directVid.duration || 0,
          label: tile.getAttribute?.('aria-label') || tile.innerText?.replace(/play_arrow|play_circle/g, '').trim() || '',
        };
      }

      const clickTarget = tile.querySelector('.mobile-play-badge') ||
        tile.querySelector('.thumbnail') ||
        tile.querySelector('img') ||
        tile;

      try {
        simulateClick(clickTarget);
      } catch (_) {
        clickTarget.click?.();
      }

      let videoUrl = null;
      let duration = 0;

      for (let attempt = 0; attempt < 25; attempt++) {
        await sleep(200);
        const vid = document.querySelector('video');
        const vSrc = vid?.currentSrc || vid?.src;
        if (vSrc && (vSrc.includes('flow-content') || vSrc.startsWith('http') || vSrc.startsWith('blob:'))) {
          videoUrl = vSrc;
          duration = vid.duration || 0;
          break;
        }
      }

      const backBtn = Array.from(document.querySelectorAll('button')).find((b) =>
        (b.innerText && b.innerText.includes('arrow_back')) ||
        (b.getAttribute('aria-label') && b.getAttribute('aria-label').toLowerCase().includes('back'))
      );
      if (backBtn) {
        try {
          simulateClick(backBtn);
        } catch (_) {
          backBtn.click?.();
        }
        await sleep(400);
      }

      const label = tile.getAttribute?.('aria-label') || tile.innerText?.replace(/play_arrow|play_circle/g, '').trim() || '';
      return videoUrl ? { videoUrl, duration, label } : null;
    }

    async harvestProjectVideos() {
      if (typeof document === 'undefined') return [];

      const backBtn = Array.from(document.querySelectorAll('button')).find((b) =>
        (b.innerText && b.innerText.includes('arrow_back')) ||
        (b.getAttribute('aria-label') && b.getAttribute('aria-label').toLowerCase().includes('back'))
      );
      if (backBtn && typeof window !== 'undefined' && window.location && window.location.pathname && window.location.pathname.includes('/edit/')) {
        backBtn.click?.();
        await sleep(500);
      }

      const rawTiles = Array.from(document.querySelectorAll('flow-video-tile, flow-grid-tile-container')).filter((t) => {
        const text = (t.innerText || t.textContent || '').toLowerCase();
        const isError = !!t.querySelector('flow-error-tile') || /failed|policy/i.test(text);
        const isProgress = /queued|\b\d{1,2}%\b|generating|rendering/i.test(text);
        const hasPlay = !!t.querySelector('mat-icon, button[aria-label*="Play" i], .mobile-play-badge') || t.tagName?.toLowerCase() === 'flow-video-tile';
        return hasPlay && !isError && !isProgress;
      });

      const uniqueTiles = [];
      const seenElements = new Set();
      for (const t of rawTiles) {
        const container = t.closest('flow-grid-tile-container') || t;
        if (!seenElements.has(container)) {
          seenElements.add(container);
          uniqueTiles.push(container);
        }
      }

      const chronologicalTiles = [...uniqueTiles].reverse();
      const results = [];

      for (let i = 0; i < chronologicalTiles.length; i++) {
        const tile = chronologicalTiles[i];
        const resolved = await this.resolveTileVideoUrl(tile);
        if (resolved && resolved.videoUrl) {
          results.push({
            index: i,
            scene_index: i + 1,
            label: resolved.label,
            video_url: resolved.videoUrl,
            duration: resolved.duration,
          });
        }
      }

      return results;
    }

    async monitorVideoRender(timeoutMs = 600000, sinceTimestamp = 0, maxRetries = 2) {
      this.notifyProgress('RENDERING_VIDEO', 'Sedang memproses render video di Google Flow...');

      const startTime = Date.now();
      let videoReadyEvent = null;
      let videoRetryCount = 0;

      while (Date.now() - startTime < timeoutMs) {
        if (typeof document !== 'undefined') {
          const allTiles = Array.from(document.querySelectorAll('flow-video-tile, flow-grid-tile-container, flow-tile-container, [class*="tile"], flow-error-tile, .error-tile'));
          const isAnyTileRendering = allTiles.some((t) => {
            if (isFlowErrorCard(t)) return false;
            const text = (t.innerText || t.textContent || '').toLowerCase();
            const isProgress = /queued/i.test(text) || /\b\d{1,2}%\b/.test(text) || /rendering/i.test(text) || /generating/i.test(text);
            const hasSpinner = !!t.querySelector('mat-spinner, .spinner, [role="progressbar"], svg.circular-loader');
            return isProgress || hasSpinner;
          });

          const failedTile = allTiles.find((t) => isFlowErrorCard(t)) ||
            document.querySelector('flow-error-tile, .error-tile, .error-message');

          if (failedTile) {
            const retryBtn = findRetryButtonInCard(failedTile);
            const cardRetriedCount = Number(failedTile.dataset?.retriedCount || 0);

            if (retryBtn && videoRetryCount < maxRetries && cardRetriedCount < maxRetries) {
              videoRetryCount++;
              if (failedTile.dataset) failedTile.dataset.retriedCount = String(cardRetriedCount + 1);
              this.notifyProgress(
                'VIDEO_RETRY',
                `⚠️ Render video ditolak/gagal di Google Flow ("Gagal / Kebijakan"). Menekan tombol Retry otomatis (Percobaan ${videoRetryCount}/${maxRetries})...`
              );
              setAllowInput(true);
              await simulateClick(retryBtn);
              await sleep(4000);
              continue;
            }
          }
        }

        try {
          videoReadyEvent = await this.waitForNetworkEvent('VIDEO_READY', 4000, sinceTimestamp);
          if (videoReadyEvent) break;
        } catch (_) {}

        if (typeof document !== 'undefined') {
          const videoTiles = Array.from(document.querySelectorAll('flow-video-tile, flow-grid-tile-container')).filter((t) => {
            const isError = isFlowErrorCard(t);
            const text = (t.innerText || t.textContent || '').toLowerCase();
            const isProgress = /queued/i.test(text) || /\b\d{1,2}%\b/.test(text) || /rendering/i.test(text);
            const hasPlay = !!t.querySelector('mat-icon, button[aria-label*="Play" i], .mobile-play-badge') || t.tagName?.toLowerCase() === 'flow-video-tile';
            return !isError && !isProgress && hasPlay;
          });

          if (videoTiles.length > 0) {
            for (const tile of videoTiles) {
              const resolved = await this.resolveTileVideoUrl(tile);
              const vUrl = resolved?.videoUrl;
              if (vUrl && (!this._seenVideoUrls || !this._seenVideoUrls.has(vUrl))) {
                if (!this._seenVideoUrls) this._seenVideoUrls = new Set();
                this._seenVideoUrls.add(vUrl);
                const completedVideo = {
                  id: `vid_${Date.now()}`,
                  url: vUrl,
                  downloadUrl: vUrl,
                  duration: resolved?.duration || 0,
                  label: resolved?.label || '',
                };
                this.notifyProgress('VIDEO_READY', 'Video selesai dirender di Google Flow!', {
                  video: completedVideo,
                  allVideos: [completedVideo],
                });
                return {
                  video: completedVideo,
                  videos: [completedVideo],
                  event: null,
                };
              }
            }
          }
        }

        await sleep(2000);
      }

      const videos = videoReadyEvent?.videos || [];
      let primaryVideoUrl = videoReadyEvent?.videoUrls?.[0] || videos[0]?.url || videos[0]?.downloadUrl;

      if (!primaryVideoUrl && (videoReadyEvent?.operationIds?.[0] || videoReadyEvent?.mediaIds?.[0])) {
        try {
          const mediaId = videoReadyEvent.operationIds?.[0] || videoReadyEvent.mediaIds?.[0];
          const mediaRes = await this.callDirectRpc('RPC_GET_MEDIA_URL', { mediaId });
          if (mediaRes && mediaRes.videoUrl) {
            primaryVideoUrl = mediaRes.videoUrl;
          }
        } catch {}
      }

      if (!primaryVideoUrl && typeof document !== 'undefined') {
        const vids = Array.from(document.querySelectorAll('video')).filter(v => v.src && v.src.includes('flow-content') && (!this._seenVideoUrls || !this._seenVideoUrls.has(v.src)));
        if (vids.length > 0) {
          primaryVideoUrl = vids[0].src;
        }
      }

      if (!primaryVideoUrl && videos.length === 0) {
        if (typeof document !== 'undefined') {
          const allTiles = Array.from(document.querySelectorAll('flow-video-tile, flow-grid-tile-container, flow-tile-container, [class*="tile"], flow-error-tile, .error-tile'));
          const failedTile = allTiles.find((t) => isFlowErrorCard(t)) ||
            document.querySelector('flow-error-tile, .error-tile, .error-message');
          if (failedTile) {
            const errText = (failedTile.innerText || failedTile.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 150);
            throw new Error(`FLOW_GENERATION_FAILED_AFTER_RETRIES: Render video ditolak atau gagal di Google Flow: ${errText}`);
          }
        }
        throw new Error('Video selesai dirender namun URL unduhan tidak ditemukan.');
      }

      if (!this._seenVideoUrls) this._seenVideoUrls = new Set();
      if (primaryVideoUrl) this._seenVideoUrls.add(primaryVideoUrl);

      const completedVideo = videos[0] || {
        id: videoReadyEvent?.operationIds?.[0] || `vid_${Date.now()}`,
        url: primaryVideoUrl,
        downloadUrl: primaryVideoUrl,
      };

      this.notifyProgress('VIDEO_READY', 'Video affiliator selesai dirender dan siap diunduh!', {
        video: completedVideo,
        allVideos: videos,
      });

      return {
        video: completedVideo,
        videos,
        event: videoReadyEvent,
      };
    }

    async generateStoryboardImageDirect(prompt, uploadedMediaIds = [], storyboardSettings = {}, projectId = '', timeoutMs = 180000) {
      this.notifyProgress('CONFIGURING_MODE', 'Mengatur opsi generasi gambar storyboard/karakter...');
      await this.configureImageSettings(storyboardSettings);
      await sleep(300);

      if (uploadedMediaIds && uploadedMediaIds.length > 0) {
        this.notifyProgress('ATTACHING_REFERENCE', `Memasukkan ${uploadedMediaIds.length} gambar referensi ke composer...`);
      }

      await this.fillPrompt(prompt);
      await sleep(300);

      await this.triggerImageGeneration({ skipDelay: true });

      const startTime = Date.now();
      const domResult = await this.waitForImageGenerationDomDone(timeoutMs, startTime);

      const imageUrl = domResult?.src || domResult?.url || null;
      const mediaId = domResult?.mediaId || (imageUrl ? (imageUrl.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i)?.[0] || imageUrl) : null);

      this.notifyProgress('IMAGE_READY', 'Gambar storyboard/karakter berhasil dibuat!', {
        mediaId,
        url: imageUrl,
      });

      return {
        id: mediaId,
        mediaId,
        url: imageUrl,
        downloadUrl: imageUrl,
        aspectRatio: storyboardSettings.aspectRatio || '9:16',
      };
    }

    async generateAffiliateVideoDirect(motionPrompt, currentStartMedia, options = {}, projectId = '', videoTimeoutMs = 600000, isPass2Plus = false) {
      if (!isPass2Plus) {
        await this.configureOptimalAffiliateVideoSettings(options);
        await sleep(300);
      }

      await this.fillPrompt(motionPrompt);
      await sleep(300);

      if (currentStartMedia) {
        if (typeof currentStartMedia === 'object' && currentStartMedia.base64Data) {
          await this.attachFrameToStartSlot(currentStartMedia, 30000);
        } else if (typeof currentStartMedia === 'string') {
          await this.attachGeneratedImageToPrompt({ mediaId: currentStartMedia, id: currentStartMedia });
        }
        await sleep(300);
      }

      await this.triggerVideoRender(motionPrompt);

      const renderResult = await this.monitorVideoRender(videoTimeoutMs);
      return renderResult?.video || null;
    }

    abort(taskId) {
      console.warn('[FlowTaskExecutor] Task aborted:', taskId);
      this.isCancelled = true;
      this.isRunning = false;
      this.currentTaskId = null;
      this.unblockUserInteraction();
    }

    async execute(taskPayload) {
      if (!taskPayload) throw new Error('Task payload is required');
      this.currentTaskId = taskPayload.taskId || `task_${Date.now()}`;
      this.isRunning = true;
      this.isCancelled = false;
      this.interceptedEvents = [];
      this.blockUserInteraction();

      try {
        if (taskPayload.action === 'FLOW_HARVEST_PROJECT_VIDEOS' || taskPayload.action === 'HARVEST_PROJECT_VIDEOS' || taskPayload.kind === 'harvest_videos') {
          this.notifyProgress('HARVESTING_VIDEOS', 'Mengumpulkan seluruh video yang telah dirender di kanvas Google Flow...');
          const harvested = await this.harvestProjectVideos();
          this.notifyProgress('HARVEST_COMPLETE', `Berhasil mengumpulkan ${harvested.length} video dari Google Flow.`, { count: harvested.length });
          return {
            success: true,
            videos: harvested,
            count: harvested.length,
          };
        }

        this.notifyProgress('INIT', 'Menyiapkan sesi Google Flow...');
        if (this.isCancelled) throw new Error('Task aborted');

        const storyboardSettings = taskPayload.storyboard || {};
        const isPass2Plus = !!taskPayload.isPass2Plus || !!taskPayload.passFrameData;

        if (!isPass2Plus) {
          await this.ensureProject();
        }
        if (this.isCancelled) throw new Error('Task aborted');

        await this.ensureAgentOff();
        if (this.isCancelled) throw new Error('Task aborted');

        let uploadedMedia = [];
        let uploadedMediaIds = [];
        let generatedImage = null;

        if (!isPass2Plus) {
          if (!taskPayload.skipImageGeneration) {
            await this.configureImageSettings(storyboardSettings);
            await sleep(400);
          }
          if (this.isCancelled) throw new Error('Task aborted');

          const imageSource = (Array.isArray(taskPayload.images) && taskPayload.images.length > 0)
            ? taskPayload.images
            : (Array.isArray(taskPayload.imagesData) && taskPayload.imagesData.length > 0)
            ? taskPayload.imagesData
            : (taskPayload.image || taskPayload.imageData || taskPayload.imagePath || taskPayload.imagePaths);

          if (imageSource) {
            uploadedMedia = await this.uploadMultipleImages(imageSource, taskPayload.projectId || '', taskPayload.timeoutMs || 45000);
          }
          if (this.isCancelled) throw new Error('Task aborted');

          uploadedMediaIds = uploadedMedia.map((m) => m.mediaId).filter(Boolean);

          if (!taskPayload.skipImageGeneration) {
            await this.configureImageSettings(storyboardSettings);
            await sleep(400);
          }
          if (this.isCancelled) throw new Error('Task aborted');

          const imagePrompt = taskPayload.prompt || taskPayload.remakePrompt || 'Affiliate product cinematic showcase';
          if (!taskPayload.skipImageGeneration) {
            generatedImage = await this.generateStoryboardImageDirect(
              imagePrompt,
              uploadedMediaIds,
              storyboardSettings,
              taskPayload.projectId || '',
              taskPayload.timeoutMs || 180000
            );
          }
          if (this.isCancelled) throw new Error('Task aborted');
        }

        let completedVideoResult = null;
        let passVideoResults = [];
        let passImageResults = generatedImage?.url ? [generatedImage.url] : [];
        const isVideoTask = taskPayload.kind === 'video' || taskPayload.videoPrompt !== undefined || taskPayload.options?.mode === 'video';

        if (isVideoTask) {
          if (this.isCancelled) throw new Error('Task aborted');
          const passCount = Math.max(1, Number(taskPayload.options?.passCount || 1));
          const videoPrompts = Array.isArray(taskPayload.videoPrompts) && taskPayload.videoPrompts.length > 0
            ? taskPayload.videoPrompts
            : [taskPayload.videoPrompt || taskPayload.motionPrompt || 'Smooth 360 rotation cinematic showcase with soft studio lighting'];

          const startMediaId = generatedImage?.mediaId || generatedImage?.id || uploadedMediaIds[0] || '';
          let currentStartMedia = startMediaId;

          for (let pass = 1; pass <= passCount; pass++) {
            const motionPrompt = videoPrompts[pass - 1] || videoPrompts[0] || 'Smooth 360 rotation cinematic showcase with soft studio lighting';
            this.notifyProgress('RENDERING_VIDEO', `Sedang memproses render video klip ${pass}/${passCount} di Google Flow...`, {
              pass,
              passCount,
              motionPrompt,
            });

            const currentPassIs2Plus = isPass2Plus || pass > 1;

            const videoItem = await this.generateAffiliateVideoDirect(
              motionPrompt,
              currentStartMedia,
              taskPayload.options || {},
              taskPayload.projectId || '',
              taskPayload.videoTimeoutMs || 600000,
              currentPassIs2Plus
            );

            if (videoItem) {
              passVideoResults.push(videoItem);
              completedVideoResult = videoItem;
            }

            if (pass < passCount) {
              const prevVideoUrl = videoItem?.url || videoItem?.downloadUrl;
              if (prevVideoUrl) {
                const extractedFrame = await this.extractLastFrameFromVideoUrl(prevVideoUrl);
                if (extractedFrame) {
                  currentStartMedia = extractedFrame;
                  if (extractedFrame.fileName) {
                    passImageResults.push(extractedFrame.fileName);
                  }
                }
              }
              await sleep(1500);
            }
          }
        }

        if (isVideoTask) {
          this.notifyProgress('DELIVERING_VIDEO', 'Mengirimkan hasil video dan metadata ke Sinematica...');
        } else {
          this.notifyProgress('DELIVERING_IMAGE', 'Mengirimkan hasil gambar karakter dan metadata ke Sinematica...');
        }

        const finalResult = {
          ok: true,
          taskId: this.currentTaskId,
          status: 'COMPLETED',
          uploadedMedia,
          generatedImage,
          mediaId: generatedImage?.mediaId || generatedImage?.id || null,
          imageUrl: generatedImage?.url || null,
          downloadImageUrl: generatedImage?.url || null,
          video: completedVideoResult,
          videoUrl: completedVideoResult?.url || completedVideoResult?.downloadUrl || null,
          downloadUrl: completedVideoResult?.downloadUrl || completedVideoResult?.url || null,
          videoPaths: passVideoResults.map((v) => v.url || v.downloadUrl).filter(Boolean),
          passVideoPaths: passVideoResults.map((v) => v.url || v.downloadUrl).filter(Boolean),
          passImagePaths: passImageResults,
          metadata: {
            aspectRatio: taskPayload.options?.aspectRatio || storyboardSettings.aspectRatio || '9:16',
            model: taskPayload.options?.model || 'Omni Flash',
            storyboardModel: storyboardSettings.model || 'nano-banana-2',
            durationSeconds: taskPayload.options?.durationSeconds || 8,
            passCount: taskPayload.options?.passCount || 1,
            totalDuration: taskPayload.options?.totalDuration || 8,
            timestamp: Date.now(),
          },
          timestamp: Date.now(),
        };

        const completionMsg = isVideoTask
          ? 'Video affiliator berhasil dibuat dan diterima di Sinematica!'
          : 'Gambar karakter/storyboard berhasil dibuat di Google Flow!';
        this.notifyProgress('COMPLETED', completionMsg, finalResult);
        this.onCompleted(finalResult);
        return finalResult;
      } catch (err) {
        const rawMsg = err.message || String(err);
        let friendlyAdvice = rawMsg;
        if (/quota|credit|saldo|kredit|limit|resource_exhausted|429/i.test(rawMsg)) {
          friendlyAdvice = 'Kuota akun Google ini telah habis atau sedang dibatasi. Silakan gunakan profil Chrome lain atau tunggu beberapa saat.';
        } else if (/unauthenticated|login|session|auth|401/i.test(rawMsg)) {
          friendlyAdvice = 'Sesi login Google Flow telah berakhir. Silakan login kembali di tab Google Flow Anda.';
        } else if (/permission|forbidden|403/i.test(rawMsg)) {
          friendlyAdvice = 'Akses ke fitur Google Flow ditolak untuk akun Google ini.';
        }

        this.notifyProgress('FAILED', friendlyAdvice, { error: friendlyAdvice, rawError: rawMsg });
        this.onError({ taskId: this.currentTaskId, error: friendlyAdvice, rawError: rawMsg });
        throw new Error(friendlyAdvice);
      } finally {
        this.unblockUserInteraction();
        this.isRunning = false;
      }
    }
  }

  FlowTaskExecutor.prototype.blockUserInteraction = blockUserInteraction;
  FlowTaskExecutor.prototype.unblockUserInteraction = unblockUserInteraction;

  const exportObj = {
    FlowTaskExecutor,
    FRIENDLY_STEPS,
    simulateClick,
    simulateInput,
    b64toBlob,
    isFlowErrorCard,
    findRetryButtonInCard,
    blockUserInteraction,
    unblockUserInteraction,
  };

  if (typeof window !== 'undefined') {
    window.__sinematicaBlock = blockUserInteraction;
    window.__sinematicaUnblock = unblockUserInteraction;
  }
  if (typeof globalThis !== 'undefined') {
    globalThis.__sinematicaBlock = blockUserInteraction;
    globalThis.__sinematicaUnblock = unblockUserInteraction;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = exportObj;
  } else if (typeof window !== 'undefined') {
    window.FlowTaskExecutor = exportObj;
  } else if (typeof globalThis !== 'undefined') {
    globalThis.FlowTaskExecutor = exportObj;
  }
})(typeof globalThis !== 'undefined' ? globalThis : typeof self !== 'undefined' ? self : this);
