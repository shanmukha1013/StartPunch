import { api, post } from '../core/api.js';
import { $, withBusy } from '../core/ui.js';

const next = new URLSearchParams(location.search).get('next');
const safeNext = next && /^[a-z]+\.html(\?[^<>"']*)?$/i.test(next) ? next : 'dashboard.html';

api('/auth/session').then((s) => { if (s.authenticated) location.replace(safeNext); }).catch(() => {});

const tabs = { login: $('#tab-login'), signup: $('#tab-signup') };
const forms = { login: $('#login-form'), signup: $('#signup-form') };
function show(which) {
  Object.entries(tabs).forEach(([k, t]) => t.setAttribute('aria-pressed', String(k === which)));
  Object.entries(forms).forEach(([k, f]) => f.classList.toggle('hidden', k !== which));
  forms[which].querySelector('input').focus();
}
tabs.login.addEventListener('click', () => show('login'));
tabs.signup.addEventListener('click', () => show('signup'));
if (location.hash === '#signup') show('signup');

async function submit(form, path, payload) {
  const error = $('.form-error', form);
  error.textContent = '';
  await withBusy($('button[data-busy]', form), async () => {
    try {
      await post(path, payload);
      location.href = path.endsWith('signup') ? 'settings.html?welcome=1' : safeNext;
    } catch (e) {
      error.textContent = e.message;
    }
  });
}

forms.login.addEventListener('submit', (e) => {
  e.preventDefault();
  const f = forms.login;
  if (!f.email.value || !f.password.value) { $('.form-error', f).textContent = 'Enter your email and password.'; return; }
  submit(f, '/auth/login', { email: f.email.value, password: f.password.value });
});
forms.signup.addEventListener('submit', (e) => {
  e.preventDefault();
  const f = forms.signup;
  if (!f.name.value.trim() || !f.email.value.includes('@') || f.password.value.length < 8) {
    $('.form-error', f).textContent = 'Enter your name, a valid email and a password of at least 8 characters.';
    return;
  }
  submit(f, '/auth/signup', { name: f.name.value.trim(), email: f.email.value.trim(), password: f.password.value });
});
