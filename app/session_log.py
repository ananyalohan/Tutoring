"""Validation and persistence for tutoring session records.

Split in two so the pure checks (validate_session_form) can be tested without
a database, and the rules that need data (check_session_rules) sit together.
"""
from datetime import date

from .constants import HOURS_STEP, MAX_HOURS_PER_SESSION, STATUSES
from .db import is_month_closed


def validate_session_form(form, today: date):
    """Parse a submitted session form. Returns (data, errors)."""
    errors = []
    data = {"notes": form.get("notes", "").strip()}

    try:
        data["student_id"] = int(form.get("student_id", ""))
    except ValueError:
        data["student_id"] = None
        errors.append("Choose a student.")

    try:
        d = date.fromisoformat(form.get("session_date", ""))
        if d > today:
            errors.append("Session date can't be in the future.")
        data["session_date"] = d.isoformat()
    except ValueError:
        data["session_date"] = None
        errors.append("Enter a valid date.")

    status = form.get("status", "held")
    if status not in STATUSES:
        errors.append("Choose whether the session was held.")
    data["status"] = status

    if status == "held":
        try:
            hours = float(form.get("hours", ""))
            if hours <= 0 or hours > MAX_HOURS_PER_SESSION:
                errors.append(f"Hours must be between 0.25 and {MAX_HOURS_PER_SESSION}.")
            elif (hours / HOURS_STEP) != int(hours / HOURS_STEP):
                errors.append("Hours must be in quarter-hour steps (e.g. 1.25, 1.5).")
            data["hours"] = hours
        except ValueError:
            data["hours"] = None
            errors.append("Enter the number of hours tutored.")
    else:
        # Absences and holidays are recorded with zero hours.
        data["hours"] = 0

    if len(data["notes"]) > 500:
        errors.append("Notes must be 500 characters or fewer.")

    return data, errors


def active_assignment(db, tutor_id, student_id, on_date: str):
    """The assignment that covers this tutor/student on a given day, if any."""
    return db.execute(
        """SELECT * FROM assignments
           WHERE tutor_id = ? AND student_id = ? AND start_date <= ?
             AND (end_date IS NULL OR end_date >= ?)""",
        (tutor_id, student_id, on_date, on_date),
    ).fetchone()


def check_session_rules(db, tutor_id, data, existing_id=None):
    """Rules that need the database. Returns a list of error messages."""
    errors = []
    if not active_assignment(db, tutor_id, data["student_id"], data["session_date"]):
        errors.append("You weren't assigned to this student on that date.")
    if is_month_closed(db, data["session_date"][:7]):
        errors.append("That month's report has been closed by staff. Contact the office to make changes.")
    dup = db.execute(
        "SELECT id FROM sessions WHERE tutor_id = ? AND student_id = ? AND session_date = ? AND id IS NOT ?",
        (tutor_id, data["student_id"], data["session_date"], existing_id),
    ).fetchone()
    if dup:
        errors.append("You already logged a session with this student on that date. Edit that entry instead.")
    return errors


def save_session(db, tutor_id, data, existing_id=None):
    if existing_id is None:
        db.execute(
            """INSERT INTO sessions (tutor_id, student_id, session_date, status, hours, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tutor_id, data["student_id"], data["session_date"], data["status"], data["hours"], data["notes"]),
        )
    else:
        db.execute(
            """UPDATE sessions SET student_id = ?, session_date = ?, status = ?, hours = ?, notes = ?,
                      updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND tutor_id = ?""",
            (data["student_id"], data["session_date"], data["status"], data["hours"], data["notes"],
             existing_id, tutor_id),
        )
    db.commit()
