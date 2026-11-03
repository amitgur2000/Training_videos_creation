"""UI labels from the web app's own translation files, so one record.py works in every language.

    t = Labels('he')
    t('clients:intake.autoEndSession')                 -> 'סיום פגישה אוטומטי'
    t('common:dashboard.addClient', client='מטופל/ת')  -> 'הוספת מטופל/ת'

Reads web_app_frontend/src/locales/<locale>/<namespace>.json from origin/main (the source of
truth; the local checkout is routinely stale), falling back to the working tree. Placeholders such
as {client} must be passed explicitly: the app fills them per account role (roleWording.ts), and a
guess would make the locator miss.
"""

from __future__ import annotations

import json
import re
import subprocess
from functools import cache

from edu_env import WEB_APP_REPO

REF = 'origin/main'


@cache
def _namespace(locale: str, ns: str) -> dict:
    rel = f'src/locales/{locale}/{ns}.json'
    proc = subprocess.run(['git', '-C', str(WEB_APP_REPO), 'show', f'{REF}:{rel}'],
                          capture_output=True, check=False)
    if proc.returncode == 0:
        return json.loads(proc.stdout.decode('utf-8'))
    path = WEB_APP_REPO / rel
    if not path.exists():
        raise SystemExit(f'Locale file not found: {rel} (in {REF} or the working tree of {WEB_APP_REPO})')
    return json.loads(path.read_text(encoding='utf-8'))


class Labels:
    def __init__(self, locale: str):
        self.locale = locale

    def __call__(self, key: str, **vars: str) -> str:
        ns, _, path = key.partition(':')
        if not path:
            raise SystemExit(f'Label key {key!r} needs a namespace, for example clients:intake.title')
        node = _namespace(self.locale, ns)
        for part in path.split('.'):
            if not isinstance(node, dict) or part not in node:
                raise SystemExit(f'Label {key!r} not found in {self.locale}/{ns}.json ({REF})')
            node = node[part]
        if not isinstance(node, str):
            raise SystemExit(f'Label {key!r} is not a string')
        text = node
        for k, v in vars.items():
            text = text.replace('{' + k + '}', v)
        left = re.findall(r'\{[^}]+\}', text)
        if left:
            raise SystemExit(f'Label {key!r} still has placeholders {left}; pass them as keywords')
        return text
