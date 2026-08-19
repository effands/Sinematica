(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FlowMediaCapture = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const MEDIA_ID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

  function buildSniffCallback(callbackUrl, message) {
    return {
      endpoint: callbackUrl,
      payload: {
        type: 'sniffed_video_request',
        url: message.url,
        method: message.method,
        ...(message.payload !== undefined ? { payload: message.payload } : {}),
        ...(message.timestamp !== undefined ? { timestamp: message.timestamp } : {}),
      },
    };
  }

  function isVideoUrl(url) {
    return /(?:\/video\/|\.mp4(?:[?#]|$)|googlevideo\.com|storage\.googleapis\.com)/i.test(url || '');
  }

  function mediaEntryFromResponse({ requestUrl = '', responseUrl = '', contentType = '' }) {
    const url = responseUrl || requestUrl;
    if (!/^video\//i.test(contentType) && !isVideoUrl(url)) return null;
    const match = requestUrl.match(MEDIA_ID) || url.match(MEDIA_ID);
    return { mediaId: match ? match[0] : 'latest-video', mediaType: 'video', url };
  }

  function mediaEntryFromResourceUrl(url) {
    return mediaEntryFromResponse({ responseUrl: url });
  }

  function mediaEntryFromWebRequest(details) {
    const contentType = (details.responseHeaders || [])
      .find((header) => String(header.name).toLowerCase() === 'content-type')?.value || '';
    return mediaEntryFromResponse({
      requestUrl: details.url || '',
      responseUrl: details.url || '',
      contentType,
    });
  }

  function findWorkflowForMedia(bodyText, mediaId) {
    try {
      const parsed = typeof bodyText === 'string' ? JSON.parse(bodyText) : bodyText;
      const media = parsed?.result?.data?.json?.projectContents?.media || [];
      const match = media.find((item) => item?.name === mediaId && item?.workflowId);
      if (!match) return null;
      return { projectId: match.projectId, workflowId: match.workflowId };
    } catch {
      return null;
    }
  }

  function buildFlowEditorUrl(projectId, workflowId) {
    return `https://labs.google/fx/tools/flow/project/${encodeURIComponent(projectId)}/edit/${encodeURIComponent(workflowId)}`;
  }

  return {
    buildSniffCallback,
    mediaEntryFromResponse,
    mediaEntryFromResourceUrl,
    mediaEntryFromWebRequest,
    findWorkflowForMedia,
    buildFlowEditorUrl,
  };
});
