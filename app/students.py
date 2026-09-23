"""Per-student pages shared by tutors and staff: year grid, achievements, stopping."""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .constants import (GOAL_CATEGORIES, GOALS, OTHER_GOAL, fiscal_year_label,
                        fiscal_year_start, goal_label)
from .db import get_db
from .reports import year_grid
from .tutor import today

bp = Blueprint("students", __name__, url_prefix="/students")


def student_for_viewer(student_id):
    """Staff can see any student; tutors only students they are or were assigned."""
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if student is None:
        abort(404)
    if g.user["role"] == "tutor":
        linked = db.execute("SELECT 1 FROM assignments WHERE tutor_id = ? AND student_id = ?",
                            (g.user["id"], student_id)).fetchone()
        if not linked:
            abort(403)
    return student


def parse_past_date(value):
    try:
        d = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return d.isoformat() if d <= today() else None


@bp.route("/<int:student_id>")
@login_required
def detail(student_id):
    db = get_db()
    student = student_for_viewer(student_id)
    fy = request.args.get("fy", type=int) or fiscal_year_start(today())
    is_tutor = g.user["role"] == "tutor"

    assignments = db.execute(
        """SELECT a.*, u.name AS tutor FROM assignments a JOIN users u ON u.id = a.tutor_id
           WHERE a.student_id = ? {} ORDER BY a.start_date DESC""".format("AND a.tutor_id = ?" if is_tutor else ""),
        (student_id, g.user["id"]) if is_tutor else (student_id,),
    ).fetchall()
    attained = db.execute(
        """SELECT ac.*, u.name AS recorded_by_name FROM achievements ac JOIN users u ON u.id = ac.recorded_by
           WHERE ac.student_id = ? ORDER BY ac.attained_on""",
        (student_id,),
    ).fetchall()

    return render_template(
        "students/detail.html",
        student=student, assignments=assignments,
        grid=year_grid(db, student_id, fy, tutor_id=g.user["id"] if is_tutor else None),
        fy=fy, fy_label=fiscal_year_label(fy),
        goal_categories=GOAL_CATEGORIES,
        attained={a["goal_code"]: a for a in attained if a["goal_code"] != OTHER_GOAL},
        other_goals=[a for a in attained if a["goal_code"] == OTHER_GOAL],
        today=today().isoformat(),
    )


@bp.route("/<int:student_id>/achievements", methods=["POST"])
@login_required
def add_achievement(student_id):
    student_for_viewer(student_id)
    db = get_db()
    code = request.form.get("goal_code", "")
    other_text = request.form.get("other_text", "").strip()
    attained_on = parse_past_date(request.form.get("attained_on"))

    if code not in GOALS and code != OTHER_GOAL:
        flash("Unknown goal.", "error")
    elif code == OTHER_GOAL and not other_text:
        flash("Describe the goal the student attained.", "error")
    elif attained_on is None:
        flash("Enter the date the goal was attained (not in the future).", "error")
    elif code != OTHER_GOAL and db.execute(
            "SELECT 1 FROM achievements WHERE student_id = ? AND goal_code = ?", (student_id, code)).fetchone():
        flash("That goal is already marked as attained.", "error")
    else:
        db.execute(
            "INSERT INTO achievements (student_id, goal_code, other_text, attained_on, recorded_by) VALUES (?, ?, ?, ?, ?)",
            (student_id, code, other_text, attained_on, g.user["id"]),
        )
        db.commit()
        flash(f"Recorded: {goal_label(code, other_text)}.", "success")
    return redirect(url_for("students.detail", student_id=student_id) + "#achievements")


@bp.route("/<int:student_id>/achievements/<int:achievement_id>/delete", methods=["POST"])
@login_required
def delete_achievement(student_id, achievement_id):
    student_for_viewer(student_id)
    db = get_db()
    db.execute("DELETE FROM achievements WHERE id = ? AND student_id = ?", (achievement_id, student_id))
    db.commit()
    flash("Achievement removed.", "success")
    return redirect(url_for("students.detail", student_id=student_id) + "#achievements")


@bp.route("/assignments/<int:assignment_id>/stop", methods=["POST"])
@login_required
def stop_assignment(assignment_id):
    """Replaces the paper form's STOPPED box. Staff see it on the report straight away."""
    db = get_db()
    a = db.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    if a is None:
        abort(404)
    if g.user["role"] == "tutor" and a["tutor_id"] != g.user["id"]:
        abort(403)

    end_date = parse_past_date(request.form.get("end_date"))
    reason = request.form.get("end_reason", "").strip()
    last = db.execute("SELECT MAX(session_date) FROM sessions WHERE tutor_id = ? AND student_id = ?",
                      (a["tutor_id"], a["student_id"])).fetchone()[0]
    if a["end_date"]:
        flash("This pairing has already been stopped.", "error")
    elif end_date is None or not reason:
        flash("Enter the last date of tutoring and a reason.", "error")
    elif end_date < a["start_date"] or (last and end_date < last):
        flash(f"The stop date can't be before the start date or the last logged session ({last}).", "error")
    else:
        db.execute("UPDATE assignments SET end_date = ?, end_reason = ? WHERE id = ?",
                   (end_date, reason, assignment_id))
        db.commit()
        flash("Marked as stopped. The office will see this on the monthly report.", "success")
    return redirect(url_for("students.detail", student_id=a["student_id"]))
