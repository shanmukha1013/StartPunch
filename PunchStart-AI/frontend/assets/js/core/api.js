// API client. Same-origin `/api` by default; a <meta name="startpunch-api"> tag can point to a separate backend.
const meta = document.querySelector('meta[name="startpunch-api"]');
const BASE = (meta?.content || '').replace(/\/$/, '');
const CROSS_ORIGIN = Boolean(BASE);

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export async function api(path, { method = 'GET', body, raw, headers = {}, timeout = 65000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const init = {
    method,
    headers: { 'X-StartPunch-Client': 'web', ...headers },
    credentials: CROSS_ORIGIN ? 'include' : 'same-origin',
    signal: controller.signal,
  };
  if (raw !== undefined) {
    init.body = raw;
  } else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(`${BASE}/api${path}`, init);
  } catch (error) {
    clearTimeout(timer);
    if (error.name === 'AbortError') throw new ApiError('The request took too long. Please try again.', 0);
    throw new ApiError('Network error — check your connection and try again.', 0);
  }
  clearTimeout(timer);
  const type = response.headers.get('content-type') || '';
  const data = type.includes('application/json') ? await response.json().catch(() => ({})) : await response.text();
  if (!response.ok) {
    if ((response.status === 404 || response.status === 405) && !type.includes('application/json')) {
      // No API behind this deployment yet (e.g. the server is still being configured).
      throw new ApiError('StartPunch is being set up — accounts and analysis will be available shortly.', 503);
    }
    const message = (data && data.detail) || `Request failed (${response.status}).`;
    throw new ApiError(typeof message === 'string' ? message : 'Request failed.', response.status, data);
  }
  return data;
}

export const get = (path) => api(path);
export const post = (path, body) => api(path, { method: 'POST', body: body ?? {} });
export const patch = (path, body) => api(path, { method: 'PATCH', body });
export const del = (path, body) => api(path, { method: 'DELETE', body });
export const apiUrl = (path) => `${BASE}/api${path}`;
export const mediaSrc = (url) => (url ? `${BASE}${url}` : '');

export async function uploadImage(file) {
  if (!file) return null;
  if (!/^image\/(png|jpeg|gif|webp)$/.test(file.type)) throw new ApiError('Use a PNG, JPEG, GIF or WebP image.', 415);
  if (file.size > 3 * 1024 * 1024) throw new ApiError('Images must be smaller than 3 MB.', 413);
  return api('/media', { method: 'POST', raw: file, headers: { 'Content-Type': file.type } });
}
