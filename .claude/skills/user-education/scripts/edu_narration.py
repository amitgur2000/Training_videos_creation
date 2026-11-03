"""The synced narration track, the subtitles and the final mux, for one device's video.

- Each clip starts at its step's cue (the moment the step's result is on screen); the rest of the
  step's lines follow with LINE_GAP between them.
- Narration loudness -16 LUFS, a normal level for web video.
- Soft subtitles (a mov_text track the viewer can switch) plus a .srt, in the script's exact words:
  at most 2 rows of 42 characters on desktop, 32 on the narrower mobile picture. Right-to-left
  languages get a right-to-left mark at both ends of each row, so punctuation and embedded Latin
  words (ACT, EMDR) land on the correct side in every player.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from edu_env import ffmpeg
from edu_lang import Lang
from edu_tts import Line

LINE_GAP = 0.4            # silence between two narration lines of the same step
TAIL = 0.6                # silence after a step's narration before the next action starts
LOUDNESS = -16            # LUFS
MAX_CHARS = {'desktop': 42, 'mobile': 32}
RLM = '\u200f'


def timeline(lines: list[Line], cues: dict[str, float]) -> list[tuple[Line, float]]:
    """Start time of every line: a step's first line at the step's cue, the rest one after another."""
    placed, cursor_step, t = [], None, 0.0
    for ln in lines:
        if ln.step != cursor_step:
            cursor_step, t = ln.step, cues[ln.step]
        placed.append((ln, round(t, 3)))
        t += ln.duration + LINE_GAP
    return placed


def _filter_script_option() -> str:
    """ffmpeg 7 added `-/filter_complex <file>`; ffmpeg 9 removed `-filter_complex_script`."""
    out = subprocess.run([ffmpeg(), '-version'], capture_output=True, text=True, check=False).stdout
    m = re.match(r'ffmpeg version n?(\d+)', out)
    return '-/filter_complex' if m and int(m.group(1)) >= 7 else '-filter_complex_script'


def build_audio(placed: list[tuple[Line, float]], audio_dir: Path, video_s: float, dest: Path) -> None:
    """One narration track as long as the video, every clip at its start time, loudness-normalized."""
    args = [ffmpeg(), '-v', 'error', '-y']
    for ln, _ in placed:
        args += ['-i', str(audio_dir / ln.file)]
    parts = [f'[{i}:a]aresample=48000,adelay={int(t * 1000)}:all=1[a{i}]' for i, (_, t) in enumerate(placed)]
    mix = ''.join(f'[a{i}]' for i in range(len(placed)))
    filt = ';'.join(parts) + (f';{mix}amix=inputs={len(placed)}:normalize=0:dropout_transition=0,'
                              f'apad,atrim=0:{video_s:.3f},loudnorm=I={LOUDNESS}:TP=-1.5:LRA=11[out]')
    script = dest.with_suffix('.filter.txt')
    script.write_text(filt, encoding='utf-8')
    subprocess.run(args + [_filter_script_option(), str(script), '-map', '[out]', '-ar', '48000',
                           '-c:a', 'aac', '-b:a', '128k', str(dest)], check=True)
    script.unlink()


def _wrap(text: str, max_chars: int) -> list[str]:
    rows, cur = [], ''
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > max_chars:
            rows.append(cur)
            cur = w
        else:
            cur = f'{cur} {w}'.strip()
    if cur:
        rows.append(cur)
    return rows


def _ts(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def _two_rows(text: str, max_chars: int) -> list[str]:
    """One caption's rows: a single row if it fits, otherwise the most even two-row split. Falls
    back to greedy wrapping (3+ rows) when no split fits, so the caller uses more captions."""
    if len(text) <= max_chars:
        return [text]
    words, best = text.split(), None
    for i in range(1, len(words)):
        a, b = ' '.join(words[:i]), ' '.join(words[i:])
        if len(a) <= max_chars and len(b) <= max_chars:
            score = max(len(a), len(b))
            if best is None or score < best[0]:
                best = (score, [a, b])
    return best[1] if best else _wrap(text, max_chars)


def split_captions(text: str, max_chars: int) -> list[list[str]]:
    """Split one narration line into as few captions as fit (each at most 2 rows), with the words
    spread evenly and breaks preferred just after punctuation."""
    words = text.split()
    k = 1
    while True:
        target = len(text) / k
        groups, cur = [], []
        for i, w in enumerate(words):
            cur.append(w)
            size = len(' '.join(cur))
            left = len(words) - i - 1
            if len(groups) < k - 1 and left:
                ends_clause = w[-1] in ',.;:?!،؟'
                if size >= target or (ends_clause and size >= 0.7 * target):
                    groups.append(cur)
                    cur = []
        if cur:
            groups.append(cur)
        wrapped = [_two_rows(' '.join(g), max_chars) for g in groups]
        if all(len(r) <= 2 for r in wrapped) or k >= len(words):
            return wrapped
        k += 1


def build_srt(placed: list[tuple[Line, float]], dest: Path, lang: Lang, device: str) -> None:
    """Captions in the script's exact wording. A line's clip time is shared between its captions in
    proportion to their length."""
    out, k = [], 1
    for ln, start in placed:
        chunks = split_captions(ln.text, MAX_CHARS[device])
        total = sum(len(' '.join(c)) for c in chunks)
        t = start
        for c in chunks:
            d = ln.duration * len(' '.join(c)) / total
            rows = [f'{RLM}{r}{RLM}' for r in c] if lang.rtl else c
            out.append(f'{k}\n{_ts(t)} --> {_ts(t + d)}\n' + '\n'.join(rows) + '\n')
            k += 1
            t += d
    dest.write_text('\n'.join(out), encoding='utf-8', newline='\n')


def mux(silent_mp4: Path, audio: Path, srt: Path, dest: Path, lang: Lang) -> None:
    """The silent video, the narration and the soft subtitles in one mp4. The video is copied as is."""
    subprocess.run([
        ffmpeg(), '-v', 'error', '-y', '-i', str(silent_mp4), '-i', str(audio), '-i', str(srt),
        '-map', '0:v', '-map', '1:a', '-map', '2:s', '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'mov_text',
        '-metadata:s:a:0', f'language={lang.iso639_2}', '-metadata:s:s:0', f'language={lang.iso639_2}',
        '-movflags', '+faststart', str(dest),
    ], check=True)
