"""A logged-in browser for one site, device and UI language. Shared by the recorder and the explorer.

- Devices: desktop and a Pixel 7 phone, overridable per site (site.yaml device_profiles). Chrome is
  launched with --force-device-scale-factor, because the DevTools screencast delivers frames in CSS
  pixels unless the browser itself runs at the device scale (a Pixel 7 profile gave soft 412x839
  frames without it, sharp 1080x2199 with it).
- UI language: forced before the first paint, by the site's mechanism (site.yaml ui_language:
  localStorage key, cookie, query parameter, or none), and optionally asserted from <html lang dir>.
- Ready: after navigation, waits for the network to idle and for the site's loading indicators
  (site.yaml wait_for_hidden) to disappear, so a screen is described only once it has content.
- Overlays: site.yaml dismiss_off_camera selectors (cookie banners, promos) are clicked if visible.
"""

from __future__ import annotations

import json
import sys
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from edu_i18n import Labels
from edu_lang import Lang
from edu_login import config as login_config
from edu_login import on_login_page, save_session, sign_in
from edu_site import Site, launch_browser


@dataclass(frozen=True)
class Device:
    name: str
    viewport: dict
    scale: float
    video: tuple[int, int]
    mobile: bool
    user_agent: str | None = None
    tile: tuple[int, int] = (640, 360)   # contact-sheet tile
    cols: int = 3

    @property
    def portrait(self) -> bool:
        return self.video[1] > self.video[0]


# desktop: 1536x864 CSS px at 1.25 -> 1920x1080.
# mobile: a Pixel 7, 412x732 CSS px at 2.625 -> 1080x1920 portrait (9:16 exactly), touch, mobile UA:
# the same emulation as Chrome's F12 device toolbar.
DEVICES = {
    'desktop': Device('desktop', {'width': 1536, 'height': 864}, 1.25, (1920, 1080), False),
    'mobile': Device(
        'mobile', {'width': 412, 'height': 732}, 2.625, (1080, 1920), True,
        'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/140.0.0.0 Mobile Safari/537.36',
        tile=(270, 480), cols=6),
}


def device_for(site: Site, name: str) -> Device:
    if name not in DEVICES:
        raise SystemExit(f'Unknown device {name!r}; use desktop or mobile.')
    over = (site.get('device_profiles') or {}).get(name) or {}
    dev = DEVICES[name]
    if over:
        kw = {k: (tuple(v) if k in ('video', 'tile') else v) for k, v in over.items()}
        dev = replace(dev, **kw)
    return dev


ANALYTICS = ('google-analytics', 'googletagmanager', 'doubleclick', 'segment.io', 'segment.com', 'mixpanel',
             'hotjar', 'sentry.io', 'clarity.ms', 'amplitude', 'intercom', 'fullstory', 'datadoghq')


class Session:
    """Use as a context manager. `setup_page` is logged in and off camera; `new_context()` makes more."""

    def __init__(self, site: Site, lang: Lang, device: str, env: str | None = None,
                 allow_production: bool = False):
        self.site, self.lang = site, lang
        self.env = site.env(env, allow_production)
        self.dev = device_for(site, device)
        self.device = device
        self.ui = site.get('ui_language') or {}
        self.t = Labels(lang.ui_locale, site)
        self.lc = login_config(site)
        self.setup_page: Page | None = None

    def __enter__(self) -> Session:  # noqa: PYI034
        self._pw = sync_playwright().start()
        if self.site.get('test_id_attribute'):
            self._pw.selectors.set_test_id_attribute(self.site.get('test_id_attribute'))
        self.browser = launch_browser(self._pw, headless=True, args=[f'--force-device-scale-factor={self.dev.scale}'])
        self.state = self.site.session_file(self.env['name'])
        self._setup_ctx = self.new_context(use_state=self.state.exists())
        self.setup_page = self._setup_ctx.new_page()
        sign_in(self.setup_page, self.site, self.env)
        if self.lc['required']:
            save_session(self._setup_ctx, self.site, self.env['name'])
        self.open(self.setup_page, self.site.get('start_page') or '/')
        return self

    def __exit__(self, exc_type, exc, tb):
        with suppress(Exception):
            self.browser.close()
        self._pw.stop()
        return False

    # ---------- contexts ----------

    def _locale_script(self) -> str | None:
        how, key, code = self.ui.get('set_by') or 'none', self.ui.get('key') or '', self.lang.ui_locale
        if how == 'localStorage' and key:
            return f'try {{ localStorage.setItem({json.dumps(key)}, {json.dumps(code)}); }} catch (e) {{}}'
        if how == 'cookie' and key:
            cookie = json.dumps(f'{key}={code}; path=/; max-age=31536000')
            return f'try {{ document.cookie = {cookie}; }} catch (e) {{}}'
        return None

    def new_context(self, use_state: bool = True, init_scripts: tuple[str, ...] = ()):
        kw = {'viewport': self.dev.viewport, 'device_scale_factor': self.dev.scale,
              'locale': self.lang.browser_locale, 'timezone_id': self.lang.timezone,
              'storage_state': str(self.state) if use_state and self.state.exists() else None}
        if self.dev.mobile:
            kw.update(is_mobile=True, has_touch=True, user_agent=self.dev.user_agent)
        ctx = self.browser.new_context(**kw)
        script = self._locale_script()
        if script:
            ctx.add_init_script(script)
        for s in init_scripts:
            ctx.add_init_script(s)
        return ctx

    # ---------- pages ----------

    def url(self, path: str) -> str:
        full = self.site.url(self.env, path)
        if (self.ui.get('set_by') == 'query') and self.ui.get('key'):
            u = urlparse(full)
            q = dict(parse_qsl(u.query))
            q[self.ui['key']] = self.lang.ui_locale
            full = urlunparse(u._replace(query=urlencode(q)))
        return full

    def open(self, page: Page, path: str) -> None:
        page.goto(self.url(path))
        self.wait_ready(page)
        if self.lc['required'] and on_login_page(page, self.lc):
            sign_in(page, self.site, self.env)
            page.goto(self.url(path))
            self.wait_ready(page)
        self.assert_locale(page)

    def wait_ready(self, page: Page, timeout_ms: int = 10_000) -> None:
        """Network idle, then every loading indicator gone (hidden or detached)."""
        with suppress(Exception):
            page.wait_for_load_state('networkidle', timeout=timeout_ms)
        sels = [s for s in (self.site.get('wait_for_hidden') or []) if s]
        if sels:
            with suppress(Exception):
                page.wait_for_function(
                    '(sels) => !sels.some(s => { try { return [...document.querySelectorAll(s)]'
                    '.some(e => e.getClientRects().length > 0); } catch (e) { return false; } })',
                    arg=sels, timeout=timeout_ms)

    def dismiss_overlays(self, page: Page) -> None:
        for sel in self.site.get('dismiss_off_camera') or []:
            with suppress(Exception):
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=3000)
                    page.wait_for_timeout(400)

    def assert_locale(self, page: Page) -> None:
        if not self.ui.get('assert_html_lang'):
            return
        got = page.evaluate('[document.documentElement.lang, document.documentElement.dir]')
        want_lang = self.lang.ui_locale.split('-')[0]
        want_dir = 'rtl' if self.site.ui_rtl(self.lang) else 'ltr'
        if (got[0] or '').split('-')[0] != want_lang or (got[1] or 'ltr') != want_dir:
            raise SystemExit(f'The site UI is {got}, expected [{want_lang!r}, {want_dir!r}]. Check ui_language '
                             'in site.yaml (set_by and key).')


def is_analytics(url: str) -> bool:
    return any(a in url for a in ANALYTICS)
