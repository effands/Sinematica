/**
 * Sinematica Flow Agent — Content Script (Identical to proven Affilia engine)
 */
(function () {
  const s = document.createElement('script');
  s.src = chrome.runtime.getURL('injected.js');
  s.onload = () => s.remove();
  (document.head || document.documentElement).appendChild(s);
})();

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
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
});

window.addEventListener('message', (e) => {
  if (e.data?.type === '__FLOWKIT_CREDITS__' && e.data.credits !== undefined) {
    try {
      chrome.runtime.sendMessage({
        type: 'SNIFFED_FLOW_CREDITS',
        credits: e.data.credits,
        timestamp: Date.now(),
      }).catch(() => {});
    } catch (_) {}
    return;
  }
  if (e.data?.type !== '__FLOWKIT_SNIFF__') return;
  const { url, body, method } = e.data;
  if (!url) return;
  try {
    chrome.runtime.sendMessage({
      type: 'SNIFFED_AISANDBOX_REQUEST',
      url,
      method,
      payload: body,
      timestamp: Date.now(),
    }).catch(() => {});
  } catch (_) {}
});

// Automatic DOM Scanner: Scans whenever the Google Account panel is opened or visible on screen
function scanCreditsFromPage() {
  try {
    const text = document.body ? (document.body.innerText || document.body.textContent || '') : '';
    const m = text.match(/([\d,.]+)\s*(?:Google Flow credits?|credits?|kredit(?: google flow)?|poin|points?)/i);
    if (m && m[1] && /\d/.test(m[1])) {
      const raw = Number(m[1].replace(/,/g, ''));
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
