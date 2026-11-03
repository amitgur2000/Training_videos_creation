"""Log the demo therapist in to the web app, and keep the session for the headless recorder.

How login works (web_app_frontend useAuth.ts, myndz-ai-backend lambdas/mfa/define_auth_challenge.py):
the sign-in request carries localStorage["myndz_device_key_<email>"]. A device that passed the
emailed code once is trusted for 14 days and skips the code. Tokens live in localStorage too, so
Playwright's storage_state holds everything: C:/tmp/user_education/.auth/<env>-demo.json.

Order of attempts, each one only when the one before is not enough:
1. The saved state still has a live session: nothing to do.
2. Sign in with email and password (MYNDZ_DEMO_USER_EMAIL, MYNDZ_DEMO_USER_PASS). The saved device
   key skips the code. Fully headless, so a recording run never needs a person for 14 days.
3. The code is asked for: read it from the demo mailbox over IMAP when EDU_IMAP_PASS is set
   (a Gmail app password with IMAP enabled for that account).
4. Otherwise, a person: run this file. It opens a VISIBLE browser, signs in, and waits while you type
   the emailed code (and accept the terms of use if they appear). The device is then trusted.

    <playwright venv python> .claude/skills/user-education/scripts/edu_login.py [--env staging]

The state file holds login tokens. It lives outside the repo: never commit, print or copy it.
"""

from __future__ import annotations

import argparse
import email
import imaplib
import re
import sys
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from edu_env import ENVS, auth_state, refuse_unknown, secret

EXIT_NEEDS_LOGIN = 3
OTP_SENDER = 'verificationemail.com'
LANDED = re.compile(r'/(dashboard|client-management|calendar|patient|settings|notifications)')


class NeedsLogin(SystemExit):
    def __init__(self, env: str, why: str):
        super().__init__(EXIT_NEEDS_LOGIN)
        print(f'Login to {env} needs a person: {why}\n'
              'Run (a browser window opens; type the emailed code there):\n'
              '  <playwright venv python> .claude/skills/user-education/scripts/edu_login.py '
              f'--env {env}', file=sys.stderr)


def _otp_from_imap(since: float, timeout_s: float = 90) -> str | None:
    """The newest login code mailed after `since`, or None when IMAP is not configured."""
    password = secret('EDU_IMAP_PASS', required=False)
    if not password:
        return None
    user = secret('MYNDZ_DEMO_USER_EMAIL')
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        m = imaplib.IMAP4_SSL('imap.gmail.com', timeout=30)
        try:
            m.login(user, password.replace(' ', ''))
            m.select('INBOX', readonly=True)
            _, data = m.search(None, f'(FROM "{OTP_SENDER}")')
            for num in reversed(data[0].split()[-5:]):
                _, msg_data = m.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])
                if parsedate_to_datetime(msg['Date']).timestamp() < since - 5:
                    continue
                body = ''.join(p.get_payload(decode=True).decode(p.get_content_charset() or 'utf-8', 'replace')
                               for p in msg.walk() if p.get_content_maintype() == 'text')
                code = re.search(r'(?<!\d)(\d{6})(?!\d)', re.sub(r'<[^>]+>', ' ', body))
                if code:
                    return code.group(1)
        finally:
            try:
                m.logout()
            except (OSError, imaplib.IMAP4.error):
                pass  # the session is already done
        time.sleep(5)
    raise SystemExit('No login code arrived in the demo mailbox within 90 seconds.')


def _wait_landing(page, timeout_ms: int) -> str:
    """Where the app settled after sign-in: 'app', 'mfa', 'terms' or 'login'."""
    end = time.time() + timeout_ms / 1000
    while time.time() < end:
        url = page.url
        if '/verify-2fa' in url:
            return 'mfa'
        if '/terms-of-use' in url:
            return 'terms'
        if LANDED.search(url) and page.locator('[data-testid^="nav-"], [data-testid="dashboard-add-patient"]').count():
            return 'app'
        page.wait_for_timeout(300)
    return 'login'


def _wait_person(page, wait_min: float) -> str:
    """Headed mode: wait while a person types the code or accepts the terms, until the app loads."""
    end = time.time() + wait_min * 60
    while time.time() < end:
        if _wait_landing(page, 2000) == 'app':
            return 'app'
        page.wait_for_timeout(1000)
    return 'timeout'


def sign_in(page, env: str, headed: bool = False, wait_min: float = 30) -> None:
    """Make `page` logged in, by the cheapest of the steps in the module docstring."""
    base = ENVS[env]['app_url']
    page.goto(base + '/dashboard')
    page.wait_for_load_state('networkidle')
    if _wait_landing(page, 4000) == 'app':
        return
    page.goto(base + '/login')
    page.get_by_test_id('login-email').fill(secret('MYNDZ_DEMO_USER_EMAIL'))
    page.get_by_test_id('login-password').fill(secret('MYNDZ_DEMO_USER_PASS'))
    submitted = time.time()
    page.get_by_test_id('login-submit').click()
    where = _wait_landing(page, 30_000)
    if where == 'mfa':
        code = _otp_from_imap(submitted)
        if code:
            boxes = page.locator('input[inputmode="numeric"]')
            boxes.first.wait_for()
            for i, digit in enumerate(code):
                boxes.nth(i).fill(digit)
            page.get_by_test_id('mfa-verify-submit').click()
            page.wait_for_url(lambda u: '/verify-2fa' not in u, timeout=30_000)
            where = _wait_landing(page, 30_000)
        elif headed:
            print(f'Type the emailed code in the browser window. Waiting up to {wait_min:g} minutes...', flush=True)
            where = _wait_person(page, wait_min)
        else:
            raise NeedsLogin(env, 'the app asks for the emailed code (device not trusted, or trust expired)')
    if where == 'terms':
        if not headed:
            raise NeedsLogin(env, 'the app asks to accept the terms of use; a person must do that')
        print(f'Accept the terms of use in the browser window. Waiting up to {wait_min:g} minutes...', flush=True)
        where = _wait_person(page, wait_min)
    if where != 'app':
        if headed:
            raise SystemExit(f'Login did not reach the app (stopped at {page.url}).')
        raise NeedsLogin(env, f'sign-in did not reach the app (stopped at {page.url})')
    page.wait_for_load_state('networkidle')


def main() -> int:
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser()
    ap.add_argument('--env', default='staging')
    ap.add_argument('--timeout-min', type=float, default=30, help='How long to wait for the person.')
    args = ap.parse_args()
    refuse_unknown(args.env)
    state = auth_state(args.env)
    state.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, channel='chrome')
        ctx = browser.new_context(viewport={'width': 1400, 'height': 900},
                                  storage_state=str(state) if state.exists() else None)
        page = ctx.new_page()
        sign_in(page, args.env, headed=True, wait_min=args.timeout_min)
        ctx.storage_state(path=str(state))
        browser.close()
    print(f'Logged in; session and trusted-device key saved to {state}. Do not commit this file.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
