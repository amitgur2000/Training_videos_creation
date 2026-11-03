"""End-to-end production of one chapter in one language, both devices. Called by each chapter's
<NN>_<slug>.record.py:

    <playwright venv python> docs/user_education/<NN>_<slug>/<NN>_<slug>.record.py --lang he [--device both]

    0. Check:     the chapter script passes edu_check_chapter
    1. TTS:       every narration line voiced and measured (.cache/tts/, git-ignored), then the ASR gate
    per device (desktop, then mobile):
    2. Record:    the web app filmed headless, each step held for its real audio (.cache/<device>/silent.mp4)
    3. Narrate:   each clip placed at its step's cue, -16 LUFS (.cache/<device>/narration.m4a)
    4. Subtitles: the script's exact words (<device>/<slug>.<lang>.<device>.srt)
    5. Mux:       picture + voice + soft subtitles (<device>/<slug>.<lang>.<device>.mp4, Git LFS)
    6. Review:    Gemini compares each step's screenshot with its narration (a report)

Committed: the script, the record.py, and per device the mp4, srt, timed.md and steps.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from edu_check_chapter import check
from edu_lang import resolve
from edu_narration import LINE_GAP, TAIL, build_audio, build_srt, mux, timeline
from edu_recorder import Recorder, probe_duration
from edu_review import asr_check, frame_review
from edu_tts import for_device, step_hold, synthesize


def produce(
    record_py: str | Path,
    setup: Callable[[Recorder], object],
    record: Callable[[Recorder, object], None],
    cleanup: Callable[[Recorder, object], None],
    argv: list[str] | None = None,
) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--lang', default='he', help='Narration language: a code (he, en, ...) or a Gemini language name.')
    ap.add_argument('--device', default='both', choices=('both', 'desktop', 'mobile'))
    ap.add_argument('--env', default='staging')
    ap.add_argument('--audio-only', action='store_true',
                    help='Rebuild narration, subtitles and the mp4 from the cached silent video and steps.json. '
                         'Only valid when the narration text has not changed.')
    ap.add_argument('--no-review', action='store_true', help='Skip the Gemini frame review.')
    ap.add_argument('--rehearse', action='store_true',
                    help='Film only, with holds estimated from word counts: no TTS, no audio, no mux. For '
                         'debugging record.py; review .work/<device>/contact_*.png afterwards.')
    args = ap.parse_args(argv)

    lang = resolve(args.lang)
    chapter_dir = Path(record_py).resolve().parent
    slug = chapter_dir.name
    lang_dir = chapter_dir / lang.code
    chapter_md = lang_dir / f'{slug}.md'
    if not chapter_md.exists():
        raise SystemExit(f'No {lang.name} script: {chapter_md}. Write it first (mode new).')
    errs, _ = check(chapter_md, lang)
    if errs:
        raise SystemExit('The chapter fails edu_check_chapter.py, so nothing was voiced or recorded:\n  '
                         + '\n  '.join(errs))

    devices = ('desktop', 'mobile') if args.device == 'both' else (args.device,)
    if args.rehearse:
        for device in devices:
            print(f'== Rehearsal {device} (estimated pacing, no audio)')
            with Recorder(chapter_md, lang, device, env=args.env, hold=None) as r:
                ctx = setup(r)
                try:
                    record(r, ctx)
                finally:
                    cleanup(r, ctx)
        return 0

    print(f'== 1 TTS ({slug}, {lang.name}, voice {lang.voice})')
    tts_dir = lang_dir / '.cache' / 'tts'
    lines = synthesize(chapter_md, tts_dir, lang)
    asr_check(lines, tts_dir, lang)

    results = []
    for device in devices:
        dl = for_device(lines, device)
        hold = step_hold(dl, LINE_GAP, TAIL)
        out = lang_dir / device
        cache = lang_dir / '.cache' / device
        silent = cache / 'silent.mp4'
        if args.audio_only:
            log = json.loads((out / 'steps.json').read_text(encoding='utf-8'))
            changed = [e['id'] for e in log if abs(e['narration_s'] - hold.get(e['id'], 0.0)) > 0.02]
            if changed or not silent.exists():
                raise SystemExit(f'--audio-only is not valid for {device}: '
                                 + (f'the narration of steps {changed} changed' if changed else 'no cached silent video')
                                 + '. Re-record.')
        else:
            print(f'== 2 Recording {device}')
            with Recorder(chapter_md, lang, device, env=args.env, hold=hold) as r:
                ctx = setup(r)
                try:
                    record(r, ctx)
                finally:
                    cleanup(r, ctx)
            log = r.log
            if not args.no_review:
                frame_review(log, dl, r.shots_dir, r.work, lang, device)

        cues = {e['id']: e['cue'] for e in log}
        ends = {e['id']: e['end'] for e in log}
        placed = timeline(dl, cues)
        overruns = [(ln.n, ln.step, round(t + ln.duration - ends[ln.step], 2))
                    for ln, t in placed if t + ln.duration > ends[ln.step] + 0.05]
        if overruns:
            raise SystemExit(f'{device}: narration runs past its step (line, step, seconds over): {overruns}. '
                             'Re-record.')
        video_s = probe_duration(silent)
        print(f'== 3 Narration track {device}')
        narration = cache / 'narration.m4a'
        build_audio(placed, tts_dir, video_s, narration)
        print(f'== 4 Subtitles {device}')
        base = f'{slug}.{lang.code}.{device}'
        srt = out / f'{base}.srt'
        build_srt(placed, srt, lang, device)
        print(f'== 5 Mux {device}')
        final = out / f'{base}.mp4'
        mux(silent, narration, srt, final, lang)
        speech = sum(ln.duration for ln in dl)
        results.append(f'OK {final}\n   video {video_s:.1f}s, speech {speech:.1f}s over {len(dl)} lines, '
                       f'{len(log)} steps, silence {video_s - speech:.1f}s, {final.stat().st_size / 1e6:.1f} MB')
    print('\n'.join(results))
    return 0


if __name__ == '__main__':
    sys.exit("Run a chapter's <NN>_<slug>.record.py, which calls produce().")
