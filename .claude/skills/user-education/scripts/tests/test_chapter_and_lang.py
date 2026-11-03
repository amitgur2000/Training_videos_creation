import pytest
from edu_chapter import for_device, parse
from edu_lang import LANGS, resolve


def test_parse_device_tags(tmp_path):
    p = tmp_path / 'c.md'
    p.write_text('# t\n> DO 1.1: Open.\nשורה אחת.\n> DO 1.2 [mobile]: Tap menu.\nשורה שתיים.\n'
                 '> DO 1.3 [desktop]: Click.\n', encoding='utf-8')
    steps = parse(p)
    assert [(s.id, s.device) for s in steps] == [('1.1', None), ('1.2', 'mobile'), ('1.3', 'desktop')]
    assert [s.id for s in for_device(steps, 'mobile')] == ['1.1', '1.2']
    assert [s.id for s in for_device(steps, 'desktop')] == ['1.1', '1.3']
    assert steps[1].narration == ['שורה שתיים.']


def test_resolve_languages():
    assert resolve(None) is LANGS['he']
    assert resolve('Hebrew').rtl and resolve('he').ui_locale == 'he'
    assert resolve('ru').ui_locale == 'en'
    assert resolve('Japanese').name == 'Japanese'
    with pytest.raises(SystemExit):
        resolve('Klingon')
