from app.session_log import validate_session_form
from conftest import TODAY


def form(**overrides):
    base = {"student_id": "10", "session_date": "2026-09-15", "status": "held", "hours": "1.5", "notes": ""}
    return {**base, **overrides}


def test_valid_held_session():
    data, errors = validate_session_form(form(), TODAY)
    assert errors == []
    assert data["hours"] == 1.5 and data["status"] == "held"


def test_future_date_rejected():
    _, errors = validate_session_form(form(session_date="2026-09-23"), TODAY)
    assert any("future" in e for e in errors)


def test_hours_bounds_and_quarter_steps():
    for bad in ["0", "-1", "9", "1.3", "abc", ""]:
        _, errors = validate_session_form(form(hours=bad), TODAY)
        assert errors, bad
    for good in ["0.25", "1", "2.75", "8"]:
        assert validate_session_form(form(hours=good), TODAY)[1] == [], good


def test_absence_records_zero_hours_regardless_of_input():
    data, errors = validate_session_form(form(status="SA", hours="3"), TODAY)
    assert errors == [] and data["hours"] == 0


def test_unknown_status_and_missing_student():
    _, errors = validate_session_form(form(status="X", student_id=""), TODAY)
    assert len(errors) == 2
