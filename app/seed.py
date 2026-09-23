"""Demo data so reviewers can click around immediately."""
import random
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from .constants import fiscal_year_start

PASSWORD = "password123"


def seed(db, today=None):
    today = today or date.today()
    rng = random.Random(42)
    fy_start = date(fiscal_year_start(today), 7, 1)
    pw = generate_password_hash(PASSWORD)

    users = [("Office Staff", "staff@lvaep.org", "staff"),
             ("Maria Lopez", "maria@example.com", "tutor"),
             ("James Chen", "james@example.com", "tutor"),
             ("Priya Patel", "priya@example.com", "tutor")]
    ids = {}
    for name, email, role in users:
        ids[email] = db.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                                (name, email, pw, role)).lastrowid
    staff_id = ids["staff@lvaep.org"]

    student_ids = {}
    for name in ["Ana Silva", "Samuel Okafor", "Lin Wei", "Rosa Martinez", "Yusuf Demir", "Grace Kim"]:
        student_ids[name] = db.execute("INSERT INTO students (name) VALUES (?)", (name,)).lastrowid

    # (tutor, student, site, weekday(s) 0=Mon, times, stopped_after_days)
    pairs = [
        ("maria@example.com", "Ana Silva", "Bloomfield Public Library", [0, 3], "Mon/Thu 6-7:30pm", None),
        ("maria@example.com", "Samuel Okafor", "Bloomfield Public Library", [2], "Wed 10-11:30am", None),
        ("james@example.com", "Lin Wei", "Montclair Library", [1], "Tue 5-6:30pm", None),
        ("james@example.com", "Rosa Martinez", "Montclair Library", [4], "Fri 1-2pm", 45),
        ("priya@example.com", "Yusuf Demir", "Online", [1, 3], "Tue/Thu 7-8pm", None),
        ("priya@example.com", "Grace Kim", "Nutley Library", [5], "Sat 11am-12:30pm", None),
    ]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for tutor_email, student, site, weekdays, times, stop_after in pairs:
        tutor_id, student_id = ids[tutor_email], student_ids[student]
        end = fy_start + timedelta(days=stop_after) if stop_after else None
        db.execute(
            """INSERT INTO assignments (tutor_id, student_id, site, meeting_days, meeting_times, start_date,
                                        end_date, end_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (tutor_id, student_id, site, "/".join(day_names[w] for w in weekdays), times, fy_start.isoformat(),
             end and end.isoformat(), "Moved out of the area" if end else None),
        )
        # Leave Grace Kim with nothing logged this month so the "missing" list has something in it.
        last = end or today
        d = fy_start
        while d <= last:
            skip_this_month = student == "Grace Kim" and (d.year, d.month) == (today.year, today.month)
            if d.weekday() in weekdays and not skip_this_month:
                roll = rng.random()
                status, hours = ("held", rng.choice([1, 1.5, 1.5, 2])) if roll < 0.82 else \
                                (rng.choice(["TA", "SA", "SA"]), 0)
                if d.month == 9 and d.day == 7:  # Labor Day
                    status, hours = "H", 0
                db.execute(
                    "INSERT INTO sessions (tutor_id, student_id, session_date, status, hours) VALUES (?, ?, ?, ?, ?)",
                    (tutor_id, student_id, d.isoformat(), status, hours),
                )
            d += timedelta(days=1)

    for student, code, days_in in [("Ana Silva", "C5", 20), ("Lin Wei", "A1", 50), ("Yusuf Demir", "D2", 70)]:
        attained = min(fy_start + timedelta(days=days_in), today)
        db.execute("INSERT INTO achievements (student_id, goal_code, attained_on, recorded_by) VALUES (?, ?, ?, ?)",
                   (student_ids[student], code, attained.isoformat(), staff_id))

    # Close the months before last so the locking behaviour is visible.
    m = date(today.year, today.month, 1)
    for _ in range(2):
        m = (m - timedelta(days=1)).replace(day=1)
    while m >= fy_start:
        db.execute("INSERT INTO closed_months (month, closed_by) VALUES (?, ?)", (m.isoformat()[:7], staff_id))
        m = (m - timedelta(days=1)).replace(day=1)
    db.commit()
