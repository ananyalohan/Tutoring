from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db, init_db

TODAY = date(2026, 9, 22)


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite"), "TODAY": TODAY})
    with app.app_context():
        init_db()
        db = get_db()
        pw = generate_password_hash("pw")
        db.executescript(f"""
            INSERT INTO users (id, name, email, password_hash, role) VALUES
              (1, 'Staff', 'staff@x.org', '{pw}', 'staff'),
              (2, 'Tina Tutor', 'tina@x.org', '{pw}', 'tutor'),
              (3, 'Omar Other', 'omar@x.org', '{pw}', 'tutor');
            INSERT INTO students (id, name) VALUES (10, 'Sam Student'), (11, 'Olga Unassigned');
            INSERT INTO assignments (id, tutor_id, student_id, site, start_date) VALUES
              (100, 2, 10, 'Library', '2026-07-01'),
              (101, 3, 11, 'Online', '2026-07-01');
        """)
        db.commit()
    yield app


class AuthedClient:
    """Test client that logs in and attaches the CSRF token to every POST."""

    def __init__(self, client):
        self.client = client

    def login(self, email):
        with self.client.session_transaction() as s:
            s["_csrf"] = "t"
        self.client.post("/login", data={"email": email, "password": "pw", "_csrf": "t"})
        # Login clears the session (rotating the token), so set it again.
        with self.client.session_transaction() as s:
            s["_csrf"] = "t"
        return self

    def get(self, *a, **kw):
        return self.client.get(*a, **kw)

    def post(self, url, data=None, **kw):
        return self.client.post(url, data={**(data or {}), "_csrf": "t"}, **kw)


@pytest.fixture
def tutor(app):
    return AuthedClient(app.test_client()).login("tina@x.org")


@pytest.fixture
def staff(app):
    return AuthedClient(app.test_client()).login("staff@x.org")
