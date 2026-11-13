import { get, post } from '../core/api.js';
import { boot, setBadge } from '../core/shell.js';
import { $, avatar, emptyState, html, icon, render, timeAgo, toastError } from '../core/ui.js';

const { page } = await boot({ active: 'notifications', title: 'Notifications' });
const ICON = { follow: 'userplus', like: 'heart', comment: 'comment', reply: 'comment', repost: 'repeat', connection_request: 'userplus',
  connection_accepted: 'check', message: 'chat', collab_request: 'rocket', collab_accepted: 'rocket', startup_follow: 'star' };

function link(n) {
  if (n.entity_type === 'post') return `post.html?id=${n.entity_id}`;
  if (n.entity_type === 'user') return n.type === 'connection_request' ? 'network.html' : `profile.html?u=${n.entity_id}`;
  if (n.entity_type === 'startup') return `startup.html?id=${n.entity_id}`;
  if (n.entity_type === 'conversation') return `messages.html?c=${n.entity_id}`;
  return '#';
}

async function load() {
  const { notifications } = await get('/notifications');
  render(page, html`<div class="page-head"><div><p class="eyebrow">Activity</p><h1>Notifications</h1></div>
    ${notifications.some((n) => !n.read) ? html`<button class="btn btn--ghost" id="read-all">${icon('check')} Mark all read</button>` : ''}</div>
    <div class="card" style="padding:0;overflow:hidden">${notifications.length ? notifications.map((n) => html`<a class="note ${n.read ? '' : 'unread'}" href="${link(n)}" data-id="${n.id}" style="color:inherit;text-decoration:none">
      <span class="icon-tile ${n.type.startsWith('collab') ? 'icon-tile--yellow' : ''}" style="width:38px;height:38px">${icon(ICON[n.type] || 'bell')}</span>
      ${n.actor ? avatar(n.actor, 'sm') : ''}<span class="grow"><span>${n.text}</span><br><span class="tiny muted">${timeAgo(n.created_at)}</span></span></a>`)
      : html`<div style="padding:20px">${emptyState({ iconName: 'bell', title: 'All quiet', text: 'Follows, comments, connection requests and messages will appear here.' })}</div>`}</div>`);
  $('#read-all')?.addEventListener('click', async () => { await post('/notifications/read', {}); setBadge('notifications', 0); load(); });
  page.querySelectorAll('.note.unread').forEach((a) => a.addEventListener('click', () => { post('/notifications/read', { ids: [a.dataset.id] }).catch(() => {}); }));
}
load().catch(toastError);
