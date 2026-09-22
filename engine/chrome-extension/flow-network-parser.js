/**
 * Sinematica Flow Agent - Google Flow Boq Batchexecute & Network Response Parser
 * Translates low-level Google Flow API responses (REST & Boq batchexecute)
 * into standardized high-level automation events:
 * QUEUED, GENERATING_IMAGE, IMAGE_READY, GENERATING_VIDEO, VIDEO_READY, ERROR,
 * PROJECT_CREATED, REFERENCE_IMAGE_UPLOADED, PROFILE_UPDATED.
 */

(function (global) {
  'use strict';

  const STATUS_EVENTS = {
    QUEUED: 'QUEUED',
    GENERATING_IMAGE: 'GENERATING_IMAGE',
    IMAGE_READY: 'IMAGE_READY',
    GENERATING_VIDEO: 'GENERATING_VIDEO',
    VIDEO_READY: 'VIDEO_READY',
    ERROR: 'ERROR',
    PROJECT_CREATED: 'PROJECT_CREATED',
    REFERENCE_IMAGE_UPLOADED: 'REFERENCE_IMAGE_UPLOADED',
    PROFILE_UPDATED: 'PROFILE_UPDATED',
  };

  const FRIENDLY_ERROR_MESSAGES = {
    QUOTA_EXHAUSTED: 'Kuota akun Google ini telah habis atau sedang dibatasi. Silakan gunakan profil Chrome lain atau tunggu beberapa saat.',
    UNAUTHENTICATED: 'Sesi login Google Flow telah berakhir. Silakan login kembali di tab Google Flow Anda.',
    PERMISSION_DENIED: 'Akses ke fitur Google Flow ditolak untuk akun Google ini.',
    RATE_LIMITED: 'Terlalu banyak permintaan dalam waktu singkat. Sistem akan menunggu beberapa detik.',
    GENERATION_FAILED: 'Google Flow mengalami kendala saat memproses media. Silakan coba kembali.',
    SERVER_BUSY: 'Server Google Flow sedang sangat sibuk. Silakan tunggu beberapa saat.',
  };

  function isResourceId(str) {
    if (!str || typeof str !== 'string') return false;
    const t = str.trim();
    if (t.startsWith('http://') || t.startsWith('https://')) return false;
    if (
      t.startsWith('operations/') ||
      t.startsWith('projects/') ||
      t.startsWith('flowMedia/') ||
      t.startsWith('users/') ||
      t.startsWith('media/')
    ) {
      return true;
    }
    if (/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(t)) {
      return true;
    }
    return false;
  }

  function isMediaUrl(str) {
    if (!str || typeof str !== 'string') return false;
    const t = str.trim();
    if (!t.startsWith('http://') && !t.startsWith('https://')) return false;
    if (t.includes('recaptcha') || t.includes('google-analytics') || t.includes('play.google.com')) {
      return false;
    }
    return (
      t.includes('googleusercontent.com') ||
      t.includes('flow-content.google') ||
      t.includes('/flowMedia') ||
      t.includes('/media/') ||
      t.includes('/video/') ||
      t.includes('/image/') ||
      /\.(png|jpg|jpeg|webp|mp4|gif)($|\?)/i.test(t)
    );
  }

  function isVideoUrl(str) {
    if (!str || typeof str !== 'string') return false;
    return isMediaUrl(str) && (/\.mp4($|\?)/i.test(str) || str.includes('/video/') || str.includes('flow-content.google/video'));
  }

  function extractProjectIdFromUrl(url) {
    if (!url || typeof url !== 'string') return null;
    const match = url.match(/\/projects?\/([0-9a-fA-F-]{36}|[a-zA-Z0-9_-]{8,})/i) ||
                  url.match(/projectId=([0-9a-fA-F-]{36}|[a-zA-Z0-9_-]{8,})/i);
    return match ? match[1] : null;
  }

  function parseJsonSafe(text) {
    if (typeof text !== 'string') return text;
    try {
      return JSON.parse(text);
    } catch {
      return null;
    }
  }

  function unwrapRecursiveJson(val, maxDepth) {
    maxDepth = maxDepth || 4;
    let current = val;
    for (let i = 0; i < maxDepth; i++) {
      if (typeof current !== 'string') return current;
      const trimmed = current.trim();
      if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return current;
      try {
        const parsed = JSON.parse(trimmed);
        current = parsed;
      } catch {
        return current;
      }
    }
    return current;
  }

  /**
   * Decode Google Boq batchexecute response envelopes
   */
  function decodeBoqResponse(rawText) {
    if (!rawText || typeof rawText !== 'string') return [];
    let clean = rawText.trim();
    if (clean.startsWith(")]}'")) {
      clean = clean.slice(4).trim();
    }
    if (!clean) return [];

    const rpcResults = [];

    // Check if chunked format: length\n[[...]]
    if (/^\d+\s*\n/.test(clean)) {
      let pos = 0;
      while (pos < clean.length) {
        while (pos < clean.length && /\s/.test(clean[pos])) pos++;
        const newline = clean.indexOf('\n', pos);
        if (newline < 0) break;
        const sizeStr = clean.slice(pos, newline).trim();
        const size = parseInt(sizeStr, 10);
        if (isNaN(size) || size <= 0) break;
        pos = newline + 1;
        const chunk = clean.slice(pos, pos + size);
        pos += size;

        try {
          const parsedChunk = JSON.parse(chunk);
          if (Array.isArray(parsedChunk)) {
            for (const item of parsedChunk) {
              if (Array.isArray(item) && item[0] === 'wrb.fr') {
                const rpcId = item[1] || '';
                const rawPayload = item[2] ?? item[5];
                const unwrapped = unwrapRecursiveJson(rawPayload);
                rpcResults.push({ rpcId, data: unwrapped, raw: rawPayload });
              }
            }
          }
        } catch {
          // ignore malformed chunk
        }
      }
      if (rpcResults.length > 0) return rpcResults;
    }

    // Standard JSON array format or line-by-line fallback
    try {
      const parsed = JSON.parse(clean);
      if (Array.isArray(parsed)) {
        for (const item of parsed) {
          if (Array.isArray(item) && item[0] === 'wrb.fr') {
            const rpcId = item[1] || '';
            const rawPayload = item[2] ?? item[5];
            const unwrapped = unwrapRecursiveJson(rawPayload);
            rpcResults.push({ rpcId, data: unwrapped, raw: rawPayload });
          }
        }
      }
    } catch {
      // ignore
    }

    // Line-by-line fallback if chunk lengths were misaligned or mixed
    if (rpcResults.length === 0) {
      const lines = clean.split('\n');
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.includes('wrb.fr') && (trimmed.startsWith('[[') || trimmed.startsWith('["wrb.fr"'))) {
          try {
            const parsed = JSON.parse(trimmed);
            if (Array.isArray(parsed)) {
              for (const item of parsed) {
                if (Array.isArray(item) && item[0] === 'wrb.fr') {
                  const rpcId = item[1] || '';
                  const rawPayload = item[2] ?? item[5];
                  const unwrapped = unwrapRecursiveJson(rawPayload);
                  rpcResults.push({ rpcId, data: unwrapped, raw: rawPayload });
                }
              }
            }
          } catch {}
        }
      }
    }

    return rpcResults;
  }

  /**
   * Recursively scan any nested data object / array for asset URLs, operation IDs, and statuses
   */
  function deepScanPayload(node, accumulator, depth) {
    depth = depth || 0;
    if (depth > 12 || !node) return;

    if (typeof node === 'string') {
      const trimmed = node.trim();
      if (isVideoUrl(trimmed)) {
        accumulator.videoUrls.push(trimmed);
      } else if (isMediaUrl(trimmed)) {
        accumulator.imageUrls.push(trimmed);
      }
      if (isResourceId(trimmed)) {
        if (trimmed.startsWith('operations/')) {
          accumulator.operationIds.push(trimmed);
        } else if (trimmed.startsWith('flowMedia/') || trimmed.startsWith('media/')) {
          accumulator.mediaIds.push(trimmed);
        } else if (/^[0-9a-fA-F-]{36}$/.test(trimmed)) {
          accumulator.uuids.push(trimmed);
        }
      }
      return;
    }

    if (Array.isArray(node)) {
      for (const child of node) {
        deepScanPayload(child, accumulator, depth + 1);
      }
      return;
    }

    if (typeof node === 'object') {
      // Check object keys for project / media / operation / error fields
      if (node.projectId && typeof node.projectId === 'string') {
        accumulator.projectIds.push(node.projectId);
      }
      if (node.projectUuid && typeof node.projectUuid === 'string') {
        accumulator.projectIds.push(node.projectUuid);
      }
      if (node.mediaId && typeof node.mediaId === 'string') {
        accumulator.mediaIds.push(node.mediaId);
      }
      if (node.name && typeof node.name === 'string' && isResourceId(node.name)) {
        if (node.name.startsWith('operations/')) {
          accumulator.operationIds.push(node.name);
        } else {
          accumulator.mediaIds.push(node.name);
        }
      }
      if (node.fifeUrl && typeof node.fifeUrl === 'string') {
        if (isVideoUrl(node.fifeUrl)) {
          accumulator.videoUrls.push(node.fifeUrl);
        } else {
          accumulator.imageUrls.push(node.fifeUrl);
        }
      }
      if (node.url && typeof node.url === 'string') {
        if (isVideoUrl(node.url)) {
          accumulator.videoUrls.push(node.url);
        } else if (isMediaUrl(node.url)) {
          accumulator.imageUrls.push(node.url);
        }
      }
      if (node.done === true) {
        accumulator.isDone = true;
      }
      if (node.error) {
        accumulator.errors.push(node.error);
      }

      for (const val of Object.values(node)) {
        deepScanPayload(val, accumulator, depth + 1);
      }
    }
  }

  /**
   * Main Parser & Event Translator Function
   * @param {string} url - Request / response endpoint URL
   * @param {number} statusCode - HTTP response status code
   * @param {string|object} rawResponseText - Raw response text or parsed JSON
   * @param {object} [requestInfo] - Optional request metadata (method, headers, body, url)
   * @returns {object|null} Standardized translated event
   */
  function parseGoogleFlowResponse(url, statusCode, rawResponseText, requestInfo) {
    url = url || '';
    statusCode = Number(statusCode) || 200;
    requestInfo = requestInfo || {};

    const cleanText = typeof rawResponseText === 'string' ? rawResponseText : JSON.stringify(rawResponseText || '');

    // 1. Handle HTTP / API Error Status Codes
    if (statusCode >= 400) {
      let errorCode = 'API_ERROR';
      let friendlyMessage = FRIENDLY_ERROR_MESSAGES.GENERATION_FAILED;

      if (statusCode === 429 || cleanText.includes('RESOURCE_EXHAUSTED') || cleanText.includes('QUOTA_EXCEEDED') || cleanText.toLowerCase().includes('quota')) {
        errorCode = 'QUOTA_EXHAUSTED';
        friendlyMessage = FRIENDLY_ERROR_MESSAGES.QUOTA_EXHAUSTED;
      } else if (statusCode === 401 || cleanText.includes('UNAUTHENTICATED') || cleanText.includes('auth/session')) {
        errorCode = 'UNAUTHENTICATED';
        friendlyMessage = FRIENDLY_ERROR_MESSAGES.UNAUTHENTICATED;
      } else if (statusCode === 403 || cleanText.includes('PERMISSION_DENIED')) {
        errorCode = 'PERMISSION_DENIED';
        friendlyMessage = FRIENDLY_ERROR_MESSAGES.PERMISSION_DENIED;
      } else if (statusCode >= 500) {
        errorCode = 'SERVER_BUSY';
        friendlyMessage = FRIENDLY_ERROR_MESSAGES.SERVER_BUSY;
      }

      return {
        type: STATUS_EVENTS.ERROR,
        status: STATUS_EVENTS.ERROR,
        statusCode,
        errorCode,
        friendlyMessage,
        rawError: cleanText.slice(0, 1000),
        url,
        timestamp: Date.now(),
      };
    }

    // 2. Check for Boq batchexecute responses
    const isBatchexecute = url.includes('batchexecute') || cleanText.includes('wrb.fr');
    if (isBatchexecute) {
      const rpcList = decodeBoqResponse(cleanText);
      if (rpcList.length > 0) {
        for (const rpc of rpcList) {
          const rpcId = rpc.rpcId;
          const rpcData = rpc.data;

          const acc = {
            projectIds: [],
            mediaIds: [],
            operationIds: [],
            uuids: [],
            imageUrls: [],
            videoUrls: [],
            errors: [],
            isDone: false,
          };
          deepScanPayload(rpcData, acc);

          // Check if RPC contained errors
          if (acc.errors.length > 0) {
            const errStr = JSON.stringify(acc.errors);
            const isQuota = errStr.includes('RESOURCE_EXHAUSTED') || errStr.toLowerCase().includes('quota');
            return {
              type: STATUS_EVENTS.ERROR,
              status: STATUS_EVENTS.ERROR,
              rpcId,
              errorCode: isQuota ? 'QUOTA_EXHAUSTED' : 'GENERATION_FAILED',
              friendlyMessage: isQuota ? FRIENDLY_ERROR_MESSAGES.QUOTA_EXHAUSTED : FRIENDLY_ERROR_MESSAGES.GENERATION_FAILED,
              rawError: errStr.slice(0, 500),
              timestamp: Date.now(),
            };
          }

          // Credits balance Boq RPC (nzlxg)
          if (rpcId === 'nzlxg' || url.includes('nzlxg')) {
            let foundCredits = null;
            if (Array.isArray(rpcData) && typeof rpcData[0] === 'number') {
              foundCredits = String(rpcData[0]);
            } else if (typeof rpcData === 'number') {
              foundCredits = String(rpcData);
            }
            if (foundCredits !== null) {
              return {
                type: STATUS_EVENTS.PROFILE_UPDATED,
                status: STATUS_EVENTS.PROFILE_UPDATED,
                credits: foundCredits,
                rpcId: 'nzlxg',
                url,
                timestamp: Date.now(),
              };
            }
          }

          // Image generation Boq RPC (ogiZ0b)
          if (rpcId === 'ogiZ0b' || url.includes('ogiZ0b')) {
            if (acc.imageUrls.length > 0 || acc.mediaIds.length > 0) {
              return {
                type: STATUS_EVENTS.IMAGE_READY,
                status: STATUS_EVENTS.IMAGE_READY,
                rpcId: 'ogiZ0b',
                images: (acc.imageUrls.length > 0 ? acc.imageUrls : acc.mediaIds).map((urlOrId, i) => ({
                  id: acc.mediaIds[i] || `img_${i}`,
                  url: acc.imageUrls[i] || '',
                  mediaId: acc.mediaIds[i] || null,
                })),
                mediaIds: acc.mediaIds,
                imageUrls: acc.imageUrls,
                timestamp: Date.now(),
              };
            }
            return {
              type: STATUS_EVENTS.GENERATING_IMAGE,
              status: STATUS_EVENTS.GENERATING_IMAGE,
              rpcId: 'ogiZ0b',
              timestamp: Date.now(),
            };
          }

          // Video generation Boq RPC (nTa, eb1hJf, YhhmEf)
          if (['nTa', 'eb1hJf', 'YhhmEf'].includes(rpcId) || url.includes('nTa') || url.includes('eb1hJf') || url.includes('YhhmEf')) {
            if (acc.videoUrls.length > 0) {
              return {
                type: STATUS_EVENTS.VIDEO_READY,
                status: STATUS_EVENTS.VIDEO_READY,
                rpcId,
                videos: acc.videoUrls.map((vUrl, i) => ({
                  id: acc.operationIds[i] || acc.mediaIds[i] || `vid_${i}`,
                  url: vUrl,
                  downloadUrl: vUrl,
                })),
                videoUrls: acc.videoUrls,
                operationIds: acc.operationIds,
                timestamp: Date.now(),
              };
            }
            if (acc.operationIds.length > 0) {
              return {
                type: STATUS_EVENTS.QUEUED,
                status: STATUS_EVENTS.QUEUED,
                kind: 'video',
                rpcId,
                operationIds: acc.operationIds,
                timestamp: Date.now(),
              };
            }
            return {
              type: STATUS_EVENTS.GENERATING_VIDEO,
              status: STATUS_EVENTS.GENERATING_VIDEO,
              rpcId,
              timestamp: Date.now(),
            };
          }

          // Video Status Polling Boq RPC (jwpduf)
          if (rpcId === 'jwpduf' || url.includes('jwpduf')) {
            if (acc.videoUrls.length > 0) {
              return {
                type: STATUS_EVENTS.VIDEO_READY,
                status: STATUS_EVENTS.VIDEO_READY,
                rpcId: 'jwpduf',
                videos: acc.videoUrls.map((vUrl, i) => ({
                  id: acc.operationIds[i] || `vid_${i}`,
                  url: vUrl,
                  downloadUrl: vUrl,
                })),
                videoUrls: acc.videoUrls,
                operationIds: acc.operationIds,
                timestamp: Date.now(),
              };
            }
            return {
              type: STATUS_EVENTS.GENERATING_VIDEO,
              status: STATUS_EVENTS.GENERATING_VIDEO,
              rpcId: 'jwpduf',
              operationIds: acc.operationIds,
              timestamp: Date.now(),
            };
          }

          // Signed CDN Download resolution Boq RPC (as29s)
          if (rpcId === 'as29s' || url.includes('as29s')) {
            if (acc.videoUrls.length > 0) {
              return {
                type: STATUS_EVENTS.VIDEO_READY,
                status: STATUS_EVENTS.VIDEO_READY,
                rpcId: 'as29s',
                videos: acc.videoUrls.map((vUrl, i) => ({
                  id: acc.mediaIds[i] || `vid_${i}`,
                  url: vUrl,
                  downloadUrl: vUrl,
                })),
                videoUrls: acc.videoUrls,
                timestamp: Date.now(),
              };
            }
          }
        }
      }
    }

    // 3. Handle Standard REST JSON APIs
    const jsonParsed = parseJsonSafe(cleanText);
    const acc = {
      projectIds: [],
      mediaIds: [],
      operationIds: [],
      uuids: [],
      imageUrls: [],
      videoUrls: [],
      errors: [],
      isDone: false,
    };
    if (jsonParsed) {
      deepScanPayload(jsonParsed, acc);
    }

    // Check for inline error objects
    if (acc.errors.length > 0) {
      const errStr = JSON.stringify(acc.errors);
      const isQuota = errStr.includes('RESOURCE_EXHAUSTED') || errStr.toLowerCase().includes('quota');
      return {
        type: STATUS_EVENTS.ERROR,
        status: STATUS_EVENTS.ERROR,
        errorCode: isQuota ? 'QUOTA_EXHAUSTED' : 'GENERATION_FAILED',
        friendlyMessage: isQuota ? FRIENDLY_ERROR_MESSAGES.QUOTA_EXHAUSTED : FRIENDLY_ERROR_MESSAGES.GENERATION_FAILED,
        rawError: errStr.slice(0, 500),
        url,
        timestamp: Date.now(),
      };
    }

    // 3.0 Profile / Credits / Session Auth Interception
    if (
      url.includes('/fx/api/credits') ||
      url.includes('/fx/api/auth/session') ||
      url.includes('/api/auth/session') ||
      url.includes('/fx/api/user') ||
      (jsonParsed && (jsonParsed.user?.email || jsonParsed.credits !== undefined || jsonParsed.remainingCredits !== undefined || jsonParsed.session?.user?.email))
    ) {
      let detectedEmail = '';
      let detectedCredits = '';

      if (jsonParsed) {
        if (jsonParsed.user?.email) detectedEmail = jsonParsed.user.email;
        else if (jsonParsed.session?.user?.email) detectedEmail = jsonParsed.session.user.email;
        else if (jsonParsed.email) detectedEmail = jsonParsed.email;

        if (jsonParsed.credits !== undefined) detectedCredits = String(jsonParsed.credits);
        else if (jsonParsed.remainingCredits !== undefined) detectedCredits = String(jsonParsed.remainingCredits);
        else if (jsonParsed.userCredits !== undefined) detectedCredits = String(jsonParsed.userCredits);
        else if (jsonParsed.session?.user?.credits !== undefined) detectedCredits = String(jsonParsed.session.user.credits);
      }

      if (!detectedEmail) {
        const emMatch = cleanText.match(/"email"\s*:\s*"([^"]+@[^"]+)"/i) || cleanText.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/i);
        if (emMatch) detectedEmail = emMatch[1] || emMatch[0];
      }

      if (!detectedCredits) {
        const crMatch = cleanText.match(/"(?:credits|remainingCredits|balance|creditCount|totalCredits|userCredits)"\s*:\s*(\d+)/i);
        if (crMatch) detectedCredits = crMatch[1];
      }

      if (detectedEmail || detectedCredits) {
        return {
          type: STATUS_EVENTS.PROFILE_UPDATED,
          status: STATUS_EVENTS.PROFILE_UPDATED,
          email: detectedEmail || undefined,
          credits: detectedCredits || undefined,
          url,
          timestamp: Date.now(),
        };
      }
    }

    // 3A. Project Creation / Project URL Navigation
    if (
      url.includes('project.createProject') ||
      url.includes('/fx/api/trpc/project') ||
      (url.includes('/project/') && /flow\.google\.com\/project\/[0-9a-fA-F-]{36}/i.test(url))
    ) {
      const foundProjectId = acc.projectIds[0] || extractProjectIdFromUrl(url) || acc.uuids[0];
      if (foundProjectId) {
        return {
          type: STATUS_EVENTS.PROJECT_CREATED,
          status: STATUS_EVENTS.PROJECT_CREATED,
          projectId: foundProjectId,
          url,
          timestamp: Date.now(),
        };
      }
    }

    // 3B. Reference Image Upload
    if (
      url.includes('/upload/') ||
      url.includes('/flowMedia:upload') ||
      url.includes('/file/upload') ||
      url.includes('/media/upload')
    ) {
      const mediaId = acc.mediaIds[0] || (jsonParsed && (jsonParsed.name || jsonParsed.mediaId || jsonParsed.id));
      if (mediaId || acc.imageUrls.length > 0) {
        return {
          type: STATUS_EVENTS.REFERENCE_IMAGE_UPLOADED,
          status: STATUS_EVENTS.REFERENCE_IMAGE_UPLOADED,
          mediaId: typeof mediaId === 'string' ? mediaId : (acc.mediaIds[0] || null),
          url: acc.imageUrls[0] || null,
          timestamp: Date.now(),
        };
      }
    }

    // 3C. Image Generation REST endpoint
    if (url.includes('flowMedia:batchGenerateImages') || url.includes('/generateImages') || url.includes('batchGenerateImages')) {
      if (acc.imageUrls.length > 0 || (jsonParsed && Array.isArray(jsonParsed.media) && jsonParsed.media.length > 0)) {
        const images = [];
        if (jsonParsed && Array.isArray(jsonParsed.media)) {
          for (const item of jsonParsed.media) {
            const gen = item.image?.generatedImage || item.generatedImage || {};
            const itemUrl = gen.fifeUrl || gen.url || item.url || '';
            const itemId = item.name || gen.mediaGenerationId || item.id || `img_${images.length}`;
            images.push({ id: itemId, url: itemUrl, mediaId: itemId });
          }
        } else {
          for (let i = 0; i < acc.imageUrls.length; i++) {
            images.push({
              id: acc.mediaIds[i] || `img_${i}`,
              url: acc.imageUrls[i],
              mediaId: acc.mediaIds[i] || null,
            });
          }
        }
        return {
          type: STATUS_EVENTS.IMAGE_READY,
          status: STATUS_EVENTS.IMAGE_READY,
          images,
          mediaIds: images.map(img => img.id),
          imageUrls: images.map(img => img.url).filter(Boolean),
          timestamp: Date.now(),
        };
      }
      return {
        type: STATUS_EVENTS.GENERATING_IMAGE,
        status: STATUS_EVENTS.GENERATING_IMAGE,
        timestamp: Date.now(),
      };
    }

    // 3D. Video Generation REST endpoint or Operations Polling
    if (
      url.includes('flowMedia:batchGenerateVideos') ||
      url.includes('batchAsyncGenerateVideoStartImage') ||
      url.includes('/operations/') ||
      url.includes('batchGenerateVideos')
    ) {
      if (acc.videoUrls.length > 0) {
        return {
          type: STATUS_EVENTS.VIDEO_READY,
          status: STATUS_EVENTS.VIDEO_READY,
          videos: acc.videoUrls.map((vUrl, i) => ({
            id: acc.operationIds[i] || acc.mediaIds[i] || `vid_${i}`,
            url: vUrl,
            downloadUrl: vUrl,
          })),
          videoUrls: acc.videoUrls,
          operationIds: acc.operationIds,
          timestamp: Date.now(),
        };
      }

      if (acc.operationIds.length > 0) {
        if (url.includes('/operations/')) {
          return {
            type: STATUS_EVENTS.GENERATING_VIDEO,
            status: STATUS_EVENTS.GENERATING_VIDEO,
            operationIds: acc.operationIds,
            timestamp: Date.now(),
          };
        }
        return {
          type: STATUS_EVENTS.QUEUED,
          status: STATUS_EVENTS.QUEUED,
          kind: 'video',
          operationIds: acc.operationIds,
          timestamp: Date.now(),
        };
      }

      return {
        type: STATUS_EVENTS.GENERATING_VIDEO,
        status: STATUS_EVENTS.GENERATING_VIDEO,
        timestamp: Date.now(),
      };
    }

    return null;
  }

  function generateBoqUuid() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function buildBoqClientContext(projectId = '', recaptchaToken = '') {
    const recaptchaProto = recaptchaToken ? [recaptchaToken, 1] : null;
    return [null, 22, null, null, null, projectId, null, null, null, null, recaptchaProto];
  }

  function buildBoqUploadImagePayload(params) {
    params = params || {};
    const projectId = params.projectId || '';
    const clientContext = buildBoqClientContext(projectId, params.recaptchaToken);
    const uuid1 = params.uuid1 || generateBoqUuid().toUpperCase();
    const uuid2 = params.uuid2 || generateBoqUuid().toUpperCase();

    return [
      clientContext,
      params.base64Data,
      params.mimeType || 'image/png',
      1,
      null,
      null,
      null,
      null,
      params.fileName || 'reference.png',
      null,
      uuid1,
      uuid2,
    ];
  }

  function parseBoqUploadImageResponse(rawResponse, defaultName = 'reference.png', fallbackMediaId = '', fallbackProjectId = '') {
    if (!rawResponse && !fallbackMediaId) {
      throw new Error('Upload image response is empty or null');
    }

    let mediaId = '';
    let displayName = defaultName;
    let projectId = fallbackProjectId || '';
    let imageUrl = '';

    if (typeof rawResponse === 'object' && rawResponse !== null) {
      const obj = rawResponse;
      if (obj.mediaId) mediaId = String(obj.mediaId);
      else if (obj.name) mediaId = String(obj.name);
      else if (obj.id) mediaId = String(obj.id);
      else if (obj.media && typeof obj.media === 'object') {
        const m = obj.media;
        mediaId = String(m.name || m.mediaId || m.id || '');
      }

      if (obj.imageUrl) imageUrl = String(obj.imageUrl);
      if (obj.displayName) displayName = String(obj.displayName);
      if (obj.projectId) projectId = String(obj.projectId);
    }

    if (!mediaId && Array.isArray(rawResponse)) {
      function findMediaIdInArray(arr) {
        for (const item of arr) {
          if (typeof item === 'string') {
            const t = item.trim();
            if (
              t.startsWith('flowMedia/') ||
              t.startsWith('users/') ||
              t.startsWith('projects/') ||
              t.startsWith('media/') ||
              /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(t) ||
              /^[a-zA-Z0-9_-]{20,}$/.test(t)
            ) {
              return t;
            }
          } else if (Array.isArray(item)) {
            const found = findMediaIdInArray(item);
            if (found) return found;
          }
        }
        return '';
      }
      mediaId = findMediaIdInArray(rawResponse);
    }

    if (!imageUrl && Array.isArray(rawResponse)) {
      function findImageUrlInArray(arr) {
        for (const item of arr) {
          if (typeof item === 'string' && isMediaUrl(item)) {
            return item;
          }
          if (Array.isArray(item)) {
            const found = findImageUrlInArray(item);
            if (found) return found;
          }
        }
        return '';
      }
      imageUrl = findImageUrlInArray(rawResponse);
    }

    if (!mediaId && typeof rawResponse === 'string') {
      mediaId = rawResponse.trim();
    }

    if (!mediaId && fallbackMediaId) {
      mediaId = fallbackMediaId;
    }

    if (!mediaId) {
      throw new Error(`Failed to parse mediaId from upload response: ${JSON.stringify(rawResponse).slice(0, 300)}`);
    }

    return {
      mediaId,
      mediaName: mediaId,
      projectId: projectId || fallbackProjectId,
      displayName,
      imageUrl: imageUrl || '',
    };
  }

  function buildBoqStructuredPrompt(promptText = '') {
    return [[[promptText || '']]];
  }

  function buildBoqImagePayload(params) {
    params = params || {};
    const count = Math.max(1, Math.min(8, Number(params.count || 1)));
    const aspectRatio = params.aspectRatio ?? 2; // 2 = 9:16 portrait, 3 = 16:9 landscape, 1 = 1:1 square
    const seed = params.seed ?? Math.floor(1000000000 + Math.random() * 900000000);
    const projectId = params.projectId || '';
    const clientContext = buildBoqClientContext(projectId, params.recaptchaToken);
    const structuredPrompt = [[[params.prompt || '']]];
    const batchUuid = generateBoqUuid().toUpperCase();

    const imageInputs = params.referenceMediaIds && params.referenceMediaIds.length > 0
      ? params.referenceMediaIds.map((id) => [String(id).replace(/^asset-/, '').trim(), null, null, null, 1])
      : null;

    const requests = Array.from({ length: count }, (_, i) => [
      null,
      null,
      imageInputs,
      seed + i,
      aspectRatio,
      'NARWHAL',
      null,
      clientContext,
      structuredPrompt,
      null,
      null,
      null,
      generateBoqUuid().toUpperCase(),
      generateBoqUuid().toUpperCase(),
    ]);

    return [null, requests, 1, clientContext, [batchUuid]];
  }

  function buildBoqVideoPayload(params) {
    params = params || {};
    const count = Math.max(1, Math.min(4, Number(params.count || 1)));
    const aspectRatio = params.aspectRatio ?? 1; // 1 = 9:16 portrait, 2 = 16:9 landscape, 0 = 1:1 square
    const structuredPrompt = [null, null, [[[params.prompt || '']]]];
    const clientContext = buildBoqClientContext(params.projectId || '', params.recaptchaToken);
    const batchUuid = generateBoqUuid().toUpperCase();

    const cleanStartImageMediaId = params.startImageMediaId
      ? params.startImageMediaId.replace(/^asset-/, '').trim()
      : undefined;

    const requests = Array.from({ length: count }, () => {
      const metadata = [
        null,
        null,
        null,
        null,
        generateBoqUuid().toUpperCase(),
        generateBoqUuid().toUpperCase(),
      ];
      if (cleanStartImageMediaId) {
        return [
          structuredPrompt,
          params.modelKey || 'abra_i2v_8s',
          aspectRatio,
          null,
          [null, cleanStartImageMediaId],
          metadata,
        ];
      }
      return [
        structuredPrompt,
        params.modelKey || 'abra_t2v_8s',
        aspectRatio,
        null,
        metadata,
      ];
    });

    return [requests, clientContext, [batchUuid, count]];
  }

  function buildBoqCheckStatusPayload(operationNames) {
    operationNames = Array.isArray(operationNames) ? operationNames : [operationNames];
    return [null, null, operationNames.map((op) => [String(op).replace(/^asset-/, '').trim()])];
  }

  function parseBoqVideoGenResponse(rawResponse, prompt = '') {
    if (!rawResponse) return [];
    const assets = [];

    if (typeof rawResponse === 'object' && rawResponse !== null && !Array.isArray(rawResponse)) {
      const root = rawResponse;
      const media = Array.isArray(root.media) ? root.media : [];
      for (const [index, item] of media.entries()) {
        const id = String(item.name || item.mediaId || item.id || `gen_asset_${Date.now()}_${index}`);
        const url = String(item.videoUrl || item.imageUrl || item.url || item.downloadUrl || '');
        const isVid = isVideoUrl(url) || item.videoMetadata !== undefined;
        assets.push({
          id,
          type: isVid ? 'video' : 'image',
          prompt: prompt || String(item.prompt || ''),
          url,
          downloadUrl: url,
          mediaId: id,
          status: 'COMPLETED',
          progress: 100,
          raw: item,
        });
      }
      if (assets.length) return assets;
    }

    if (Array.isArray(rawResponse)) {
      const discoveredMediaIds = [];
      const discoveredUrls = [];
      const discoveredOperations = [];

      function walk(val) {
        if (!val) return;
        if (typeof val === 'string') {
          const t = val.trim();
          if (isVideoUrl(t) || isMediaUrl(t)) {
            if (!discoveredUrls.includes(t)) discoveredUrls.push(t);
          } else if (t.startsWith('operations/') || t.startsWith('projects/') && t.includes('/operations/')) {
            if (!discoveredOperations.includes(t)) discoveredOperations.push(t);
          } else if (isResourceId(t)) {
            if (!discoveredMediaIds.includes(t)) discoveredMediaIds.push(t);
          }
        } else if (Array.isArray(val)) {
          for (const item of val) walk(item);
        } else if (typeof val === 'object') {
          for (const k of Object.keys(val)) walk(val[k]);
        }
      }

      walk(rawResponse);

      const count = Math.max(discoveredUrls.length, discoveredMediaIds.length, discoveredOperations.length, 1);
      for (let i = 0; i < count; i++) {
        const url = discoveredUrls[i] || '';
        const id = discoveredMediaIds[i] || discoveredOperations[i] || `boq_gen_${Date.now()}_${i}`;
        const isVid = isVideoUrl(url) || (!url && discoveredOperations[i]);
        assets.push({
          id,
          type: isVid ? 'video' : 'image',
          prompt,
          url,
          downloadUrl: url,
          mediaId: id,
          operationName: discoveredOperations[i] || undefined,
          status: url ? 'COMPLETED' : 'PENDING',
          progress: url ? 100 : 0,
        });
      }
    }

    return assets;
  }

  const exportObj = {
    STATUS_EVENTS,
    FRIENDLY_ERROR_MESSAGES,
    parseGoogleFlowResponse,
    decodeBoqResponse,
    extractProjectIdFromUrl,
    isResourceId,
    isMediaUrl,
    isVideoUrl,
    generateBoqUuid,
    buildBoqClientContext,
    buildBoqStructuredPrompt,
    buildBoqUploadImagePayload,
    buildBoqImagePayload,
    buildBoqVideoPayload,
    buildBoqCheckStatusPayload,
    parseBoqUploadImageResponse,
    parseBoqVideoGenResponse,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { FlowNetworkParser: exportObj };
  } else if (typeof window !== 'undefined') {
    window.FlowNetworkParser = exportObj;
  } else if (typeof globalThis !== 'undefined') {
    globalThis.FlowNetworkParser = exportObj;
  }
})(typeof globalThis !== 'undefined' ? globalThis : typeof self !== 'undefined' ? self : this);
