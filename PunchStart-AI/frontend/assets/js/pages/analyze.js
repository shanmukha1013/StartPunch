import { post } from '../core/api.js';
import { boot } from '../core/shell.js';
import { $, $$, html, icon, raw, render, storage, store, toastError, withBusy } from '../core/ui.js';

const DRAFT = 'startpunch.analysis.draft.v2';
const STAGES = [['idea', 'Just an idea'], ['prototype', 'Prototype'], ['mvp', 'MVP'], ['beta', 'Beta / pilots'], ['paying_customers', 'Paying customers'], ['scaling', 'Scaling']];
const FIELDS = ['idea', 'name', 'stage', 'target_customers', 'revenue_model', 'geography', 'problem', 'solution', 'team', 'funding',
  'competitors_known', 'differentiation', 'traction'];

const { page, aiConfigured } = await boot({ active: 'analyze', title: 'New analysis' });
let step = 0;
let clarification = null;
const draft = storage(DRAFT, {}) || {};
const prefill = new URLSearchParams(location.search).get('prefill');
if (prefill) { try { Object.assign(draft, JSON.parse(prefill)); } catch { /* ignore malformed */ } }

render(page, html`
  <div class="page-head"><div><p class="eyebrow">New analysis</p><h1>What are you thinking of building?</h1>
    <p>Describe any startup, product, marketplace or project. We'll ask what's missing, research comparable launches and shutdowns, score the opportunity transparently and write a sourced report.</p></div></div>
  ${aiConfigured ? '' : html`<div class="notice" style="margin-bottom:16px">${icon('alert')}<div><strong>AI engine not configured on this server</strong>You'll still get retrieval results and the rubric score, but report sections will be marked unavailable rather than invented.</div></div>`}
  <div class="wizard-steps" aria-label="Progress">
    ${['Describe', 'Details', 'Follow-up questions', 'Review'].map((label, i) => html`<span class="wizard-step" data-step-ind="${i}"><b>${i + 1}</b>${label}</span>`)}
  </div>
  <div class="split">
    <form id="wizard" class="card" novalidate>
      <section data-step="0" class="stack">
        <div class="field"><label for="idea">Your idea <span class="hint">— the more specific, the better the research</span></label>
          <textarea class="textarea" id="idea" name="idea" maxlength="5000" style="min-height:160px" placeholder="e.g. A tool that automatically reconciles invoices, bank statements and FX payments for small exporters in India, so their accountants stop doing it by hand every month."></textarea>
          <span class="hint" id="idea-count">0 / 5000 — at least 30 characters</span></div>
        <div class="grid grid-2">
          <div class="field"><label for="name">Name <span class="hint">(optional)</span></label><input class="input" id="name" name="name" maxlength="100"></div>
          <div class="field"><label for="geography">Target market / geography</label><input class="input" id="geography" name="geography" maxlength="120" placeholder="e.g. India, US mid-market, EU"></div>
        </div>
        <div class="field"><span class="label">Stage</span><div class="segmented" id="stage" role="group" aria-label="Stage">
          ${STAGES.map(([v, l]) => html`<button type="button" data-v="${v}" aria-pressed="false">${l}</button>`)}</div></div>
        <div class="grid grid-2">
          <div class="field"><label for="target_customers">Target customers</label><input class="input" id="target_customers" name="target_customers" maxlength="1000" placeholder="Who buys and who uses it?"></div>
          <div class="field"><label for="revenue_model">Revenue model</label><input class="input" id="revenue_model" name="revenue_model" maxlength="500" placeholder="e.g. ₹2,000/month subscription"></div>
        </div>
      </section>
      <section data-step="1" class="stack hidden">
        <p class="muted small">All optional — anything you add here sharpens the scoring and the report.</p>
        <div class="field"><label for="problem">Problem</label><textarea class="textarea" id="problem" name="problem" maxlength="2000" placeholder="What is painful today, for whom, and how often?"></textarea></div>
        <div class="field"><label for="solution">Solution</label><textarea class="textarea" id="solution" name="solution" maxlength="2000"></textarea></div>
        <div class="grid grid-2">
          <div class="field"><label for="differentiation">Why you'll win</label><textarea class="textarea" id="differentiation" name="differentiation" maxlength="1500"></textarea></div>
          <div class="field"><label for="traction">Validation so far</label><textarea class="textarea" id="traction" name="traction" maxlength="1500" placeholder="Interviews, waitlist, pilots, revenue…"></textarea></div>
        </div>
        <div class="grid grid-2">
          <div class="field"><label for="competitors_known">Competitors you know</label><input class="input" id="competitors_known" name="competitors_known" maxlength="1000"></div>
          <div class="field"><label for="team">Team</label><input class="input" id="team" name="team" maxlength="1000" placeholder="Size and relevant skills"></div>
        </div>
        <div class="field"><label for="funding">Funding plan</label><input class="input" id="funding" name="funding" maxlength="500" placeholder="Bootstrapped, raising pre-seed, grant…"></div>
      </section>
      <section data-step="2" class="hidden" id="clarify-step"></section>
      <section data-step="3" class="hidden" id="review-step"></section>
      <p class="form-error" id="form-error" role="alert"></p>
      <div class="row between" style="margin-top:8px">
        <button type="button" class="btn btn--ghost" id="prev">${icon('back')} Back</button>
        <div class="row">
          <button type="button" class="btn btn--quiet hidden" id="skip">Skip questions</button>
          <button type="button" class="btn" id="next" data-busy="Thinking">Continue ${icon('arrow')}</button>
          <button type="button" class="btn btn--yellow hidden" id="run" data-busy="Starting">${icon('sparkles')} Run analysis</button>
        </div>
      </div>
    </form>
    <aside class="stack sticky">
      <div class="card card--ai"><div class="ai-mark">${icon('sparkles')} WHAT HAPPENS NEXT</div>
        <ol class="small" style="padding-left:18px;margin:10px 0 0">
          <li>We classify the idea (sector, business model) with trained models.</li>
          <li>Hybrid search finds comparable launches and verified shutdowns; AI grades each as a direct, indirect or unrelated match.</li>
          <li>A 13-dimension rubric scores the idea — every score shows its reasoning.</li>
          <li>The AI writes 35 sections using only that evidence; citations are checked automatically.</li>
        </ol></div>
      <div class="card"><h3>Honest by design</h3><p class="small muted" style="margin:0">Where data is missing we say so instead of inventing numbers. Market sizes and costs are labeled as estimates with their assumptions. Your report is private.</p></div>
    </aside>
  </div>`);

const form = $('#wizard');
FIELDS.forEach((f) => { if (form[f] && draft[f]) form[f].value = draft[f]; });
let stage = draft.stage || 'idea';
const stageButtons = $$('#stage button');
const drawStage = () => stageButtons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === stage)));
stageButtons.forEach((b) => b.addEventListener('click', () => { stage = b.dataset.v; drawStage(); save(); }));
drawStage();

function collect() {
  const data = Object.fromEntries(FIELDS.filter((f) => form[f]).map((f) => [f, form[f].value.trim()]));
  data.stage = stage;
  return data;
}
function save() { store(DRAFT, collect()); }
form.addEventListener('input', () => {
  save();
  $('#idea-count').textContent = `${form.idea.value.length} / 5000 — at least 30 characters`;
});
$('#idea-count').textContent = `${form.idea.value.length} / 5000 — at least 30 characters`;

function show(n) {
  step = n;
  $$('[data-step]').forEach((s) => s.classList.toggle('hidden', Number(s.dataset.step) !== n));
  $$('[data-step-ind]').forEach((s) => {
    const i = Number(s.dataset.stepInd);
    s.classList.toggle('active', i === n);
    s.classList.toggle('done', i < n);
  });
  $('#prev').classList.toggle('hidden', n === 0);
  $('#next').classList.toggle('hidden', n === 3);
  $('#run').classList.toggle('hidden', n !== 3);
  $('#skip').classList.toggle('hidden', n !== 2);
  $('#form-error').textContent = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function answers() {
  return $$('[data-q]').map((el) => ({ question: el.dataset.q, answer: el.value.trim() })).filter((a) => a.answer);
}

function renderReview() {
  const data = collect();
  const qa = answers();
  const label = { idea: 'Idea', name: 'Name', stage: 'Stage', target_customers: 'Customers', revenue_model: 'Revenue model', geography: 'Geography',
    problem: 'Problem', solution: 'Solution', differentiation: 'Differentiation', traction: 'Validation', competitors_known: 'Known competitors',
    team: 'Team', funding: 'Funding' };
  render($('#review-step'), html`<h2>Review</h2><p class="muted small">This is everything the analysis will use.</p>
    <div class="table-wrap"><table class="data"><tbody>
      ${Object.entries(label).filter(([k]) => data[k]).map(([k, l]) => html`<tr><th style="width:170px">${l}</th><td>${k === 'stage' ? STAGES.find((s) => s[0] === data.stage)?.[1] : data[k]}</td></tr>`)}
      ${qa.map((a) => html`<tr><th>${a.question}</th><td>${a.answer}</td></tr>`)}
    </tbody></table></div>`);
}

async function loadClarify(button) {
  await withBusy(button, async () => {
    try {
      clarification = await post('/analysis/clarify', collect());
    } catch (error) {
      clarification = { questions: [], summary: '', missing: [], error: error.message };
    }
  });
  const c = clarification;
  render($('#clarify-step'), html`
    <div class="ai-mark">${icon('sparkles')} FOLLOW-UP QUESTIONS</div>
    ${c.summary ? html`<p style="margin-top:8px"><b>We understood:</b> ${c.summary}</p>` : ''}
    ${c.error ? html`<div class="notice">${icon('alert')}<div>${c.error}</div></div>` : ''}
    ${c.questions.length ? html`<p class="muted small">Answer what you can — skipped questions are recorded as missing information.</p>
      ${c.questions.map((q) => html`<div class="question"><label for="${q.id}">${q.question}</label><p class="why">${q.why}</p>
        <textarea class="textarea" id="${q.id}" data-q="${q.question}" maxlength="1500" style="min-height:70px"></textarea></div>`)}`
      : html`<p class="muted">No follow-up questions — your description covers the essentials.</p>`}
    <p class="tiny muted" style="margin-top:10px">${c.method === 'rules' ? 'Questions generated by rules (AI unavailable).' : c.method ? `Questions by ${c.method}.` : ''}</p>`);
}

$('#next').addEventListener('click', async (e) => {
  const err = $('#form-error');
  if (step === 0) {
    if (form.idea.value.trim().length < 30) { err.textContent = 'Describe the idea in at least 30 characters.'; form.idea.focus(); return; }
    show(1);
  } else if (step === 1) {
    await loadClarify(e.currentTarget);
    show(2);
  } else if (step === 2) {
    renderReview();
    show(3);
  }
});
$('#skip').addEventListener('click', () => { $$('[data-q]').forEach((t) => { t.value = ''; }); renderReview(); show(3); });
$('#prev').addEventListener('click', () => show(Math.max(0, step - 1)));
$('#run').addEventListener('click', async (e) => {
  const payload = { ...collect(), clarifications: answers() };
  await withBusy(e.currentTarget, async () => {
    try {
      const report = await post('/reports', payload);
      try { localStorage.removeItem(DRAFT); } catch { /* ignore */ }
      location.href = `results.html?id=${report.id}`;
    } catch (error) {
      $('#form-error').textContent = error.message;
      toastError(error);
    }
  });
});
show(0);
void raw;
