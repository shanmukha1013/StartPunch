import { get, post } from '../core/api.js';
import { barsH, columns } from '../core/charts.js';
import { boot } from '../core/shell.js';
import { $, $$, emptyState, fmtDate, html, icon, modal, num, param, render, titleCase, toast, toastError } from '../core/ui.js';

const { page } = await boot({ active: 'intelligence', title: 'Market intelligence' });

const [cov, sectors] = await Promise.all([get('/intelligence/coverage'), get('/intelligence/sectors')]).catch((e) => { toastError(e); return [null, null]; });
if (!cov || !cov.available) {
  render(page, emptyState({ iconName: 'database', title: 'Knowledge base not available', text: 'The knowledge-base snapshot has not been built on this server.' }));
} else {
  const label = (key) => sectors.taxonomy[key] || (key === 'unclassified' ? 'Unclassified' : titleCase(key));
  const emb = cov.embedding;
  const ev = cov.retrieval_evaluation;
  render(page, html`
    <div class="page-head"><div><p class="eyebrow">Market intelligence</p><h1>What StartPunch knows — and what it doesn't</h1>
      <p>Every analysis draws on this knowledge base. Here is its actual coverage, freshness, models and evaluation — so you can judge the evidence yourself.</p></div></div>
    <div class="grid grid-4">
      <div class="card card--ink stat"><span class="stat-label">Entities indexed</span><span class="stat-value">${num(cov.counts.entities)}</span><span class="stat-note" style="color:var(--k-300)">${num(cov.counts.by_type?.startup)} startups · ${num(cov.counts.by_type?.product)} products</span></div>
      <div class="card stat"><span class="stat-label">Verified shutdowns</span><span class="stat-value">${num(cov.counts.shutdown_announced)}</span><span class="stat-note">${num(cov.validation?.shutdown_candidates_checked_by_llm)} candidates checked by AI</span></div>
      <div class="card stat"><span class="stat-label">Snapshot freshness</span><span class="stat-value">${cov.age_days ?? '—'}<span class="muted" style="font-size:1rem"> days</span></span><span class="stat-note">${titleCase(cov.freshness)} · policy ${cov.freshness_policy_days} days · built ${fmtDate(cov.built_at)}</span></div>
      <div class="card stat"><span class="stat-label">Semantic index coverage</span><span class="stat-value">${emb ? Math.round((emb.chunks_embedded / emb.chunks_total) * 100) : 0}%</span><span class="stat-note">${emb ? `${num(emb.chunks_embedded)} of ${num(emb.chunks_total)} chunks embedded; all are keyword-searchable` : 'Keyword search only'}</span></div>
    </div>
    <div class="tabs" role="tablist" style="margin-top:22px">${[['search', 'Search companies'], ['sectors', 'Sectors'], ['clusters', 'Market clusters'], ['sources', 'Sources & quality']]
      .map(([id, l], i) => html`<button class="tab" role="tab" data-tab="${id}" aria-selected="${i === 0}">${l}</button>`)}</div>

    <div data-panel="search">
      <form id="kb-search" class="card" style="margin-bottom:14px"><div class="row" style="flex-wrap:nowrap"><input class="input input--search" name="q" placeholder="Describe a product, problem or market — e.g. 'AI bookkeeping for freelancers'" value="${param('q') || ''}" aria-label="Search the knowledge base" minlength="2"><button class="btn">Search</button></div>
        <div class="row" style="margin-top:10px">
          <select class="select" name="sector" style="width:auto"><option value="">All sectors</option>${Object.entries(sectors.taxonomy).map(([k, v]) => html`<option value="${k}">${v}</option>`)}</select>
          <select class="select" name="status" style="width:auto"><option value="">Any status</option><option value="launched">Launched</option><option value="shutdown_announced">Shutdown announced</option></select>
          <select class="select" name="entity_type" style="width:auto"><option value="">Any type</option><option value="startup">Startup (Launch HN)</option><option value="product">Product (Show HN)</option><option value="company">Company</option></select>
          <input class="input" type="date" name="since" style="width:auto" aria-label="Posted since">
          <select class="select" name="mode" style="width:auto"><option value="hybrid">Hybrid retrieval</option><option value="lexical">Keyword (BM25)</option><option value="dense">Semantic only</option></select></div></form>
      <div id="results"></div></div>

    <div data-panel="sectors" class="hidden"><div class="split"><div class="card"><div class="card-title"><h2>Entities by sector</h2><span class="muted small">Click a sector in the list for detail</span></div><div id="sector-chart"></div></div>
      <aside class="card"><h3>Sectors</h3><div id="sector-list"></div></aside></div><div id="sector-detail" style="margin-top:18px"></div></div>

    <div data-panel="clusters" class="hidden"><div id="clusters"></div></div>

    <div data-panel="sources" class="hidden"><div class="split"><div class="stack">
      ${cov.sources.map((s) => html`<div class="card"><div class="row between"><h3 style="margin:0">${s.name}</h3><a class="small" href="${s.url}" target="_blank" rel="noopener noreferrer">${icon('external')} Source</a></div>
        <p class="small" style="margin:6px 0">${s.description}</p>
        <div class="small muted">${num(s.items_fetched)} items fetched · fetched ${fmtDate(s.fetched_at)} · latest item ${fmtDate(s.latest_item)}</div>
        <div class="tiny muted" style="margin-top:4px">License / terms: ${s.license}</div></div>`)}
      <div class="card"><h3>Launch posts by year</h3><p class="small muted">All Launch HN + Show HN posts in the knowledge base. Reflects Hacker News activity, not total market activity.</p><div id="years"></div></div></div>
      <aside class="stack">
        <div class="card"><h3>Build pipeline</h3><ul class="small" style="padding-left:18px;margin:0">
          ${Object.entries(cov.build_report.raw_items || {}).map(([k, v]) => html`<li>${k}: ${num(v)} raw items</li>`)}
          ${Object.entries(cov.build_report.rejected || {}).map(([k, v]) => html`<li>Rejected — ${k.replace(/_/g, ' ')}: ${num(v)}</li>`)}
          <li>Entity resolution: ${num(cov.build_report.resolved_by_domain)} by domain, ${num(cov.build_report.resolved_by_name)} by name</li>
          <li>Shutdowns confirmed by AI: ${num(cov.validation?.shutdown_confirmed)} of ${num(cov.validation?.shutdown_candidates_checked_by_llm)}</li></ul></div>
        <div class="card"><h3>Models</h3><div id="models"><div class="skeleton sk-line"></div></div></div>
        ${ev ? html`<div class="card"><h3>Retrieval evaluation</h3><p class="tiny muted">${ev.protocol}</p>
          <div class="table-wrap"><table class="data"><thead><tr><th>Mode</th><th>Known-item recall@10</th><th>Sector precision@10</th></tr></thead><tbody>
          ${Object.entries(ev.results).map(([m, r]) => html`<tr><td>${m}</td><td>${r['known_item_recall@10']}</td><td>${r['sector_precision@10'] ?? '—'}</td></tr>`)}</tbody></table></div>
          ${ev.skipped ? html`<p class="tiny muted" style="margin:8px 0 0">${ev.skipped.split(':')[0]} (embedding quota).</p>` : ''}</div>` : ''}
        <div class="notice">${icon('alert')}<div><strong>Known limitations</strong><ul class="small" style="padding-left:18px;margin:4px 0 0">${cov.caveats.map((c) => html`<li>${c}</li>`)}</ul></div></div>
      </aside></div></div>`);

  const opened = new Set(['search']);
  $$('[role="tab"]').forEach((t) => t.addEventListener('click', () => {
    $$('[role="tab"]').forEach((x) => x.setAttribute('aria-selected', String(x === t)));
    $$('[data-panel]').forEach((p) => p.classList.toggle('hidden', p.dataset.panel !== t.dataset.tab));
    if (opened.has(t.dataset.tab)) return;
    opened.add(t.dataset.tab);
    if (t.dataset.tab === 'sectors') drawSectors();
    if (t.dataset.tab === 'clusters') drawClusters();
    if (t.dataset.tab === 'sources') drawSources();
  }));

  // ---------------------------------------------------------------- search
  const resultCard = (h) => html`<div class="card" style="margin-bottom:10px"><div class="row between" style="flex-wrap:nowrap">
      <div class="grow"><button class="btn btn--quiet" style="padding:0;font-size:1rem;font-weight:700" data-company="${h.company_id}">${h.name}</button>
        <div class="small">${h.description}</div></div>
      <div class="chip-row" style="justify-content:flex-end">${h.status === 'shutdown_announced' ? html`<span class="chip chip--ink">Shutdown announced</span>` : ''}
        ${h.sector_label && h.sector_label !== 'Other' ? html`<span class="chip">${h.sector_label}</span>` : ''}${h.batch ? html`<span class="chip chip--yellow">${h.batch}</span>` : ''}</div></div>
    ${h.evidence[0] ? html`<p class="small muted" style="margin:8px 0 4px">${h.evidence[0].text.slice(0, 260)}${h.evidence[0].text.length > 260 ? '…' : ''}</p>
      <div class="tiny muted">${h.evidence[0].title || ''} · ${h.evidence[0].date || ''} · <a href="${h.evidence[0].url}" target="_blank" rel="noopener noreferrer">source</a> · match: keyword ${h.signals.lexical}, semantic ${h.signals.dense}</div>` : ''}</div>`;
  async function search(form) {
    const data = Object.fromEntries(new FormData(form));
    if (!data.q || data.q.trim().length < 2) {
      render($('#results'), html`<p class="muted small">Search ${num(cov.counts.entities)} startups and products by what they do. Results link to their original posts.</p>`);
      return;
    }
    render($('#results'), html`<div class="skeleton sk-block"></div>`);
    const params = new URLSearchParams(Object.entries(data).filter(([, v]) => v));
    try {
      const res = await get(`/intelligence/search?${params}`);
      render($('#results'), html`<p class="tiny muted">Retrieval: ${res.diagnostics.mode} · ${res.diagnostics.candidates_after_filters ?? 0} chunks after filters</p>
        ${res.results.length ? res.results.map(resultCard) : emptyState({ iconName: 'search', title: 'No matches', text: 'Try broader words or remove filters. Coverage is limited to Hacker News launches.' })}`);
    } catch (error) { toastError(error); }
  }
  $('#kb-search').addEventListener('submit', (e) => { e.preventDefault(); search(e.target); });
  search($('#kb-search'));
  page.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-company]');
    if (!b) return;
    try {
      const c = await get(`/intelligence/companies/${encodeURIComponent(b.dataset.company)}`);
      modal({ title: c.name, wide: true, body: html`<div class="stack">
        <div class="chip-row"><span class="chip">${titleCase(c.entity_type)}</span><span class="chip ${c.status === 'shutdown_announced' ? 'chip--ink' : ''}">${titleCase(c.status)}</span>
          ${c.sector_label ? html`<span class="chip chip--ai">${c.sector_label} (${c.sector_source === 'llm_label' ? 'AI-labelled' : c.sector_source === 'model_predicted' ? 'model-predicted' : 'unclassified'})</span>` : ''}
          ${c.business_model ? html`<span class="chip">${titleCase(c.business_model)}</span>` : ''}${c.batch ? html`<span class="chip chip--yellow">${c.batch}</span>` : ''}</div>
        <p>${c.description}</p>${c.website ? html`<a href="${c.website}" target="_blank" rel="noopener noreferrer nofollow">${icon('globe')} ${c.website}</a>` : ''}
        <h3>Public record</h3><div class="table-wrap"><table class="data"><thead><tr><th>Date</th><th>Type</th><th>Post</th><th>Points</th></tr></thead><tbody>
        ${c.documents.map((d) => html`<tr><td class="nowrap">${d.date}</td><td>${titleCase(d.kind)}</td><td><a href="${d.url}" target="_blank" rel="noopener noreferrer">${d.title}</a></td><td>${d.points}</td></tr>`)}</tbody></table></div></div>`,
        actions: [{ label: 'Close', kind: 'btn--ghost' }, { label: 'Watch competitor', kind: 'btn--yellow', onClick: async () => { await post('/watchlist', { company_id: c.id }); toast('Added to your watchlist'); } }] });
    } catch (error) { toastError(error); }
  });

  // ---------------------------------------------------------------- sectors
  function drawSectors() {
    const rows = sectors.sectors.filter((s) => s.sector !== 'unclassified');
    barsH($('#sector-chart'), rows.map((s) => ({ label: s.label, value: s.entities, note: `${s.shutdown_announcements} shutdowns · launch share ${s.launch_share_trend.direction}` })),
      { caption: 'Knowledge-base entities per sector', format: (v) => num(v) });
    const uncl = sectors.sectors.find((s) => s.sector === 'unclassified');
    render($('#sector-list'), html`${rows.map((s) => html`<button class="btn btn--quiet btn--block" style="justify-content:space-between" data-sector="${s.sector}">${s.label}<span class="muted small">${s.launch_share_trend.direction}</span></button>`)}
      ${uncl ? html`<p class="tiny muted" style="margin:10px 0 0">${num(uncl.entities)} entities are unclassified (no confident label).</p>` : ''}`);
    $('#sector-list').addEventListener('click', (e) => { const b = e.target.closest('[data-sector]'); if (b) sectorDetail(b.dataset.sector); });
    if (param('sector')) sectorDetail(param('sector'));
  }
  async function sectorDetail(key) {
    try {
      const d = await get(`/intelligence/sectors/${key}`);
      const s = d.stats;
      const t = s.launch_share_trend;
      render($('#sector-detail'), html`<div class="card"><div class="card-title"><h2>${s.label}</h2><span class="chip">${num(s.entities)} entities</span></div>
        <div class="grid grid-3"><div><h3>Launch posts per year</h3><div id="sector-years"></div></div>
          <div><h3>Momentum</h3><p class="small">Share of all launch posts: <b>${(t.prior_share * 100).toFixed(1)}%</b> in ${t.prior_years.join('–')} → <b>${(t.recent_share * 100).toFixed(1)}%</b> in ${t.recent_years.join('–')} (${t.prior_count} → ${t.recent_count} posts). Direction: <b>${t.direction}</b>.</p>
            <h3>Business models</h3><div class="chip-row">${Object.entries(s.business_models).map(([k, v]) => html`<span class="chip">${titleCase(k)} · ${v}</span>`)}</div></div>
          <div><h3>Shutdown announcements (${s.shutdown_announcements})</h3>${s.shutdown_examples.length ? html`<ul class="small" style="padding-left:18px;margin:0">${s.shutdown_examples.map((x) => html`<li><button class="btn btn--quiet btn--sm" style="padding:0" data-company="${x.id}">${x.name}</button> <span class="muted">${x.date || ''}</span></li>`)}</ul>` : html`<p class="small muted">None recorded.</p>`}</div></div>
        <div class="grid grid-2" style="margin-top:16px"><div><h3>Most discussed</h3>${d.most_discussed.map((c) => html`<div class="small" style="padding:4px 0"><button class="btn btn--quiet btn--sm" style="padding:0" data-company="${c.id}">${c.name}</button> <span class="muted">${c.max_points} points</span></div>`)}</div>
          <div><h3>Most recent</h3>${d.recent.map((c) => html`<div class="small" style="padding:4px 0"><button class="btn btn--quiet btn--sm" style="padding:0" data-company="${c.id}">${c.name}</button> <span class="muted">${c.first_launch}</span></div>`)}</div></div></div>`);
      const years = Object.entries(s.launch_posts_by_year).filter(([y]) => Number(y) >= 2012);
      columns($('#sector-years'), years.map(([y, v]) => ({ label: y.slice(2), value: v })), { caption: `${s.label} launch posts per year` });
      $('#sector-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) { toastError(error); }
  }

  // ---------------------------------------------------------------- clusters
  async function drawClusters() {
    const c = await get('/intelligence/clusters');
    if (!c.available) { render($('#clusters'), emptyState({ iconName: 'layers', title: 'Clusters unavailable', text: 'Clustering requires embeddings.' })); return; }
    render($('#clusters'), html`<div class="notice" style="margin-bottom:14px">${icon('info')}<div><strong>${c.algorithm}</strong>k = ${c.k_selection.chosen_k} chosen by silhouette score (${c.k_selection.silhouette_cosine_sample[c.k_selection.chosen_k]}). ${c.limitations.join(' ')}</div></div>
      <div class="grid grid-3">${c.clusters.map((cl) => html`<div class="card"><div class="row between"><strong>Cluster ${cl.id + 1}</strong><span class="chip">${cl.size} entities</span></div>
        <div class="chip-row" style="margin:10px 0">${cl.top_terms.slice(0, 6).map((t) => html`<span class="chip chip--ai">${t}</span>`)}</div>
        <p class="tiny muted" style="margin:0 0 6px">${cl.dominant_sectors.map((d) => `${d.label} ${Math.round(d.share * 100)}%`).join(' · ')}</p>
        <p class="small" style="margin:0">${cl.examples.map((e) => e.name).join(', ')}</p></div>`)}</div>`);
  }

  // ---------------------------------------------------------------- sources/models
  async function drawSources() {
    const years = Object.entries(cov.launch_posts_by_year).filter(([y]) => Number(y) >= 2008);
    columns($('#years'), years.map(([y, v]) => ({ label: y.slice(2), value: v })), { caption: 'Launch posts per year in the knowledge base', format: (v) => num(v) });
    const { models } = await get('/intelligence/models');
    render($('#models'), html`${Object.entries(models).map(([name, m]) => html`<div style="padding:8px 0;border-top:1px solid var(--line-soft)">
      <strong>${titleCase(name)}</strong> <span class="chip">${m.version}</span>
      ${m.metrics ? html`<div class="small" style="margin-top:4px">${Object.entries(m.metrics).filter(([k]) => k !== 'majority_baseline').map(([k, v]) => html`<div>${k}: accuracy ${v.accuracy}, macro-F1 ${v.macro_f1}</div>`)}
        ${m.metrics.majority_baseline ? html`<div class="muted">baseline (majority class): accuracy ${m.metrics.majority_baseline.accuracy}, macro-F1 ${m.metrics.majority_baseline.macro_f1}</div>` : ''}</div>` : ''}
      ${m.k_selection ? html`<div class="small">k=${m.k_selection.chosen_k}, silhouette ${m.k_selection.silhouette_cosine_sample[m.k_selection.chosen_k]}</div>` : ''}
      ${m.evaluation_note ? html`<div class="tiny muted">${m.evaluation_note}</div>` : ''}
      ${m.training_data ? html`<div class="tiny muted">${num(m.training_data.examples)} training examples · ${m.label_source}</div>` : ''}</div>`)}`);
  }
}
