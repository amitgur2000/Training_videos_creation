# Chapter style guide

Every chapter script (`training/<site>/<NN>_<slug>/<lang>/<NN>_<slug>.md`) follows this file, for every site. The pipeline parses chapters mechanically, so the format section is a contract, not a suggestion. `scripts/edu_check_chapter.py` enforces the mechanical parts.

## Format contract

Chapters are Markdown, UTF-8, with LF line endings. Narration is in the chapter's language. Everything else (headings may be in either language, `>` lines in English) is for people and tools. Every line is exactly one of these kinds:

| Line starts with | Meaning | Spoken? |
|---|---|---|
| `# ` | Chapter title. One per file, the first line. | no |
| `## ` | A page change: a new page, tab, section, dialog or menu. | no |
| `> ` | For people and tools: the metadata block, recorder notes, and `DO` steps. | no |
| blank | Separator. | no |
| anything else | **Narration.** Spoken exactly as written, and shown as the subtitle text. | **yes** |

### Skeleton

```md
# פרק 1: איך פותחים בקשה חדשה

> TITLE (EN): How to open a new request
> LANGUAGE: he
> AUDIENCE: Employees
> START PAGE: /dashboard
> PREREQUISITES: The demo account on staging. Type only fictional content.
> SOURCE COMMIT: bad45b8          (or: live 2026-11-03, for a site explored without its code)
> SOURCES: src/pages/Dashboard.tsx, src/pages/NewRequest.tsx   (or the URLs walked)
> ESTIMATED NARRATION: about 2 minutes

## Introduction

> DO 0.1: Show the dashboard. Do not click anything.

הסרטון הזה מיועד לכל מי שצריך עזרה מצוות המחשוב, התחזוקה או משאבי אנוש.

## Page 1: Dashboard

> DO 1.1 [desktop]: Click the New request button at the top.

כדי לפתוח בקשה חדשה, לוחצים על הכפתור בקשה חדשה בראש המסך.

> DO 1.2 [mobile]: Tap the round plus button at the bottom.

בטלפון, הכפתור העגול בתחתית המסך פותח בקשה חדשה.
```

The full example is `training/demo/01_new_request/he/01_new_request.md`.

### Headings

- The first `##` is `## Introduction`. Pages are then numbered: `## Page 1: <where you are>`.
- A dialog or menu on top of a page is `## Popup <page><letter>: <what it is>`. When it closes, resume with `## Page <n>, continued: <where you are>`.
- The last `##` is `## Summary`. Its DO ids use the next page number.
- The heading says where the viewer is, in the app's own words.

### DO steps

- Format: `> DO <page>.<step>: <instruction>`. Ids are `0.x` in the Introduction and `<page>.x` after that. They are unique and in order, and popups continue their page's numbering.
- **Device tags.** `> DO 3.2 [desktop]: ...` or `> DO 3.2 [mobile]: ...` is a step that exists in one video only, and so does the narration under it. Untagged steps are in both videos. Use a tag only where the UI really differs: a control that exists in one layout, or a different way to reach the same place. Tagged ids still follow the global order.
- Each step is one physical action or one thing to show. Name the control by its visible label and say where it is.
- **Every DO must be automatable:** click or tap, hover, type, press a key, choose from a list, or wait for something to appear. "Point at X" means hover, which shows as a highlight ring on mobile.
- A `DO` with no narration after it is a silent action.
- Every action the narration describes has a `DO` just before it.

### Recorder notes

Anything else the recorder must know goes on a `>` line starting with `NOTE:`. Cleanup goes in the metadata block as `> AFTER RECORDING:`.

## Why the format looks like this

- **Every narration line becomes one TTS clip and one timing unit.** It starts at its step's cue, or right after the previous line of the same step.
- **Subtitles use the script's exact wording,** at most 2 rows of 42 characters on desktop and 32 on mobile.
- **Each `> DO n.m:` line is one recorded step,** held on screen for exactly as long as its narration lasts.
- So: narration has no prefix, never starts with `[` (`.timed.md` puts cues there), and is one short line per on-screen moment. Put the words where their picture is.

## Writing narration

### For the voice and the subtitles (every language)

- One or two short sentences per line: 25 words or fewer as a rule, 45 at most.
- Plain words only. No `& / % ( ) [ ] * _ # @ | < > = "`, no quote marks of any kind around labels, no bullets, no numbered lists, no emoji.
- Speak UI labels naturally, exactly as the screen shows them, without quotes.
- Never read out an email address, a URL, an ID or a phone number.
- Small numbers as words where natural. Durations and option values may stay as the screen shows them ("90 דקות", "30 days").
- Write abbreviations out in full. The voice may read them letter by letter.
- The product's name is written as `product.spoken_name` in site.yaml says, even inside narration in another script (a Latin name stays Latin in Hebrew). Check the first clips that contain it; if the voice says it wrongly, change `spoken_name` to a spelling the voice reads right.

### Hebrew (and other right-to-left languages)

- No niqqud. No gershayim abbreviations (`ד"ר`, `וכו'`, `ש"ח`): write `דוקטור`, `וכן הלאה`, `שקלים`. The checker rejects quote marks.
- No bidi control characters; the subtitles add their own direction marks.
- Gender-neutral second person, plural: `לוחצים`, `בוחרים`, `אפשר`, `שימו לב`. When the UI uses slash forms (`משתמש/ת`), speak a natural form in narration (`משתמש`, `משתמשת`), never the slash.
- Latin product terms inside Hebrew (acronyms, feature names) are fine when the screen shows them; keep them few per line, because each one switches the voice's language.
- The Summary opens with `לסיכום` once.

### Voice

- Talk to the viewer as a calm, friendly colleague showing them the system (the narrator's persona in narrator.yaml says the same to the voice).
- Use the words the audience uses (`product.vocabulary` in site.yaml), not the developers' words.
- Never say recording-setup words in narration: no "test user", "demo account" or "the record we prepared". Say "this customer", "this order". The site's `narration.forbidden_words` are checked too.
- Keep technology words out: no API, backend, token, cache, database.
- For every action, say **what** it does, **when** to use it, and **what happens next**.
- Warn about consequences that matter to the viewer: what cannot be undone, who gets notified, what costs money, what a setting changes later.
- Narration must fit **both** videos unless its step is device-tagged. Don't say "on the left" or "click" where the phone shows something else. "Choose" and "open" fit both.

### Staying in sync with the screen

- Narrate what is on screen now, or the step about to happen. Never describe a page before the video is on it.
- Do not narrate over a page load. Put the load in its own `DO` ("Wait for the form to load").
- Go forward only.

## Context rules

- **Open with the big picture.** Two to four lines: who the chapter is for, what problem it solves in the viewer's day, and where it sits in the product.
- **Connect beyond the screen** where it is true and useful (product-context.md), in one sentence.
- **Finish the task on screen before the Summary**, and wait for its result: the toast, the updated list, the closed dialog.
- **Summary:** the opener once, then one line per key action, then related chapters by title, never by number.
- **Facts the code does not show** (for example "a change applies from the next meeting") are narrated only when the user supplied them. Record each one in product-context.md with its date.

## Honesty and privacy

- Describe only behaviour confirmed on the recorded site, in its code at `source.ref`, or supplied by the user.
- If the flow has a bug, route around it and report it. Do not teach it, and do not mention it in narration.
- Type only obviously fictional names. Videos are committed, and everything on screen is published.
- No real-world side effects on camera: no payments, no messages to real people, no deleting real data, no starting a microphone or camera. Show the confirmation dialog, then cancel.

## Learnings from feedback

Rules added by `fix` runs. Each one is dated, with a one-line why. When a learning changes an earlier rule in this file, edit that rule instead of appending a contradiction.

The following learnings come from earlier sites, where they were learned. They hold for every site:

- **2026-09-28: Never say the same sentence twice.** Why: a cache bug once made a video repeat 14 sentences. Rule: a sentence is said once per video; if two places need the idea, refer back. Both the checker and the TTS stage enforce it.
- **2026-09-28: The summary opener is said once.** Why: it was heard twice. Rule: only the Summary's first line opens with it.
- **2026-09-28: Give every control on the walked screens one line.** Why: a happy-path-only video skipped the controls around it. Rule: list each walked page's visible controls from the code, and give each one a short line, even when the video doesn't click it. Leave out only broken flows and internal-only controls.
- **2026-09-28: Avoid words whose sound depends on meaning.** Why: the voice guesses wrong, and there is no lexicon. Rule: re-word.
- **2026-10-02: A slip in one clip is fixed in that line only.** Why: one clip mispronounced a word that ten others said correctly. Rule: re-word just that line, and keep the clips the user already heard.
- **2026-09-28: End the video by finishing the task.**
