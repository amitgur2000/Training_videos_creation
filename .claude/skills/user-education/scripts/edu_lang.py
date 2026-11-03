"""Narration languages.

Gemini TTS (gemini-3.8-flash-tts) detects the language from the text itself: there is no
language-code parameter. The narration is simply written in the target language, and the
style instruction names it. Any language on GEMINI_TTS_LANGUAGES can be narrated.

The web app's own UI exists only in Hebrew and English (web_app_frontend src/i18n/locales.ts).
A chapter narrated in another language is filmed on the English UI.

`sec_per_char` bounds a clip's length by its text length (spaces included). Measured for
Hebrew with the Aoede voice on 2026-10-04: 0.086 to 0.092 s a character. A clip outside the
band is not its line's audio, or was cut off or ran away.
"""

from __future__ import annotations

from dataclasses import dataclass

# The official list (ai.google.dev/gemini-api/docs/speech-generation, 2026-10-04).
GEMINI_TTS_LANGUAGES = [
    'Acehnese', 'Afrikaans', 'Akan', 'Amharic', 'Armenian', 'Assamese', 'Awadhi', 'Balinese',
    'Bangla', 'Banjar', 'Bashkir', 'Basque', 'Belarusian', 'Bemba', 'Bhojpuri', 'Bosnian',
    'Buginese', 'Bulgarian', 'Burmese', 'Cantonese', 'Catalan', 'Cebuano', 'Central Kurdish',
    'Chhattisgarhi', 'Chinese', 'Crimean Tatar', 'Croatian', 'Czech', 'Danish', 'Dutch', 'Dyula',
    'Dzongkha', 'Egyptian Arabic', 'English', 'Estonian', 'Filipino', 'Finnish', 'French',
    'Galician', 'Ganda', 'Georgian', 'German', 'Greek', 'Guarani', 'Gujarati', 'Haitian Creole',
    'Halh Mongolian', 'Hausa', 'Hebrew', 'Hindi', 'Hungarian', 'Icelandic', 'Igbo', 'Iloko',
    'Indonesian', 'Iranian Persian', 'Italian', 'Japanese', 'Javanese', 'Kabyle', 'Kamba',
    'Kannada', 'Kashmiri', 'Kazakh', 'Khmer', 'Kikuyu', 'Kinyarwanda', 'Kongo', 'Korean', 'Kyrgyz',
    'Lao', 'Latgalian', 'Lingala', 'Lithuanian', 'Luxembourgish', 'Macedonian', 'Magahi',
    'Maithili', 'Malayalam', 'Maltese', 'Manipuri', 'Marathi', 'Minangkabau', 'Mizo', 'Nepali',
    'Nigerian Fulfulde', 'North Azerbaijani', 'Northern Sotho', 'Northern Uzbek',
    'Norwegian Bokmal', 'Norwegian Nynorsk', 'Nyanja', 'Occitan', 'Odia', 'Pangasinan',
    'Persian (Afghanistan)', 'Polish', 'Portuguese', 'Punjabi', 'Romanian', 'Russian', 'Santali',
    'Serbian', 'Sindhi', 'Sinhala', 'Slovak', 'Slovenian', 'Somali', 'South Azerbaijani',
    'Southern Pashto', 'Southern Sotho', 'Spanish', 'Standard Arabic', 'Standard Latvian',
    'Standard Malay', 'Swahili', 'Swati', 'Swedish', 'Tajik', 'Tamil', 'Telugu', 'Thai',
    'Tigrinya', 'Tosk Albanian', 'Turkish', 'Uyghur', 'Vietnamese',
]

APP_UI_LOCALES = ('he', 'en')
DEFAULT_VOICE = 'Aoede'   # chosen by the user from four Hebrew samples, 2026-10-04


@dataclass(frozen=True)
class Lang:
    code: str                 # folder name and CLI value, e.g. 'he'
    name: str                 # as Gemini lists it, e.g. 'Hebrew'
    dir: str = 'ltr'          # 'rtl' adds direction marks to subtitle rows
    browser_locale: str = 'en-US'
    timezone: str = 'Asia/Jerusalem'
    iso639_2: str = 'und'     # mp4 audio/subtitle language tag
    sum_up: tuple[str, ...] = ()  # the Summary's opener; said once per chapter
    wpm: float = 140.0        # estimate only, for ESTIMATED NARRATION
    sec_per_char: tuple[float, float] = (0.03, 0.25)
    voice: str = DEFAULT_VOICE

    @property
    def ui_locale(self) -> str:
        return self.code if self.code in APP_UI_LOCALES else 'en'

    @property
    def rtl(self) -> bool:
        return self.dir == 'rtl'


LANGS: dict[str, Lang] = {
    'he': Lang('he', 'Hebrew', 'rtl', 'he-IL', 'Asia/Jerusalem', 'heb', ('לסיכום',), 120.0,
               (0.045, 0.2)),
    'en': Lang('en', 'English', 'ltr', 'en-US', 'Asia/Jerusalem', 'eng', ('to sum up',), 150.0,
               (0.03, 0.15)),
    'ar': Lang('ar', 'Standard Arabic', 'rtl', 'ar', 'Asia/Jerusalem', 'ara', ('باختصار', 'للتلخيص'),
               120.0, (0.04, 0.22)),
    'ru': Lang('ru', 'Russian', 'ltr', 'ru-RU', 'Asia/Jerusalem', 'rus', ('подводя итог', 'итак'),
               130.0),
    'fr': Lang('fr', 'French', 'ltr', 'fr-FR', 'Europe/Paris', 'fra', ('pour résumer', 'en résumé'),
               150.0),
    'es': Lang('es', 'Spanish', 'ltr', 'es-ES', 'Europe/Madrid', 'spa', ('en resumen', 'para resumir'),
               150.0),
    'de': Lang('de', 'German', 'ltr', 'de-DE', 'Europe/Berlin', 'deu', ('zusammengefasst', 'zusammenfassend'),
               130.0),
}

_ALIASES = {'hebrew': 'he', 'עברית': 'he', 'english': 'en', 'arabic': 'ar', 'russian': 'ru',
            'french': 'fr', 'spanish': 'es', 'german': 'de'}


def resolve(value: str | None) -> Lang:
    """A language from a code ('he') or a name ('Hebrew'). Default Hebrew. Languages Gemini supports
    but this table does not tune get a generic entry: LTR, English UI, wide clip bounds."""
    v = (value or 'he').strip()
    key = _ALIASES.get(v.lower(), v.lower())
    if key in LANGS:
        return LANGS[key]
    by_name = {n.lower(): n for n in GEMINI_TTS_LANGUAGES}
    if v.lower() in by_name:
        name = by_name[v.lower()]
        code = ''.join(ch for ch in name.lower() if ch.isalnum())[:12]
        return Lang(code, name)
    raise SystemExit(f'Language {value!r} is not supported by Gemini TTS. Use a code from '
                     f'{", ".join(LANGS)} or a name from edu_lang.GEMINI_TTS_LANGUAGES.')
