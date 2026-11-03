---
name: training-videos
description: Produce narrated training videos for any web site or web app, one chapter at a time, in two versions, desktop and mobile. Takes the site (a URL, optionally its source code) and the chapters the user wants; writes each chapter's script (what to click, and what the narrator says) from the site's real content; voices every line with Gemini TTS in the chosen language (Hebrew well tuned, 130+ languages) and the narrator voice the user picked from samples; logs in by itself (including TOTP or email MFA, or once by hand for SMS, push or SSO); records the site headless with Playwright (desktop 1920x1080, and a Pixel 7 phone emulation in portrait 1080x1920); holds each step on screen for exactly its audio; adds soft subtitles; and writes the scripts plus the final mp4s to training/<site>/<NN>_<slug>/. Use when asked to set up a site for training videos, plan a curriculum, write, update, fix, record, voice, translate or produce a tutorial, training, onboarding or how-to video for a web site, or to choose or sample a narrator voice. Not for release notes, marketing videos or developer docs.
argument-hint: "--site <name> [--chapter \"<chapter name>\"] [--description \"<what to teach, comments>\"] [--mode init|new|update|fix|voices] [--lang <code>] [--env <name>]"
---

# Training-video producer

You produce narrated tutorial videos of a web site, one chapter and one language per run. Every run ends with a video per device in the site profile (normally **two**, desktop and mobile), built from one script.

**Audio comes first, by design.** Every line is voiced and measured before the video is recorded. The recorder then holds each step on screen for exactly as long as its audio lasts, so the sync is exact by construction: nothing is sped up, no line is late, and no last frame is held. Gemini also checks the result in two ways. It transcribes every clip to confirm the clip says its line, and it compares each step's screenshot with its narration.

**The skill is product-free.** Everything about a particular site lives in its folder, `training/<site>/` (the root is `$TRAINING_ROOT` or `<repo>/training`). A run never writes product facts into the skill.

| In `training/<site>/` | What | Committed? |
|---|---|---|
| `site.yaml` | The site profile: URLs, login and MFA, languages, devices, source code, selectors. Schema: [site-profile.md](site-profile.md) | yes |
| `narrator.yaml` | The narrator voice and persona per language, written by `edu_voices.py save` | yes |
| `chapters.md` | The chapter registry (curriculum) | yes |
| `ui-map.md` | Where each screen lives (code paths or URLs), its test ids and labels, per device | yes |
| `product-context.md` | How the product's parts fit together; facts the user supplied, dated | yes |
| `labels/<locale>.json` | On-screen strings, for sites without source access (captured by `edu_explore.py`) | yes |
| `designed_voices.json` | Designed Gemini voices made for this site | yes |
| `<NN>_<slug>/<NN>_<slug>.record.py` | The recording script. One per chapter; works for every language and device | yes |
| `<NN>_<slug>/<lang>/<NN>_<slug>.md` | The chapter script: English DO steps, narration in `<lang>` | yes |
| `<NN>_<slug>/<lang>/<device>/` `.mp4` | Picture, voice and a switchable subtitle track | yes, **Git LFS** |
| `<NN>_<slug>/<lang>/<device>/` `.srt`, `.timed.md`, `steps.json` | Subtitles, the script with cue times, each step's timing | yes |
| `.env` | Credentials, TOTP secret, API key | **never** |
| `.explore/`, `voices/`, `<lang>/.cache/`, `<lang>/.work/` | Exploration dumps, voice samples, TTS clips, frames, review material | no (git-ignored) |
| Login session (`site.session_file`) | `~/.training_videos/<site>/<env>.json`, outside every repo | **never** |

## Read these, don't restate them

| Question | File |
|---|---|
| What goes in site.yaml? | [site-profile.md](site-profile.md) |
| How is login handled, with or without MFA? What does exit code 3 mean? | [login.md](login.md) |
| Which voices exist, how are samples made, how is the narrator chosen? | [voices.md](voices.md) |
| What is the chapter file format, and how must narration be written (in any language)? | [style-guide.md](style-guide.md) |
| How do TTS, devices, recording, sync and review work? | [recording.md](recording.md) |
| Starting files for a new site or chapter | [templates/](templates/) |

## Setup (once per machine)

```bash
python -m pip install -r .claude/skills/training-videos/scripts/requirements.txt
python -m playwright install chromium        # Google Chrome is used when installed
```

ffmpeg and ffprobe must be on PATH (or set `EDU_FFMPEG`/`EDU_FFPROBE`). `GEMINI_API_KEY` must be in the environment or a `.env`. Run every script with `PYTHONUTF8=1`. Below, `S=.claude/skills/training-videos/scripts`.

## Parse arguments

Arguments: `$ARGUMENTS`

| Input | Required | Notes |
|---|---|---|
| `site` | yes | The folder name under `training/`. If only one site exists, use it. If none exists, the mode is `init`. |
| `chapter` | for new, update, fix | The chapter name in any language, matched against the site's chapters.md (tolerating case, typos, partial names, the native or the English title). |
| `description` | no | What the chapter should teach, plus comments: audience, emphasis, facts with no source, things to skip. For `fix`, the feedback. For `init`, the chapter list if the user gave one. |
| `mode` | no, default `new` | `init`, `new`, `update`, `fix` or `voices`. See below. |
| `lang` | no | A code (`he`, `en`, `ar`, `ru`, `fr`, `es`, `de`) or any language Gemini TTS supports (`edu_lang.GEMINI_TTS_LANGUAGES`). Default: the site's `default_lang`. |
| `env` | no | An environment in site.yaml. Default: `default_env`. |

| Mode | Does |
|---|---|
| `init` | Sets up a new site: profile, login, exploration, curriculum, narrator. See "Init". |
| `new` | Writes the chapter script (steps 1 to 7), then produces the videos (step 8). If the chapter exists in another language, this is a **translation**: copy that script, keep every DO line and id exactly, translate the narration, reuse the record.py. |
| `update` | Brings an existing script up to date with the current site (steps 1 to 7), then produces. |
| `fix` | Applies the feedback in `description` to the script, the record.py, the site profile or the production settings, and to the skill itself when the lesson is general. Then produces. |
| `voices` | Samples narrator voices for a language and saves the user's pick ([voices.md](voices.md)). |

If anything is ambiguous (the chapter match, the site, a fact), ask the user. Do not guess.

## Init: a new site

Ask the user (one round of questions, then confirm the profile before writing it):
1. **Name and URL(s).** A short folder name; each environment's URL. Which environment is safe to record: one where typing creates only demo data? Prefer staging or a demo tenant. A production URL is marked `production: true`; recording it needs the user's explicit opt-in (site-profile.md).
2. **Login.** None, or form login; the account to use (a demo account with fictional data); the **MFA** method: none, TOTP (ask for the shared secret, the one behind the QR code), email code (IMAP access), or something only a person can do (SMS, push, passkey, SSO, CAPTCHA). Credentials go in `training/<site>/.env`, never in site.yaml or chat logs. See [login.md](login.md).
3. **Audience and words.** Who watches; the words they use for the product's things (`product.vocabulary`); words never to say (`narration.forbidden_words`).
4. **Languages and devices.** Narration languages (default first); the UI languages the site has and how it switches language (localStorage key, cookie, query parameter); desktop, mobile or both.
5. **Source code (optional).** A local clone and branch, and where the translation files are. Without it, the live site is the only source.
6. **The chapters.** The list the user wants to teach, in order, with a line each. If they have none, propose a curriculum from the exploration (step 7 below) and confirm it.

Then:
1. Copy `templates/` into `training/<site>/`: `site.yaml` (filled in), `chapters.md`, `ui-map.md`, `product-context.md`, `.gitignore`. Create `.env` from the answers (git-ignored; never print it). Append `templates/gitattributes.txt` to the repo's `.gitattributes` if its LFS lines are missing, and run `git lfs install --local` once.
2. Log in once: `python $S/edu_login.py --site <site>` (a visible browser; the person finishes MFA if needed). Then check that headless works: `python $S/edu_login.py --site <site> --headless`. Exit 0 means recordings need no person until the site forgets the device or the session.
3. Explore: `python $S/edu_explore.py --site <site> [--capture-labels] <start page> <other pages>`. Read the `.controls.md` and `.png` files, then fill `ui-map.md` and `product-context.md` (mark what the user told you, with the date).
4. Register the chapters in `chapters.md`: two-digit numbers in curriculum order, snake_case English slugs, English and native titles, audience, start page, `Languages` empty.
5. Narrator: run the `voices` mode for the default language and save the pick.
6. Report what was set up, and what is still missing (a TOTP secret, a demo account, test ids).

## Procedure for new, update and fix

### 1. Resolve the chapter

1. Look the name up in the site's chapters.md.
2. **No match: a new chapter.** Propose a registry row: the next free number, a snake_case English slug, the English and native title, the audience, and the start page (normally `start_page`). Confirm it with the user, then append it. Never renumber.
3. The chapter folder is `training/<site>/<NN>_<slug>/`, and the script is `<lang>/<NN>_<slug>.md` inside it.
4. Check the mode against the folder:
   - `new` when this language's script exists: stop and ask whether to switch to `update`.
   - `update` or `fix` when it does not exist: stop and ask whether to switch to `new`.
5. If `narrator.yaml` has no voice for this language (and no default), run the `voices` mode first.

### 2. Get the source of truth

Describe only what the site does today. Memory, design documents and older chapters are not sources.

1. **The live site, always.** `python $S/edu_explore.py --site <site> --lang <lang> <path> ...` for every page the chapter walks, on every device. The `.png` shows what the viewer will see; `.controls.md` lists each control's visible label, test id and best locator; `.aria.yaml` is the page as the accessibility tree names it. The mobile layout often has different controls and wording: read both.
2. **The source code, when site.yaml has `source.repo`.** `git -C <repo> fetch`, then read files at `source.ref` (`git show <ref>:<path>`); the local checkout is routinely stale. Read the entry files from ui-map.md for exact labels (translation files, resolved through the key the component uses), dialog titles, toasts, validation messages, test ids, and which layout shows which control. When code and screen disagree, the screen on the recorded environment wins; report the difference.
3. If an area is not in ui-map.md yet, add it: path or URL, the controls the chapter uses, their test ids and labels, per device.
4. Facts with no source come from the user (`description`, or ask). Never invent them. Record each one in product-context.md as user-supplied, with the date.

### 3. Mode-specific work

- **`new`**: go on to step 4. For a translation, go straight to step 5 and translate.
- **`update`**:
  1. Read the script's `SOURCE COMMIT` (or the date it was last explored) and `SOURCES`.
  2. With code: `git log --oneline <sha>..<ref> -- <SOURCES>`. Without: re-explore and compare with ui-map.md.
  3. Re-verify every label.
  4. Keep wording that is still true. Keep DO ids stable where the step is unchanged, so the record.py and the TTS cache stay valid.
  5. Update every language folder of the chapter, or say which ones are now stale.
- **`fix`**:
  1. Apply the feedback.
  2. Decide whether it is a **general** lesson ("never narrate over a page load", "the voice mispronounces X", "the tap ripple is too small"), a **site** lesson (a selector, a login quirk, a word this audience dislikes), or chapter-only.
  3. General: add a dated rule to style-guide.md's **Learnings from feedback**, or fix `scripts/` when it is about recording or audio. Change a contradicting rule rather than appending a conflict. Site: update `site.yaml`, `ui-map.md` or `product-context.md`. Never write a site's facts into the skill.
  4. Tell the user which files were updated.

### 4. Plan the page walk

1. Start on the chapter's start page and go forward only.
2. Every page, dialog or menu is its own `##` section.
3. Plan **all devices at once**. Where a control differs (a phone's round + button instead of a desktop header button, a menu behind a hamburger), use a device-tagged DO pair (`> DO 3.2 [desktop]:` / `> DO 3.3 [mobile]:`) and write narration that fits both, or tag the narration too.
4. Show the user the page list before writing, unless they said to go ahead.

### 5. Write the chapter

Follow [style-guide.md](style-guide.md) exactly. Fill in the metadata block: `SOURCE COMMIT` (the short sha of `source.ref`, or `live <date>` without source), `SOURCES` (code paths or URLs), `LANGUAGE`, `ESTIMATED NARRATION`.

Write or update `<NN>_<slug>.record.py` from [templates/record.py](templates/record.py) (API in recording.md, "The record script"):
- `setup(r)` runs off camera, on `r.setup_page`; it returns a context for `record`.
- `record(r, ctx)` calls `page = r.start()`, then has one `with r.step(id):` per DO, guarded with `if r.has(id):` for device-tagged steps.
- `cleanup(r, ctx)` runs at the end, off camera.
- Locators: test ids first, then roles with labels from `r.t('<key>')`. **Never hard-code UI text in record.py**; it must work in every UI language. Typed content (fictional names, sentences) goes in per-language dicts.

### 6. Verify the script

```bash
python $S/edu_check_chapter.py training/<site>/<NN>_<slug>/<lang>/<NN>_<slug>.md
```

Fix everything it reports. It checks the format, symbols, quote marks, niqqud, bidi marks, DO ids and device tags, setup words and the site's forbidden words, and fails on any sentence said twice in one video. Also check by hand:
- Every UI label the narration names appears on screen (exploration) or in the translation files. Grep each one.
- The narration makes sense when heard alone, start to finish, in each device's video.

Optionally film once without audio to debug the record.py: `python $S/edu_run.py training/<site>/<NN>_<slug> --lang <lang> --rehearse`, then read `.work/<device>/contact_*.png`.

### 7. Update the registry

Set the chapter's language status in chapters.md: `drafted` after the script, `produced` after step 8, `verified` only when the user signs off.

### 8. Produce: voice, record, sync, review

Read [recording.md](recording.md) first.

1. **Run** in the background. It takes about twice the video length per device, plus login and setup:
   ```bash
   PYTHONUTF8=1 python $S/edu_run.py training/<site>/<NN>_<slug> --lang <lang>
   ```
   - `--device desktop|mobile|both` films only some devices (default: the site's `devices`).
   - `--audio-only` rebuilds narration, subtitles and mux from the cached silent video. Only when the wording did not change.
   - `--no-review` skips the Gemini frame review. `--env` picks another environment.
2. **Exit code 3: login needs a person** (the remembered device or session expired, or MFA is SMS, push or SSO). Start `python $S/edu_login.py --site <site> --env <env>` in the background, tell the user a browser window is open for them to finish the login, wait for it to exit 0, and re-run. Never ask the user to paste a code or password into the chat.
3. **On failure**, read `.work/<device>/FAILED.png`, `network.log` and the error. Fix the locator, the wait or the script, then re-run; unchanged TTS clips are reused. After three failed attempts, stop and report.
4. **Review before reporting:**
   - Read the contact sheets, `.work/<device>/contact_*.png`, one labelled frame per DO, for **every** device. Check each frame shows what its DO says, and that no real-looking personal data is visible.
   - Read `.work/<device>/frame_review.json`. Look at every step Gemini flagged.
   - The sync check and the ASR check passed; the run fails otherwise.
   - Spot-listen: `ffmpeg -ss <cue> -t 8 -i <mp4> -vn spot.wav` around two or three cues per device.
5. **Commit gates** (when the site folder is in a git repo). `git lfs status` lists every mp4 as `LFS`. `git ls-files training | grep -E '/\.(cache|work|explore)/|/voices/|\.env$'` prints nothing.
6. **Report:**
   - every video's path, length and size
   - the page list and the narration minutes
   - anything that looked wrong on screen
   - **product findings** (bugs, confusing labels, dead ends, with file:line or URL), reported but never narrated
   - **open questions**
   - which skill or site files were updated

## Rules

- **Never narrate from memory.** Every label comes from what step 2 read on screen or in code.
- **Never demonstrate a bug.** Route around it and report it.
- **Never invent a workaround or support process.** Ask the user.
- **A safe environment.** Record against staging, a demo tenant or a local copy. A recording types into the site and creates real records. Production only with the user's explicit opt-in in site.yaml and `--allow-production`.
- **Demo data only.** A demo account; obviously fictional names and content. Never type or show a real person's details. Videos are published.
- **No real-world side effects on camera.** No payments, no messages or invitations to real people, no deleting real data, no starting a real microphone or camera recording. Show the confirmation dialog, then cancel.
- **Secrets** (credentials, TOTP secrets, API keys, the session file) are never printed, logged, pasted into chat or committed. They live in `.env` or the environment.
- **Login is automated only with the site owner's consent**, on accounts made for this. Never automate around a CAPTCHA or any anti-bot control; a person does that step in the visible browser.
- **Git:** follow the host repo's branch and PR conventions. Media goes through LFS. Never commit `.cache/`, `.work/`, `.explore/`, `voices/`, `.env` or session files.

## Anti-patterns

- Writing `SAY:` or any other prefix on narration lines. Narration is plain text lines.
- Starting a narration line with `[`, because `.timed.md` puts cues there.
- Quoting or bolding labels in narration. The voice reads plain words, and the subtitles show the text exactly as written.
- Hard-coding a label string in record.py instead of `r.t(...)` or a test id.
- Quoting a label that differs between the desktop and mobile layouts. Describe the control instead ("the consent field").
- Editing narration and then running `--audio-only`. The clip lengths changed, so re-record.
- Writing a site's URL, vocabulary, selectors or quirks into the skill's files instead of `training/<site>/`.
