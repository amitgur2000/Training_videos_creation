# UI map: where each screen lives in web_app_frontend

A pointer to the code, not a copy of it. Always read the files on `origin/main` before narrating: labels change. Runs add areas they explore.

**General**
- Repo: `../web_app_frontend` (Vite, React, MUI, react-router; `main` is the default branch).
- Routes are in `src/App.tsx`. Pages are in `src/pages/`; their components are in `src/components/<page>-page/`.
- Strings are in `src/locales/<he|en>/<namespace>.json`: `auth`, `billing`, `clients`, `common`, `errors`, `legal`, `onboarding`, `session`, `settings`, `summary`.
- `{client}` placeholders are filled per account role (`src/utils/roleWording.ts`). For a therapist, `clients:noun_therapist` is מטופל and `nounNeutral_therapist` is מטופל/ת. A coach account reads מתאמן instead.
- **Mobile layout below 900px** (`theme.breakpoints.down(900)`):
  - the sidebar becomes a drawer behind the menu button (`menu-toggle`)
  - many pages render separate mobile components with their own element ids and sometimes different wording
- Toasts come from react-hot-toast.
- Selectors: test ids are listed per screen below. Nav links are `nav-<path>` (`nav-dashboard`, `nav-client-management`, ...).

## Global

| Element | Test id / locator | Notes |
|---|---|---|
| Trial / plan banner close | button named `billing:banner.dismissAria` (סגור הודעה) | `TrialSubscriptionBanner.tsx`. Dismissed per tab in sessionStorage. The recorder closes it off camera. |
| Ask Myndz button | `chatbot-fab` | In the header on mobile, floating on desktop |
| Mobile menu | `menu-toggle` | Opens the drawer |

## Dashboard: `/dashboard`

`src/pages/DashboardPage.tsx`

| Element | Test id | Label (he) |
|---|---|---|
| Add patient card | `dashboard-add-patient` | `common:dashboard.addClient`, "הוספת מטופל/ת" |
| Summary without recording | `dashboard-manual-summary` | "סיכום ללא הקלטה" |
| Upload meeting | `dashboard-upload-meeting` | "העלאת פגישה" |
| Record meeting | `dashboard-record-meeting` | "הקלטת פגישה" |
| Manage patients | `dashboard-manage-patients` | "ניהול מטופלים" |

The four action cards are a row on desktop and a 2×2 grid on mobile.

## Add patient: `/add-new-patient`

- Page: `src/pages/AddNewPatientPage.tsx`. It holds the defaults, the validation and the submit.
- Desktop form: `src/components/add-new-patient-page/DesktopPatientIntakeForm.tsx`. Mobile form: `MobilePatientIntakeForm.tsx`.
- Title: "קליטת מטופל/ת חדש/ה" (`clients:intake.headerNewNeutral`).

| Field | Desktop id | Mobile id | Label (he), default |
|---|---|---|---|
| Treatment type | `#patient-treatment` | `#patient-treatment-mobile` | סוג טיפול: פרטני, זוגי, הדרכה. Default פרטני. |
| Activity status | `#patient-activity-status` | `#patient-activity-status-mobile` | סטאטוס פעילות. Default מטופל באופן פעיל. |
| Therapeutic approach (required) | `#patient-main-therapeutic-method` | `#main-therapeutic-method-mobile` | גישה טיפולית לסיכום הפגישה. Placeholder בחר גישה... Options come from `src/constants/summaryMethods.ts` (generated), and the option `data-value` is the method's `promptName`. Choosing CBT silently sets `analyze_meetings`. |
| First / last name (required) | test ids `patient-first-name`, `patient-last-name` | same test ids | שם פרטי, שם משפחה |
| Phone | `patient-phone` | same | מספר טלפון. Optional, 7 to 15 digits. |
| Gender | `patient-gender` (`-male`, `-female`, `-other`) | same | מגדר. Default אישה. |
| Organization | `#organization` | `#organization-mobile` | ארגון |
| Fee | `#session-fee` | `#hourly-rate-mobile` | Desktop סכום לפגישה בש"ח; mobile מחיר לשעה |
| Recording consent | `#recording-consent-status` (test id `recording-consent`) | `#recording-consent-mobile` | Desktop סטטוס אישור הקלטה (ההקלטה מאושרת / ההקלטה לא מאושרת); mobile אישור הקלטה (מאושר / נדחה). **Default: not approved.** |
| Recording retention | `#recording-retention-status` | `#recording-retention-mobile` | Desktop סטטוס שמירת הקלטה; mobile שמירת הקלטות. Default שמירה ללא הגבלת זמן. |
| Automatic session end | `#automatic-meeting-termination` | `#automatic-meeting-termination-mobile` | סיום פגישה אוטומטי: 50, 60, 75, 90 or 120 דקות. Default 90. Hint `clients:intake.autoEndSessionHint`. |
| Diagnosis | `#dsm-diagnosis` | `#dsm-diagnosis-mobile` | אבחון DSM/ICD (therapists only) |
| Risk | `#risk-level` | `#risk-level-mobile` | Desktop מסוכנות; mobile רמת סיכון. A details field becomes required when the value is not none. |
| Substance use | `#substance-use` | `#substance-use-mobile` | שימוש בחומרים מסוכנים |
| Goals | `#treatment-goal` | `#therapy-goals-mobile` | Desktop מטרות הטיפול; mobile מטרות טיפול |
| Therapist notes | `#therapist-notes` | `#therapist-notes-mobile` | הערות המטפל/ת |
| Dictation mic (every text field) | `voice-dictation-button` | same | הכתבה קולית (`common:voiceInput.start`) |
| Save / Cancel | `patient-submit` / `patient-cancel` | same | שמירה (shows שומר... while saving) / ביטול |

**After saving**
- **Success:** toast `clients:intake.createdSuccess` ("המטופל נוצר בהצלחה."), then the app goes to `/client-management`, not to the new patient.
- **Failure:** `clients:intake.createFailed`, or the API's message. The API answers **409 for a duplicate name with the same treatment type**.
- **Bug:** both auto-delete retention options save "30-days" on create (`AddNewPatientPage.tsx` around line 568). Avoid "מחיקה אוטומטית (לאחר יום אחד)" in videos.

## Patient list: `/client-management`

`src/pages/ClientManagementPage.tsx`, `src/components/client-management/PatientCard.tsx`

| Element | Test id | Notes |
|---|---|---|
| Add patient | `add-patient` (desktop header); round + button, aria `clients:list.addAria` (mobile) | |
| Search, active-only filter, count | `client-search`, `client-active-filter`, `client-count` | |
| Card / name / view | `patient-card`, `patient-card-name`, `patient-card-view` (הצג) | A card opens through its הצג button, not a click on the card |

## Patient page: `/patient/:id`

`src/pages/PatientPage.tsx`; mobile buttons are in `src/components/patient-page/MobileSessionFabs.tsx`

| Element | Test id | Label (he) |
|---|---|---|
| Tabs | `tab-sessions`, `tab-overview`, `tab-documents`, `tab-progress`, `tab-ai` | פגישות, מטופל/ת, מסמכים, דוחות, AI. The overview tab is the inline edit form, where the approach, consent and auto-end can be changed later. |
| Record meeting | `patient-record` | הקלטת פגישה. On mobile it is the round mic button on the פגישות tab. **Without consent it opens the consent dialog instead of the recorder.** |
| Consent dialog | role dialog | Title `clients:patient.recordingConsentRequired`. Buttons `clients:patient.approveRecording` (sets consent and starts recording) and `clients:patient.recordingNotApproved` (closes). |
| New meeting | `patient-new-session` | Desktop פגישה חדשה opens a dialog; on mobile it is the round + button, which opens a menu |
| New meeting options | `new-meeting-option-upload`, `-transcript`, `-typing` | העלאת קובץ שמע, העלאת תמלול, הקלדת תוכן פגישה (mobile: הקלדת תוכן ידני) |
| Manual content dialog | `manual-summary-modal`, `manual-summary-input`, `manual-summary-submit`, `manual-summary-cancel` | קליטת תוכן ידנית (`ManualMeetingContentModal.tsx`). The summary field has a dictation mic. |

The meetings list paints MUI skeletons (`.MuiSkeleton-root`) before its content. Wait for them to go before narrating.
