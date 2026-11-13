import { api } from '../core/api.js';

const fmt = (n) => Number(n || 0).toLocaleString();

api('/intelligence/public-overview').then((data) => {
  document.querySelectorAll('#kb-numbers [data-k]').forEach((el) => { el.textContent = fmt(data[el.dataset.k]); });
  if (data.built_at) {
    document.getElementById('kb-note').textContent =
      `Snapshot built ${new Date(data.built_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })} from: ${data.sources.join(', ')}.`;
  }
}).catch(() => {
  document.getElementById('kb-note').textContent = 'Live knowledge-base numbers are unavailable right now.';
});

api('/auth/session').then((s) => {
  if (!s.authenticated) return;
  for (const id of ['nav-cta', 'hero-cta']) {
    const el = document.getElementById(id);
    if (el) { el.href = 'pages/dashboard.html'; el.textContent = 'Open workspace'; }
  }
  document.getElementById('nav-signin')?.remove();
}).catch(() => {});
