---
name: user-education
description: Produce a narrated Myndz tutorial video chapter (1 to 10 minutes) for therapists, end to end, in two versions, desktop and mobile. Writes the chapter script (what to click, and what the narrator says) from the web app's real code, voices every line with Gemini TTS (gemini-3.8-flash-tts) in the chosen language (default Hebrew), records the staging web app headless with Playwright (desktop 1920x1080, and a Pixel 7 phone emulation in portrait 1080x1920), holds each step on screen for exactly its audio, adds soft subtitles, and commits the scripts plus the final mp4s (Git LFS) to docs/user_education/<NN>_<slug>/. Use when asked to write, update, fix, record, voice, translate or produce a user-education chapter, tutorial video, training video, onboarding video or how-to for the Myndz web app. Not for release notes or developer docs.
argument-hint: "--chapter \"<chapter name>\" [--description \"<description and comments>\"] [--mode new|update|fix] [--lang he]"
---

# User-education chapter producer

You produce narrated tutorial videos of the Myndz web app, one chapter and one language per run. Every run ends with **two videos**, desktop and mobile, built from one script.

| Output in `docs/user_education/<NN>_<slug>/` | Committed? |
|---|---|
| `<NN>_<slug>.record.py`: the recording script. There is one per chapter, and it works for every language and both devices. | yes |
| `<lang>/<NN>_<slug>.md`: the chapter script, with English DO steps and narration in `<lang>` | yes |
| `<lang>/desktop/<NN>_<slug>.<lang>.desktop.mp4`, and the same under `mobile/`: picture, voice and a switchable subtitle track | yes, **Git LFS** |
| `<lang>/<device>/` `.srt`, `.timed.md`, `steps.json`: the subtitles, the script with cue times, and each step's timing | yes |
| `<lang>/.cache/`: TTS clips, the ASR cache, the silent videos, the narration tracks | no (git-ignored) |
| `<lang>/.work/<device>/`: frames, screenshots, contact sheets, sync check, frame review, network log | no (git-ignored) |

**Audio comes first, by design.** Every line is voiced and measured before the video is recorded. The recorder then holds each step on screen for exactly as long as its audio lasts, so the sync is exact by construction: nothing is sped up, no line is late, and no last frame is held. Gemini also checks the result in two ways. It transcribes every clip to confirm the clip says its line, and it compares each step's screenshot with its narration.

The skill is generic: everything chapter-specific lives in the data files next to this one, which grow as chapters are added.

## Read these, don't restate them

| Question | File |
|---|---|
| What is the file format, and how must narration be written (in any language)? | [style-guide.md](style-guide.md) |
| Which chapters exist, with what number, audience, start page and language status? | [chapters.md](chapters.md) |
| Where in the code does each page live, and what are its test ids and labels? | [ui-map.md](ui-map.md) |
| How do the product parts fit together (patients, meetings, summaries, methods, consent)? | [product-context.md](product-context.md) |
| How do TTS, login, devices, recording, sync, review and LFS work? | [recording.md](recording.md) |

## Parse arguments

Arguments: `$ARGUMENTS`

| Input | Required | Notes |
|---|---|---|
| `chapter` | yes | The chapter name, in any language. It is matched against chapters.md, tolerating case, typos, partial names and a Hebrew or English title. |
| `description` | no | What the chapter should teach, plus comments: audience, emphasis, facts with no code source, things to skip. For `fix`, this is the feedback. |
| `mode` | no, default `new` | `new`, `update` or `fix`. See below. |
| `lang` | no, default `he` | A code (`he`, `en`, `ar`, `ru`, `fr`, `es`, `de`) or any language name Gemini TTS supports (`edu_lang.GEMINI_TTS_LANGUAGES`: 130+ languages, Hebrew included). The app's own UI exists only in Hebrew and English, so other languages are filmed on the English UI. |

| Mode | Does |
|---|---|
| `new` | Writes the script (steps 1 to 7), then produces both videos (step 8). If the chapter already exists in another language, this is a **translation**: copy that script, keep every DO line and id exactly, translate the narration, and reuse the existing record.py. |
| `update` | Brings an existing script up to date with the current UI (steps 1 to 7), then produces. |
| `fix` | Applies the feedback in `description` to the script, the record.py or the production settings, and to the skill itself when the lesson is general. Then produces. |

If the chapter match is ambiguous, ask the user. Do not guess.

## Procedure

### 1. Resolve the chapter

1. Look the name up in chapters.md.
2. **If there is no match, it is a new chapter.** Propose a registry row: the next free number, a snake_case English slug, the English and the native title, the audience, and the start page (normally `/dashboard`). Confirm the row with the user, then append it. Never renumber.
3. The chapter folder is `docs/user_education/<NN>_<slug>/`, and the script is `<lang>/<NN>_<slug>.md` inside it.
4. Check the mode against the folder:
   - `new` when this language's script exists: stop and ask whether to switch to `update`.
   - `update` or `fix` when this language's script does not exist: stop and ask whether to switch to `new`.

### 2. Get the source of truth

Describe only what the product does today. The code on `origin/main` is the source of truth; memory, design docs and older chapters are not.

1. Run `git -C ../web_app_frontend fetch origin`, then read files on `origin/main` (`git show origin/main:<path>`). The local checkout is routinely stale. Do the same for `../myndz-ai-backend` when the behaviour lives on the server.
2. Use ui-map.md to find the entry files. Read them for everything the viewer will see, on **both** layouts. Below 900px the app renders mobile components, often with different wording:
   - exact labels, in `src/locales/<he|en>/*.json`, resolved through the i18n key the component uses
   - dialog titles, toasts and validation messages
   - test ids and aria labels (for record.py)
   - which layout shows which control
3. If an area is not in ui-map.md yet, explore it, then **add it to ui-map.md**.
4. Facts with no code source come from the user (`description`, or ask). Never invent them. Record each one in product-context.md as user-supplied, with the date.

### 3. Mode-specific work

- **`new`**: go on to step 4. For a translation, go straight to step 5 and translate.
- **`update`**:
  1. Read the script's `SOURCE COMMIT` and `SOURCES`.
  2. Run `git log --oneline <sha>..origin/main -- <SOURCES>`.
  3. Re-verify every label.
  4. Keep wording that is still true. Keep DO ids stable where the step is unchanged, so the record.py and the TTS cache stay valid.
  5. Update every language folder of the chapter, or say which ones are now stale.
- **`fix`**:
  1. Apply the feedback.
  2. Decide whether it is a **general** lesson, such as "never narrate over a page load", "the voice mispronounces X", or "the tap ripple is too small".
  3. If it is general, add a dated rule to style-guide.md's **Learnings from feedback**. Change a contradicting rule rather than appending a conflict. Fix `scripts/` when the lesson is about recording or audio.
  4. Tell the user that the skill was updated.

### 4. Plan the page walk

1. Start on the chapter's start page and go forward only.
2. Every page, dialog or menu is its own `##` section.
3. Plan **both devices at once**. Where a control differs, for example the mobile round + button instead of the desktop header button, use a device-tagged DO pair (`> DO 3.2 [desktop]:` / `> DO 3.3 [mobile]:`) and write narration that fits both, or tag the narration too.
4. Show the user the page list before writing, unless they said to go ahead.

### 5. Write the chapter

Follow style-guide.md exactly. Fill in the metadata block: `SOURCE COMMIT` (the short sha of `web_app_frontend` origin/main), `SOURCES`, `LANGUAGE`, and `ESTIMATED NARRATION`.

Write or update `<NN>_<slug>.record.py` (see recording.md, "The record script"):
- `setup(r)` runs off camera.
- `record(r, ctx)` has one `with r.step(id):` per DO, guarded with `if r.has(id):` for device-tagged steps.
- `cleanup(r, ctx)` runs at the end.
- Locators use test ids first, then `r.t('<ns>:<key>')` labels. **Never hard-code Hebrew or English text in record.py**; it must work in every language.

### 6. Verify the script

```bash
python .claude/skills/user-education/scripts/edu_check_chapter.py docs/user_education/<NN>_<slug>/<lang>/<NN>_<slug>.md
```

Fix everything it reports. It checks the format, symbols, quote marks, niqqud, bidi marks, DO ids and device tags, and fails on any sentence said twice in one video. Also check by hand:
- Every UI label the narration names appears in the locale files or SOURCES. Grep each one.
- The narration makes sense when heard alone, from start to finish, in each device's video.

### 7. Update the registry

Set the chapter's language status in chapters.md: `drafted` after the script, `produced` after step 8, `verified` only when the user signs off.

### 8. Produce: voice, record, sync, review

Read [recording.md](recording.md) first.

1. **Login.** The recorder signs in by itself with the saved trusted-device key. If the run exits with **code 3**, the device trust expired (after 14 days) or the terms of use need accepting. Start `scripts/edu_login.py` in the background and ask the user to type the emailed code in the browser window that opens.
2. **Run** with the Playwright venv, in the background. It takes about twice the video length plus setup:
   ```bash
   PYTHONUTF8=1 C:/Users/amitg/projects/playwright/playwright/Scripts/python.exe docs/user_education/<NN>_<slug>/<NN>_<slug>.record.py --lang <lang>
   ```
   - `--device desktop|mobile` films one device only.
   - `--audio-only` rebuilds narration, subtitles and mux from the cached silent video. Use it only when the wording did not change.
   - `--no-review` skips the Gemini frame review.
3. **On failure**, read `.work/<device>/FAILED.png`, `network.log` and the error. Fix the locator, the wait or the script, then re-run; unchanged TTS clips are reused. After three failed attempts, stop and report.
4. **Review before reporting:**
   - Read the contact sheets, `.work/<device>/contact_*.png`, one labelled frame per DO, for **both** devices. Check each frame shows what its DO says, and that no real-looking personal data is visible.
   - Read `.work/<device>/frame_review.json`. Look at every step Gemini flagged.
   - The sync check and the ASR check passed; the run fails otherwise.
   - Spot-listen: `ffmpeg -ss <cue> -t 8 -i <mp4> -vn spot.wav` around two or three cues per device.
5. **Commit gates.** `git lfs status` must list every mp4 as `LFS`. `git ls-files docs/user_education | grep -E '/\.(cache|work)/'` must print nothing.
6. **Report:**
   - both videos' paths, lengths and sizes
   - the page list and the narration minutes
   - anything that looked wrong on screen
   - **product findings** (bugs, confusing labels, dead ends, with file:line), which are reported but never narrated
   - **open questions**
   - which skill files were updated

## Rules

- **Never narrate from memory.** Every label comes from the code you read in step 2.
- **Never demonstrate a bug.** Route around it and report it.
- **Never invent a workaround or support process.** Ask the user.
- **Staging only.** `edu_env.py` has no production entry, and must not get one. Recording creates real records in the demo account.
- **Demo data only.** Type obviously fictional names. Never type or show a real person's details. Videos are committed.
- **Never start a real microphone recording** in a video. Show the consent dialog or the menu instead.
- **Secrets:** the demo login, the Gemini key and the auth state file are never printed, logged or committed.
- **Git:** branch from `origin/main` with an allowed prefix (`feature/`, `docs/`, ...). Media goes through LFS. Open a PR; never merge it.

## Anti-patterns

- Writing `SAY:` or any other prefix on narration lines. Narration is plain text lines.
- Starting a narration line with `[`, because `.timed.md` puts cues there.
- Quoting or bolding labels in narration. The voice reads plain words, and the subtitles show the text exactly as written.
- Hard-coding a label string in record.py instead of using `r.t(...)` or a test id.
- Quoting a label that differs between the desktop and mobile layouts. Describe the control instead ("the recording consent field").
- Editing narration and then running `--audio-only`. The clip lengths changed, so re-record.
