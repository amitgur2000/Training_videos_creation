"""Recording script for chapter <NN>, <Title (EN)>. Every language, every device.

    PYTHONUTF8=1 python .claude/skills/training-videos/scripts/edu_run.py training/<site>/<NN>_<slug> --lang <lang>

One `with r.step('n.m'):` per `> DO n.m:` line of the chapter script, in order. Device-tagged steps
are guarded with `if r.has('n.m'):`. Locators: test ids first, then roles with labels from r.t().
No literal UI text, so the same script films every UI language. API: recording.md, "The record script".
"""

# Fictional content typed on camera, per UI locale. Never a real person's details.
TYPED = {
    'en': {'name': 'Dana Example'},
}


def setup(r):
    """Off camera, on r.setup_page (logged in). Prepare data; return whatever record() needs."""
    return {'typed': TYPED.get(r.lang.ui_locale, TYPED['en'])}


def record(r, ctx):
    page = r.start()                     # the site's start_page; r.start('/path') for another

    # Introduction
    with r.step('0.1'):
        pass

    # Page 1: <where you are>
    with r.step('1.1'):
        r.hover(page.get_by_test_id('<test-id>'))
    if r.has('1.2'):                     # [desktop]
        with r.step('1.2'):
            r.click(page.get_by_test_id('<desktop-button>'))
    if r.has('1.3'):                     # [mobile]
        with r.step('1.3'):
            r.click(page.get_by_role('button', name=r.t('<ns:key>')))


def cleanup(r, ctx):
    """Off camera, after the last step: delete what setup() or the chapter created, when the site allows."""
