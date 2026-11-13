import { get, post } from '../core/api.js';
import { composer, renderPostList } from '../core/posts.js';
import { boot } from '../core/shell.js';
import { $, $$, emptyState, html, icon, person, render, toastError } from '../core/ui.js';

const { page, user } = await boot({ active: 'feed', title: 'Feed' });

render(page, html`
  <div class="page-head"><div><p class="eyebrow">Founder network</p><h1>Feed</h1><p>Ideas, progress, questions and milestones from founders and communities you follow.</p></div></div>
  <div class="split">
    <div>
      <div id="composer"></div>
      <div class="tabs" role="tablist">
        <button class="tab" role="tab" data-tab="for_you" aria-selected="true">For you</button>
        <button class="tab" role="tab" data-tab="following" aria-selected="false">Following</button>
        <button class="tab" role="tab" data-tab="latest" aria-selected="false">Latest</button>
      </div>
      <p class="tiny muted" id="ranking-note"></p>
      <div id="posts"><div class="skeleton sk-block"></div></div>
      <div style="text-align:center;margin-top:14px"><button class="btn btn--ghost hidden" id="more">Load more</button></div>
    </div>
    <aside class="stack sticky">
      <div class="card"><div class="card-title"><h3>${icon('trending')} Trending this week</h3></div><div id="trending"><div class="skeleton sk-line"></div></div></div>
      <div class="card"><div class="card-title"><h3>Suggested founders</h3><a class="small" href="network.html">More</a></div><div id="suggested"><div class="skeleton sk-line"></div></div></div>
      <div class="card"><div class="card-title"><h3>Communities</h3><a class="small" href="communities.html">Browse</a></div><div id="comms"></div></div>
    </aside>
  </div>`);

let tab = 'for_you';
let offset = 0;
const list = $('#posts');

async function load(reset = true) {
  if (reset) { offset = 0; render(list, html`<div class="skeleton sk-block"></div>`); }
  try {
    const data = await get(`/feed?tab=${tab}&offset=${offset}`);
    $('#ranking-note').textContent = tab === 'for_you' ? `Ranked by ${data.ranking}. No promoted or simulated engagement.` : '';
    renderPostList(list, data.posts, { me: user, append: !reset, empty: emptyState({ iconName: 'feed', title: tab === 'following' ? 'Nothing from your network yet' : 'No posts yet',
      text: tab === 'following' ? 'Follow founders or join communities to fill this feed.' : 'Be the first to share an idea or question with the network.',
      action: html`<a class="btn btn--ghost" href="explore.html">Explore founders</a>` }) });
    offset = data.next_offset ?? offset;
    $('#more').classList.toggle('hidden', data.next_offset == null);
  } catch (error) { toastError(error); }
}

const { communities } = await get('/communities').catch(() => ({ communities: [] }));
const joined = communities.filter((c) => c.joined);
composer($('#composer'), user, { communities: joined, onPosted: () => { tab = 'latest'; $$('[role="tab"]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === tab))); load(); } });
$$('[role="tab"]').forEach((t) => t.addEventListener('click', () => {
  tab = t.dataset.tab;
  $$('[role="tab"]').forEach((x) => x.setAttribute('aria-selected', String(x === t)));
  load();
}));
$('#more').addEventListener('click', () => load(false));
load();

get('/trending').then((t) => render($('#trending'), t.tags.length || t.posts.length ? html`
  ${t.tags.length ? html`<div class="chip-row" style="margin-bottom:10px">${t.tags.map((x) => html`<a class="chip" href="explore.html?q=%23${x.tag}">#${x.tag} · ${x.posts}</a>`)}</div>` : ''}
  ${t.posts.slice(0, 4).map((p) => html`<a href="post.html?id=${p.id}" style="display:block;padding:7px 0;border-top:1px solid var(--line-soft);color:var(--k-800)"><strong class="small">${p.title || p.body.slice(0, 70)}</strong><div class="tiny muted">${p.author?.name} · ${p.counts.likes} likes · ${p.counts.comments} comments</div></a>`)}
  <p class="tiny muted" style="margin:8px 0 0">${t.method}</p>` : html`<p class="small muted" style="margin:0">No trending discussions this week yet.</p>`)).catch(() => {});

get('/people/suggestions').then((s) => {
  render($('#suggested'), s.people.length ? html`${s.people.slice(0, 4).map((p) => html`<div class="row" style="padding:7px 0;flex-wrap:nowrap"><div class="grow">${person(p.user, p.reasons[0])}</div>
    <button class="btn btn--sm btn--ghost" data-follow="${p.user.handle}">Follow</button></div>`)}` : (s.profile_complete ? html`<p class="small muted" style="margin:0">No strong matches yet. As more founders with overlapping interests join, they'll appear here.</p>`
      : html`<p class="small muted" style="margin:0">Add interests to your <a href="settings.html">profile</a> to get suggestions.</p>`));
  render($('#comms'), html`${(joined.length ? joined : s.communities).slice(0, 5).map((c) => html`<a class="row" href="community.html?c=${c.slug}" style="padding:6px 0;color:var(--k-800);flex-wrap:nowrap"><span class="icon-tile" style="width:32px;height:32px;border-radius:9px">${icon('community')}</span><span class="grow small"><strong>${c.name}</strong><br><span class="muted">${c.member_count} members</span></span></a>`)}`);
}).catch(() => {});

$('#suggested').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-follow]');
  if (!b) return;
  try { await post(`/users/${b.dataset.follow}/follow`); b.textContent = 'Following'; b.disabled = true; } catch (error) { toastError(error); }
});
