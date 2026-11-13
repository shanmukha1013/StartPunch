import { get, post } from '../core/api.js';
import { boot, setBadge } from '../core/shell.js';
import { $, avatar, emptyState, esc, html, icon, param, render, timeAgo, toastError } from '../core/ui.js';

const { page } = await boot({ active: 'messages', title: 'Messages' });
let active = param('c');
let pollTimer = null;

render(page, html`<div class="page-head"><div><p class="eyebrow">Messages</p><h1>Inbox</h1><p>Private conversations with your connections and collaborators.</p></div></div>
  <div class="card inbox"><div class="inbox-list" id="list"></div><div class="thread" id="thread"></div></div>`);

async function loadList() {
  const { conversations } = await get('/conversations');
  setBadge('messages', conversations.reduce((s, c) => s + c.unread, 0));
  render($('#list'), conversations.length ? html`${conversations.map((c) => html`<button class="inbox-item" data-c="${c.id}" aria-current="${c.id === active}">
    ${avatar(c.with)}<span style="min-width:0"><strong class="small">${c.with?.name || 'Member'}</strong><br>
    <span class="tiny muted">${c.last_message ? `${c.last_message.from_me ? 'You: ' : ''}${c.last_message.body}` : 'No messages yet'}</span></span>
    ${c.unread ? html`<span class="unread">${c.unread}</span>` : ''}</button>`)}`
    : html`<div style="padding:16px">${emptyState({ iconName: 'chat', title: 'No conversations', text: 'Connect with founders, then message them from their profile or your network.', action: html`<a class="btn btn--sm" href="network.html">Open network</a>` })}</div>`);
  return conversations;
}

async function openThread(id, { quiet = false } = {}) {
  active = id;
  $('.inbox').classList.add('has-thread');
  history.replaceState(null, '', `messages.html?c=${id}`);
  try {
    const t = await get(`/conversations/${id}/messages`);
    const body = $('#thread-body');
    const atBottom = body ? body.scrollHeight - body.scrollTop - body.clientHeight < 60 : true;
    if (!quiet || !body) {
      render($('#thread'), html`<div class="thread-head row"><button class="icon-btn mobile-only" id="back" aria-label="Back">${icon('back')}</button>
        ${t.with ? html`<a class="person" href="profile.html?u=${t.with.handle}">${avatar(t.with)}<span class="person-meta"><strong>${t.with.name}</strong><span>@${t.with.handle}</span></span></a>` : 'Member'}</div>
        <div class="thread-body" id="thread-body" aria-live="polite"></div>
        <form class="thread-foot" id="send"><textarea class="textarea" name="body" maxlength="4000" placeholder="Write a message…" aria-label="Message" style="min-height:46px;height:46px" required></textarea><button class="btn">${icon('send')}</button></form>`);
      $('#back').addEventListener('click', () => { $('.inbox').classList.remove('has-thread'); active = null; });
      const form = $('#send');
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = form.body.value.trim();
        if (!text) return;
        form.body.value = '';
        try { await post(`/conversations/${id}/messages`, { body: text }); await openThread(id, { quiet: true }); } catch (error) { toastError(error); form.body.value = text; }
      });
      form.body.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
    }
    const thread = $('#thread-body');
    thread.innerHTML = t.messages.length ? t.messages.map((m) => `<div class="msg ${m.from_me ? 'me' : ''}">${esc(m.body)}<time>${esc(timeAgo(m.created_at))}</time></div>`).join('')
      : '<p class="muted small" style="text-align:center">Say hello 👋</p>';
    if (!quiet || atBottom) thread.scrollTop = thread.scrollHeight;
    loadList();
  } catch (error) { toastError(error); }
}

$('#list').addEventListener('click', (e) => { const b = e.target.closest('[data-c]'); if (b) openThread(b.dataset.c); });
const conversations = await loadList().catch((e) => { toastError(e); return []; });
if (active) openThread(active);
else if (conversations.length && window.innerWidth > 900) openThread(conversations[0].id);
else render($('#thread'), html`<div style="display:grid;place-items:center;height:100%;padding:24px">${emptyState({ iconName: 'chat', title: 'Select a conversation', text: 'Messages are private between members.' })}</div>`);
pollTimer = setInterval(() => { if (active && document.visibilityState === 'visible') openThread(active, { quiet: true }); }, 8000);
window.addEventListener('beforeunload', () => clearInterval(pollTimer));
