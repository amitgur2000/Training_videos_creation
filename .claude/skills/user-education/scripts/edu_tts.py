"""Narration clips with Gemini TTS (gemini-3.8-flash-tts): one WAV per narration line, cached.

Audio-first by design. Every line is synthesized BEFORE the video is recorded and its exact
length is measured from the WAV header. The recorder then holds each step on screen for as long
as its real audio lasts, so the audio fits by construction.

- Model gemini-3.8-flash-tts (EDU_TTS_MODEL overrides). Output: WAV, 24 kHz, mono, 16-bit.
- The language is detected from the text; the style instruction names it as well.
- Called through the Gemini Developer API with GEMINI_API_KEY (the Interactions API, which is
  what the TTS docs show). EDU_TTS_VERTEX=1 uses Vertex AI with gcloud application-default
  credentials instead (GOOGLE_CLOUD_PROJECT, location global).
- Cache: <lang>/.cache/tts/inputs.json + NNN_<step>.wav, git-ignored. A clip is reused while its
  model, voice, style, language and text are unchanged.

Reused clips are first moved aside by content (.hold/<sha>.wav) and only then placed at their new
positional names. The reference pipeline renamed them in place, one at a time, and a rename
overwrote a clip another line still needed: a whole video then said 14 sentences twice.
verify_clips() fails the run if that class of mistake ever returns.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from edu_chapter import parse
from edu_env import ffmpeg, secret
from edu_lang import Lang

MODEL = os.environ.get('EDU_TTS_MODEL', 'gemini-3.8-flash-tts')
EXT = '.wav'


def style_for(lang: Lang) -> str:
    return (f'Calm, warm and clear narrator of a software tutorial. Native {lang.name} speaker. '
            'Moderate, even pace. Read the text exactly as written, adding and skipping nothing.')


@dataclass
class Line:
    n: int                    # 1-based order in the chapter
    step: str                 # the DO id it follows
    device: str | None        # None = spoken in both videos
    text: str
    file: str = ''
    duration: float = 0.0

    def sha(self, lang: Lang) -> str:
        key = f'{MODEL}|{lang.voice}|{style_for(lang)}|{lang.name}|{self.text}'
        return hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]


def narration_lines(chapter_md: Path) -> list[Line]:
    lines: list[Line] = []
    for s in parse(chapter_md):
        for text in s.narration:
            lines.append(Line(len(lines) + 1, s.id, s.device, text))
    return lines


def for_device(lines: list[Line], device: str) -> list[Line]:
    return [ln for ln in lines if ln.device in (None, device)]


def wav_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / float(w.getframerate())


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        from google.genai import types
        # A request with no timeout once hung a run for 20 minutes; every call now gives up after
        # two minutes and is retried by its caller.
        http = types.HttpOptions(timeout=120_000)
        if os.environ.get('EDU_TTS_VERTEX') == '1':
            _client = genai.Client(vertexai=True, project=secret('GOOGLE_CLOUD_PROJECT'), location='global',
                                   http_options=http)
        else:
            _client = genai.Client(api_key=secret('GEMINI_API_KEY'), http_options=http)
    return _client


def _audio_bytes(resp) -> bytes:
    for step in reversed(getattr(resp, 'steps', None) or []):
        for part in getattr(step, 'content', None) or []:
            if getattr(part, 'type', '') == 'audio' and getattr(part, 'data', None):
                d = part.data
                return base64.b64decode(d) if isinstance(d, str) else bytes(d)
    raise RuntimeError(f'no audio in the TTS response (status {getattr(resp, "status", "?")})')


def gemini_tts(text: str, lang: Lang, attempts: int = 5) -> bytes:
    """One clip as WAV bytes. Retries rate limits and server errors with backoff."""
    import warnings
    warnings.filterwarnings('ignore', message='.*Interactions usage is experimental.*')
    delay = 4.0
    for i in range(attempts):
        try:
            resp = _get_client().interactions.create(
                model=MODEL,
                input=[{'type': 'user_input', 'content': [{
                    'type': 'text', 'text': text,
                    'annotations': [{'type': 'speech_metadata', 'style': style_for(lang)}],
                }]}],
                response_format={'type': 'audio'},
                generation_config={'speech_config': [{'voice': lang.voice}]},
            )
            data = _audio_bytes(resp)
            if not data.startswith(b'RIFF'):
                raise RuntimeError('TTS returned audio without a WAV header')
            return data
        except Exception as e:  # noqa: BLE001 - transient errors retry, the rest stop the run
            msg = str(e)
            transient = re.search(r'\b(429|500|502|503|504)\b|RESOURCE_EXHAUSTED|UNAVAILABLE|time(d ?)?out',
                                  msg, re.IGNORECASE)
            if i + 1 == attempts or not transient:
                raise SystemExit(f'Gemini TTS failed: {msg[:300]}')
            time.sleep(delay)
            delay *= 2
    raise AssertionError('unreachable')


def synthesize(chapter_md: Path, cache_dir: Path, lang: Lang, tts=gemini_tts) -> list[Line]:
    """Every narration line of the chapter (both devices) into cache_dir/NNN_<step>.wav, plus
    cache_dir/inputs.json (exact text, model, voice, style, each clip's duration and audio hash).
    `tts(text, lang) -> wav bytes` is injectable for tests."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    hold_dir = cache_dir / '.hold'
    manifest = cache_dir / 'inputs.json'

    # 1. Move every clip the manifest vouches for into the hold, keyed by content. A clip whose bytes
    #    no longer match the hash recorded when it was made is not trusted and is re-synthesized.
    held: set[str] = set()
    if manifest.exists():
        hold_dir.mkdir(exist_ok=True)
        for e in json.loads(manifest.read_text(encoding='utf-8'))['lines']:
            src = cache_dir / e['file']
            if e['sha'] in held or not src.exists():
                continue
            if e.get('audio_md5') and _md5(src) != e['audio_md5']:
                continue
            src.replace(hold_dir / f"{e['sha']}{EXT}")
            held.add(e['sha'])
    for stale in cache_dir.glob(f'*{EXT}'):
        stale.unlink()

    # 2. Place each line's clip at its positional name: from the hold, or freshly synthesized.
    lines = narration_lines(chapter_md)
    md5s: dict[str, str] = {}
    fresh: list[Line] = []
    for ln in lines:
        ln.file = f'{ln.n:03d}_{ln.step}{EXT}'
        dest = cache_dir / ln.file
        sha = ln.sha(lang)
        if sha in held:
            shutil.copyfile(hold_dir / f'{sha}{EXT}', dest)
        else:
            dest.write_bytes(tts(ln.text, lang))
            fresh.append(ln)
            print(f'  tts {ln.file}: {ln.text[:60]}')
        ln.duration = round(wav_seconds(dest.read_bytes()), 3)
        md5s[ln.file] = _md5(dest)
    shutil.rmtree(hold_dir, ignore_errors=True)

    verify_clips(lines, md5s, lang, cache_dir, check_silence=tts is gemini_tts)
    manifest.write_text(json.dumps({
        'model': MODEL, 'voice': lang.voice, 'style': style_for(lang), 'language': lang.name,
        'format': 'wav 24 kHz mono s16le',
        'lines': [{'n': ln.n, 'step': ln.step, 'device': ln.device, 'file': ln.file, 'sha': ln.sha(lang),
                   'audio_md5': md5s[ln.file], 'duration': ln.duration, 'text': ln.text} for ln in lines],
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    total = sum(ln.duration for ln in lines)
    print(f'TTS: {len(lines)} lines ({len(fresh)} new), {total:.1f} s of speech, every clip verified')
    return lines


def _peak_db(path: Path) -> float:
    out = subprocess.run([ffmpeg(), '-v', 'info', '-i', str(path), '-af', 'volumedetect', '-f', 'null', '-'],
                         capture_output=True, text=True, check=False).stderr
    m = re.search(r'max_volume:\s*(-?[\d.]+|-inf) dB', out)
    return float(m.group(1)) if m and m.group(1) != '-inf' else -999.0


def verify_clips(lines: list[Line], md5s: dict[str, str], lang: Lang, cache_dir: Path | None = None,
                 check_silence: bool = True) -> None:
    """Fail unless every clip plausibly belongs to its own line:
    - two lines with DIFFERENT text never share identical audio (the doubled-sentence bug);
    - each clip's length fits its text length (a wrong, truncated or runaway clip does not);
    - no clip is silent."""
    by_audio: dict[str, list[Line]] = {}
    for ln in lines:
        by_audio.setdefault(md5s[ln.file], []).append(ln)
    shared = [g for g in by_audio.values() if len({ln.text for ln in g}) > 1]
    lo, hi = lang.sec_per_char
    odd = [(ln.n, ln.step, round(ln.duration / len(ln.text), 3)) for ln in lines
           if not lo <= ln.duration / len(ln.text) <= hi]
    silent = []
    if check_silence and cache_dir is not None:
        silent = [(ln.n, ln.step) for ln in lines if _peak_db(cache_dir / ln.file) < -35]
    problems = []
    if shared:
        problems.append('different lines share one audio clip (a sentence would be spoken twice): '
                        + '; '.join(', '.join(f'line {ln.n} ({ln.step})' for ln in g) for g in shared))
    if odd:
        problems.append(f'clip length does not fit the text (line, step, s/char; expected {lo}-{hi}): {odd}')
    if silent:
        problems.append(f'silent clips (line, step): {silent}')
    if problems:
        raise SystemExit('TTS clips failed verification: ' + ' | '.join(problems)
                         + '. Delete the .cache/tts folder to re-synthesize from scratch.')


def step_hold(lines: list[Line], line_gap: float, tail: float) -> dict[str, float]:
    """Seconds each step must stay on screen after its cue so its narration fits."""
    hold: dict[str, float] = {}
    for step in dict.fromkeys(ln.step for ln in lines):
        mine = [ln for ln in lines if ln.step == step]
        hold[step] = sum(ln.duration for ln in mine) + line_gap * (len(mine) - 1) + tail
    return hold
