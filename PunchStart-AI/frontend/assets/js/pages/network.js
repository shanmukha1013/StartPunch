import { del, get, post } from '../core/api.js';
import { boot } from '../core/shell.js';
import { $, $$, emptyState, html, icon, person, render, timeAgo, toast, toastError } from '../core/ui.js';

const { page } = await boot({ active: 'network', title: 'Network' });

async function load() {
  const [conns, recs] = await Promise.all([get('/connections'), get('/people/suggestions')]);
  render(page, html`
    <div class="page-head"><div><p class="eyebrow">Network</p><h1>Your founder network</h1><p>Connections can message each other. Recommendations explain why someone is a match — based on your profile, follows and communities.</p></div>
      <a class="btn btn--ghost" href="explore.html">${icon('search')} Find people</a></div>
    ${conns.incoming.length ? html`<div class="card" style="margin-bottom:18px"><h2>Requests <span class="chip chip--ai">${conns.incoming.length}</span></h2>
      ${conns.incoming.map((r) => html`<div class="row between" style="padding:10px 0;border-top:1px solid var(--line-soft)"><div class="grow">${person(r.user)}${r.message ? html`<p class="small" style="margin:6px 0 0 51px">"${r.message}"</p>` : ''}</div>
        <div class="row"><button class="btn btn--sm btn--yellow" data-respond="${r.id}" data-accept="1">Accept</button><button class="btn btn--sm btn--ghost" data-respond="${r.id}" data-accept="">Ignore</button></div></div>`)}</div>` : ''}
    <div class="split"><div class="stack">
      <div class="card"><div class="card-title"><h2>Recommended for you</h2></div>
        ${!recs.profile_complete ? html`<div class="notice" style="margin-bottom:12px">${icon('info')}<div>Recommendations improve when your <a href="settings.html">profile</a> lists interests, skills and what you're looking for.</div></div>` : ''}
        ${recs.people.length ? html`<div class="grid grid-2">${recs.people.map((p) => html`<div class="card" style="box-shadow:none">${person(p.user)}
          <ul class="tiny" style="padding-left:16px;margin:10px 0;color:var(--p-700)">${p.reasons.map((r) => html`<li>${r}</li>`)}</ul>
          <div class="row"><button class="btn btn--sm" data-connect="${p.user.handle}">${icon('userplus')} Connect</button><button class="btn btn--sm btn--ghost" data-follow="${p.user.handle}">Follow</button></div></div>`)}</div>`
          : emptyState({ iconName: 'users', title: 'No matches yet', text: 'As more founders join with overlapping interests and skills, they will appear here.' })}
        <p class="tiny muted" style="margin:10px 0 0">${recs.method}</p></div>
      <div class="card"><h2>Connections <span class="chip">${conns.connections.length}</span></h2>
        ${conns.connections.length ? conns.connections.map((c) => html`<div class="row between" style="padding:10px 0;border-top:1px solid var(--line-soft)"><div class="grow">${person(c.user)}</div>
          <div class="row"><button class="btn btn--sm btn--ghost" data-message="${c.user.handle}">${icon('chat')} Message</button><button class="icon-btn" data-remove="${c.id}" aria-label="Remove connection">${icon('x')}</button></div></div>`)
          : html`<p class="muted small" style="margin:0">No connections yet.</p>`}</div></div>
      <aside class="stack"><div class="card"><h3>Sent requests</h3>${conns.outgoing.length ? conns.outgoing.map((r) => html`<div class="row between" style="padding:6px 0">${person(r.user, `sent ${timeAgo(r.created_at)}`)}<button class="btn btn--quiet btn--sm" data-remove="${r.id}">Cancel</button></div>`) : html`<p class="small muted" style="margin:0">None pending.</p>`}</div>
        <div class="card"><h3>Communities for you</h3>${recs.communities.map((c) => html`<a href="community.html?c=${c.slug}" style="display:block;padding:6px 0"><strong>${c.name}</strong><div class="tiny muted">${c.reasons[0] || `${c.member_count} members`}</div></a>`)}</div></aside></div>`);
}

page.addEventListener('click', async (e) => {
  const t = e.target.closest('button');
  if (!t) return;
  try {
    if (t.dataset.respond) { await post(`/connections/${t.dataset.respond}/respond`, { accept: Boolean(t.dataset.accept) }); toast(t.dataset.accept ? 'Connected' : 'Ignored'); load(); }
    if (t.dataset.connect) { await post('/connections', { handle: t.dataset.connect }); t.textContent = 'Requested'; t.disabled = true; }
    if (t.dataset.follow) { await post(`/users/${t.dataset.follow}/follow`); t.textContent = 'Following'; t.disabled = true; }
    if (t.dataset.remove) { await del(`/connections/${t.dataset.remove}`); load(); }
    if (t.dataset.message) { const c = await post('/conversations', { handle: t.dataset.message }); location.href = `messages.html?c=${c.id}`; }
  } catch (error) { toastError(error); }
});
load().catch(toastError);
void $; void $$;
