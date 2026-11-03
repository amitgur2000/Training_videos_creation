# Voices: choosing the narrator

Every narration line is voiced by Gemini TTS (`gemini-3.8-flash-tts`, `EDU_TTS_MODEL` overrides). The **narrator** of a site is two things, per language:

| | What | Example |
|---|---|---|
| **voice** | A prebuilt Gemini voice, or a **designed** voice made from a description (a persistent `voice_...` id) | `Aoede`, `voice_8f2c...` |
| **persona** | The style instruction sent with every line: who is speaking, and how | `Calm, warm and clear narrator of a software tutorial, like a friendly colleague.` |

They live in `training/<site>/narrator.yaml`, written by `edu_voices.py save`:

```yaml
default:
  voice: Kore
he:
  voice: Aoede
  persona: Calm, warm colleague who explains slowly and kindly
  chosen: '2026-11-03'
```

A language without its own entry uses `default`; with no file at all, the voice is `Kore` and the persona is the skill's default. Both are part of the TTS cache key, so a new choice re-voices every line on the next production.

**The voice is the user's choice, by ear.** Never pick one silently. The `voices` mode (and `init`, and the first `new` in a language with no narrator) makes samples and asks the user to listen.

## The `voices` mode

1. **Ask** what the user wants to hear: a quick shortlist (default), a style ("warm", "firm"), all 30, or a described persona. For a persona, also ask: female or male, age, tone, pace.
2. **Sample.** Every sample reads the same text, so the comparison is fair. The default text greets the viewer with the product's spoken name, which also tests how the voice pronounces it inside, for example, Hebrew narration. `--chapter` uses the chapter's first lines instead; `--text` takes any sentence.
   ```bash
   python $S/edu_voices.py sample --site <s> --lang he                                   # the shortlist: Kore, Aoede, Charon, Sulafat
   python $S/edu_voices.py sample --site <s> --lang he --tag warm                        # every voice with that style
   python $S/edu_voices.py sample --site <s> --lang he --voices Aoede,Sulafat \
          --persona "Calm, warm colleague" --persona "Energetic, upbeat coach"           # voices x personas
   python $S/edu_voices.py sample --site <s> --lang he --all                             # all 30 (30 API calls)
   ```
   The samples land in `training/<s>/voices/<lang>/` (git-ignored) with an `index.html` that has one player per sample. Give the user that file's full path, or the WAV paths.
3. **Design a voice** when no prebuilt voice fits, or the user describes a specific person-like voice:
   ```bash
   python $S/edu_voices.py design --site <s> --lang he --gender female \
          --description "A warm, calm woman in her forties, clear and unhurried, like a patient teacher"
   ```
   Gemini creates a persistent voice (`voice_...`), returns its own preview, and the script also voices the sample text with it. The id is recorded in `designed_voices.json`. Designed voices belong to the Gemini project of the API key, expire a year after their last use, and count toward 200 per project. Gemini's voice design does not publish a list of supported languages; listen to the Hebrew sample before choosing it. It cannot clone a real person's voice from a description, and the skill must never try to imitate a real, identifiable person.
4. **Save** the user's pick, for one language or as the default:
   ```bash
   python $S/edu_voices.py save --site <s> --lang he --voice Aoede --persona "Calm, warm colleague"
   python $S/edu_voices.py save --site <s> --voice Kore --default
   ```
5. `python $S/edu_voices.py list --site <s>` shows the prebuilt voices, the site's designed voices and the current choice.

## The prebuilt voices

Gemini lists each with one style word (speech-generation docs, checked 2026-11-03). The shortlist is the four a user compared for Hebrew tutorial narration (Aoede was chosen then).

| Style | Voices |
|---|---|
| Warm, gentle, soft | **Sulafat** (warm), Vindemiatrix (gentle), Achernar (soft), Enceladus (breathy) |
| Calm, even, smooth | Schedar (even), Algieba (smooth), Despina (smooth), Callirrhoe (easy-going), Umbriel (easy-going), **Aoede** (breezy) |
| Clear, informative | **Charon** (informative), Rasalgethi (informative), Sadaltager (knowledgeable), Iapetus (clear), Erinome (clear) |
| Firm, mature | **Kore** (firm), Orus (firm), Alnilam (firm), Gacrux (mature), Pulcherrima (forward), Algenib (gravelly) |
| Friendly, casual | Achird (friendly), Zubenelgenubi (casual) |
| Bright, lively, upbeat | Zephyr (bright), Autonoe (bright), Puck (upbeat), Laomedeia (upbeat), Sadachbia (lively), Leda (youthful), Fenrir (excitable) |

For tutorials, start with the calm, warm or clear rows; bright and excitable voices tire viewers over several minutes. `--tag` takes Gemini's single style word (`--tag warm`, `--tag firm`).

## Writing a persona

- One or two sentences: who is speaking, the tone, the pace. "Calm, warm and clear narrator of a software tutorial, like a friendly colleague."
- The skill appends the language and the rule to read the text exactly as written, so do not repeat those.
- Keep it short and situational. Gemini's docs advise a designed voice, not a long persona, for a strongly specific character.
- Never ask for an accent or a manner that mocks a group, and never name a real person to imitate.

## Language notes

- **Hebrew** is tuned: the clip-length band, right-to-left subtitles, the summary opener, and style-guide rules for niqqud, abbreviations and gender-neutral plural. Check the first clips that say the product name, and any Latin acronyms.
- Any language Gemini TTS supports can be narrated (`edu_lang.GEMINI_TTS_LANGUAGES`); there is no language-code parameter, so the narration text sets the language. The same voice and persona can serve several languages, but listen to each one: a voice that sounds natural in English can sound flat in another language.
