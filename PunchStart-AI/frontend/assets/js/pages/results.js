import { apiUrl, del, get, patch, post } from '../core/api.js';
import { meter, scoreRing } from '../core/charts.js';
import { boot } from '../core/shell.js';
import { $, $$, confirmDialog, emptyState, esc, fmtDate, html, icon, modal, param, raw, render, tagsInput, timeAgo, titleCase, toast,
  toastError, withBusy } from '../core/ui.js';

const BASIS = { fact: 'Fact', founder_input: 'Founder input', estimate: 'Estimate', assumption: 'Assumption', recommendation: 'Recommendation', unverified: 'Unverified' };
const GROUP_LABEL = { synthesis: 'Summary', market: 'Opportunity', competition: 'Competition', business: 'Business', build: 'Build', risk: 'Risks & next steps' };
const SECTION_GROUP = {
  executive_summary: 'synthesis', final_recommendations: 'synthesis',
  problem_analysis: 'market', proposed_solution: 'market', target_audience: 'market', customer_personas: 'market', market_research: 'market', market_sizing: 'market', market_trends: 'market',
  competitor_analysis: 'competition', direct_competitors: 'competition', indirect_competitors: 'competition', competitor_comparison: 'competition', swot: 'competition', pestle: 'competition',
  business_model: 'business', revenue_streams: 'business', pricing_strategy: 'business', unit_economics: 'business', customer_acquisition: 'business', go_to_market: 'business', marketing_strategy: 'business',
  product_roadmap: 'build', technical_architecture: 'build', technology_stack: 'build', development_cost: 'build', operational_requirements: 'build', funding_requirements: 'build', financial_projections: 'build',
  risk_analysis: 'risk', regulatory_compliance: 'risk', validation_experiments: 'risk', mvp_scope: 'risk', growth_strategy: 'risk', long_term_roadmap: 'risk',
};
const STAGE_ORDER = ['understand', 'research', 'write', 'synthesize', 'complete'];
const STAGE_TEXT = {
  understand: ['Understanding the idea', 'Trained classifiers predict sector and business model; AI extracts structured signals with quotes from your text.'],
  research: ['Researching the knowledge base', 'Hybrid keyword + semantic search, then AI grades each match as direct, indirect or unrelated. Rubric scoring.'],
  write: ['Writing the report', 'Five section groups are written in parallel from the retrieved evidence only.'],
  synthesize: ['Synthesizing & validating', 'Executive summary, final verdict, and automatic citation checks.'],
};

const { page, user } = await boot({ active: 'dashboard', title: 'Startup report' });
const reportId = param('id');
let report = null;

if (!reportId) {
  render(page, emptyState({ iconName: 'file', title: 'No report selected', text: 'Open a report from your workspace or start a new analysis.', action: html`<a class="btn btn--yellow" href="analyze.html">New analysis</a>` }));
} else {
  load();
}

async function load() {
  try {
    report = await get(`/reports/${reportId}`);
  } catch (error) {
    render(page, emptyState({ iconName: 'alert', title: 'Report not available', text: error.message, action: html`<a class="btn" href="dashboard.html">Back to workspace</a>` }));
    return;
  }
  document.title = `${report.title} · StartPunch`;
  if (['queued', 'running'].includes(report.status)) return runPipeline();
  if (report.status === 'failed') return renderFailed();
  if (report.legacy) return renderLegacy();
  renderReport();
}

// ------------------------------------------------------------------- pipeline
function drawProgress(status) {
  const current = STAGE_ORDER.indexOf(status.stage);
  render(page, html`<div class="page-head"><div><p class="eyebrow">Analysis in progress</p><h1>${report.title}</h1>
    <p>Keep this tab open — each step runs on our servers and reports real progress. If you leave, it resumes when you return.</p></div></div>
    <div class="card" style="max-width:760px">
      <div class="row between"><strong>${status.stage_label || 'Starting'}</strong><span class="muted small">${status.progress}%</span></div>
      <div class="progress" style="margin-top:10px" role="progressbar" aria-valuenow="${status.progress}" aria-valuemin="0" aria-valuemax="100"><span style="width:${status.progress}%"></span></div>
      <ul class="pipeline">${Object.entries(STAGE_TEXT).map(([key, [title, text]], i) => {
        const state = i < current ? 'done' : i === current ? 'active' : '';
        return html`<li class="${state}"><span class="state">${state === 'done' ? icon('check') : state === 'active' ? raw('<span class="spinner" style="width:13px;height:13px"></span>') : i + 1}</span>
          <div><div style="font-weight:600">${title}</div><div class="small muted">${text}</div>
          ${key === 'write' && status.groups && Object.keys(status.groups).length ? html`<div class="chip-row" style="margin-top:6px">${Object.entries(status.groups).map(([g, s]) => html`<span class="chip ${s.status === 'done' ? 'chip--ink' : ''}">${GROUP_LABEL[g] || g}: ${s.status || 'pending'}</span>`)}</div>` : ''}
          </div></li>`;
      })}</ul></div>`);
}

async function runPipeline() {
  let status = report.status_detail;
  drawProgress(status);
  let busyStreak = 0;
  for (let i = 0; i < 20; i++) {
    try {
      status = await post(`/reports/${reportId}/advance`);
    } catch (error) {
      toastError(error);
      await new Promise((r) => setTimeout(r, 4000));
      continue;
    }
    drawProgress(status);
    if (['complete', 'partial', 'failed'].includes(status.status)) break;
    if (status.busy) { busyStreak += 1; await new Promise((r) => setTimeout(r, Math.min(8000, 2500 * busyStreak))); } else busyStreak = 0;
  }
  report = await get(`/reports/${reportId}`);
  if (report.status === 'failed') renderFailed();
  else if (['queued', 'running'].includes(report.status)) {
    render(page, emptyState({ iconName: 'alert', title: 'Still working', text: 'The analysis is taking longer than expected. Refresh to continue.', action: html`<a class="btn" href="results.html?id=${reportId}">Continue</a>` }));
  } else renderReport();
}

function renderFailed() {
  render(page, emptyState({ iconName: 'alert', title: 'The analysis could not finish', text: `${report.error || 'An unexpected error occurred.'} Nothing was invented — you can run it again.`,
    action: html`<a class="btn btn--yellow" href="analyze.html?prefill=${encodeURIComponent(JSON.stringify(report.input))}">Run again</a>` }));
}

function renderLegacy() {
  const old = report.result?.legacy_payload || {};
  render(page, html`<div class="page-head"><div><p class="eyebrow">Imported report</p><h1>${report.title}</h1></div>
    <button class="btn btn--ghost" id="del">${icon('trash')} Delete</button></div>
    <div class="notice" style="margin-bottom:16px">${icon('info')}<div><strong>Generated by the previous PunchStart engine</strong>
    This report was imported from your browser. It was produced without retrieval, sources or the current rubric, and may contain template text. Re-run it to get an evidence-backed analysis.</div></div>
    <div class="card stack">
      ${report.score != null ? html`<p><b>Previous score:</b> ${report.score}/100 (old heuristic)</p>` : ''}
      ${['executive_summary', 'market_analysis', 'revenue_strategy', 'go_to_market_strategy', 'funding_recommendation'].filter((k) => old[k]).map((k) => html`<div><h3>${titleCase(k)}</h3><p>${old[k]}</p></div>`)}
      <a class="btn btn--yellow" href="analyze.html?prefill=${encodeURIComponent(JSON.stringify({ idea: report.input?.idea || '', name: report.title }))}">${icon('sparkles')} Re-run with the new engine</a>
    </div>`);
  $('#del').addEventListener('click', deleteReport);
}

// ------------------------------------------------------------------- report
function basisBadge(basis) {
  return html`<span class="basis basis--${basis}" title="${basis === 'unverified' ? 'Stated as a fact but not supported by cited evidence' : ''}">${BASIS[basis] || basis}</span>`;
}
function cites(sources) {
  return html`${(sources || []).map((s) => html`<a class="cite" href="#src-${s}" data-cite="${s}">${s}</a>`)}`;
}

function sectionHtml(key, s) {
  const unavailable = s.unavailable;
  return html`<section class="card section" id="sec-${key}">
    <h2>${s.title || titleCase(key)} ${s.confidence && !unavailable ? html`<span class="chip">${titleCase(s.confidence)} confidence</span>` : ''}</h2>
    ${unavailable ? html`<div class="notice">${icon('info')}<div>${s.summary}</div></div>` : html`
      <p class="summary">${s.summary}</p>
      ${s.metrics?.length ? html`<div class="metrics">${s.metrics.map((m) => html`<div class="metric"><div class="label">${m.label}</div><div class="value">${m.value}</div>${basisBadge(m.basis)}${m.note ? html`<div class="note">${m.note}</div>` : ''}</div>`)}</div>` : ''}
      ${s.groups?.length ? html`<div class="groups">${s.groups.map((g) => html`<div class="group"><h4>${g.label}</h4><ul>${g.items.map((it) => html`<li>${it}</li>`)}</ul></div>`)}</div>` : ''}
      ${s.table?.columns?.length ? html`<div class="table-wrap"><table class="data"><thead><tr>${s.table.columns.map((c) => html`<th>${c}</th>`)}</tr></thead>
        <tbody>${s.table.rows.map((r) => html`<tr>${r.map((c) => html`<td>${c}</td>`)}</tr>`)}</tbody></table></div>` : ''}
      ${s.points?.length ? html`<ul class="points">${s.points.map((p) => html`<li>${basisBadge(p.basis)}<div>${p.text}${cites(p.sources)}
        ${p.basis === 'unverified' && p.validation ? html`<div class="check-flag">Check failed: ${p.validation.join('; ')}</div>` : ''}</div></li>`)}</ul>` : ''}
      ${s.missing?.length ? html`<p class="missing"><strong>Missing data:</strong> ${s.missing.join(' · ')}</p>` : ''}`}
  </section>`;
}

function renderReport() {
  const r = report.result;
  const scores = r.scores;
  const verdict = (r.sections.final_recommendations?.metrics || []).find((m) => (m.label || '').toLowerCase() === 'verdict');
  const sector = r.classification?.sector?.top || [];
  const bm = r.classification?.business_model?.top || [];
  const cluster = r.classification?.cluster;
  const groups = {};
  r.section_order.forEach((k) => { const g = SECTION_GROUP[k] || 'synthesis'; (groups[g] ||= []).push(k); });

  render(page, html`
    <div class="page-head">
      <div><p class="eyebrow">Startup report · ${fmtDate(report.created_at)}</p><h1>${report.title}</h1>
        <p>${r.signals?.one_liner || ''}</p></div>
      <div class="row no-print">
        <a class="btn btn--ghost btn--sm" href="${apiUrl(`/reports/${reportId}/export?format=md`)}">${icon('download')} Markdown</a>
        <a class="btn btn--ghost btn--sm" href="${apiUrl(`/reports/${reportId}/export?format=json`)}">${icon('download')} JSON</a>
        <button class="btn btn--ghost btn--sm" id="print">${icon('print')} PDF</button>
        <button class="btn btn--yellow btn--sm" id="publish">${icon('globe')} Publish summary</button>
        <button class="icon-btn" id="del" aria-label="Delete report">${icon('trash')}</button>
      </div>
    </div>
    ${report.status === 'partial' ? html`<div class="notice" style="margin-bottom:16px">${icon('alert')}<div><strong>Partial report</strong>Some sections could not be generated (AI quota, timeout or configuration) and are marked as unavailable — nothing was filled in with placeholder text. Retrieval and scoring are complete.</div></div>` : ''}
    <div class="grid" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);margin-bottom:18px" id="hero-grid">
      <div class="card score-hero">
        ${scoreRing(scores.overall)}
        <div class="stack">
          <div class="row">${verdict ? html`<span class="chip chip--ink">${icon('target')} ${verdict.value}</span>` : ''}<span class="chip">${titleCase(scores.confidence)} confidence</span></div>
          <p class="small muted" style="margin:0">${scores.method}</p>
          <div class="row small"><a href="#" data-tab-link="scores">See all 13 dimensions →</a></div>
        </div>
      </div>
      <div class="card card--ai stack">
        <div class="ai-mark">${icon('layers')} MODEL CLASSIFICATION</div>
        ${sector.length ? html`<div><span class="label">Sector</span><div class="chip-row" style="margin-top:4px">${sector.map((t, i) => html`<span class="chip ${i === 0 ? 'chip--ai' : ''}">${t.description || titleCase(t.label)}${t.probability != null ? ` · ${Math.round(t.probability * 100)}%` : ''}</span>`)}</div></div>` : ''}
        ${bm.length ? html`<div><span class="label">Business model</span><div class="chip-row" style="margin-top:4px">${bm.slice(0, 2).map((t, i) => html`<span class="chip ${i === 0 ? 'chip--ai' : ''}">${titleCase(t.label)} · ${Math.round(t.probability * 100)}%</span>`)}</div></div>` : ''}
        ${cluster ? html`<div class="small"><span class="label">Nearest market cluster</span><br>${cluster.top_terms.slice(0, 5).join(', ')} <span class="muted">(${cluster.size} entities)</span></div>` : ''}
        <p class="tiny muted" style="margin:0">Predicted by ${r.classification?.sector?.model || 'rules'}${r.classification?.sector?.heldout?.macro_f1 ? ` (hold-out macro-F1 ${r.classification.sector.heldout.macro_f1} vs. LLM labels)` : ''}. Predictions, not ground truth.</p>
      </div>
    </div>
    <div class="tabs no-print" role="tablist">
      ${[['report', 'Report'], ['scores', 'Score breakdown'], ['evidence', 'Evidence & sources', r.evidence.sources.length], ['assistant', 'AI assistant'], ['validate', 'Validation tracker']]
        .map(([id, label, count], i) => html`<button class="tab" role="tab" data-tab="${id}" aria-selected="${i === 0}">${label}${count != null ? html`<span class="count">${count}</span>` : ''}</button>`)}
    </div>
    <div data-panel="report">
      <div class="report-layout">
        <nav class="toc" aria-label="Report sections">${Object.entries(groups).map(([g, keys]) => html`<div class="toc-group">${GROUP_LABEL[g]}</div>${keys.map((k) => html`<a href="#sec-${k}" data-toc="${k}">${r.sections[k]?.title || titleCase(k)}</a>`)}`)}</nav>
        <div>${r.section_order.map((k) => (r.sections[k] ? sectionHtml(k, r.sections[k]) : ''))}
          <p class="tiny muted" style="margin-top:16px">Engine ${r.engine.version} · rubric ${r.engine.rubric} · writing models: ${(r.engine.llm_models || []).join(', ') || 'none'} · knowledge base ${r.engine.kb_snapshot || 'n/a'} · retrieval ${r.engine.retrieval_mode}</p></div>
      </div>
    </div>
    <div data-panel="scores" class="hidden"></div>
    <div data-panel="evidence" class="hidden"></div>
    <div data-panel="assistant" class="hidden"></div>
    <div data-panel="validate" class="hidden"></div>`);
  if (window.innerWidth < 900) $('#hero-grid').style.gridTemplateColumns = '1fr';

  const panels = { scores: renderScores, evidence: renderEvidence, assistant: renderAssistant, validate: renderValidation };
  const rendered = new Set();
  const openTab = (id) => {
    $$('[role="tab"]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === id)));
    $$('[data-panel]').forEach((p) => p.classList.toggle('hidden', p.dataset.panel !== id));
    if (panels[id] && !rendered.has(id)) { rendered.add(id); panels[id]($(`[data-panel="${id}"]`)); }
  };
  $$('[role="tab"]').forEach((t) => t.addEventListener('click', () => openTab(t.dataset.tab)));
  page.addEventListener('click', (e) => {
    const link = e.target.closest('[data-tab-link]');
    if (link) { e.preventDefault(); openTab(link.dataset.tabLink); }
    const cite = e.target.closest('[data-cite]');
    if (cite) {
      e.preventDefault();
      openTab('evidence');
      const target = document.getElementById(`src-${cite.dataset.cite}`);
      if (target) { target.scrollIntoView({ behavior: 'smooth', block: 'center' }); target.classList.remove('flash'); void target.offsetWidth; target.classList.add('flash'); }
    }
  });
  $('#print').addEventListener('click', () => window.print());
  $('#del').addEventListener('click', deleteReport);
  $('#publish').addEventListener('click', publishDialog);

  const tocLinks = $$('[data-toc]');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const key = entry.target.id.replace('sec-', '');
        tocLinks.forEach((a) => a.classList.toggle('active', a.dataset.toc === key));
      }
    });
  }, { rootMargin: '-40% 0px -55% 0px' });
  $$('.section').forEach((s) => observer.observe(s));
}

function renderScores(panel) {
  const scores = report.result.scores;
  render(panel, html`<div class="split">
    <div class="card"><div class="card-title"><h2>13 dimensions</h2><span class="muted small">Click a row for evidence and next steps</span></div>
      ${scores.dimensions.map((d) => html`<div class="dim-row" data-dim="${d.key}" role="button" tabindex="0" aria-expanded="false">
        <div><strong class="small">${d.label}</strong><div class="tiny muted">weight ${d.weight} · ${d.confidence} confidence</div></div>
        ${meter(d.score, 10)}<strong style="text-align:right">${d.score}</strong></div>
        <div class="dim-detail hidden" data-dim-detail="${d.key}">
          <p>${d.rationale}</p>
          ${d.evidence.length ? html`<p><b>Evidence:</b> ${d.evidence.map((e) => html`${e.text}${cites(e.sources)}`)}</p>` : ''}
          ${d.missing.length ? html`<p><b>Missing:</b> ${d.missing.join('; ')}</p>` : ''}
          <p style="margin:0"><b>Cheapest next test:</b> ${d.next_step}</p></div>`)}
    </div>
    <aside class="stack">
      <div class="card card--ink stat"><span class="stat-label">Overall rubric score</span><span class="stat-value">${scores.overall}/100</span><span class="stat-note" style="color:var(--k-300)">${titleCase(scores.confidence)} confidence · ${scores.version}</span></div>
      <div class="card"><h3>How this score works</h3><p class="small">${scores.method} Each dimension is 0–10; the overall score is their weighted average. Confidence reflects whether signals came from your own words (high), inference (medium) or defaults (low).</p>
        <p class="small muted" style="margin:0">Signals extracted by: ${scores.signals_method === 'llm' ? report.result.signals.model : 'keyword heuristics (AI unavailable)'}.</p></div>
      ${scores.missing_information.length ? html`<div class="card"><h3>What would sharpen this</h3><ul class="small" style="padding-left:18px;margin:0">${scores.missing_information.map((m) => html`<li>${m}</li>`)}</ul></div>` : ''}
    </aside></div>`);
  panel.addEventListener('click', (e) => {
    const row = e.target.closest('[data-dim]');
    if (!row) return;
    const detail = $(`[data-dim-detail="${row.dataset.dim}"]`, panel);
    detail.classList.toggle('hidden');
    row.setAttribute('aria-expanded', String(!detail.classList.contains('hidden')));
  });
  panel.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('[data-dim]')) e.target.click(); });
}

function companyRow(s) {
  return html`<div class="source-item" id="src-${s.sid}"><span class="sid">${s.sid}</span><div>
    <div class="row between"><strong>${s.name}</strong><span class="row">
      ${s.status === 'shutdown_announced' ? html`<span class="chip chip--ink">Shutdown announced</span>` : ''}
      <span class="chip ${s.relation === 'direct_competitor' ? 'chip--yellow' : ''}">${titleCase(s.relation)}${s.relevance != null ? ` · ${s.relevance}/3` : ''}</span>
      <button class="btn btn--ghost btn--sm" data-watch="${s.company_id}">${icon('eye')} Watch</button></span></div>
    ${s.description ? html`<div class="small" style="margin:2px 0 4px">${s.description}</div>` : ''}
    ${s.reason ? html`<div class="small muted">Why matched: ${s.reason}</div>` : ''}
    <blockquote class="small" style="margin:6px 0;padding:8px 12px;border-left:3px solid var(--y-400);background:var(--surface-2);border-radius:0 10px 10px 0">${s.snippet}</blockquote>
    <div class="tiny muted">${s.title || ''} · ${s.date || 'undated'} · ${titleCase(s.stream || '')}${s.batch ? ` · ${s.batch}` : ''} · ${s.url ? html`<a href="${s.url}" target="_blank" rel="noopener noreferrer">Source ${icon('external')}</a>` : ''}</div>
  </div></div>`;
}

function renderEvidence(panel) {
  const ev = report.result.evidence;
  const v = report.result.validation;
  const comps = ev.competitors;
  const bucket = (title, list, hint) => html`<div class="card"><div class="card-title"><h3>${title} <span class="chip">${list.length}</span></h3><span class="muted small">${hint}</span></div>
    ${list.length ? list.map((s) => companyRow(s)) : html`<p class="muted small" style="margin:0">None found in the knowledge base. That can mean an open space — or simply that comparable companies never launched on Hacker News.</p>`}</div>`;
  render(panel, html`<div class="split split--wide"><div class="stack">
      ${bucket('Direct competitors', comps.direct, 'Same problem, same customer')}
      ${bucket('Indirect competitors', comps.indirect, 'Different approach or customer')}
      ${bucket('Similar business models', comps.similar_models, 'Worth learning from')}
      ${bucket('Adjacent', comps.adjacent, 'Same space, not competing')}
      ${ev.shutdowns.length ? html`<div class="card"><h3>Shutdown announcements among matches</h3><p class="small muted">Public shutdown announcements or founder post-mortems (verified by AI from the post title/text). Read the source to learn why.</p>
        <ul class="small">${ev.shutdowns.map((s) => html`<li><a href="#src-${s.sid}" data-cite="${s.sid}">${s.sid}</a> ${s.name} — ${s.date || ''}</li>`)}</ul></div>` : ''}
    </div>
    <aside class="stack">
      <div class="card"><h3>Research method</h3><ul class="small" style="padding-left:18px;margin:0">
        <li>Retrieval mode: <b>${ev.retrieval.mode}</b>${ev.retrieval.mode === 'lexical' ? ' (semantic search unavailable for this run)' : ''}</li>
        <li>Queries: ${ev.retrieval.queries.length}</li>
        <li>Candidates considered: ${ev.retrieval.candidates}; dropped as unrelated: ${ev.retrieval.dropped_as_unrelated}</li>
        <li>AI relevance grading: ${ev.retrieval.llm_graded ? 'yes' : 'no (matches marked unclassified)'}</li></ul>
        <details style="margin-top:8px"><summary class="small muted">Search queries</summary><ul class="small">${ev.retrieval.queries.map((q) => html`<li>${q}</li>`)}</ul></details></div>
      <div class="card"><h3>Citation checks</h3><ul class="small" style="padding-left:18px;margin:0">
        <li>Citations checked: ${v.citations_checked}</li><li>Invalid citations removed: ${v.citations_removed}</li>
        <li>Facts supported by evidence: ${v.facts_supported}</li><li>Facts downgraded to "unverified": ${v.facts_downgraded}</li>
        <li>Metrics relabelled as estimates: ${v.metrics_relabelled}</li></ul></div>
      ${ev.sector_stats ? html`<div class="card"><h3>${ev.sector_stats.label} in the knowledge base</h3><p class="small" style="margin:0">${ev.sector_stats.entities} entities · ${ev.sector_stats.shutdown_announcements} shutdown announcements · launch share ${ev.sector_stats.launch_share_trend?.direction}.
        <a href="intelligence.html?sector=${ev.sector_stats.sector}">Explore sector →</a></p></div>` : ''}
      ${ev.recent_launches?.length ? html`<div class="card"><h3>Recent launches in this sector</h3><ul class="small" style="padding-left:18px;margin:0">${ev.recent_launches.map((l) => html`<li>${l.url ? html`<a href="${l.url}" target="_blank" rel="noopener noreferrer">${l.name}</a>` : l.name} <span class="muted">${l.date || ''}</span></li>`)}</ul></div>` : ''}
      <div class="notice">${icon('database')}<div><strong>Coverage</strong>${ev.knowledge_base.coverage_note} Snapshot ${ev.knowledge_base.snapshot_id || ''}${ev.knowledge_base.built_at ? `, built ${fmtDate(ev.knowledge_base.built_at)}` : ''}.</div></div>
    </aside></div>`);
  panel.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-watch]');
    if (!btn) return;
    try { await post('/watchlist', { company_id: btn.dataset.watch, report_id: reportId }); toast('Added to your competitor watchlist'); btn.disabled = true; }
    catch (error) { toastError(error); }
  });
}

async function renderAssistant(panel) {
  const suggestions = ['Why did I get this score?', 'Who are my biggest competitors?', 'How can I differentiate?', 'What if I target a different customer?',
    'Which features should I build first?', 'Why did similar startups shut down?'];
  render(panel, html`<div class="split"><div class="card chat">
      <div class="chat-log" id="chat-log" aria-live="polite"><div class="skeleton sk-line"></div></div>
      <div class="suggestions">${suggestions.map((s) => html`<button class="suggestion" data-suggest="${s}">${s}</button>`)}</div>
      <form class="chat-foot" id="chat-form"><textarea class="textarea" name="message" maxlength="2000" placeholder="Ask about your report…" aria-label="Message" required></textarea>
        <button class="btn btn--ai" data-busy="">${icon('send')}</button></form>
    </div>
    <aside class="card card--ai"><div class="ai-mark">${icon('sparkles')} FOUNDER ASSISTANT</div>
      <p class="small" style="margin-top:8px">Answers are grounded in this report plus a fresh search of the knowledge base for your question. Citations are verified; anything the evidence can't support is labeled.</p>
      <p class="small muted" style="margin:0">"What if" questions are answered as scenarios, not predictions.</p></aside></div>`);
  const log = $('#chat-log', panel);
  const sourcesHtml = (meta) => (meta?.sources?.length ? html`<div class="meta">${meta.sources.map((s) => html`<a class="chip chip--ai" href="${s.url || '#'}" target="_blank" rel="noopener noreferrer">${s.sid} · ${s.name}</a>`)}</div>` : '');
  const msgHtml = (m) => html`<div class="chat-msg ${m.role}">${m.content}${m.role === 'assistant' ? html`${sourcesHtml(m.meta)}<div class="tiny muted" style="margin-top:6px">${titleCase(m.meta?.answer_type || '')}${m.meta?.model ? ` · ${m.meta.model}` : ''}${m.meta?.citations_removed ? ` · ${m.meta.citations_removed} unsupported citation(s) removed` : ''}</div>` : ''}</div>`;
  try {
    const { messages } = await get(`/reports/${reportId}/chat`);
    render(log, messages.length ? html`${messages.map(msgHtml)}` : html`<div class="chat-msg assistant">Hi ${user.name.split(' ')[0]} — ask me anything about this report: the score, competitors, pricing, what to build first, or "what if" scenarios.</div>`);
    log.scrollTop = log.scrollHeight;
  } catch (error) { toastError(error); }
  const form = $('#chat-form', panel);
  const send = async (text) => {
    if (!text.trim()) return;
    log.insertAdjacentHTML('beforeend', msgHtml({ role: 'user', content: text }).html);
    log.insertAdjacentHTML('beforeend', '<div class="chat-msg assistant" id="typing"><span class="spinner"></span></div>');
    log.scrollTop = log.scrollHeight;
    form.message.value = '';
    try {
      const reply = await post(`/reports/${reportId}/chat`, { message: text });
      $('#typing')?.remove();
      log.insertAdjacentHTML('beforeend', msgHtml(reply).html);
      if (reply.meta?.follow_ups?.length) {
        render($('.suggestions', panel), html`${reply.meta.follow_ups.map((s) => html`<button class="suggestion" data-suggest="${s}">${s}</button>`)}`);
      }
    } catch (error) {
      $('#typing')?.remove();
      log.insertAdjacentHTML('beforeend', `<div class="chat-msg assistant">${esc(error.message)}</div>`);
    }
    log.scrollTop = log.scrollHeight;
  };
  form.addEventListener('submit', (e) => { e.preventDefault(); withBusy($('button', form), () => send(form.message.value)); });
  form.message.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  panel.addEventListener('click', (e) => { const s = e.target.closest('[data-suggest]'); if (s) send(s.dataset.suggest); });
}

async function renderValidation(panel) {
  const COLS = [['todo', 'To do'], ['running', 'Running'], ['validated', 'Validated'], ['invalidated', 'Invalidated']];
  const draw = (items) => render(panel, html`<div class="row between" style="margin-bottom:12px"><p class="muted small" style="margin:0">Experiments seeded from the report. Track what you test and what you learn.</p>
      <button class="btn btn--sm" id="add-item">${icon('plus')} Add experiment</button></div>
    <div class="board">${COLS.map(([key, label]) => {
      const list = items.filter((i) => i.status === key);
      return html`<div class="board-col"><h4>${label}<span class="muted">${list.length}</span></h4>${list.map((i) => html`<div class="vcard">
        <strong>${i.title}</strong>${i.method ? html`<div class="small muted" style="margin-top:4px">${i.method}</div>` : ''}
        ${i.success_metric ? html`<div class="tiny" style="margin-top:4px"><b>Success:</b> ${i.success_metric}</div>` : ''}
        ${i.notes ? html`<div class="tiny" style="margin-top:4px"><b>Notes:</b> ${i.notes}</div>` : ''}
        <div class="row" style="gap:6px"><select data-status="${i.id}" aria-label="Status">${COLS.map(([k, l]) => html`<option value="${k}" ${k === i.status ? raw('selected') : ''}>${l}</option>`)}</select>
        <button class="btn btn--quiet btn--sm" data-notes="${i.id}">Notes</button><button class="btn btn--quiet btn--sm" data-remove="${i.id}" aria-label="Delete">${icon('trash')}</button></div></div>`)}</div>`;
    })}</div>`);
  let items = (await get(`/reports/${reportId}/validation`)).items;
  draw(items);
  panel.addEventListener('change', async (e) => {
    const sel = e.target.closest('[data-status]');
    if (!sel) return;
    try { await patch(`/validation/${sel.dataset.status}`, { status: sel.value }); items = (await get(`/reports/${reportId}/validation`)).items; draw(items); }
    catch (error) { toastError(error); }
  });
  panel.addEventListener('click', async (e) => {
    if (e.target.closest('#add-item')) {
      modal({ title: 'New experiment', body: html`<div class="field"><label for="vt">Hypothesis</label><input class="input" id="vt" maxlength="200"></div>
        <div class="field"><label for="vm">How you'll test it</label><textarea class="textarea" id="vm"></textarea></div>
        <div class="field"><label for="vs">Success metric</label><input class="input" id="vs"></div>`,
      actions: [{ label: 'Cancel', kind: 'btn--ghost' }, { label: 'Add', kind: 'btn--yellow', onClick: async (m) => {
        if (!$('#vt', m).value.trim()) { toast('Add a hypothesis', 'error'); return true; }
        await post(`/reports/${reportId}/validation`, { title: $('#vt', m).value, hypothesis: $('#vt', m).value, method: $('#vm', m).value, success_metric: $('#vs', m).value });
        items = (await get(`/reports/${reportId}/validation`)).items; draw(items);
      } }] });
    }
    const notes = e.target.closest('[data-notes]');
    if (notes) {
      const item = items.find((i) => i.id === notes.dataset.notes);
      modal({ title: 'Notes & learnings', body: html`<textarea class="textarea" id="vn" maxlength="4000">${item.notes}</textarea>`,
        actions: [{ label: 'Cancel', kind: 'btn--ghost' }, { label: 'Save', kind: 'btn--yellow', onClick: async (m) => {
          await patch(`/validation/${item.id}`, { notes: $('#vn', m).value }); items = (await get(`/reports/${reportId}/validation`)).items; draw(items);
        } }] });
    }
    const rm = e.target.closest('[data-remove]');
    if (rm && await confirmDialog('Delete this experiment?', { confirm: 'Delete' })) {
      await del(`/validation/${rm.dataset.remove}`); items = items.filter((i) => i.id !== rm.dataset.remove); draw(items);
    }
  });
}

function publishDialog() {
  const lookingFor = { ref: null };
  modal({ title: 'Publish a public summary', wide: true, body: html`<div class="stack">
      <div class="notice notice--ai">${icon('lock')}<div><strong>You control what's shared</strong>Your inputs, evidence, competitors and report sections stay private. Only the fields below appear on a public startup page.</div></div>
      <div class="field"><label for="pn">Startup name</label><input class="input" id="pn" maxlength="100" value="${report.title}"></div>
      <div class="field"><label for="pt">Tagline</label><input class="input" id="pt" maxlength="160" value="${report.result.signals?.one_liner?.slice(0, 160) || ''}"></div>
      <label class="check"><input type="checkbox" id="ps" checked> Share the one-line description</label>
      <label class="check"><input type="checkbox" id="psc"> Share the overall rubric score (${report.result.scores.overall}/100)</label>
      <label class="check"><input type="checkbox" id="psb"> Share the per-dimension score breakdown</label>
      <label class="check"><input type="checkbox" id="pai"> Allow other members to run their own StartPunch analysis on the public description</label>
      <div class="field"><span class="label">Looking for</span><div id="plf"></div><span class="hint">e.g. co-founder, designer, beta users, angel investors</span></div>
      <div class="field"><label for="pq">Ask the community a question <span class="hint">(optional — posts to the feed)</span></label><input class="input" id="pq" maxlength="500" placeholder="Would you pay for this? What would make you switch?"></div></div>`,
  onOpen: (m) => { lookingFor.ref = tagsInput($('#plf', m), [], { placeholder: 'Add a role and press Enter' }); },
  actions: [{ label: 'Cancel', kind: 'btn--ghost' }, { label: 'Publish', kind: 'btn--yellow', onClick: async (m) => {
    const res = await post(`/reports/${reportId}/publish`, { name: $('#pn', m).value, tagline: $('#pt', m).value, share_summary: $('#ps', m).checked,
      share_score: $('#psc', m).checked, share_scores_breakdown: $('#psb', m).checked, allow_ai_analysis: $('#pai', m).checked,
      looking_for: lookingFor.ref.get(), feedback_question: $('#pq', m).value });
    toast('Published');
    location.href = `startup.html?id=${res.startup_id}`;
  } }] });
}

async function deleteReport() {
  if (!(await confirmDialog('This permanently deletes the report, its assistant conversation and validation tracker.', { title: 'Delete report?', confirm: 'Delete' }))) return;
  try { await del(`/reports/${reportId}`); location.href = 'dashboard.html'; } catch (error) { toastError(error); }
}
void timeAgo;
