# Producing a chapter: TTS, devices, recording, sync, review

How `edu_run.py` turns a chapter script into narrated videos without a screen, and why it is built this way. Login is in [login.md](login.md); the narrator voice in [voices.md](voices.md); site settings in [site-profile.md](site-profile.md).

## Stages and outputs

`edu_run.py training/<site>/<NN>_<slug>` loads the chapter's `<NN>_<slug>.record.py` and the nearest `site.yaml`, then calls `produce()` in `scripts/edu_produce.py`. One run handles one language and the site's devices:

| # | Stage | Code | Output (under `<NN>_<slug>/<lang>/`) |
|---|---|---|---|
| 0 | Check the script | `edu_check_chapter.check` | (none: a failing chapter is never voiced) |
| 1 | TTS: one clip per narration line, measured | `edu_tts.synthesize` | `.cache/tts/inputs.json`, `.cache/tts/NNN_<step>.wav` |
| 1b | ASR gate: each clip says its line | `edu_review.asr_check` | `.cache/tts/asr.json` |
| 2 | Recording, each step held for its audio (per device) | `edu_recorder.Recorder` | `.cache/<device>/silent.mp4`, `<device>/steps.json`, `<device>/<slug>.<lang>.<device>.timed.md` |
| 3 | Narration track, each clip at its cue, -16 LUFS | `edu_narration.build_audio` | `.cache/<device>/narration.m4a` |
| 4 | Subtitles in the script's exact words | `edu_narration.build_srt` | `<device>/<slug>.<lang>.<device>.srt` |
| 5 | Mux: the video copied as is, plus voice and a switchable subtitle track | `edu_narration.mux` | `<device>/<slug>.<lang>.<device>.mp4` (Git LFS) |
| 6 | Frame review (a report, not a gate) | `edu_review.frame_review` | `.work/<device>/frame_review.json` |

Other scripts: `edu_login.py` (login, [login.md](login.md)), `edu_explore.py` (what a page shows), `edu_voices.py` (narrator samples), `edu_browser.py` (the shared logged-in browser), `edu_site.py` (site.yaml, secrets, tools).

**Git.**
- `.gitattributes` sends `training/**/*.mp4` and `*.m4a` through LFS ([templates/gitattributes.txt](templates/gitattributes.txt)). Put those lines after any broader binary rules: the last match wins.
- The site folder's `.gitignore` excludes `.cache/`, `.work/`, `.explore/`, `voices/` and `.env`. Only the final mp4 is committed. The silent video and the narration track stay local; they are needed only for `--audio-only`.
- On a fresh clone, run `git lfs install --local` once, or the pre-push hook is missing and the mp4 objects never reach the server.

## Tools

| Piece | Where |
|---|---|
| Python packages | `scripts/requirements.txt`: Playwright, google-genai, PyYAML, pyotp. Run every script with `PYTHONUTF8=1` (Windows consoles otherwise break on Hebrew). |
| Browser | Installed Google Chrome (`channel='chrome'`, new headless mode); else Playwright's Chromium. `EDU_BROWSER_CHANNEL=chromium` forces Chromium. |
| ffmpeg / ffprobe | `EDU_FFMPEG`/`EDU_FFPROBE`, then PATH, then the WinGet, Homebrew and `/usr/bin` locations (`edu_site._tool`). |
| Contact-sheet font | Arial Bold on Windows and macOS, DejaVu Sans Bold on Linux; `EDU_FONT` overrides. |
| Secrets | `Site.secret()`: the process environment, then `training/<site>/.env`, then the repo-root `.env`. Parsed in Python, never printed. |
| Labels | `edu_i18n.Labels`: the site's translation files at `source.ref`, else `training/<site>/labels/<locale>.json`. |
| Git Bash on Windows | Arguments that start with `/` (page paths) are rewritten into Windows paths. Prefix commands with `MSYS_NO_PATHCONV=1`, or write paths without the leading slash. |

## TTS: Gemini

- **Model:** `gemini-3.8-flash-tts` (GA). `EDU_TTS_MODEL` overrides it (`gemini-3.8-flash-lite-tts` is cheaper and faster).
- **Output:** WAV, 24 kHz, mono, 16-bit. Timing comes from the WAV header, never from the model.
- **Voice and persona:** per language from `narrator.yaml` ([voices.md](voices.md)). A prebuilt voice name or a designed `voice_...` id.
- **Language:** there is no language-code parameter; the model detects the language from the text. The style instruction (`edu_tts.style_for`) is the persona, plus the language name and an instruction to read the text exactly as written.
- **API:** the Interactions API (`client.interactions.create`, `response_format={'type': 'audio'}`, `generation_config={'speech_config': [{'voice': ...}]}`, `speech_metadata.style`), as the TTS docs show.
- **Auth:** `GEMINI_API_KEY` (the Developer API). `EDU_TTS_VERTEX=1` switches to Vertex AI with application-default credentials and `GOOGLE_CLOUD_PROJECT`.
- **Caching:** a clip is reused while its model, voice, style, language and text are unchanged, so re-wording three lines costs three calls. Reused clips are moved aside by content hash before being placed. Renaming them in place once made a video repeat 14 sentences.
- **Verification**, which stops the run before recording:
  - two different lines never share identical audio
  - each clip's seconds per character fits the language's band (Hebrew 0.045 to 0.2; measured at 0.086 to 0.092)
  - no clip is silent (peak above -35 dB)
- **ASR gate:** `gemini-3.8-flash` (`EDU_REVIEW_MODEL`) transcribes every clip, and the text must match the line (normalized similarity at least 0.82). This catches skipped or invented words. The prompt gives the product's spoken name. Results are cached by audio hash.
- **A line that keeps mispronouncing:** don't re-record everything. Voice two or three re-wordings straight from `edu_tts.gemini_tts`, let the user pick one, put that wording in the script, and copy the chosen WAV into the cache. Update its `inputs.json` entry with `sha`, `text`, `audio_md5` and `duration`. The run then reuses the clip the user heard.

## Why audio comes first

Each step holds for `sum(clip lengths) + 0.4 s between lines + 0.6 s tail`, so every line fits inside its step by construction. `produce` still checks this, and refuses to mux if any line would run past its step.

## Devices

| | desktop | mobile |
|---|---|---|
| Emulation | 1536x864 CSS px | Pixel 7: 412x732 CSS px, `is_mobile`, `has_touch`, Android Chrome user agent. Chrome's own device emulation, the same as the F12 device toolbar. |
| Scale | 1.25 | 2.625 |
| Video | 1920x1080 | 1080x1920 portrait |
| Pointer | arrow and click ripple | tap ripple; `hover` draws a highlight ring |
| Scroll | mouse wheel | smooth `scrollIntoView` glide. Headless mobile emulation ignores both the wheel and `Input.synthesizeScrollGesture` swipes: they moved nothing, and an old swipe loop made every mobile step take 30 to 50 s. |
| Site layout | whatever the site serves at 1536 px | whatever it serves at 412 px: often a drawer menu, round action buttons, different components and wording |

`site.yaml` `devices` picks which videos a chapter gets; `device_profiles` can override the sizes.

**Sharp frames need the browser itself at the device scale.** The CDP screencast delivers frames in CSS pixels whatever the context's `device_scale_factor` is: a Pixel 7 context gave 412x839 frames, too soft to upscale. Launching Chrome with `--force-device-scale-factor=<scale>` gives native frames. So each device's recording launches its own browser. The 412x732 viewport is chosen so 412 x 2.625 by 732 x 2.625 is 9:16, exactly 1080x1920.

## How the video is captured

- **Off camera first:** a separate context logs in, saves the session, and opens the start page; `setup(r)` runs there. The filming context starts from the saved session, sets the UI language before the first paint, closes `dismiss_off_camera` overlays, runs `before_filming`, and only then starts the screencast.
- **Screencast:** CDP `Page.startScreencast`, JPEG at quality 92, each frame stamped with its capture time.
- **Constant-rate assembly by sampling:** for every output frame at 30 fps, the latest captured frame at or before that moment is used. Never pass per-frame durations to ffmpeg's concat demuxer: it drifted a recording by 18 s in an earlier pipeline.
- **A step's cue** is the moment its body returns **and** the page is ready: network idle, then every `wait_for_hidden` indicator (skeletons, spinners, `aria-busy`) gone. The screenshot is taken then, and the narration starts there.
- **Sync gate:** the video frame at every cue is compared with the screenshot taken at that moment, as small greyscale thumbnails. Above 6 the run fails. Scores are in `.work/<device>/sync_check.json`.
- **Waiting:** always use `page.wait_for_timeout`, never `time.sleep`. Frames arrive through Playwright's event loop.
- **Network log:** every non-GET request the site makes while filming, with status, and the body of failures, in `.work/<device>/network.log` (analytics hosts skipped). The first place to look when a save "did nothing".

## Language of the UI

The recorder forces the site's UI language by the mechanism in `site.yaml` `ui_language` (a localStorage key or a cookie set by an init script before the first paint, or a query parameter on every URL). A narration language the site's UI lacks is filmed on `fallback`. With `assert_html_lang: true`, the run stops unless `<html lang dir>` match before filming.

## The record script

Start from [templates/record.py](templates/record.py). A chapter's `<NN>_<slug>.record.py` defines three functions and imports nothing from the skill:

```python
SUBJECT = {'he': '...', 'en': '...'}     # typed content, fictional, per UI language

def setup(r):            # off camera, on r.setup_page; returns ctx for record()
    return None

def record(r, ctx):
    page = r.start()                     # the site's start_page; or r.start('/orders', before_filming=fn)
    with r.step('0.1'):
        pass
    with r.step('1.1'):
        r.click(page.get_by_test_id('new-order'))
    if r.has('1.2'):                     # a [mobile]-only step
        with r.step('1.2'):
            r.click(page.get_by_role('button', name=r.t('orders:list.addAria')))

def cleanup(r, ctx):
    pass
```

- **Locators:** test ids first (`page.get_by_test_id`; the attribute is `test_id_attribute`), then roles and labels from `r.t('<ns>:<key>', **placeholders)` or `r.t('<key>')`. **No literal UI text**, so the script works in every UI language. `edu_explore.py` prints the best locator for every control.
- **`r.mobile`** branches where the controls differ. `r.has(id)` guards device-tagged steps. `r.lang.ui_locale` picks typed content.
- **Helpers:**
  - `r.click`: a click on desktop, a tap on mobile
  - `r.hover`: a pointer dwell on desktop, a highlight ring on mobile
  - `r.highlight`
  - `r.type_text`, `r.press`, `r.pause`
  - `r.select(loc, value=...)`: a native `<select>`
  - `r.scroll_to`: the wheel on desktop, a smooth glide on mobile
  - `r.wait_text(text, fail_texts=...)`
  - `r.open(page, path)`: navigate, re-logging in if needed, and wait for content
- **Native selects vs custom dropdowns.** A native `<select>` opens an operating-system list that never appears in the screencast: use `r.select`, which points at the field and sets the value. Custom dropdowns (MUI, Radix, Headless UI, ant) draw their list in the page, so the video shows them: click the field, then click the option (`get_by_role('option', name=...)`).
- **Never press a control with real-world side effects** (pay, send to real people, delete real data, start a microphone or camera). Show the confirmation dialog, then cancel it.

## Demo account and data

- **Environment:** a non-production environment from site.yaml, as the demo account.
- **Records a chapter creates may not be deletable.** Find out during `init` (ask the user), and record it in product-context.md. If they pile up, `cleanup()` can delete them off camera when the site allows it.
- **Uniqueness.** When the site refuses duplicates (a name, an email), `setup()` picks a fictional value not yet in use, by reading the list off camera.
- **Lists are filmed as they are.** Check the contact sheets for anything that looks like real personal data before committing.
- **Wait for content, not for the network.** Add the site's skeleton or spinner selector to `wait_for_hidden`, so no step's narration describes an empty page.

## Windows: never leave a shell inside `.work/`

A shell or monitor whose working directory is inside `.work/<device>/shots` locks it, and the next run dies cleaning up. Start review commands from the repo root. A stopped run can also leave its Python process behind holding `network.log`: find it by command line and stop it.
