// App shell: auth guard + sidebar/topbar/bottom navigation shared by every signed-in page.
import { api, ApiError, post } from './api.js';
import { $, avatar, brandMark, html, icon, raw, render, toastError } from './ui.js';

const NAV = [
  { section: 'Build' },
  { id: 'dashboard', label: 'Workspace', icon: 'home', href: 'dashboard.html' },
  { id: 'analyze', label: 'New analysis', icon: 'sparkles', href: 'analyze.html' },
  { id: 'intelligence', label: 'Market intelligence', icon: 'database', href: 'intelligence.html' },
  { section: 'Connect' },
  { id: 'feed', label: 'Feed', icon: 'feed', href: 'feed.html' },
  { id: 'explore', label: 'Explore', icon: 'compass', href: 'explore.html' },
  { id: 'communities', label: 'Communities', icon: 'community', href: 'communities.html' },
  { id: 'network', label: 'Network', icon: 'users', href: 'network.html' },
  { id: 'messages', label: 'Messages', icon: 'chat', href: 'messages.html', badge: 'messages' },
  { id: 'notifications', label: 'Notifications', icon: 'bell', href: 'notifications.html', badge: 'notifications' },
];
const MOBILE = [
  { id: 'dashboard', label: 'Home', icon: 'home', href: 'dashboard.html' },
  { id: 'feed', label: 'Feed', icon: 'feed', href: 'feed.html' },
  { id: 'analyze', label: 'Analyze', icon: 'sparkles', href: 'analyze.html' },
  { id: 'messages', label: 'Inbox', icon: 'chat', href: 'messages.html' },
  { id: 'explore', label: 'Explore', icon: 'compass', href: 'explore.html' },
];

export const session = { user: null, aiConfigured: false };

function configErrorScreen(message) {
  render(document.body, html`<main class="auth-main" style="min-height:100vh">
    <div class="card" style="max-width:560px">
      <div class="row" style="margin-bottom:10px">${brandMark()}<h2 style="margin:0">StartPunch is not fully configured</h2></div>
      <p>${message}</p>
      <p class="muted small">Operators: see the deployment section of the README for the required environment variables.</p>
    </div></main>`);
}

export async function boot({ active, title } = {}) {
  let me;
  try {
    me = await api('/auth/me');
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      location.replace(`login.html?next=${encodeURIComponent(location.pathname.split('/').pop() + location.search)}`);
      return new Promise(() => {});
    }
    if (error instanceof ApiError && error.status === 503) {
      configErrorScreen(error.message);
      return new Promise(() => {});
    }
    configErrorScreen('The StartPunch API could not be reached. Please try again in a moment.');
    return new Promise(() => {});
  }
  session.user = me.user;
  session.aiConfigured = me.ai_configured;
  if (title) document.title = `${title} · StartPunch`;

  const app = document.getElementById('app');
  const pageContent = app.innerHTML;
  render(app, html`<div class="app">
    <aside class="sidebar" aria-label="Main navigation">
      <a class="brand" href="dashboard.html">${brandMark()}<span>Start<b>Punch</b></span></a>
      ${NAV.map((item) => item.section
        ? html`<div class="nav-section">${item.section}</div>`
        : html`<a class="nav-link" href="${item.href}" ${item.id === active ? raw('aria-current="page"') : ''}>${icon(item.icon)}<span>${item.label}</span>${item.badge ? html`<span class="badge hidden" data-badge="${item.badge}"></span>` : ''}</a>`)}
      <div class="sidebar-cta"><a class="btn btn--yellow btn--block" href="analyze.html">${icon('plus')} Analyze an idea</a></div>
      <div class="sidebar-foot">
        <a href="profile.html?u=${encodeURIComponent(me.user.handle)}" aria-label="Your profile">${avatar(me.user)}</a>
        <div class="who"><strong>${me.user.name}</strong><span>@${me.user.handle}</span></div>
        <a class="icon-btn" href="settings.html" aria-label="Settings" ${active === 'settings' ? raw('aria-current="page"') : ''}>${icon('settings')}</a>
      </div>
    </aside>
    <div class="main">
      <header class="topbar">
        <a class="brand mobile-only on-light" href="dashboard.html" aria-label="StartPunch home">${brandMark()}</a>
        <form class="global-search" role="search" action="explore.html">
          <label class="sr-only" for="global-q">Search StartPunch</label>
          <input id="global-q" class="input input--search" name="q" placeholder="Search founders, startups, posts…  ( / )" autocomplete="off">
        </form>
        <span class="spacer"></span>
        <a class="icon-btn mobile-only" href="explore.html" aria-label="Search">${icon('search')}</a>
        <a class="icon-btn" href="notifications.html" aria-label="Notifications">${icon('bell')}<span class="dot hidden" data-badge="notifications"></span></a>
        <div class="menu-wrap">
          <button class="icon-btn" id="user-menu-btn" aria-haspopup="menu" aria-expanded="false" aria-label="Account menu">${avatar(me.user, 'sm')}</button>
          <div class="menu hidden" id="user-menu" role="menu">
            <a href="profile.html?u=${encodeURIComponent(me.user.handle)}" role="menuitem">${icon('users')} Your profile</a>
            <a href="network.html" role="menuitem">${icon('userplus')} Network</a>
            <a href="communities.html" role="menuitem">${icon('community')} Communities</a>
            <a href="intelligence.html" role="menuitem">${icon('database')} Market intelligence</a>
            <a href="settings.html" role="menuitem">${icon('settings')} Settings</a>
            ${me.user.role === 'admin' ? html`<a href="settings.html#moderation" role="menuitem">${icon('shield')} Moderation</a>` : ''}
            <button id="logout-btn" role="menuitem">${icon('logout')} Sign out</button>
          </div>
        </div>
      </header>
      <main class="page" id="page">${raw(pageContent)}</main>
    </div>
  </div>
  <nav class="bottom-nav" aria-label="Mobile navigation">
    ${MOBILE.map((item) => html`<a href="${item.href}" ${item.id === active ? raw('aria-current="page"') : ''}>${icon(item.icon)}<span>${item.label}</span></a>`)}
  </nav>`);

  const menuBtn = $('#user-menu-btn');
  const menu = $('#user-menu');
  menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = menu.classList.toggle('hidden') === false;
    menuBtn.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', () => { menu.classList.add('hidden'); menuBtn.setAttribute('aria-expanded', 'false'); });
  $('#logout-btn').addEventListener('click', async () => {
    try { await post('/auth/logout'); } catch (error) { toastError(error); }
    location.href = '../index.html';
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !/input|textarea|select/i.test(document.activeElement?.tagName || '')) {
      const q = $('#global-q');
      if (q && q.offsetParent) { e.preventDefault(); q.focus(); }
    }
  });
  refreshBadges(me.unread_notifications);
  setInterval(() => refreshBadges(), 45000);
  return { user: me.user, page: $('#page'), aiConfigured: me.ai_configured };
}

async function refreshBadges(initialNotes) {
  try {
    const notes = initialNotes ?? (await api('/notifications/unread-count')).notifications;
    const convs = await api('/conversations');
    const unreadMessages = convs.conversations.reduce((sum, c) => sum + (c.unread || 0), 0);
    setBadge('notifications', notes);
    setBadge('messages', unreadMessages);
  } catch { /* badges are best-effort */ }
}

export function setBadge(name, count) {
  document.querySelectorAll(`[data-badge="${name}"]`).forEach((el) => {
    el.textContent = count > 99 ? '99+' : String(count);
    el.classList.toggle('hidden', !count);
  });
}
