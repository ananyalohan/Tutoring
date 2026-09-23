# LVA Tutor Session Reporting

A small web app that replaces LVA Essex/Passaic's paper *Student Monthly Attendance & Achievement Form*.
Tutors log each session as it happens; staff get the monthly report computed for them.

## Running it

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app seed-demo      # creates instance/tutoring.sqlite with demo data
flask --app app run
```

Open http://127.0.0.1:5000 and log in with password `password123` as:

| Role  | Email               | What to look at |
|-------|---------------------|-----------------|
| Staff | `staff@lvaep.org`   | Monthly report, month navigation, CSV export, close month, Tutors & students |
| Tutor | `maria@example.com` | Log a session, edit recent entries, click a student for the year grid & achievements |

(`james@example.com` and `priya@example.com` are also tutors.) Use `flask --app app init-db` for an empty database.

Tests: `pytest` (24 tests, covering validation, permissions, sign-up, report totals, the year grid, and month locking).

### Live demo / deploying

The repo includes a [`render.yaml`](render.yaml) blueprint: on [Render](https://render.com), choose **New → Blueprint** and pick this repo. It runs under gunicorn with `DEMO_MODE=1`, which adds one-click demo logins to the login page and seeds sample data on startup. Free-tier storage is temporary, so the demo resets whenever the service restarts. That's intentional for a public demo. A real deployment would set `DATABASE_PATH` to a persistent disk and leave `DEMO_MODE` off.

## The problem with the current workflow

The paper form is one sheet **per student, per tutor, per fiscal year**: a 31×12 grid of hours, absence codes,
an achievements checklist, and a "stopped" box. To produce a monthly report, someone at the office has to
collect every tutor's sheet and add up one column from each by hand. The main pain points:

- **Aggregation is manual.** Monthly totals are the thing staff actually need, and the form doesn't give them.
- **Late or missing data is invisible.** Staff can't tell who hasn't reported until they chase sheets.
- **No validation.** A cell can hold anything, and the form has no way to know a date is wrong or a tutor wasn't assigned yet.
- **Urgent information travels slowly.** "Stopped tutoring… notify the office ASAP" relies on the tutor making a separate call or email.

## What I built

**Tutors**
- **Self sign-up** at `/signup` (linked from the login page). A new tutor lands on a friendly "waiting to be matched" dashboard and can't see any student data until staff assign them a student.
- One quick-entry form: student, date (defaults to today), *what happened* (held / tutor absent / student absent / holiday), hours, and optional notes. After saving, the same student stays selected so backfilling several sessions is fast.
- "My students" cards showing hours this month and the date of the last entry.
- A list of recent entries, each editable or deletable until staff close that month.
- A per-student page with the **same 31-day × 12-month grid as the paper form**, generated from their entries (printable), the achievements checklist, and a "Stopped tutoring?" form.

**Staff**
- **Monthly report** (the landing page): total hours, sessions held, active pairs, and pairs with **nothing logged**. It shows a table by tutor → student with hours, held/TA/SA/H counts, last entry and tutor subtotals; a "Needs attention" box listing stopped pairings and missing entries; and achievements attained that month.
- **CSV export** of the report, for spreadsheets or grant reporting.
- **Close month**: locks a month so the numbers staff reported can't change afterwards. It can be reopened.
- **Tutors & students**: add tutors, add students, and create assignments (with site, day(s) and time(s) from the form's footer).
- Tutors with no active students, including anyone who just signed up, are listed under "Needs attention" with a link to assign them.

### How the paper form maps to the data model

| Paper form | App |
|---|---|
| Tutor / Student header, Site / Day(s) / Time(s) footer | `assignments` row (tutor, student, site, meeting_days, meeting_times, start_date) |
| One grid cell (day × month) | One `sessions` row: `(tutor, student, date)` with `hours` or a status of `TA`/`SA`/`H` |
| Monthly "Total" row | Computed with a `SUM` query, never stored |
| Achievements checklist A–D | `achievements` row with a goal code (`A1`…`D4`) and the date attained |
| "E. Other(s)" | `achievements` row with code `E` and free text |
| STOPPED box + reason | `assignments.end_date` + `end_reason`; appears on the staff report immediately |

Totals are always derived from the session rows rather than stored, so they can't drift out of sync.

## Assumptions

- **One entry per tutor, per student, per day**, mirroring the one-box-per-day grid. If a pair meets twice in a day, the tutor enters the combined hours. The app rejects a duplicate and points the tutor to the existing entry.
- **Tutors record TA/SA/H themselves.** The form labels these codes "For Internal Use Only". I read that as "these are the office's codes" rather than "tutors must not use them". Recording a cancelled session gives staff attendance data they don't get today. This is easy to restrict to staff if I've read it wrong.
- **Hours are 0.25–8 per session, in quarter-hour steps.** No future dates. A session must fall within an active assignment, so a tutor can't log before they were assigned or after the pairing stopped.
- **The fiscal year is July–June**, as the form's column order shows. The year grid follows that.
- **Tutors can sign up themselves; staff control access.** Anyone can create a *tutor* account (never a staff account), but an account on its own grants no access to student data. Visibility comes only from an assignment that staff create. So open sign-up saves the office from typing in accounts, without adding a vetting risk. Staff can still add tutors directly. If LVA wants tighter control, an "approved" flag or an invite code would be a small addition.
- **"Notify the office" can be an in-app alert.** Stopped pairings appear on the report straight away. Email notifications would be a natural next step.
- **Starred (*) goals** are flagged in the UI, but I didn't guess at what the star means (probably federally reportable outcomes needing documentation), so no extra rules are attached.
- **Achievements belong to the student, not the pairing.** A goal is attained once, whoever the tutor is. Any tutor linked to the student, or staff, can record one.

## Key decisions and trade-offs

- **Flask + SQLite, server-rendered HTML.** The users are volunteer tutors (often not very technical) and a small office. A plain web app works on any phone or laptop with nothing to install. It needs one process and one file-based database, and it's easy for a small nonprofit to host. A single-page app would add build tooling without making anything better for these users.
- **Raw SQL rather than an ORM.** The interesting logic is aggregation, and the report query reads directly as "sum held hours per assignment for this month". It's in `app/reports.py`. The schema is in one file (`app/schema.sql`) with comments tying each table to the paper form.
- **Validation is split in two.** `validate_session_form` handles pure field checks and is unit-tested without a database. `check_session_rules` handles rules that need data: assignment, closed month, duplicates.
- **Logging per session, not a monthly grid to fill in.** The grid is familiar, but filling it in is exactly the month-end batch job this replaces. Logging each session as it happens spreads the work out and means the staff report is live. The grid is still available as a read-only, printable view, for anyone who wants the familiar layout or needs a paper record.
- **Month locking** matters once numbers have gone into a funder report. Without it, a tutor's late edit would silently change a figure that was already submitted.
- **Security basics:** hashed passwords, session auth, role checks on every route, tutors can only see and edit their own students and sessions, CSRF tokens on every form, parameterised SQL throughout.

## Project layout

```
app/
  __init__.py      app factory, CLI commands (init-db, seed-demo)
  schema.sql       database schema
  constants.py     goals, statuses, fiscal-year helpers (from the paper form)
  auth.py          login/logout, role decorators, CSRF
  session_log.py   session validation + save
  reports.py       monthly report, CSV, year grid queries
  tutor.py         tutor routes (log / edit / delete sessions)
  students.py      student page, achievements, stop tutoring
  staff.py         staff routes (report, CSV, close month, people & assignments)
  seed.py          demo data
  templates/, static/
tests/             pytest suite
```

## What I'd do next

- **Reminders:** a weekly email to tutors with nothing logged, and an email to the office when a pairing is stopped.
- **Password reset and email verification** for sign-ups.
- **Staff corrections to tutor entries, with an audit log** of who changed what. Right now only tutors edit sessions.
- **Grant-specific exports**, once I know what funders ask for (e.g. hours per student per quarter, and starred outcomes).
- **Deployment:** a production WSGI server, `SECRET_KEY` from the environment, and scheduled backups of the SQLite file. Or Postgres, if the program grows beyond one office.
- **Archiving students** and editing assignments (site/schedule changes) from the UI.
