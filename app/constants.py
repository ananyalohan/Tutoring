"""Domain constants taken from the paper Attendance & Achievement form."""
from datetime import date

# (code, label, starred). Starred goals carry a "*" on the paper form; we keep
# the flag so it can be shown, but don't attach extra rules to it.
GOAL_CATEGORIES = [
    ("A", "Economic", [
        ("A1", "Enter Employment", True),
        ("A2", "Retain Employment", True),
        ("A3", "Leave public assistance", False),
    ]),
    ("B", "Educational", [
        ("B1", "Achieve work-based project learner goal", False),
        ("B2", "Enter Occupational Skills Training Program", True),
        ("B3", "Enter Postsecondary Education", True),
        ("B4", "Obtain High School Diploma", True),
    ]),
    ("C", "Family", [
        ("C1", "Help more frequently with school", False),
        ("C2", "Increase contact with child(ren)'s teachers", False),
        ("C3", "More involvement in child(ren)'s school activities", False),
        ("C4", "Purchase books or magazines", False),
        ("C5", "Read to child(ren)", False),
        ("C6", "Visit the library (with/for child(ren))", False),
    ]),
    ("D", "Societal/Community", [
        ("D1", "Obtain citizenship", True),
        ("D2", "Achieve civics skills", False),
        ("D3", "Increase involvement in community activities", False),
        ("D4", "Vote or register to vote", False),
    ]),
]
GOALS = {code: label for _, _, goals in GOAL_CATEGORIES for code, label, _ in goals}
OTHER_GOAL = "E"

STATUSES = {
    "held": "Session held",
    "TA": "Tutor absent",
    "SA": "Student absent",
    "H": "Holiday",
}

MAX_HOURS_PER_SESSION = 8
HOURS_STEP = 0.25  # quarter-hour increments


def fiscal_year_start(d: date) -> int:
    """LVAEP's fiscal year runs July–June; return the calendar year it starts in."""
    return d.year if d.month >= 7 else d.year - 1


def fiscal_year_months(start_year: int):
    """The twelve (year, month) pairs of a fiscal year, in form column order."""
    return [(start_year, m) for m in range(7, 13)] + [(start_year + 1, m) for m in range(1, 7)]


def fiscal_year_label(start_year: int) -> str:
    return f"FY {start_year}-{start_year + 1}"


def goal_label(code: str, other_text: str = "") -> str:
    if code == OTHER_GOAL:
        return f"Other: {other_text}"
    return GOALS.get(code, code)
