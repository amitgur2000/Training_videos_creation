from pathlib import Path

from edu_check_chapter import _norm, check
from edu_lang import LANGS

HE = LANGS['he']


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / 'he' / '01_x.md'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding='utf-8', newline='\n')
    return p


HEAD = '# כותרת\n\n> AUDIENCE: מטפלים\n\n## Introduction\n\n> DO 0.1: Show the dashboard.\n\n'


def test_distinct_hebrew_sentences_are_not_duplicates(tmp_path):
    p = _write(tmp_path, HEAD + 'הפרק הזה מיועד למטפלים.\nכאן מוסיפים מטופל חדש למערכת.\n')
    errs, stats = check(p, HE)
    assert errs == []
    assert stats['lines'] == 2


def test_norm_keeps_hebrew_letters():
    assert _norm('שלום, עולם!') == 'שלום עולם'


def test_repeated_hebrew_sentence_fails(tmp_path):
    p = _write(tmp_path, HEAD + 'לוחצים על שמירה.\n\n> DO 0.2: Click Save.\n\nלוחצים על שמירה.\n')
    errs, _ = check(p, HE)
    assert any('same sentence' in e for e in errs)


def test_device_alternatives_may_repeat(tmp_path):
    body = HEAD + ('> DO 0.2 [desktop]: Click the button.\n\nלוחצים על הכפתור כדי לפתוח את הטופס החדש.\n\n'
                   '> DO 0.3 [mobile]: Tap the button.\n\nלוחצים על הכפתור כדי לפתוח את הטופס החדש.\n')
    errs, _ = check(_write(tmp_path, body), HE)
    assert errs == []


def test_sum_up_inside_a_label_is_not_an_opener(tmp_path):
    body = HEAD + 'בוחרים גישה טיפולית לסיכום הפגישה.\n\n> DO 0.2: Wait.\n\nלסיכום, זה הכול.\n'
    errs, _ = check(_write(tmp_path, body), HE)
    assert errs == []


def test_sum_up_once_per_video(tmp_path):
    body = HEAD + 'לסיכום, הוספנו מטופל.\n\n> DO 0.2: Wait.\n\nלסיכום, זה הכול.\n'
    errs, _ = check(_write(tmp_path, body), HE)
    assert any('summary opener' in e for e in errs)


def test_bidi_niqqud_quotes_and_bad_tags(tmp_path):
    body = HEAD + 'שָׁלוֹם לכולם.\nלוחצים על "שמירה".\n\u200fטקסט עם סימן כיוון.\n\n> DO 0.2 [tablet]: Tap.\n'
    errs, _ = check(_write(tmp_path, body), HE)
    text = ' | '.join(errs)
    assert 'niqqud' in text and 'quote' in text and 'bidi' in text and 'malformed DO' in text


def test_crlf_and_order(tmp_path):
    p = tmp_path / 'he' / '01_x.md'
    p.parent.mkdir(parents=True)
    p.write_bytes(HEAD.replace('\n', '\r\n').encode() + b'> DO 0.0: x\r\n')
    errs, _ = check(p, HE)
    assert any('CRLF' in e for e in errs) and any('not in order' in e for e in errs)
