function encodeUiVideoHandle(url) {
  if (!url || typeof url !== 'string') return `ui_video_${Date.now()}`;
  try {
    const b64 = btoa(unescape(encodeURIComponent(url)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
    return `ui_video:${b64}`;
  } catch (_) {
    return `ui_video:${url.replace(/[^a-zA-Z0-9_-]/g, '')}`;
  }
}

function decodeUiVideoHandle(handle) {
  if (!handle || typeof handle !== 'string' || !handle.startsWith('ui_video:')) return null;
  const raw = handle.slice('ui_video:'.length);
  try {
    let b64 = raw.replace(/-/g, '+').replace(/_/g, '/');
    while (b64.length % 4 !== 0) b64 += '=';
    return decodeURIComponent(escape(atob(b64)));
  } catch (_) {
    try {
      let b64 = raw.replace(/-/g, '+').replace(/_/g, '/');
      while (b64.length % 4 !== 0) b64 += '=';
      return atob(b64);
    } catch (_) {
      return null;
    }
  }
}

/**
 * Sinematica Flow Agent — Chrome Extension Background Service Worker
 * Executes API requests natively in tab main world with real reCAPTCHA Enterprise tokens.
 */

importScripts(
  'flow-network-parser.js',
  'flow-executor.js',
  'trpc-response.js',
  'flow-tab.js',
  'flow-auth.js',
  'flow-logger.js',
  'flow-project.js',
  'flow-composer-editor.js',
  'flow-composer-config.js',
  'flow-composer-ingredients.js',
  'flow-watcher.js',
  'flow-recaptcha.js',
  'flow-api-client.js'
);

const API_KEY = 'AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY';

const WS_URL = 'ws://127.0.0.1:8888/ws/agent';
const RECONNECT_BASE_MS = 2000;
const RECONNECT_MAX_MS = 8000;   // server dev sering restart; jangan menunggu terlalu lama

let ws = null;
let flowKey = null;
let instanceId = null;
let instanceName = "Chrome Profile";
let currentProjectId = null;
let lastKnownCredits = null;
let flowSessionReady = false;

const logger = (typeof FlowLogger !== 'undefined' && FlowLogger.createLogger)
  ? FlowLogger.createLogger({
      instanceId,
      projectId: currentProjectId,
      wsSender: (payload) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          try { ws.send(JSON.stringify(payload)); } catch (_) {}
        }
      }
    })
  : {
      debug: () => {},
      info: (tag, msg, meta) => console.log(`[${tag}] ${msg}`, meta || ''),
      warn: (tag, msg, meta) => console.warn(`[${tag}] ${msg}`, meta || ''),
      error: (tag, msg, meta) => console.error(`[${tag}] ${msg}`, meta || ''),
      setContext: () => {}
    };

let reconnectTimer = null;
let reconnectAttempts = 0;
let offlineLogged = false;
let registrationRefreshTimer = null;
let sessionRecovery = null;
let lastSessionRecoveryAt = 0;

// Requests Sinematica itself fires also pass through webRequest. Without this guard the
// schema learner would "learn" from our own rejected guesses instead of from the Flow UI.
let selfRequestsInFlight = 0;

chrome.storage.local.get(['instanceId', 'instanceName', 'flowKey', 'currentProjectId', 'lastKnownCredits'], (data) => {
  if (data.instanceId) {
    instanceId = data.instanceId;
  } else {
    instanceId = 'profile-' + Math.random().toString(36).substring(2, 10);
    chrome.storage.local.set({ instanceId });
  }
  if (data.instanceName) instanceName = data.instanceName;
  if (data.flowKey) flowKey = data.flowKey;
  if (data.currentProjectId) currentProjectId = data.currentProjectId;
  if (data.lastKnownCredits !== undefined && data.lastKnownCredits !== null) {
    lastKnownCredits = Number(data.lastKnownCredits);
  }

  logger.setContext({ instanceId, projectId: currentProjectId });
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
    // Ignore Sinematica's own worker/injected requests. Otherwise an expired token
    // sent by this extension is immediately captured and persisted again.
    // Flow may issue generation requests from its own service worker, which
    // Chrome reports with tabId === -1. Do not discard those: they carry the
    // real OAuth bearer we need to relay. Sinematica's own requests remain
    // excluded by selfRequestsInFlight.
    if (selfRequestsInFlight > 0) return;
    if (!details?.requestHeaders?.length) return;
    const authHeader = details.requestHeaders.find(
      (h) => h.name?.toLowerCase() === 'authorization',
    );
    const value = authHeader?.value || '';
    // Google access-token prefixes are implementation details and can change. Restrict
    // capture by Flow tab + Google API URL instead of requiring the historic ya29 prefix.
    if (!/^Bearer\s+\S+/i.test(value)) return;

    const token = value.replace(/^Bearer\s+/i, '').trim();
    if (!token) return;

    if (flowKey !== token) {
      flowKey = token;
      chrome.storage.local.set({ flowKey });
      console.log('[Sinematica Agent] Captured Flow OAuth session.');
      notifyTokenCaptured();
    }
  },
  { urls: [
    'https://aisandbox-pa.googleapis.com/*',
    'https://aisandbox-pa.sandbox.googleapis.com/*',
    'https://*.googleapis.com/*',
    'https://*.google.com/*',
    'https://labs.google/*',
    'https://flow.google.com/*'
  ] },
  ['requestHeaders', 'extraHeaders'],
);

// Some service-worker initiated Flow requests expose Authorization only on the
// post-header event. Capture that path as well.
chrome.webRequest.onSendHeaders.addListener(
  (details) => {
    if (selfRequestsInFlight > 0 || !details?.requestHeaders?.length) return;
    const authHeader = details.requestHeaders.find(
      (h) => h.name?.toLowerCase() === 'authorization',
    );
    const value = authHeader?.value || '';
    if (details.url.includes('batchGenerateImages') && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'flow_ui_request_meta',
        instance_id: instanceId,
        header_names: details.requestHeaders.map(h => String(h.name || '').toLowerCase()).filter(Boolean),
        has_authorization: Boolean(authHeader),
        has_bearer: /^Bearer\s+\S+/i.test(value),
        has_cookie: details.requestHeaders.some(h => h.name?.toLowerCase() === 'cookie'),
      }));
    }
    if (!/^Bearer\s+\S+/i.test(value)) return;
    const token = value.replace(/^Bearer\s+/i, '').trim();
    if (!token || flowKey === token) return;
    flowKey = token;
    chrome.storage.local.set({ flowKey });
    console.log('[Sinematica Agent] Captured Flow OAuth session after headers sent.');
    notifyTokenCaptured();
  },
  { urls: [
    'https://aisandbox-pa.googleapis.com/*',
    'https://aisandbox-pa.sandbox.googleapis.com/*',
    'https://*.googleapis.com/*',
    'https://*.google.com/*',
    'https://labs.google/*',
    'https://flow.google.com/*'
  ] },
  ['requestHeaders', 'extraHeaders'],
);

function invalidateFlowAuth(reason = 'FLOW_LOGIN_EXPIRED') {
  if (!flowKey) return;
  flowKey = null;
  chrome.storage.local.remove('flowKey');
  console.warn('[Sinematica Agent] Flow OAuth token invalidated:', reason);
  notifyRegistration();
}

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
    let tabs = [];
    // Prefer the actual active tab in the last-focused window. This prevents a
    // restored/background Flow tab from supplying a stale project ID.
    try {
      const activeTabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      tabs = (activeTabs || []).filter(tab => FlowTab.isFlowUrl(tab.url || tab.pendingUrl));
    } catch (_) {}
    if (!tabs.length) tabs = await FlowTab.queryFlowTabs(chrome);
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
        const detected = FlowProject.detectProjectIdFromUrl(tab.url || tab.pendingUrl || '');
        if (detected) {
          const previousProjectId = currentProjectId;
          currentProjectId = detected;
          logger.setContext({ instanceId, projectId: currentProjectId });
          chrome.storage.local.set({ currentProjectId });
          if (previousProjectId && previousProjectId !== currentProjectId) {
            logger.info('PROJECT', `Project aktif diperbarui: ${previousProjectId} → ${currentProjectId}`, {
              previousProjectId,
              currentProjectId,
              tabId: tab.id,
            });
          }
          return currentProjectId;
        }
      }
    }
  } catch (e) {}
  return currentProjectId;
}

function init() {
  _detectProjectIdFromTabs();
  connectWebSocket();
  // A Flow tab can already be open before the extension worker starts. In that
  // case no navigation/request event is emitted after registration, leaving a
  // valid profile stuck at FLOW_LOGIN_REQUIRED. Probe each profile periodically
  // until its own session token is recovered.
  setInterval(() => {
    if (!flowKey) {
      _detectProjectIdFromTabs().then(() => notifyRegistration()).catch(() => {});
    }
  }, 10000);
  // Chrome clamps anything under 1 minute and logs a warning, so stay at the documented minimum.
  chrome.alarms.create('keepAlive', { periodInMinutes: 1 });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'keepAlive') {
    connectWebSocket();
    _detectProjectIdFromTabs().then(() => notifyRegistration());
  }
});

function scheduleRegistrationRefresh() {
  clearTimeout(registrationRefreshTimer);
  registrationRefreshTimer = setTimeout(() => {
    registrationRefreshTimer = null;
    _detectProjectIdFromTabs().then(() => notifyRegistration());
  }, 250);
}

// Report readiness immediately when Flow is opened, redirected, activated, or closed.
// The alarm remains as a recovery path if Chrome suspends the service worker.
chrome.tabs.onCreated.addListener((tab) => {
  if (FlowTab.isFlowUrl(tab.url || tab.pendingUrl)) scheduleRegistrationRefresh();
});
chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (FlowTab.isFlowUrl(changeInfo.url || tab.url || tab.pendingUrl)) scheduleRegistrationRefresh();
});
chrome.tabs.onActivated.addListener(() => scheduleRegistrationRefresh());
chrome.tabs.onRemoved.addListener(() => scheduleRegistrationRefresh());

function scheduleReconnect() {
  if (reconnectTimer) return; // never let more than one retry be queued
  const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts), RECONNECT_MAX_MS);
  reconnectAttempts++;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
  }, delay);
}

async function broadcastUnblockAllTabs() {
  try {
    if (typeof chrome !== 'undefined' && chrome.tabs && typeof chrome.tabs.query === 'function') {
      const tabs = await chrome.tabs.query({ url: '*://labs.google/fx/tools/flow*' }).catch(() => []);
      for (const tab of (tabs || [])) {
        if (tab && tab.id && chrome.scripting && typeof chrome.scripting.executeScript === 'function') {
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            world: 'MAIN',
            func: () => {
              if (typeof window !== 'undefined' && typeof window.__sinematicaUnblock === 'function') {
                window.__sinematicaUnblock();
              }
              if (typeof document !== 'undefined') {
                const blocker = document.getElementById('sinematica-interaction-blocker');
                if (blocker) blocker.remove();
                const cursor = document.getElementById('sinematica-fake-cursor');
                if (cursor) cursor.remove();
              }
            }
          }).catch(() => {});
        }
      }
    }
  } catch (_) {}
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
      } else if (msg.type === 'agent_task' || msg.type === 'execute_task' || msg.type === 'flow_task') {
        await handleFlowTask(msg);
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
    broadcastUnblockAllTabs();
    if (!offlineLogged) {
      offlineLogged = true;
      console.warn('[Sinematica Agent] Backend belum tersedia. Mencoba menyambung ulang di latar belakang...');
    }
    scheduleReconnect();
  };

  // `onclose` always follows `onerror`, so retrying is handled there only.
  // Doing it here too would spawn duplicate sockets and duplicate registrations.
  socket.onerror = () => {
    broadcastUnblockAllTabs();
  };
}

async function handleTrpcRequest(msg) {
  const { id, params = {} } = msg;
  const { url, method = 'POST', headers = {}, body } = params;
  if (!FlowTab.isTrustedFlowRequestUrl(url)) {
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
    // A profile may already have a valid Flow project/token while its tab was
    // closed or was opened after the worker registered. Ensure the tab here so
    // the fleet card does not incorrectly report NO_FLOW_WINDOW.
    flowTab = await FlowTab.ensureFlowTab(chrome);
    await _detectProjectIdFromTabs(flowTab?.id ?? null);
    if (!flowKey && flowTab?.id) {
      await _probeTokenFromTab(flowTab.id);
    }
  } catch (error) {
    readinessError = error?.message || String(error);
  }
  const readiness = readinessError
    ? { ready: false, error: readinessError }
    : FlowTab.readinessState({
      tab: flowTab,
      flowKey,
      sessionReady: flowSessionReady || !!flowKey || await hasFlowSessionCookie(),
      projectId: currentProjectId,
    });
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'register',
    instance_id: instanceId,
    name: instanceName,
    flow_key: flowKey,
    session_ready: flowSessionReady,
    project_id: currentProjectId,
    ready: readiness.ready,
    readiness_error: readiness.error,
    credits: Number.isFinite(Number(lastKnownCredits)) ? Number(lastKnownCredits) : null,
    version: chrome.runtime.getManifest().version,
  }));
}

async function hasFlowSessionCookie() {
  try {
    const names = ['SID', '__Secure-1PSID', '__Secure-3PSID', 'SAPISID', '__Secure-1PAPISID'];
    for (const name of names) {
      const cookie = await chrome.cookies.get({ url: 'https://flow.google.com/', name });
      if (cookie?.value) { flowSessionReady = true; return true; }
    }
  } catch (_) {}
  flowSessionReady = false;
  return false;
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

function sendTaskProgress(requestId, stage, message, extra = {}) {
  if (!requestId) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  try {
    ws.send(JSON.stringify({
      type: 'task_progress',
      id: requestId,
      stage: stage || 'PROGRESS',
      message: message || '',
      timestamp: Date.now(),
      ...(extra || {})
    }));
  } catch (_) {}
}

async function handleFlowTask(msg) {
  const taskId = msg.id || msg.taskId || msg.task_id || `task_${Date.now()}`;
  try {
    const targetTab = await FlowTab.ensureFlowTab(chrome);
    if (!targetTab || !targetTab.id) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'task_response',
          id: taskId,
          status: 500,
          error: 'FLOW_TAB_NOT_READY'
        }));
      }
      return;
    }

    const tabInfo = await chrome.tabs.get(targetTab.id).catch(() => null);
    if (tabInfo && tabInfo.status === 'loading') {
      await new Promise(r => setTimeout(r, 1500));
    }

    const payload = {
      taskId,
      ...msg.params,
      ...msg,
      projectId: msg.params?.projectId || msg.projectId || currentProjectId,
    };

    const sendTaskWithInjectionFallback = () => {
      chrome.tabs.sendMessage(targetTab.id, {
        type: 'EXECUTE_FLOW_TASK',
        payload
      }, async (res) => {
        const lastErr = chrome.runtime.lastError;
        if (lastErr) {
          console.warn('[Sinematica Agent] Content script unreachable, injecting scripts dynamically...');
          try {
            await chrome.scripting.executeScript({
              target: { tabId: targetTab.id },
              files: ['flow-network-parser.js', 'flow-executor.js', 'content.js'],
            });
            await new Promise(r => setTimeout(r, 600));
            chrome.tabs.sendMessage(targetTab.id, {
              type: 'EXECUTE_FLOW_TASK',
              payload
            }, (retryRes) => {
              const retryErr = chrome.runtime.lastError;
              if (retryErr && ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                  type: 'task_response',
                  id: taskId,
                  status: 500,
                  error: `CONTENT_SCRIPT_UNREACHABLE: ${retryErr.message}`
                }));
              }
            });
          } catch (injectErr) {
            if (ws && ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({
                type: 'task_response',
                id: taskId,
                status: 500,
                error: `CONTENT_SCRIPT_UNREACHABLE: ${lastErr.message}`
              }));
            }
          }
        }
      });
    };
    sendTaskWithInjectionFallback();
  } catch (err) {
    console.error('[Sinematica Agent] handleFlowTask error:', err);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'task_response',
        id: taskId,
        status: 500,
        error: err.toString()
      }));
    }
  }
}

async function generateImageViaAuthenticatedFlowUi(tabId, requestBody, requestId = null) {
  if (!tabId || !requestBody?.requests?.length) {
    return { status: 500, data: { error: 'FLOW_UI_FALLBACK_INVALID_REQUEST' } };
  }
  const prompt = requestBody.requests[0]?.structuredPrompt?.parts
    ?.find((part) => typeof part?.text === 'string')?.text;
  if (!prompt) {
    return { status: 500, data: { error: 'FLOW_UI_FALLBACK_PROMPT_MISSING' } };
  }

  sendTaskProgress(requestId, 'PREPARE_COMPOSER', 'Menyiapkan sesi Google Flow (Mode Image, Rasio, 1 output)...', { percent: 10 });
  const referenceIds = [];
  const collectReferenceIds = (value, key = '') => {
    if (Array.isArray(value)) return value.forEach((item) => collectReferenceIds(item, key));
    if (!value || typeof value !== 'object') {
      if (typeof value === 'string' && key === 'mediaId') referenceIds.push(value);
      if (typeof value === 'string' && key === 'name') {
        const match = value.match(/\/media\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i);
        if (match) referenceIds.push(match[1]);
      }
      return;
    }
    Object.entries(value).forEach(([childKey, childValue]) => collectReferenceIds(childValue, childKey));
  };
  collectReferenceIds(requestBody);

  try {
    let flowTabs = await FlowTab.queryFlowTabs(chrome);
    const isProjectComposer = (tab) => {
      try {
        const parsed = new URL(tab?.url || '');
        if (parsed.hostname !== 'flow.google.com') return false;
        const normalized = parsed.pathname.replace(/^\/u\/\d+/, '').replace(/\/$/, '');
        if (currentProjectId && normalized === `/project/${currentProjectId}`) return true;
        return /^\/project\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(normalized);
      } catch (_) {
        return false;
      }
    };

    let composerTabs = (flowTabs || []).filter(isProjectComposer);
    if (!composerTabs.length) {
      const candidateTab = (tabId ? await chrome.tabs.get(tabId).catch(() => null) : null) || (flowTabs && flowTabs[0]);
      const tabProjId = (candidateTab?.url || '').match(/\/project\/([0-9a-fA-F-]{36})/i)?.[1] || currentProjectId;
      const userPrefix = (candidateTab?.url || '').match(/\/u\/\d+/i)?.[0] || '';
      if (candidateTab && candidateTab.id && tabProjId) {
        const projectUrl = `https://flow.google.com${userPrefix}/project/${encodeURIComponent(tabProjId)}`;
        await chrome.tabs.update(candidateTab.id, { url: projectUrl });
        await new Promise(resolve => setTimeout(resolve, 2000));
        flowTabs = await FlowTab.queryFlowTabs(chrome);
        composerTabs = (flowTabs || []).filter(isProjectComposer);
      }
    }
    if (!composerTabs.length) {
      const targetTab = (flowTabs && flowTabs[0]) || (tabId ? await chrome.tabs.get(tabId).catch(() => null) : null);
      if (targetTab && targetTab.id) {
        const tabProjId = (targetTab.url || '').match(/\/project\/([0-9a-fA-F-]{36})/i)?.[1] || currentProjectId;
        const userPrefix = (targetTab.url || '').match(/\/u\/\d+/i)?.[0] || '';
        if (tabProjId) {
          const projectUrl = `https://flow.google.com${userPrefix}/project/${encodeURIComponent(tabProjId)}`;
          await chrome.tabs.update(targetTab.id, { url: projectUrl });
          await new Promise(resolve => setTimeout(resolve, 2000));
          flowTabs = await FlowTab.queryFlowTabs(chrome);
          composerTabs = (flowTabs || []).filter(isProjectComposer);
        } else {
          try {
            await chrome.tabs.sendMessage(targetTab.id, { action: 'ENSURE_PROJECT_CANVAS', projectId: currentProjectId }).catch(() => null);
          } catch (_) {}
          await chrome.scripting.executeScript({
            target: { tabId: targetTab.id },
            world: 'MAIN',
            func: async (knownProjId) => {
              const userPrefix = window.location.href.match(/\/u\/\d+/i)?.[0] || '';
              if (knownProjId && /^[0-9a-fA-F-]{36}$/.test(knownProjId)) {
                window.location.href = `https://flow.google.com${userPrefix}/project/${knownProjId}`;
                return;
              }
              const btn = document.querySelector('button.new-project-button') ||
                Array.from(document.querySelectorAll('button, a, [role="button"], div')).find(el => {
                  const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().toLowerCase();
                  return (text.includes('new project') || text.includes('project baru') || text.includes('proyek baru')) && !el.closest('flow-prompt-box');
                });
              if (btn) btn.click();
            },
            args: [currentProjectId]
          }).catch(() => null);
          await new Promise(resolve => setTimeout(resolve, 2500));
          flowTabs = await FlowTab.queryFlowTabs(chrome);
          composerTabs = (flowTabs || []).filter(isProjectComposer);
        }
      }
    }
    for (const t of composerTabs) {
      const match = (t.url || '').match(/\/project\/([0-9a-fA-F-]+)/i);
      if (match && match[1]) {
        currentProjectId = match[1];
        chrome.storage.local.set({ currentProjectId });
        break;
      }
    }
    const candidateIds = [...composerTabs.map(tab => tab.id)]
      .filter((id, index, list) => id && list.indexOf(id) === index);
    if (!candidateIds.length) {
      return { status: 503, data: { error: 'FLOW_UI_IMAGE_FALLBACK_COMPOSER_ROOT_UNAVAILABLE' } };
    }

    let result = null;
    try {
    for (const candidateId of candidateIds) {
      // Step 1: Configure settings, paste prompt into ProseMirror, and extract button coordinates
      const prepResult = await chrome.scripting.executeScript({
        target: { tabId: candidateId },
        world: 'MAIN',
        func: async (text, requestedRatio, requestedReferenceIds, reqId) => {
          if (typeof window !== 'undefined' && typeof window.__sinematicaBlock === 'function') {
            window.__sinematicaBlock();
          }
          const notifyProgress = (stage, message, percent = undefined) => {
            try {
              if (typeof window !== 'undefined' && window.postMessage) {
                window.postMessage({ type: 'FLOW_TASK_PROGRESS', id: reqId, stage, message, percent, source: 'FLOW_UI' }, '*');
              }
            } catch (_) {}
          };
          const sleep = (ms) => new Promise(r => setTimeout(r, ms));
          const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
            const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
            return (!style || (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'))
                && (!rect || (rect.width > 0 && rect.height > 0));
          };
          const normalize = (value) => (value || '').toLowerCase().trim();
          const controls = () => Array.from(document.querySelectorAll(
            'flow-prompt-box-settings button, flow-prompt-box-settings [role="button"], flow-prompt-box-settings [role="radio"], flow-prompt-box-settings [role="option"], flow-prompt-box-settings mat-button-toggle, flow-prompt-box button, flow-prompt-box [role="button"], flow-add-menu-popover-content button, flow-mobile-add-menu button, button.settings-trigger-button, button.generate-icon-button, button.add-menu-trigger, mat-button-toggle, button'
          ));
          const allToggles = () => Array.from(document.querySelectorAll(
            'flow-prompt-box-settings mat-button-toggle, flow-prompt-box-settings [role="radio"], flow-prompt-box-settings [role="option"], flow-prompt-box-settings button, flow-prompt-box mat-button-toggle, flow-toggles mat-button-toggle, mat-button-toggle'
          ));
          const findLabelNode = (label) => {
            const needle = normalize(label);
            return allToggles().find(el => {
              if (!visible(el)) return false;
              const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
              const parts = text.split(/[\s\n\r_-]+/);
              return text === needle || parts.includes(needle) || text.endsWith(` ${needle}`) || text.includes(needle);
            });
          };
          const clickExact = (label) => {
            const node = findLabelNode(label);
            const target = node?.closest('button,[role="radio"],[role="option"],mat-button-toggle,label') || node;
            if (!target) return false;
            const clickTarget = target.querySelector('button') || target;
            clickTarget.click();
            return true;
          };
          const clickExactEventually = async (label, timeout = 5000) => {
            const deadline = Date.now() + timeout;
            while (Date.now() < deadline) {
              if (clickExact(label)) return true;
              await new Promise((resolve) => setTimeout(resolve, 150));
            }
            return false;
          };
          const selectedExact = (label) => {
            const node = findLabelNode(label);
            const target = node?.closest('button,[role="radio"],[role="option"],mat-button-toggle,label') || node;
            if (!target) return false;
            const parentTog = target.closest('mat-button-toggle') || target;
            const btn = parentTog.querySelector('button') || target;
            return parentTog.classList.contains('mat-button-toggle-checked')
                || parentTog.getAttribute('aria-checked') === 'true'
                || btn.getAttribute('aria-checked') === 'true'
                || node.getAttribute('aria-pressed') === 'true'
                || btn.getAttribute('aria-pressed') === 'true'
                || /(^|\s)(selected|checked|active)(\s|$)/i.test(parentTog.className)
                || /(^|\s)(selected|checked|active)(\s|$)/i.test(btn.className);
          };

          const findAddIngredientTrigger = () => {
            const promptBox = document.querySelector('flow-prompt-box, .flow-prompt-box, .prompt-box') || document;
            const direct = promptBox.querySelector('flow-add-menu button.add-menu-trigger, flow-add-menu button, button.add-menu-trigger, button.add-media-button');
            if (direct && visible(direct) && !direct.disabled) return direct;

            const primaryCandidates = Array.from(promptBox.querySelectorAll(
              'button.add-menu-trigger, button.add-media-button, button[aria-label*="Add" i], button[aria-label*="Tambah" i], button[aria-label*="Ingredient" i], button[aria-label*="Reference" i], button[aria-label*="Media" i]'
            ));
            for (const el of primaryCandidates) {
              if (el.closest('flow-ingredient-chip, flow-image-ingredient-chip, .chip-container, flow-ingredient-bar, flow-media-chip, .chip, flow-generate-icon-button, button.generate-icon-button')) {
                continue;
              }
              if (visible(el) && !el.disabled) return el;
            }
            const allBtns = Array.from(promptBox.querySelectorAll('button'));
            for (const btn of allBtns) {
              if (!visible(btn) || btn.disabled) continue;
              if (btn.closest('flow-ingredient-chip, flow-image-ingredient-chip, .chip-container, flow-ingredient-bar, flow-media-chip, .chip, flow-generate-icon-button, button.generate-icon-button')) {
                continue;
              }
              const label = normalize(btn.getAttribute('aria-label') || btn.innerText || btn.textContent || '');
              const icon = btn.querySelector('mat-icon, svg');
              const iconText = normalize(icon?.innerText || icon?.textContent || icon?.getAttribute('data-icon') || '');
              if (label === 'add' || label === 'tambah' || label.startsWith('add ') || label.startsWith('tambah ') || label.includes('ingredient') || iconText === 'add' || iconText === 'add_circle' || iconText === '+') {
                return btn;
              }
            }
            return null;
          };

          const addImageReferences = async (ids) => {
            if (!ids.length) return { added: 0, missing: [] };
            notifyProgress('OPENING_ADD_MENU', `Membuka menu pemilihan bahan untuk melampirkan ${ids.length} referensi karakter...`, 15);
            const normalizeText = (value) => normalize(value).replace(/[\s_-]/g, '');
            const selected = [];
            const missing = [];

            const extractToken = (val) => {
              if (!val) return '';
              const str = String(val);
              const uuid = str.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
              if (uuid) return uuid[1].toLowerCase();
              const asb = str.match(/AB-n[A-Za-z0-9_-]{12,}/);
              if (asb) return asb[0];
              return str.toLowerCase();
            };

            for (const id of ids) {
              const token = extractToken(id);
              notifyProgress('ATTACHING_REFERENCE', `Melampirkan referensi karakter (${selected.length + 1}/${ids.length})...`, 18 + (selected.length * 3));
              let popover = document.querySelector('flow-add-menu-popover-content, flow-mobile-add-menu, .mobile-add-menu-container');
              if (!popover) {
                const trigger = findAddIngredientTrigger();
                if (trigger && !trigger.classList.contains('add-menu-trigger-active')) {
                  trigger.click();
                }
              }

              let items = [];
              const deadline = Date.now() + 4000;
              while (Date.now() < deadline) {
                popover = document.querySelector('flow-add-menu-popover-content, flow-mobile-add-menu, .mobile-add-menu-container');
                if (popover) {
                  items = Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"]'));
                  if (items.length > 0) break;
                }
                await sleep(200);
              }

              if (!popover) {
                missing.push(id);
                continue;
              }

              // Ensure only Image assets (storyboards & character sheets) are targeted
              const imagesTab = Array.from(popover.querySelectorAll('[role="tab"], button, .mat-mdc-tab')).find(t => normalize(t.innerText || t.textContent).includes('image') || normalize(t.innerText || t.textContent).includes('gambar'));
              if (imagesTab) {
                imagesTab.click();
                await sleep(300);
              }

              const rawImageItems = Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"]'));
              items = rawImageItems.filter(el => {
                const hasImg = !!el.querySelector('img') || !!el.querySelector('video');
                const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
                if (!hasImg && (text.includes('create') || text.includes('buat') || text.includes('new') || text.includes('upload') || text.includes('unggah'))) {
                  return false;
                }
                if (text.includes('create character') || text.includes('buat karakter') || text.includes('new character') || text.includes('karakter baru')) {
                  return false;
                }
                return hasImg || el.classList.contains('asset-item');
              });

              // If popover is in detail view from previous item, click back button
              const backBtn = popover.querySelector('button[aria-label*="Back" i], button[aria-label*="Kembali" i], button.back-button');
              if (backBtn && visible(backBtn) && popover.querySelector('button.detail-add-to-prompt-btn')) {
                backBtn.click();
                await sleep(300);
                const recheckedRaw = Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"]'));
                items = recheckedRaw.filter(el => {
                  const hasImg = !!el.querySelector('img') || !!el.querySelector('video');
                  const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
                  if (!hasImg && (text.includes('create') || text.includes('buat') || text.includes('new') || text.includes('upload') || text.includes('unggah'))) {
                    return false;
                  }
                  if (text.includes('create character') || text.includes('buat karakter') || text.includes('new character') || text.includes('karakter baru')) {
                    return false;
                  }
                  return hasImg || el.classList.contains('asset-item');
                });
              }

              let matchedItem = null;

              if (token) {
                matchedItem = items.find(item => {
                  const img = item.querySelector('img');
                  const imgSrc = (img?.src || img?.currentSrc || '').toLowerCase();
                  const text = (item.innerText || item.textContent || '').toLowerCase();
                  const html = (item.outerHTML || '').toLowerCase();
                  return imgSrc.includes(token) || text.includes(token) || html.includes(token);
                });
              }

              if (!matchedItem && items.length > 0) {
                const unusedItems = items.filter(item => !selected.includes(item));
                if (unusedItems.length > 0) {
                  matchedItem = unusedItems[0];
                }
              }

              if (matchedItem) {
                matchedItem.click();
                await sleep(350);

                let addBtn = null;
                const addDeadline = Date.now() + 2500;
                while (Date.now() < addDeadline) {
                  addBtn = popover.querySelector('button.detail-add-to-prompt-btn') ||
                    controls().find(el => visible(el) && !el.disabled && normalize(el.innerText || el.textContent || '').includes('add to prompt'));
                  if (addBtn && !addBtn.disabled) break;
                  await sleep(150);
                }

                if (addBtn) {
                  addBtn.click();
                  selected.push(matchedItem);
                  await sleep(600);
                } else {
                  missing.push(id);
                }
              } else {
                missing.push(id);
              }
            }

            // Close popover if still open
            const openPopover = document.querySelector('flow-add-menu-popover-content');
            if (openPopover) {
              document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
              await sleep(250);
            }

            return { added: selected.length, missing };
          };

          const referenceResult = await addImageReferences(requestedReferenceIds || []);
          if ((requestedReferenceIds || []).length && referenceResult.added === 0) {
            notifyProgress('REFERENCE_WARNING', 'Referensi tidak ditemukan di popover; melanjutkan generate gambar dengan prompt...', 25);
          }
          const editor = document.querySelector('[contenteditable="true"], .ProseMirror, textarea');
          if (!editor) return { error: 'FLOW_UI_COMPOSER_UNAVAILABLE' };

          notifyProgress('CONFIGURING_MODE', 'Mengatur opsi gambar (Mode Image, Rasio, 1 output)...', 30);
          // Close any stray top-bar or context menus before opening prompt settings
          const strayMenu = document.querySelector('.cdk-overlay-pane:not(:has(flow-toggles)):not(:has(flow-add-menu-popover-content))');
          if (strayMenu) {
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
            await sleep(250);
          }

          const findSettingsTrigger = () => {
            const promptBox = document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') || document;
            const direct = promptBox.querySelector('.settings-trigger-button, button.settings-trigger-button, button[aria-label*="Settings trigger" i], button[aria-label*="Pemicu setelan" i], [data-test-id*="settings-trigger"]');
            if (direct && visible(direct)) return direct;

            const promptButtons = Array.from(promptBox.querySelectorAll('button, [role="button"], div[role="button"]')).filter(visible);
            
            const pill = promptButtons.find(btn => {
              const text = (btn.innerText || btn.textContent || '').trim();
              const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
              if (btn.closest('flow-generate-icon-button') || btn.querySelector('mat-icon.arrow_forward') || aria.includes('start') || aria.includes('mulai') || aria.includes('generate')) {
                return false;
              }
              return text.includes('•') || text.includes('·') || /720p|1080p|9:16|16:9|3:4|4:3|1:1|x1|x2|x4|banana|veo|video|image|gambar/i.test(text) ||
                     aria.includes('settings trigger') || aria.includes('pemicu setelan') || aria.includes('settings') || aria.includes('tune');
            });
            if (pill) return pill;

            if (promptButtons.length >= 2) {
              return promptButtons[promptButtons.length - 2];
            }
            return null;
          };

          const isSettingsPopoverOpen = () => !!document.querySelector('flow-prompt-box-settings, .cdk-overlay-pane:has(flow-toggles), .settings-content-overlay');
          if (!isSettingsPopoverOpen()) {
            const settingsTrigger = findSettingsTrigger();
            if (settingsTrigger) {
              settingsTrigger.click();
              await sleep(400);
            }
          }
          const selectFlowOption = async (type, targetValue) => {
            const normTarget = normalize(targetValue);
            const getToggles = () => Array.from(document.querySelectorAll('flow-prompt-box-settings mat-button-toggle, flow-toggles mat-button-toggle, .cdk-overlay-pane mat-button-toggle, mat-button-toggle-group mat-button-toggle, mat-button-toggle, button[role="radio"], button[role="tab"]'));
            
            for (let attempt = 0; attempt < 15; attempt++) {
              const toggles = getToggles().filter(visible);
              let matched = null;

              if (type === 'mode') {
                matched = toggles.find(t => {
                  const txt = normalize(t.innerText || t.textContent);
                  const aria = normalize(t.getAttribute('aria-label') || '');
                  if (normTarget === 'image' || normTarget === 'gambar') {
                    return (txt === 'image' || txt === 'gambar' || txt.includes('image') || txt.includes('gambar') || aria.includes('image') || aria.includes('gambar')) && !txt.includes('video');
                  }
                  if (normTarget === 'video') {
                    return (txt === 'video' || txt.includes('video') || aria.includes('video')) && !txt.includes('image');
                  }
                  return txt.includes(normTarget) || aria.includes(normTarget);
                });
              } else if (type === 'ratio') {
                const is16_9 = normTarget.includes('16:9') || normTarget.includes('landscape') || normTarget.includes('lanskap');
                const is9_16 = normTarget.includes('9:16') || normTarget.includes('portrait') || normTarget.includes('potret');
                const is1_1 = normTarget.includes('1:1') || normTarget.includes('square');
                const is3_4 = normTarget.includes('3:4');
                const key = is16_9 ? '16:9' : (is9_16 ? '9:16' : (is1_1 ? '1:1' : (is3_4 ? '3:4' : normTarget)));
                matched = toggles.find(t => {
                  const txt = normalize(t.innerText || t.textContent);
                  const aria = normalize(t.getAttribute('aria-label') || '');
                  return txt.includes(key) || aria.includes(key) || (is16_9 && (txt.includes('16_9') || txt.includes('landscape') || txt.includes('lanskap'))) || (is9_16 && (txt.includes('9_16') || txt.includes('portrait') || txt.includes('potret')));
                });
              } else if (type === 'count') {
                const countNum = (normTarget.match(/\d+/) || ['1'])[0];
                matched = toggles.find(t => {
                  const txt = normalize(t.innerText || t.textContent);
                  const aria = normalize(t.getAttribute('aria-label') || '');
                  return txt === `x${countNum}` || txt === countNum || txt.includes(`x${countNum}`) || aria.includes(`x${countNum}`);
                });
              } else {
                matched = toggles.find(t => {
                  const txt = normalize(t.innerText || t.textContent);
                  const aria = normalize(t.getAttribute('aria-label') || '');
                  return txt.includes(normTarget) || aria.includes(normTarget);
                });
              }

              if (matched) {
                const isChecked = matched.classList.contains('mat-button-toggle-checked')
                  || matched.getAttribute('aria-checked') === 'true'
                  || matched.querySelector('button[aria-checked="true"]')
                  || matched.getAttribute('aria-pressed') === 'true';
                if (!isChecked) {
                  const btn = matched.querySelector('button') || matched;
                  btn.click();
                  await sleep(200);
                }
                return true;
              }
              await sleep(150);
            }
            return false;
          };

          await selectFlowOption('mode', 'image');
          await sleep(200);

          const ratioLabel = (requestedRatio === 'IMAGE_ASPECT_RATIO_LANDSCAPE' || requestedRatio === '16:9' || requestedRatio === 'landscape') ? '16:9'
            : (requestedRatio === 'IMAGE_ASPECT_RATIO_PORTRAIT' || requestedRatio === '9:16' || requestedRatio === 'portrait') ? '9:16'
            : (requestedRatio === 'IMAGE_ASPECT_RATIO_3_4' || requestedRatio === '3:4') ? '3:4'
            : (requestedRatio === 'IMAGE_ASPECT_RATIO_SQUARE' || requestedRatio === '1:1' || requestedRatio === 'square') ? '1:1' : '16:9';
          if (ratioLabel) await selectFlowOption('ratio', ratioLabel);
          await selectFlowOption('count', '1');
          await sleep(250);

          const backdrop = document.querySelector('.cdk-overlay-backdrop');
          if (backdrop) backdrop.click();
          else document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
          await sleep(300);

          if (isSettingsPopoverOpen()) {
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
            await sleep(200);
          }

          notifyProgress('TYPING_PROMPT', `Mengisi prompt gambar: "${text.slice(0, 60)}..."`, 40);
          editor.focus();

          try {
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            if ((editor.innerText || editor.textContent || '').trim().length > 0) {
              editor.innerHTML = '<p><br></p>';
            }
          } catch (_) {}

          try {
            document.execCommand('insertText', false, text);
          } catch (_) {}

          try {
            if (typeof InputEvent !== 'undefined') {
              editor.dispatchEvent(new InputEvent('beforeinput', {
                bubbles: true, cancelable: true, inputType: 'insertText', data: text, composed: true,
              }));
              editor.dispatchEvent(new InputEvent('input', {
                bubbles: true, cancelable: true, inputType: 'insertText', data: text, composed: true,
              }));
            }
            if (typeof Event !== 'undefined') {
              editor.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
              editor.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            }
          } catch (_) {}

          const isButtonDisabled = (btn) => {
            if (!btn) return true;
            return btn.disabled ||
              (typeof btn.hasAttribute === 'function' && btn.hasAttribute('disabled')) ||
              (typeof btn.getAttribute === 'function' && btn.getAttribute('aria-disabled') === 'true') ||
              (btn.classList && typeof btn.classList.contains === 'function' && btn.classList.contains('mat-mdc-button-disabled'));
          };

          const findStartButton = () => {
            const direct = document.querySelector(
              'flow-generate-icon-button button, button.generate-icon-button, button[aria-label*="Start generation" i], button[aria-label*="Mulai pembuatan" i], button[aria-label*="Start" i], button[aria-label*="Generate" i], button[aria-label*="Submit" i], button[aria-label*="Send" i], button[aria-label*="Mulai" i], button[aria-label*="Buat" i], button[aria-label*="Hasilkan" i]'
            );
            if (direct && !isButtonDisabled(direct)) return direct;
            const promptBox = document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') || document;
            const queryAll = Array.from(promptBox.querySelectorAll(
              'flow-generate-icon-button button, button[type="submit"], [data-test-id*="generate"], button[aria-label*="generate" i], button[aria-label*="start" i], button[aria-label*="buat" i], button[aria-label*="mulai" i], button[aria-label*="hasilkan" i], button[aria-label*="submit" i], button[aria-label*="send" i], button',
            ));
            const matched = queryAll.find((el) => {
              if (isButtonDisabled(el)) return false;
              const label = [
                el.getAttribute('aria-label') || '',
                el.getAttribute('title') || '',
                el.innerText || '',
                el.textContent || '',
              ].join(' ').toLowerCase();
              if (label.includes('character') || label.includes('karakter') || label.includes('actor') || label.includes('upload') || label.includes('unggah') || label.includes('sidebar') || label.includes('settings') || label.includes('pemicu setelan')) {
                return false;
              }
              const inComposer = !!el.closest('flow-prompt-box') || !!el.closest('flow-generate-icon-button');
              const isGenerateText = /arrow|start|generate|submit|send|buat|mulai|hasilkan/i.test(label) || !!el.querySelector('mat-icon, svg');
              return inComposer && isGenerateText;
            });
            if (matched) return matched;

            const promptButtons = Array.from(promptBox.querySelectorAll('button')).filter((b) => {
              if (!b || isButtonDisabled(b)) return false;
              const txt = [b.getAttribute('aria-label') || '', b.innerText || '', b.textContent || ''].join(' ').toLowerCase();
              return !txt.includes('character') && !txt.includes('karakter') && !txt.includes('upload') && !txt.includes('unggah') && !txt.includes('sidebar') && !txt.includes('settings') && !txt.includes('pemicu setelan');
            });
            if (promptButtons.length > 0) {
              return promptButtons[promptButtons.length - 1];
            }
            return null;
          };

          let button = null;
          const buttonDeadline = Date.now() + 10000;
          while (Date.now() < buttonDeadline) {
            button = findStartButton()
              || document.querySelector('flow-generate-icon-button button')
              || document.querySelector('button[aria-label*="Start" i], button[aria-label*="Mulai" i]');
            const isReady = button && !isButtonDisabled(button) && (editor.innerText || editor.textContent || '').trim().length > 0;
            if (isReady) break;

            try {
              editor.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: ' ', composed: true }));
              editor.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', code: 'KeyA', bubbles: true, composed: true }));
              editor.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
              editor.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            } catch (_) {}

            await new Promise((resolve) => setTimeout(resolve, 250));
          }

          if (!button) {
            button = findStartButton()
              || document.querySelector('flow-generate-icon-button button')
              || document.querySelector('button[aria-label*="Start" i], button[aria-label*="Mulai" i]');
          }

          if (!button) {
            return { error: 'FLOW_UI_START_BUTTON_NOT_FOUND' };
          }

          button.scrollIntoView({ block: 'center', inline: 'center' });
          await new Promise((resolve) => setTimeout(resolve, 150));
          editor.focus();

          const target = button.querySelector('mat-icon, .mat-mdc-button-touch-target') || button;
          const rect = target.getBoundingClientRect();
          const clickX = Math.round(rect.left + rect.width / 2);
          const clickY = Math.round(rect.top + rect.height / 2);

          try {
            if (typeof window !== 'undefined') window.__sinematicaAllowNativeInput = true;
            const eventInit = { bubbles: true, cancelable: true, composed: true, view: window, clientX: clickX, clientY: clickY, button: 0, buttons: 1, __sinematicaSynthetic: true };
            target.dispatchEvent(new PointerEvent('pointerdown', eventInit));
            target.dispatchEvent(new MouseEvent('mousedown', eventInit));
            target.dispatchEvent(new PointerEvent('pointerup', { ...eventInit, buttons: 0 }));
            target.dispatchEvent(new MouseEvent('mouseup', { ...eventInit, buttons: 0 }));
            target.dispatchEvent(new MouseEvent('click', { ...eventInit, buttons: 0 }));
            button.click();

            const enterInit = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true, composed: true, view: window, __sinematicaSynthetic: true };
            editor.dispatchEvent(new KeyboardEvent('keydown', enterInit));
            editor.dispatchEvent(new KeyboardEvent('keypress', enterInit));
            editor.dispatchEvent(new KeyboardEvent('keyup', enterInit));
          } catch (_) {}

          notifyProgress('TRIGGERING_START', 'Menekan tombol Start generation di Google Flow...', 50);

          return {
            ready: true,
            clickX,
            clickY,
            beforeSources: Array.from(document.images).map((img) => img.currentSrc || img.src).filter(Boolean),
          };
        },
        args: [prompt, requestBody.requests[0]?.imageAspectRatio, referenceIds, requestId],
      }).catch(() => null);

      const prepData = prepResult?.[0]?.result;
      if (!prepData || !prepData.ready) {
        if (prepData?.error) {
          result = [{ result: { error: prepData.error } }];
        }
        continue;
      }

      // Step 2: Trigger hardware-level trusted click via chrome.debugger
      let clickSucceeded = false;
      if (prepData.clickX && prepData.clickY) {
        const nativeRes = await handleNativeClick(candidateId, prepData.clickX, prepData.clickY);
        if (nativeRes?.ok) clickSucceeded = true;
      }
      if (!clickSucceeded) {
        await chrome.scripting.executeScript({
          target: { tabId: candidateId },
          world: 'MAIN',
          func: () => {
            const editor = document.querySelector('.ProseMirror, [contenteditable="true"]');
            if (editor) editor.focus();
            const btn = document.querySelector('flow-generate-icon-button button, button.generate-icon-button, button[aria-label*="Start" i], button[aria-label*="Mulai" i]');
            if (btn && !btn.disabled) {
              const target = btn.querySelector('mat-icon, .mat-mdc-button-touch-target') || btn;
              const rect = target.getBoundingClientRect();
              const clickX = Math.round(rect.left + rect.width / 2);
              const clickY = Math.round(rect.top + rect.height / 2);
              const eventInit = { bubbles: true, cancelable: true, composed: true, view: window, clientX: clickX, clientY: clickY, button: 0, buttons: 1 };
              target.dispatchEvent(new PointerEvent('pointerdown', eventInit));
              target.dispatchEvent(new MouseEvent('mousedown', eventInit));
              target.dispatchEvent(new PointerEvent('pointerup', { ...eventInit, buttons: 0 }));
              target.dispatchEvent(new MouseEvent('mouseup', { ...eventInit, buttons: 0 }));
              target.dispatchEvent(new MouseEvent('click', { ...eventInit, buttons: 0 }));
              btn.click();
            }
            if (editor) {
              const enterInit = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true, composed: true, view: window };
              editor.dispatchEvent(new KeyboardEvent('keydown', enterInit));
              editor.dispatchEvent(new KeyboardEvent('keypress', enterInit));
              editor.dispatchEvent(new KeyboardEvent('keyup', enterInit));
            }
          }
        }).catch(() => null);
      }

      // Step 3: Monitor generation and poll for output image
      result = await chrome.scripting.executeScript({
        target: { tabId: candidateId },
        world: 'MAIN',
        func: async (beforeSourcesList, reqId) => {
          const before = new Set(beforeSourcesList || []);
          const notifyProgress = (stage, message, percent = undefined) => {
            try {
              if (typeof window !== 'undefined' && window.postMessage) {
                window.postMessage({ type: 'FLOW_TASK_PROGRESS', id: reqId, stage, message, percent, source: 'FLOW_UI' }, '*');
              }
            } catch (_) {}
          };
          let lastPct = null;
          let retryAttempts = 0;
          let lastRetryTime = 0;
          let deadline = Date.now() + 90000;
          let lastHeartbeat = Date.now();
          notifyProgress('WAITING_QUEUE', 'Menunggu proses render gambar dimulai di Google Flow...', 50);

          while (Date.now() < deadline) {
            await new Promise((resolve) => setTimeout(resolve, 1000));

            if (Date.now() - lastHeartbeat > 4000) {
              lastHeartbeat = Date.now();
              const elapsedSec = Math.round((Date.now() - (deadline - 90000)) / 1000);
              notifyProgress('POLLING_HEARTBEAT', `Proses render gambar sedang diproses Google Flow (${elapsedSec}s berjalan)...`, lastPct ? Number(lastPct) : 50);
            }

            // 1. Check window.__sinematicaLastImageReadyEvent from interceptor
            if (typeof window !== 'undefined' && window.__sinematicaLastImageReadyEvent) {
              const lastEvt = window.__sinematicaLastImageReadyEvent;
              const imgUrl = (lastEvt.imageUrls && lastEvt.imageUrls[0]) || (lastEvt.images && lastEvt.images[0] && (lastEvt.images[0].url || lastEvt.images[0].fifeUrl));
              if (imgUrl && imgIsUsable(imgUrl)) {
                notifyProgress('IMAGE_READY', 'Gambar karakter berhasil dibuat!', 100);
                return { image_url: imgUrl };
              }
            }

            // 2. Check newly rendered image tiles on canvas
            const allImgs = Array.from(document.querySelectorAll('img, flow-media-tile img, [data-media-id] img, .gallery-item img'));
            const fresh = allImgs
              .map((img) => img.currentSrc || img.src)
              .filter((url) => url && !before.has(url) && imgIsUsable(url));
            if (fresh.length > 0) {
              notifyProgress('IMAGE_READY', 'Gambar karakter berhasil dibuat!', 100);
              return { image_url: fresh[fresh.length - 1] };
            }

            // 3. Progress percentage tracking
            const tileNodes = Array.from(document.querySelectorAll('flow-media-tile, flow-grid-tile-container, flow-image-tile, button, [role="progressbar"]'));
            for (const node of tileNodes) {
              const txt = (node.innerText || node.textContent || '').trim();
              const pctMatch = txt.match(/\b(\d{1,2})%\b/);
              if (pctMatch && pctMatch[1] && pctMatch[1] !== lastPct) {
                lastPct = pctMatch[1];
                notifyProgress('POLLING_PROGRESS', `Memantau render Google Flow (${lastPct}%)...`, Number(lastPct));
                break;
              }
            }

            // 4. Controlled Auto-Retry on genuine error tiles (up to 2x)
            const isErrorEl = (el) => {
              if (!el) return false;
              const tag = (el.tagName || '').toLowerCase();
              if (tag === 'flow-error-tile' || (el.classList && (el.classList.contains('error-tile') || el.classList.contains('flow-error-tile')))) return true;
              if (el.querySelector && el.querySelector('flow-error-tile, .error-tile, [class*="error-tile"]')) return true;
              const txt = (el.innerText || el.textContent || '').toLowerCase();
              return (
                txt.includes('gagal') ||
                txt.includes('failed') ||
                txt.includes('kebijakan') ||
                txt.includes('policy') ||
                txt.includes('melanggar') ||
                txt.includes('violate') ||
                txt.includes('berbahaya') ||
                txt.includes('harmful') ||
                txt.includes('coba perintah lain') ||
                txt.includes('try another prompt') ||
                txt.includes('tidak perlu menggunakan kredit') ||
                txt.includes('not be charged') ||
                txt.includes('sorry')
              );
            };

            const findRetryBtn = (card) => {
              if (!card) return null;
              return card.querySelector(
                'button[aria-label*="coba lagi" i], button[aria-label*="retry" i], button[aria-label*="try again" i], button[aria-label*="refresh" i], button[aria-label*="ulang" i], button[title*="coba lagi" i], button[title*="retry" i], button[title*="try again" i]'
              ) || Array.from(card.querySelectorAll('button')).find((b) => {
                const label = (b.getAttribute('aria-label') || b.title || b.innerText || '').toLowerCase();
                const icon = (b.querySelector('mat-icon, .mat-icon, i, span')?.innerText || '').toLowerCase();
                return (
                  label.includes('coba lagi') ||
                  label.includes('retry') ||
                  label.includes('try again') ||
                  label.includes('ulang') ||
                  icon.includes('refresh') ||
                  icon.includes('replay') ||
                  icon.includes('retry') ||
                  icon.includes('redo') ||
                  icon.includes('cached') ||
                  icon.includes('autorenew') ||
                  icon.includes('sync') ||
                  icon.includes('restart_alt') ||
                  icon.includes('loop')
                );
              }) || Array.from(card.querySelectorAll('button')).find((b) => {
                const txt = (b.innerText || b.getAttribute('aria-label') || b.title || '').toLowerCase();
                const icon = (b.querySelector('mat-icon, .mat-icon, i, span')?.innerText || '').toLowerCase();
                const isDelete = txt.includes('delete') || txt.includes('hapus') || txt.includes('trash') || icon.includes('delete') || icon.includes('trash');
                const isFeedback = txt.includes('feedback') || txt.includes('masukan') || txt.includes('lapor') || icon.includes('feedback') || icon.includes('chat') || icon.includes('flag') || icon.includes('comment');
                return !isDelete && !isFeedback;
              }) || card.querySelector('button');
            };

            const clickElementWithBypass = (target) => {
              if (!target) return;
              if (typeof window !== 'undefined') {
                window.__sinematicaAllowNativeInput = true;
                window.__sinematicaAllowInput = true;
              }
              if (typeof document !== 'undefined' && document.documentElement) {
                document.documentElement.dataset.sinematicaAllowInput = 'true';
              }
              const blocker = document.getElementById('sinematica-interaction-blocker');
              if (blocker) blocker.style.pointerEvents = 'none';

              try {
                if (typeof target.scrollIntoView === 'function') {
                  target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
              } catch (_) {}

              const rect = target.getBoundingClientRect ? target.getBoundingClientRect() : { left: 0, top: 0, width: 20, height: 20 };
              const clickX = Math.round(rect.left + rect.width / 2);
              const clickY = Math.round(rect.top + rect.height / 2);
              const eventInit = {
                bubbles: true,
                cancelable: true,
                composed: true,
                view: window,
                clientX: clickX,
                clientY: clickY,
                button: 0,
                buttons: 1,
                __sinematicaSynthetic: true,
              };

              const subTarget = target.querySelector('.mat-mdc-button-touch-target, mat-icon, svg') || target;
              [subTarget, target].forEach((t) => {
                if (!t) return;
                try { t.dispatchEvent(new PointerEvent('pointerover', eventInit)); } catch (_) {}
                try { t.dispatchEvent(new PointerEvent('pointerenter', eventInit)); } catch (_) {}
                try { t.dispatchEvent(new PointerEvent('pointerdown', eventInit)); } catch (_) {}
                try { t.dispatchEvent(new MouseEvent('mousedown', eventInit)); } catch (_) {}
                try { t.dispatchEvent(new PointerEvent('pointerup', { ...eventInit, buttons: 0 })); } catch (_) {}
                try { t.dispatchEvent(new MouseEvent('mouseup', { ...eventInit, buttons: 0 })); } catch (_) {}
                try { t.dispatchEvent(new MouseEvent('click', { ...eventInit, buttons: 0 })); } catch (_) {}
              });
              if (typeof target.click === 'function') {
                try { target.click(); } catch (_) {}
              }

              setTimeout(() => {
                if (blocker) blocker.style.pointerEvents = 'auto';
                if (typeof window !== 'undefined') {
                  window.__sinematicaAllowNativeInput = false;
                  window.__sinematicaAllowInput = false;
                }
                if (typeof document !== 'undefined' && document.documentElement) {
                  delete document.documentElement.dataset.sinematicaAllowInput;
                }
              }, 800);
            };

            const allCandidates = Array.from(document.querySelectorAll('flow-error-tile, .error-tile, flow-grid-tile-container, flow-image-tile, [class*="tile"], [data-media-id]'));
            const errorCards = allCandidates.filter((card) => isErrorEl(card));
            if (errorCards.length > 0) {
              const targetCard = errorCards[0];
              const retryBtn = findRetryBtn(targetCard);
              const cardRetries = Number(targetCard.dataset.retriedCount || 0);

              if (cardRetries < 2 && retryAttempts < 2 && Date.now() - lastRetryTime > 6000) {
                if (retryBtn) {
                  targetCard.dataset.retriedCount = String(cardRetries + 1);
                  retryAttempts++;
                  lastRetryTime = Date.now();
                  notifyProgress('AUTO_RETRY', `⚠️ Google Flow menampilkan pesan kendala gambar; mencoba retry otomatis (${retryAttempts}/2)...`, 55);
                  clickElementWithBypass(retryBtn);
                  deadline = Math.max(deadline, Date.now() + 60000);
                  await new Promise((r) => setTimeout(r, 3500));
                  continue;
                }
              } else if (cardRetries >= 2 || retryAttempts >= 2) {
                const errText = (targetCard.innerText || targetCard.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 150);
                notifyProgress('GENERATION_FAILED', `⛔ Generasi gambar ditolak atau gagal di Google Flow setelah 2x retry: ${errText}`, 0);
                return { error: 'FLOW_IMAGE_GENERATION_FAILED_AFTER_RETRIES', details: errText };
              }
            }
          }

          // Fallback: Return the most recent valid generated image on the page
          const availableImgs = Array.from(document.querySelectorAll('img, flow-media-tile img, [data-media-id] img'))
            .map((img) => img.currentSrc || img.src)
            .filter((url) => url && imgIsUsable(url));
          if (availableImgs.length > 0) {
            notifyProgress('IMAGE_READY', 'Mengambil gambar generasi terbaru di halaman Flow...', 100);
            return { image_url: availableImgs[availableImgs.length - 1] };
          }

          return { error: 'FLOW_UI_GENERATION_TIMEOUT' };

          function imgIsUsable(url) {
            try {
              if (!url || typeof url !== 'string') return false;
              if (url.startsWith('blob:') || url.startsWith('data:image/')) return true;
              if (url.includes('avatar') || url.includes('logo') || url.includes('icon') || url.includes('svg') || url.includes('profile_photo') || url.includes('ring') || url.includes('/gb/')) return false;
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
          }
        },
        args: [prepData.beforeSources, requestId],
      }).catch(() => null);

      if (result?.[0]?.result?.image_url) break;
    }
    } finally {
      for (const cid of candidateIds) {
        await chrome.scripting.executeScript({
          target: { tabId: cid },
          world: 'MAIN',
          func: () => {
            if (typeof window !== 'undefined' && typeof window.__sinematicaUnblock === 'function') {
              window.__sinematicaUnblock();
            }
            if (typeof document !== 'undefined') {
              const blocker = document.getElementById('sinematica-interaction-blocker');
              if (blocker) blocker.remove();
              const cursor = document.getElementById('sinematica-fake-cursor');
              if (cursor) cursor.remove();
            }
          }
        }).catch(() => {});
      }
    }

    if (!result) {
      return { status: 500, data: { error: 'FLOW_UI_FALLBACK_FLOW_UI_COMPOSER_UNAVAILABLE' } };
    }
    const value = result?.[0]?.result;
    if (!value?.image_url) {
      return { status: 500, data: { error: `FLOW_UI_FALLBACK_${value?.error || 'NO_IMAGE'}` } };
    }
    const match = value.image_url.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
    const mediaId = match ? match[0] : value.image_url;
    return { status: 200, data: { media: [{ name: mediaId, image: { generatedImage: { fifeUrl: value.image_url } } }] } };
  } catch (error) {
    console.warn('[Sinematica Agent] Flow UI fallback failed:', error);
    return { status: 500, data: { error: `FLOW_UI_FALLBACK_EXCEPTION: ${error?.message || String(error)}` } };
  }
}

async function generateVideoViaAuthenticatedFlowUi(tabId, requestBody, requestId = null) {
  if (!tabId || !requestBody?.requests?.length) {
    return { status: 500, data: { error: 'FLOW_UI_VIDEO_FALLBACK_INVALID_REQUEST' } };
  }
  const prompt = requestBody.requests[0]?.textInput?.structuredPrompt?.parts
    ?.find((part) => typeof part?.text === 'string')?.text;
  const referenceIds = Array.from(new Set(
    (requestBody.requests[0]?.referenceImages || [])
      .map((item) => item?.mediaId || item?.name || item?.media?.mediaId || '')
      .filter(Boolean)
  )).slice(0, 7);
  if (!prompt) {
    return { status: 500, data: { error: 'FLOW_UI_VIDEO_FALLBACK_PROMPT_MISSING' } };
  }

  sendTaskProgress(requestId, 'PREPARE_COMPOSER', 'Menyiapkan sesi Google Flow (Mode Video, Rasio, Model)...', { percent: 10 });

  try {
    let flowTabs = await FlowTab.queryFlowTabs(chrome);
    const isProjectComposer = (tab) => {
      try {
        const parsed = new URL(tab?.url || '');
        if (parsed.hostname !== 'flow.google.com') return false;
        const normalized = parsed.pathname.replace(/^\/u\/\d+/, '').replace(/\/$/, '');
        if (currentProjectId && normalized === `/project/${currentProjectId}`) return true;
        return /^\/project\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(normalized);
      } catch (_) {
        return false;
      }
    };
    let composerTabs = (flowTabs || []).filter(isProjectComposer);
    if (!composerTabs.length) {
      const candidateTab = (tabId ? await chrome.tabs.get(tabId).catch(() => null) : null) || (flowTabs && flowTabs[0]);
      const tabProjId = (candidateTab?.url || '').match(/\/project\/([0-9a-fA-F-]{36})/i)?.[1] || currentProjectId;
      const userPrefix = (candidateTab?.url || '').match(/\/u\/\d+/i)?.[0] || '';
      if (candidateTab && candidateTab.id && tabProjId) {
        const projectUrl = `https://flow.google.com${userPrefix}/project/${encodeURIComponent(tabProjId)}`;
        await chrome.tabs.update(candidateTab.id, { url: projectUrl });
        await new Promise(resolve => setTimeout(resolve, 2000));
        flowTabs = await FlowTab.queryFlowTabs(chrome);
        composerTabs = (flowTabs || []).filter(isProjectComposer);
      }
    }
    if (!composerTabs.length) {
      const targetTab = (flowTabs && flowTabs[0]) || (tabId ? await chrome.tabs.get(tabId).catch(() => null) : null);
      if (targetTab && targetTab.id) {
        const tabProjId = (targetTab.url || '').match(/\/project\/([0-9a-fA-F-]{36})/i)?.[1] || currentProjectId;
        const userPrefix = (targetTab.url || '').match(/\/u\/\d+/i)?.[0] || '';
        if (tabProjId) {
          const projectUrl = `https://flow.google.com${userPrefix}/project/${encodeURIComponent(tabProjId)}`;
          await chrome.tabs.update(targetTab.id, { url: projectUrl });
          await new Promise(resolve => setTimeout(resolve, 2000));
          flowTabs = await FlowTab.queryFlowTabs(chrome);
          composerTabs = (flowTabs || []).filter(isProjectComposer);
        } else {
          try {
            await chrome.tabs.sendMessage(targetTab.id, { action: 'ENSURE_PROJECT_CANVAS', projectId: currentProjectId }).catch(() => null);
          } catch (_) {}
          await chrome.scripting.executeScript({
            target: { tabId: targetTab.id },
            world: 'MAIN',
            func: async (knownProjId) => {
              const userPrefix = window.location.href.match(/\/u\/\d+/i)?.[0] || '';
              if (knownProjId && /^[0-9a-fA-F-]{36}$/.test(knownProjId)) {
                window.location.href = `https://flow.google.com${userPrefix}/project/${knownProjId}`;
                return;
              }
              const btn = document.querySelector('button.new-project-button') ||
                Array.from(document.querySelectorAll('button, a, [role="button"], div')).find(el => {
                  const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().toLowerCase();
                  return (text.includes('new project') || text.includes('project baru') || text.includes('proyek baru')) && !el.closest('flow-prompt-box');
                });
              if (btn) btn.click();
            },
            args: [currentProjectId]
          }).catch(() => null);
          await new Promise(resolve => setTimeout(resolve, 2500));
          flowTabs = await FlowTab.queryFlowTabs(chrome);
          composerTabs = (flowTabs || []).filter(isProjectComposer);
        }
      }
    }
    for (const t of composerTabs) {
      const match = (t.url || '').match(/\/project\/([0-9a-fA-F-]+)/i);
      if (match && match[1]) {
        currentProjectId = match[1];
        chrome.storage.local.set({ currentProjectId });
        break;
      }
    }
    const candidateIds = [...composerTabs.map(tab => tab.id)]
      .filter((id, index, list) => id && list.indexOf(id) === index);
    if (!candidateIds.length) {
      return { status: 503, data: { error: 'FLOW_UI_VIDEO_FALLBACK_COMPOSER_ROOT_UNAVAILABLE' } };
    }
    let result = null;
    try {
    for (const candidateId of candidateIds) {
      // Step 1: Configure video settings, add ingredients, paste prompt into ProseMirror, get button coords
      const prepResult = await chrome.scripting.executeScript({
        target: { tabId: candidateId },
        world: 'MAIN',
        func: async (text, refIds, requestedAspectRatio, requestedVideoModelKey, reqId) => {
          if (typeof window !== 'undefined' && typeof window.__sinematicaBlock === 'function') {
            window.__sinematicaBlock();
          }
          const notifyProgress = (stage, message, percent = undefined) => {
            try {
              if (typeof window !== 'undefined' && window.postMessage) {
                window.postMessage({ type: 'FLOW_TASK_PROGRESS', id: reqId, stage, message, percent, source: 'FLOW_UI' }, '*');
              }
            } catch (_) {}
          };
          const sleep = (ms) => new Promise(r => setTimeout(r, ms));
          const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
            const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
            return (!style || (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'))
                && (!rect || (rect.width > 0 && rect.height > 0));
          };
          const normalize = (value) => (value || '').toLowerCase().trim();
          const controls = () => Array.from(document.querySelectorAll(
            'flow-prompt-box-settings button, flow-prompt-box-settings [role="button"], flow-prompt-box-settings [role="radio"], flow-prompt-box-settings [role="option"], flow-prompt-box-settings mat-button-toggle, flow-prompt-box button, flow-prompt-box [role="button"], flow-add-menu-popover-content button, flow-mobile-add-menu button, button.settings-trigger-button, button.generate-icon-button, button.add-menu-trigger',
          ));
          const allToggles = () => Array.from(document.querySelectorAll(
            'flow-prompt-box-settings mat-button-toggle, flow-prompt-box-settings [role="radio"], flow-prompt-box-settings [role="option"], flow-prompt-box-settings button, flow-prompt-box mat-button-toggle, flow-toggles mat-button-toggle, mat-button-toggle'
          ));
          const findLabelNode = (label) => {
            const needle = normalize(label);
            return allToggles().find(el => {
              if (!visible(el)) return false;
              const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
              const parts = text.split(/[\s\n\r_-]+/);
              return text === needle || parts.includes(needle) || text.endsWith(` ${needle}`) || text.includes(needle);
            });
          };
          const clickExact = (label) => {
            const node = findLabelNode(label);
            const target = node?.closest('button,[role="radio"],[role="option"],mat-button-toggle,label') || node;
            if (!target) return false;
            const clickTarget = target.querySelector('button') || target;
            clickTarget.click();
            return true;
          };
          const clickExactEventually = async (label, timeout = 5000) => {
            const deadline = Date.now() + timeout;
            while (Date.now() < deadline) {
              if (clickExact(label)) return true;
              await sleep(150);
            }
            return false;
          };
          const clickContains = (needle) => {
            const normalized = normalize(needle);
            const target = allToggles().find(el => visible(el) && normalize(el.innerText || el.textContent || el.getAttribute('aria-label')).includes(normalized));
            if (!target) return false;
            (target.closest('button,[role="radio"],[role="option"],mat-button-toggle,label') || target).click();
            return true;
          };
          const selectedExact = (label) => {
            const node = findLabelNode(label);
            const target = node?.closest('button,[role="radio"],[role="option"],mat-button-toggle,label') || node;
            if (!target) return false;
            const parentTog = target.closest('mat-button-toggle') || target;
            const btn = parentTog.querySelector('button') || target;
            return parentTog.classList.contains('mat-button-toggle-checked')
                || parentTog.getAttribute('aria-checked') === 'true'
                || btn.getAttribute('aria-checked') === 'true'
                || node.getAttribute('aria-pressed') === 'true'
                || btn.getAttribute('aria-pressed') === 'true'
                || /(^|\s)(selected|checked|active)(\s|$)/i.test(parentTog.className)
                || /(^|\s)(selected|checked|active)(\s|$)/i.test(btn.className);
          };
          const setInputValue = (input, value) => {
            if (!input) return false;
            input.focus();
            const proto = window.HTMLInputElement ? window.HTMLInputElement.prototype : null;
            const setter = proto ? Object.getOwnPropertyDescriptor(proto, 'value')?.set : null;
            if (setter) setter.call(input, value);
            else input.value = value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
          };
          const findAssetNodes = (refId) => {
            const needle = String(refId).toLowerCase();
            const nodes = Array.from(document.querySelectorAll('*'));
            const direct = nodes.filter(el => {
              if (!visible(el)) return false;
              const attrs = Array.from(el.attributes || [])
                .map(attr => `${attr.name}=${attr.value}`)
                .join(' ')
                .toLowerCase();
              const source = `${attrs} ${el.getAttribute('src') || ''} ${el.getAttribute('href') || ''}`.toLowerCase();
              return source.includes(needle) || source.includes(`media/${needle}`);
            });
            if (direct.length) return direct;
            return nodes.filter(el => {
              if (!visible(el)) return false;
              return String(el.outerHTML || '').slice(0, 4000).toLowerCase().includes(needle);
            });
          };
          const clickAssetNode = (node) => {
            if (!node) return false;
            const target = node.closest(
              '[data-media-id],[data-mediaid],[role="option"],[role="listitem"],button,[tabindex]',
            ) || node.parentElement || node;
            target.click();
            return true;
          };
          const findAddIngredientTrigger = () => {
            const promptBox = document.querySelector('flow-prompt-box, .flow-prompt-box, .prompt-box') || document;
            const direct = promptBox.querySelector('flow-add-menu button.add-menu-trigger, flow-add-menu button, button.add-menu-trigger, button.add-media-button');
            if (direct && visible(direct) && !direct.disabled) return direct;

            const primaryCandidates = Array.from(promptBox.querySelectorAll(
              'button.add-menu-trigger, button.add-media-button, button[aria-label*="Add" i], button[aria-label*="Tambah" i], button[aria-label*="Ingredient" i], button[aria-label*="Reference" i], button[aria-label*="Media" i]'
            ));
            for (const el of primaryCandidates) {
              if (el.closest('flow-ingredient-chip, flow-image-ingredient-chip, .chip-container, flow-ingredient-bar, flow-media-chip, .chip, flow-generate-icon-button, button.generate-icon-button')) {
                continue;
              }
              if (visible(el) && !el.disabled) return el;
            }
            const allBtns = Array.from(promptBox.querySelectorAll('button'));
            for (const btn of allBtns) {
              if (!visible(btn) || btn.disabled) continue;
              if (btn.closest('flow-ingredient-chip, flow-image-ingredient-chip, .chip-container, flow-ingredient-bar, flow-media-chip, .chip, flow-generate-icon-button, button.generate-icon-button')) {
                continue;
              }
              const label = normalize(btn.getAttribute('aria-label') || btn.innerText || btn.textContent || '');
              const icon = btn.querySelector('mat-icon, svg');
              const iconText = normalize(icon?.innerText || icon?.textContent || icon?.getAttribute('data-icon') || '');
              if (label === 'add' || label === 'tambah' || label.startsWith('add ') || label.startsWith('tambah ') || label.includes('ingredient') || iconText === 'add' || iconText === 'add_circle' || iconText === '+') {
                return btn;
              }
            }
            return null;
          };

          const addFlowIngredients = async (ids) => {
            if (!ids.length) return { added: 0, missing: [] };
            notifyProgress('OPENING_ADD_MENU', `Membuka menu bahan untuk melampirkan ${ids.length} referensi storyboard & karakter...`, 15);
            const selected = [];
            const missing = [];

            const extractToken = (val) => {
              if (!val) return '';
              const str = String(val);
              const uuid = str.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
              if (uuid) return uuid[1].toLowerCase();
              const asb = str.match(/AB-n[A-Za-z0-9_-]{12,}/);
              if (asb) return asb[0];
              return str.toLowerCase();
            };

            for (const id of ids) {
              const token = extractToken(id);
              notifyProgress('ATTACHING_INGREDIENT', `Melampirkan bahan referensi (${selected.length + 1}/${ids.length})...`, 18 + (selected.length * 3));
              let popover = document.querySelector('flow-add-menu-popover-content, flow-mobile-add-menu, .mobile-add-menu-container');
              if (!popover) {
                const trigger = findAddIngredientTrigger();
                if (trigger && !trigger.classList.contains('add-menu-trigger-active')) {
                  trigger.click();
                }
              }

              let items = [];
              const deadline = Date.now() + 4000;
              while (Date.now() < deadline) {
                popover = document.querySelector('flow-add-menu-popover-content, flow-mobile-add-menu, .mobile-add-menu-container');
                if (popover) {
                  // Ensure only Image assets (storyboards & character sheets) are targeted
                  const imagesTab = Array.from(popover.querySelectorAll('[role="tab"], button, .mat-mdc-tab')).find(t => normalize(t.innerText || t.textContent).includes('image') || normalize(t.innerText || t.textContent).includes('gambar'));
                  if (imagesTab) {
                    imagesTab.click();
                    await sleep(300);
                  }

                  const rawItems = Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"], flow-add-menu-asset-item'));
                  items = rawItems.filter(el => {
                    const hasImg = !!el.querySelector('img') || !!el.querySelector('video');
                    const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
                    if (!hasImg && (text.includes('create') || text.includes('buat') || text.includes('new') || text.includes('upload') || text.includes('unggah'))) {
                      return false;
                    }
                    if (text.includes('create character') || text.includes('buat karakter') || text.includes('new character') || text.includes('karakter baru')) {
                      return false;
                    }
                    return hasImg || el.classList.contains('asset-item');
                  });
                  if (items.length > 0) break;
                }
                await sleep(200);
              }

              if (!popover) {
                missing.push(id);
                continue;
              }

              // If popover is in detail view from previous item, click back button
              const backBtn = popover.querySelector('button[aria-label*="Back" i], button[aria-label*="Kembali" i], button.back-button');
              if (backBtn && visible(backBtn) && popover.querySelector('button.detail-add-to-prompt-btn')) {
                backBtn.click();
                await sleep(300);
                const recheckedRaw = Array.from(popover.querySelectorAll('button.asset-item, .asset-item, [role="option"], flow-add-menu-asset-item'));
                items = recheckedRaw.filter(el => {
                  const hasImg = !!el.querySelector('img') || !!el.querySelector('video');
                  const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
                  if (!hasImg && (text.includes('create') || text.includes('buat') || text.includes('new') || text.includes('upload') || text.includes('unggah'))) {
                    return false;
                  }
                  if (text.includes('create character') || text.includes('buat karakter') || text.includes('new character') || text.includes('karakter baru')) {
                    return false;
                  }
                  return hasImg || el.classList.contains('asset-item');
                });
              }

              let matchedItem = null;

              if (token) {
                matchedItem = items.find(item => {
                  if (selected.includes(item)) return false;
                  const img = item.querySelector('img');
                  const imgSrc = (img?.src || img?.currentSrc || '').toLowerCase();
                  const text = (item.innerText || item.textContent || '').toLowerCase();
                  const html = (item.outerHTML || '').toLowerCase();
                  return imgSrc.includes(token) || text.includes(token) || html.includes(token);
                });
                if (!matchedItem) {
                  matchedItem = items.find(item => {
                    const img = item.querySelector('img');
                    const imgSrc = (img?.src || img?.currentSrc || '').toLowerCase();
                    const text = (item.innerText || item.textContent || '').toLowerCase();
                    const html = (item.outerHTML || '').toLowerCase();
                    return imgSrc.includes(token) || text.includes(token) || html.includes(token);
                  });
                }
              }

              // Fallback: If not found by exact token, select the first available unselected item
              if (!matchedItem && items.length > 0) {
                const unusedItems = items.filter(item => !selected.includes(item));
                if (unusedItems.length > 0) {
                  matchedItem = unusedItems[0];
                }
              }

              if (matchedItem) {
                (matchedItem.closest('button.asset-item') || matchedItem).click();
                await sleep(400);

                let addBtn = null;
                const addDeadline = Date.now() + 2500;
                while (Date.now() < addDeadline) {
                  addBtn = popover.querySelector('button.detail-add-to-prompt-btn') ||
                    controls().find(el => visible(el) && !el.disabled && normalize(el.innerText || el.textContent).includes('add to prompt'));
                  if (addBtn && !addBtn.disabled) break;
                  await sleep(150);
                }

                if (addBtn) {
                  addBtn.click();
                  selected.push(matchedItem);
                  await sleep(600);
                } else {
                  // In mobile/direct overlay, clicking the item immediately adds it
                  selected.push(matchedItem);
                  await sleep(400);
                }
              } else {
                missing.push(id);
              }
            }

            // Close popover if still open
            const openPopover = document.querySelector('flow-add-menu-popover-content, flow-mobile-add-menu');
            if (openPopover) {
              document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
              await sleep(250);
            }

            return { added: selected.length, missing };
          };

          // Close any stray top-bar or context menus before opening prompt settings
          const strayMenu = document.querySelector('.cdk-overlay-pane:not(:has(flow-toggles)):not(:has(flow-add-menu-popover-content))');
          if (strayMenu) {
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
            await sleep(250);
          }

          const findSettingsTrigger = () => {
            const promptBox = document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') || document;
            const direct = promptBox.querySelector('.settings-trigger-button, button.settings-trigger-button, button[aria-label*="Settings trigger" i], button[aria-label*="Pemicu setelan" i], [data-test-id*="settings-trigger"]');
            if (direct && visible(direct)) return direct;

            const promptButtons = Array.from(promptBox.querySelectorAll('button, [role="button"], div[role="button"]')).filter(visible);
            
            const pill = promptButtons.find(btn => {
              const text = (btn.innerText || btn.textContent || '').trim();
              const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
              if (btn.closest('flow-generate-icon-button') || btn.querySelector('mat-icon.arrow_forward') || aria.includes('start') || aria.includes('mulai') || aria.includes('generate')) {
                return false;
              }
              return text.includes('•') || text.includes('·') || /720p|1080p|9:16|16:9|3:4|4:3|1:1|x1|x2|x4|banana|veo|video|image|gambar/i.test(text) ||
                     aria.includes('settings trigger') || aria.includes('pemicu setelan') || aria.includes('settings') || aria.includes('tune');
            });
            if (pill) return pill;

            if (promptButtons.length >= 2) {
              return promptButtons[promptButtons.length - 2];
            }
            return null;
          };

          const isSettingsPopoverOpen = () => !!document.querySelector('flow-prompt-box-settings, .cdk-overlay-pane:has(flow-toggles), .settings-content-overlay');
          if (!isSettingsPopoverOpen()) {
            const settingsTrigger = findSettingsTrigger();
            if (settingsTrigger) {
              settingsTrigger.click();
              await sleep(400);
            }
          }
          const selectFlowOption = async (type, targetValue) => {
            const normTarget = normalize(targetValue);
            const getToggles = () => Array.from(document.querySelectorAll('mat-button-toggle-group mat-button-toggle, flow-prompt-box-settings mat-button-toggle, flow-toggles mat-button-toggle, .cdk-overlay-pane mat-button-toggle, mat-button-toggle'));
            
            for (let attempt = 0; attempt < 10; attempt++) {
              const toggles = getToggles();
              let matched = null;

              if (type === 'duration') {
                const durNum = (normTarget.match(/\d+/) || ['8'])[0];
                matched = toggles.find(t => {
                  const txt = normalize(t.innerText || t.textContent);
                  const parts = txt.split(/[\s_-]+/);
                  return parts.includes(durNum) || txt.includes(`${durNum}s`) || txt.includes(`${durNum} dtk`) || txt.includes(`${durNum} detik`) || txt.includes(`${durNum} sec`);
                });
              } else if (type === 'ratio') {
                const is16_9 = normTarget.includes('16:9') || normTarget.includes('landscape') || normTarget.includes('lanskap');
                const is9_16 = normTarget.includes('9:16') || normTarget.includes('portrait') || normTarget.includes('potret');
                const key = is16_9 ? '16:9' : (is9_16 ? '9:16' : normTarget);
                matched = toggles.find(t => {
                  const txt = normalize(t.innerText || t.textContent);
                  return txt.includes(key) || (is16_9 && (txt.includes('16_9') || txt.includes('landscape') || txt.includes('lanskap'))) || (is9_16 && (txt.includes('9_16') || txt.includes('portrait') || txt.includes('potret')));
                });
              } else if (type === 'count') {
                const countNum = (normTarget.match(/\d+/) || ['1'])[0];
                matched = toggles.find(t => {
                  const txt = normalize(t.innerText || t.textContent);
                  return txt === `x${countNum}` || txt === countNum || txt.includes(`x${countNum}`);
                });
              } else {
                matched = toggles.find(t => {
                  const txt = normalize(t.innerText || t.textContent);
                  if (normTarget === 'video') return txt.includes('video');
                  if (normTarget === 'image' || normTarget === 'gambar') return txt.includes('image') || txt.includes('gambar');
                  if (normTarget === 'ingredients' || normTarget === 'bahan') return txt.includes('ingredient') || txt.includes('bahan');
                  if (normTarget === 'frames' || normTarget === 'frame') return txt.includes('frame');
                  return txt.includes(normTarget);
                });
              }

              if (matched) {
                const btn = matched.querySelector('button') || matched;
                btn.click();
                await sleep(200);
                return true;
              }
              await sleep(150);
            }
            return false;
          };

          await selectFlowOption('mode', 'video');
          await sleep(200);

          if (refIds.length) {
            await selectFlowOption('submode', 'bahan');
          } else {
            await selectFlowOption('submode', 'frames');
          }
          await sleep(200);

          const videoRatioLabel = (requestedAspectRatio === 'VIDEO_ASPECT_RATIO_PORTRAIT' || requestedAspectRatio === '9:16' || requestedAspectRatio === 'portrait')
            ? '9:16' : (requestedAspectRatio === 'VIDEO_ASPECT_RATIO_LANDSCAPE' || requestedAspectRatio === '16:9' || requestedAspectRatio === 'landscape')
              ? '16:9' : (requestedAspectRatio || '16:9');
          const durationMatch = String(requestedVideoModelKey || '').match(/_(\d+)s$/i);
          const videoDurationLabel = durationMatch ? `${durationMatch[1]}s` : '10s';

          if (videoRatioLabel) await selectFlowOption('ratio', videoRatioLabel);
          if (videoDurationLabel) await selectFlowOption('duration', videoDurationLabel);
          await selectFlowOption('count', '1');
          await sleep(250);

          const backdrop = document.querySelector('.cdk-overlay-backdrop');
          if (backdrop) backdrop.click();
          else document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          await sleep(300);

          const editor = document.querySelector('[contenteditable="true"], .ProseMirror, textarea');
          if (!editor) return { error: 'FLOW_UI_VIDEO_COMPOSER_UNAVAILABLE' };

          // Step 1: Type prompt text FIRST so subsequent ingredient attachments are never erased
          notifyProgress('TYPING_PROMPT', `Mengisi prompt video: "${text.slice(0, 60)}..."`, 35);
          editor.focus();

          try {
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            if ((editor.innerText || editor.textContent || '').trim().length > 0) {
              editor.innerHTML = '<p><br></p>';
            }
          } catch (_) {}

          try {
            document.execCommand('insertText', false, text);
          } catch (_) {}

          try {
            if (typeof InputEvent !== 'undefined') {
              editor.dispatchEvent(new InputEvent('beforeinput', {
                bubbles: true, cancelable: true, inputType: 'insertText', data: text, composed: true,
              }));
              editor.dispatchEvent(new InputEvent('input', {
                bubbles: true, cancelable: true, inputType: 'insertText', data: text, composed: true,
              }));
            }
            if (typeof Event !== 'undefined') {
              editor.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
              editor.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            }
          } catch (_) {}
          await sleep(300);

          // Step 2: Attach reference images (storyboard & character sheets) AFTER prompt text is populated
          let ingredientResult = { added: 0, missing: [] };
          if (refIds && refIds.length) {
            notifyProgress('ATTACHING_INGREDIENTS', `Memasang ${refIds.length} referensi storyboard & karakter ke prompt box...`, 40);
            ingredientResult = await addFlowIngredients(refIds);
            if (ingredientResult.added === 0) {
              notifyProgress('INGREDIENT_WARNING', 'Ingredient tidak ditemukan di popover; melanjutkan render video dengan prompt...', 45);
            } else {
              notifyProgress('INGREDIENT_ATTACHED', `Berhasil memasang ${ingredientResult.added} referensi storyboard & karakter ke prompt box!`, 45);
            }
          }
          await sleep(300);

          // Verify prompt text still exists; if missing, inject text safely without wiping chips
          const promptContent = (editor.innerText || editor.textContent || '').trim();
          if (!promptContent) {
            try {
              editor.focus();
              document.execCommand('insertText', false, text);
            } catch (_) {}
          }

          const isButtonDisabled = (btn) => {
            if (!btn) return true;
            return btn.disabled ||
              (typeof btn.hasAttribute === 'function' && btn.hasAttribute('disabled')) ||
              (typeof btn.getAttribute === 'function' && btn.getAttribute('aria-disabled') === 'true') ||
              (btn.classList && typeof btn.classList.contains === 'function' && btn.classList.contains('mat-mdc-button-disabled'));
          };

          const findStartButton = () => {
            const direct = document.querySelector(
              'flow-generate-icon-button button, button.generate-icon-button, button[aria-label*="Start generation" i], button[aria-label*="Mulai pembuatan" i], button[aria-label*="Start" i], button[aria-label*="Generate" i], button[aria-label*="Submit" i], button[aria-label*="Send" i], button[aria-label*="Mulai" i], button[aria-label*="Buat" i], button[aria-label*="Hasilkan" i]'
            );
            if (direct && !isButtonDisabled(direct)) return direct;
            const promptBox = document.querySelector('flow-prompt-box, .flow-prompt-box, [class*="prompt-box"]') || document;
            const queryAll = Array.from(promptBox.querySelectorAll(
              'flow-generate-icon-button button, button[type="submit"], [data-test-id*="generate"], button[aria-label*="generate" i], button[aria-label*="start" i], button[aria-label*="buat" i], button[aria-label*="mulai" i], button[aria-label*="hasilkan" i], button[aria-label*="submit" i], button[aria-label*="send" i], button',
            ));
            const matched = queryAll.find((el) => {
              if (isButtonDisabled(el)) return false;
              const label = [
                el.getAttribute('aria-label') || '',
                el.getAttribute('title') || '',
                el.innerText || '',
                el.textContent || '',
              ].join(' ').toLowerCase();
              if (label.includes('character') || label.includes('karakter') || label.includes('actor') || label.includes('upload') || label.includes('unggah') || label.includes('sidebar') || label.includes('settings') || label.includes('pemicu setelan')) {
                return false;
              }
              const inComposer = !!el.closest('flow-prompt-box') || !!el.closest('flow-generate-icon-button');
              const isGenerateText = /arrow|start|generate|submit|send|buat|mulai|hasilkan/i.test(label) || !!el.querySelector('mat-icon, svg');
              return inComposer && isGenerateText;
            });
            if (matched) return matched;

            const promptButtons = Array.from(promptBox.querySelectorAll('button')).filter((b) => {
              if (!b || isButtonDisabled(b)) return false;
              const txt = [b.getAttribute('aria-label') || '', b.innerText || '', b.textContent || ''].join(' ').toLowerCase();
              return !txt.includes('character') && !txt.includes('karakter') && !txt.includes('upload') && !txt.includes('unggah') && !txt.includes('sidebar') && !txt.includes('settings') && !txt.includes('pemicu setelan');
            });
            if (promptButtons.length > 0) {
              return promptButtons[promptButtons.length - 1];
            }
            return null;
          };

          let start = null;
          const deadline = Date.now() + 10000;
          while (Date.now() < deadline) {
            start = findStartButton()
              || document.querySelector('flow-generate-icon-button button')
              || document.querySelector('button[aria-label*="Start" i], button[aria-label*="Mulai" i]');
            const isReady = start && !isButtonDisabled(start) && (editor.innerText || editor.textContent || '').trim().length > 0;
            if (isReady) break;

            try {
              editor.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: ' ', composed: true }));
              editor.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', code: 'KeyA', bubbles: true, composed: true }));
              editor.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
              editor.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            } catch (_) {}

            await sleep(250);
          }

          if (!start) {
            start = findStartButton()
              || document.querySelector('flow-generate-icon-button button')
              || document.querySelector('button[aria-label*="Start" i], button[aria-label*="Mulai" i]');
          }

          if (!start) return { error: 'FLOW_UI_START_BUTTON_NOT_FOUND' };

          start.scrollIntoView({ block: 'center', inline: 'center' });
          await sleep(150);
          editor.focus();

          const target = start.querySelector('mat-icon, .mat-mdc-button-touch-target') || start;
          const rect = target.getBoundingClientRect();
          const clickX = Math.round(rect.left + rect.width / 2);
          const clickY = Math.round(rect.top + rect.height / 2);

          try {
            if (typeof window !== 'undefined') window.__sinematicaAllowNativeInput = true;
            const eventInit = { bubbles: true, cancelable: true, composed: true, view: window, clientX: clickX, clientY: clickY, button: 0, buttons: 1, __sinematicaSynthetic: true };
            target.dispatchEvent(new PointerEvent('pointerdown', eventInit));
            target.dispatchEvent(new MouseEvent('mousedown', eventInit));
            target.dispatchEvent(new PointerEvent('pointerup', { ...eventInit, buttons: 0 }));
            target.dispatchEvent(new MouseEvent('mouseup', { ...eventInit, buttons: 0 }));
            target.dispatchEvent(new MouseEvent('click', { ...eventInit, buttons: 0 }));
            start.click();

            const enterInit = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true, composed: true, view: window, __sinematicaSynthetic: true };
            editor.dispatchEvent(new KeyboardEvent('keydown', enterInit));
            editor.dispatchEvent(new KeyboardEvent('keypress', enterInit));
            editor.dispatchEvent(new KeyboardEvent('keyup', enterInit));
          } catch (_) {}

          notifyProgress('TRIGGERING_START', 'Menekan tombol Start video generation...', 50);

          const assetSources = () => Array.from(document.querySelectorAll('video, flow-media-tile video, [data-media-id] video, source'))
            .map(el => el.currentSrc || el.src || el.getAttribute('src') || '')
            .filter(Boolean);

          const imageSources = () => Array.from(document.querySelectorAll('img, flow-media-tile img, [data-media-id] img, .gallery-item img'))
            .map(el => el.currentSrc || el.src || el.getAttribute('src') || '')
            .filter(Boolean);

          const mediaIdsList = () => Array.from(document.querySelectorAll('[data-media-id]'))
            .map(el => el.getAttribute('data-media-id'))
            .filter(Boolean);

          const existingTileIds = () => Array.from(document.querySelectorAll('flow-media-tile, flow-grid-tile-container, flow-video-tile, [data-media-id]'))
            .map(el => el.getAttribute('data-media-id') || el.getAttribute('id') || (el.querySelector('img')?.src) || '')
            .filter(Boolean);

          const isPrepErrorEl = (el) => {
            if (!el) return false;
            const tag = (el.tagName || '').toLowerCase();
            if (tag === 'flow-error-tile' || (el.classList && (el.classList.contains('error-tile') || el.classList.contains('flow-error-tile')))) return true;
            if (el.querySelector && el.querySelector('flow-error-tile, .error-tile, [class*="error-tile"]')) return true;
            const txt = (el.innerText || el.textContent || '').toLowerCase();
            return (
              txt.includes('gagal') ||
              txt.includes('gagal dibuat') ||
              txt.includes('maaf, video ini gagal') ||
              txt.includes('maaf, gambar ini gagal') ||
              txt.includes('tidak perlu menggunakan kredit') ||
              txt.includes('kebijakan') ||
              txt.includes('policy') ||
              txt.includes('melanggar') ||
              txt.includes('violate') ||
              txt.includes('berbahaya') ||
              txt.includes('harmful') ||
              txt.includes('coba perintah lain') ||
              txt.includes('try another prompt') ||
              txt.includes('tokoh berpengaruh') ||
              txt.includes('public figure') ||
              txt.includes('kesalahan pembuatan') ||
              txt.includes('failed to generate') ||
              txt.includes('generation failed') ||
              txt.includes('video failed') ||
              txt.includes('image failed') ||
              txt.includes('sorry, this video failed') ||
              txt.includes('sorry, this image failed') ||
              txt.includes('will not be charged') ||
              txt.includes('were not charged') ||
              txt.includes('not need to use credits') ||
              txt.includes('could not generate')
            );
          };

          const errorTileIds = () => Array.from(document.querySelectorAll('flow-error-tile, .error-tile, flow-grid-tile-container, flow-video-tile, [class*="tile"], [data-media-id]'))
            .filter(isPrepErrorEl)
            .map(el => el.getAttribute('data-media-id') || el.getAttribute('id') || (el.querySelector('img')?.src) || (el.innerText || '').slice(0, 50))
            .filter(Boolean);

          return {
            ready: true,
            clickX,
            clickY,
            beforeSources: assetSources(),
            beforeImages: imageSources(),
            beforeMediaIds: mediaIdsList(),
            beforeTileIds: existingTileIds(),
            beforeErrorTileIds: errorTileIds(),
            startTime: Date.now(),
            references_added: ingredientResult.added,
          };
        },
        args: [prompt, referenceIds, requestBody.requests[0]?.aspectRatio, requestBody.requests[0]?.videoModelKey, requestId],
      }).catch(() => null);

      const prepData = prepResult?.[0]?.result;
      if (!prepData || !prepData.ready) {
        if (prepData?.error) {
          result = [{ result: { error: prepData.error } }];
        }
        continue;
      }

      // Step 2: Trigger hardware-level trusted click via chrome.debugger
      let clickSucceeded = false;
      if (prepData.clickX && prepData.clickY) {
        const nativeRes = await handleNativeClick(candidateId, prepData.clickX, prepData.clickY);
        if (nativeRes?.ok) clickSucceeded = true;
      }
      if (!clickSucceeded) {
        await chrome.scripting.executeScript({
          target: { tabId: candidateId },
          world: 'MAIN',
          func: () => {
            const editor = document.querySelector('.ProseMirror, [contenteditable="true"]');
            if (editor) editor.focus();
            const btn = document.querySelector('flow-generate-icon-button button, button.generate-icon-button, button[aria-label*="Start" i], button[aria-label*="Mulai" i]');
            if (btn && !btn.disabled) {
              const target = btn.querySelector('mat-icon, .mat-mdc-button-touch-target') || btn;
              const rect = target.getBoundingClientRect();
              const clickX = Math.round(rect.left + rect.width / 2);
              const clickY = Math.round(rect.top + rect.height / 2);
              const eventInit = { bubbles: true, cancelable: true, composed: true, view: window, clientX: clickX, clientY: clickY, button: 0, buttons: 1 };
              target.dispatchEvent(new PointerEvent('pointerdown', eventInit));
              target.dispatchEvent(new MouseEvent('mousedown', eventInit));
              target.dispatchEvent(new PointerEvent('pointerup', { ...eventInit, buttons: 0 }));
              target.dispatchEvent(new MouseEvent('mouseup', { ...eventInit, buttons: 0 }));
              target.dispatchEvent(new MouseEvent('click', { ...eventInit, buttons: 0 }));
              btn.click();
            }
            if (editor) {
              const enterInit = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true, composed: true, view: window };
              editor.dispatchEvent(new KeyboardEvent('keydown', enterInit));
              editor.dispatchEvent(new KeyboardEvent('keypress', enterInit));
              editor.dispatchEvent(new KeyboardEvent('keyup', enterInit));
            }
          }
        }).catch(() => null);
      }

      // Step 3: Monitor generation and poll for output video
      result = await chrome.scripting.executeScript({
        target: { tabId: candidateId },
        world: 'MAIN',
        func: async (prepPayload, reqId) => {
          const before = new Set(prepPayload?.beforeSources || []);
          const beforeImages = new Set(prepPayload?.beforeImages || []);
          const beforeMediaIds = new Set(prepPayload?.beforeMediaIds || []);
          const beforeTileIds = new Set(prepPayload?.beforeTileIds || []);
          const beforeErrorTileIds = new Set(prepPayload?.beforeErrorTileIds || []);
          const startTime = prepPayload?.startTime || Date.now();
          const referencesAdded = prepPayload?.references_added || 0;

          const notifyProgress = (stage, message, percent = undefined) => {
            try {
              if (typeof window !== 'undefined' && window.postMessage) {
                window.postMessage({ type: 'FLOW_TASK_PROGRESS', id: reqId, stage, message, percent, source: 'FLOW_UI' }, '*');
              }
            } catch (_) {}
          };
          const sleep = (ms) => new Promise(r => setTimeout(r, ms));
          const assetSources = () => Array.from(document.querySelectorAll('video, flow-media-tile video, [data-media-id] video, source'))
            .map(el => el.currentSrc || el.src || el.getAttribute('src') || '')
            .filter(Boolean);
          const isUsableVideoUrl = (url) => {
            if (!url || typeof url !== 'string') return false;
            if (url.startsWith('blob:') || url.startsWith('data:video/')) return true;
            try {
              const parsed = new URL(url);
              return parsed.hostname === 'flow-content.google'
                || parsed.hostname === 'flow.google.com'
                || parsed.hostname.endsWith('.googleusercontent.com')
                || parsed.hostname === 'storage.googleapis.com'
                || parsed.hostname.endsWith('.gstatic.com');
            } catch (_) {
              return false;
            }
          };
          const extractFreshVideoUrl = (prior) => {
            const current = assetSources().filter(isUsableVideoUrl);
            const fresh = current.filter(src => !prior.has(src));
            return fresh.length ? fresh[fresh.length - 1] : null;
          };

          const isErrorEl = (el) => {
            if (!el) return false;
            const tag = (el.tagName || '').toLowerCase();
            if (tag === 'flow-error-tile' || (el.classList && (el.classList.contains('error-tile') || el.classList.contains('flow-error-tile')))) return true;
            if (el.querySelector && el.querySelector('flow-error-tile, .error-tile, [class*="error-tile"]')) return true;
            const txt = (el.innerText || el.textContent || '').toLowerCase();
            return (
              txt.includes('gagal') ||
              txt.includes('gagal dibuat') ||
              txt.includes('maaf, video ini gagal') ||
              txt.includes('maaf, gambar ini gagal') ||
              txt.includes('tidak perlu menggunakan kredit') ||
              txt.includes('kebijakan') ||
              txt.includes('policy') ||
              txt.includes('melanggar') ||
              txt.includes('violate') ||
              txt.includes('berbahaya') ||
              txt.includes('harmful') ||
              txt.includes('coba perintah lain') ||
              txt.includes('try another prompt') ||
              txt.includes('tokoh berpengaruh') ||
              txt.includes('public figure') ||
              txt.includes('kesalahan pembuatan') ||
              txt.includes('failed to generate') ||
              txt.includes('generation failed') ||
              txt.includes('video failed') ||
              txt.includes('image failed') ||
              txt.includes('sorry, this video failed') ||
              txt.includes('sorry, this image failed') ||
              txt.includes('will not be charged') ||
              txt.includes('were not charged') ||
              txt.includes('not need to use credits') ||
              txt.includes('could not generate')
            );
          };

          const findRetryBtn = (card) => {
            if (!card) return null;
            return card.querySelector(
              'button[aria-label*="coba lagi" i], button[aria-label*="retry" i], button[aria-label*="try again" i], button[aria-label*="refresh" i], button[aria-label*="ulang" i], button[title*="coba lagi" i], button[title*="retry" i], button[title*="try again" i]'
            ) || Array.from(card.querySelectorAll('button')).find((b) => {
              const label = (b.getAttribute('aria-label') || b.title || b.innerText || '').toLowerCase();
              const icon = (b.querySelector('mat-icon, .mat-icon, i, span')?.innerText || '').toLowerCase();
              return (
                label.includes('coba lagi') ||
                label.includes('retry') ||
                label.includes('try again') ||
                label.includes('ulang') ||
                icon.includes('refresh') ||
                icon.includes('replay') ||
                icon.includes('retry') ||
                icon.includes('redo') ||
                icon.includes('cached') ||
                icon.includes('autorenew') ||
                icon.includes('sync') ||
                icon.includes('restart_alt') ||
                icon.includes('loop')
              );
            }) || Array.from(card.querySelectorAll('button')).find((b) => {
              const txt = (b.innerText || b.getAttribute('aria-label') || b.title || '').toLowerCase();
              const icon = (b.querySelector('mat-icon, .mat-icon, i, span')?.innerText || '').toLowerCase();
              const isDelete = txt.includes('delete') || txt.includes('hapus') || txt.includes('trash') || icon.includes('delete') || icon.includes('trash');
              const isFeedback = txt.includes('feedback') || txt.includes('masukan') || txt.includes('lapor') || icon.includes('feedback') || icon.includes('chat') || icon.includes('flag') || icon.includes('comment');
              return !isDelete && !isFeedback;
            }) || card.querySelector('button');
          };

          const clickElementWithBypass = (target) => {
            if (!target) return;
            if (typeof window !== 'undefined') {
              window.__sinematicaAllowNativeInput = true;
              window.__sinematicaAllowInput = true;
            }
            if (typeof document !== 'undefined' && document.documentElement) {
              document.documentElement.dataset.sinematicaAllowInput = 'true';
            }
            const blocker = document.getElementById('sinematica-interaction-blocker');
            if (blocker) blocker.style.pointerEvents = 'none';

            try {
              if (typeof target.scrollIntoView === 'function') {
                target.scrollIntoView({ behavior: 'smooth', block: 'center' });
              }
            } catch (_) {}

            const rect = target.getBoundingClientRect ? target.getBoundingClientRect() : { left: 0, top: 0, width: 20, height: 20 };
            const clickX = Math.round(rect.left + rect.width / 2);
            const clickY = Math.round(rect.top + rect.height / 2);
            const eventInit = {
              bubbles: true,
              cancelable: true,
              composed: true,
              view: window,
              clientX: clickX,
              clientY: clickY,
              button: 0,
              buttons: 1,
              __sinematicaSynthetic: true,
            };

            const subTarget = target.querySelector('.mat-mdc-button-touch-target, mat-icon, svg') || target;
            [subTarget, target].forEach((t) => {
              if (!t) return;
              try { t.dispatchEvent(new PointerEvent('pointerover', eventInit)); } catch (_) {}
              try { t.dispatchEvent(new PointerEvent('pointerenter', eventInit)); } catch (_) {}
              try { t.dispatchEvent(new PointerEvent('pointerdown', eventInit)); } catch (_) {}
              try { t.dispatchEvent(new MouseEvent('mousedown', eventInit)); } catch (_) {}
              try { t.dispatchEvent(new PointerEvent('pointerup', { ...eventInit, buttons: 0 })); } catch (_) {}
              try { t.dispatchEvent(new MouseEvent('mouseup', { ...eventInit, buttons: 0 })); } catch (_) {}
              try { t.dispatchEvent(new MouseEvent('click', { ...eventInit, buttons: 0 })); } catch (_) {}
            });
            if (typeof target.click === 'function') {
              try { target.click(); } catch (_) {}
            }

            setTimeout(() => {
              if (blocker) blocker.style.pointerEvents = 'auto';
              if (typeof window !== 'undefined') {
                window.__sinematicaAllowNativeInput = false;
                window.__sinematicaAllowInput = false;
              }
              if (typeof document !== 'undefined' && document.documentElement) {
                delete document.documentElement.dataset.sinematicaAllowInput;
              }
            }, 800);
          };

          const resolveTileVideo = async (tile) => {
            if (!tile) return null;
            const directVid = tile.querySelector('video');
            const directSrc = directVid?.currentSrc || directVid?.src;
            if (directSrc && isUsableVideoUrl(directSrc) && !before.has(directSrc)) {
              return directSrc;
            }

            const clickTarget = tile.querySelector('.mobile-play-badge') ||
              tile.querySelector('.thumbnail') ||
              tile.querySelector('img') ||
              tile;

            if (clickTarget) {
              clickElementWithBypass(clickTarget);
              let foundSrc = null;
              for (let att = 0; att < 25; att++) {
                await sleep(200);
                const mountedVid = document.querySelector('video');
                const mSrc = mountedVid?.currentSrc || mountedVid?.src;
                if (mSrc && isUsableVideoUrl(mSrc) && !before.has(mSrc) && (mSrc.includes('flow-content') || mSrc.endsWith('.mp4') || mSrc.startsWith('blob:'))) {
                  foundSrc = mSrc;
                  break;
                }
              }

              const backBtn = Array.from(document.querySelectorAll('button')).find((b) =>
                (b.innerText && b.innerText.includes('arrow_back')) ||
                (b.getAttribute('aria-label') && b.getAttribute('aria-label').toLowerCase().includes('back'))
              );
              if (backBtn) {
                clickElementWithBypass(backBtn);
                await sleep(350);
              }

              return foundSrc;
            }
            return null;
          };

          let lastPct = null;
          let videoRetryAttempts = 0;
          let lastVideoRetryTime = 0;
          let renderDeadline = Date.now() + 180000;
          let lastHeartbeat = Date.now();
          notifyProgress('WAITING_QUEUE', 'Menunggu proses render video dimulai di antrean Google Flow...', 50);

          while (Date.now() < renderDeadline) {
            await sleep(1500);

            if (Date.now() - lastHeartbeat > 4500) {
              lastHeartbeat = Date.now();
              const elapsedSec = Math.round((Date.now() - startTime) / 1000);
              notifyProgress('POLLING_HEARTBEAT', `Render video sedang diproses di Google Flow (${elapsedSec}s berjalan)...`, lastPct ? Number(lastPct) : 50);
            }

            // 1. Detect all canvas tiles and check if ANY tile is actively rendering
            const allCanvasTiles = Array.from(document.querySelectorAll('flow-media-tile, flow-grid-tile-container, flow-video-tile, flow-error-tile, .error-tile, [class*="tile"], [data-media-id]'));
            const activeRenderingTiles = allCanvasTiles.filter((t) => {
              if (isErrorEl(t)) return false;
              const text = (t.innerText || t.textContent || '').toLowerCase();
              const isProgress = /\b\d{1,2}%\b|generating|queued|rendering|sedang|memproses|menyiapkan/i.test(text);
              const hasSpinner = !!t.querySelector('mat-spinner, .spinner, [role="progressbar"], svg.circular-loader, [aria-label*="loading" i], [aria-label*="generating" i]');
              const hasProgressBar = !!t.querySelector('[role="progressbar"], .mat-mdc-progress-bar');
              return isProgress || hasSpinner || hasProgressBar;
            });
            const isAnyTileRendering = activeRenderingTiles.length > 0;

            // 2. Progress percentage tracking from active tiles or canvas
            for (const node of activeRenderingTiles.concat(allCanvasTiles)) {
              const txt = (node.innerText || node.textContent || '').trim();
              const pctMatch = txt.match(/\b(\d{1,2})%\b/);
              if (pctMatch && pctMatch[1] && pctMatch[1] !== lastPct) {
                lastPct = pctMatch[1];
                notifyProgress('POLLING_PROGRESS', `Memantau render video Google Flow (${lastPct}%)...`, Number(lastPct));
                break;
              }
            }

            // 3. Check window.__sinematicaLastVideoReadyEvent from interceptor
            if (typeof window !== 'undefined' && window.__sinematicaLastVideoReadyEvent) {
              const lastEvt = window.__sinematicaLastVideoReadyEvent;
              if (lastEvt.time >= startTime) {
                const vidUrl = (lastEvt.videoUrls && lastEvt.videoUrls[0]) || (lastEvt.videos && lastEvt.videos[0] && (lastEvt.videos[0].url || lastEvt.videos[0].downloadUrl));
                if (vidUrl && isUsableVideoUrl(vidUrl) && !before.has(vidUrl)) {
                  notifyProgress('VIDEO_READY', 'Video berhasil dirender di Google Flow!', 100);
                  return { video_url: vidUrl, references_added: referencesAdded };
                }
              }
            }

            // 4. Direct video tag source check
            const freshUrl = extractFreshVideoUrl(before);
            if (freshUrl && !before.has(freshUrl)) {
              notifyProgress('VIDEO_READY', 'Video berhasil dirender di Google Flow!', 100);
              return { video_url: freshUrl, references_added: referencesAdded };
            }

            // 5. Scan for NEW completed video tiles on canvas (Strictly excluding prior baseline)
            const completedVideoTiles = allCanvasTiles.filter((t) => {
              if (isErrorEl(t)) return false;
              const text = (t.innerText || t.textContent || '').toLowerCase();
              const isProgress = /\b\d{1,2}%\b|generating|queued|rendering/i.test(text);
              if (isProgress) return false;

              const mId = t.getAttribute('data-media-id') || t.getAttribute('id');
              const tileImgSrc = t.querySelector('img')?.src || t.querySelector('img')?.currentSrc || '';
              const tileVidSrc = t.querySelector('video')?.src || t.querySelector('video')?.currentSrc || '';

              // Strictly reject pre-existing tiles from Scene 1
              if (mId && beforeMediaIds.has(mId)) return false;
              if (tileVidSrc && before.has(tileVidSrc)) return false;
              if (tileImgSrc && beforeImages.has(tileImgSrc) && !t.querySelector('video')) return false;

              const hasPlay = !!t.querySelector('mat-icon, button[aria-label*="Play" i], .play-icon, .mobile-play-badge') &&
                /play|videocam|play_arrow/i.test(t.querySelector('mat-icon')?.innerText || t.querySelector('button')?.getAttribute('aria-label') || '');
              const isVideoEl = !!t.querySelector('video') || t.tagName?.toLowerCase() === 'flow-video-tile';
              return (hasPlay || isVideoEl);
            });

            if (completedVideoTiles.length > 0) {
              for (const candidateTile of completedVideoTiles) {
                const resolvedUrl = await resolveTileVideo(candidateTile);
                if (resolvedUrl && isUsableVideoUrl(resolvedUrl) && !before.has(resolvedUrl)) {
                  notifyProgress('VIDEO_READY', 'Video berhasil dirender di Google Flow!', 100);
                  return { video_url: resolvedUrl, references_added: referencesAdded };
                }
              }
            }

            // 6. Check for Error Cards on Canvas (Trigger retry if available, but NEVER abort early!)
            const errorCards = allCanvasTiles.filter(isErrorEl);
            const newErrorCards = errorCards.filter((t) => {
              const tileKey = t.getAttribute('data-media-id') || t.getAttribute('id') || (t.querySelector('img')?.src) || (t.innerText || '').slice(0, 50);
              if (tileKey && beforeErrorTileIds.has(tileKey)) return false;
              return true;
            });

            if (newErrorCards.length > 0) {
              const targetCard = newErrorCards[0];
              const retryBtn = findRetryBtn(targetCard);
              const cardRetries = Number(targetCard.dataset.retriedCount || 0);

              if (cardRetries < 2 && videoRetryAttempts < 2 && Date.now() - lastVideoRetryTime > 6000) {
                if (retryBtn) {
                  targetCard.dataset.retriedCount = String(cardRetries + 1);
                  videoRetryAttempts++;
                  lastVideoRetryTime = Date.now();
                  notifyProgress('AUTO_RETRY', `⚠️ Google Flow menampilkan pesan kendala video ("Gagal / Kebijakan"); mencoba klik Retry otomatis (${videoRetryAttempts}/2)...`, 50 + (videoRetryAttempts * 10));
                  clickElementWithBypass(retryBtn);
                  renderDeadline = Math.max(renderDeadline, Date.now() + 60000);
                  await sleep(4000);
                  continue;
                }
              }
              // In Google Flow dual generation, 1 tile frequently fails while the 2nd tile succeeds.
              // We do not abort early here; we let the polling loop continue until renderDeadline so the valid sibling tile can complete!
            }
          }

          // When renderDeadline has elapsed without finding any valid video:
          const finalErrorCards = Array.from(document.querySelectorAll('flow-error-tile, .error-tile, [class*="error"]')).filter(isErrorEl);
          if (finalErrorCards.length > 0) {
            const errText = (finalErrorCards[0].innerText || finalErrorCards[0].textContent || '').trim().replace(/\s+/g, ' ').slice(0, 150);
            notifyProgress('GENERATION_FAILED', `⛔ Render video ditolak atau gagal di Google Flow setelah percobaan: ${errText}`, 0);
            return { error: 'FLOW_GENERATION_FAILED_AFTER_RETRIES', details: errText };
          }

          // Timeout: Return explicit error, never return prior scene video
          return { error: 'FLOW_UI_VIDEO_GENERATION_TIMEOUT' };
        },
        args: [prepData, requestId],
      }).catch(() => null);

      if (result?.[0]?.result?.video_url) break;
    }
    } finally {
      for (const cid of candidateIds) {
        await chrome.scripting.executeScript({
          target: { tabId: cid },
          world: 'MAIN',
          func: () => {
            if (typeof window !== 'undefined' && typeof window.__sinematicaUnblock === 'function') {
              window.__sinematicaUnblock();
            }
            if (typeof document !== 'undefined') {
              const blocker = document.getElementById('sinematica-interaction-blocker');
              if (blocker) blocker.remove();
              const cursor = document.getElementById('sinematica-fake-cursor');
              if (cursor) cursor.remove();
            }
          }
        }).catch(() => {});
      }
    }

    const value = result?.[0]?.result;
    if (!value?.video_url) {
      return { status: 500, data: { error: `FLOW_UI_VIDEO_FALLBACK_${value?.error || 'NO_VIDEO'}` } };
    }
    const handle = encodeUiVideoHandle(value.video_url);
    return {
      status: 200,
      data: {
        media: [{ name: handle, video: { videoUrl: value.video_url } }],
        uiVideoUrl: value.video_url,
        referencesAdded: value.references_added || 0,
      },
      auth_mode: 'authenticated_flow_ui_session',
    };
  } catch (error) {
    console.warn('[Sinematica Agent] Flow UI video fallback failed:', error);
    return { status: 500, data: { error: `FLOW_UI_VIDEO_FALLBACK_EXCEPTION: ${error?.message || String(error)}` } };
  }
}

async function _probeTokenFromTab(tabId) {
  if (flowKey || !tabId) return flowKey;
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      world: 'MAIN',
      func: () => {
        try {
          const findBearer = (value, seen = new Set()) => {
            if (typeof value === 'string') {
              const m = value.match(/ya29\.[A-Za-z0-9_.~-]+/);
              return m?.[0] || null;
            }
            if (!value || typeof value !== 'object' || seen.has(value)) return null;
            seen.add(value);
            for (const key of Object.keys(value).slice(0, 80)) {
              const found = findBearer(value[key], seen);
              if (found) return found;
            }
            return null;
          };
          for (let i = 0; i < localStorage.length; i++) {
            const found = findBearer(localStorage.getItem(localStorage.key(i)));
            if (found) return found;
          }
          for (let i = 0; i < sessionStorage.length; i++) {
            const found = findBearer(sessionStorage.getItem(sessionStorage.key(i)));
            if (found) return found;
          }
        } catch (_) {}
        return null;
      },
    });
    const foundToken = results?.[0]?.result;
    if (foundToken && typeof foundToken === 'string' && !flowKey) {
      flowKey = foundToken;
      chrome.storage.local.set({ flowKey });
      console.log('[Sinematica Agent] Recovered OAuth session from Flow tab.');
      notifyTokenCaptured();
      return flowKey;
    }
    // MV3 isolated content scripts can see a different storage context than
    // MAIN-world injection. Ask the content script as a second per-profile
    // recovery path before declaring this Chrome profile unauthenticated.
    if (!flowKey) {
      const pageAuth = await chrome.tabs.sendMessage(tabId, { type: 'GET_PAGE_AUTH_TOKEN' }).catch(() => null);
      const recoveredPageToken = pageAuth?.flow_key;
      if (recoveredPageToken && !flowKey) {
        flowKey = recoveredPageToken;
        chrome.storage.local.set({ flowKey });
        notifyTokenCaptured();
        return flowKey;
      }
    }
  } catch (_) {}
  // A logged-in Flow page need not keep its access token in Web Storage or
  // send an API request while idle. Recover from the existing Google session.
  if (!flowKey) {
    if (!sessionRecovery && Date.now() - lastSessionRecoveryAt >= 15000) {
      lastSessionRecoveryAt = Date.now();
      sessionRecovery = FlowAuth.recoverSession().finally(() => { sessionRecovery = null; });
    }
    const recovered = sessionRecovery ? await sessionRecovery : null;
    if (recovered && !flowKey) {
      flowKey = recovered;
      chrome.storage.local.set({ flowKey });
      notifyTokenCaptured();
    }
  }
  return flowKey;
}

async function _probeTokenFromAnyFlowTab(preferredTabId = null) {
  if (flowKey) return flowKey;
  const tabs = await FlowTab.queryFlowTabs(chrome).catch(() => []);
  const ids = [preferredTabId, ...(tabs || []).map(tab => tab.id)]
    .filter((id, index, list) => id && list.indexOf(id) === index);
  for (const id of ids) {
    const found = await _probeTokenFromTab(id);
    if (found) return found;
  }
  return flowKey;
}
// ─── Native Main World API Request Proxy ───────────────────
async function handleApiRequest(msg) {
  const { id, endpoint, body, flow_key } = msg;

  // Video renders created through the authenticated Flow composer do not have
  // an API operation that can be polled with the public API key. Return the
  // already completed UI result directly to the normal backend poller.
  if (endpoint.includes('batchCheckAsyncVideoGenerationStatus')) {
    const serializedBody = JSON.stringify(body || {});
    const uiHandle = serializedBody.match(/ui_video:[A-Za-z0-9_-]+/)?.[0];
    const uiVideoUrl = decodeUiVideoHandle(uiHandle);
    if (uiHandle && uiVideoUrl && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'api_response',
        id,
        status: 200,
        data: {
          media: [{
            name: uiHandle,
            status: 'COMPLETED',
            mediaMetadata: { mediaStatus: 'MEDIA_GENERATION_STATUS_SUCCESSFUL' },
            video: { videoUrl: uiVideoUrl },
          }],
        },
        auth_mode: 'authenticated_flow_ui_session',
      }));
      return;
    }
  }

  // Harvest all completed video tiles from the Google Flow project canvas
  if (endpoint === '/internal/harvest_project_videos' || endpoint === '/v1/harvest_project_videos' || (endpoint && endpoint.includes('harvest_project_videos'))) {
    try {
      const harvestTargetTab = await FlowTab.ensureFlowTab(chrome);
      const harvestResults = await chrome.scripting.executeScript({
        target: { tabId: harvestTargetTab.id },
        func: async () => {
          const sleep = (ms) => new Promise(r => setTimeout(r, ms));
          const isUsableVideoUrl = (url) => {
            if (!url || typeof url !== 'string') return false;
            if (url.startsWith('blob:') || url.startsWith('data:video/')) return true;
            try {
              const parsed = new URL(url);
              return parsed.hostname === 'flow-content.google'
                || parsed.hostname === 'flow.google.com'
                || parsed.hostname.endsWith('.googleusercontent.com')
                || parsed.hostname === 'storage.googleapis.com'
                || parsed.hostname.endsWith('.gstatic.com');
            } catch (_) {
              return false;
            }
          };

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
            const directVid = tile.querySelector('video');
            let videoUrl = directVid?.currentSrc || directVid?.src;
            let duration = directVid?.duration || 0;
            const label = tile.getAttribute?.('aria-label') || tile.innerText?.replace(/play_arrow|play_circle/g, '').trim() || '';

            if (!videoUrl || !isUsableVideoUrl(videoUrl)) {
              const clickTarget = tile.querySelector('.mobile-play-badge') ||
                tile.querySelector('.thumbnail') ||
                tile.querySelector('img') ||
                tile;

              if (clickTarget) {
                try { clickTarget.click(); } catch (_) {}
                for (let att = 0; att < 25; att++) {
                  await sleep(200);
                  const mVid = document.querySelector('video');
                  const mSrc = mVid?.currentSrc || mVid?.src;
                  if (mSrc && isUsableVideoUrl(mSrc) && (mSrc.includes('flow-content') || mSrc.endsWith('.mp4') || mSrc.startsWith('blob:'))) {
                    videoUrl = mSrc;
                    duration = mVid?.duration || 0;
                    break;
                  }
                }

                const bBtn = Array.from(document.querySelectorAll('button')).find((b) =>
                  (b.innerText && b.innerText.includes('arrow_back')) ||
                  (b.getAttribute('aria-label') && b.getAttribute('aria-label').toLowerCase().includes('back'))
                );
                if (bBtn) {
                  try { bBtn.click(); } catch (_) {}
                  await sleep(350);
                }
              }
            }

            if (videoUrl && isUsableVideoUrl(videoUrl)) {
              results.push({
                index: i,
                scene_index: i + 1,
                label,
                video_url: videoUrl,
                duration,
              });
            }
          }

          return results;
        },
      });

      const harvestedVideos = harvestResults?.[0]?.result || [];
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'api_response',
          id,
          status: 200,
          data: {
            success: true,
            videos: harvestedVideos,
            count: harvestedVideos.length,
          },
          auth_mode: 'authenticated_flow_ui_session',
        }));
      }
      return;
    } catch (harvestErr) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'api_response',
          id,
          status: 500,
          data: { error: `HARVEST_FAILED: ${harvestErr.message}` },
        }));
      }
      return;
    }
  }

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
    if (lastKnownCredits !== null && lastKnownCredits !== undefined && Number.isFinite(lastKnownCredits)) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'api_response',
          id,
          status: 200,
          data: {
            credits: `${lastKnownCredits} Kredit`,
            details: { exact: true, value: lastKnownCredits }
          }
        }));
      }
      return;
    }

    try {
      const domResults = await chrome.scripting.executeScript({
        target: { tabId: targetTab.id, allFrames: true },
        func: async () => {
          try {
            const parseCreditStr = (str) => {
              if (!str) return null;
              const m1 = str.match(/([\d,.]+)\s*(?:Google Flow credits?|credits?|kredit(?: google flow)?|poin|points?)/i);
              if (m1 && m1[1] && /\d/.test(m1[1])) {
                return m1[1].trim() + " Kredit";
              }
              const m2 = str.match(/(?:kredit|credits?|poin|points?)\s*[:：]?\s*([\d,.]+)/i);
              if (m2 && m2[1] && /\d/.test(m2[1])) {
                return m2[1].trim() + " Kredit";
              }
              return null;
            };

            // 1. Check existing visible text first (DO NOT click if already visible or open)
            let bodyText = document.body ? (document.body.innerText || document.body.textContent || "") : "";
            let found = parseCreditStr(bodyText);
            if (found) return { credits: found, source: 'direct_visible' };

            // 2. Check shadow DOMs passively (DO NOT click any link or avatar button)
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
              if (el.shadowRoot) {
                const sTxt = el.shadowRoot.innerText || el.shadowRoot.textContent || "";
                found = parseCreditStr(sTxt);
                if (found) return { credits: found, source: 'shadow_root' };
              }
            }

            // 3. TreeWalker fallback
            const walk = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walk.nextNode()) {
              const val = node.nodeValue || "";
              if (val.toLowerCase().includes('credit') || val.toLowerCase().includes('kredit') || val.toLowerCase().includes('poin')) {
                const parentText = node.parentElement ? node.parentElement.innerText : val;
                found = parseCreditStr(parentText);
                if (found) return { credits: found, source: 'treewalker' };
              }
            }

            return { credits: null };
          } catch (e) {
            return { error: e.toString() };
          }
        }
      });

      const matchedFrame = (domResults || []).map(r => r.result).find(r => r && r.credits);
      const resObj = matchedFrame || (domResults && domResults[0] && domResults[0].result) || {};
      const creditsFound = (matchedFrame && matchedFrame.credits) || (lastKnownCredits !== null ? `${lastKnownCredits} Kredit` : null);

      if (creditsFound) {
        const numMatch = creditsFound.match(/\d[\d,.]*/);
        if (numMatch) {
          const token = numMatch[0];
          const rawNum = Number(token.includes('.') && /^\d{1,3}(?:\.\d{3})+$/.test(token)
            ? token.replace(/\./g, '')
            : token.replace(/,/g, ''));
          if (Number.isFinite(rawNum)) {
            lastKnownCredits = rawNum;
            chrome.storage.local.set({ lastKnownCredits });
          }
        }
      }

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'api_response',
          id,
          status: creditsFound ? 200 : 404,
          data: {
            credits: creditsFound || "Belum Terbaca (Buka Profil di Flow)",
            details: resObj
          }
        }));
      }
      return;
    } catch (domErr) {
      console.warn('[Sinematica Agent] Error scraping DOM credits:', domErr);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'api_response',
          id,
          status: 404,
          data: {
            credits: "Belum Terbaca (Buka Profil di Flow)",
            error: domErr.toString()
          }
        }));
      }
      return;
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
    // A profile may report session_ready while its cached flowKey is empty or
    // stale. Recover the OAuth token from this profile's actual Flow tab before
    // sending the request; otherwise Google sees only the public API key.
    const recoveredBearerKey = await _probeTokenFromAnyFlowTab(targetTab.id);
    const activeBearerKey = recoveredBearerKey || flow_key || flowKey;
    const isOwnImageRequest = endpoint.includes('batchGenerateImages');
    const isVideoReferenceRequest = endpoint.includes('batchAsyncGenerateVideoReferenceImages');

    // Keep request-local reference extraction here.  The UI fallback has its
    // own collector, but this handler must not read that function's local
    // `referenceIds` variable (which caused the Mika 500 ReferenceError).
    const requestReferenceIds = [];
    const collectRequestReferenceIds = (value, key = '') => {
      if (!value) return;
      if (Array.isArray(value)) {
        value.forEach(item => collectRequestReferenceIds(item, key));
        return;
      }
      if (typeof value !== 'object') return;
      if (typeof value.mediaId === 'string') requestReferenceIds.push(value.mediaId);
      if (typeof value.referenceId === 'string') requestReferenceIds.push(value.referenceId);
      if (typeof value.imageId === 'string') requestReferenceIds.push(value.imageId);
      Object.entries(value).forEach(([childKey, childValue]) => {
        if (/reference|imageinput|ingredient|media/i.test(childKey)) {
          collectRequestReferenceIds(childValue, childKey);
        }
      });
    };
    collectRequestReferenceIds(body);

    // Google Flow's current UI keeps the OAuth credential inside its own
    // authenticated application context. Do not send an API-key-only image
    // request first: that path is rejected by aisandbox-pa with HTTP 401 even
    // though the visible Flow session is valid. Route image generation through
    // the logged-in Flow composer when no bearer is available.
    const imageHasReferences = requestReferenceIds.length > 0;
    // Reference Image requests must use the visible authenticated Flow
    // composer. Even a stale cached bearer token can otherwise make the
    // extension send an API-key/HTTP request and Flow returns 401.
    if (isOwnImageRequest && imageHasReferences) {
      const uiFallback = await generateImageViaAuthenticatedFlowUi(targetTab.id, body, id);
      if (uiFallback?.status === 200) {
        recordMetrics(true, 'IMAGE');
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'api_response', id, status: 200, data: uiFallback.data, auth_mode: 'authenticated_flow_ui_session' }));
        }
        return;
      }
      const fallbackError = uiFallback?.data?.error || 'FLOW_UI_AUTHENTICATED_REFERENCE_GENERATION_UNAVAILABLE';
      recordMetrics(false, 'IMAGE', fallbackError);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'api_response', id, status: 503, data: { error: fallbackError }, auth_mode: 'authenticated_flow_ui_session_unavailable' }));
      }
      return;
    }
    if (isOwnImageRequest && !activeBearerKey) {
      const uiFallback = await generateImageViaAuthenticatedFlowUi(targetTab.id, body, id);
      if (uiFallback?.status === 200) {
        recordMetrics(true, 'IMAGE');
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'api_response',
            id,
            status: uiFallback.status,
            data: uiFallback.data,
            auth_mode: 'authenticated_flow_ui_session',
          }));
        }
        return;
      }
      // Never fall through to the API-key-only endpoint. Google rejects that
      // request with 401 even when the visible Flow session is authenticated.
      const fallbackError = uiFallback?.data?.error || 'FLOW_UI_AUTHENTICATED_GENERATION_UNAVAILABLE';
      recordMetrics(false, 'IMAGE', fallbackError);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'api_response',
          id,
          status: 503,
          data: { error: fallbackError },
          auth_mode: 'authenticated_flow_ui_session_unavailable',
        }));
      }
      return;
    }

    // The current Flow web app can submit Ingredients video jobs from its
    // authenticated composer, but its R2V HTTP endpoint rejects the public
    // API key when no bearer is exposed to the extension. Always use the UI
    // session and attach the storyboard and character ingredients directly into the composer.
    if (isVideoReferenceRequest) {
      const uiFallback = await generateVideoViaAuthenticatedFlowUi(targetTab.id, body, id);
      if (uiFallback?.status === 200) {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'api_response',
            id,
            status: 200,
            data: uiFallback.data,
            auth_mode: 'authenticated_flow_ui_session',
          }));
        }
        return;
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'api_response',
          id,
          status: 503,
          data: { error: uiFallback?.data?.error || 'FLOW_UI_VIDEO_FALLBACK_UNAVAILABLE' },
          auth_mode: 'authenticated_flow_ui_session_unavailable',
        }));
      }
      return;
    }

    if (isOwnImageRequest) selfRequestsInFlight++;

    let attempts = 0;
    const maxAttempts = 3;
    let lastTabErr = null;

    while (attempts < maxAttempts) {
      attempts++;
      try {
        const tabCheck = await chrome.tabs.get(targetTab.id).catch(() => null);
        if (!tabCheck) {
          const freshTabs = await FlowTab.queryFlowTabs(chrome);
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
          func: async (fetchUrl, requestBody, actionName, projId, bearerKey, deferFetchToWorker) => {
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

              // flow.google.com is a new UI origin, while this API key is still restricted
              // to labs.google. Let the extension worker perform the network call so the
              // successful response is not hidden from JavaScript by page-origin CORS.
              if (deferFetchToWorker) {
                return { deferred: true, finalBody, reqHeaders };
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
          args: [
            url,
            body,
            captchaAction,
            currentProjectId,
            activeBearerKey,
            // Uploads must use the extension worker too.  The Flow page can
            // generate through its own origin, but upload endpoints reject or
            // hide page-origin fetches behind CORS; the worker has the same
            // authenticated session and host permissions.
            String(tabCheck?.url || targetTab.url || '').startsWith('https://flow.google.com/'),
          ]
        });

        if (isOwnImageRequest) selfRequestsInFlight = Math.max(0, selfRequestsInFlight - 1);

        if (results && results[0] && results[0].result) {
          let executionResult = results[0].result;
          if (executionResult.deferred) {
            try {
              const workerResponse = await fetch(url, {
                method: 'POST',
                headers: executionResult.reqHeaders || { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(executionResult.finalBody),
              });
              const responseText = await workerResponse.text();
              let responseData = {};
              try {
                responseData = responseText ? JSON.parse(responseText) : {};
              } catch (_) {
                responseData = { error: responseText.slice(0, 1000) };
              }
              executionResult = { status: workerResponse.status, data: responseData };
            } catch (workerError) {
              executionResult = {
                status: 500,
                error: `Extension worker fetch gagal: ${workerError?.message || String(workerError)}`,
              };
            }
          }

          const { status, data, error } = executionResult;
          const responseData = data ?? (error ? { error } : {});
          if (status === 401) {
            console.warn('[Sinematica Agent] Request 401 received, refreshing Flow OAuth token...');
            invalidateFlowAuth('FLOW_LOGIN_EXPIRED');
            if (isOwnImageRequest && attempts === 1) {
              const uiFallback = await generateImageViaAuthenticatedFlowUi(targetTab.id, body, id);
              if (uiFallback) {
                if (isOwnImageRequest) selfRequestsInFlight = Math.max(0, selfRequestsInFlight - 1);
                recordMetrics(uiFallback.status === 200, 'IMAGE', uiFallback.status === 200 ? '' : (uiFallback.data?.error || 'FLOW_UI_FALLBACK_FAILED'));
                if (ws && ws.readyState === WebSocket.OPEN) {
                  ws.send(JSON.stringify({
                    type: 'api_response',
                    id,
                    status: uiFallback.status,
                    data: uiFallback.data,
                    auth_mode: 'authenticated_flow_ui_session',
                  }));
                }
                return;
              }
            }
            if (attempts < maxAttempts) {
              const refreshedToken = await _probeTokenFromTab(targetTab.id);
              if (refreshedToken) continue;
            }
          }
          if (responseData && typeof responseData === 'object') {
            const rem = responseData.remainingCredits ?? responseData.credits;
            if (rem !== undefined && rem !== null && Number.isFinite(Number(rem))) {
              lastKnownCredits = Number(rem);
              chrome.storage.local.set({ lastKnownCredits });
            }
          }
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
              data: responseData,
              error: error || undefined,
              auth_mode: activeBearerKey ? 'oauth_bearer' : 'authenticated_flow_page_session',
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

async function handleNativeClick(targetTabId, x, y, options = {}) {
  let resolvedTabId = targetTabId;
  if (!resolvedTabId) {
    try {
      const activeTab = await FlowTab.ensureFlowTab(chrome);
      if (activeTab && activeTab.id) {
        resolvedTabId = activeTab.id;
      }
    } catch (_) {}
  }

  if (!resolvedTabId || typeof x !== 'number' || typeof y !== 'number') {
    return { ok: false, error: 'Invalid click coordinates or tabId' };
  }
  const target = { tabId: resolvedTabId };

  // Temporarily permit automation input through the blocker and disable blocker pointer-events
  await chrome.scripting.executeScript({
    target: { tabId: resolvedTabId },
    world: 'MAIN',
    func: () => {
      window.__sinematicaAllowNativeInput = true;
      if (document.documentElement && document.documentElement.dataset) {
        document.documentElement.dataset.sinematicaAllowInput = 'true';
      }
      const blocker = document.getElementById('sinematica-interaction-blocker');
      if (blocker) blocker.style.setProperty('pointer-events', 'none', 'important');
    },
  }).catch(() => {});

  let debuggerAttached = false;
  try {
    try {
      await chrome.debugger.attach(target, '1.3');
      debuggerAttached = true;
    } catch (e) {
      console.warn('[Sinematica Agent] Debugger attach note:', e?.message || e);
    }

    if (debuggerAttached) {
      await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
        type: 'mouseMoved',
        x: Math.round(x),
        y: Math.round(y),
      }).catch(() => {});
      await new Promise((r) => setTimeout(r, 40));

      await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
        type: 'mousePressed',
        x: Math.round(x),
        y: Math.round(y),
        button: 'left',
        clickCount: 1,
      }).catch(() => {});

      await new Promise((r) => setTimeout(r, 80));

      await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
        type: 'mouseReleased',
        x: Math.round(x),
        y: Math.round(y),
        button: 'left',
        clickCount: 1,
      }).catch(() => {});

      if (options && options.sendEnter) {
        await new Promise((r) => setTimeout(r, 40));
        await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
          type: 'rawKeyDown',
          key: 'Enter',
          code: 'Enter',
          windowsVirtualKeyCode: 13,
          nativeVirtualKeyCode: 13,
          macCharCode: 13,
          text: '\r',
          unmodifiedText: '\r',
        }).catch(() => {});
        await new Promise((r) => setTimeout(r, 40));
        await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
          type: 'keyUp',
          key: 'Enter',
          code: 'Enter',
          windowsVirtualKeyCode: 13,
          nativeVirtualKeyCode: 13,
          macCharCode: 13,
          text: '\r',
          unmodifiedText: '\r',
        }).catch(() => {});
      }

      await new Promise((r) => setTimeout(r, 60));

      try {
        await chrome.debugger.detach(target);
      } catch (_) {}
    } else {
      // Fallback: Dispatch direct in-page element click if debugger is unavailable (e.g. DevTools already open)
      await chrome.scripting.executeScript({
        target: { tabId: resolvedTabId },
        world: 'MAIN',
        func: (clickX, clickY) => {
          const el = document.elementFromPoint(clickX, clickY);
          const btn = el?.closest('button') || document.querySelector('flow-generate-icon-button button') || el;
          if (btn && typeof btn.click === 'function') {
            btn.click();
          }
        },
        args: [Math.round(x), Math.round(y)],
      }).catch(() => {});
    }

    return { ok: true, debuggerUsed: debuggerAttached };
  } catch (err) {
    if (debuggerAttached) {
      try { await chrome.debugger.detach(target); } catch (_) {}
    }
    return { ok: false, error: err?.message || String(err) };
  } finally {
    await new Promise((r) => setTimeout(r, 120));
    // Restore blocker pointer-events and clear native input allow flag
    await chrome.scripting.executeScript({
      target: { tabId: resolvedTabId },
      world: 'MAIN',
      func: () => {
        window.__sinematicaAllowNativeInput = false;
        if (document.documentElement && document.documentElement.dataset) {
          delete document.documentElement.dataset.sinematicaAllowInput;
        }
        const blocker = document.getElementById('sinematica-interaction-blocker');
        if (blocker) blocker.style.setProperty('pointer-events', 'auto', 'important');
      },
    }).catch(() => {});
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'DISPATCH_NATIVE_CLICK') {
    const targetTabId = msg.tabId || (sender && sender.tab ? sender.tab.id : null);
    handleNativeClick(targetTabId, msg.x, msg.y, { sendEnter: Boolean(msg.sendEnter) }).then((res) => {
      sendResponse(res);
    }).catch((err) => {
      sendResponse({ ok: false, error: err?.message || String(err) });
    });
    return true;
  }
  if (msg.type === 'FLOW_PAGE_PROGRESS' || msg.type === 'FLOW_TASK_PROGRESS') {
    sendTaskProgress(msg.id || msg.taskId, msg.stage, msg.message, { percent: msg.percent, ...(msg.extra || {}) });
  }

  if (msg.type === 'CAPTURE_FLOW_AUTH' && typeof msg.value === 'string') {
    const match = msg.value.match(/^Bearer\s+(\S+)/i);
    if (match && match[1] && flowKey !== match[1]) {
      flowKey = match[1];
      chrome.storage.local.set({ flowKey });
      notifyTokenCaptured();
    }
  }
  if (msg.type === 'SNIFFED_FLOW_CREDITS' && msg.credits !== undefined) {
    const val = Number(msg.credits);
    if (Number.isFinite(val)) {
      lastKnownCredits = val;
      chrome.storage.local.set({ lastKnownCredits });
      console.log('[Sinematica Agent] Sniffed exact Flow credits:', lastKnownCredits);
    }
  }

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

  if (msg.type === 'UPDATE_MANUAL_TOKEN' && msg.flowKey) {
    flowKey = msg.flowKey;
    chrome.storage.local.set({ flowKey });
    console.log('[Sinematica Agent] Manual token applied:', flowKey.slice(0, 15) + '...');
    notifyTokenCaptured();
    sendResponse({ success: true });
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

  if (msg.type === 'TASK_PROGRESS') {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'task_progress',
        id: msg.payload?.taskId || msg.taskId || msg.id,
        progress: msg.payload?.progress || msg.progress,
        stage: msg.payload?.step || msg.step || msg.stage,
        message: msg.payload?.message || msg.message,
        data: msg.payload?.data || msg.data,
      }));
    }
  }

  if (msg.type === 'TASK_COMPLETED') {
    const taskId = msg.payload?.taskId || msg.taskId || msg.id;
    recordMetrics(true, 'TASK');
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'task_response',
        id: taskId,
        status: 200,
        data: msg.payload || msg.data || msg.result,
        result: msg.payload || msg.data || msg.result,
      }));
    }
  }

  if (msg.type === 'TASK_FAILED') {
    const taskId = msg.payload?.taskId || msg.taskId || msg.id;
    const errorMsg = msg.payload?.error || msg.error || 'FLOW_TASK_FAILED';
    recordMetrics(false, 'TASK', errorMsg);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'task_response',
        id: taskId,
        status: 500,
        error: errorMsg,
        data: msg.payload || msg.data,
      }));
    }
  }

  if (msg.type === 'GOOGLE_FLOW_API_EVENT') {
    const flowEvt = msg.event;
    if (flowEvt) {
      if (flowEvt.type === 'CREDITS_UPDATED' && flowEvt.credits !== undefined) {
        const val = Number(flowEvt.credits);
        if (Number.isFinite(val)) {
          lastKnownCredits = val;
          chrome.storage.local.set({ lastKnownCredits });
        }
      }
      if (flowEvt.type === 'PROJECT_DETECTED' && flowEvt.projectId) {
        if (currentProjectId !== flowEvt.projectId) {
          currentProjectId = flowEvt.projectId;
          chrome.storage.local.set({ currentProjectId });
          notifyRegistration();
        }
      }
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'flow_api_event',
        event: msg.event,
        url: msg.url,
        instance_id: instanceId,
      }));
    }
  }

  if (msg.type === 'GOOGLE_FLOW_PROFILE_DETECTED') {
    if (msg.credits !== undefined && msg.credits !== '') {
      const val = Number(msg.credits);
      if (Number.isFinite(val)) {
        lastKnownCredits = val;
        chrome.storage.local.set({ lastKnownCredits });
      }
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'flow_profile_detected',
        email: msg.email,
        credits: msg.credits,
        url: msg.url,
        instance_id: instanceId,
      }));
    }
  }
});
