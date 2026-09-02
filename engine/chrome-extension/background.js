/**
 * Sinematica Flow Agent — Chrome Extension Background Service Worker
 * Executes API requests natively in tab main world with real reCAPTCHA Enterprise tokens.
 */

importScripts('trpc-response.js', 'flow-tab.js');

const API_KEY = 'AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY';

const WS_URL = 'ws://127.0.0.1:8888/ws/agent';
const RECONNECT_BASE_MS = 2000;
const RECONNECT_MAX_MS = 8000;   // server dev sering restart; jangan menunggu terlalu lama

let ws = null;
let flowKey = null;
let instanceId = null;
let instanceName = "Chrome Profile";
let currentProjectId = null;

let reconnectTimer = null;
let reconnectAttempts = 0;
let offlineLogged = false;

// Requests Sinematica itself fires also pass through webRequest. Without this guard the
// schema learner would "learn" from our own rejected guesses instead of from the Flow UI.
let selfRequestsInFlight = 0;

chrome.storage.local.get(['instanceId', 'instanceName', 'flowKey', 'currentProjectId'], (data) => {
  if (data.instanceId) {
    instanceId = data.instanceId;
  } else {
    instanceId = 'profile-' + Math.random().toString(36).substring(2, 10);
    chrome.storage.local.set({ instanceId });
  }
  if (data.instanceName) instanceName = data.instanceName;
  if (data.flowKey) flowKey = data.flowKey;
  if (data.currentProjectId) currentProjectId = data.currentProjectId;

  init();
});

try {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
} catch (_) {}

function recordMetrics(isSuccess, reqType = 'IMAGE', errorMsg = '') {
  chrome.storage.local.get(['requestStats', 'requestLogs'], (d) => {
    const stats = d.requestStats || { total: 0, success: 0, failed: 0 };
    stats.total = (stats.total || 0) + 1;
    if (isSuccess) stats.success = (stats.success || 0) + 1;
    else stats.failed = (stats.failed || 0) + 1;

    const logs = d.requestLogs || [];
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

    logs.unshift({
      id: Math.random().toString(36).substring(2, 8),
      type: reqType,
      time: timeStr,
      status: isSuccess ? 'SUCCESS' : 'FAILED',
      error: isSuccess ? '-' : (errorMsg || 'HTTP Error')
    });

    const trimmedLogs = logs.slice(0, 30);

    chrome.storage.local.set({
      requestStats: stats,
      requestLogs: trimmedLogs,
      metricTotal: stats.total,
      metricSuccess: stats.success,
      metricFailed: stats.failed
    });
  });
}

// ─── Token Capture via webRequest ───────────────────────────
chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (!details?.requestHeaders?.length) return;
    const authHeader = details.requestHeaders.find(
      (h) => h.name?.toLowerCase() === 'authorization',
    );
    const value = authHeader?.value || '';
    if (!value.startsWith('Bearer ya29.')) return;

    const token = value.replace(/^Bearer\s+/i, '').trim();
    if (!token) return;

    if (flowKey !== token) {
      flowKey = token;
      chrome.storage.local.set({ flowKey });
      console.log('[Sinematica Agent] Captured OAuth Bearer token:', flowKey.slice(0, 20) + '...');
      notifyTokenCaptured();
    }
  },
  { urls: ['https://aisandbox-pa.googleapis.com/*', 'https://labs.google/*'] },
  ['requestHeaders'],
);

// ─── Capture Flow's own image requests at the network layer ─────────
// Reading them from the page (injected fetch/XHR hooks) depends on injection timing and on
// how the app happens to send the request. webRequest sees the bytes regardless.
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    try {
      if (details.method !== 'POST') return;
      if (!details.url.includes('flowMedia') && !details.url.includes('batchGenerate') && !details.url.includes('image')) return;
      if (details.url.includes('batchCheck') || details.url.includes('checkStatus') || details.url.includes('batchGenerateVideos')) return;
      if (selfRequestsInFlight > 0) return;   // this one is ours, not the Flow UI's
      const raw = details.requestBody && details.requestBody.raw;
      if (!raw || !raw.length || !raw[0].bytes) return;

      const payload = new TextDecoder('utf-8').decode(raw[0].bytes);
      if (!payload) return;

      console.log('[Sinematica Agent] Captured Flow image request (' + payload.length + ' bytes)');
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'flow_ui_request',
          url: details.url,
          payload,
          instance_id: instanceId,
        }));
      } else {
        // Backend was down at that moment; keep it so it can be replayed on reconnect.
        chrome.storage.local.set({ pendingFlowSample: { url: details.url, payload } });
      }
    } catch (err) {
      console.warn('[Sinematica Agent] Failed to read Flow image request:', err);
    }
  },
  { urls: ['https://aisandbox-pa.googleapis.com/*'] },
  ['requestBody'],
);

function flushPendingFlowSample() {
  chrome.storage.local.get(['pendingFlowSample'], (d) => {
    const sample = d.pendingFlowSample;
    if (!sample || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
      type: 'flow_ui_request',
      url: sample.url,
      payload: sample.payload,
      instance_id: instanceId,
    }));
    chrome.storage.local.remove('pendingFlowSample');
  });
}

async function _detectProjectIdFromTabs(preferredTabId = null) {
  try {
    const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
    if (tabs && tabs.length) {
      // chrome.tabs.query does not guarantee useful ordering. Always bind the
      // project to the tab selected for this request; otherwise an old Flow tab
      // can silently overwrite endpoint + clientContext with a stale project ID.
      const orderedTabs = [...tabs].sort((a, b) => {
        if (preferredTabId !== null) {
          if (a.id === preferredTabId && b.id !== preferredTabId) return -1;
          if (b.id === preferredTabId && a.id !== preferredTabId) return 1;
        }
        if (!!a.active !== !!b.active) return a.active ? -1 : 1;
        if (!!a.currentWindow !== !!b.currentWindow) return a.currentWindow ? -1 : 1;
        return (b.lastAccessed || 0) - (a.lastAccessed || 0);
      });
      for (const tab of orderedTabs) {
        if (tab.url) {
          const match = tab.url.match(/project\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
          if (match && match[1]) {
            const previousProjectId = currentProjectId;
            currentProjectId = match[1];
            chrome.storage.local.set({ currentProjectId });
            if (previousProjectId && previousProjectId !== currentProjectId) {
              console.log('[Sinematica Agent] Project aktif diperbarui:', previousProjectId, '→', currentProjectId);
            }
            return currentProjectId;
          }
        }
      }
    }
  } catch (e) {}
  return currentProjectId;
}

function init() {
  _detectProjectIdFromTabs();
  connectWebSocket();
  // Chrome clamps anything under 1 minute and logs a warning, so stay at the documented minimum.
  chrome.alarms.create('keepAlive', { periodInMinutes: 1 });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'keepAlive') {
    connectWebSocket();
    _detectProjectIdFromTabs().then(() => notifyRegistration());
  }
});

function scheduleReconnect() {
  if (reconnectTimer) return; // never let more than one retry be queued
  const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts), RECONNECT_MAX_MS);
  reconnectAttempts++;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
  }, delay);
}

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  let socket;
  try {
    socket = new WebSocket(WS_URL);
  } catch (ex) {
    scheduleReconnect();
    return;
  }
  ws = socket;

  socket.onopen = () => {
    if (socket !== ws) return;
    reconnectAttempts = 0;
    offlineLogged = false;
    console.log('[Sinematica Agent] Connected to Sinematica Backend Server!');
    notifyRegistration();
    flushPendingFlowSample();
  };

  socket.onmessage = async (event) => {
    if (socket !== ws) return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'api_request') {
        await handleApiRequest(msg);
      } else if (msg.type === 'trpc_request') {
        await handleTrpcRequest(msg);
      } else if (msg.type === 'download_request') {
        await handleDownloadRequest(msg);
      } else if (msg.type === 'ping' && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'pong' }));
      }
    } catch (err) {
      console.error('[Sinematica Agent] Message handler error:', err);
    }
  };

  socket.onclose = () => {
    if (socket !== ws) return; // a newer socket already replaced this one
    ws = null;
    if (!offlineLogged) {
      offlineLogged = true;
      console.warn('[Sinematica Agent] Backend belum tersedia. Mencoba menyambung ulang di latar belakang...');
    }
    scheduleReconnect();
  };

  // `onclose` always follows `onerror`, so retrying is handled there only.
  // Doing it here too would spawn duplicate sockets and duplicate registrations.
  socket.onerror = () => {};
}

async function handleTrpcRequest(msg) {
  const { id, params = {} } = msg;
  const { url, method = 'POST', headers = {}, body } = params;
  if (!url || !url.startsWith('https://labs.google/')) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'trpc_response', id, error: 'INVALID_TRPC_URL' }));
    }
    return;
  }
  const requestHeaders = { 'Content-Type': 'application/json', ...headers };
  try {
    // Resolve private Flow media from the authenticated page's MAIN world. A fetch from
    // the extension service worker has the extension as its cookie context, so Google's
    // media redirect can reject an otherwise valid project/media name.
    let targetTab = await FlowTab.ensureFlowTab(chrome);
    const tabResults = await chrome.scripting.executeScript({
      target: { tabId: targetTab.id },
      world: 'MAIN',
      func: async (fetchUrl, fetchMethod, fetchHeaders, fetchBody) => {
        try {
          const response = await fetch(fetchUrl, {
            method: fetchMethod,
            headers: fetchHeaders,
            body: fetchBody !== undefined && fetchBody !== null
              ? JSON.stringify(fetchBody)
              : undefined,
            credentials: 'include',
            redirect: 'follow',
          });
          const responseUrl = response.url || '';
          const contentType = response.headers.get('content-type') || '';
          const isMedia = /^video\//i.test(contentType)
            || /flow-content\.google|googleusercontent\.com|\.mp4(?:[?#]|$)/i.test(responseUrl);
          if (isMedia) {
            // Do not consume MP4 bytes here; the backend streams this final signed URL.
            return { status: response.status, data: { url: responseUrl }, responseUrl };
          }
          const responseText = await response.text();
          let data = {};
          try {
            data = responseText ? JSON.parse(responseText) : {};
          } catch (_) {
            data = { error: responseText.slice(0, 500) };
          }
          return { status: response.status, data, responseUrl };
        } catch (error) {
          return { status: 0, error: error?.message || String(error), responseUrl: '' };
        }
      },
      args: [url, method, requestHeaders, body],
    });
    let tabResult = tabResults?.[0]?.result || {};

    // A page-world fetch can be blocked while following the redirect to Flow's CDN
    // because the video response is cross-origin. Retry from the extension worker,
    // whose host permissions cover both labs.google and the signed CDN hosts.
    const tabResponseUrl = tabResult.responseUrl || '';
    const tabIsMedia = /flow-content\.google|googleusercontent\.com|googlevideo\.com|storage\.googleapis\.com|\.mp4(?:[?#]|$)/i.test(tabResponseUrl);
    if (!tabIsMedia) {
      try {
        const workerResponse = await fetch(url, {
          method,
          headers: requestHeaders,
          body: body !== undefined && body !== null ? JSON.stringify(body) : undefined,
          credentials: 'include',
          redirect: 'follow',
        });
        const workerResponseUrl = workerResponse.url || '';
        const workerContentType = workerResponse.headers.get('content-type') || '';
        const workerIsMedia = /^video\//i.test(workerContentType)
          || /flow-content\.google|googleusercontent\.com|googlevideo\.com|storage\.googleapis\.com|\.mp4(?:[?#]|$)/i.test(workerResponseUrl);
        if (workerIsMedia) {
          tabResult = {
            status: workerResponse.status,
            data: { url: workerResponseUrl },
            responseUrl: workerResponseUrl,
          };
        } else if (!tabResult.status || tabResult.status >= 400 || tabResult.error) {
          const detail = (await workerResponse.text()).slice(0, 500);
          tabResult = {
            status: workerResponse.status,
            data: { error: detail },
            responseUrl: workerResponseUrl,
            error: detail || `Flow resolver returned HTTP ${workerResponse.status}`,
          };
        }
      } catch (workerError) {
        if (!tabResult.error) tabResult.error = workerError?.message || String(workerError);
      }
    }
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'trpc_response', id, status: tabResult.status || 0,
        data: tabResult.data || {}, responseUrl: tabResult.responseUrl || '',
        ...(tabResult.error ? { error: tabResult.error } : {}),
      }));
    }
  } catch (error) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'trpc_response', id, error: error?.message || 'TRPC_FETCH_FAILED' }));
    }
  }
}

async function handleDownloadRequest(msg) {
  const { id, url } = msg;
  try {
    let authenticatedUrl = url;
    if (authenticatedUrl.startsWith('https://aisandbox-pa.googleapis.com/') && !authenticatedUrl.includes('key=')) {
      authenticatedUrl += (authenticatedUrl.includes('?') ? '&' : '?') + `key=${API_KEY}`;
    }
    const requestHeaders = {};
    if (flowKey && authenticatedUrl.startsWith('https://aisandbox-pa.googleapis.com/')) {
      requestHeaders.authorization = flowKey.startsWith('Bearer ') ? flowKey : `Bearer ${flowKey}`;
    }
    const response = await fetch(authenticatedUrl, {
      credentials: 'include',
      headers: requestHeaders,
    });
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 300);
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }
    if (!response.body) throw new Error('Respons unduhan Flow tidak memiliki stream data.');

    // Do not return an entire MP4 through executeScript. Chrome has to serialize that
    // result as one giant value and can silently stall on larger renders. Read the body
    // in the extension worker and forward bounded chunks as they arrive instead.
    const reader = response.body.getReader();
    const contentType = response.headers.get('content-type') || 'application/octet-stream';
    const chunks = [];
    let totalBytes = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value && value.byteLength) {
        chunks.push(value);
        totalBytes += value.byteLength;
      }
    }
    if (!totalBytes) throw new Error('Respons unduhan video kosong.');

    const transferChunkSize = 384 * 1024;
    const totalChunks = Math.ceil(totalBytes / transferChunkSize);
    if (!ws || ws.readyState !== WebSocket.OPEN) throw new Error('Koneksi backend terputus saat unduhan selesai.');
    ws.send(JSON.stringify({
      type: 'download_start', id, status: 200,
      content_type: contentType, total_chunks: totalChunks,
    }));

    let pending = new Uint8Array(0);
    let chunkIndex = 0;
    for (const incoming of chunks) {
      const combined = new Uint8Array(pending.byteLength + incoming.byteLength);
      combined.set(pending);
      combined.set(incoming, pending.byteLength);
      let offset = 0;
      while (combined.byteLength - offset >= transferChunkSize) {
        await sendDownloadChunk(id, chunkIndex++, combined.subarray(offset, offset + transferChunkSize));
        offset += transferChunkSize;
      }
      pending = combined.slice(offset);
    }
    if (pending.byteLength) await sendDownloadChunk(id, chunkIndex++, pending);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'download_complete', id, status: 200 }));
    }
  } catch (err) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'download_response', id, status: 500, error: err.toString() }));
    }
  }
}

async function sendDownloadChunk(id, index, bytes) {
  while (ws && ws.readyState === WebSocket.OPEN && ws.bufferedAmount > 4 * 1024 * 1024) {
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    throw new Error('Koneksi backend terputus saat transfer MP4.');
  }
  let binary = '';
  for (let offset = 0; offset < bytes.byteLength; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  ws.send(JSON.stringify({ type: 'download_chunk', id, index, data_base64: btoa(binary) }));
}

async function notifyRegistration() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  let flowTab = null;
  let readinessError = null;
  try {
    flowTab = await FlowTab.findExistingFlowTab(chrome);
    await _detectProjectIdFromTabs(flowTab?.id ?? null);
  } catch (error) {
    readinessError = error?.message || String(error);
  }
  const readiness = readinessError
    ? { ready: false, error: readinessError }
    : FlowTab.readinessState({ tab: flowTab, flowKey, projectId: currentProjectId });
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'register',
    instance_id: instanceId,
    name: instanceName,
    flow_key: flowKey,
    project_id: currentProjectId,
    ready: readiness.ready,
    readiness_error: readiness.error,
  }));
}

function notifyTokenCaptured() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'token_captured',
    instance_id: instanceId,
    flow_key: flowKey
  }));
  notifyRegistration();
}

// ─── Native Main World API Request Proxy ───────────────────
async function handleApiRequest(msg) {
  const { id, endpoint, body, flow_key } = msg;

  let targetTab;
  try {
    targetTab = await FlowTab.ensureFlowTab(chrome);
  } catch (e) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'api_response',
        id,
        status: 400,
        data: { error: 'FLOW_TAB_NOT_READY: ' + e.toString() }
      }));
    }
    notifyRegistration();
    return;
  }

  // Resolve the project from the exact tab that will execute this request.
  await _detectProjectIdFromTabs(targetTab.id);

  // Special Async DOM Scraping for Google Flow Credits (Extracts exact number e.g. '894 Credits')
  if (endpoint === '/v1/credits' || endpoint === '/internal/get_credits_from_dom') {
    try {
      const domResults = await chrome.scripting.executeScript({
        target: { tabId: targetTab.id },
        func: async () => {
          try {
            const parseCreditStr = (str) => {
              if (!str) return null;
              const m = str.match(/([\d,.]+)\s*(?:Google Flow credits|credits)/i);
              if (m && m[1]) {
                return m[1].replace(/,/g, '') + " Credits";
              }
              return null;
            };

            // 1. Check existing text first
            let bodyText = document.body ? document.body.innerText : "";
            let found = parseCreditStr(bodyText);
            if (found) return { credits: found };

            // 2. Click avatar button & wait for popup rendering
            const avatarBtn = document.querySelector('button[aria-label*="Google Account"], button[aria-label*="Account"], img[src*="googleusercontent"], [data-identifier]');
            if (avatarBtn) {
              const targetClick = avatarBtn.closest('button') || avatarBtn;
              targetClick.click();
              await new Promise(r => setTimeout(r, 450));

              bodyText = document.body ? document.body.innerText : "";
              found = parseCreditStr(bodyText);

              if (!found) {
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                  if (el.shadowRoot) {
                    const sTxt = el.shadowRoot.innerText || el.shadowRoot.textContent || "";
                    found = parseCreditStr(sTxt);
                    if (found) break;
                  }
                }
              }

              // Toggle popup closed
              targetClick.click();
              if (found) return { credits: found };
            }

            // 3. TreeWalker fallback
            const walk = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walk.nextNode()) {
              const val = node.nodeValue || "";
              if (val.toLowerCase().includes('credits')) {
                const parentText = node.parentElement ? node.parentElement.innerText : val;
                found = parseCreditStr(parentText);
                if (found) return { credits: found };
              }
            }

            return { credits: null };
          } catch (e) {
            return { error: e.toString() };
          }
        }
      });

      const resObj = (domResults && domResults[0] && domResults[0].result) ? domResults[0].result : {};
      const creditsFound = resObj.credits || "Unlimited (Kuota Melimpah)";

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'api_response',
          id,
          status: 200,
          data: {
            credits: creditsFound,
            details: resObj
          }
        }));
      }
      return;
    } catch (domErr) {
      console.warn('[Sinematica Agent] Error scraping DOM credits:', domErr);
    }
  }

  let targetEndpoint = endpoint;
  if (currentProjectId && targetEndpoint.includes('/projects/')) {
    targetEndpoint = targetEndpoint.replace(/projects\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i, `projects/${currentProjectId}`);
  }

  let baseUrl = targetEndpoint.startsWith('http') ? targetEndpoint : `https://aisandbox-pa.googleapis.com${targetEndpoint}`;
  if (!baseUrl.includes('key=')) {
    baseUrl += (baseUrl.includes('?') ? '&' : '?') + `key=${API_KEY}`;
  }
  const url = baseUrl;

  let captchaAction = 'VIDEO_GENERATION';
  if (endpoint.includes('batchGenerateImages') || endpoint.includes('flowMedia')) {
    captchaAction = 'IMAGE_GENERATION';
  }

  try {
    const activeBearerKey = flow_key || flowKey;
    const isOwnImageRequest = endpoint.includes('batchGenerateImages');
    if (isOwnImageRequest) selfRequestsInFlight++;

    let attempts = 0;
    const maxAttempts = 3;
    let lastTabErr = null;

    while (attempts < maxAttempts) {
      attempts++;
      try {
        const tabCheck = await chrome.tabs.get(targetTab.id).catch(() => null);
        if (!tabCheck) {
          const freshTabs = await chrome.tabs.query({ url: '*://labs.google/*' });
            if (freshTabs && freshTabs.length) {
              targetTab = freshTabs[0];
            } else {
              targetTab = await FlowTab.ensureFlowTab(chrome);
            }
        } else if (tabCheck.status === 'loading') {
          await new Promise(r => setTimeout(r, 1500));
        }

        const results = await chrome.scripting.executeScript({
          target: { tabId: targetTab.id },
          world: 'MAIN',
          func: async (fetchUrl, requestBody, actionName, projId, bearerKey) => {
            try {
              let captchaToken = null;
              if (window.grecaptcha && window.grecaptcha.enterprise && window.grecaptcha.enterprise.execute) {
                let siteKey = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';
                if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {
                  for (const k in window.___grecaptcha_cfg.clients) {
                    const c = window.___grecaptcha_cfg.clients[k];
                    if (c && c.sitekey) { siteKey = c.sitekey; break; }
                  }
                }
                try {
                  captchaToken = await window.grecaptcha.enterprise.execute(siteKey, { action: actionName });
                } catch (gErr) {
                  console.warn('[Flow In-Tab] grecaptcha execute error:', gErr);
                }
              }

              let finalBody = requestBody;
              if (finalBody && typeof finalBody === 'object') {
                finalBody = JSON.parse(JSON.stringify(finalBody));
                
                if (finalBody.clientContext) {
                  if (projId) finalBody.clientContext.projectId = projId;
                  if (captchaToken) {
                    if (!finalBody.clientContext.recaptchaContext) finalBody.clientContext.recaptchaContext = {};
                    finalBody.clientContext.recaptchaContext.token = captchaToken;
                  }
                }

                if (finalBody.requests && Array.isArray(finalBody.requests)) {
                  for (const r of finalBody.requests) {
                    if (r && typeof r === 'object' && r.clientContext) {
                      if (projId) r.clientContext.projectId = projId;
                      if (captchaToken) {
                        if (!r.clientContext.recaptchaContext) r.clientContext.recaptchaContext = {};
                        r.clientContext.recaptchaContext.token = captchaToken;
                      }
                    }
                  }
                }

                if (finalBody.operations && Array.isArray(finalBody.operations)) {
                  for (const op of finalBody.operations) {
                    if (op && typeof op === 'object') {
                      if (op.clientContext) {
                        if (projId) op.clientContext.projectId = projId;
                        if (captchaToken) {
                          if (!op.clientContext.recaptchaContext) op.clientContext.recaptchaContext = {};
                          op.clientContext.recaptchaContext.token = captchaToken;
                        }
                      }
                    }
                  }
                }
              }

              const reqHeaders = { 'Content-Type': 'application/json' };
              let activeToken = bearerKey;

              if (!activeToken) {
                try {
                  for (let i = 0; i < localStorage.length; i++) {
                    const v = localStorage.getItem(localStorage.key(i));
                    if (v && typeof v === 'string' && v.includes('ya29.')) {
                      const m = v.match(/ya29\.[A-Za-z0-9_-]+/);
                      if (m && m[0]) { activeToken = m[0]; break; }
                    }
                  }
                } catch (_) {}
              }

              if (activeToken) {
                reqHeaders['Authorization'] = activeToken.startsWith('Bearer ') ? activeToken : `Bearer ${activeToken}`;
              }

              const res = await fetch(fetchUrl, {
                method: 'POST',
                headers: reqHeaders,
                credentials: 'include',
                body: JSON.stringify(finalBody)
              });

              const status = res.status;
              let data = {};
              try { data = await res.json(); } catch (_) {}
              return { status, data };
            } catch (err) {
              return { status: 500, error: err.toString() };
            }
          },
          args: [url, body, captchaAction, currentProjectId, activeBearerKey]
        });

        if (isOwnImageRequest) selfRequestsInFlight = Math.max(0, selfRequestsInFlight - 1);

        if (results && results[0] && results[0].result) {
          const { status, data } = results[0].result;
          const isPolling = endpoint.includes('batchCheck') || endpoint.includes('checkStatus');
          if (!isPolling) {
            const reqType = (endpoint.includes('batchGenerateImages') || endpoint.includes('flowMedia')) ? 'IMAGE' : 'VIDEO';
            const errDetail = status === 200 ? '' : `HTTP ${status}`;
            recordMetrics(status === 200, reqType, errDetail);
          }

          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'api_response',
              id,
              status,
              data
            }));
          }
          return;
        }
      } catch (tabErr) {
        lastTabErr = tabErr;
        console.warn(`[Sinematica Agent] executeScript attempt ${attempts} error:`, tabErr);
        if (attempts < maxAttempts) {
          await new Promise(r => setTimeout(r, 1500));
        }
      }
    }

    if (isOwnImageRequest) selfRequestsInFlight = Math.max(0, selfRequestsInFlight - 1);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'api_response',
        id,
        status: 500,
        data: { error: lastTabErr ? lastTabErr.toString() : 'Gagal mengeksekusi script di tab Flow setelah beberapa kali mencoba.' }
      }));
    }
  } catch (tabErr) {
    if (endpoint.includes('batchGenerateImages')) {
      selfRequestsInFlight = Math.max(0, selfRequestsInFlight - 1);
    }
    console.error('[Sinematica Agent] executeScript error:', tabErr);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'api_response',
        id,
        status: 500,
        data: { error: tabErr.toString() }
      }));
    }
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'SNIFFED_AISANDBOX_REQUEST' && msg.url) {
    const match = msg.url.match(/projects\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
    if (match && match[1] && match[1] !== currentProjectId) {
      currentProjectId = match[1];
      chrome.storage.local.set({ currentProjectId });
      console.log('[Sinematica Agent] Sniffed current Flow Project ID:', currentProjectId);
      notifyRegistration();
    }

    // Forward image-generation bodies so the backend can learn Flow's real request shape.
    if (msg.payload && msg.url.includes('batchGenerateImages') && ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({
          type: 'flow_ui_request',
          url: msg.url,
          payload: msg.payload,
          instance_id: instanceId
        }));
      } catch (_) {}
    }
  }

  if (msg.type === 'UPDATE_PROFILE_NAME' && msg.name) {
    instanceName = msg.name;
    chrome.storage.local.set({ instanceName });
    notifyRegistration();
    sendResponse({ success: true });
  }

  if (msg.type === 'GET_AGENT_STATUS') {
    sendResponse({
      instanceId,
      instanceName,
      connected: ws && ws.readyState === WebSocket.OPEN,
      loggedIn: !!flowKey,
      flowKey,
      currentProjectId
    });
  }
});
