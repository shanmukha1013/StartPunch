import { del, get, post } from '../core/api.js';
import { composer, renderPostList } from '../core/posts.js';
import { boot } from '../core/shell.js';
import { $, emptyState, html, icon, param, person, render, toastError } from '../core/ui.js';

const { page, user } = await boot({ active: 'communities', title: 'Community' });
const slug = param('c');

async function load() {
  let data;
  try { data = await get(`/communities/${encodeURIComponent(slug || '')}`); }
  catch (error) { render(page, emptyState({ iconName: 'community', title: 'Community not found', text: error.message, action: html`<a class="btn" href="communities.html">All communities</a>` })); return; }
  const c = data.community;
  document.title = `${c.name} · StartPunch`;
  render(page, html`
    <div class="card card--yellow" style="margin-bottom:18px"><div class="row between">
      <div class="row" style="flex-wrap:nowrap"><span class="icon-tile">${icon('community')}</span><div><h1 style="margin:0">${c.name}</h1><p style="margin:2px 0 0">${c.description}</p></div></div>
      <div class="row"><span class="chip chip--ink">${c.member_count} members</span><button class="btn ${c.joined ? 'btn--ghost' : ''}" id="join">${c.joined ? 'Leave' : 'Join community'}</button></div></div></div>
    <div class="split"><div>
      <div id="composer">${c.joined ? '' : html`<div class="notice" style="margin-bottom:16px">${icon('info')}<div>Join to post in ${c.name}.</div></div>`}</div>
      <div id="posts"></div>
      <div style="text-align:center;margin-top:12px"><button class="btn btn--ghost ${data.next_offset == null ? 'hidden' : ''}" id="more">Load more</button></div></div>
      <aside class="stack"><div class="card"><h3>Recently joined</h3>${data.recent_members.length ? data.recent_members.map((m) => html`<div style="padding:6px 0">${person(m)}</div>`) : html`<p class="small muted" style="margin:0">No members yet — be the first.</p>`}</div>
        <div class="card"><h3>Topics</h3><div class="chip-row">${c.tags.map((t) => html`<span class="chip chip--ai">${t}</span>`)}</div></div></aside></div>`);
  if (c.joined) composer($('#composer'), user, { communities: [{ slug: c.slug, name: c.name }], defaultCommunity: c.slug, onPosted: load, placeholder: `Start a discussion in ${c.name}…` });
  renderPostList($('#posts'), data.posts, { me: user, empty: emptyState({ iconName: 'comment', title: 'No discussions yet', text: 'Start the first conversation in this community.' }) });
  let offset = data.next_offset;
  $('#more').addEventListener('click', async () => {
    const more = await get(`/communities/${slug}?offset=${offset}`);
    renderPostList($('#posts'), more.posts, { me: user, append: true });
    offset = more.next_offset;
    $('#more').classList.toggle('hidden', offset == null);
  });
  $('#join').addEventListener('click', async () => {
    try { await (c.joined ? del(`/communities/${slug}/join`) : post(`/communities/${slug}/join`)); load(); } catch (error) { toastError(error); }
  });
}
load();
