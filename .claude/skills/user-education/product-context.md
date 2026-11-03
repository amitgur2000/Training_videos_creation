# Product context

Background for writing chapters. **It is not a source of labels**: those come from the code (ui-map.md). Facts marked "(user, date)" were supplied by the user and have no code source. **TODO** marks something to confirm with the user before narrating it.

## The parts

**Myndz.** An AI system for therapists, coaches and supervisors that records meetings, transcribes them and writes structured summaries. Therapists use the web app (`staging.myndz.ai` / `app`), and there is also a mobile app shell. The UI exists in Hebrew (the default) and English.

**Patients (מטופלים).**
- Created from the dashboard card or from the patient list, through the intake form.
- A patient carries the settings that govern every meeting:
  - the therapeutic approach
  - recording consent
  - retention
  - automatic session end
- A patient cannot be deleted from the app; set "not actively in treatment" (לא מטופל באופן פעיל) to hide them from the active list.
- Chapters: 01 How to add a new patient.

**Therapeutic approach (גישה טיפולית לסיכום הפגישה).**
- The summary of each meeting is written according to the patient's approach. There are about 29 approaches (CBT, psychodynamic, ACT, DBT, EMDR, IFS, ...), defined in a registry generated from the "Myndz Prompts" document.
- It can be changed at any time from the patient's tab, and the change applies from the next meeting (user, 2026-10-04). No text in the UI says this.
- A single meeting can also be re-analysed by another approach from its summary page ("בחר גישה אחרת").

**Meetings (פגישות).** There are four ways to create one:
- record it live in the app (needs recording consent)
- upload an audio file: a recording made elsewhere, or the therapist summarising the meeting aloud (user, 2026-10-04)
- upload an external transcript (TXT, JSON, DOCX, PDF)
- type the content (with voice dictation)

Each one ends in a transcript and a summary.

**Recording consent (אישור הקלטה).**
- The therapist must ask the patient for consent before recording (user, 2026-10-04).
- The patient's consent setting defaults to not approved. Recording is blocked until it is approved, either in the patient's settings or from the dialog that appears when pressing record. Uploading and typing are not blocked.

**Automatic session end (סיום פגישה אוטומטי).** A recording stops by itself after 50 to 120 minutes (default 90), for when the therapist forgets to stop it (user, 2026-10-04). It can always be stopped earlier by hand.

**Retention.** Recordings are kept with no time limit by default, or auto-deleted. Retention deletes by the meeting's recorded date, so backdated uploads can be purged early. Don't narrate retention edge cases.

**Ask Myndz.** An AI chat about a patient's meetings (the `tab-ai` tab and the Ask Myndz button). TODO: a chapter of its own.
