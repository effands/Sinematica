/**
 * Sinematica Flow Agent — Injected Script (Isolated inside IIFE scope)
 * Has access to window.grecaptcha.enterprise & sniffs Flow traffic
 */
(function () {
  if (window.__SINEMATICA_INJECTED__) return;
  window.__SINEMATICA_INJECTED__ = true;

  const FLOW_SITE_KEY = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';

  const _xhrOpen = XMLHttpRequest.prototype.open;
  const _xhrSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__sniffUrl = url;
    this.__sniffMethod = method;
    return _xhrOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (body) {
    try {
      const url = this.__sniffUrl || '';
      if (url.includes('googleapis.com') || url.includes('labs.google') || url.includes('flow.google.com')) {
        window.postMessage({
          type: '__FLOWKIT_SNIFF__',
          url,
          body: typeof body === 'string' ? body : `(binary)`,
          method: this.__sniffMethod || 'POST',
        }, '*');
      }
      this.addEventListener('load', function () {
        try {
          if (url.includes('aisandbox-pa.googleapis.com') && this.responseText) {
            const data = JSON.parse(this.responseText);
            const rem = data.remainingCredits ?? data.credits;
            if (rem !== undefined && rem !== null && Number.isFinite(Number(rem))) {
              window.postMessage({ type: '__FLOWKIT_CREDITS__', credits: Number(rem) }, '*');
            }
          }
        } catch (_) {}
      });
    } catch (_) {}
    return _xhrSend.call(this, body);
  };

  const _originalFetch = window.fetch;
  window.fetch = async function (...args) {
    try {
      const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      let bodyText = '';
      if (args[1]?.body) {
        const b = args[1].body;
        const keepFull = url.includes('aisandbox-pa.googleapis.com');
        const limit = keepFull ? 400000 : 5000;
        if (typeof b === 'string') bodyText = b.length > limit ? b.slice(0, 200) + '...' : b;
        else bodyText = '(binary)';
      }
      window.postMessage({
        type: '__FLOWKIT_SNIFF__',
        url, body: bodyText, method: args[1]?.method || 'GET',
      }, '*');
    } catch (_) {}

    const res = await _originalFetch.apply(this, args);

    try {
      const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      if (url.includes('aisandbox-pa.googleapis.com')) {
        const clone = res.clone();
        clone.json().then(data => {
          if (data && typeof data === 'object') {
            const rem = data.remainingCredits ?? data.credits;
            if (rem !== undefined && rem !== null && Number.isFinite(Number(rem))) {
              window.postMessage({ type: '__FLOWKIT_CREDITS__', credits: Number(rem) }, '*');
            }
          }
        }).catch(() => {});
      }
    } catch (_) {}

    return res;
  };

  window.addEventListener('GET_CAPTCHA', async ({ detail }) => {
    const { requestId, pageAction } = detail;
    try {
      await waitForGrecaptcha();
      let siteKey = FLOW_SITE_KEY;
      try {
        if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {
          for (const k in window.___grecaptcha_cfg.clients) {
            const c = window.___grecaptcha_cfg.clients[k];
            if (c && c.sitekey) {
              siteKey = c.sitekey;
              break;
            }
          }
        }
      } catch (_) {}

      const action = pageAction || 'IMAGE_GENERATION';
      const token = await window.grecaptcha.enterprise.execute(siteKey, { action });
      console.log('[Sinematica Agent] reCAPTCHA Enterprise token solved successfully for action:', action);
      window.dispatchEvent(new CustomEvent('CAPTCHA_RESULT', {
        detail: { requestId, token },
      }));
    } catch (e) {
      console.warn('[Sinematica Agent] reCAPTCHA Enterprise solve failed:', e);
      window.dispatchEvent(new CustomEvent('CAPTCHA_RESULT', {
        detail: { requestId, error: e.message },
      }));
    }
  });

  function waitForGrecaptcha(timeout = 10000) {
    return new Promise((resolve, reject) => {
      const start = Date.now();
      const check = () => {
        if (window.grecaptcha?.enterprise?.execute) return resolve();
        if (Date.now() - start > timeout) return reject(new Error('grecaptcha not available'));
        setTimeout(check, 200);
      };
      check();
    });
  }
})();
