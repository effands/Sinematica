/**
 * Sinematica Flow Agent — Content Script
 * Bridges main-world intercepted network events from window.postMessage
 * to the extension background service worker via chrome.runtime.sendMessage,
 * while maintaining existing auth/captcha and sniffing capabilities.
 */

(function () {
  'use strict';

  const MESSAGE_SOURCE = 'SINEMATICA_FLOW_INTERCEPTOR';
  let activeExecutor = null;
  const pendingRpcRequests = new Map();
  let lastReportedEmail = '';
  let lastReportedCredits = '';

  function dispatchMainWorldRpc(action, payload, timeoutMs = 60000) {
    if (typeof window !== 'undefined' && typeof window.__sinematica_uploadImageDirect === 'function') {
      if (action === 'RPC_UPLOAD_IMAGE' || action === 'DISPATCH_INPAGE_UPLOAD') {
        return window.__sinematica_uploadImageDirect(payload);
      } else if (action === 'RPC_GENERATE_IMAGE' && typeof window.__sinematica_generateImageDirect === 'function') {
        return window.__sinematica_generateImageDirect(payload);
      } else if (action === 'RPC_GENERATE_VIDEO' && typeof window.__sinematica_generateVideoDirect === 'function') {
        return window.__sinematica_generateVideoDirect(payload);
      } else if (action === 'RPC_GET_MEDIA_URL' && typeof window.__sinematica_getMediaDownloadUrlDirect === 'function') {
        return window.__sinematica_getMediaDownloadUrlDirect(payload.mediaId);
      }
    }

    return new Promise((resolve, reject) => {
      const requestId = `rpc_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
      const timer = setTimeout(() => {
        pendingRpcRequests.delete(requestId);
        reject(new Error(`In-page direct RPC [${action}] timed out after ${timeoutMs / 1000}s`));
      }, timeoutMs);

      pendingRpcRequests.set(requestId, { resolve, reject, timer });

      window.postMessage({
        source: 'SINEMATICA_CONTENT_SCRIPT',
        action,
        requestId,
        payload,
      }, '*');
    });
  }

  // Expose on window
  window.__sinematica_dispatchMainWorldRpc = dispatchMainWorldRpc;

  function safeSendMessage(message) {
    try {
      if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.id) {
        const res = chrome.runtime.sendMessage(message);
        if (res && typeof res.catch === 'function') {
          res.catch(() => {});
        }
      }
    } catch (_) {}
  }

  function getExecutor() {
    if (activeExecutor) return activeExecutor;
    const ExecutorClass = (typeof window !== 'undefined' && window.FlowTaskExecutor?.FlowTaskExecutor) ||
      (typeof globalThis !== 'undefined' && globalThis.FlowTaskExecutor?.FlowTaskExecutor) ||
      (typeof window !== 'undefined' && window.FlowTaskExecutor) ||
      (typeof globalThis !== 'undefined' && globalThis.FlowTaskExecutor);
    if (!ExecutorClass) return null;

    activeExecutor = new ExecutorClass({
      onProgress: (progress) => {
        safeSendMessage({
          type: 'TASK_PROGRESS',
          payload: progress,
        });
      },
      onCompleted: (result) => {
        safeSendMessage({
          type: 'TASK_COMPLETED',
          payload: result,
        });
      },
      onError: (err) => {
        safeSendMessage({
          type: 'TASK_FAILED',
          payload: err,
        });
      },
    });
    return activeExecutor;
  }

  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (msg.type === 'ENSURE_PROJECT_CANVAS' || msg.action === 'ENSURE_PROJECT_CANVAS') {
      const url = window.location.href || '';
      const userPrefix = url.match(/\/u\/(\d+)/i)?.[0] || '';
      const projId = msg.projectId || url.match(/\/project\/([0-9a-fA-F-]{36})/i)?.[1];
      if (projId && /^[0-9a-fA-F-]{36}$/.test(projId)) {
        let isRoot = false;
        try {
          const parsed = new URL(url);
          const normalized = parsed.pathname.replace(/^\/u\/\d+/, '').replace(/\/$/, '');
          isRoot = normalized === `/project/${projId}`;
        } catch (_) {}
        if (!isRoot) {
          window.location.href = `https://flow.google.com${userPrefix}/project/${projId}`;
          reply({ ok: true, navigated: true });
          return true;
        }
      }
      const btn = document.querySelector('button.new-project-button') ||
                  Array.from(document.querySelectorAll('button, a, [role="button"], div')).find(b => {
                    const text = (b.innerText || b.textContent || b.getAttribute('aria-label') || '').trim().toLowerCase();
                    return text.includes('new project') || text.includes('project baru') || text.includes('proyek baru');
                  });
      if (btn) {
        btn.click();
        reply({ ok: true, clicked: true });
      } else {
        reply({ ok: false, message: 'Button not found or already in project' });
      }
      return true;
    }

    if (msg.type === 'GET_PAGE_AUTH_TOKEN') {
      let token = null;
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const v = localStorage.getItem(localStorage.key(i));
          if (v && typeof v === 'string' && v.includes('ya29.')) {
            const m = v.match(/ya29\.[A-Za-z0-9_.~-]+/);
            if (m && m[0]) { token = m[0]; break; }
          }
        }
        if (!token) {
          for (let i = 0; i < sessionStorage.length; i++) {
            const v = sessionStorage.getItem(sessionStorage.key(i));
            if (v && typeof v === 'string' && v.includes('ya29.')) {
              const m = v.match(/ya29\.[A-Za-z0-9_.~-]+/);
              if (m && m[0]) { token = m[0]; break; }
            }
          }
        }
      } catch (_) {}
      reply({ flow_key: token });
      return true;
    }

    if (msg.type === 'GET_CAPTCHA') {
      const { requestId, pageAction } = msg;

      const handler = (e) => {
        if (e.detail?.requestId === requestId) {
          window.removeEventListener('CAPTCHA_RESULT', handler);
          clearTimeout(timer);
          reply({ token: e.detail.token, error: e.detail.error });
        }
      };

      const timer = setTimeout(() => {
        window.removeEventListener('CAPTCHA_RESULT', handler);
        reply({ error: 'CAPTCHA_TIMEOUT' });
      }, 25000);

      window.addEventListener('CAPTCHA_RESULT', handler);

      window.dispatchEvent(new CustomEvent('GET_CAPTCHA', {
        detail: { requestId, pageAction },
      }));

      return true;
    }

    if (msg.action === 'CANCEL_FLOW_TASK' || msg.type === 'CANCEL_FLOW_TASK') {
      const executor = getExecutor();
      if (executor) {
        executor.abort(msg.taskId);
      }
      reply({ ok: true, cancelled: true });
      return false;
    }

    if ((msg.action === 'EXECUTE_FLOW_TASK' || msg.type === 'EXECUTE_FLOW_TASK') && msg.payload) {
      const executor = getExecutor();
      if (!executor) {
        reply({ ok: false, error: 'Executor not initialized in page context' });
        return false;
      }

      reply({ ok: true, started: true, taskId: msg.payload.taskId });

      executor.execute(msg.payload).catch((err) => {
        console.warn('[Sinematica Content Bridge] Executor failed:', err);
      });
      return true;
    }
  });

  window.addEventListener('message', (event) => {
    // 1. Existing Flowkit message sniffers
    if (event.data?.type === '__FLOWKIT_AUTH__' && event.data.value) {
      try { chrome.runtime.sendMessage({ type: 'CAPTURE_FLOW_AUTH', value: event.data.value }).catch(() => {}); } catch (_) {}
      return;
    }
    if (event.data?.type === '__FLOWKIT_CREDITS__' && event.data.credits !== undefined) {
      try {
        chrome.runtime.sendMessage({
          type: 'SNIFFED_FLOW_CREDITS',
          credits: event.data.credits,
          timestamp: Date.now(),
        }).catch(() => {});
      } catch (_) {}
      return;
    }
    if (event.data?.type === '__FLOWKIT_SNIFF__') {
      const { url, body, method } = event.data;
      if (url) {
        try {
          chrome.runtime.sendMessage({
            type: 'SNIFFED_AISANDBOX_REQUEST',
            url,
            method,
            payload: body,
            timestamp: Date.now(),
          }).catch(() => {});
        } catch (_) {}
      }
      return;
    }

    // 1b. Flow task & page progress events
    if (event.data?.type === 'FLOW_TASK_PROGRESS' || event.data?.type === 'FLOW_PAGE_PROGRESS') {
      try {
        chrome.runtime.sendMessage(event.data).catch(() => {});
      } catch (_) {}
      return;
    }

    // 2. Interceptor events
    if (event.source !== window || !event.data || event.data.source !== MESSAGE_SOURCE) {
      return;
    }

    if (event.data.type === 'SINEMATICA_DIRECT_RPC_RESPONSE' && event.data.requestId) {
      const pending = pendingRpcRequests.get(event.data.requestId);
      if (pending) {
        clearTimeout(pending.timer);
        pendingRpcRequests.delete(event.data.requestId);
        if (event.data.ok) {
          pending.resolve(event.data.result);
        } else {
          pending.reject(new Error(event.data.error || 'Direct in-page RPC failed'));
        }
      }
      return;
    }

    const flowEvent = event.data.event;
    if (!flowEvent || !flowEvent.type) {
      return;
    }

    if (activeExecutor) {
      activeExecutor.handleNetworkEvent(flowEvent);
    }

    if (flowEvent.type === 'PROFILE_UPDATED') {
      if (flowEvent.email || flowEvent.credits) {
        lastReportedEmail = flowEvent.email || lastReportedEmail;
        lastReportedCredits = flowEvent.credits || lastReportedCredits;
        safeSendMessage({
          type: 'GOOGLE_FLOW_PROFILE_DETECTED',
          email: lastReportedEmail,
          credits: lastReportedCredits,
          url: window.location.href,
        });
      }
    }

    safeSendMessage({
      type: 'GOOGLE_FLOW_API_EVENT',
      event: flowEvent,
      url: window.location.href,
      timestamp: Date.now(),
    });
  });

  // Automatic DOM Scanner for visible credits
  function scanCreditsFromPage() {
    try {
      const text = document.body ? (document.body.innerText || document.body.textContent || '') : '';
      const m = text.match(/([\d,.]+)\s*(?:Google Flow credits?|credits?|kredit(?: google flow)?|poin|points?)/i);
      if (m && m[1] && /\d/.test(m[1])) {
        const token = m[1];
        const raw = Number(token.includes('.') && /^\d{1,3}(?:\.\d{3})+$/.test(token)
          ? token.replace(/\./g, '')
          : token.replace(/,/g, ''));
        if (Number.isFinite(raw)) {
          chrome.runtime.sendMessage({
            type: 'SNIFFED_FLOW_CREDITS',
            credits: raw,
            timestamp: Date.now(),
          }).catch(() => {});
        }
      }
    } catch (_) {}
  }

  setInterval(scanCreditsFromPage, 2000);
  if (typeof MutationObserver !== 'undefined' && document.documentElement) {
    const obs = new MutationObserver(() => scanCreditsFromPage());
    obs.observe(document.documentElement, { childList: true, subtree: true });
  }

  // Fallback DOM injector: ensures main-world scripts exist if document_start was skipped
  function ensureMainWorldScripts() {
    try {
      if (document.getElementById('sinematica-flow-interceptor-script')) {
        return;
      }

      const parserScript = document.createElement('script');
      parserScript.id = 'sinematica-flow-parser-script';
      parserScript.src = chrome.runtime.getURL('flow-network-parser.js');
      parserScript.onload = function () {
        this.remove();

        const interceptorScript = document.createElement('script');
        interceptorScript.id = 'sinematica-flow-interceptor-script';
        interceptorScript.src = chrome.runtime.getURL('flow-interceptor.js');
        interceptorScript.onload = function () {
          this.remove();
        };
        (document.head || document.documentElement).appendChild(interceptorScript);
      };

      (document.head || document.documentElement).appendChild(parserScript);
    } catch (_) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureMainWorldScripts);
  } else {
    ensureMainWorldScripts();
  }
  // Auto-detect and enter project canvas ONLY on initial home landing without interfering with active canvas
  if (typeof window !== 'undefined' && window.location.hostname.includes('flow.google.com')) {
    if (window.location.pathname === '/' || window.location.pathname === '') {
      setTimeout(() => {
        if (window.location.pathname === '/' || window.location.pathname === '') {
          const btn = document.querySelector('button.new-project-button') ||
                      Array.from(document.querySelectorAll('button')).find(b => /new project/i.test(b.innerText || ''));
          if (btn) {
            console.log('[Sinematica Agent] Initializing project canvas on root landing...');
            btn.click();
          }
        }
      }, 2500);
    }
  }
})();
