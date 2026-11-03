"""Gemini review gates: does each clip say its line, and does each step's picture match its words.

1. asr_check (a gate, before recording): every narration clip is transcribed by a Gemini model and
   compared to its text. TTS models can skip or add words, mispronounce a product name, or invent
   speech; a clip that does not say its line stops the run. Results are cached by the clip's audio
   hash in .cache/tts/asr.json, so only new clips cost a call.
2. frame_review (a report, after recording): each step's cue screenshot and its narration go to
   Gemini, which says whether the screen shows what the narration describes. Mismatches are
   printed and written to .work/<device>/frame_review.json, for the person reviewing the video.

The sync itself does not depend on Gemini: audio is measured first and the recorder holds each
step for exactly its audio. Gemini only checks the result.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

from edu_check_chapter import _norm
from edu_lang import Lang
from edu_tts import Line, _get_client

MODEL = os.environ.get('EDU_REVIEW_MODEL', 'gemini-3.8-flash')
ASR_MIN_RATIO = 0.82


def _generate(parts: list, json_out: bool = False, attempts: int = 4) -> str:
    from google.genai import types
    cfg = types.GenerateContentConfig(
        temperature=0, response_mime_type='application/json' if json_out else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    for i in range(attempts):
        try:
            resp = _get_client().models.generate_content(model=MODEL, contents=parts, config=cfg)
            return (resp.text or '').strip()
        except Exception as e:  # network errors and timeouts retry, then stop the run
            if i + 1 == attempts:
                raise SystemExit(f'Gemini review call failed: {str(e)[:300]}') from e
            time.sleep(4 * 2 ** i)
    raise AssertionError('unreachable')


def asr_check(lines: list[Line], cache_dir: Path, lang: Lang, product_name: str = '') -> None:
    from google.genai import types
    store = cache_dir / 'asr.json'
    known = json.loads(store.read_text(encoding='utf-8')) if store.exists() else {}
    bad = []
    for ln in lines:
        data = (cache_dir / ln.file).read_bytes()
        key = hashlib.md5(data).hexdigest()
        if key not in known:
            prompt = f'Transcribe this {lang.name} audio verbatim. Output only the transcript.'
            if product_name:
                prompt += f' Write the product name {product_name} exactly like that.'
            heard = _generate([types.Part.from_bytes(data=data, mime_type='audio/wav'), prompt])
            known[key] = heard
            # Saved after every clip, so an interrupted run keeps what it already paid for.
            store.write_text(json.dumps(known, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
            print(f'  asr {ln.file}', flush=True)
        heard = known[key]
        ratio = SequenceMatcher(None, _norm(ln.text), _norm(heard)).ratio()
        if ratio < ASR_MIN_RATIO:
            bad.append((ln.n, ln.step, round(ratio, 2), heard[:80]))
    if bad:
        detail = '\n  '.join(f'line {n} ({s}) similarity {r}: heard {h!r}' for n, s, r, h in bad)
        raise SystemExit('Some clips do not say their line (listen to them; re-word the line or delete its '
                         f'clip to re-voice it):\n  {detail}')
    print(f'ASR check: all {len(lines)} clips say their line (similarity >= {ASR_MIN_RATIO})')


def frame_review(log: list[dict], lines: list[Line], shots_dir: Path, work: Path, lang: Lang,
                 device: str) -> list[dict]:
    from google.genai import types
    by_step: dict[str, list[str]] = {}
    for ln in lines:
        by_step.setdefault(ln.step, []).append(ln.text)
    report = []
    for e in log:
        said = ' '.join(by_step.get(e['id'], []))
        if not said:
            continue
        png = (shots_dir / f'{e["id"]}.png').read_bytes()
        prompt = (f'This is a screenshot of a web site ({device} layout, UI in {lang.ui_locale}) taken while a '
                  f'tutorial narrator says, in {lang.name}: "{said}"\n'
                  'Does the screen show what the narration describes at this moment (the page, dialog, '
                  'field or result it talks about)? Narration may also explain context that has no '
                  'picture; that is fine. Answer JSON: {"match": true|false, "reason": "<one short sentence>"}')
        raw = _generate([types.Part.from_bytes(data=png, mime_type='image/png'), prompt], json_out=True)
        try:
            verdict = json.loads(re.sub(r'^```(json)?|```$', '', raw).strip())
        except json.JSONDecodeError:
            verdict = {'match': None, 'reason': raw[:200]}
        report.append({'id': e['id'], **verdict})
    (work / 'frame_review.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n',
                                            encoding='utf-8', newline='\n')
    misses = [r for r in report if r.get('match') is not True]
    print(f'Frame review ({device}): {len(report) - len(misses)}/{len(report)} steps match their narration')
    for r in misses:
        print(f'  CHECK step {r["id"]}: {r.get("reason")}')
    return report
