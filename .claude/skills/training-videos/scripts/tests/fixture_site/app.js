// A tiny fake web app for testing the training-videos skill end to end: login, TOTP MFA, a terms page,
// a cookie banner, a skeleton loader, he/en UI (RTL), and different controls on desktop and mobile.
// Everything lives in localStorage. The credentials and TOTP secret are fixture values, not secrets.
const DEMO = { user: 'demo@example.com', pass: 'demo-pass', totp: 'JBSWY3DPEHPK3PXP' };
const LOCALE_KEY = 'demo.locale';

const store = {
  get: (k) => localStorage.getItem(k),
  set: (k, v) => localStorage.setItem(k, v),
  del: (k) => localStorage.removeItem(k),
  json: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } },
};

let T = {};
function t(key, vars = {}) {
  let s = key.split('.').reduce((n, p) => (n && n[p] !== undefined ? n[p] : null), T) ?? key;
  for (const [k, v] of Object.entries(vars)) s = s.replace('{{' + k + '}}', v);
  return s;
}

async function loadLocale() {
  const locale = store.get(LOCALE_KEY) || 'he';
  T = await (await fetch(`locales/${locale}.json`)).json();
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === 'he' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-t]').forEach((el) => { el.textContent = t(el.dataset.t); });
  document.querySelectorAll('[data-t-placeholder]').forEach((el) => { el.placeholder = t(el.dataset.tPlaceholder); });
  document.querySelectorAll('[data-t-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.tAria)); });
  document.title = t('app.name');
}

function go(page) { location.href = page; }

function requireAuth() {
  if (store.get('demo.auth') !== 'ok') { go('login.html'); return false; }
  if (store.get('demo.terms') !== 'ok' && !location.pathname.endsWith('terms.html')) { go('terms.html'); return false; }
  return true;
}

function cookieBanner() {
  if (store.get('demo.cookies') === 'ok') return;
  const b = document.createElement('div');
  b.className = 'cookie';
  b.innerHTML = `<span>${t('cookie.text')}</span><button id="cookie-accept">${t('cookie.accept')}</button>`;
  document.body.appendChild(b);
  b.querySelector('button').onclick = () => { store.set('demo.cookies', 'ok'); b.remove(); };
}

function toast(text, ms = 4000) {
  const d = document.createElement('div');
  d.className = 'toast'; d.setAttribute('role', 'status'); d.textContent = text;
  document.body.appendChild(d);
  setTimeout(() => d.remove(), ms);
}

async function totp(secret, when = Date.now()) {
  const abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const c of secret.replace(/=+$/, '').toUpperCase()) bits += abc.indexOf(c).toString(2).padStart(5, '0');
  const key = new Uint8Array(Math.floor(bits.length / 8)).map((_, i) => parseInt(bits.substr(i * 8, 8), 2));
  const counter = Math.floor(when / 1000 / 30);
  const msg = new DataView(new ArrayBuffer(8));
  msg.setUint32(0, Math.floor(counter / 2 ** 32)); msg.setUint32(4, counter >>> 0);
  const k = await crypto.subtle.importKey('raw', key, { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
  const h = new Uint8Array(await crypto.subtle.sign('HMAC', k, msg.buffer));
  const o = h[19] & 15;
  const n = (((h[o] & 127) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3]) % 1e6;
  return String(n).padStart(6, '0');
}

function shell(active) {
  const nav = document.querySelector('nav.side');
  if (!nav) return;
  nav.innerHTML = `
    <a data-testid="nav-dashboard" href="dashboard.html" class="${active === 'dashboard' ? 'on' : ''}">${t('nav.dashboard')}</a>
    <a data-testid="nav-requests" href="request.html" class="${active === 'request' ? 'on' : ''}">${t('nav.newRequest')}</a>
    <a data-testid="nav-logout" href="#" id="logout">${t('nav.logout')}</a>`;
  nav.querySelector('#logout').onclick = (e) => { e.preventDefault(); store.del('demo.auth'); go('login.html'); };
  const toggle = document.querySelector('[data-testid="menu-toggle"]');
  if (toggle) toggle.onclick = () => nav.classList.toggle('open');
}
