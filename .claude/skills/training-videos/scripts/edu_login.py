"""Log in to the site, with MFA when it asks, and keep the session for the headless recorder.

Driven by the `login:` block of site.yaml (login.md documents every key). The ladder, cheapest
first; each rung runs only when the one before is not enough:

1. The saved session (Playwright storage_state: cookies, localStorage and IndexedDB, in
   site.session_file(env), outside every repo) still lands in the app: nothing to do.
2. Headless form login with credentials from the environment or .env. A device the site already
   remembers skips MFA here.
3. MFA is asked for and can be answered by a machine:
     method: totp   the code is computed from the shared secret (pyotp)       fully automatic
     method: email  the code is read over IMAP from the inbox it was sent to  fully automatic
4. Anything else (sms, push, passkey, SSO, CAPTCHA, a terms page with action: manual) needs a
   person. A headless run exits with code 3 and prints the command to run:

       python <skill>/scripts/edu_login.py --site <site> --env <env>

   It opens a VISIBLE browser, fills the credentials, and waits while the person finishes the rest.
   It succeeds only when the app itself has loaded (a page "waiting to leave" the MFA screen once
   counted as success; it must not). The session is then saved for the headless runs.

A site whose login fits none of this puts a training/<site>/login.py next to site.yaml defining
`sign_in(page, site, env, headed) -> None`; it replaces rungs 2 to 4.

Never print, log or commit the credentials, the TOTP secret or the session file.
"""

from __future__ import annotations

import argparse
import email
import imaplib
import importlib.util
import re
import sys
import time
from contextlib import suppress
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from edu_site import Site, launch_browser, load

EXIT_NEEDS_LOGIN = 3

DEFAULTS = {
    'required': True,
    'url': '/login',
    'logged_in': {'url_pattern': None, 'selector': None},
    'username': {'selector': 'input[type="email"], input[name*="user" i], input[name*="email" i], '
                             'input[autocomplete="username"], input[id*="user" i], input[id*="email" i]',
                 'env': 'SITE_USER'},
    'password': {'selector': 'input[type="password"]', 'env': 'SITE_PASS'},
    'submit': 'button[type="submit"], input[type="submit"]',
    'two_step': False,
    'next': None,
    'remember_me': None,
    'mfa': {
        'method': 'none',
        'detect': {'url_pattern': r'(mfa|2fa|otp|verify|two-factor|challenge)', 'selector': None},
        'code_input': 'input[autocomplete="one-time-code"], input[inputmode="numeric"], input[name*="code" i], '
                      'input[name*="otp" i]',
        'submit': 'button[type="submit"]',
        'remember_device': None,
        'totp_secret_env': 'SITE_TOTP_SECRET',
        'email': {'imap_host': None, 'imap_port': 993, 'user_env': None, 'pass_env': None, 'folder': 'INBOX',
                  'sender': None, 'subject': None, 'code_regex': r'(?<!\d)(\d{6})(?!\d)', 'timeout_s': 90},
    },
    'interstitials': [],
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def config(site: Site) -> dict:
    return _merge(DEFAULTS, site.get('login') or {})


class NeedsLogin(SystemExit):
    def __init__(self, site: Site, env: str, why: str):
        super().__init__(EXIT_NEEDS_LOGIN)
        print(f'Login to {site.name} ({env}) needs a person: {why}\n'
              'Run this; a browser window opens, finish the login there:\n'
              f'  python {Path(__file__).resolve()} --site {site.name} --env {env}', file=sys.stderr)


# ---------- where is the page? ----------

def _visible(page, selector: str | None) -> bool:
    if not selector:
        return False
    with suppress(Exception):
        loc = page.locator(selector)
        return any(loc.nth(i).is_visible() for i in range(min(loc.count(), 5)))
    return False


def _matches(page, rule: dict | None) -> bool:
    rule = rule or {}
    url_hit = bool(rule.get('url_pattern')) and re.search(rule['url_pattern'], page.url, re.IGNORECASE) is not None
    return url_hit or _visible(page, rule.get('selector'))


def on_login_page(page, lc: dict) -> bool:
    login_path = lc['url'] if not re.match(r'https?://', lc['url']) else re.sub(r'https?://[^/]+', '', lc['url'])
    on_url = login_path not in ('', '/') and login_path.split('?')[0] in page.url
    return on_url or _visible(page, lc['password']['selector'])


def where(page, lc: dict) -> str:
    """'mfa', 'interstitial:<n>', 'app' or 'login'."""
    if lc['mfa']['method'] != 'none' or lc['mfa']['detect'].get('selector'):
        mfa = lc['mfa']['detect']
        if _matches(page, mfa) and not _visible(page, lc['password']['selector']):
            return 'mfa'
    for i, rule in enumerate(lc['interstitials']):
        if _matches(page, rule):
            return f'interstitial:{i}'
    li = lc['logged_in']
    if li.get('url_pattern') or li.get('selector'):
        url_ok = not li.get('url_pattern') or re.search(li['url_pattern'], page.url, re.IGNORECASE)
        sel_ok = not li.get('selector') or _visible(page, li['selector'])
        if url_ok and sel_ok:
            return 'app'
        return 'login'
    return 'login' if on_login_page(page, lc) else 'app'


def _settle(page, timeout_ms: int = 10_000) -> None:
    with suppress(Exception):
        page.wait_for_load_state('networkidle', timeout=timeout_ms)


def _wait_change(page, lc: dict, timeout_ms: int, from_state: str = 'login') -> str:
    end = time.time() + timeout_ms / 1000
    state = where(page, lc)
    while time.time() < end:
        state = where(page, lc)
        if state != from_state:
            return state
        page.wait_for_timeout(300)
    return state


def _already_in(page, lc: dict, timeout_ms: int = 4000) -> bool:
    """True when the page shows the app and still does a moment later: a single-page app may paint
    its shell before its auth check redirects to the login page."""
    end = time.time() + timeout_ms / 1000
    while time.time() < end:
        if where(page, lc) == 'app':
            page.wait_for_timeout(700)
            _settle(page, 3000)
            if where(page, lc) == 'app':
                return True
        page.wait_for_timeout(300)
    return False


def _wait_person(page, lc: dict, wait_min: float) -> str:
    """Headed mode: wait while a person finishes MFA, SSO or a terms page, until the app loads."""
    end = time.time() + wait_min * 60
    while time.time() < end:
        if where(page, lc) == 'app':
            _settle(page)
            if where(page, lc) == 'app':
                return 'app'
        page.wait_for_timeout(1000)
    return 'timeout'


# ---------- the form ----------

def _first_visible(page, selector: str, timeout_ms: int = 15_000):
    loc = page.locator(selector)
    end = time.time() + timeout_ms / 1000
    while time.time() < end:
        for i in range(min(loc.count(), 10)):
            if loc.nth(i).is_visible():
                return loc.nth(i)
        page.wait_for_timeout(200)
    raise SystemExit(f'Login: no visible element for {selector!r} at {page.url}. Set it in site.yaml login.')


def _tick(page, selector: str | None) -> None:
    if selector and _visible(page, selector):
        box = page.locator(selector).first
        with suppress(Exception):
            if not box.is_checked():
                box.check()


def _fill_form(page, site: Site, env: dict, lc: dict) -> float:
    page.goto(site.url(env, lc['url']))
    _settle(page)
    user = _first_visible(page, lc['username']['selector'])
    user.fill(site.secret(lc['username']['env']))
    if lc['two_step']:
        _first_visible(page, lc['next'] or lc['submit']).click()
    pw = _first_visible(page, lc['password']['selector'])
    pw.fill(site.secret(lc['password']['env']))
    _tick(page, lc['remember_me'])
    submitted = time.time()
    _first_visible(page, lc['submit']).click()
    return submitted


# ---------- MFA ----------

def _totp(site: Site, mfa: dict) -> str:
    import pyotp
    totp = pyotp.TOTP(site.secret(mfa['totp_secret_env']).replace(' ', ''))
    left = totp.interval - time.time() % totp.interval
    if left < 4:                      # too close to the edge; wait for a fresh code
        time.sleep(left + 0.5)
    return totp.now()


def _email_code(site: Site, mfa: dict, since: float) -> str:
    cfg = mfa['email']
    if not (cfg.get('imap_host') and cfg.get('user_env') and cfg.get('pass_env')):
        raise SystemExit('login.mfa.method is email, but login.mfa.email needs imap_host, user_env and pass_env.')
    user, password = site.secret(cfg['user_env']), site.secret(cfg['pass_env'])
    criteria = []
    if cfg.get('sender'):
        criteria.append(f'FROM "{cfg["sender"]}"')
    if cfg.get('subject'):
        criteria.append(f'SUBJECT "{cfg["subject"]}"')
    query = f'({" ".join(criteria)})' if criteria else 'ALL'
    deadline = time.time() + float(cfg.get('timeout_s') or 90)
    while time.time() < deadline:
        m = imaplib.IMAP4_SSL(cfg['imap_host'], int(cfg.get('imap_port') or 993), timeout=30)
        try:
            m.login(user, password.replace(' ', ''))
            m.select(cfg.get('folder') or 'INBOX', readonly=True)
            _, data = m.search(None, query)
            for num in reversed(data[0].split()[-5:]):
                _, msg_data = m.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])
                if parsedate_to_datetime(msg['Date']).timestamp() < since - 5:
                    continue
                body = ''.join(p.get_payload(decode=True).decode(p.get_content_charset() or 'utf-8', 'replace')
                               for p in msg.walk() if p.get_content_maintype() == 'text')
                code = re.search(cfg['code_regex'], re.sub(r'<[^>]+>', ' ', body))
                if code:
                    return code.group(1)
        finally:
            with suppress(OSError, imaplib.IMAP4.error):
                m.logout()
        time.sleep(5)
    raise SystemExit(f'No login code arrived in the mailbox within {cfg.get("timeout_s") or 90} seconds.')


def _enter_code(page, mfa: dict, code: str) -> None:
    boxes = page.locator(mfa['code_input'])
    boxes.first.wait_for()
    visible = [boxes.nth(i) for i in range(boxes.count()) if boxes.nth(i).is_visible()]
    if len(visible) >= len(code):     # one box per digit
        for box, digit in zip(visible, code):
            box.fill(digit)
    else:
        visible[0].fill(code)
    _tick(page, mfa['remember_device'])
    if _visible(page, mfa['submit']):
        with suppress(Exception):
            page.locator(mfa['submit']).first.click(timeout=3000)
    else:
        page.keyboard.press('Enter')


# ---------- the ladder ----------

def _custom(site: Site):
    path = site.root / 'login.py'
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f'{site.name}_login', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.sign_in


def sign_in(page, site: Site, env: dict, headed: bool = False, wait_min: float = 30) -> None:
    """Make `page` logged in, by the cheapest rung of the module docstring's ladder."""
    lc = config(site)
    if not lc['required']:
        return
    start = site.url(env, site.get('start_page') or '/')
    page.goto(start)
    _settle(page)
    if _already_in(page, lc):
        return
    custom = _custom(site)
    if custom is not None:
        custom(page, site, env, headed)
        return

    submitted = _fill_form(page, site, env, lc)
    state = _wait_change(page, lc, 30_000)
    for _ in range(6):
        if state == 'app':
            break
        if state == 'mfa':
            method = lc['mfa']['method']
            code = (_totp(site, lc['mfa']) if method == 'totp'
                    else _email_code(site, lc['mfa'], submitted) if method == 'email' else None)
            if code:
                _enter_code(page, lc['mfa'], code)
                state = _wait_change(page, lc, 30_000, from_state='mfa')
            elif headed:
                print(f'Finish the verification ({method}) in the browser window. '
                      f'Waiting up to {wait_min:g} minutes...', flush=True)
                state = _wait_person(page, lc, wait_min)
            else:
                raise NeedsLogin(site, env['name'], f'the site asks for verification ({method}), '
                                 'and this device is not remembered (or no longer)')
        elif state.startswith('interstitial:'):
            rule = lc['interstitials'][int(state.split(':')[1])]
            if rule.get('click'):
                page.locator(rule['click']).first.click()
                state = _wait_change(page, lc, 30_000, from_state=state)
            elif headed:
                print(f'Finish the page at {page.url} in the browser window. Waiting up to {wait_min:g} minutes...',
                      flush=True)
                state = _wait_person(page, lc, wait_min)
            else:
                raise NeedsLogin(site, env['name'], f'a page after login needs a person ({page.url})')
        elif headed:
            print('Login did not reach the app by itself; finish it in the browser window. '
                  f'Waiting up to {wait_min:g} minutes...', flush=True)
            state = _wait_person(page, lc, wait_min)
        else:
            raise NeedsLogin(site, env['name'], f'sign-in did not reach the app (stopped at {page.url}); '
                             'check the credentials and the login selectors')
    if state != 'app':
        raise SystemExit(f'Login did not reach the app (stopped at {page.url}).')
    _settle(page)


def save_session(ctx, site: Site, env_name: str) -> Path:
    path = site.session_file(env_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ctx.storage_state(path=str(path), indexed_db=True)
    except TypeError:   # Playwright before 1.51
        ctx.storage_state(path=str(path))
    return path


def main() -> int:
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser(description='Log in once with a visible browser and save the session.')
    ap.add_argument('--site', required=True)
    ap.add_argument('--env', default=None)
    ap.add_argument('--timeout-min', type=float, default=30, help='How long to wait for the person.')
    ap.add_argument('--headless', action='store_true',
                    help='Check only: try the automatic rungs, exit 3 if a person is needed.')
    ap.add_argument('--allow-production', action='store_true')
    args = ap.parse_args()
    site = load(args.site)
    env = site.env(args.env, args.allow_production)
    state = site.session_file(env['name'])
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=args.headless)
        ctx = browser.new_context(viewport={'width': 1400, 'height': 900},
                                  storage_state=str(state) if state.exists() else None)
        if site.get('test_id_attribute'):
            pw.selectors.set_test_id_attribute(site.get('test_id_attribute'))
        page = ctx.new_page()
        sign_in(page, site, env, headed=not args.headless, wait_min=args.timeout_min)
        path = save_session(ctx, site, env['name'])
        browser.close()
    print(f'Logged in to {site.name} ({env["name"]}); session saved to {path}. Never commit this file.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
