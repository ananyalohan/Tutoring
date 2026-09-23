"""Read-side queries: the monthly staff report and the per-student year grid."""
import calendar
import csv
import io
from datetime import date

from .constants import fiscal_year_months, goal_label


def month_bounds(month: str):
    """'2026-09' -> ('2026-09-01', '2026-10-01'), a half-open date range."""
    first = date.fromisoformat(month + "-01")
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first.isoformat(), nxt.isoformat()


def monthly_report(db, month: str):
    """Hours and attendance for every assignment active at any point in the month."""
    start, end = month_bounds(month)
    rows = db.execute(
        """SELECT a.id AS assignment_id, t.id AS tutor_id, t.name AS tutor,
                  s.id AS student_id, s.name AS student, a.site, a.end_date, a.end_reason,
                  COALESCE(SUM(CASE WHEN x.status = 'held' THEN x.hours END), 0) AS hours,
                  COUNT(CASE WHEN x.status = 'held' THEN 1 END) AS held,
                  COUNT(CASE WHEN x.status = 'TA' THEN 1 END) AS ta,
                  COUNT(CASE WHEN x.status = 'SA' THEN 1 END) AS sa,
                  COUNT(CASE WHEN x.status = 'H' THEN 1 END) AS holiday,
                  MAX(x.session_date) AS last_entry
           FROM assignments a
           JOIN users t ON t.id = a.tutor_id
           JOIN students s ON s.id = a.student_id
           LEFT JOIN sessions x
                  ON x.tutor_id = a.tutor_id AND x.student_id = a.student_id
                 AND x.session_date >= ? AND x.session_date < ?
                 AND x.session_date >= a.start_date
                 AND (a.end_date IS NULL OR x.session_date <= a.end_date)
           WHERE a.start_date < ? AND (a.end_date IS NULL OR a.end_date >= ?)
           GROUP BY a.id
           ORDER BY t.name, s.name""",
        (start, end, end, start),
    ).fetchall()
    rows = [dict(r) for r in rows]
    for r in rows:
        r["entries"] = r["held"] + r["ta"] + r["sa"] + r["holiday"]

    achievements = db.execute(
        """SELECT s.name AS student, ac.goal_code, ac.other_text, ac.attained_on, u.name AS recorded_by
           FROM achievements ac JOIN students s ON s.id = ac.student_id JOIN users u ON u.id = ac.recorded_by
           WHERE ac.attained_on >= ? AND ac.attained_on < ?
           ORDER BY ac.attained_on, s.name""",
        (start, end),
    ).fetchall()

    stopped = [r for r in rows if r["end_date"] and start <= r["end_date"] < end]
    return {
        "month": month,
        "rows": rows,
        "total_hours": sum(r["hours"] for r in rows),
        "total_held": sum(r["held"] for r in rows),
        "missing": [r for r in rows if r["entries"] == 0],
        "stopped": stopped,
        "achievements": [dict(a, label=goal_label(a["goal_code"], a["other_text"])) for a in achievements],
    }


CSV_COLUMNS = [
    ("tutor", "Tutor"), ("student", "Student"), ("site", "Site"), ("hours", "Hours"),
    ("held", "Sessions held"), ("ta", "Tutor absent"), ("sa", "Student absent"),
    ("holiday", "Holiday"), ("last_entry", "Last entry"), ("end_date", "Stopped on"),
    ("end_reason", "Stop reason"),
]


def monthly_report_csv(report) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in CSV_COLUMNS])
    for r in report["rows"]:
        writer.writerow(["" if r[key] is None else r[key] for key, _ in CSV_COLUMNS])
    writer.writerow(["TOTAL", "", "", report["total_hours"], report["total_held"]])
    return buf.getvalue()


def year_grid(db, student_id, fy_start: int, tutor_id=None):
    """Rebuild the paper form's 31-day x 12-month grid from session records.

    Each cell holds hours tutored, or an absence code (TA/SA/H). If a tutor_id
    is given, only that tutor's sessions are included (the paper form is per
    tutor); staff see every tutor's sessions for the student.
    """
    months = fiscal_year_months(fy_start)
    start = date(fy_start, 7, 1).isoformat()
    end = date(fy_start + 1, 7, 1).isoformat()
    sql = "SELECT session_date, status, hours FROM sessions WHERE student_id = ? AND session_date >= ? AND session_date < ?"
    params = [student_id, start, end]
    if tutor_id is not None:
        sql += " AND tutor_id = ?"
        params.append(tutor_id)

    cells, totals = {}, {m: 0.0 for m in months}
    for row in db.execute(sql, params):
        d = date.fromisoformat(row["session_date"])
        key = ((d.year, d.month), d.day)
        prev_hours, prev_codes = cells.get(key, (0.0, []))
        if row["status"] == "held":
            cells[key] = (prev_hours + row["hours"], prev_codes)
            totals[(d.year, d.month)] += row["hours"]
        else:
            cells[key] = (prev_hours, prev_codes + [row["status"]])

    days_in = {m: calendar.monthrange(*m)[1] for m in months}
    return {
        "months": months,
        "month_names": [calendar.month_abbr[m] for _, m in months],
        "cells": cells,
        "days_in": days_in,
        "totals": totals,
        "grand_total": sum(totals.values()),
    }
