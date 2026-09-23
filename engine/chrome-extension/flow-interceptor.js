/**
 * Sinematica Flow Agent - Main-World Network Interceptor
 * Injected into the MAIN execution world on https://flow.google.com/*
 * Intercepts fetch and XMLHttpRequest calls non-intrusively, parses API responses,
 * posts high-level events to the isolated world content script, and provides
 * direct in-page Boq/REST RPC dispatch for background file uploads.
 */

(function (global) {
  'use strict';

  if (typeof window !== 'undefined' && window.__sinematicaFlowInterceptorInjected) {
    return;
  }
  if (typeof window !== 'undefined') {
    window.__sinematicaFlowInterceptorInjected = true;
  }

  const MESSAGE_SOURCE = 'SINEMATICA_FLOW_INTERCEPTOR';
  let lastDispatchedEventKey = '';
  let lastKnownProjectId = '';

  function getParser() {
    return (typeof window !== 'undefined' && window.FlowNetworkParser) ||
      (typeof globalThis !== 'undefined' ? globalThis.FlowNetworkParser : null) ||
      (typeof require !== 'undefined' ? require('./flow-network-parser.js').FlowNetworkParser : null);
  }

  function emitFlowEvent(event) {
    if (!event || !event.type) return;

    if (typeof window !== 'undefined') {
      window.__sinematicaFlowEvents = window.__sinematicaFlowEvents || [];
      window.__sinematicaFlowEvents.push({ ...event, time: Date.now() });
      if (event.type === 'VIDEO_READY' || event.status === 'VIDEO_READY') {
        window.__sinematicaLastVideoReadyEvent = { ...event, time: Date.now() };
      }
      if (event.type === 'IMAGE_READY' || event.status === 'IMAGE_READY') {
        window.__sinematicaLastImageReadyEvent = { ...event, time: Date.now() };
      }
    }

    // Deduplicate rapid identical events
    const eventKey = `${event.type}_${event.status}_${event.projectId || ''}_${event.mediaId || ''}_${(event.videoUrls || []).join(',')}_${(event.imageUrls || []).join(',')}_${event.errorCode || ''}`;
    if (eventKey === lastDispatchedEventKey && Date.now() - (event.lastSent || 0) < 500) {
      return;
    }
    lastDispatchedEventKey = eventKey;
    event.lastSent = Date.now();

    // Track active project ID
    if (event.projectId && event.projectId !== lastKnownProjectId) {
      lastKnownProjectId = event.projectId;
    } else if (lastKnownProjectId && !event.projectId) {
      event.projectId = lastKnownProjectId;
    }

    try {
      if (typeof window !== 'undefined' && typeof window.postMessage === 'function') {
        window.postMessage({
          source: MESSAGE_SOURCE,
          event,
          timestamp: Date.now(),
        }, '*');
      }
    } catch (err) {
      console.warn('[Sinematica Flow Interceptor] Failed to postMessage:', err);
    }
  }

  // Check current URL for project UUID
  function inspectCurrentUrl() {
    if (typeof window === 'undefined') return;
    const parser = getParser();
    if (!parser) return;
    const currentUrl = window.location.href || '';
    const projId = parser.extractProjectIdFromUrl(currentUrl);
    if (projId && projId !== lastKnownProjectId) {
      lastKnownProjectId = projId;
      emitFlowEvent({
        type: parser.STATUS_EVENTS.PROJECT_CREATED,
        status: parser.STATUS_EVENTS.PROJECT_CREATED,
        projectId: projId,
        url: currentUrl,
      });
    }
  }

  if (typeof window !== 'undefined') {
    inspectCurrentUrl();
    if (typeof window.addEventListener === 'function') {
      window.addEventListener('popstate', inspectCurrentUrl);
      window.addEventListener('hashchange', inspectCurrentUrl);
    }

    if (typeof history !== 'undefined') {
      const origPushState = history.pushState;
      if (typeof origPushState === 'function') {
        history.pushState = function () {
          const res = origPushState.apply(this, arguments);
          setTimeout(inspectCurrentUrl, 0);
          return res;
        };
      }

      const origReplaceState = history.replaceState;
      if (typeof origReplaceState === 'function') {
        history.replaceState = function () {
          const res = origReplaceState.apply(this, arguments);
          setTimeout(inspectCurrentUrl, 0);
          return res;
        };
      }
    }
  }

  // -------------------------------------------------------------
  // Monkey-patch window.fetch (Non-intrusive)
  // -------------------------------------------------------------
  if (typeof window !== 'undefined') {
    const originalFetch = window.fetch;
    if (typeof originalFetch === 'function') {
      window.fetch = async function (...args) {
        const response = await originalFetch.apply(this, args);

        try {
          const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
          const shouldInspect =
            url.includes('flow.google.com') ||
            url.includes('aisandbox-pa.googleapis.com') ||
            url.includes('batchexecute') ||
            url.includes('flowMedia') ||
            url.includes('/fx/api') ||
            url.includes('/upload/') ||
            url.includes('/project');

          if (shouldInspect) {
            // Asynchronously clone response so we never block or drain original stream
            response.clone().text().then((text) => {
              const parser = getParser();
              if (!parser) return;
              const parsedEvent = parser.parseGoogleFlowResponse(url, response.status, text, {
                method: (args[1] && args[1].method) || 'GET',
              });
              if (parsedEvent) {
                emitFlowEvent(parsedEvent);
              }
            }).catch(() => {
              // Ignore cloning / streaming errors silently
            });
          }
        } catch {
          // Non-intrusive: never interfere with page logic
        }

        return response;
      };
    }
  }

  // -------------------------------------------------------------
  // Monkey-patch window.XMLHttpRequest (Non-intrusive)
  // -------------------------------------------------------------
  if (typeof XMLHttpRequest !== 'undefined') {
    const originalXhrOpen = XMLHttpRequest.prototype.open;
    const originalXhrSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
      this.__sinematicaRequestUrl = String(url || '');
      this.__sinematicaRequestMethod = String(method || 'GET');
      return originalXhrOpen.apply(this, [method, url, ...rest]);
    };

    XMLHttpRequest.prototype.send = function (...args) {
      const self = this;
      const url = self.__sinematicaRequestUrl || '';

      const shouldInspect =
        url.includes('flow.google.com') ||
        url.includes('aisandbox-pa.googleapis.com') ||
        url.includes('batchexecute') ||
        url.includes('flowMedia') ||
        url.includes('/fx/api') ||
        url.includes('/upload/') ||
        url.includes('/project');

      if (shouldInspect) {
        self.addEventListener('load', function () {
          try {
            const parser = getParser();
            if (!parser) return;
            const status = self.status;
            const text = self.responseText;
            const parsedEvent = parser.parseGoogleFlowResponse(url, status, text, {
              method: self.__sinematicaRequestMethod,
            });
            if (parsedEvent) {
              emitFlowEvent(parsedEvent);
            }
          } catch {
            // Silent
          }
        });
      }

      return originalXhrSend.apply(this, args);
    };
  }

  // -------------------------------------------------------------
  // Direct In-Page Boq RPC Execution Engine (100% Silent Background Execution)
  // -------------------------------------------------------------
  function getWizSessionData() {
    const wiz = (() => {
      if (typeof document !== 'undefined' && typeof document.querySelectorAll === 'function') {
        const s = Array.from(document.querySelectorAll('script')).find((x) => x.textContent?.includes('WIZ_global_data'));
        const m = s ? s.textContent?.match(/window\.WIZ_global_data\s*=\s*({[\s\S]*?});/) : null;
        if (m) {
          try { return JSON.parse(m[1]); } catch {}
        }
      }
      return (typeof window !== 'undefined' ? window.WIZ_global_data : null) || {};
    })();

    const fsid = wiz.FdrFJe || '';
    const bl = wiz.cfb2h || 'boq_labs-ai-sandbox-frontend_20260903.13_p0';
    const at = wiz.SNlM0e || '';
    const reqId = Math.floor(100000 + Math.random() * 900000);

    const pathname = (typeof location !== 'undefined' ? location.pathname : (typeof window !== 'undefined' && window.location ? window.location.pathname : '')) || '';
    const uMatch = pathname.match(/^(\/u\/\d+)/);
    const userPrefix = uMatch ? uMatch[1] : '';

    return { fsid, bl, at, reqId, userPrefix, pathname };
  }

  async function executeBatchexecuteRpc(rpcId, payloadArray) {
    const { fsid, bl, at, reqId, userPrefix, pathname } = getWizSessionData();
    const rpcRequest = [[[rpcId, JSON.stringify(payloadArray), null, 'generic']]];
    const body = new URLSearchParams();
    body.set('f.req', JSON.stringify(rpcRequest));
    if (at) body.set('at', at);

    const targetUrl = `${userPrefix}/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=${encodeURIComponent(rpcId)}&source-path=${encodeURIComponent(pathname)}&bl=${encodeURIComponent(bl)}&f.sid=${encodeURIComponent(fsid)}&hl=en&_reqid=${reqId}&rt=c`;

    const fetchFn = (typeof window !== 'undefined' && window.fetch) || globalThis.fetch;
    const res = await fetchFn(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
      credentials: 'include',
      body: body.toString(),
    });

    if (!res.ok) {
      throw new Error(`Boq RPC [${rpcId}] failed with HTTP status ${res.status}`);
    }

    const responseText = await res.text();
    const parser = getParser();
    if (!parser) return responseText;

    const decoded = parser.decodeBoqResponse(responseText);
    const targetRpc = decoded.find((r) => r.rpcId === rpcId) || decoded[0];
    return targetRpc ? targetRpc.data : responseText;
  }

  async function uploadImageDirect(params) {
    params = params || {};
    const parser = getParser();
    if (!parser) {
      throw new Error('FlowNetworkParser is not loaded in page context');
    }

    const currentUrl = typeof window !== 'undefined' ? window.location.href : '';
    const projectId = params.projectId || lastKnownProjectId || parser.extractProjectIdFromUrl(currentUrl) || '';
    let rawBase64 = params.base64Data || params.data || '';
    if (rawBase64.includes('base64,')) {
      rawBase64 = rawBase64.split('base64,')[1];
    }
    rawBase64 = rawBase64.trim();

    if (!rawBase64) {
      throw new Error('Base64 image data is required for in-page upload');
    }

    const mimeType = params.mimeType || 'image/png';
    const fileName = params.fileName || `ref_${Date.now()}.png`;

    const boqPayload = parser.buildBoqUploadImagePayload({
      base64Data: rawBase64,
      mimeType,
      fileName,
      projectId,
    });

    const rawResponse = await executeBatchexecuteRpc('uploadMedia', boqPayload);
    const parsedMedia = parser.parseBoqUploadImageResponse(
      rawResponse,
      fileName,
      '',
      projectId
    );

    return {
      ok: true,
      mediaId: parsedMedia.mediaId,
      displayName: parsedMedia.displayName,
      projectId: parsedMedia.projectId,
      timestamp: Date.now(),
    };
  }

  async function generateImageDirect(params) {
    params = params || {};
    const parser = getParser();
    if (!parser) {
      throw new Error('FlowNetworkParser is not loaded in page context');
    }

    const prompt = String(params.prompt || '').trim();
    if (!prompt) {
      throw new Error('Prompt is required for direct image generation');
    }

    const currentUrl = typeof window !== 'undefined' ? window.location.href : '';
    const projectId = params.projectId || lastKnownProjectId || parser.extractProjectIdFromUrl(currentUrl) || '';
    const ratioStr = String(params.aspectRatio || '9:16').trim();
    const aspectNum = ratioStr === '1:1' || ratioStr === 'square' ? 1 : ratioStr === '16:9' || ratioStr === 'landscape' ? 3 : 2; // 2 = 9:16
    const count = Math.max(1, Number(params.count || 1));
    const refIds = Array.isArray(params.referenceMediaIds) ? params.referenceMediaIds : (params.referenceMediaId ? [params.referenceMediaId] : []);

    const boqPayload = parser.buildBoqImagePayload({
      prompt,
      count,
      aspectRatio: aspectNum,
      seed: params.seed,
      projectId,
      referenceMediaIds: refIds,
    });

    const rawResponse = await executeBatchexecuteRpc('ogiZ0b', boqPayload);
    const assets = parser.parseBoqVideoGenResponse(rawResponse, prompt);

    let generatedImage = null;
    if (assets.length > 0) {
      const first = assets[0];
      const validUrl = first.url || first.downloadUrl || '';
      generatedImage = {
        id: first.mediaId || first.id,
        mediaId: first.mediaId || first.id,
        url: validUrl,
        downloadUrl: validUrl,
      };
    }

    return {
      ok: true,
      generatedImage,
      assets,
      projectId,
      timestamp: Date.now(),
    };
  }

  async function generateVideoDirect(params) {
    params = params || {};
    const parser = getParser();
    if (!parser) {
      throw new Error('FlowNetworkParser is not loaded in page context');
    }

    const prompt = String(params.prompt || params.videoPrompt || '').trim();
    if (!prompt) {
      throw new Error('Prompt is required for direct video generation');
    }

    const currentUrl = typeof window !== 'undefined' ? window.location.href : '';
    const projectId = params.projectId || lastKnownProjectId || parser.extractProjectIdFromUrl(currentUrl) || '';
    const ratioStr = String(params.aspectRatio || '9:16').trim();
    const aspectNum = ratioStr === '1:1' || ratioStr === 'square' ? 0 : ratioStr === '16:9' || ratioStr === 'landscape' ? 2 : 1;
    const isPortrait = aspectNum === 1;

    const startImageMediaId = params.startImageMediaId || params.referenceMediaId || '';
    const hasRef = Boolean(startImageMediaId);
    const durationSeconds = Number(params.durationSeconds || 8);

    let modelKey = params.model || '';
    if (/omni|flash|abra/i.test(modelKey)) {
      modelKey = durationSeconds
        ? (hasRef ? `abra_i2v_${durationSeconds}s` : `abra_t2v_${durationSeconds}s`)
        : (hasRef ? 'abra_i2v_8s' : 'abra_t2v_8s');
    } else if (/quality/i.test(modelKey)) {
      modelKey = hasRef
        ? (isPortrait ? 'veo_3_1_i2v_s_portrait' : 'veo_3_1_i2v_s')
        : (isPortrait ? 'veo_3_1_t2v_portrait' : 'veo_3_1_t2v');
    } else if (/fast/i.test(modelKey)) {
      modelKey = hasRef
        ? (isPortrait ? 'veo_3_1_i2v_s_fast_portrait_ultra_relaxed' : 'veo_3_1_i2v_s_fast_ultra_relaxed')
        : (isPortrait ? 'veo_3_1_t2v_fast_portrait_ultra_relaxed' : 'veo_3_1_t2v_fast_ultra_relaxed');
    } else {
      modelKey = hasRef
        ? (durationSeconds ? `abra_i2v_${durationSeconds}s` : 'abra_i2v_8s')
        : (durationSeconds ? `abra_t2v_${durationSeconds}s` : 'abra_t2v_8s');
    }

    const rpcId = hasRef ? 'eb1hJf' : 'YhhmEf';
    const boqPayload = parser.buildBoqVideoPayload({
      prompt,
      modelKey,
      aspectRatio: aspectNum,
      seed: params.seed,
      projectId,
      startImageMediaId,
      count: params.count || 1,
    });

    const rawResponse = await executeBatchexecuteRpc(rpcId, boqPayload);
    const assets = parser.parseBoqVideoGenResponse(rawResponse, prompt);

    return {
      ok: true,
      assets,
      rpcId,
      modelKey,
      projectId,
      timestamp: Date.now(),
    };
  }

  async function getMediaDownloadUrlDirect(mediaId) {
    if (!mediaId) throw new Error('mediaId is required to get media download URL');
    const cleanId = String(mediaId).replace(/^asset-/, '').replace(/^video-/, '').trim();
    const rawResponse = await executeBatchexecuteRpc('as29s', [cleanId]);
    const strJson = JSON.stringify(rawResponse);
    const videoUrlMatch = strJson.match(/https:\/\/flow-content\.google\/video\/[^"\s\\]+/) ||
                          strJson.match(/https?:\/\/[^"\s\\]+\.mp4[^"\s\\]*/);
    const imageUrlMatch = strJson.match(/https:\/\/flow-content\.google\/image\/[^"\s\\]+/) ||
                          strJson.match(/https?:\/\/[^"\s\\]+\.(png|jpg|jpeg|webp)[^"\s\\]*/);

    return {
      ok: true,
      mediaId: cleanId,
      videoUrl: videoUrlMatch ? videoUrlMatch[0] : null,
      imageUrl: imageUrlMatch ? imageUrlMatch[0] : null,
      raw: rawResponse,
    };
  }

  // Expose on window if in browser
  if (typeof window !== 'undefined') {
    window.__sinematica_uploadImageDirect = uploadImageDirect;
    window.__sinematica_generateImageDirect = generateImageDirect;
    window.__sinematica_generateVideoDirect = generateVideoDirect;
    window.__sinematica_getMediaDownloadUrlDirect = getMediaDownloadUrlDirect;
    window.__sinematica_executeBatchexecuteRpc = executeBatchexecuteRpc;

    // Listen for direct RPC dispatch requests from content script
    window.addEventListener('message', async (event) => {
      if (event.source !== window || !event.data || event.data.source !== 'SINEMATICA_CONTENT_SCRIPT') {
        return;
      }

      const { action, requestId, payload } = event.data;
      if (!action || !requestId) return;

      try {
        let result = null;
        if (action === 'DISPATCH_INPAGE_UPLOAD' || action === 'RPC_UPLOAD_IMAGE') {
          result = await uploadImageDirect(payload);
        } else if (action === 'RPC_GENERATE_IMAGE') {
          result = await generateImageDirect(payload);
        } else if (action === 'RPC_GENERATE_VIDEO') {
          result = await generateVideoDirect(payload);
        } else if (action === 'RPC_GET_MEDIA_URL') {
          result = await getMediaDownloadUrlDirect(payload.mediaId);
        } else if (action === 'RPC_EXECUTE_BATCHEXECUTE') {
          result = await executeBatchexecuteRpc(payload.rpcId, payload.payloadArray);
        } else if (action === 'ENSURE_PROJECT') {
          const parser = getParser();
          const pid = lastKnownProjectId || (parser ? parser.extractProjectIdFromUrl(window.location.href) : '');
          result = { ok: true, projectId: pid };
        } else {
          return;
        }

        window.postMessage({
          source: MESSAGE_SOURCE,
          type: 'SINEMATICA_DIRECT_RPC_RESPONSE',
          requestId,
          ok: true,
          result,
        }, '*');
      } catch (err) {
        window.postMessage({
          source: MESSAGE_SOURCE,
          type: 'SINEMATICA_DIRECT_RPC_RESPONSE',
          requestId,
          ok: false,
          error: err instanceof Error ? err.message : String(err),
        }, '*');
      }
    });
  }

  const exportObj = {
    getWizSessionData,
    executeBatchexecuteRpc,
    uploadImageDirect,
    generateImageDirect,
    generateVideoDirect,
    getMediaDownloadUrlDirect,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = exportObj;
  } else if (typeof window !== 'undefined') {
    window.FlowInterceptor = exportObj;
  } else if (typeof globalThis !== 'undefined') {
    globalThis.FlowInterceptor = exportObj;
  }
})(typeof globalThis !== 'undefined' ? globalThis : typeof self !== 'undefined' ? self : this);
