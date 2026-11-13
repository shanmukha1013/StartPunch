import { api, apiUrl, get, patch, post, uploadImage } from '../core/api.js';
import { boot } from '../core/shell.js';
import { $, $$, avatar, html, icon, param, person, raw, render, tagsInput, timeAgo, titleCase, toast, toastError, withBusy } from '../core/ui.js';

const { page, user } = await boot({ active: 'settings', title: 'Settings' });
const me = (await get('/auth/me')).user;
const welcome = param('welcome');

render(page, html`
  <div class="page-head"><div><p class="eyebrow">Settings</p><h1>${welcome ? 'Welcome to StartPunch — set up your profile' : 'Settings'}</h1>
    <p>${welcome ? 'A complete profile powers co-founder, collaborator and community recommendations.' : 'Profile, privacy, security and your data.'}</p></div>
    ${welcome ? html`<a class="btn btn--ghost" href="dashboard.html">Skip for now</a>` : ''}</div>
  <div class="tabs" role="tablist">${[['profile', 'Profile'], ['privacy', 'Privacy'], ['security', 'Security'], ['data', 'Your data'], ...(user.role === 'admin' ? [['moderation', 'Moderation']] : [])]
    .map(([id, l], i) => html`<button class="tab" role="tab" data-tab="${id}" aria-selected="${i === 0}">${l}</button>`)}</div>

  <form data-panel="profile" id="profile-form" class="split">
    <div class="card stack">
      <div class="row" style="gap:16px"><span id="avatar-preview">${avatar(me, 'lg')}</span>
        <div class="stack" style="margin:0"><label class="btn btn--ghost btn--sm">${icon('image')} Change photo<input type="file" accept="image/*" class="sr-only" id="avatar-file"></label>
          <label class="btn btn--quiet btn--sm">${icon('image')} Change cover<input type="file" accept="image/*" class="sr-only" id="cover-file"></label><span class="tiny muted" id="cover-state">${me.cover_url ? 'Cover image set' : 'No cover image'}</span></div></div>
      <div class="grid grid-2"><div class="field"><label for="name">Name</label><input class="input" id="name" maxlength="80" value="${me.name}"></div>
        <div class="field"><label for="handle">Handle</label><input class="input" id="handle" maxlength="30" value="${me.handle}" pattern="[a-z0-9_]{3,30}"></div></div>
      <div class="field"><label for="headline">Headline</label><input class="input" id="headline" maxlength="140" value="${me.headline}" placeholder="e.g. Building AI tools for exporters · ex-fintech PM"></div>
      <div class="field"><label for="bio">Bio</label><textarea class="textarea" id="bio" maxlength="2000">${me.bio}</textarea></div>
      <div class="field"><label for="location">Location</label><input class="input" id="location" maxlength="80" value="${me.location}"></div>
      <div class="field"><span class="label">Skills & expertise</span><div id="skills"></div></div>
      <div class="field"><span class="label">Interests</span><div id="interests"></div><span class="hint">e.g. fintech, AI, climate, creator economy</span></div>
      <div class="field"><span class="label">Industries</span><div id="industries"></div></div>
      <div class="grid grid-2"><div class="field"><span class="label">Looking for</span><div id="looking_for"></div><span class="hint">co-founder, designer, investors…</span></div>
        <div class="field"><span class="label">Open to</span><div id="open_to"></div><span class="hint">advising, freelance, joining a startup…</span></div></div>
      <div class="field"><span class="label">Links</span>${['website', 'linkedin', 'github', 'x', 'youtube', 'portfolio'].map((k) => html`<input class="input" data-link="${k}" placeholder="${titleCase(k)} URL" value="${me.links?.[k] || ''}" style="margin-top:6px">`)}</div>
      <div class="field"><span class="label">Achievements</span><textarea class="textarea" id="achievements" placeholder="One per line, e.g. Won Smart India Hackathon 2025" style="min-height:80px">${(me.achievements || []).map((a) => `${a.title}${a.year ? ` (${a.year})` : ''}`).join('\n')}</textarea></div>
      <p class="form-error" role="alert"></p>
      <div><button class="btn btn--yellow" data-busy="Saving">Save profile</button></div>
    </div>
    <aside class="card sticky"><h3>Preview</h3><div id="preview"></div><p class="tiny muted" style="margin-top:10px">Visible to ${me.profile_visibility === 'public' ? 'all members' : 'your connections'}.</p></aside>
  </form>

  <div data-panel="privacy" class="card hidden stack" style="max-width:720px">
    <div class="field"><label for="pv">Who can see your full profile and posts</label><select class="select" id="pv">
      <option value="public" ${me.profile_visibility === 'public' ? raw('selected') : ''}>All StartPunch members</option>
      <option value="connections" ${me.profile_visibility === 'connections' ? raw('selected') : ''}>Only my connections</option></select></div>
    <div class="field"><label for="mp">Who can message you</label><select class="select" id="mp">
      <option value="connections" ${me.message_policy === 'connections' ? raw('selected') : ''}>Connections and accepted collaborators</option>
      <option value="everyone" ${me.message_policy === 'everyone' ? raw('selected') : ''}>Any member</option></select></div>
    <div class="notice notice--ai">${icon('lock')}<div><strong>Your reports are always private</strong>Only summaries you explicitly publish appear on public startup pages.</div></div>
    <div><button class="btn btn--yellow" id="save-privacy">Save privacy settings</button></div>
  </div>

  <div data-panel="security" class="card hidden" style="max-width:560px">
    <form id="pw-form" class="stack"><h3>Change password</h3>
      <div class="field"><label for="cur">Current password</label><input class="input" id="cur" type="password" autocomplete="current-password"></div>
      <div class="field"><label for="new">New password</label><input class="input" id="new" type="password" autocomplete="new-password" minlength="8"></div>
      <p class="form-error" role="alert"></p><div><button class="btn">Update password</button></div></form>
    <hr class="divider"><h3>Sessions</h3><p class="small muted">Signs you out on every device, including this one.</p><button class="btn btn--ghost" id="logout-all">${icon('logout')} Sign out everywhere</button>
  </div>

  <div data-panel="data" class="card hidden stack" style="max-width:720px">
    <h3>Export your data</h3><p class="small muted" style="margin:0">Download everything we store about you: profile, reports, assistant conversations, posts, comments, connections and messages you sent.</p>
    <div><a class="btn btn--ghost" href="${apiUrl('/auth/export')}" download="startpunch-export.json">${icon('download')} Download JSON</a></div>
    <hr class="divider"><h3>Delete account</h3><p class="small muted" style="margin:0">Permanently deletes your account, reports, posts, comments, startups and messages. This cannot be undone.</p>
    <div class="row"><input class="input" type="password" id="del-pw" placeholder="Confirm with your password" autocomplete="current-password" style="max-width:280px"><button class="btn btn--ghost" id="delete-account">${icon('trash')} Delete my account</button></div>
  </div>
  ${user.role === 'admin' ? html`<div data-panel="moderation" class="hidden"><div class="segmented" style="margin-bottom:12px">${['open', 'actioned', 'dismissed'].map((s, i) => html`<button type="button" data-q="${s}" aria-pressed="${i === 0}">${titleCase(s)}</button>`)}</div><div id="mod-queue"></div></div>` : ''}`);

const tabsEl = $$('[role="tab"]');
const openTab = (id) => {
  tabsEl.forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === id)));
  $$('[data-panel]').forEach((p) => p.classList.toggle('hidden', p.dataset.panel !== id));
  if (id === 'moderation') loadQueue('open');
};
tabsEl.forEach((t) => t.addEventListener('click', () => openTab(t.dataset.tab)));
if (location.hash === '#moderation' && user.role === 'admin') openTab('moderation');

const lists = Object.fromEntries(['skills', 'interests', 'industries', 'looking_for', 'open_to'].map((k) => [k, tagsInput($(`#${k}`), me[k] || [])]));
let avatarId = null;
let coverId = null;
const drawPreview = () => render($('#preview'), html`${person({ ...me, name: $('#name').value, headline: $('#headline').value, handle: $('#handle').value })}
  <div class="chip-row" style="margin-top:10px">${lists.skills.get().slice(0, 5).map((s) => html`<span class="chip">${s}</span>`)}</div>`);
drawPreview();
$('#profile-form').addEventListener('input', drawPreview);

for (const [inputId, kind] of [['#avatar-file', 'avatar'], ['#cover-file', 'cover']]) {
  $(inputId).addEventListener('change', async (e) => {
    try {
      const media = await uploadImage(e.target.files[0]);
      if (kind === 'avatar') { avatarId = media.id; render($('#avatar-preview'), html`<span class="avatar avatar--lg"><img src="${media.url}" alt=""></span>`); }
      else { coverId = media.id; $('#cover-state').textContent = 'New cover ready — save to apply'; }
    } catch (error) { toastError(error); }
  });
}

$('#profile-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('#profile-form .form-error');
  err.textContent = '';
  const links = Object.fromEntries($$('[data-link]').map((i) => [i.dataset.link, i.value.trim()]).filter(([, v]) => v));
  const achievements = $('#achievements').value.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
    const m = l.match(/^(.*?)\s*\((\d{4})\)$/);
    return m ? { title: m[1], year: m[2] } : { title: l, year: '' };
  });
  const payload = { name: $('#name').value, headline: $('#headline').value, bio: $('#bio').value, location: $('#location').value, links, achievements,
    ...Object.fromEntries(Object.entries(lists).map(([k, l]) => [k, l.get()])) };
  if ($('#handle').value !== me.handle) payload.handle = $('#handle').value.toLowerCase();
  if (avatarId) payload.avatar_media_id = avatarId;
  if (coverId) payload.cover_media_id = coverId;
  await withBusy($('#profile-form button[data-busy]'), async () => {
    try { await patch('/me/profile', payload); toast('Profile saved'); if (welcome) location.href = 'network.html'; }
    catch (error) { err.textContent = error.message; }
  });
});

$('#save-privacy').addEventListener('click', async () => {
  try { await patch('/me/profile', { profile_visibility: $('#pv').value, message_policy: $('#mp').value }); toast('Privacy settings saved'); } catch (error) { toastError(error); }
});
$('#pw-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('#pw-form .form-error');
  try { await post('/auth/password', { current_password: $('#cur').value, new_password: $('#new').value }); toast('Password updated — other sessions were signed out'); e.target.reset(); err.textContent = ''; }
  catch (error) { err.textContent = error.message; }
});
$('#logout-all').addEventListener('click', async () => { try { await post('/auth/logout-all'); location.href = '../index.html'; } catch (error) { toastError(error); } });
$('#delete-account').addEventListener('click', async () => {
  if (!$('#del-pw').value) return toast('Enter your password to confirm', 'error');
  if (!window.confirm('Delete your StartPunch account permanently?')) return;
  try { await api('/auth/account', { method: 'DELETE', body: { password: $('#del-pw').value } }); location.href = '../index.html'; } catch (error) { toastError(error); }
});

async function loadQueue(status) {
  $$('[data-q]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.q === status)));
  const { reports } = await get(`/moderation/reports?status=${status}`);
  render($('#mod-queue'), reports.length ? html`${reports.map((r) => html`<div class="card" style="margin-bottom:10px"><div class="row between">
      <div><span class="chip chip--ink">${titleCase(r.reason)}</span> <span class="small muted">${r.entity_type} · reported ${timeAgo(r.created_at)} by ${r.reporter?.name || 'member'}</span></div>
      ${status === 'open' ? html`<div class="row"><button class="btn btn--sm" data-resolve="${r.id}" data-action="hide">Hide content</button><button class="btn btn--sm btn--ghost" data-resolve="${r.id}" data-action="dismiss">Dismiss</button></div>` : ''}</div>
      ${r.preview ? html`<blockquote class="small" style="margin:10px 0 0;padding:8px 12px;border-left:3px solid var(--y-400);background:var(--surface-2)">${r.preview}</blockquote>` : ''}
      ${r.details ? html`<p class="small" style="margin:8px 0 0">${r.details}</p>` : ''}
      ${r.entity_type === 'post' ? html`<a class="small" href="post.html?id=${r.entity_id}">Open post</a>` : ''}</div>`)}`
    : html`<p class="muted">Nothing here.</p>`);
}
$('[data-panel="moderation"]')?.addEventListener('click', async (e) => {
  const q = e.target.closest('[data-q]');
  if (q) loadQueue(q.dataset.q);
  const b = e.target.closest('[data-resolve]');
  if (b) { try { await post(`/moderation/reports/${b.dataset.resolve}/resolve`, { action: b.dataset.action }); toast('Resolved'); loadQueue('open'); } catch (error) { toastError(error); } }
});
