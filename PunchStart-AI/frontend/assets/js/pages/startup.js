import { del, get, patch, post } from '../core/api.js';
import { meter } from '../core/charts.js';
import { composer, renderPostList, reportDialog } from '../core/posts.js';
import { boot } from '../core/shell.js';
import { $, confirmDialog, emptyState, fmtDate, html, icon, modal, param, person, raw, render, richText, tagsInput, titleCase, toast,
  toastError, withBusy } from '../core/ui.js';

const { page, user } = await boot({ active: 'explore', title: 'Startup' });
const id = param('id');

function form(s = {}) {
  return html`<div class="stack">
    <div class="field"><label for="f-name">Name</label><input class="input" id="f-name" maxlength="100" value="${s.name || ''}" required></div>
    <div class="field"><label for="f-tag">One-line pitch</label><input class="input" id="f-tag" maxlength="160" value="${s.tagline || ''}"></div>
    <div class="field"><label for="f-desc">Description</label><textarea class="textarea" id="f-desc" maxlength="5000">${s.description || ''}</textarea></div>
    <div class="grid grid-2"><div class="field"><label for="f-prob">Problem</label><textarea class="textarea" id="f-prob" maxlength="2000">${s.problem || ''}</textarea></div>
      <div class="field"><label for="f-sol">Solution</label><textarea class="textarea" id="f-sol" maxlength="2000">${s.solution || ''}</textarea></div></div>
    <div class="grid grid-2"><div class="field"><label for="f-ind">Industry</label><input class="input" id="f-ind" maxlength="60" value="${s.industry || ''}"></div>
      <div class="field"><label for="f-stage">Stage</label><input class="input" id="f-stage" maxlength="40" value="${s.stage || ''}" placeholder="idea, MVP, beta…"></div></div>
    <div class="field"><label for="f-web">Website</label><input class="input" id="f-web" maxlength="300" value="${s.website || ''}" placeholder="https://"></div>
    <div class="field"><span class="label">Looking for</span><div id="f-look"></div></div>
    <div class="field"><span class="label">Visibility</span><select class="select" id="f-vis"><option value="private">Private — only you</option><option value="public" ${s.visibility === 'public' ? raw('selected') : ''}>Public — discoverable by members</option></select></div>
    <label class="check"><input type="checkbox" id="f-ai" ${s.allow_ai_analysis ? raw('checked') : ''}> Allow members to run a StartPunch analysis on the public description</label></div>`;
}
function readForm(m, looking) {
  return { name: $('#f-name', m).value, tagline: $('#f-tag', m).value, description: $('#f-desc', m).value, problem: $('#f-prob', m).value,
    solution: $('#f-sol', m).value, industry: $('#f-ind', m).value, stage: $('#f-stage', m).value, website: $('#f-web', m).value,
    looking_for: looking.get(), visibility: $('#f-vis', m).value, allow_ai_analysis: $('#f-ai', m).checked };
}

if (param('new')) {
  render(page, html`<div class="page-head"><div><p class="eyebrow">Startup page</p><h1>Share your startup</h1><p>Create a page to share progress, attract collaborators and get feedback. Keep it private until you're ready.</p></div></div>
    <form class="card" id="create" style="max-width:760px">${form()}<p class="form-error" role="alert"></p><button class="btn btn--yellow" data-busy="Creating">Create startup page</button></form>`);
  const looking = tagsInput($('#f-look'), [], { placeholder: 'e.g. co-founder, designer' });
  $('#create').addEventListener('submit', async (e) => {
    e.preventDefault();
    await withBusy($('button[data-busy]', e.target), async () => {
      try { const r = await post('/startups', readForm(e.target, looking)); location.href = `startup.html?id=${r.id}`; }
      catch (error) { $('.form-error', e.target).textContent = error.message; }
    });
  });
} else load();

async function load() {
  let s;
  try { s = await get(`/startups/${encodeURIComponent(id || '')}`); }
  catch (error) { render(page, emptyState({ iconName: 'rocket', title: 'Startup not found', text: 'It may be private or removed.', action: html`<a class="btn" href="explore.html">Explore startups</a>` })); return; }
  document.title = `${s.name} · StartPunch`;
  const summary = s.public_summary || {};
  render(page, html`
    <div class="card card--yellow" style="margin-bottom:18px">
      <div class="row between"><div class="row" style="flex-wrap:nowrap"><span class="icon-tile" style="width:56px;height:56px">${icon('rocket')}</span>
        <div><h1 style="margin:0">${s.name}</h1><p style="margin:2px 0 0;font-weight:600">${s.tagline}</p></div></div>
        <div class="row">
          ${s.visibility === 'private' ? html`<span class="chip chip--ink">${icon('lock')} Private</span>` : ''}
          ${s.is_owner ? html`<button class="btn btn--ghost" id="edit">${icon('edit')} Edit</button>` : html`
            <button class="btn ${s.following ? 'btn--ghost' : ''}" id="follow">${s.following ? 'Following' : 'Follow'}</button>
            ${s.my_request ? html`<span class="chip">${titleCase(s.my_request.status)}: ${s.my_request.role}</span>` : html`<button class="btn btn--ghost" id="join">${icon('userplus')} Request to join</button>`}
            <button class="icon-btn" id="report" aria-label="Report">${icon('flag')}</button>`}
        </div></div>
      <div class="row small" style="margin-top:12px;gap:14px">${s.industry ? html`<span><b>Industry:</b> ${titleCase(s.industry)}</span>` : ''}${s.stage ? html`<span><b>Stage:</b> ${titleCase(s.stage)}</span>` : ''}
        <span><b>${s.follower_count}</b> followers</span>${s.website ? html`<a href="${s.website}" target="_blank" rel="noopener noreferrer nofollow">${icon('globe')} Website</a>` : ''}</div>
    </div>
    <div class="split"><div class="stack">
      ${s.description || s.problem || s.solution ? html`<div class="card">${s.description ? html`<div class="post-body">${richText(s.description)}</div>` : ''}
        ${s.problem ? html`<h3 style="margin-top:14px">Problem</h3><p class="post-body">${s.problem}</p>` : ''}${s.solution ? html`<h3>Solution</h3><p class="post-body">${s.solution}</p>` : ''}</div>` : ''}
      <h2>Updates & discussion</h2>
      <div id="composer"></div><div id="updates"></div></div>
      <aside class="stack">
        <div class="card"><h3>Founder</h3>${person(s.owner)}</div>
        ${s.looking_for.length ? html`<div class="card card--ink"><h3 style="color:#fff">Looking for</h3><div class="chip-row">${s.looking_for.map((r) => html`<span class="chip chip--yellow">${r}</span>`)}</div></div>` : ''}
        ${summary.score != null || summary.dimensions ? html`<div class="card"><h3>StartPunch evaluation</h3>
          ${summary.score != null ? html`<div class="stat"><span class="stat-value">${summary.score}/100</span><span class="stat-note">${summary.score_note || ''}</span></div>` : ''}
          ${summary.dimensions ? html`<div style="margin-top:10px">${summary.dimensions.map((d) => html`<div class="dim-row" style="cursor:default"><span class="small">${d.label}</span>${meter(d.score)}<span class="small">${d.score}</span></div>`)}</div>` : ''}
          <p class="tiny muted" style="margin:6px 0 0">Shared by the founder on ${fmtDate(summary.published_at)}.</p></div>` : ''}
        ${s.allow_ai_analysis || s.is_owner ? html`<div class="card card--ai"><div class="ai-mark">${icon('sparkles')} ANALYZE THIS OPPORTUNITY</div>
          <p class="small" style="margin:8px 0">${s.is_owner ? 'Run a fresh analysis from this page\'s public description.' : 'The founder allows members to analyze the public description. Your report is private to you.'}</p>
          <button class="btn btn--ai btn--sm" id="analyze" data-busy="Starting">${icon('sparkles')} Run analysis</button></div>` : ''}
        ${s.is_owner ? html`<div class="card"><h3>Collaboration requests ${s.pending_requests ? html`<span class="chip chip--ai">${s.pending_requests} new</span>` : ''}</h3><div id="requests"><div class="skeleton sk-line"></div></div></div>
          <button class="btn btn--quiet btn--sm" id="delete">${icon('trash')} Delete startup page</button>` : ''}
      </aside></div>`);

  renderPostList($('#updates'), s.updates, { me: user, empty: emptyState({ iconName: 'trending', title: 'No updates yet', text: s.is_owner ? 'Post progress, milestones and questions to keep followers engaged.' : 'Follow to hear about progress.' }) });
  if (s.is_owner) {
    composer($('#composer'), user, { startupId: s.id, onPosted: load, placeholder: `Share a progress update for ${s.name}…` });
    const { requests } = await get(`/startups/${s.id}/collab-requests`);
    render($('#requests'), requests.length ? html`${requests.map((r) => html`<div style="padding:8px 0;border-top:1px solid var(--line-soft)">${person(r.user, `wants to join as ${r.role}`)}
      ${r.message ? html`<p class="small" style="margin:6px 0">${r.message}</p>` : ''}
      ${r.status === 'pending' ? html`<div class="row"><button class="btn btn--sm" data-respond="${r.id}" data-accept="1">Accept</button><button class="btn btn--sm btn--ghost" data-respond="${r.id}" data-accept="">Decline</button></div>` : html`<span class="chip">${titleCase(r.status)}</span>`}</div>`)}`
      : html`<p class="small muted" style="margin:0">No requests yet. Add roles to "Looking for" so members know how to help.</p>`);
    $('#requests').addEventListener('click', async (e) => {
      const b = e.target.closest('[data-respond]');
      if (!b) return;
      try { await post(`/collab-requests/${b.dataset.respond}/respond`, { accept: Boolean(b.dataset.accept) }); toast(b.dataset.accept ? 'Accepted — you can now message each other' : 'Declined'); load(); } catch (error) { toastError(error); }
    });
    $('#edit').addEventListener('click', () => {
      let looking;
      modal({ title: 'Edit startup page', wide: true, body: form(s), onOpen: (m) => { looking = tagsInput($('#f-look', m), s.looking_for); },
        actions: [{ label: 'Cancel', kind: 'btn--ghost' }, { label: 'Save', kind: 'btn--yellow', onClick: async (m) => { await patch(`/startups/${s.id}`, readForm(m, looking)); toast('Saved'); load(); } }] });
    });
    $('#delete').addEventListener('click', async () => {
      if (await confirmDialog('Delete this startup page? Updates stay on your profile.', { confirm: 'Delete' })) { await del(`/startups/${s.id}`); location.href = 'dashboard.html'; }
    });
  } else {
    $('#follow').addEventListener('click', async () => { try { await (s.following ? del(`/startups/${s.id}/follow`) : post(`/startups/${s.id}/follow`)); load(); } catch (error) { toastError(error); } });
    $('#join')?.addEventListener('click', () => modal({ title: `Join ${s.name}`, body: html`<div class="field"><label for="jr">Role</label><input class="input" id="jr" maxlength="60" placeholder="${s.looking_for[0] || 'e.g. designer'}"></div>
      <div class="field"><label for="jm">Message</label><textarea class="textarea" id="jm" maxlength="1500" placeholder="What you'd bring and why this excites you"></textarea></div>`,
      actions: [{ label: 'Cancel', kind: 'btn--ghost' }, { label: 'Send request', kind: 'btn--yellow', onClick: async (m) => {
        if (!$('#jr', m).value.trim()) { toast('Add the role you want', 'error'); return true; }
        await post(`/startups/${s.id}/collaborate`, { role: $('#jr', m).value, message: $('#jm', m).value }); toast('Request sent to the founder'); load();
      } }] }));
    $('#report').addEventListener('click', () => reportDialog('startup', s.id));
  }
  $('#analyze')?.addEventListener('click', (e) => withBusy(e.currentTarget, async () => {
    try { const r = await post(`/startups/${s.id}/analyze`); location.href = `results.html?id=${r.id}`; } catch (error) { toastError(error); }
  }));
}
