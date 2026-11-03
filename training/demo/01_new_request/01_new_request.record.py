"""Recording script for the demo site's chapter 01, How to open a new request. Every language, both devices.

    python .claude/skills/training-videos/scripts/edu_run.py training/demo/01_new_request --lang he

Locators are test ids from the fixture's HTML, or labels from its locale files through r.t().
No literal UI text: the same script films the Hebrew and the English UI.
"""

# Fictional content typed on camera, per UI language.
SUBJECT = {'he': 'המדפסת בקומה השנייה לא מדפיסה', 'en': 'The second-floor printer does not print'}
DETAILS = {'he': 'המדפסת ליד חדר הישיבות מציגה נורה אדומה מהבוקר.',
           'en': 'The printer next to the meeting room has shown a red light since this morning.'}


def setup(r):
    return None


def record(r, ctx):
    page = r.start()
    ui = r.lang.ui_locale

    with r.step('0.1'):
        pass

    # Page 1: Dashboard
    with r.step('1.1'):
        r.hover(page.get_by_test_id('request-list'))
    if r.has('1.2'):
        with r.step('1.2'):
            r.click(page.get_by_test_id('new-request'))
            page.wait_for_url('**/request.html')
    if r.has('1.3'):
        with r.step('1.3'):
            r.click(page.get_by_test_id('fab-new-request'))
            page.wait_for_url('**/request.html')

    # Page 2: the form
    with r.step('2.1'):
        page.get_by_test_id('request-subject').wait_for()
    with r.step('2.2'):
        r.type_text(page.get_by_test_id('request-subject'), SUBJECT.get(ui, SUBJECT['en']))
    with r.step('2.3'):
        r.select(page.get_by_test_id('request-category'), value='facilities')
    with r.step('2.4'):
        r.click(page.get_by_test_id('request-urgent'))
    with r.step('2.5'):
        r.type_text(page.get_by_test_id('request-details'), DETAILS.get(ui, DETAILS['en']))
    with r.step('2.6'):
        r.click(page.get_by_test_id('request-submit'))
        page.wait_for_url('**/dashboard.html')

    # Page 3: back on the dashboard
    with r.step('3.1'):
        r.wait_text(r.t('request.saved'), fail_texts=(r.t('request.required'),))
        page.get_by_test_id('request-item').first.wait_for()

    # Summary
    with r.step('4.1'):
        r.hover(page.get_by_test_id('request-item').first)


def cleanup(r, ctx):
    pass
