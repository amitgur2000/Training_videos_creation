# Producing a chapter: TTS, login, devices, recording, sync, review

How `produce` turns a chapter script into two narrated videos without a screen, and why it is built this way.

## Stages and outputs

A chapter's `<NN>_<slug>.record.py` calls `produce()` in `scripts/edu_produce.py`. One run handles one language and both devices:

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

**Git.**
- `.gitattributes` sends `docs/user_education/**/*.mp4` and `*.m4a` through LFS. Those lines come after the repo's binary list, because the last match wins.
- `docs/user_education/.gitignore` excludes `.cache/` and `.work/`. Only the final mp4 is committed (a user decision, 2026-10-04): the silent video and narration track are local, and are needed only for `--audio-only`.
- On a fresh clone, run `git lfs install --local` once, or the pre-push hook is missing and the mp4 objects never reach GitHub.

## Tools

| Piece | Where |
|---|---|
| Python, Playwright, google-genai | venv `C:/Users/amitg/projects/playwright/playwright/Scripts/python.exe` (Playwright 1.55, google-genai 2.28). Run with `PYTHONUTF8=1`. |
| Browser | Installed Google Chrome (`channel='chrome'`, new headless mode). `EDU_BROWSER_CHANNEL=chromium` forces Playwright's Chromium. |
| ffmpeg / ffprobe | Taken from `EDU_FFMPEG`/`EDU_FFPROBE`, then PATH, then the WinGet package folder (`edu_env._tool`). ffmpeg 8 is installed via WinGet and is not on the Bash PATH. |
| Secrets | `edu_env.secret()`: the process environment first, then the git-ignored `init_shell_local_debug_Eran_2.sh`. Parsed in Python, never printed. |
| Labels | `edu_i18n.Labels` reads `web_app_frontend` `src/locales/<locale>/<ns>.json` from `origin/main`. Fetch that repo first. |

## TTS: Gemini

- **Model:** `gemini-3.8-flash-tts` (GA). `EDU_TTS_MODEL` overrides it.
- **Output:** WAV, 24 kHz, mono, 16-bit. Timing comes from the WAV header, never from the model.
- **Voice:** `Aoede`, chosen by the user from four Hebrew samples (Kore, Aoede, Charon, Sulafat) on 2026-10-04. `edu_lang.DEFAULT_VOICE` sets it; a `Lang` entry can override it.
- **Language:** there is no language-code parameter; the model detects the language from the text. The style instruction (`edu_tts.style_for`) also names the language, and tells the voice to read the text exactly as written.
- **API:** the Interactions API (`client.interactions.create`, `response_format={'type': 'audio'}`, `generation_config={'speech_config': [{'voice': ...}]}`, `speech_metadata.style`). This is what the TTS docs show. `generate_content` with `response_modalities=['AUDIO']` also worked in the spike, as a fallback.
- **Auth:** `GEMINI_API_KEY` (the Developer API). `EDU_TTS_VERTEX=1` switches to Vertex AI, which needs fresh `gcloud auth application-default login`. That had expired on 2026-10-04, which is why the key is the default.
- **Caching:** a clip is reused while its model, voice, style, language and text are unchanged, so re-wording three lines costs three calls. Reused clips are moved aside by content hash before being placed. Renaming them in place once made a video repeat 14 sentences.
- **Verification**, which stops the run before recording:
  - two different lines never share identical audio
  - each clip's seconds per character fits the language's band (Hebrew 0.045 to 0.2; measured at 0.086 to 0.092)
  - no clip is silent (peak above -35 dB)
- **ASR gate:** `gemini-3.8-flash` transcribes every clip, and the text must match the line (normalized similarity at least 0.82). This catches skipped or invented words. Results are cached by audio hash.
- **A line that keeps mispronouncing:** don't re-record everything. Voice two or three re-wordings straight from `edu_tts.gemini_tts`, let the user pick one, put that wording in the script, and copy the chosen WAV into the cache. Update its `inputs.json` entry with `sha`, `text`, `audio_md5` and `duration`. The run then reuses the clip the user heard.

## Why audio comes first

Each step holds for `sum(clip lengths) + 0.4 s between lines + 0.6 s tail`, so every line fits inside its step by construction. `produce` still checks this, and refuses to mux if any line would run past its step.

## Devices

| | desktop | mobile |
|---|---|---|
| Emulation | 1536x864 CSS px | Pixel 7: 412x732 CSS px, `is_mobile`, `has_touch`, Android Chrome user agent. This is Chrome's own device emulation, the same as the F12 device toolbar. |
| Scale | 1.25 | 2.625 |
| Video | 1920x1080 | 1080x1920 portrait |
| Pointer | arrow and click ripple | tap ripple; `hover` draws a highlight ring |
| Scroll | mouse wheel | smooth `scrollIntoView` glide. Headless mobile emulation ignores both the wheel and `Input.synthesizeScrollGesture` swipes: they moved nothing, and the old swipe loop made every mobile step take 30 to 50 s. |
| App layout | sidebar | below 900px: drawer, round buttons, mobile intake form |

**Sharp frames need the browser itself at the device scale.** The CDP screencast delivers frames in CSS pixels whatever the context's `device_scale_factor` is: a Pixel 7 context gave 412x839 frames, too soft to upscale. Launching Chrome with `--force-device-scale-factor=<scale>` gives native frames (1080x2199 in the spike). So each device's recording launches its own browser. The 412x732 viewport is chosen so 412 × 2.625 by 732 × 2.625 is 9:16, exactly 1080x1920.

## How the video is captured

- **Screencast:** CDP `Page.startScreencast`, JPEG at quality 92, each frame stamped with its capture time.
- **Constant-rate assembly by sampling:** for every output frame at 30 fps, the latest captured frame at or before that moment is used. Never pass per-frame durations to ffmpeg's concat demuxer: it drifted a recording by 18 s in the reference pipeline.
- **Sync gate:** the video frame at every cue is compared with the screenshot taken at that moment, as small greyscale thumbnails. Above 6 the run fails. Scores are in `.work/<device>/sync_check.json`.
- **Waiting:** always use `page.wait_for_timeout`, never `time.sleep`. Frames arrive through Playwright's event loop.

## Language of the UI

The recorder sets `localStorage["myndz.locale"]` with an init script, before the app's first paint, to the language's UI locale: `he` or `en`, with `en` for every other narration language. It then asserts `<html lang dir>`.

A choice stored in the browser wins over the server preference (`reconcileServerLocale` in `src/i18n/localeSwitch.ts`). The app also writes it back to the therapist's `preferred_language`. So filming in English switches the demo account's email language until a Hebrew run switches it back. This is harmless on the staging demo account.

## Login

- **How login works:** the sign-in sends `localStorage["myndz_device_key_<email>"]` (`useAuth.ts`). The backend skips the emailed code for a device it trusted within the last 14 days (`define_auth_challenge.py`, `MFA_RETENTION_HOURS=336`). Tokens are also in localStorage, so Playwright's `storage_state` file `C:/tmp/user_education/.auth/staging-demo.json` holds everything. It is outside the repo; never commit, print or copy it.
- **Each recording:** the recorder signs in off camera, re-using the saved device key, and saves the refreshed state. No person is needed for 14 days.
- **Exit code 3** means the code or the terms of use are needed. Run `scripts/edu_login.py --env staging` in the background. It opens a visible Chrome, signs in, and waits (default 30 minutes, `--timeout-min`) while the person types the code from the demo Gmail inbox.
- **Fully automatic codes (optional):** `edu_login` reads the code over IMAP when `EDU_IMAP_PASS` is set. That has to be a Gmail app password for the demo inbox with IMAP enabled. On 2026-10-04, IMAP rejected `MYNDZ_ADMIN_GMAIL_PASS` (the SMTP app password), so this is off until such a password exists.
- **Bug fixed 2026-10-04:** the headed login gave up the moment it saw the code page, because the page it was "waiting to leave" counted as an answer. It now waits until the app itself loads.

## The record script

```python
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / '.claude' / 'skills' / 'user-education' / 'scripts'))
from edu_produce import produce

def setup(r):            # off camera, r.setup_page; returns ctx for record()
    return None

def record(r, ctx):
    page = r.start('/dashboard')
    with r.step('0.1'):
        pass
    with r.step('1.1'):
        r.click(page.get_by_test_id('dashboard-add-patient'))
    if r.has('3.2'):                     # a [mobile]-only step
        with r.step('3.2'):
            r.click(page.get_by_role('button', name=r.t('clients:list.addAria', client=...)))

def cleanup(r, ctx):
    pass

if __name__ == '__main__':
    sys.exit(produce(__file__, setup, record, cleanup))
```

- **Locators:** test ids first (`page.get_by_test_id`), then roles and labels from `r.t('<ns>:<key>', **placeholders)`. **No literal UI text**, so the script works in every language. `{client}` and similar placeholders are filled per account role in the app (`roleWording.ts`): pass the word the screen shows.
- **`r.mobile`** branches where the controls differ. `r.has(id)` guards device-tagged steps.
- **Helpers:**
  - `r.click`: a click on desktop, a tap on mobile
  - `r.hover`: a pointer dwell on desktop, a highlight ring on mobile
  - `r.highlight`
  - `r.type_text`, `r.press`, `r.pause`
  - `r.scroll_to`: the wheel on desktop, a smooth glide on mobile
  - `r.wait_text(text, fail_texts=...)`
- **MUI selects are not native.** Their menus are drawn in the page, so the video shows them. Open the field, then click the option (`get_by_role('option', name=...)`).
- **Never press a control that starts a microphone recording.** The consent dialog is the furthest a video goes.

## Demo account and data

- **Environment:** staging only (`https://staging.myndz.ai`), as the demo therapist (`MYNDZ_DEMO_USER_EMAIL`).
- **Patients can't be deleted** (there is no UI and no API). Every add-patient recording leaves one more fictional patient in the demo list; the user accepted this on 2026-10-04.
- **The backend refuses a duplicate name** with the same treatment type (409). A chapter that creates a patient picks, in `setup()`, a fictional name not yet in the list (see chapter 01's `NAMES`).
- **Every patient in the staging demo list is fictional** (user, 2026-10-04), so lists are filmed as they are. Still check the contact sheets for anything that looks like real personal data before committing.
- **Wait for content, not for the network.** Pages paint MUI skeletons (`.MuiSkeleton-root`) first. A step whose narration describes the page waits until they are gone.

## Windows: never leave a shell inside `.work/`

A shell or monitor whose working directory is inside `.work/<device>/shots` locks it. The next run then dies cleaning up. Start review commands from the repo root.
