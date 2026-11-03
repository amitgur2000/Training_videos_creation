"""Explore the live site: what each page shows, per device and UI language, for writing chapters.

    python edu_explore.py --site <s> [--env <e>] [--lang he] [--device site|both|desktop|mobile]
                          [--capture-labels] /path/one /path/two ...

For each path and device, logged in, after the page is ready and overlays are dismissed:
    <path>.aria.yaml     the accessibility tree (roles, names, states): the page as a screen reader
                         hears it, which is close to what the narration must name
    <path>.controls.md   every interactive control: role, visible label, test id / id / name, and
                         the best Playwright locator for record.py
    <path>.png           a full-page screenshot
into training/<s>/.explore/<ui locale>/<device>/ (git-ignored).

--capture-labels also adds every control's visible label to training/<s>/labels/<ui locale>.json under
`explore.<path>.<key>`, for r.t() on sites without source access. Review that file before committing.

This is the source of truth when the site's code is not available, and a cross-check when it is:
labels on screen win over labels in a stale checkout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edu_browser import Session
from edu_site import load

CONTROLS_JS = r"""
(tid) => {
  const sel = 'a[href], button, input, select, textarea, summary, [role=button], [role=link], [role=tab],'
    + '[role=menuitem], [role=option], [role=combobox], [role=checkbox], [role=radio], [role=switch],'
    + '[role=textbox], [role=searchbox], [role=slider], [contenteditable=true], [' + tid + ']';
  const seen = new Set(), out = [];
  for (const el of document.querySelectorAll(sel)) {
    if (seen.has(el)) continue; seen.add(el);
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    const visible = r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || ({a: 'link', button: 'button', select: 'combobox', textarea: 'textbox',
      summary: 'button'})[tag] || (tag === 'input' ? ({checkbox: 'checkbox', radio: 'radio', submit: 'button',
      button: 'button', range: 'slider', search: 'searchbox'})[el.type] || 'textbox' : tag);
    let label = el.getAttribute('aria-label') || '';
    if (!label && el.labels && el.labels.length) label = el.labels[0].innerText;
    if (!label && el.getAttribute('aria-labelledby')) {
      const l = document.getElementById(el.getAttribute('aria-labelledby')); if (l) label = l.innerText;
    }
    if (!label) label = (el.innerText || el.value || el.getAttribute('placeholder') || el.getAttribute('title') || '');
    out.push({role, label: label.replace(/\s+/g, ' ').trim().slice(0, 90), testid: el.getAttribute(tid) || '',
      id: el.id || '', name: el.getAttribute('name') || '', type: el.getAttribute('type') || '',
      placeholder: el.getAttribute('placeholder') || '', href: tag === 'a' ? el.getAttribute('href') : '',
      visible, disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
      y: Math.round(r.top + window.scrollY)});
  }
  return out.sort((a, b) => a.y - b.y);
}
"""


def _path_slug(path: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '_', path.strip('/')).strip('_') or 'root'


def _locator(c: dict) -> str:
    """The most stable locator first: test id (site.yaml test_id_attribute), a hand-written id, a role
    with its label, then the form name."""
    if c['testid']:
        return f"page.get_by_test_id({c['testid']!r})"
    if c['id'] and not re.match(r'^(:r|mui-|radix-|headlessui-|react-)', c['id']):
        return f"page.locator('#{c['id']}')"
    if c['label']:
        return f"page.get_by_role({c['role']!r}, name=r.t('<key>'))  # {c['label']!r}"
    if c['name']:
        return f"page.locator('[name=\"{c['name']}\"]')"
    return '(no stable locator: ask for a test id)'


def _controls_md(controls: list[dict], url: str) -> str:
    rows = ['| # | Role | Label | Test id / id / name | Locator | Notes |', '|---|---|---|---|---|---|']
    for i, c in enumerate(controls, 1):
        ident = ' / '.join(x for x in (c['testid'], f"#{c['id']}" if c['id'] else '', c['name']) if x)
        notes = ', '.join(x for x in ('hidden' if not c['visible'] else '', 'disabled' if c['disabled'] else '',
                                      c['href'] or '') if x)
        label = c['label'].replace('|', '\\|')
        rows.append(f"| {i} | {c['role']} | {label} | {ident} | `{_locator(c)}` | {notes} |")
    return f'# Controls at {url}\n\n' + '\n'.join(rows) + '\n'


def _capture_labels(site, locale: str, path: str, controls: list[dict]) -> int:
    f = site.root / 'labels' / f'{locale}.json'
    data = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
    bucket = data.setdefault('explore', {}).setdefault(_path_slug(path), {})
    added = 0
    for c in controls:
        if not c['label'] or not c['visible']:
            continue
        key = _path_slug(c['testid'] or c['id'] or c['name'] or c['label'])[:40].lower()
        if key and key not in bucket:
            bucket[key] = c['label']
            added += 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    return added


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--site', required=True)
    ap.add_argument('--env', default=None)
    ap.add_argument('--lang', default=None)
    ap.add_argument('--device', default='site', choices=('site', 'both', 'desktop', 'mobile'))
    ap.add_argument('--capture-labels', action='store_true')
    ap.add_argument('--allow-production', action='store_true')
    ap.add_argument('paths', nargs='*')
    args = ap.parse_args(argv)
    site = load(args.site)
    lang = site.lang(args.lang)
    paths = args.paths or [site.get('start_page') or '/']
    mangled = [p for p in paths if re.match(r'^[A-Za-z]:[\\/]', p)]
    if mangled:
        raise SystemExit(f'{mangled} look like Windows paths: Git Bash rewrites arguments starting with /. '
                         'Set MSYS_NO_PATHCONV=1, or drop the leading slash (dashboard.html).')
    devices = {'site': tuple(site.get('devices') or ('desktop', 'mobile')), 'both': ('desktop', 'mobile')}.get(
        args.device, (args.device,))
    tid = site.get('test_id_attribute') or 'data-testid'
    for device in devices:
        out = site.root / '.explore' / lang.ui_locale / device
        out.mkdir(parents=True, exist_ok=True)
        with Session(site, lang, device, args.env, args.allow_production) as s:
            page = s.setup_page
            for path in paths:
                s.open(page, path)
                s.dismiss_overlays(page)
                base = out / _path_slug(path)
                try:
                    aria = page.locator('body').aria_snapshot()
                except Exception as e:  # noqa: BLE001 - older Playwright: skip the tree, keep the rest
                    aria = f'# aria snapshot unavailable: {e}'
                base.with_suffix('.aria.yaml').write_text(aria + '\n', encoding='utf-8', newline='\n')
                controls = page.evaluate(CONTROLS_JS, tid)
                base.with_suffix('.controls.md').write_text(_controls_md(controls, page.url), encoding='utf-8',
                                                            newline='\n')
                page.screenshot(path=str(base.with_suffix('.png')), full_page=True)
                extra = ''
                if args.capture_labels:
                    extra = f', {_capture_labels(site, lang.ui_locale, path, controls)} new labels'
                print(f'[{device}] {path} -> {base}.* ({len(controls)} controls{extra})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
