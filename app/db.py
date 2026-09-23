import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    schema = (Path(__file__).parent / "schema.sql").read_text()
    get_db().executescript(schema)


def is_month_closed(db, month: str) -> bool:
    return db.execute("SELECT 1 FROM closed_months WHERE month = ?", (month,)).fetchone() is not None
