function shouldRetryFlowAuth(status, attempt) {
  return Number(status) === 401 && Number(attempt) === 0;
}

function isFlowLoginUrl(url) {
  const value = String(url || '');
  return value.startsWith('https://accounts.google.com/') &&
    (value.includes('app_domain=https%3A%2F%2Flabs.google') ||
     value.includes('redirect_uri=https%3A%2F%2Flabs.google') ||
     value.includes('app_domain=https%3A%2F%2Fflow.google.com') ||
     value.includes('redirect_uri=https%3A%2F%2Fflow.google.com'));
}

if (typeof module !== 'undefined') module.exports = { shouldRetryFlowAuth, isFlowLoginUrl };
