// Small DOM toolkit: escaping, element builder, icons, toasts, modals, formatting.

export const esc = (value) => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

/** Tagged template that escapes interpolations unless wrapped with raw(). */
const RAW = Symbol('raw');
export const raw = (html) => ({ [RAW]: true, html: String(html ?? '') });
export function html(strings, ...values) {
  let out = '';
  strings.forEach((s, i) => {
    out += s;
    if (i < values.length) {
      const v = values[i];
      if (v && v[RAW]) out += v.html;
      else if (Array.isArray(v)) out += v.map((x) => (x && x[RAW] ? x.html : esc(x))).join('');
      else if (v !== false && v !== null && v !== undefined) out += esc(v);
    }
  });
  return raw(out);
}
export const render = (el, tpl) => { el.innerHTML = tpl && tpl[RAW] ? tpl.html : String(tpl ?? ''); return el; };
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const P = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
  feed: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 9h10M7 13h10M7 17h6"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14a6 6 0 0 1 3.5 6"/>',
  community: '<circle cx="12" cy="7" r="3"/><circle cx="5" cy="17" r="3"/><circle cx="19" cy="17" r="3"/><path d="M9.5 9.5 7 14.5M14.5 9.5 17 14.5M8 17h8"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  sparkles: '<path d="M12 3l1.8 4.6L18.5 9.5l-4.7 1.9L12 16l-1.8-4.6L5.5 9.5l4.7-1.9z"/><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  heart: '<path d="M12 20s-7.5-4.6-9.2-9.4A4.9 4.9 0 0 1 12 6.3a4.9 4.9 0 0 1 9.2 4.3C19.5 15.4 12 20 12 20z"/>',
  comment: '<path d="M4 5h16v11H9l-5 4z"/>',
  repeat: '<path d="M17 2l3 3-3 3"/><path d="M4 11V9a4 4 0 0 1 4-4h12"/><path d="M7 22l-3-3 3-3"/><path d="M20 13v2a4 4 0 0 1-4 4H4"/>',
  bookmark: '<path d="M6 3h12v18l-6-4.5L6 21z"/>',
  share: '<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4"/>',
  flag: '<path d="M5 21V4M5 4h12l-2 4 2 4H5"/>',
  more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
  logout: '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  rocket: '<path d="M5 15c-1.5 1.3-2 4-2 6 2 0 4.7-.5 6-2"/><path d="M9 15 6.5 12.5C8 8 11.5 3.5 20.5 3.5 20.5 12.5 16 16 11.5 17.5z"/><circle cx="15" cy="9" r="1.6"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.3"/>',
  shield: '<path d="M12 3 4.5 6v6c0 4.4 3.2 7.8 7.5 9 4.3-1.2 7.5-4.6 7.5-9V6z"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  trending: '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5L6 20"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="m16 10 5-3v10l-5-3"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  send: '<path d="M21 3 3 10.5l7 2.5 2.5 7z"/><path d="m10 13 4-4"/>',
  star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
  database: '<ellipse cx="12" cy="5.5" rx="8" ry="2.5"/><path d="M4 5.5v13c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-13"/><path d="M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17.5v.5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M4 20h16"/>',
  print: '<path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/>',
  userplus: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M19 8v6M16 11h6"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.5 5.6 3.5 9S14.5 18.3 12 21c-2.5-2.7-3.5-5.6-3.5-9S9.5 5.7 12 3z"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  compare: '<path d="M8 3v18M16 3v18M3 8h5M16 16h5"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  punch: '<path d="M7 11V6.5a1.5 1.5 0 0 1 3 0V10m0-4a1.5 1.5 0 0 1 3 0v4m0-3a1.5 1.5 0 0 1 3 0v4m0-2a1.5 1.5 0 0 1 3 0v4.5a6.5 6.5 0 0 1-6.5 6.5h-1A6.5 6.5 0 0 1 5 15.5V13a2 2 0 0 1 2-2"/>',
};

export const icon = (name, cls = '') =>
  raw(`<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || P.info}</svg>`);

export const brandMark = () => raw(`<span class="brand-mark">${icon('punch').html}</span>`);

export function initials(name) {
  return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
}

export function avatar(user, size = '') {
  const cls = `avatar ${size ? `avatar--${size}` : ''}`;
  if (user?.avatar_url) return html`<span class="${cls}"><img src="${user.avatar_url}" alt="" loading="lazy"></span>`;
  return html`<span class="${cls}" aria-hidden="true">${initials(user?.name)}</span>`;
}

export function person(user, sub) {
  if (!user) return html`<span class="person muted">Deleted member</span>`;
  return html`<a class="person" href="profile.html?u=${encodeURIComponent(user.handle)}">${avatar(user)}<span class="person-meta"><strong>${user.name}</strong><span>${sub ?? (user.headline || `@${user.handle}`)}</span></span></a>`;
}

// ---------------------------------------------------------------- formatting
export function timeAgo(value) {
  if (!value) return '';
  const date = new Date(value);
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 45) return 'just now';
  const units = [[60, 'min'], [24, 'h'], [7, 'd']];
  let amount = seconds / 60;
  for (const [limit, label] of units) {
    if (amount < limit) return `${Math.floor(amount)}${label === 'min' ? ' min' : label} ago`;
    amount /= limit;
  }
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: date.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
}
export const fmtDate = (value) => (value ? new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '');
export const num = (n) => (n == null ? '—' : Number(n).toLocaleString());
export const compact = (n) => (n == null ? '—' : Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(n));
export const titleCase = (s) => String(s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/** Linkify URLs and hashtags in already-escaped text. */
export function richText(text) {
  const escaped = esc(text);
  return raw(escaped
    .replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g, '<a href="$1" target="_blank" rel="noopener noreferrer nofollow">$1</a>')
    .replace(/(^|[\s(])#([A-Za-z][A-Za-z0-9_]{1,30})/g, '$1<a class="tag" href="explore.html?q=%23$2">#$2</a>'));
}

// ---------------------------------------------------------------- feedback
function toastHost() {
  let host = document.querySelector('.toasts');
  if (!host) {
    host = document.createElement('div');
    host.className = 'toasts';
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'polite');
    document.body.append(host);
  }
  return host;
}
export function toast(message, kind = 'ok') {
  const el = document.createElement('div');
  el.className = `toast ${kind === 'error' ? 'toast--error' : ''}`;
  render(el, html`${icon(kind === 'error' ? 'alert' : 'check')}<span>${message}</span>`);
  toastHost().append(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 3800);
  setTimeout(() => el.remove(), 4200);
}
export const toastError = (error) => toast(error?.message || 'Something went wrong.', 'error');

export function modal({ title, body, actions = [], onOpen, wide = false }) {
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  render(backdrop, html`<div class="modal" role="dialog" aria-modal="true" aria-label="${title}" ${wide ? raw('style="width:min(760px,100%)"') : ''}>
    <div class="modal-head"><h2>${title}</h2><button class="icon-btn" data-close aria-label="Close">${icon('x')}</button></div>
    <div class="modal-body">${body}</div>
    ${actions.length ? html`<div class="modal-foot">${actions.map((a, i) => html`<button class="btn ${a.kind || ''}" data-action="${i}">${a.label}</button>`)}</div>` : ''}
  </div>`);
  const previouslyFocused = document.activeElement;
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey); previouslyFocused?.focus?.(); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop || e.target.closest('[data-close]')) close(); });
  backdrop.querySelectorAll('[data-action]').forEach((btn) => btn.addEventListener('click', async () => {
    const action = actions[Number(btn.dataset.action)];
    if (!action.onClick) return close();
    btn.disabled = true;
    try {
      const keepOpen = await action.onClick(backdrop.querySelector('.modal'), close);
      if (!keepOpen) close();
    } catch (error) {
      toastError(error);
    } finally {
      btn.disabled = false;
    }
  }));
  document.addEventListener('keydown', onKey);
  document.body.append(backdrop);
  backdrop.querySelector('input, textarea, select, button:not([data-close])')?.focus();
  onOpen?.(backdrop.querySelector('.modal'), close);
  return { el: backdrop, close };
}

export function confirmDialog(message, { title = 'Are you sure?', confirm = 'Confirm', danger = false } = {}) {
  return new Promise((resolve) => {
    const m = modal({ title, body: html`<p>${message}</p>`, actions: [
      { label: 'Cancel', kind: 'btn--ghost', onClick: () => resolve(false) },
      { label: confirm, kind: danger ? '' : 'btn--yellow', onClick: () => resolve(true) },
    ] });
    m.el.addEventListener('click', (e) => { if (e.target === m.el || e.target.closest('[data-close]')) resolve(false); });
  });
}

export async function withBusy(button, fn) {
  if (!button) return fn();
  const original = button.innerHTML;
  button.disabled = true;
  button.classList.add('is-loading');
  button.innerHTML = `<span class="spinner"></span>${button.dataset.busy ? `<span>${esc(button.dataset.busy)}</span>` : ''}`;
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.classList.remove('is-loading');
    button.innerHTML = original;
  }
}

export const skeleton = (lines = 3) => html`<div class="card">${Array.from({ length: lines }, (_, i) => html`<div class="skeleton sk-line" style="width:${90 - i * 15}%"></div>`)}</div>`;
export const emptyState = ({ iconName = 'info', title, text, action }) =>
  html`<div class="empty">${icon(iconName)}<h3>${title}</h3><p>${text}</p>${action || ''}</div>`;

export function param(name) {
  return new URLSearchParams(location.search).get(name);
}

export function tagsInput(container, values = [], { placeholder = 'Type and press Enter', max = 20 } = {}) {
  let items = [...values];
  let drawing = false;
  const draw = () => {
    if (drawing) return; // removing the focused input fires blur synchronously; don't re-enter
    drawing = true;
    try { renderTags(); } finally { drawing = false; }
  };
  const renderTags = () => {
    render(container, html`${items.map((v, i) => html`<span class="chip">${v}<button type="button" data-i="${i}" aria-label="Remove ${v}">×</button></span>`)}<input type="text" placeholder="${items.length ? '' : placeholder}" aria-label="${placeholder}">`);
    const input = container.querySelector('input');
    input.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ',') && input.value.trim()) {
        e.preventDefault();
        const value = input.value.trim();
        input.value = '';
        if (items.length < max && !items.some((x) => x.toLowerCase() === value.toLowerCase())) items.push(value.slice(0, 40));
        draw();
        container.querySelector('input').focus();
      } else if (e.key === 'Backspace' && !input.value && items.length) {
        items.pop();
        draw();
        container.querySelector('input').focus();
      }
    });
    input.addEventListener('blur', () => {
      const value = input.value.trim();
      if (!value || drawing || !input.isConnected) return;
      input.value = '';
      if (items.length < max && !items.some((x) => x.toLowerCase() === value.toLowerCase())) items.push(value.slice(0, 40));
      setTimeout(draw);
    });
  };
  container.classList.add('tags-input');
  container.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-i]');
    if (b) { items.splice(Number(b.dataset.i), 1); draw(); }
    else container.querySelector('input')?.focus();
  });
  draw();
  return { get: () => [...items], set: (v) => { items = [...v]; draw(); } };
}

export function storage(key, fallback = null) {
  try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
}
export function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: ignore */ }
}
