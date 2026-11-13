import { get } from '../core/api.js';
import { meter } from '../core/charts.js';
import { boot } from '../core/shell.js';
import { emptyState, fmtDate, html, icon, param, render, titleCase } from '../core/ui.js';

const { page } = await boot({ active: 'dashboard', title: 'Compare reports' });
const ids = param('ids') || '';

try {
  const { reports } = await get(`/reports-compare?ids=${encodeURIComponent(ids)}`);
  const dims = Object.entries(reports[0].dimensions);
  const best = (key) => Math.max(...reports.map((r) => r.dimensions[key].score));
  render(page, html`
    <div class="page-head"><div><p class="eyebrow">Comparison</p><h1>Compare ${reports.length} ideas</h1>
      <p>Same rubric, same weights. Highest score per row is marked. Scores are rule-based and comparable only because they use the same rules.</p></div>
      <a class="btn btn--ghost" href="dashboard.html">${icon('back')} Workspace</a></div>
    <div class="card" style="padding:0;overflow:hidden"><div class="table-wrap" style="margin:0;border:0;border-radius:0"><table class="data">
      <thead><tr><th>Dimension</th>${reports.map((r) => html`<th><a href="results.html?id=${r.id}">${r.title}</a><div class="tiny muted" style="text-transform:none;letter-spacing:0">${fmtDate(r.created_at)}</div></th>`)}</tr></thead>
      <tbody>
        <tr><td><strong>Overall</strong></td>${reports.map((r) => html`<td><strong style="font-size:1.3rem;font-family:var(--font-display)">${r.overall}</strong><span class="muted">/100 · ${r.confidence}</span></td>`)}</tr>
        <tr><td>Verdict</td>${reports.map((r) => html`<td>${r.verdict ? html`<span class="chip chip--ink">${r.verdict}</span>` : html`<span class="muted">—</span>`}</td>`)}</tr>
        <tr><td>Sector (predicted)</td>${reports.map((r) => html`<td>${r.sector ? titleCase(r.sector) : '—'}</td>`)}</tr>
        ${dims.map(([key, d]) => html`<tr><td>${d.label}</td>${reports.map((r) => {
          const s = r.dimensions[key].score;
          return html`<td style="min-width:160px"><div class="row" style="flex-wrap:nowrap"><strong style="width:30px">${s}</strong>${meter(s, 10, s === best(key))}${s === best(key) && reports.length > 1 ? html`<span class="tiny" title="Highest">${icon('star')}</span>` : ''}</div></td>`;
        })}</tr>`)}
        <tr><td>Direct competitors found</td>${reports.map((r) => html`<td class="small">${r.direct_competitors.length ? r.direct_competitors.join(', ') : html`<span class="muted">none in knowledge base</span>`}</td>`)}</tr>
        <tr><td>Market sizing (estimates)</td>${reports.map((r) => html`<td class="small">${r.market_sizing.length ? r.market_sizing.map((m) => html`<div>${m.label}: ${m.value}</div>`) : html`<span class="muted">—</span>`}</td>`)}</tr>
      </tbody></table></div></div>
    <p class="tiny muted" style="margin-top:10px">Darker bars mark the highest score in each row. Market sizes are model estimates with stated assumptions, not sourced figures.</p>`);
} catch (error) {
  render(page, emptyState({ iconName: 'compare', title: 'Nothing to compare', text: error.message, action: html`<a class="btn" href="dashboard.html">Choose reports</a>` }));
}
