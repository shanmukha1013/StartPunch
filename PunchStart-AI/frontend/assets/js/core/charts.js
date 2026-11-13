// Minimal SVG charts. Single-series → one hue (purple), no legend; hairline recessive grid;
// <=24px bars with 4px rounded data-end; 2px lines; >=8px dots with a surface ring; hover tooltips;
// every chart offers a table view (identity/value never depends on color alone).
import { esc, html, raw, render } from './ui.js';

function tooltip(container) {
  let tip = container.querySelector('.chart-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'chart-tip hidden';
    container.append(tip);
  }
  return {
    show(x, y, content) { tip.innerHTML = content; tip.style.left = `${x}px`; tip.style.top = `${y}px`; tip.classList.remove('hidden'); },
    hide() { tip.classList.add('hidden'); },
  };
}

function withTable(container, chartHtml, rows, headers, caption) {
  const id = `t${Math.random().toString(36).slice(2, 8)}`;
  render(container, html`<div class="chart">${raw(chartHtml)}</div>
    <details class="table-toggle"><summary class="muted small">Show as table</summary>
      <div class="table-wrap"><table class="data" id="${id}"><caption class="sr-only">${caption}</caption>
        <thead><tr>${headers.map((h) => html`<th>${h}</th>`)}</tr></thead>
        <tbody>${rows.map((r) => html`<tr>${r.map((c) => html`<td>${c}</td>`)}</tr>`)}</tbody></table></div></details>`);
  return container.querySelector('.chart');
}

/** Horizontal bars: rows = [{label, value, display?}] */
export function barsH(container, rows, { max = null, caption = 'Chart', format = (v) => v } = {}) {
  if (!rows.length) { container.innerHTML = '<p class="muted small">No data.</p>'; return; }
  const top = max ?? Math.max(...rows.map((r) => r.value), 1);
  const labelW = 150, barMax = 360, rowH = 30, barH = 14, width = labelW + barMax + 60;
  const height = rows.length * rowH + 4;
  const parts = [`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(caption)}">`];
  rows.forEach((r, i) => {
    const y = i * rowH + 4;
    const w = Math.max(3, (r.value / top) * barMax);
    const label = r.label.length > 22 ? `${r.label.slice(0, 21)}…` : r.label;
    parts.push(`<text class="axis-text" x="${labelW - 10}" y="${y + barH - 2}" text-anchor="end">${esc(label)}</text>`);
    parts.push(`<rect class="grid-line" x="${labelW}" y="${y + barH / 2}" width="${barMax}" height="1" fill="currentColor" opacity=".0"></rect>`);
    parts.push(`<path class="mark" d="M${labelW},${y} h${Math.max(0, w - 4)} a4,4 0 0 1 4,4 v${barH - 8} a4,4 0 0 1 -4,4 h-${Math.max(0, w - 4)} z"></path>`);
    parts.push(`<text class="val-text" x="${labelW + w + 6}" y="${y + barH - 2}">${esc(r.display ?? format(r.value))}</text>`);
    parts.push(`<rect class="hit" data-i="${i}" x="0" y="${y - 6}" width="${width}" height="${rowH}"></rect>`);
  });
  parts.push(`<line class="grid-line" x1="${labelW}" x2="${labelW}" y1="0" y2="${height}"></line></svg>`);
  const chart = withTable(container, parts.join(''), rows.map((r) => [r.label, r.display ?? format(r.value)]), ['Item', 'Value'], caption);
  const tip = tooltip(chart);
  chart.querySelectorAll('.hit').forEach((hit) => {
    hit.addEventListener('mousemove', (e) => {
      const r = rows[Number(hit.dataset.i)];
      const box = chart.getBoundingClientRect();
      tip.show(e.clientX - box.left, e.clientY - box.top, `${esc(r.label)}: <strong>${esc(r.display ?? format(r.value))}</strong>${r.note ? `<br>${esc(r.note)}` : ''}`);
    });
    hit.addEventListener('mouseleave', tip.hide);
  });
}

/** Vertical columns: rows = [{label, value}] */
export function columns(container, rows, { caption = 'Chart', format = (v) => v, highlightLast = false } = {}) {
  if (!rows.length) { container.innerHTML = '<p class="muted small">No data.</p>'; return; }
  const width = 560, height = 200, padL = 34, padB = 26, padT = 18;
  const top = Math.max(...rows.map((r) => r.value), 1);
  const nice = niceMax(top);
  const slot = (width - padL) / rows.length;
  const bw = Math.min(24, slot * 0.62);
  const scale = (v) => (v / nice) * (height - padB - padT);
  const parts = [`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(caption)}">`];
  [0, 0.5, 1].forEach((f) => {
    const y = height - padB - f * (height - padB - padT);
    parts.push(`<line class="grid-line" x1="${padL}" x2="${width}" y1="${y}" y2="${y}"></line><text class="axis-text" x="${padL - 6}" y="${y + 4}" text-anchor="end">${esc(format(Math.round(nice * f)))}</text>`);
  });
  const labelEvery = Math.ceil(rows.length / 12);
  rows.forEach((r, i) => {
    const x = padL + i * slot + (slot - bw) / 2;
    const h = Math.max(r.value ? 3 : 0, scale(r.value));
    const y = height - padB - h;
    const cls = highlightLast && i !== rows.length - 1 ? 'mark dim' : 'mark';
    if (h > 0) parts.push(`<path class="${cls}" d="M${x},${height - padB} v-${Math.max(0, h - 4)} a4,4 0 0 1 4,-4 h${bw - 8} a4,4 0 0 1 4,4 v${Math.max(0, h - 4)} z"></path>`);
    if (i % labelEvery === 0 || i === rows.length - 1) parts.push(`<text class="axis-text" x="${x + bw / 2}" y="${height - 8}" text-anchor="middle">${esc(r.label)}</text>`);
    parts.push(`<rect class="hit" data-i="${i}" x="${padL + i * slot}" y="${padT - 10}" width="${slot}" height="${height - padB - padT + 10}"></rect>`);
  });
  const peak = rows.reduce((best, r, i) => (r.value > rows[best].value ? i : best), 0);
  const px = padL + peak * slot + slot / 2;
  parts.push(`<text class="val-text" x="${px}" y="${height - padB - scale(rows[peak].value) - 6}" text-anchor="middle">${esc(format(rows[peak].value))}</text></svg>`);
  const chart = withTable(container, parts.join(''), rows.map((r) => [r.label, format(r.value)]), ['Period', 'Value'], caption);
  const tip = tooltip(chart);
  chart.querySelectorAll('.hit').forEach((hit) => {
    hit.addEventListener('mousemove', (e) => {
      const r = rows[Number(hit.dataset.i)];
      const box = chart.getBoundingClientRect();
      tip.show(e.clientX - box.left, e.clientY - box.top, `${esc(r.label)}: <strong>${esc(format(r.value))}</strong>`);
    });
    hit.addEventListener('mouseleave', tip.hide);
  });
}

/** Line with dots: points = [{label, value, href?}], fixed y-domain [min,max]. */
export function line(container, points, { min = 0, max = 100, caption = 'Chart', format = (v) => v } = {}) {
  if (!points.length) { container.innerHTML = '<p class="muted small">No data.</p>'; return; }
  const width = 560, height = 200, padL = 34, padR = 16, padB = 26, padT = 16;
  const x = (i) => padL + (points.length === 1 ? (width - padL - padR) / 2 : (i / (points.length - 1)) * (width - padL - padR));
  const y = (v) => height - padB - ((v - min) / (max - min)) * (height - padB - padT);
  const parts = [`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(caption)}">`];
  [min, (min + max) / 2, max].forEach((v) => parts.push(`<line class="grid-line" x1="${padL}" x2="${width - padR}" y1="${y(v)}" y2="${y(v)}"></line><text class="axis-text" x="${padL - 6}" y="${y(v) + 4}" text-anchor="end">${esc(format(v))}</text>`));
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.value)}`).join(' ');
  if (points.length > 1) {
    parts.push(`<path class="area" d="${d} L${x(points.length - 1)},${y(min)} L${x(0)},${y(min)} Z"></path>`);
    parts.push(`<path class="line" d="${d}"></path>`);
  }
  points.forEach((p, i) => parts.push(`<circle class="dot" cx="${x(i)}" cy="${y(p.value)}" r="5"></circle><rect class="hit" data-i="${i}" x="${x(i) - 16}" y="${padT - 8}" width="32" height="${height - padB - padT + 16}"></rect>`));
  const last = points.length - 1;
  parts.push(`<text class="val-text" x="${x(last)}" y="${y(points[last].value) - 10}" text-anchor="middle">${esc(format(points[last].value))}</text></svg>`);
  const chart = withTable(container, parts.join(''), points.map((p) => [p.label, format(p.value)]), ['Report', 'Score'], caption);
  const tip = tooltip(chart);
  chart.querySelectorAll('.hit').forEach((hit) => {
    const p = points[Number(hit.dataset.i)];
    hit.addEventListener('mousemove', () => {
      const box = chart.getBoundingClientRect();
      const svg = chart.querySelector('svg').getBoundingClientRect();
      const scaleX = svg.width / width;
      tip.show(x(Number(hit.dataset.i)) * scaleX + (svg.left - box.left), y(p.value) * (svg.height / height) + (svg.top - box.top), `${esc(p.label)}: <strong>${esc(format(p.value))}</strong>`);
    });
    hit.addEventListener('mouseleave', tip.hide);
    if (p.href) hit.addEventListener('click', () => { location.href = p.href; });
  });
}

/** Score ring (0-100). The track is a lighter step of the same ramp. */
export function scoreRing(score, label = 'of 100') {
  const r = 62, c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score ?? 0)) / 100;
  return raw(`<div class="score-ring" role="img" aria-label="Score ${score} out of 100">
    <svg viewBox="0 0 148 148"><circle cx="74" cy="74" r="${r}" fill="none" stroke="var(--y-200)" stroke-width="12"/>
    <circle cx="74" cy="74" r="${r}" fill="none" stroke="var(--k-900)" stroke-width="12" stroke-linecap="round" stroke-dasharray="${c * pct} ${c}"/></svg>
    <div class="num"><div><strong>${score ?? '—'}</strong><span>${esc(label)}</span></div></div></div>`);
}

export function meter(value, max = 10, ink = false) {
  const pct = Math.max(0, Math.min(1, (value ?? 0) / max)) * 100;
  return raw(`<div class="bar-track" role="img" aria-label="${value} of ${max}"><div class="bar-fill ${ink ? 'ink' : ''}" style="width:${pct}%"></div></div>`);
}

function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p) * p;
}
