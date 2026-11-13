import { del, get, post } from '../core/api.js';
import { line, meter } from '../core/charts.js';
import { boot } from '../core/shell.js';
import { $, $$, emptyState, fmtDate, html, icon, person, render, storage, timeAgo, titleCase, toast, toastError, withBusy } from '../core/ui.js';

const { page, user } = await boot({ active: 'dashboard', title: 'Workspace' });
const LEGACY_KEY = 'punchstart_reports';

render(page, html`
  <div class="page-head"><div><p class="eyebrow">Workspace</p><h1>Hi ${user.name.split(' ')[0]} — what are we validating?</h1>
    <p>Your private reports, experiments and competitor watchlist, next to the people who can help you build.</p></div>
    <div class="row"><a class="btn btn--ghost" href="feed.html">${icon('feed')} Feed</a><a class="btn btn--yellow" href="analyze.html">${icon('sparkles')} New analysis</a></div></div>
  <div id="legacy"></div>
  <div class="grid grid-4" id="stats">${[1, 2, 3, 4].map(() => html`<div class="card"><div class="skeleton sk-line"></div><div class="skeleton sk-line" style="height:28px;width:50%"></div></div>`)}</div>
  <div class="split" style="margin-top:18px">
    <div class="stack">
      <div class="card"><div class="card-title"><h2>Startup reports</h2><button class="btn btn--ghost btn--sm hidden" id="compare">${icon('compare')} Compare selected</button></div><div id="reports"><div class="skeleton sk-block"></div></div></div>
      <div class="card"><div class="card-title"><h2>Evaluation history</h2><span class="muted small">Overall rubric score per completed report</span></div><div id="history"></div></div>
      <div class="card"><div class="card-title"><h2>Competitor watchlist</h2><a class="small" href="intelligence.html">Find companies →</a></div><div id="watch"></div></div>
    </div>
    <aside class="stack">
      <div class="card card--ai" id="recs"><div class="ai-mark">${icon('sparkles')} NEXT STEPS FROM YOUR LATEST REPORT</div><div class="skeleton sk-line" style="margin-top:10px"></div></div>
      <div class="card" id="profile-nudge"></div>
      <div class="card"><div class="card-title"><h3>Founders to meet</h3><a class="small" href="network.html">See all</a></div><div id="people"><div class="skeleton sk-line"></div></div></div>
    </aside>
  </div>`);

// ---------------------------------------------------------- preserve previous-version data
const legacy = storage(LEGACY_KEY, []);
if (Array.isArray(legacy) && legacy.length) {
  render($('#legacy'), html`<div class="notice" style="margin-bottom:18px">${icon('database')}<div class="grow"><strong>${legacy.length} report${legacy.length === 1 ? '' : 's'} from the previous PunchStart version are saved in this browser</strong>
    Import them into your account so they're not lost. They'll be marked as legacy (generated without sources), and you can re-run any of them with the new engine.
    <div class="row" style="margin-top:10px"><button class="btn btn--sm" id="import-legacy" data-busy="Importing">Import ${legacy.length}</button><button class="btn btn--quiet btn--sm" id="dismiss-legacy">Not now</button></div></div></div>`);
  $('#import-legacy').addEventListener('click', (e) => withBusy(e.currentTarget, async () => {
    try {
      const reports = legacy.slice(0, 20).map((r) => ({ startup_name: String(r.startup_name || 'Imported report').slice(0, 120), industry: String(r.industry || '').slice(0, 80),
        created_at: String(r.created_at || ''), startup_score: Number.isFinite(Number(r.startup_score)) ? Number(r.startup_score) : null, data: r }));
      const res = await post('/reports/import-legacy', { reports });
      localStorage.removeItem(LEGACY_KEY);
      toast(`Imported ${res.imported} report(s)`);
      location.reload();
    } catch (error) { toastError(error); }
  }));
  $('#dismiss-legacy').addEventListener('click', () => { $('#legacy').innerHTML = ''; });
}

// ---------------------------------------------------------------------- data
const [{ reports }, watch, people] = await Promise.all([
  get('/reports').catch((e) => { toastError(e); return { reports: [] }; }),
  get('/watchlist').catch(() => ({ items: [] })),
  get('/people/suggestions').catch(() => ({ people: [], profile_complete: true })),
]);
const scored = reports.filter((r) => !r.legacy && r.score != null && ['complete', 'partial'].includes(r.status));
const avg = scored.length ? Math.round(scored.reduce((s, r) => s + r.score, 0) / scored.length) : null;
const v = reports.reduce((acc, r) => { Object.entries(r.validation || {}).forEach(([k, n]) => { acc[k] = (acc[k] || 0) + n; }); return acc; }, {});
const vTotal = Object.values(v).reduce((a, b) => a + b, 0);

render($('#stats'), html`
  <div class="card card--ink stat rise"><span class="stat-label">Reports</span><span class="stat-value">${reports.length}</span><span class="stat-note" style="color:var(--k-300)">${scored.length} scored by the current engine</span></div>
  <div class="card stat rise"><span class="stat-label">Average rubric score</span><span class="stat-value">${avg ?? '—'}</span><span class="stat-note">${avg == null ? 'Run an analysis to see one' : 'Across current-engine reports'}</span></div>
  <div class="card stat rise"><span class="stat-label">Experiments validated</span><span class="stat-value">${v.validated || 0}<span class="muted" style="font-size:1rem"> / ${vTotal}</span></span><span class="stat-note">${v.invalidated || 0} invalidated · ${v.running || 0} running</span></div>
  <div class="card stat rise"><span class="stat-label">Competitors watched</span><span class="stat-value">${watch.items.length}</span><span class="stat-note">From knowledge-base companies</span></div>`);

const selected = new Set();
if (!reports.length) {
  render($('#reports'), emptyState({ iconName: 'sparkles', title: 'No reports yet', text: 'Describe an idea and get a sourced, explainable analysis in a few minutes.', action: html`<a class="btn btn--yellow" href="analyze.html">Analyze your first idea</a>` }));
} else {
  render($('#reports'), html`<div class="table-wrap"><table class="data"><thead><tr><th style="width:32px"><span class="sr-only">Compare</span></th><th>Report</th><th>Score</th><th>Validation</th><th>Created</th></tr></thead><tbody>
    ${reports.map((r) => {
      const vt = Object.values(r.validation || {}).reduce((a, b) => a + b, 0);
      return html`<tr>
        <td>${!r.legacy && r.score != null ? html`<input type="checkbox" data-pick="${r.id}" aria-label="Select ${r.title} for comparison">` : ''}</td>
        <td><a href="results.html?id=${r.id}"><strong>${r.title}</strong></a>
          <div class="tiny muted">${r.sector ? titleCase(r.sector) : ''}${r.legacy ? ' · legacy import' : ''}${['queued', 'running'].includes(r.status) ? ` · in progress (${r.progress}%)` : ''}${r.status === 'partial' ? ' · partial' : ''}${r.status === 'failed' ? ' · failed' : ''}</div></td>
        <td style="min-width:120px">${r.score != null ? html`<div class="row" style="flex-wrap:nowrap"><strong>${r.score}</strong>${meter(r.score, 100, true)}</div>` : html`<span class="muted">—</span>`}</td>
        <td class="small">${vt ? `${r.validation.validated || 0}/${vt} validated` : html`<span class="muted">—</span>`}</td>
        <td class="small muted nowrap">${timeAgo(r.created_at)}</td></tr>`;
    })}</tbody></table></div>`);
  $('#reports').addEventListener('change', (e) => {
    const cb = e.target.closest('[data-pick]');
    if (!cb) return;
    if (cb.checked) selected.add(cb.dataset.pick); else selected.delete(cb.dataset.pick);
    if (selected.size > 4) { cb.checked = false; selected.delete(cb.dataset.pick); toast('Compare up to 4 reports', 'error'); }
    $('#compare').classList.toggle('hidden', selected.size < 2);
  });
  $('#compare').addEventListener('click', () => { location.href = `compare.html?ids=${[...selected].join(',')}`; });
}

const history = [...scored].reverse();
if (history.length) {
  line($('#history'), history.map((r) => ({ label: `${r.title.slice(0, 18)} (${fmtDate(r.created_at)})`, value: r.score, href: `results.html?id=${r.id}` })),
    { caption: 'Overall rubric score per report, oldest to newest' });
} else render($('#history'), html`<p class="muted small" style="margin:0">Your score history appears after your first completed analysis.</p>`);

function drawWatch(items) {
  render($('#watch'), items.length ? html`${items.map((w) => html`<div class="source-item" style="grid-template-columns:44px minmax(0,1fr) auto">
      <span class="icon-tile icon-tile--yellow" style="width:40px;height:40px">${icon('eye')}</span>
      <div><strong>${w.name}</strong>${w.company ? html`<div class="small muted">${w.company.description || ''}</div>
        <div class="tiny muted">${titleCase(w.company.status)}${w.company.first_launch ? ` · launched ${w.company.first_launch}` : ''}${w.company.shutdown_date ? ` · shutdown announced ${w.company.shutdown_date}` : ''}
        ${w.company.documents?.length ? html` · <a href="${w.company.documents[w.company.documents.length - 1].url}" target="_blank" rel="noopener noreferrer">latest post</a>` : ''}</div>`
        : html`<div class="small muted">No longer in the current knowledge-base snapshot.</div>`}</div>
      <button class="icon-btn" data-unwatch="${w.id}" aria-label="Stop watching ${w.name}">${icon('x')}</button></div>`)}`
    : html`<p class="muted small" style="margin:0">Watch competitors from a report's Evidence tab or from Market intelligence.</p>`);
}
drawWatch(watch.items);
$('#watch').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-unwatch]');
  if (!b) return;
  try { await del(`/watchlist/${b.dataset.unwatch}`); drawWatch((await get('/watchlist')).items); } catch (error) { toastError(error); }
});

// latest recommendations (real report content)
const latest = scored[0];
if (latest) {
  get(`/reports/${latest.id}`).then((full) => {
    const recs = full.result?.sections?.final_recommendations;
    const points = (recs?.points || []).slice(0, 4);
    render($('#recs'), html`<div class="ai-mark">${icon('sparkles')} NEXT STEPS · ${latest.title}</div>
      ${points.length ? html`<ol class="small" style="padding-left:18px;margin:10px 0">${points.map((p) => html`<li style="margin-bottom:6px">${p.text}</li>`)}</ol>`
        : html`<p class="small muted">Recommendations were not generated for this report.</p>`}
      <a class="small" href="results.html?id=${latest.id}">Open report →</a>`);
  }).catch(() => {});
} else render($('#recs'), html`<div class="ai-mark">${icon('sparkles')} NEXT STEPS</div><p class="small muted" style="margin:8px 0 0">Run an analysis to get prioritized recommendations and validation experiments.</p>`);

if (!people.profile_complete) {
  render($('#profile-nudge'), html`<h3>Complete your profile</h3><p class="small muted">Add your skills, interests and what you're looking for — recommendations for co-founders and communities depend on it.</p><a class="btn btn--sm" href="settings.html">Edit profile</a>`);
} else $('#profile-nudge').remove();
render($('#people'), people.people.length ? html`${people.people.slice(0, 4).map((p) => html`<div style="padding:8px 0;border-bottom:1px solid var(--line-soft)">${person(p.user)}<div class="tiny muted" style="margin:4px 0 0 51px">${p.reasons[0] || ''}</div></div>`)}`
  : html`<p class="small muted" style="margin:0">${people.profile_complete ? 'No strong matches yet — explore communities to meet founders.' : 'No matches yet — add interests and skills to your profile, or explore communities.'}</p>`);
void $$;
