"""Parse a chapter script: DO steps (optionally tagged with one device) and their narration.

    > DO 2.1: Click Save.                       shared by the desktop and the mobile video
    > DO 2.2 [mobile]: Tap the round + button.  only in the mobile video, with its narration

Narration is every line that is not a heading, not a `>` line and not blank. It belongs to the
DO step above it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DEVICES = ('desktop', 'mobile')
DO_RE = re.compile(r'^>\s*DO (\d+)\.(\d+)(?:\s*\[(desktop|mobile)\])?:\s*(.*)$')


@dataclass
class Step:
    id: str
    device: str | None        # None = both devices
    instruction: str
    line_no: int
    narration: list[str] = field(default_factory=list)

    def on(self, device: str) -> bool:
        return self.device is None or self.device == device

    @property
    def key(self) -> tuple[int, int]:
        a, b = self.id.split('.')
        return int(a), int(b)


def parse(md_path: Path) -> list[Step]:
    steps: list[Step] = []
    for n, raw in enumerate(md_path.read_text(encoding='utf-8').splitlines(), 1):
        s = raw.strip()
        m = DO_RE.match(s)
        if m:
            steps.append(Step(f'{m[1]}.{m[2]}', m[3], m[4], n))
            continue
        if not s or s.startswith(('#', '>')):
            continue
        if not steps:
            raise SystemExit(f'{md_path.name} L{n}: narration before the first DO step: {s[:60]!r}')
        steps[-1].narration.append(s)
    return steps


def for_device(steps: list[Step], device: str) -> list[Step]:
    return [s for s in steps if s.on(device)]
