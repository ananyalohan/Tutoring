DROP TABLE IF EXISTS closed_months;
DROP TABLE IF EXISTS achievements;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS assignments;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS users;

-- Tutors and staff share one table; role decides what they can see.
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('tutor', 'staff'))
);

CREATE TABLE students (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

-- A tutor/student pairing. Site, day(s) and time(s) come from the footer of
-- the paper form. end_date + end_reason replace the "STOPPED" box.
CREATE TABLE assignments (
    id            INTEGER PRIMARY KEY,
    tutor_id      INTEGER NOT NULL REFERENCES users (id),
    student_id    INTEGER NOT NULL REFERENCES students (id),
    site          TEXT NOT NULL DEFAULT '',
    meeting_days  TEXT NOT NULL DEFAULT '',
    meeting_times TEXT NOT NULL DEFAULT '',
    start_date    TEXT NOT NULL,          -- ISO date
    end_date      TEXT,                   -- NULL while active
    end_reason    TEXT
);

-- One row per box on the paper grid: a (tutor, student, day) with either
-- hours tutored or an absence code.
CREATE TABLE sessions (
    id           INTEGER PRIMARY KEY,
    tutor_id     INTEGER NOT NULL REFERENCES users (id),
    student_id   INTEGER NOT NULL REFERENCES students (id),
    session_date TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('held', 'TA', 'SA', 'H')),
    hours        REAL NOT NULL DEFAULT 0 CHECK (hours >= 0),
    notes        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tutor_id, student_id, session_date)
);
CREATE INDEX idx_sessions_date ON sessions (session_date);

-- Goals from the "ACHIEVEMENTS" column. goal_code is a key into
-- constants.GOALS, or 'E' for a free-text "Other" goal.
CREATE TABLE achievements (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students (id),
    goal_code   TEXT NOT NULL,
    other_text  TEXT NOT NULL DEFAULT '',
    attained_on TEXT NOT NULL,
    recorded_by INTEGER NOT NULL REFERENCES users (id)
);
CREATE UNIQUE INDEX idx_achievement_once
    ON achievements (student_id, goal_code) WHERE goal_code != 'E';

-- Months staff have finalised; sessions in them can no longer be changed.
CREATE TABLE closed_months (
    month     TEXT PRIMARY KEY,           -- 'YYYY-MM'
    closed_by INTEGER NOT NULL REFERENCES users (id),
    closed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
