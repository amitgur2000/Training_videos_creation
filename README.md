# Training_videos_creation

A Claude Code skill that produces narrated training videos for any web site: [.claude/skills/training-videos/](.claude/skills/training-videos/SKILL.md).

You give it the site (a URL, and optionally its source code) and the chapters you want to teach. For each chapter it:

1. explores the site (and reads its code when available) and writes a script: what to click, and what the narrator says;
2. voices every line with Gemini TTS in the language you choose (Hebrew is well tuned) and the narrator voice you picked from samples;
3. logs in by itself, including TOTP or email MFA (SMS, push or SSO: a person logs in once in a visible browser);
4. records the site headless with Playwright, desktop 1920x1080 and a phone in portrait 1080x1920, holding each step on screen for exactly its audio;
5. adds subtitles and checks the result (each clip says its line; each screenshot matches its narration; the video is in sync).

## Quick start

```bash
python -m pip install -r .claude/skills/training-videos/scripts/requirements.txt
python -m playwright install chromium
# ffmpeg on PATH; GEMINI_API_KEY in the environment or a .env file
```

Then, in Claude Code:

```
/training-videos --site acme --mode init                     # profile, login, curriculum, narrator voice
/training-videos --site acme --chapter "Create an order"     # script, voice, record, review
/training-videos --site acme --mode voices --lang he         # sample and choose a narrator
```

Each site lives in `training/<site>/`: `site.yaml` (URLs, login, languages, devices), `chapters.md` (the curriculum) and one folder per chapter with its scripts and videos (mp4s through Git LFS).

## Try it on the built-in demo

`training/demo/` is a complete example against a small fake app shipped with the skill (login, TOTP MFA, Hebrew/English UI, desktop and mobile layouts):

```bash
python -m http.server 8765 --directory .claude/skills/training-videos/scripts/tests/fixture_site
cp training/demo/.env.example training/demo/.env          # fixture credentials, and add GEMINI_API_KEY
PYTHONUTF8=1 python .claude/skills/training-videos/scripts/edu_run.py training/demo/01_new_request --lang he --rehearse
PYTHONUTF8=1 python .claude/skills/training-videos/scripts/edu_run.py training/demo/01_new_request --lang he
```

`--rehearse` films without audio and needs no API key.
