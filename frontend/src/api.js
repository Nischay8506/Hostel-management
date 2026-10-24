// One API origin for public pages, authenticated requests, and downloads.
export function resolveApiBase(value = '/api', production = false) {
  const base = String(value || '/api').trim().replace(/\/+$/, '');
  if (base === '/api') return base;
  let url;
  try { url = new URL(base); } catch { throw new Error('VITE_API_BASE_URL must be /api or an HTTPS API URL ending in /api.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || !url.pathname.endsWith('/api'))
    throw new Error('VITE_API_BASE_URL must identify the API, without credentials, query parameters or fragments.');
  if (production && (url.protocol !== 'https:' || /^(localhost|127\.|0\.0\.0\.0|\[::1\])/.test(url.hostname)))
    throw new Error('Production API requests require a public HTTPS backend.');
  return base;
}

const environment = import.meta.env || {};
export const API_BASE_URL = resolveApiBase(environment.VITE_API_BASE_URL, environment.PROD);
export const resourcePaths = {
  branches: '/managed-branches', branchAdmins: '/branch-admins',
  gatePasses: '/gate-passes', feePlans: '/fee-plans', complaintAssignees: '/complaint-assignees',
  availableRooms: '/my/available-rooms', notifications: '/my/notifications',
};

export async function apiFetch(path, options = {}) {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Invalid API path.');
  let response;
  try {
    response = await fetch(API_BASE_URL + path, {...options, signal: options.signal || AbortSignal.timeout(20000)});
  } catch (error) {
    if (error.name === 'AbortError' && options.signal) throw error;
    throw new Error('We could not connect to Cityhive. Please try again shortly.');
  }
  const type = response.headers.get('content-type') || '';
  if (type.includes('text/html')) throw new Error('Cityhive online services are temporarily unavailable. Please try again later.');
  if (!response.ok) {
    let body = {};
    if (type.includes('application/json')) { try { body = await response.json(); } catch {} }
    const detail = Array.isArray(body.detail) ? body.detail.map(e => `${e.loc?.at(-1) || 'Field'}: ${e.msg}`).join('; ') : body.detail;
    const error = new Error(typeof detail === 'string' ? detail : 'The request could not be completed. Please try again.');
    error.status = response.status;
    throw error;
  }
  return response;
}

export async function apiJson(path, options = {}) {
  const response = await apiFetch(path, options);
  if (!response.headers.get('content-type')?.includes('application/json'))
    throw new Error('Cityhive returned an unexpected response. Please try again later.');
  return response.json();
}
