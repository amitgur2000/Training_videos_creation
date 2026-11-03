"""UI labels, so one record.py works in every UI language without literal UI text.

    t = Labels('he', site)
    t('settings.title')                      -> from the site's label source, no namespace
    t('common:dashboard.addItem', item='x')  -> namespaced; {item} or {{item}} placeholders filled

Sources, first hit wins:
1. The site's own translation files, when site.yaml has `source.repo` and `source.i18n.pattern`
   (for example "src/locales/{locale}/{ns}.json", or "public/i18n/{locale}.json" without {ns}).
   Read from `source.ref` (default origin/main; the local checkout is often stale), falling back
   to the working tree.
2. training/<site>/labels/<locale>.json (or labels/<locale>/<ns>.json), kept by the skill for sites
   without source access: the exact on-screen strings, captured with edu_explore.py.

Placeholders must be passed explicitly: a guess would make the locator miss.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from functools import cache
from pathlib import Path


@cache
def _git_show(repo: str, ref: str, rel: str) -> bytes | None:
    proc = subprocess.run(['git', '-C', repo, 'show', f'{ref}:{rel}'], capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else None


class Labels:
    def __init__(self, locale: str, site=None):
        self.locale = locale
        self.site = site
        self._loaded: dict[str | None, dict | None] = {}

    def _candidates(self, ns: str | None) -> list[tuple[str, Callable[[], bytes | None]]]:
        out = []
        site = self.site
        if site is None:
            return out
        repo, pattern = site.get('source.repo'), site.get('source.i18n.pattern')
        if repo and pattern and (ns or '{ns}' not in pattern):
            repo_path = Path(repo) if Path(repo).is_absolute() else (site.root / repo).resolve()
            rel = pattern.format(locale=self.locale, ns=ns or '')
            ref = site.get('source.ref') or 'origin/main'
            out.append((f'{repo_path.name}@{ref}:{rel}',
                        lambda r=str(repo_path), rel=rel, ref=ref: _git_show(r, ref, rel)))
            wt = repo_path / rel
            out.append((str(wt), lambda wt=wt: wt.read_bytes() if wt.exists() else None))
        local = site.root / 'labels' / (f'{self.locale}/{ns}.json' if ns else f'{self.locale}.json')
        out.append((str(local), lambda p=local: p.read_bytes() if p.exists() else None))
        return out

    def _table(self, ns: str | None) -> dict:
        if ns not in self._loaded:
            self._loaded[ns] = None
            for _, read in self._candidates(ns):
                data = read()
                if data is not None:
                    self._loaded[ns] = json.loads(data.decode('utf-8'))
                    break
        if self._loaded[ns] is None:
            tried = ', '.join(name for name, _ in self._candidates(ns)) or 'none (no site)'
            raise SystemExit(f'No label file for locale {self.locale!r}{f", namespace {ns!r}" if ns else ""}. '
                             f'Tried: {tried}. Configure source.i18n in site.yaml, or capture the strings into '
                             'labels/<locale>.json, or use test ids and roles instead of labels.')
        return self._loaded[ns]

    def __call__(self, key: str, **vars: str) -> str:
        ns, sep, path = key.partition(':')
        if not sep:
            ns, path = None, key
        node = self._table(ns)
        if path in node and isinstance(node[path], str):   # flat files with dotted keys
            node = node[path]
        else:
            for part in path.split('.'):
                if not isinstance(node, dict) or part not in node:
                    raise SystemExit(f'Label {key!r} not found for locale {self.locale!r}')
                node = node[part]
        if not isinstance(node, str):
            raise SystemExit(f'Label {key!r} is not a string')
        text = node
        for k, v in vars.items():
            text = text.replace('{{' + k + '}}', v).replace('{' + k + '}', v)
        left = re.findall(r'\{\{?[^}]+\}?\}', text)
        if left:
            raise SystemExit(f'Label {key!r} still has placeholders {left}; pass them as keywords')
        return text
