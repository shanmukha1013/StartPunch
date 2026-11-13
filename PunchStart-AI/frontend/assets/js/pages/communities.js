import { del, get, post } from '../core/api.js';
import { boot } from '../core/shell.js';
import { $, html, icon, render, toastError } from '../core/ui.js';

const { page } = await boot({ active: 'communities', title: 'Communities' });

async function load() {
  const { communities, suggested } = await get('/communities');
  const reasons = Object.fromEntries(suggested.map((s) => [s.slug, s.reasons]));
  const joined = communities.filter((c) => c.joined);
  const card = (c) => html`<article class="card card--hover community-card stack">
    <div class="row" style="flex-wrap:nowrap"><span class="icon-tile">${icon('community')}</span>
      <div class="grow"><a href="community.html?c=${c.slug}"><h3 style="margin:0">${c.name}</h3></a><div class="tiny muted">${c.member_count} members · ${c.post_count} posts</div></div></div>
    <p class="small" style="margin:0;color:var(--k-700)">${c.description}</p>
    ${reasons[c.slug]?.length ? html`<p class="tiny" style="margin:0;color:var(--p-600)">${icon('sparkles')} ${reasons[c.slug][0]}</p>` : ''}
    <div class="row"><button class="btn btn--sm ${c.joined ? 'btn--ghost' : 'btn--yellow'}" data-join="${c.slug}" data-joined="${c.joined}">${c.joined ? 'Joined' : 'Join'}</button>
      <a class="btn btn--quiet btn--sm" href="community.html?c=${c.slug}">Open ${icon('arrow')}</a></div></article>`;
  render(page, html`
    <div class="page-head"><div><p class="eyebrow">Communities</p><h1>Find your people</h1><p>Topic communities for founders, builders and investors. Join to post, discuss and discover relevant members.</p></div></div>
    ${joined.length ? html`<h2>Your communities</h2><div class="grid grid-3" style="margin-bottom:26px">${joined.map(card)}</div>` : ''}
    <h2>${joined.length ? 'More communities' : 'All communities'}</h2>
    <div class="grid grid-3">${communities.filter((c) => !c.joined).map(card)}</div>`);
}

page.addEventListener('click', async (e) => {
  const b = e.target.closest('[data-join]');
  if (!b) return;
  try {
    await (b.dataset.joined === 'true' ? del(`/communities/${b.dataset.join}/join`) : post(`/communities/${b.dataset.join}/join`));
    load();
  } catch (error) { toastError(error); }
});
load().catch(toastError);
void $;
