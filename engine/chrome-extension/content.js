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
