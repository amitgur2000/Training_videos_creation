"""Environments the user-education recorder may run against, tools, and local secrets.

Production is deliberately absent: a recording creates real patients in the demo
account, and the videos are committed. Never add a production entry.

Secrets (demo login, Gemini key, Gmail app password) come from the process
environment first, then from the git-ignored init_shell_local_debug_Eran_2.sh at
the repo root. They are parsed here and never printed.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SIBLINGS = REPO.parent
WEB_APP_REPO = SIBLINGS / 'web_app_frontend'

ENVS = {
    'staging': {
        'app_url': 'https://staging.myndz.ai',
    },
}

# Login state (tokens + the trusted-device key) lives outside the repo.
LOCAL_ROOT = Path(os.environ.get('USER_EDUCATION_HOME', 'C:/tmp/user_education'))

INIT_FILES = [REPO / 'init_shell_local_debug_Eran_2.sh']


def refuse_unknown(env: str) -> None:
    if env not in ENVS:
        raise SystemExit(f'Unknown environment {env!r}. Allowed: {", ".join(ENVS)}. '
                         'Production is never allowed.')


def auth_state(env: str) -> Path:
    return LOCAL_ROOT / '.auth' / f'{env}-demo.json'


_secrets: dict[str, str] | None = None


def _load_init() -> dict[str, str]:
    out: dict[str, str] = {}
    for f in INIT_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
            m = re.match(r'\s*(?:export\s+)+([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$', line)
            if not m:
                continue
            v = m.group(2).strip()
            if v[:1] in '"\'' and v[-1:] == v[:1]:
                v = v[1:-1]
            out.setdefault(m.group(1), v)
    return out


def secret(name: str, required: bool = True) -> str:
    """Value of `name` from the environment or the init file. Never print the result."""
    global _secrets
    if os.environ.get(name):
        return os.environ[name]
    if _secrets is None:
        _secrets = _load_init()
    v = _secrets.get(name, '')
    if required and not v:
        raise SystemExit(f'{name} is not set (environment or {INIT_FILES[0].name}).')
    return v


def _tool(name: str) -> str:
    override = os.environ.get(f'EDU_{name.upper()}')
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    # WinGet installs ffmpeg without putting it on every shell's PATH.
    pattern = os.path.expandvars(
        rf'%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\*\bin\{name}.exe')
    hits = sorted(glob.glob(pattern))
    if hits:
        return hits[-1]
    raise SystemExit(f'{name} not found. Install ffmpeg or set EDU_{name.upper()}.')


def ffmpeg() -> str:
    return _tool('ffmpeg')


def ffprobe() -> str:
    return _tool('ffprobe')
