import { del, get, post } from '../core/api.js';
import { renderPostList, reportDialog } from '../core/posts.js';
import { boot } from '../core/shell.js';
import { $, $$, avatar, confirmDialog, emptyState, fmtDate, html, icon, modal, param, person, raw, render, richText, titleCase, toast,
  toastError } from '../core/ui.js';

const { page, user } = await boot({ active: '', title: 'Profile' });
const handle = param('u') || user.handle;

async function load() {
  let p;
  try { p = await get(`/users/${encodeURIComponent(handle)}`); }
  catch (error) { render(page, emptyState({ iconName: 'users', title: 'Member not found', text: error.message, action: html`<a class="btn" href="explore.html">Explore</a>` })); return; }
  document.title = `${p.name} · StartPunch`;
  const rel = p.relationship;
  const links = Object.entries(p.links || {});
  render(page, html`
    <div class="profile-cover" ${p.cover_url ? raw(`style="background-image:url('${p.cover_url}')"`) : ''}></div>
    <div class="card profile-card">
      <div class="profile-top">
        ${avatar(p, 'lg')}
        <div class="grow"><h1 style="margin:0">${p.name}</h1><div class="muted">@${p.handle}${p.location ? ` · ${p.location}` : ''}</div></div>
        <div class="row" style="padding-bottom:6px">
          ${rel.is_self ? html`<a class="btn btn--ghost" href="settings.html">${icon('edit')} Edit profile</a>` : html`
            <button class="btn ${rel.following ? 'btn--ghost' : 'btn--yellow'}" id="follow">${rel.following ? 'Following' : 'Follow'}</button>
            ${rel.connection?.status === 'accepted' ? html`<span class="chip chip--ink">${icon('check')} Connected</span>`
              : rel.connection?.status === 'pending' ? html`<span class="chip">${rel.connection.direction === 'incoming' ? 'Wants to connect' : 'Request sent'}</span>`
              : html`<button class="btn btn--ghost" id="connect">${icon('userplus')} Connect</button>`}
            ${rel.can_message ? html`<button class="btn btn--ghost" id="message">${icon('chat')} Message</button>` : ''}
            <div class="menu-wrap"><button class="icon-btn" id="more" aria-label="More">${icon('more')}</button></div>`}
        </div>
      </div>
      ${p.headline ? html`<p style="font-size:1.05rem;margin:14px 0 6px;font-weight:600">${p.headline}</p>` : ''}
      ${p.restricted ? html`<div class="notice" style="margin-top:12px">${icon('lock')}<div><strong>Profile visible to connections</strong>Connect with ${p.name.split(' ')[0]} to see their full profile and posts.</div></div>` : html`
        ${p.bio ? html`<div class="post-body" style="margin-top:8px">${richText(p.bio)}</div>` : ''}
        <div class="row small" style="margin-top:12px;gap:16px">
          <a href="#" data-rel="followers"><b>${p.follower_count}</b> followers</a><a href="#" data-rel="following"><b>${p.following_count}</b> following</a>
          <span class="muted">${p.post_count} posts · joined ${fmtDate(p.joined_at)}</span>
          ${links.map(([k, v]) => html`<a href="${v}" target="_blank" rel="noopener noreferrer nofollow">${icon(k === 'website' ? 'globe' : 'external')} ${titleCase(k)}</a>`)}
        </div>`}
    </div>
    ${p.restricted ? '' : html`<div class="split" style="margin-top:18px">
      <div><div class="tabs" role="tablist"><button class="tab" role="tab" aria-selected="true">Posts</button></div><div id="posts"><div class="skeleton sk-block"></div></div>
        <div style="text-align:center;margin-top:12px"><button class="btn btn--ghost hidden" id="more-posts">Load more</button></div></div>
      <aside class="stack">
        ${p.looking_for.length || p.open_to.length ? html`<div class="card card--yellow">${p.looking_for.length ? html`<h3>Looking for</h3><div class="chip-row">${p.looking_for.map((x) => html`<span class="chip chip--ink">${x}</span>`)}</div>` : ''}
          ${p.open_to.length ? html`<h3 style="margin-top:12px">Open to</h3><div class="chip-row">${p.open_to.map((x) => html`<span class="chip">${x}</span>`)}</div>` : ''}</div>` : ''}
        ${p.skills.length ? html`<div class="card"><h3>Skills</h3><div class="chip-row">${p.skills.map((x) => html`<span class="chip">${x}</span>`)}</div></div>` : ''}
        ${p.interests.length || p.industries.length ? html`<div class="card"><h3>Interests</h3><div class="chip-row">${[...p.industries, ...p.interests].map((x) => html`<span class="chip chip--ai">${x}</span>`)}</div></div>` : ''}
        ${p.startups?.length ? html`<div class="card"><h3>Startups & projects</h3>${p.startups.map((s) => html`<a href="startup.html?id=${s.id}" class="row" style="padding:8px 0;flex-wrap:nowrap;color:inherit">
          <span class="icon-tile" style="width:36px;height:36px">${icon('rocket')}</span><span class="grow"><strong>${s.name}</strong>${s.visibility === 'private' ? html` <span class="chip">${icon('lock')} private</span>` : ''}<br><span class="small muted">${s.tagline}</span></span></a>`)}</div>` : ''}
        ${p.achievements?.length ? html`<div class="card"><h3>Achievements</h3><ul class="small" style="padding-left:18px;margin:0">${p.achievements.map((a) => html`<li>${a.title}${a.year ? html` <span class="muted">(${a.year})</span>` : ''}</li>`)}</ul></div>` : ''}
      </aside></div>`}`);

  let offset = 0;
  const loadPosts = async (reset) => {
    const data = await get(`/users/${encodeURIComponent(handle)}/posts?offset=${offset}`);
    renderPostList($('#posts'), data.posts, { me: user, append: !reset, empty: emptyState({ iconName: 'feed', title: 'No posts yet', text: rel.is_self ? 'Share your first idea or update from the feed.' : `${p.name.split(' ')[0]} hasn't posted yet.` }) });
    offset = data.next_offset ?? offset;
    $('#more-posts').classList.toggle('hidden', data.next_offset == null);
  };
  if (!p.restricted) { loadPosts(true).catch(toastError); $('#more-posts').addEventListener('click', () => loadPosts(false)); }

  $$('[data-rel]').forEach((a) => a.addEventListener('click', async (e) => {
    e.preventDefault();
    const { users } = await get(`/users/${encodeURIComponent(handle)}/${a.dataset.rel}`);
    modal({ title: titleCase(a.dataset.rel), body: users.length ? html`${users.map((u) => html`<div style="padding:7px 0">${person(u)}</div>`)}` : html`<p class="muted">Nobody yet.</p>` });
  }));
  $('#follow')?.addEventListener('click', async () => {
    try { await (rel.following ? del(`/users/${handle}/follow`) : post(`/users/${handle}/follow`)); load(); } catch (error) { toastError(error); }
  });
  $('#connect')?.addEventListener('click', () => modal({ title: `Connect with ${p.name}`, body: html`<label for="cm">Add a note <span class="hint">(optional)</span></label><textarea class="textarea" id="cm" maxlength="300" placeholder="Why do you want to connect?"></textarea>`,
    actions: [{ label: 'Cancel', kind: 'btn--ghost' }, { label: 'Send request', kind: 'btn--yellow', onClick: async (m) => { await post('/connections', { handle, message: $('#cm', m).value }); toast('Connection request sent'); load(); } }] }));
  $('#message')?.addEventListener('click', async () => {
    try { const c = await post('/conversations', { handle }); location.href = `messages.html?c=${c.id}`; } catch (error) { toastError(error); }
  });
  $('#more')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const menu = document.createElement('div');
    menu.className = 'menu';
    render(menu, html`<button data-m="block">${icon('shield')} ${rel.blocked ? 'Unblock' : 'Block'} @${handle}</button><button data-m="report">${icon('flag')} Report profile</button>`);
    e.currentTarget.parentElement.append(menu);
    setTimeout(() => document.addEventListener('click', () => menu.remove(), { once: true }));
    menu.addEventListener('click', async (ev) => {
      const m = ev.target.closest('[data-m]')?.dataset.m;
      if (m === 'report') reportDialog('user', p.id);
      if (m === 'block') {
        if (!rel.blocked && !(await confirmDialog(`Blocking removes follows and connections both ways and hides each other's content.`, { title: `Block @${handle}?`, confirm: 'Block' }))) return;
        try { await (rel.blocked ? del(`/users/${handle}/block`) : post(`/users/${handle}/block`)); toast(rel.blocked ? 'Unblocked' : 'Blocked'); location.href = rel.blocked ? location.href : 'feed.html'; }
        catch (error) { toastError(error); }
      }
    });
  });
}
load();
