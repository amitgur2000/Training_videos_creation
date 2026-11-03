"""Choose the narrator: sample Gemini voices and personas, design a custom voice, save the choice.

    # 1. Listen: the same text in several voices (and personas), plus a listening page
    python edu_voices.py sample --site <s> --lang he [--voices Kore,Aoede,Charon,Sulafat | --all | --tag warm]
                                [--persona "Calm, warm colleague"] [--persona "Upbeat coach"]
                                [--text "..." | --chapter training/<s>/<NN>_<slug>]

    # 2. Or design a voice from a description (Gemini voice design; a persistent voice_... id)
    python edu_voices.py design --site <s> --lang he --gender female \
                                --description "A warm, calm woman in her forties, clear and unhurried"

    # 3. Save the pick: training/<s>/narrator.yaml, per language (or as the default)
    python edu_voices.py save --site <s> --lang he --voice Aoede [--persona "..."]
    python edu_voices.py save --site <s> --voice voice_abc123 --default

    python edu_voices.py list --site <s>          # prebuilt voices, designed voices, current choice

Samples go to training/<s>/voices/<lang>/ (git-ignored) with index.html, one player per sample.
Every sample is the same text, so the voices compare fairly. The default text greets the viewer
with the product's spoken name, which also tests how the voice says it inside, for example,
Hebrew narration. A choice changes the TTS cache key, so the next production re-voices every line.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edu_chapter import parse
from edu_site import DEFAULT_PERSONA, Site, load
from edu_tts import MODEL, _get_client, gemini_tts, style_for, use_site, wav_seconds

# Gemini's prebuilt voices and their style, as the speech-generation docs list them (2026-11-03).
PREBUILT = {
    'Zephyr': 'Bright', 'Puck': 'Upbeat', 'Charon': 'Informative', 'Kore': 'Firm', 'Fenrir': 'Excitable',
    'Leda': 'Youthful', 'Orus': 'Firm', 'Aoede': 'Breezy', 'Callirrhoe': 'Easy-going', 'Autonoe': 'Bright',
    'Enceladus': 'Breathy', 'Iapetus': 'Clear', 'Umbriel': 'Easy-going', 'Algieba': 'Smooth',
    'Despina': 'Smooth', 'Erinome': 'Clear', 'Algenib': 'Gravelly', 'Rasalgethi': 'Informative',
    'Laomedeia': 'Upbeat', 'Achernar': 'Soft', 'Alnilam': 'Firm', 'Schedar': 'Even', 'Gacrux': 'Mature',
    'Pulcherrima': 'Forward', 'Achird': 'Friendly', 'Zubenelgenubi': 'Casual', 'Vindemiatrix': 'Gentle',
    'Sadachbia': 'Lively', 'Sadaltager': 'Knowledgeable', 'Sulafat': 'Warm',
}
# A balanced first shortlist for tutorial narration (the four a user compared for Hebrew, 2026-10-04).
SHORTLIST = ['Kore', 'Aoede', 'Charon', 'Sulafat']

SAMPLE_TEXT = {
    'he': 'שלום וברוכים הבאים ל{name}. בסרטון הקצר הזה נראה צעד אחר צעד איך מתחילים לעבוד, '
          'ובסוף תדעו בדיוק מה לעשות בכל מסך.',
    'en': 'Hello, and welcome to {name}. In this short video we will go step by step through getting started, '
          'and by the end you will know exactly what to do on every screen.',
    'ar': 'مرحبا بكم في {name}. في هذا الفيديو القصير سنتعرف خطوة بخطوة على كيفية البدء، '
          'وفي النهاية ستعرفون بالضبط ما يجب فعله في كل شاشة.',
    'ru': 'Здравствуйте и добро пожаловать в {name}. '
          'В этом коротком видео мы шаг за шагом разберём, как начать работу.',
    'fr': 'Bonjour et bienvenue dans {name}. Dans cette courte vidéo, nous verrons pas à pas comment bien démarrer.',
    'es': 'Hola y bienvenidos a {name}. En este breve video veremos paso a paso cómo empezar a trabajar.',
    'de': 'Hallo und willkommen bei {name}. In diesem kurzen Video zeigen wir Schritt für Schritt, wie Sie loslegen.',
}


def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:24] or 'p'


def _voices_dir(site: Site, code: str) -> Path:
    d = site.root / 'voices' / code
    d.mkdir(parents=True, exist_ok=True)
    return d


def _designed_file(site: Site) -> Path:
    return site.root / 'designed_voices.json'


def _designed(site: Site) -> list[dict]:
    f = _designed_file(site)
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else []


def _sample_text(site: Site, lang, args) -> str:
    if args.text:
        return args.text
    if args.chapter:
        md = Path(args.chapter) / lang.code / f'{Path(args.chapter).name}.md'
        lines = [t for s in parse(md) for t in s.narration][:2]
        if lines:
            return ' '.join(lines)
    template = SAMPLE_TEXT.get(lang.code) or SAMPLE_TEXT['en']
    return template.format(name=site.spoken_name)


def _write_index(folder: Path, entries: list[dict], text: str, lang_name: str) -> Path:
    rows = []
    for e in entries:
        rows.append(
            f'<tr><td><b>{html.escape(e["voice"])}</b><br><small>{html.escape(e.get("tag", ""))}</small></td>'
            f'<td>{html.escape(e.get("persona", ""))}</td><td>{e["seconds"]:.1f}s</td>'
            f'<td><audio controls preload="none" src="{html.escape(e["file"])}"></audio></td></tr>')
    page = f'''<!doctype html><meta charset="utf-8"><title>Narrator samples ({html.escape(lang_name)})</title>
<style>body{{font:15px system-ui,sans-serif;margin:24px;max-width:1000px}}
td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:start;vertical-align:middle}}blockquote{{background:#f5f5f5;padding:12px;border-radius:8px}}</style>
<h1>Narrator samples: {html.escape(lang_name)}</h1>
<p>Every sample reads the same text:</p><blockquote dir="auto">{html.escape(text)}</blockquote>
<table><tr><th>Voice</th><th>Persona</th><th>Length</th><th>Listen</th></tr>{''.join(rows)}</table>
<p>Pick one, then: <code>edu_voices.py save --site ... --lang ... --voice NAME [--persona "..."]</code></p>
'''
    f = folder / 'index.html'
    f.write_text(page, encoding='utf-8', newline='\n')
    return f


def cmd_sample(site: Site, args) -> int:
    lang = site.lang(args.lang)
    if args.all:
        voices = list(PREBUILT)
    elif args.tag:
        voices = [v for v, t in PREBUILT.items() if t.lower() == args.tag.lower()]
        if not voices:
            styles = ', '.join(sorted(set(PREBUILT.values())))
            raise SystemExit(f'No voice has the style {args.tag!r}. Styles: {styles}')
    elif args.voices:
        voices = [v.strip() for v in args.voices.split(',') if v.strip()]
    else:
        voices = SHORTLIST
    unknown = [v for v in voices if v not in PREBUILT and not v.startswith('voice_')]
    if unknown:
        raise SystemExit(f'Unknown voices {unknown}. Prebuilt: {", ".join(PREBUILT)}; or a designed voice_... id.')
    personas = args.persona or [lang.persona or DEFAULT_PERSONA]
    text = _sample_text(site, lang, args)
    folder = _voices_dir(site, lang.code)
    entries = []
    print(f'Sampling {len(voices)} voice(s) x {len(personas)} persona(s) in {lang.name} with {MODEL}.')
    for voice in voices:
        for k, persona in enumerate(personas):
            name = f'{voice}.wav' if len(personas) == 1 else f'{voice}__{k + 1}-{_slug(persona)}.wav'
            data = gemini_tts(text, lang, voice=voice, persona=persona)
            (folder / name).write_bytes(data)
            secs = wav_seconds(data)
            entries.append({'voice': voice, 'tag': PREBUILT.get(voice, 'designed'), 'persona': persona,
                            'file': name, 'seconds': secs, 'style': style_for(lang, persona)})
            print(f'  {name:40s} {secs:5.1f}s  {PREBUILT.get(voice, "designed")}')
    (folder / 'samples.json').write_text(json.dumps({'text': text, 'model': MODEL, 'samples': entries},
                                                    ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    index = _write_index(folder, entries, text, lang.name)
    print(f'Listen: {index}')
    return 0


def cmd_design(site: Site, args) -> int:
    lang = site.lang(args.lang)
    client = _get_client()
    name = args.name or f'{site.product_name} narrator ({lang.name})'
    voice = client.voices.create(store=True, voice={
        'model': MODEL, 'type': 'prompted', 'display_name': name, 'gender': args.gender,
        'language_code': args.language_code or lang.browser_locale,
        'prompted': {'input': args.description},
    })
    folder = _voices_dir(site, lang.code)
    preview = folder / f'{voice.id}.preview.wav'
    if getattr(voice, 'sample_audio', None) and getattr(voice.sample_audio, 'data', None):
        d = voice.sample_audio.data
        preview.write_bytes(base64.b64decode(d) if isinstance(d, str) else bytes(d))
    text = _sample_text(site, lang, args)
    sample = folder / f'{voice.id}.wav'
    sample.write_bytes(gemini_tts(text, lang, voice=voice.id))
    registry = _designed(site)
    registry.append({'id': voice.id, 'name': name, 'lang': lang.code, 'gender': args.gender,
                     'description': args.description, 'model': MODEL, 'created': date.today().isoformat()})
    _designed_file(site).write_text(json.dumps(registry, ensure_ascii=False, indent=1) + '\n', encoding='utf-8',
                                    newline='\n')
    print(f'Designed voice {voice.id} ({name}).\n  preview: {preview}\n  our sample text: {sample}\n'
          f'Keep it: edu_voices.py save --site {site.name} --lang {lang.code} --voice {voice.id}\n'
          'Designed voices live in the Gemini project of the API key, expire a year after their last use, '
          'and count toward a limit of 200 per project.')
    return 0


def cmd_save(site: Site, args) -> int:
    if args.voice not in PREBUILT and not args.voice.startswith('voice_'):
        raise SystemExit(f'Unknown voice {args.voice!r}. Prebuilt: {", ".join(PREBUILT)}; or a designed voice_... id.')
    key = 'default' if args.default else site.lang(args.lang).code
    data = dict(site.narrator)
    entry = dict(data.get(key) or {})
    entry['voice'] = args.voice
    if args.persona:
        entry['persona'] = args.persona
    entry['chosen'] = date.today().isoformat()
    data[key] = entry
    f = site.root / 'narrator.yaml'
    header = ('# The narrator per language, written by edu_voices.py save. "default" applies to languages\n'
              '# without their own entry. voice: a prebuilt Gemini voice or a designed voice_... id.\n'
              '# persona: the style instruction for the voice. Changing either re-voices every line.\n')
    f.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=True), encoding='utf-8', newline='\n')
    print(f'Saved {key}: voice {args.voice}' + (f', persona {args.persona!r}' if args.persona else '') + f' -> {f}')
    return 0


def cmd_list(site: Site, args) -> int:
    print('Prebuilt Gemini voices:')
    for v, t in PREBUILT.items():
        print(f'  {v:15s} {t}{"   (shortlist)" if v in SHORTLIST else ""}')
    designed = _designed(site)
    if designed:
        print('Designed voices for this site:')
        for d in designed:
            print(f'  {d["id"]}  {d["lang"]}  {d["gender"]}  {d["name"]}: {d["description"]}')
    print('Current narrator (narrator.yaml):')
    for k, v in (site.narrator or {'(none)': {}}).items():
        print(f'  {k}: {v}')
    return 0


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('sample', 'design', 'save', 'list'):
        p = sub.add_parser(name)
        p.add_argument('--site', required=True)
        p.add_argument('--lang', default=None)
        if name in ('sample', 'design'):
            p.add_argument('--text', default=None)
            p.add_argument('--chapter', default=None, help='Use the chapter\'s first narration lines as the text.')
    s = sub.choices['sample']
    s.add_argument('--voices', default=None, help='Comma-separated prebuilt names or designed voice_... ids.')
    s.add_argument('--all', action='store_true', help='All 30 prebuilt voices.')
    s.add_argument('--tag', default=None, help='Every prebuilt voice with this style, for example Warm or Firm.')
    s.add_argument('--persona', action='append', help='A narrator persona; repeat to compare several.')
    d = sub.choices['design']
    d.add_argument('--description', required=True, help='One or two sentences: who the voice is and how it sounds.')
    d.add_argument('--gender', required=True, choices=('female', 'male'))
    d.add_argument('--name', default=None)
    d.add_argument('--language-code', default=None, help="BCP-47, for example he-IL. Default: the language's.")
    v = sub.choices['save']
    v.add_argument('--voice', required=True)
    v.add_argument('--persona', default=None)
    v.add_argument('--default', action='store_true', help='Save as the default for every language.')
    args = ap.parse_args(argv)
    site = load(args.site)
    use_site(site)
    started = time.time()
    rc = {'sample': cmd_sample, 'design': cmd_design, 'save': cmd_save, 'list': cmd_list}[args.cmd](site, args)
    if args.cmd in ('sample', 'design'):
        print(f'({time.time() - started:.0f}s)')
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
