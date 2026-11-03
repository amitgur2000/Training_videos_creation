"""The site profile: training/<site>/site.yaml plus narrator.yaml, environments, secrets and tools.

Everything product-specific lives in the site folder, never in the skill:

    training/<site>/site.yaml        written by people (see site-profile.md for every key)
    training/<site>/narrator.yaml    written by edu_voices.py save: voice and persona per language
    training/<site>/.env             optional, git-ignored: credentials and API keys

The training root is $TRAINING_ROOT, else <git top level of the current directory>/training.

Secrets come from the process environment first, then from .env in the site folder, then .env at
the repo root. They are parsed here and never printed.

An environment marked `production: true` is refused unless site.yaml sets
`allow_production_recording: true` AND the run passes --allow-production: a recording types into
the site and the videos are published.
"""

from __future__ import annotations

import copy
import glob
import os
import platform
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import yaml

from edu_lang import RTL_LOCALES, Lang, resolve

SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL_DIR / 'templates'
DEFAULT_VOICE = 'Kore'
DEFAULT_PERSONA = 'Calm, warm and clear narrator of a software tutorial, like a friendly colleague.'

DEFAULTS: dict = {
    'product': {'name': '', 'spoken_name': '', 'audience': '', 'vocabulary': {}},
    'default_lang': 'en',
    'environments': {},
    'default_env': None,
    'allow_production_recording': False,
    'devices': ['desktop', 'mobile'],
    'device_profiles': {},
    'start_page': '/',
    'timezone': 'UTC',
    'test_id_attribute': 'data-testid',
    'source': {'repo': None, 'ref': 'origin/main', 'i18n': {'pattern': None}},
    'ui_language': {'locales': [], 'fallback': None, 'set_by': 'none', 'key': '',
                    'assert_html_lang': False},
    'wait_for_hidden': ['[aria-busy="true"]', '.MuiSkeleton-root', '.skeleton', '.spinner',
                        '[role="progressbar"]'],
    'dismiss_off_camera': [],
    'narration': {'forbidden_words': []},
    'login': {'required': False},
    'session_dir': None,
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def repo_root(start: Path | None = None) -> Path:
    proc = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=str(start or Path.cwd()),
                          capture_output=True, text=True, check=False)
    return Path(proc.stdout.strip()) if proc.returncode == 0 else Path.cwd()


def training_root() -> Path:
    return Path(os.environ['TRAINING_ROOT']) if os.environ.get('TRAINING_ROOT') else repo_root() / 'training'


def read_env_files(files: list[Path]) -> dict[str, str]:
    """KEY=VALUE lines (optionally `export KEY=...`, optionally quoted); the first file wins."""
    out: dict[str, str] = {}
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
            m = re.match(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
            if not m:
                continue
            v = m.group(2).strip()
            if v[:1] in ('"', "'") and v[-1:] == v[:1]:
                v = v[1:-1]
            out.setdefault(m.group(1), v)
    return out


class Site:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.name = self.root.name
        raw = yaml.safe_load((self.root / 'site.yaml').read_text(encoding='utf-8')) or {}
        self.cfg = _merge(DEFAULTS, raw)
        narrator = self.root / 'narrator.yaml'
        self.narrator: dict = (yaml.safe_load(narrator.read_text(encoding='utf-8')) or {}) if narrator.exists() else {}
        self._secrets: dict[str, str] | None = None

    def get(self, dotted: str, default=None):
        node = self.cfg
        for part in dotted.split('.'):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    # ---------- product and language ----------

    @property
    def product_name(self) -> str:
        return self.get('product.name') or self.name

    @property
    def spoken_name(self) -> str:
        return self.get('product.spoken_name') or self.product_name

    def ui_locale_for(self, code: str) -> str:
        ui = self.cfg['ui_language']
        locales = ui.get('locales') or []
        if not locales or code in locales:
            return code
        return ui.get('fallback') or locales[0]

    def voice_for(self, code: str) -> tuple[str, str]:
        """(voice, persona) for a narration language: narrator.yaml <lang>, then its default."""
        mine = self.narrator.get(code) or {}
        default = self.narrator.get('default') or {}
        voice = mine.get('voice') or default.get('voice') or DEFAULT_VOICE
        persona = mine.get('persona') or default.get('persona') or DEFAULT_PERSONA
        return voice, persona

    def has_voice(self, code: str) -> bool:
        return bool((self.narrator.get(code) or {}).get('voice') or (self.narrator.get('default') or {}).get('voice'))

    def lang(self, value: str | None = None) -> Lang:
        base = resolve(value or self.cfg.get('default_lang') or 'en')
        voice, persona = self.voice_for(base.code)
        return replace(base, voice=voice, persona=persona, ui=self.ui_locale_for(base.code),
                       timezone=self.cfg.get('timezone') or base.timezone)

    def ui_rtl(self, lang: Lang) -> bool:
        return lang.ui_locale.split('-')[0] in RTL_LOCALES

    # ---------- environments ----------

    @property
    def default_env(self) -> str:
        envs = self.cfg['environments']
        if self.cfg.get('default_env'):
            return self.cfg['default_env']
        safe = [k for k, v in envs.items() if not (v or {}).get('production')]
        if not safe:
            raise SystemExit(f'{self.root / "site.yaml"}: no non-production environment to record against.')
        return safe[0]

    def env(self, name: str | None, allow_production: bool = False) -> dict:
        name = name or self.default_env
        envs = self.cfg['environments']
        if name not in envs:
            raise SystemExit(f'Unknown environment {name!r} for site {self.name}. Allowed: {", ".join(envs)}.')
        e = dict(envs[name] or {})
        if e.get('production') and not (allow_production and self.cfg.get('allow_production_recording')):
            raise SystemExit(f'{name!r} is marked production. Recording creates real data and publishes what is on '
                             'screen; use a staging or demo environment. Only the site owner can opt in, with '
                             'allow_production_recording: true in site.yaml AND --allow-production.')
        if not e.get('url'):
            raise SystemExit(f'Environment {name!r} has no url in site.yaml.')
        e['name'] = name
        return e

    def url(self, env: dict, path: str) -> str:
        return path if re.match(r'https?://', path) else env['url'].rstrip('/') + '/' + path.lstrip('/')

    def session_file(self, env: str) -> Path:
        base = self.cfg.get('session_dir') or str(Path.home() / '.training_videos' / self.name)
        return Path(os.path.expanduser(base)) / f'{env}.json'

    # ---------- secrets ----------

    def secret(self, name: str, required: bool = True) -> str:
        """Value of `name` from the environment or a .env file. Never print the result."""
        if os.environ.get(name):
            return os.environ[name]
        if self._secrets is None:
            self._secrets = read_env_files([self.root / '.env', repo_root(self.root) / '.env'])
        v = self._secrets.get(name, '')
        if required and not v:
            raise SystemExit(f'{name} is not set (process environment, {self.root / ".env"} or the repo .env).')
        return v


def find_site_dir(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / 'site.yaml').exists():
            return p
    return None


def load(site: str | Path | None = None, start: Path | None = None) -> Site:
    """A site by name (training/<name>), by folder, or found by walking up from `start`."""
    if site:
        p = Path(site)
        if (p / 'site.yaml').exists():
            return Site(p)
        p = training_root() / str(site)
        if (p / 'site.yaml').exists():
            return Site(p)
        raise SystemExit(f'No site.yaml for site {site!r} (looked in {p}). Run the skill with --mode init first.')
    found = find_site_dir((start or Path.cwd()).resolve())
    if not found:
        raise SystemExit('No site.yaml found above this folder. Pass --site <name>.')
    return Site(found)


_shared: dict[str, str] | None = None


def secret_anywhere(name: str, site: Site | None = None, required: bool = True) -> str:
    """For callers without a site at hand (the TTS client): the site's .env when given, else the repo .env."""
    if site is not None:
        return site.secret(name, required)
    global _shared
    if os.environ.get(name):
        return os.environ[name]
    if _shared is None:
        _shared = read_env_files([repo_root() / '.env'])
    v = _shared.get(name, '')
    if required and not v:
        raise SystemExit(f'{name} is not set (process environment or a .env file).')
    return v


# ---------- tools ----------

def _tool(name: str) -> str:
    override = os.environ.get(f'EDU_{name.upper()}')
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    patterns = [
        os.path.expandvars(rf'%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\*\bin\{name}.exe'),
        f'/opt/homebrew/bin/{name}', f'/usr/local/bin/{name}', f'/usr/bin/{name}',
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    raise SystemExit(f'{name} not found. Install ffmpeg or set EDU_{name.upper()}.')


def ffmpeg() -> str:
    return _tool('ffmpeg')


def ffprobe() -> str:
    return _tool('ffprobe')


def drawtext_font() -> str:
    """A bold TTF for ffmpeg drawtext, escaped for a filter graph. EDU_FONT overrides."""
    candidates = [os.environ.get('EDU_FONT', '')]
    if platform.system() == 'Windows':
        candidates += [os.path.expandvars(rf'%WINDIR%\Fonts\{f}') for f in ('arialbd.ttf', 'arial.ttf')]
    candidates += ['/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/Library/Fonts/Arial Bold.ttf',
                   '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                   '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf']
    for c in candidates:
        if c and Path(c).exists():
            return c.replace('\\', '/').replace(':', '\\:')
    raise SystemExit('No TTF font found for contact-sheet labels. Set EDU_FONT to a .ttf file.')


def launch_browser(pw, headless: bool, args: list[str] | None = None):
    """Installed Google Chrome, else Playwright's Chromium. EDU_BROWSER_CHANNEL=chromium forces Chromium."""
    channel = os.environ.get('EDU_BROWSER_CHANNEL', 'chrome')
    try:
        return pw.chromium.launch(headless=headless, channel=channel, args=args or [])
    except Exception as e:
        if channel == 'chromium':
            raise
        print(f'[edu] Google Chrome not available ({str(e).splitlines()[0]}); using Playwright Chromium.')
        return pw.chromium.launch(headless=headless, channel='chromium', args=args or [])
