# UI map: <Product>

A pointer to where each screen lives and how to reach its controls, not a copy of the site. Always re-read the live page (edu_explore.py) or the code at `source.ref` before narrating: labels change. Runs add the areas they explore.

**General**
- Source: <repo path and framework, or "none: live site only">.
- Routes: <where they are defined, or the URL scheme>.
- Strings: <translation files and namespaces, or labels/<locale>.json>.
- Mobile layout: <the breakpoint, and what changes below it: drawer menu, round buttons, other components>.
- Toasts and dialogs: <library or how they look>.
- Loading indicators: <selectors, also in site.yaml wait_for_hidden>.

## Global

| Element | Test id / locator | Notes |
|---|---|---|

## <Page name>: `<path>`

<Source file(s), if any.>

| Element | Desktop locator | Mobile locator | Label (<locale>) | Notes |
|---|---|---|---|---|

**After the main action**
- **Success:** <toast, redirect>.
- **Failure:** <messages, status codes>.
