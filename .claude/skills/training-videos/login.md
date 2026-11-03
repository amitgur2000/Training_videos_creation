# Login and MFA

How the recorder gets into a site that needs a login, with or without a second factor, without a person at every run. Code: `scripts/edu_login.py`; configuration: the `login:` block of `training/<site>/site.yaml`.

## The principle: log in once, reuse the session

A recording logs in **off camera**, in a separate browser context, and films in a context that starts from the saved session. The session is Playwright's `storage_state`: cookies, localStorage and IndexedDB, saved after every successful login to `~/.training_videos/<site>/<env>.json` (or `session_dir`). It sits outside every repo. It holds live login tokens, so never commit, print, copy or upload it.

Many sites also **remember the device** after a successful MFA (a cookie or a localStorage key, for days or weeks). The saved session carries that too, so a fresh password login skips MFA for as long as the site remembers the device.

## The ladder

Each run tries the cheapest rung first, and climbs only when that is not enough:

| # | Rung | Needs a person? |
|---|---|---|
| 1 | The saved session still lands in the app | no |
| 2 | Headless form login with the credentials from `.env`; a remembered device skips MFA | no |
| 3 | MFA answered by a machine: `totp` (the code is computed from the shared secret) or `email` (the code is read over IMAP) | no |
| 4 | Anything else: exit **code 3**, and a person finishes the login once in a visible browser | yes, once |

**Exit code 3** from `edu_run.py`, `edu_explore.py` or `edu_login.py --headless` always means "a person must log in". The message prints the command:

```bash
python .claude/skills/training-videos/scripts/edu_login.py --site <site> --env <env>
```

It opens a **visible** Chrome, fills the credentials, and waits (30 minutes by default, `--timeout-min`) while the person types the SMS code, approves the push, completes SSO, solves a CAPTCHA or accepts terms. It succeeds only when the app itself has loaded, never merely because the MFA page appeared or changed. (An early version gave up the moment it saw the code page, because the page it was "waiting to leave" counted as an answer.) The session, with the now-remembered device, is then saved, and headless runs work again.

The agent starts it in the background and tells the user a window is waiting for them. Never ask the user to paste a code, a password or a secret into the chat.

## Choosing the MFA method (init asks this)

| What the site does | `login.mfa.method` | Fully automatic? | What to set up |
|---|---|---|---|
| No second factor | `none` | yes | nothing |
| Authenticator app (TOTP: Google Authenticator, Authy, 1Password...) | `totp` | yes | When enrolling the demo account, keep the **secret** behind the QR code (the "can't scan? enter this key" text). Put it in `.env` as the variable named by `totp_secret_env`. |
| Code by email | `email` | yes, with IMAP | A mailbox the demo account uses, with IMAP enabled and an app password (Gmail, Outlook and most hosts require one). Set `imap_host`, `user_env`, `pass_env`, and `sender` or `subject` to find the right message. |
| Code by SMS, push approval, passkey, hardware key | `manual` | no; once per remembered-device period | Nothing. Run `edu_login.py` when exit code 3 appears. |
| SSO (Google, Microsoft, Okta, SAML) | `manual`, or a `login.py` | usually once per session lifetime | Prefer a demo account that signs in with a password. Otherwise a person signs in once; the saved session usually lasts days. |
| CAPTCHA or bot challenge | `manual` | no | Ask the site owner to allow-list the demo account or the test environment. Never automate around it. |

If the site lets the user choose between methods, choose TOTP for the demo account: it is the only one that is automatic, needs no mailbox, and is supported everywhere.

## Configuration

Every key is optional except where the site differs from the defaults. Selectors are Playwright selectors (CSS, `text=`, `role=`); each one is tried against the visible elements.

```yaml
login:
  required: true                  # false: the site is public; nothing below is used
  url: /login                     # where the form is; absolute URLs are allowed (an identity provider)
  logged_in:                      # how to tell the app has loaded. Set at least one; both = both must hold
    url_pattern: '/(dashboard|home|app)'
    selector: 'nav [data-testid="user-menu"]'
  username: {selector: 'input[type="email"], input[name*="user" i], ...', env: SITE_USER}
  password: {selector: 'input[type="password"]', env: SITE_PASS}
  submit: 'button[type="submit"], input[type="submit"]'
  two_step: false                 # true: username, then Next, then password on the next screen
  next: null                      # the Next button for two_step (default: submit)
  remember_me: null               # a "keep me signed in" checkbox to tick, if any
  mfa:
    method: none                  # none | totp | email | manual
    detect:                       # how to recognize the MFA screen
      url_pattern: '(mfa|2fa|otp|verify|two-factor|challenge)'
      selector: null
    code_input: 'input[autocomplete="one-time-code"], input[inputmode="numeric"], ...'
                                  # one box gets the whole code; one box per digit is detected
    submit: 'button[type="submit"]'   # Enter is pressed when no submit is visible
    remember_device: null         # "trust this device" checkbox: always set it when the site has one
    totp_secret_env: SITE_TOTP_SECRET
    email:
      imap_host: imap.gmail.com
      imap_port: 993
      user_env: SITE_MAIL_USER
      pass_env: SITE_MAIL_APP_PASSWORD
      folder: INBOX
      sender: no-reply@example.com
      subject: null
      code_regex: '(?<!\d)(\d{6})(?!\d)'
      timeout_s: 90
  interstitials:                  # pages that can appear after login, in any order
    - {url_pattern: '/terms', click: 'button#accept'}           # handled automatically
    - {url_pattern: '/whats-new', click: 'text=Skip'}
    - {selector: '#password-expiry', action: manual}            # a person must handle it
```

The credentials themselves go in `training/<site>/.env` (git-ignored) or the process environment:

```bash
SITE_USER=demo@example.com
SITE_PASS=...
SITE_TOTP_SECRET=JBSWY3DPEHPK3PXP
```

## When the built-in flow does not fit

Put `training/<site>/login.py` next to site.yaml:

```python
def sign_in(page, site, env, headed):
    """Leave `page` logged in. site.secret('NAME') reads .env; site.url(env, '/path') builds URLs.
    Raise SystemExit(3) when a person is needed and headed is False."""
```

It replaces rungs 2 to 4; rung 1 (the saved session) and the session saving still apply. Typical uses: a login inside an iframe, a magic link, an API that returns a token you set in localStorage.

## Mid-recording expiry

`r.open()` (and `Session.open()`) checks after navigating whether the page is a login page. If so, it signs in again and returns to the page. The recording starts only after the start page has opened logged in. A session that expires in the middle of filming shows the login page in the video. The run then fails on its next locator: log in and re-run.

## Limits

- **sessionStorage is not saved** by Playwright. A site that keeps its token only in sessionStorage logs in on every run: fine with `totp` or `email`, a person each time with `manual`. A `login.py` can restore it with an init script.
- **Short sessions.** A site that expires sessions within minutes still works: the password and automatic MFA rungs run off camera before filming.
- **One account per site and environment.** A chapter that needs two roles (an admin and a user) needs a second site entry or a `login.py`; ask the user.

## Checking a site's login

```bash
python $S/edu_login.py --site <site>             # visible browser, a person can finish; saves the session
python $S/edu_login.py --site <site> --headless  # exit 0: recordings need no person; 3: they do
```
