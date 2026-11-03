"""Produce one chapter: load its record.py and the site, then voice, film, narrate, subtitle and mux.

    python .claude/skills/training-videos/scripts/edu_run.py training/<site>/<NN>_<slug> --lang he
        [--device site|both|desktop|mobile] [--env <name>] [--rehearse] [--audio-only] [--no-review]

The chapter folder holds <NN>_<slug>.record.py, which defines three functions and nothing else:

    def setup(r):        off camera, on r.setup_page; returns a context object for record()
    def record(r, ctx):  page = r.start(); then one `with r.step('n.m'):` per DO line
    def cleanup(r, ctx): off camera, after the last step

The site is the nearest site.yaml above the chapter folder. Exit code 3 means the login needs a
person (see edu_login.py).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edu_produce import produce
from edu_site import load


def load_record_module(chapter_dir: Path):
    path = chapter_dir / f'{chapter_dir.name}.record.py'
    if not path.exists():
        raise SystemExit(f'No recording script: {path}. Write it from templates/record.py.')
    spec = importlib.util.spec_from_file_location(f'record_{chapter_dir.name}', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    missing = [f for f in ('setup', 'record', 'cleanup') if not callable(getattr(mod, f, None))]
    if missing:
        raise SystemExit(f'{path.name} must define {", ".join(missing)}.')
    return mod


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith('-'):
        print(__doc__)
        return 2
    target = Path(argv[0]).resolve()
    chapter_dir = target.parent if target.is_file() else target
    site = load(start=chapter_dir)
    mod = load_record_module(chapter_dir)
    return produce(site, chapter_dir, mod.setup, mod.record, mod.cleanup, [str(chapter_dir), *argv[1:]])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
