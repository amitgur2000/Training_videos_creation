import pytest
from edu_check_chapter import check
from edu_i18n import Labels
from edu_site import Site
from edu_tts import style_for

SITE_YAML = """
product: {name: Acme, spoken_name: Acme}
default_lang: he
timezone: Europe/Paris
environments:
  staging: {url: https://staging.acme.example}
  prod: {url: https://acme.example, production: true}
ui_language: {locales: [he, en], fallback: en}
narration: {forbidden_words: [ticket]}
source:
  i18n: {pattern: null}
"""


@pytest.fixture
def site(tmp_path):
    root = tmp_path / 'acme'
    root.mkdir()
    (root / 'site.yaml').write_text(SITE_YAML, encoding='utf-8')
    (root / 'narrator.yaml').write_text('default: {voice: Kore}\nhe: {voice: Aoede, persona: Warm colleague}\n',
                                        encoding='utf-8')
    (root / '.env').write_text('export SITE_PASS="s3cret"\n# COMMENTED=1\n', encoding='utf-8')
    return Site(root)


def test_lang_takes_voice_persona_ui_and_timezone(site):
    he = site.lang(None)
    assert (he.code, he.voice, he.persona, he.ui_locale, he.timezone) == ('he', 'Aoede', 'Warm colleague', 'he',
                                                                         'Europe/Paris')
    ru = site.lang('ru')
    assert (ru.voice, ru.ui_locale) == ('Kore', 'en')          # default voice, fallback UI
    assert 'Warm colleague.' in style_for(he) and 'Hebrew' in style_for(he)


def test_environments_refuse_production(site):
    assert site.env(None)['name'] == 'staging'
    with pytest.raises(SystemExit, match='production'):
        site.env('prod')
    with pytest.raises(SystemExit, match='production'):
        site.env('prod', allow_production=True)              # the site has not opted in
    with pytest.raises(SystemExit, match='Unknown'):
        site.env('nope')


def test_secret_from_env_file(site, monkeypatch):
    monkeypatch.delenv('SITE_PASS', raising=False)
    assert site.secret('SITE_PASS') == 's3cret'
    assert site.secret('COMMENTED', required=False) == ''
    with pytest.raises(SystemExit, match='not set'):
        site.secret('MISSING_KEY_XYZ')


def test_labels_flat_nested_and_placeholders(site):
    (site.root / 'labels').mkdir()
    (site.root / 'labels' / 'en.json').write_text(
        '{"orders": {"add": "Add {{item}}"}, "flat.key": "Flat"}', encoding='utf-8')
    t = Labels('en', site)
    assert t('orders.add', item='order') == 'Add order'
    assert t('flat.key') == 'Flat'
    with pytest.raises(SystemExit, match='placeholders'):
        t('orders.add')
    with pytest.raises(SystemExit, match='No label file'):
        Labels('fr', site)('orders.add')


def test_checker_uses_site_forbidden_words(site):
    p = site.root / '01_x' / 'he' / '01_x.md'
    p.parent.mkdir(parents=True)
    p.write_text('# t\n\n> DO 0.1: Show.\n\nפותחים ticket חדש מהמסך הזה.\n', encoding='utf-8', newline='\n')
    errs, _ = check(p, site=site)
    assert any('forbidden word' in e for e in errs)
