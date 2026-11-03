# The site profile: training/<site>/site.yaml

Everything the skill knows about one site, and the only place product facts may live. Start from [templates/site.yaml](templates/site.yaml); a complete working example is `training/demo/site.yaml`. Unknown keys are ignored; every key has a default except `environments`.

Login keys are in [login.md](login.md), and the narrator (voice and persona) is in `narrator.yaml` ([voices.md](voices.md)).

## Product and audience

```yaml
product:
  name: Acme Portal              # as written on screen
  spoken_name: Acme Portal       # how the narrator says it; the ASR check expects this spelling
  audience: Store managers who order stock weekly
  vocabulary:                    # the audience's words for the product's things; narration uses them
    order: never "purchase request"
    store: the branch the manager runs
default_lang: he                 # narration language when --lang is not given
timezone: Asia/Jerusalem         # the browser's timezone: dates and times on screen
```

## Environments

```yaml
environments:
  staging: {url: https://staging.acme.example, production: false}
  demo:    {url: https://demo.acme.example}
  prod:    {url: https://acme.example, production: true}
default_env: staging             # default: the first non-production environment
allow_production_recording: false
```

A recording **types into the site**: it creates records, sends forms, changes settings. Record against staging, a demo tenant or a local copy, as a demo account with fictional data. An environment marked `production: true` is refused unless `allow_production_recording: true` is set here (the site owner's decision, never the agent's) **and** the run passes `--allow-production`.

## Devices

```yaml
devices: [desktop, mobile]       # which videos every chapter gets; either or both
device_profiles:                 # optional overrides of the built-in profiles
  desktop: {viewport: {width: 1536, height: 864}, scale: 1.25, video: [1920, 1080]}
  mobile:  {viewport: {width: 412, height: 732}, scale: 2.625, video: [1080, 1920]}
```

The built-in desktop profile is 1536x864 CSS pixels at scale 1.25: a 1920x1080 video. Mobile is a Pixel 7 (touch, mobile user agent), 412x732 at 2.625: a 1080x1920 portrait video. If you override them, keep `viewport x scale = video`, or the picture is letterboxed.

## Pages and selectors

```yaml
start_page: /dashboard           # where chapters start, normally where the app lands after login
test_id_attribute: data-testid   # what page.get_by_test_id() looks for (data-test, data-qa, data-cy...)
wait_for_hidden:                 # loading indicators: a step's cue waits until none is visible
  - '[aria-busy="true"]'
  - .MuiSkeleton-root
  - .skeleton
  - .spinner
  - '[role="progressbar"]'
dismiss_off_camera:              # clicked before filming if visible: cookie banners, promos, tours
  - '#onetrust-accept-btn-handler'
  - 'button:has-text("Got it")'
```

`wait_for_hidden` matters. A step's narration starts at its cue, and the cue must show real content, not a skeleton. Add the site's own spinner or skeleton class when exploration shows one. A permanent progress bar (an upload meter, for example) must not be listed, or every step waits 10 seconds.

## The UI language

```yaml
ui_language:
  locales: [he, en]              # the UI languages the site has
  fallback: en                   # the UI used for a narration language the site lacks
  set_by: localStorage           # localStorage | cookie | query | none
  key: app.locale                # the localStorage key, cookie name or query parameter
  assert_html_lang: true         # fail the run unless <html lang dir> matches before filming
```

The recorder sets the language **before the first paint**, so the first frame is already in the right language. `set_by: none` means the account's own setting decides: use a demo account per language, or switch it in a chapter's `setup()`. Find the mechanism in the code (search for `localStorage.setItem` near the i18n setup, or the language switcher), or switch the language by hand once and watch DevTools, Application tab.

A site's stored language may also be written back to the user's profile on the server (emails then arrive in that language). That is harmless on a demo account; mention it in product-context.md when you see it.

## Source code (optional)

```yaml
source:
  repo: ../acme-web              # relative to this folder, or absolute
  ref: origin/main               # read with git show <ref>:<path>; fetch first
  i18n:
    pattern: src/locales/{locale}/{ns}.json   # or public/i18n/{locale}.json (no namespace)
```

With source access, labels come from the translation files through `r.t('ns:key')` (or `r.t('key')` without namespaces), and chapters cite file paths in `SOURCES`. Without it, the live site is the source: `edu_explore.py --capture-labels` stores on-screen strings in `labels/<locale>.json`, and `r.t()` reads those.

## Narration

```yaml
narration:
  forbidden_words: [ticket, beta, internal, staging]   # never said; the checker fails on them
```

The checker always rejects words that reveal the recording setup (test or demo account, test user, fake data). Add words the audience must not hear: internal code names, deprecated names, a competitor.

## Session

```yaml
session_dir: ~/.training_videos/acme   # where the login session is saved; default ~/.training_videos/<site>
```

Keep it outside every repo.

## Secrets: training/<site>/.env

Not part of site.yaml. Git-ignored. `KEY=value` lines, read after the process environment and before the repo-root `.env`:

```bash
SITE_USER=demo@acme.example
SITE_PASS=...
SITE_TOTP_SECRET=...
GEMINI_API_KEY=...
```
