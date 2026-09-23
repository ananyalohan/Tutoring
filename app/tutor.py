from datetime import date

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from .auth import role_required
from .constants import STATUSES
from .db import get_db, is_month_closed
from .reports import month_bounds
from .session_log import check_session_rules, save_session, validate_session_form

bp = Blueprint("tutor", __name__)


def today() -> date:
    # Overridable in tests so date rules are deterministic.
    return current_app.config.get("TODAY") or date.today()


def my_students(db, tutor_id):
    """Active assignments for this tutor, with hours logged this month."""
    start, end = month_bounds(today().isoformat()[:7])
    return db.execute(
        """SELECT a.*, s.name AS student,
                  (SELECT COALESCE(SUM(hours), 0) FROM sessions x
                    WHERE x.tutor_id = a.tutor_id AND x.student_id = a.student_id
                      AND x.session_date >= ? AND x.session_date < ?) AS month_hours,
                  (SELECT MAX(session_date) FROM sessions x
                    WHERE x.tutor_id = a.tutor_id AND x.student_id = a.student_id) AS last_session
           FROM assignments a JOIN students s ON s.id = a.student_id
           WHERE a.tutor_id = ? AND (a.end_date IS NULL OR a.end_date >= ?)
           ORDER BY s.name""",
        (start, end, tutor_id, today().isoformat()),
    ).fetchall()


def render_dashboard(form=None, errors=(), status_code=200):
    db = get_db()
    recent = db.execute(
        """SELECT x.*, s.name AS student FROM sessions x JOIN students s ON s.id = x.student_id
           WHERE x.tutor_id = ? ORDER BY x.session_date DESC, x.id DESC LIMIT 25""",
        (g.user["id"],),
    ).fetchall()
    closed = {r["month"] for r in db.execute("SELECT month FROM closed_months")}
    students = my_students(db, g.user["id"])
    defaults = {"session_date": today().isoformat(), "status": "held", "hours": "1",
                "student_id": request.args.get("student_id")
                or (str(students[0]["student_id"]) if len(students) == 1 else "")}
    return render_template(
        "tutor/dashboard.html",
        students=students, recent=recent, closed=closed, statuses=STATUSES,
        form=form or defaults, errors=errors, today=today().isoformat(),
    ), status_code


@bp.route("/log")
@role_required("tutor")
def dashboard():
    return render_dashboard()


@bp.route("/sessions", methods=["POST"])
@role_required("tutor")
def create_session():
    db = get_db()
    data, errors = validate_session_form(request.form, today())
    if not errors:
        errors = check_session_rules(db, g.user["id"], data)
    if errors:
        return render_dashboard(request.form, errors, 422)
    save_session(db, g.user["id"], data)
    flash("Session saved.", "success")
    # Keep the same student selected so logging several sessions in a row is quick.
    return redirect(url_for("tutor.dashboard", student_id=data["student_id"]))


def own_session_or_404(session_id):
    row = get_db().execute(
        "SELECT * FROM sessions WHERE id = ? AND tutor_id = ?", (session_id, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    return row


@bp.route("/sessions/<int:session_id>/edit", methods=["GET", "POST"])
@role_required("tutor")
def edit_session(session_id):
    db = get_db()
    existing = own_session_or_404(session_id)
    if is_month_closed(db, existing["session_date"][:7]):
        flash("That month has been closed by staff and can no longer be edited.", "error")
        return redirect(url_for("tutor.dashboard"))

    errors, form = [], dict(existing)
    if request.method == "POST":
        form = request.form
        data, errors = validate_session_form(request.form, today())
        if not errors:
            errors = check_session_rules(db, g.user["id"], data, existing_id=session_id)
        if not errors:
            save_session(db, g.user["id"], data, existing_id=session_id)
            flash("Session updated.", "success")
            return redirect(url_for("tutor.dashboard"))
    # Include students from ended assignments so older entries stay editable.
    students = db.execute(
        """SELECT DISTINCT s.id AS student_id, s.name AS student FROM assignments a
           JOIN students s ON s.id = a.student_id WHERE a.tutor_id = ? ORDER BY s.name""",
        (g.user["id"],),
    ).fetchall()
    return render_template("tutor/edit_session.html", session_row=existing, form=form, errors=errors,
                           students=students, statuses=STATUSES, today=today().isoformat()), (422 if errors else 200)


@bp.route("/sessions/<int:session_id>/delete", methods=["POST"])
@role_required("tutor")
def delete_session(session_id):
    db = get_db()
    existing = own_session_or_404(session_id)
    if is_month_closed(db, existing["session_date"][:7]):
        flash("That month has been closed by staff and can no longer be edited.", "error")
    else:
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        db.commit()
        flash("Session deleted.", "success")
    return redirect(url_for("tutor.dashboard"))
