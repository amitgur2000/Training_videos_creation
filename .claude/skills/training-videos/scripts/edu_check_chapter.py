"""Check a chapter script against the style guide's mechanical rules, before anything is voiced.

    python .claude/skills/training-videos/scripts/edu_check_chapter.py training/<site>/<NN>_<slug>/<lang>/<NN>_<slug>.md

The language comes from the folder the script sits in (`he/`, `en/`, ...), and the site (for its
forbidden words) from the nearest site.yaml above it. Prints the narration
size and either FORMAT OK or one line per problem, and exits 1 on any problem. produce() runs it
first, so a chapter that fails is never sent to TTS.

The checks, all from style-guide.md:
- UTF-8, LF endings; no bidi control characters, no niqqud;
- narration lines: no symbols, quote marks, URLs, list markers, timing-cue look-alikes,
  recording-setup words or the site's narration.forbidden_words, and at most 45 words;
- DO ids unique and in order; a device tag is [desktop] or [mobile];
- NO REPEATED SENTENCE within one video: no narration sentence, or a near-copy, is spoken twice;
- the Summary's opener ("לסיכום", "To sum up", ...) is said once per video;
- English only: words the voice is known to misread (MISREAD).
"""

from __future__ import annotations

import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from edu_chapter import DEVICES, DO_RE
from edu_lang import LANGS, Lang, resolve

MAX_WORDS = 45
# Two sentences this similar (0 to 1, by characters) count as the same sentence said twice.
NEAR_COPY = 0.88
# Sentences shorter than this are too generic to compare ("Click Save.") except by exact match.
MIN_WORDS_NEAR = 6
SYMBOLS = re.compile(r'[*_`|\[\]()<>/&%@#~^={}\\"“”„«»״]')
BIDI = re.compile('[\u200e\u200f\u202a-\u202e\u2066-\u2069]')
NIQQUD = re.compile('[֑-ׇ]')
# Words that give away how the video was made. Sites add their own in narration.forbidden_words.
SETUP_WORDS = re.compile(r'\b(test|demo|dummy|fake|sample) (account|user|data|record|customer|client|patient|'
                         r'environment|tenant|company)\b|\bDO \d', re.IGNORECASE)
# English: words and phrases a TTS voice was heard to say wrongly. Re-word, there is no lexicon.
MISREAD = {
    'en': [
        (re.compile(r'\b(Dr|Mr|Mrs|Ms|St|Approx)\.', re.IGNORECASE),
         'abbreviation read as letters: write the word, for example Doctor'),
        (re.compile(r'\bread[- ]only\b', re.IGNORECASE), '"read only" can be said as "red only": re-word'),
        (re.compile(r'\bon record\b', re.IGNORECASE), '"record" noun or verb by stress: re-word'),
    ],
}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'(?<=[.?!؟])\s+', text) if s.strip()]


def _norm(s: str) -> str:
    """Lower-case letters, digits and spaces of any script. (An ASCII-only version turned every
    Hebrew sentence into an empty string, so all of them looked like the same sentence.)"""
    s = ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', re.sub(r'[^\w ]', '', s.lower())).strip()


def lang_of(path: Path, site=None) -> Lang:
    if site is not None:
        return site.lang(path.parent.name)
    return LANGS.get(path.parent.name) or resolve(path.parent.name)


def _site_of(path: Path):
    from edu_site import Site, find_site_dir
    root = find_site_dir(path.resolve().parent)
    return Site(root) if root else None


def check(path: Path, lang: Lang | None = None, site=None) -> tuple[list[str], dict]:
    raw = path.read_bytes()
    text = raw.decode('utf-8', 'replace')
    lang = lang or lang_of(path, site)
    forbidden = [w for w in ((site.get('narration.forbidden_words') if site else None) or []) if w]
    forbidden_re = (re.compile(r'(?<!\w)(' + '|'.join(re.escape(w) for w in forbidden) + r')(?!\w)', re.IGNORECASE)
                    if forbidden else None)
    errs: list[str] = []
    if b'\r' in raw:
        errs.append('CRLF line endings: convert to LF')
    if '�' in text:
        errs.append('not valid UTF-8')
    if BIDI.search(text):
        errs.append('bidi control characters: delete them (the subtitles add their own)')

    narr: list[tuple[int, str, str | None]] = []   # (line, text, device of its step)
    ids: list[tuple[int, int, int]] = []
    device: str | None = None
    for n, line in enumerate(text.split('\n'), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith('>'):
            m = DO_RE.match(s)
            if m:
                ids.append((int(m[1]), int(m[2]), n))
                device = m[3]
            elif re.match(r'>\s*DO\b', s):
                errs.append(f'L{n}: malformed DO line; use "> DO n.m: ..." or "> DO n.m [mobile]: ..."')
            continue
        narr.append((n, s, device))
        if not ids:
            errs.append(f'L{n}: narration before the first DO step')
        if SYMBOLS.search(s):
            errs.append(f'L{n}: symbol or quote mark in narration: {s[:60]}')
        if NIQQUD.search(s):
            errs.append(f'L{n}: niqqud in narration; write plain letters')
        if re.search(r'https?:|www\.|\b[\w-]+\.(com|net|org|io|ai|app|dev|co|il|uk|de|fr|info|biz)\b', s,
                     re.IGNORECASE):
            errs.append(f'L{n}: URL or domain in narration')
        if re.match(r'\d+:\d', s):
            errs.append(f'L{n}: narration starts like a timing cue')
        if SETUP_WORDS.search(s):
            errs.append(f'L{n}: recording-setup words in narration: {SETUP_WORDS.search(s).group(0)}')
        if forbidden_re and forbidden_re.search(s):
            errs.append(f'L{n}: forbidden word for this site (site.yaml narration.forbidden_words): '
                        f'{forbidden_re.search(s).group(0)}')
        if s.startswith('-') or re.match(r'\d+\.\s', s):
            errs.append(f'L{n}: list marker in narration')
        for pat, why in MISREAD.get(lang.code, []):
            if pat.search(s):
                errs.append(f'L{n}: the voice misreads this: {why}')
        if len(s.split()) > MAX_WORDS:
            errs.append(f'L{n}: narration line over {MAX_WORDS} words, split it')

    seen: set[tuple[int, int]] = set()
    for a, b, n in ids:
        if (a, b) in seen:
            errs.append(f'L{n}: duplicate DO id {a}.{b}')
        seen.add((a, b))
    if [(a, b) for a, b, _ in ids] != sorted((a, b) for a, b, _ in ids):
        errs.append('DO ids are not in order')

    # No sentence is said twice in one video. A [desktop] line and a [mobile] line may say the
    # same thing: each is heard in a different video.
    for dev in DEVICES:
        spoken = [(n, sen) for n, line, d in narr if d in (None, dev) for sen in _sentences(line)]
        for i, (n1, s1) in enumerate(spoken):
            for n2, s2 in spoken[i + 1:]:
                a, b = _norm(s1), _norm(s2)
                if a == b:
                    errs.append(f'L{n1} and L{n2}: the same sentence is said twice: {s1[:60]}')
                elif (min(len(a.split()), len(b.split())) >= MIN_WORDS_NEAR
                      and SequenceMatcher(None, a, b).ratio() >= NEAR_COPY):
                    errs.append(f'L{n1} and L{n2}: nearly the same sentence twice: {s1[:50]} / {s2[:50]}')
        if lang.sum_up:
            # Only as a line's opener: Hebrew labels can contain the word mid-sentence (סיכום, לסיכום הפגישה).
            pat = re.compile(r'^(?:' + '|'.join(re.escape(p) for p in lang.sum_up) + r')\b', re.IGNORECASE)
            hits = [n for n, s, d in narr if d in (None, dev) and pat.search(s)]
            if len(hits) > 1:
                errs.append(f'the summary opener is said {len(hits)} times in the {dev} video '
                            f'(lines {hits}); say it once')
    errs = list(dict.fromkeys(errs))

    words = sum(len(s.split()) for _, s, _ in narr)
    return errs, {'lines': len(narr), 'words': words, 'minutes': round(words / lang.wpm, 1),
                  'do_steps': len(ids), 'lang': lang.code}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    errs, stats = check(path, site=_site_of(path))
    print(f"lang={stats['lang']} narration lines={stats['lines']} words={stats['words']} "
          f"minutes~{stats['minutes']} DO steps={stats['do_steps']}")
    print('\n'.join(errs) if errs else 'FORMAT OK')
    return 1 if errs else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main(sys.argv))
