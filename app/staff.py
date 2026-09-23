from datetime import date

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from .auth import role_required
from .db import get_db, is_month_closed
from .reports import monthly_report, monthly_report_csv
from .tutor import today

bp = Blueprint("staff", __name__, url_prefix="/staff")


def month_arg():
    """?month=YYYY-MM, defaulting to the current month."""
    month = request.args.get("month") or today().isoformat()[:7]
    try:
        date.fromisoformat(month + "-01")
    except ValueError:
        abort(400, "month must look like 2026-09")
    return month


def shift_month(month: str, delta: int) -> str:
    y, m = map(int, month.split("-"))
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


@bp.route("/reports")
@role_required("staff")
def report():
    month = month_arg()
    db = get_db()
    closed = db.execute(
        "SELECT c.*, u.name FROM closed_months c JOIN users u ON u.id = c.closed_by WHERE month = ?", (month,)
    ).fetchone()
    # Includes tutors who signed up themselves and are waiting to be matched.
    unassigned = db.execute(
        """SELECT name, email FROM users u WHERE role = 'tutor' AND NOT EXISTS
             (SELECT 1 FROM assignments a WHERE a.tutor_id = u.id AND a.end_date IS NULL)
           ORDER BY name"""
    ).fetchall()
    return render_template(
        "staff/report.html", r=monthly_report(db, month), closed=closed, unassigned=unassigned,
        prev_month=shift_month(month, -1), next_month=shift_month(month, 1),
        is_current=month == today().isoformat()[:7],
    )


@bp.route("/reports.csv")
@role_required("staff")
def report_csv():
    month = month_arg()
    body = monthly_report_csv(monthly_report(get_db(), month))
    return Response(body, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=tutoring-report-{month}.csv"})


@bp.route("/months/<month>/close", methods=["POST"])
@role_required("staff")
def close_month(month):
    db = get_db()
    if not is_month_closed(db, month):
        db.execute("INSERT INTO closed_months (month, closed_by) VALUES (?, ?)", (month, g.user["id"]))
        db.commit()
        flash(f"{month} closed. Tutors can no longer change sessions in this month.", "success")
    return redirect(url_for("staff.report", month=month))


@bp.route("/months/<month>/reopen", methods=["POST"])
@role_required("staff")
def reopen_month(month):
    db = get_db()
    db.execute("DELETE FROM closed_months WHERE month = ?", (month,))
    db.commit()
    flash(f"{month} reopened for edits.", "success")
    return redirect(url_for("staff.report", month=month))


# --- People & assignments -------------------------------------------------

@bp.route("/people")
@role_required("staff")
def people():
    db = get_db()
    return render_template(
        "staff/people.html",
        tutors=db.execute(
            """SELECT u.*, (SELECT COUNT(*) FROM assignments a WHERE a.tutor_id = u.id AND a.end_date IS NULL) AS active
               FROM users u WHERE role = 'tutor' ORDER BY name""").fetchall(),
        students=db.execute("SELECT * FROM students ORDER BY name").fetchall(),
        assignments=db.execute(
            """SELECT a.*, u.name AS tutor, s.name AS student FROM assignments a
               JOIN users u ON u.id = a.tutor_id JOIN students s ON s.id = a.student_id
               ORDER BY a.end_date IS NOT NULL, u.name, s.name""").fetchall(),
        today=today().isoformat(),
    )


@bp.route("/tutors", methods=["POST"])
@role_required("staff")
def add_tutor():
    db = get_db()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not name or "@" not in email or len(password) < 8:
        flash("Tutor needs a name, a valid email and a temporary password of at least 8 characters.", "error")
    elif db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        flash("An account with that email already exists.", "error")
    else:
        db.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'tutor')",
                   (name, email, generate_password_hash(password)))
        db.commit()
        flash(f"Added tutor {name}.", "success")
    return redirect(url_for("staff.people"))


@bp.route("/students", methods=["POST"])
@role_required("staff")
def add_student():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Student name is required.", "error")
    else:
        db = get_db()
        db.execute("INSERT INTO students (name) VALUES (?)", (name,))
        db.commit()
        flash(f"Added student {name}.", "success")
    return redirect(url_for("staff.people"))


@bp.route("/assignments", methods=["POST"])
@role_required("staff")
def add_assignment():
    db = get_db()
    f = request.form
    try:
        tutor_id, student_id = int(f.get("tutor_id", "")), int(f.get("student_id", ""))
        start = date.fromisoformat(f.get("start_date", "")).isoformat()
    except ValueError:
        flash("Choose a tutor, a student and a start date.", "error")
        return redirect(url_for("staff.people"))

    if not db.execute("SELECT 1 FROM users WHERE id = ? AND role = 'tutor'", (tutor_id,)).fetchone() \
            or not db.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone():
        flash("Unknown tutor or student.", "error")
    elif db.execute("SELECT 1 FROM assignments WHERE tutor_id = ? AND student_id = ? AND end_date IS NULL",
                    (tutor_id, student_id)).fetchone():
        flash("That tutor is already assigned to that student.", "error")
    else:
        db.execute(
            """INSERT INTO assignments (tutor_id, student_id, site, meeting_days, meeting_times, start_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tutor_id, student_id, f.get("site", "").strip(), f.get("meeting_days", "").strip(),
             f.get("meeting_times", "").strip(), start),
        )
        db.commit()
        flash("Assignment created.", "success")
    return redirect(url_for("staff.people"))
