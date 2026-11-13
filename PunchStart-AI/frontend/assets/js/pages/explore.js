import { get } from '../core/api.js';
import { renderPostList } from '../core/posts.js';
import { boot } from '../core/shell.js';
import { $, $$, emptyState, html, icon, param, person, render, titleCase, toastError } from '../core/ui.js';

const { page, user } = await boot({ active: 'explore', title: 'Explore' });
const q0 = param('q') || '';

render(page, html`
  <div class="page-head"><div><p class="eyebrow">Discover</p><h1>Explore</h1><p>Find public startup ideas, founders with the skills you need, communities and discussions.</p></div></div>
  <form id="search" class="card row" role="search" style="margin-bottom:18px;flex-wrap:nowrap">
    <input class="input input--search" name="q" value="${q0}" placeholder="Search people, startups, posts, communities or #tags" aria-label="Search" minlength="2">
    <button class="btn">Search</button></form>
  <div class="tabs" role="tablist">
    ${[['all', 'Results'], ['startups', 'Startup ideas'], ['people', 'People']].map(([id, l], i) => html`<button class="tab" role="tab" data-tab="${id}" aria-selected="${i === 0}">${l}</button>`)}
  </div>
  <div data-panel="all"></div>
  <div data-panel="startups" class="hidden">
    <div class="row" style="margin-bottom:14px"><input class="input" id="s-q" placeholder="Filter by name, industry…" style="max-width:320px">
      <input class="input" id="s-role" placeholder="Looking for (e.g. designer)" style="max-width:240px"><button class="btn btn--ghost" id="s-go">Filter</button>
      <a class="btn btn--yellow" href="startup.html?new=1" style="margin-left:auto">${icon('plus')} Share your startup</a></div>
    <div id="startups" class="grid grid-3"></div></div>
  <div data-panel="people" class="hidden">
    <div class="row" style="margin-bottom:14px"><input class="input" id="p-q" placeholder="Name or headline" style="max-width:260px">
      <input class="input" id="p-skill" placeholder="Skill (e.g. React, sales)" style="max-width:220px">
      <input class="input" id="p-role" placeholder="Open to (e.g. co-founder)" style="max-width:220px"><button class="btn btn--ghost" id="p-go">Filter</button></div>
    <div id="people" class="grid grid-3"></div></div>`);

const startupCard = (s) => html`<a class="card card--hover" href="startup.html?id=${s.id}" style="color:inherit;text-decoration:none">
  <div class="row" style="flex-wrap:nowrap;margin-bottom:8px"><span class="icon-tile">${icon('rocket')}</span><div class="grow"><strong>${s.name}</strong><div class="tiny muted">${s.industry ? titleCase(s.industry) : ''}${s.stage ? ` · ${titleCase(s.stage)}` : ''}</div></div></div>
  <p class="small" style="color:var(--k-700)">${s.tagline || ''}</p>
  ${s.looking_for?.length ? html`<div class="chip-row">${s.looking_for.slice(0, 3).map((r) => html`<span class="chip chip--yellow">Seeking ${r}</span>`)}</div>` : ''}
  <div class="tiny muted" style="margin-top:8px">${s.owner ? `by ${s.owner.name}` : ''} · ${s.follower_count} followers${s.allow_ai_analysis ? ' · AI analysis allowed' : ''}</div></a>`;
const personCard = (u) => html`<div class="card">${person(u)}
  ${u.skills?.length ? html`<div class="chip-row" style="margin-top:10px">${u.skills.slice(0, 4).map((s) => html`<span class="chip">${s}</span>`)}</div>` : ''}
  ${u.open_to?.length ? html`<p class="tiny muted" style="margin:8px 0 0">Open to: ${u.open_to.join(', ')}</p>` : ''}
  <a class="btn btn--ghost btn--sm" style="margin-top:10px" href="profile.html?u=${u.handle}">View profile</a></div>`;

async function searchAll(q) {
  const panel = $('[data-panel="all"]');
  if (!q || q.trim().length < 2) {
    const [trending, startups] = await Promise.all([get('/trending'), get('/startups')]).catch((e) => { toastError(e); return [{ posts: [], tags: [] }, { startups: [] }]; });
    render(panel, html`<div class="split"><div><h2>Trending discussions</h2><div id="trend-posts"></div></div>
      <aside class="stack"><div class="card"><h3>Trending tags</h3>${trending.tags.length ? html`<div class="chip-row">${trending.tags.map((t) => html`<a class="chip" href="explore.html?q=%23${t.tag}">#${t.tag} · ${t.posts}</a>`)}</div>` : html`<p class="small muted" style="margin:0">No tags used this week yet.</p>`}</div>
      <div class="card"><h3>Newest public startups</h3>${startups.startups.length ? startups.startups.slice(0, 5).map((s) => html`<a href="startup.html?id=${s.id}" style="display:block;padding:6px 0"><strong>${s.name}</strong> <span class="small muted">${s.tagline}</span></a>`) : html`<p class="small muted" style="margin:0">No public startups yet.</p>`}</div></aside></div>`);
    renderPostList($('#trend-posts'), trending.posts, { me: user, empty: emptyState({ iconName: 'trending', title: 'Quiet week', text: 'Trending shows posts with real engagement in the last 7 days.' }) });
    return;
  }
  render(panel, html`<div class="skeleton sk-block"></div>`);
  try {
    const r = await get(`/search?q=${encodeURIComponent(q.trim())}`);
    render(panel, html`<div class="split"><div><h2>Posts <span class="chip">${r.posts.length}</span></h2><div id="res-posts"></div></div>
      <aside class="stack">
        <div class="card"><h3>People</h3>${r.users.length ? r.users.map((u) => html`<div style="padding:6px 0">${person(u)}</div>`) : html`<p class="small muted" style="margin:0">No people found.</p>`}</div>
        <div class="card"><h3>Startups</h3>${r.startups.length ? r.startups.map((s) => html`<a href="startup.html?id=${s.id}" style="display:block;padding:6px 0"><strong>${s.name}</strong> <span class="small muted">${s.tagline}</span></a>`) : html`<p class="small muted" style="margin:0">No startups found.</p>`}</div>
        <div class="card"><h3>Communities</h3>${r.communities.length ? r.communities.map((c) => html`<a href="community.html?c=${c.slug}" style="display:block;padding:6px 0">${c.name} <span class="small muted">${c.member_count} members</span></a>`) : html`<p class="small muted" style="margin:0">No communities found.</p>`}</div>
        <div class="notice notice--ai">${icon('database')}<div>Looking for companies, not members? Search the <a href="intelligence.html?q=${encodeURIComponent(q)}">market intelligence knowledge base</a>.</div></div>
      </aside></div>`);
    renderPostList($('#res-posts'), r.posts, { me: user, empty: emptyState({ iconName: 'search', title: 'No matching posts', text: 'Try a different word or a #tag.' }) });
  } catch (error) { toastError(error); }
}

async function loadStartups() {
  const q = $('#s-q').value.trim();
  const role = $('#s-role').value.trim();
  try {
    const { startups } = await get(`/startups?q=${encodeURIComponent(q)}&looking_for=${encodeURIComponent(role)}`);
    render($('#startups'), startups.length ? html`${startups.map(startupCard)}` : html`<div style="grid-column:1/-1">${emptyState({ iconName: 'rocket', title: 'No public startups match', text: 'Founders can publish a summary from any report, or create a startup page.', action: html`<a class="btn btn--yellow" href="startup.html?new=1">Share yours</a>` })}</div>`);
  } catch (error) { toastError(error); }
}
async function loadPeople() {
  try {
    const { users } = await get(`/people?q=${encodeURIComponent($('#p-q').value)}&skill=${encodeURIComponent($('#p-skill').value)}&looking_for=${encodeURIComponent($('#p-role').value)}`);
    render($('#people'), users.length ? html`${users.map(personCard)}` : html`<div style="grid-column:1/-1">${emptyState({ iconName: 'users', title: 'No members match', text: 'Try fewer filters.' })}</div>`);
  } catch (error) { toastError(error); }
}

const loaded = new Set();
$$('[role="tab"]').forEach((t) => t.addEventListener('click', () => {
  $$('[role="tab"]').forEach((x) => x.setAttribute('aria-selected', String(x === t)));
  $$('[data-panel]').forEach((p) => p.classList.toggle('hidden', p.dataset.panel !== t.dataset.tab));
  if (!loaded.has(t.dataset.tab)) { loaded.add(t.dataset.tab); if (t.dataset.tab === 'startups') loadStartups(); if (t.dataset.tab === 'people') loadPeople(); }
}));
$('#s-go').addEventListener('click', loadStartups);
$('#p-go').addEventListener('click', loadPeople);
$('#search').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = e.target.q.value;
  history.replaceState(null, '', `explore.html${q ? `?q=${encodeURIComponent(q)}` : ''}`);
  $('[data-tab="all"]').click();
  searchAll(q);
});
searchAll(q0);
