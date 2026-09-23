from app.db import get_db
from app.reports import monthly_report, monthly_report_csv, year_grid


def log(client, **overrides):
    data = {"student_id": "10", "session_date": "2026-09-15", "status": "held", "hours": "1.5"}
    return client.post("/sessions", data={**data, **overrides})


def count_sessions(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM sessions").fetchone()[0]


# --- Access control ------------------------------------------------------

def test_login_required(app):
    assert app.test_client().get("/log").status_code == 302


def test_roles_are_separated(tutor, staff):
    assert tutor.get("/staff/reports").status_code == 403
    assert staff.get("/log").status_code == 403


def test_tutor_cannot_view_unassigned_student(tutor):
    assert tutor.get("/students/10").status_code == 200
    assert tutor.get("/students/11").status_code == 403


# --- Logging sessions ----------------------------------------------------

def test_tutor_logs_session(app, tutor):
    assert log(tutor).status_code == 302
    assert count_sessions(app) == 1


def test_cannot_log_for_unassigned_student(app, tutor):
    resp = log(tutor, student_id="11")
    assert resp.status_code == 422 and b"assigned" in resp.data
    assert count_sessions(app) == 0


def test_cannot_log_before_assignment_started(app, tutor):
    assert log(tutor, session_date="2026-06-30").status_code == 422


def test_duplicate_day_rejected(app, tutor):
    log(tutor)
    resp = log(tutor, hours="1")
    assert resp.status_code == 422 and b"already logged" in resp.data
    assert count_sessions(app) == 1


def test_closed_month_blocks_create_edit_delete(app, tutor, staff):
    log(tutor)
    staff.post("/staff/months/2026-09/close")
    assert log(tutor, session_date="2026-09-16").status_code == 422
    tutor.post("/sessions/1/edit", data={"student_id": "10", "session_date": "2026-09-15",
                                         "status": "held", "hours": "3"})
    tutor.post("/sessions/1/delete")
    with app.app_context():
        assert get_db().execute("SELECT hours FROM sessions").fetchone()[0] == 1.5


def test_tutor_cannot_edit_someone_elses_session(app, tutor):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO sessions (tutor_id, student_id, session_date, status, hours) "
                   "VALUES (3, 11, '2026-09-10', 'held', 1)")
        db.commit()
    assert tutor.get("/sessions/1/edit").status_code == 404


def test_stop_assignment_blocks_later_sessions(app, tutor):
    log(tutor, session_date="2026-09-10")
    resp = tutor.post("/students/assignments/100/stop", data={"end_date": "2026-09-12", "end_reason": "Moved"})
    assert resp.status_code == 302
    assert log(tutor, session_date="2026-09-15").status_code == 422
    # Can't back-date a stop before a logged session.
    with app.app_context():
        get_db().execute("UPDATE assignments SET end_date = NULL WHERE id = 100")
        get_db().commit()
    tutor.post("/students/assignments/100/stop", data={"end_date": "2026-09-01", "end_reason": "x"})
    with app.app_context():
        assert get_db().execute("SELECT end_date FROM assignments WHERE id = 100").fetchone()[0] is None


# --- Reports -------------------------------------------------------------

def test_monthly_report_aggregates(app, tutor):
    log(tutor, session_date="2026-09-01", hours="1.5")
    log(tutor, session_date="2026-09-08", hours="2")
    log(tutor, session_date="2026-09-10", status="SA")
    log(tutor, session_date="2026-08-31", hours="5")  # previous month, excluded
    with app.app_context():
        r = monthly_report(get_db(), "2026-09")
    tina = next(row for row in r["rows"] if row["tutor"] == "Tina Tutor")
    assert (tina["hours"], tina["held"], tina["sa"]) == (3.5, 2, 1)
    assert r["total_hours"] == 3.5
    # Omar logged nothing for his student, so that pairing is flagged.
    assert [m["tutor"] for m in r["missing"]] == ["Omar Other"]


def test_report_csv(staff, tutor):
    log(tutor)
    resp = staff.get("/staff/reports.csv?month=2026-09")
    assert resp.mimetype == "text/csv"
    lines = resp.data.decode().strip().splitlines()
    assert lines[0].startswith("Tutor,Student")
    assert "Tina Tutor,Sam Student,Library,1.5,1,0,0,0,2026-09-15,," in lines
    assert lines[-1].startswith("TOTAL,,,1.5,1")


def test_year_grid_matches_paper_layout(app, tutor):
    log(tutor, session_date="2026-09-15", hours="1.5")
    log(tutor, session_date="2026-09-17", status="TA")
    with app.app_context():
        grid = year_grid(get_db(), 10, 2026)
    assert grid["month_names"][0] == "Jul" and grid["month_names"][-1] == "Jun"
    assert grid["cells"][((2026, 9), 15)] == (1.5, [])
    assert grid["cells"][((2026, 9), 17)] == (0.0, ["TA"])
    assert grid["days_in"][(2027, 2)] == 28
    assert grid["grand_total"] == 1.5


def test_achievements_recorded_once(app, tutor):
    tutor.post("/students/10/achievements", data={"goal_code": "A1", "attained_on": "2026-09-01"})
    tutor.post("/students/10/achievements", data={"goal_code": "A1", "attained_on": "2026-09-02"})
    tutor.post("/students/10/achievements", data={"goal_code": "E", "other_text": "Got library card",
                                                  "attained_on": "2026-09-03"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM achievements").fetchone()[0] == 2
        r = monthly_report(get_db(), "2026-09")
    assert {a["label"] for a in r["achievements"]} == {"Enter Employment", "Other: Got library card"}


def test_pages_render(staff):
    for url in ["/staff/reports", "/staff/reports?month=2026-07", "/staff/people", "/students/10"]:
        assert staff.get(url).status_code == 200, url


# --- Tutor sign-up -------------------------------------------------------

def signup(app, **overrides):
    from conftest import AuthedClient
    client = AuthedClient(app.test_client())
    with client.client.session_transaction() as s:
        s["_csrf"] = "t"
    data = {"name": "New Tutor", "email": "New@Example.com", "password": "longenough", "confirm": "longenough"}
    return client, client.post("/signup", data={**data, **overrides})


def test_signup_creates_tutor_and_logs_in(app):
    client, resp = signup(app)
    assert resp.status_code == 302
    with app.app_context():
        user = get_db().execute("SELECT * FROM users WHERE email = 'new@example.com'").fetchone()
    assert user["role"] == "tutor" and user["password_hash"] != "longenough"
    # Logged straight in, but sees no student data until staff assign someone.
    with client.client.session_transaction() as s:
        s["_csrf"] = "t"
    page = client.get("/log")
    assert page.status_code == 200 and b"any students assigned yet" in page.data
    assert client.get("/students/10").status_code == 403
    assert client.get("/staff/reports").status_code == 403


def test_signup_validation(app):
    for overrides, message in [
        ({"email": "tina@x.org"}, b"already exists"),
        ({"password": "short", "confirm": "short"}, b"at least 8"),
        ({"confirm": "different1"}, b"don&#39;t match"),
        ({"name": "  "}, b"Enter your name"),
        ({"email": "nope"}, b"valid email"),
    ]:
        _, resp = signup(app, **overrides)
        assert resp.status_code == 422 and message in resp.data, overrides


def test_signup_cannot_create_staff(app):
    signup(app, role="staff", email="sneaky@x.org")
    with app.app_context():
        assert get_db().execute("SELECT role FROM users WHERE email = 'sneaky@x.org'").fetchone()[0] == "tutor"


def test_new_tutor_flagged_for_staff(app, staff):
    signup(app)
    assert b"New Tutor" in staff.get("/staff/reports").data
