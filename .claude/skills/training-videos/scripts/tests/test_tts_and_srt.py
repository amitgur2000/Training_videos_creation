import io
import json
import wave
from pathlib import Path

import pytest
from edu_lang import LANGS
from edu_narration import RLM, build_srt, split_captions, timeline
from edu_tts import Line, step_hold, synthesize, verify_clips

HE = LANGS['he']


def fake_wav(text: str, lang=HE) -> bytes:
    rate, secs = 24000, len(text) * 0.09
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        # Distinct content per text, so identical audio means identical text.
        seed = sum(map(ord, text)) % 251 + 1
        w.writeframes(bytes((i * seed) % 256 for i in range(int(rate * secs) * 2)))
    return buf.getvalue()


def _chapter(tmp_path: Path, lines: list[str]) -> Path:
    body = '# t\n\n> DO 1.1: Open.\n\n' + '\n'.join(lines) + '\n'
    p = tmp_path / 'c.md'
    p.write_text(body, encoding='utf-8', newline='\n')
    return p


def test_cache_reuses_clips_after_insert(tmp_path):
    calls = []

    def tts(text, lang):
        calls.append(text)
        return fake_wav(text)

    cache = tmp_path / 'tts'
    a, b, c = 'שורה ראשונה של הקריינות.', 'שורה שנייה של הקריינות.', 'שורה חדשה באמצע.'
    synthesize(_chapter(tmp_path, [a, b]), cache, HE, tts=tts)
    assert calls == [a, b]
    lines = synthesize(_chapter(tmp_path, [a, c, b]), cache, HE, tts=tts)
    assert calls == [a, b, c]           # only the new line was voiced
    manifest = json.loads((cache / 'inputs.json').read_text(encoding='utf-8'))
    assert [e['text'] for e in manifest['lines']] == [a, c, b]
    # Each positional clip holds its own line's audio.
    for ln in lines:
        assert (cache / ln.file).read_bytes() == fake_wav(ln.text)


def test_verify_rejects_shared_audio_and_bad_length():
    lines = [Line(1, '1.1', None, 'שורה אחת ארוכה מספיק.', 'a.wav', 1.8),
             Line(2, '1.2', None, 'שורה אחרת לגמרי כאן.', 'b.wav', 1.8)]
    with pytest.raises(SystemExit, match='share one audio'):
        verify_clips(lines, {'a.wav': 'x', 'b.wav': 'x'}, HE, check_silence=False)
    lines[1].duration = 30.0
    with pytest.raises(SystemExit, match='does not fit'):
        verify_clips(lines, {'a.wav': 'x', 'b.wav': 'y'}, HE, check_silence=False)


def test_hold_and_timeline():
    lines = [Line(1, '1.1', None, 'a', 'a', 2.0), Line(2, '1.1', None, 'b', 'b', 1.0),
             Line(3, '1.2', None, 'c', 'c', 3.0)]
    assert step_hold(lines, 0.4, 0.6) == {'1.1': pytest.approx(4.0), '1.2': pytest.approx(3.6)}
    placed = timeline(lines, {'1.1': 10.0, '1.2': 20.0})
    assert [t for _, t in placed] == [10.0, 12.4, 20.0]


def test_captions_fit_and_rtl_marks(tmp_path):
    text = 'בשדה גישה טיפולית לסיכום הפגישה בוחרים את השיטה שלפיה ייכתבו הסיכומים של כל פגישה.'
    for chunk in split_captions(text, 32):
        assert len(chunk) <= 2 and all(len(r) <= 32 for r in chunk)
    srt = tmp_path / 'x.srt'
    build_srt([(Line(1, '1.1', None, text, 'a', 7.0), 1.0)], srt, HE, 'mobile')
    rows = [r for r in srt.read_text(encoding='utf-8').splitlines() if r and not r[0].isdigit()]
    assert rows and all(r.startswith(RLM) and r.endswith(RLM) for r in rows)
