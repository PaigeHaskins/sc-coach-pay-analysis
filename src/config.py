"""
config.py - Settings shared by every step of the pipeline.

This is the only file to edit when something changes:
  - your regular schedule changes         -> REGULAR_SCHEDULE
  - a holiday schedule or a swapped shift  -> SCHEDULE_EXCEPTIONS
  - pay rules change                       -> the PAY section
"""
from datetime import date, time
from pathlib import Path

# ---------------------------------------------------------------- anonymization
COMPANY = "ABC Studio"
COACH = "Jane Doe"
CLASS_NAME = "Full Body (50 min)"
# Words that must never appear in cleaned data (real names, company, location).
# They're kept in private_terms.txt (one per line), which is never published,
# so the check itself doesn't reveal them. Missing file = no check.
_TERMS_FILE = Path(__file__).resolve().parents[1] / "private_terms.txt"
BANNED_TERMS = ([t.strip().lower() for t in _TERMS_FILE.read_text().splitlines() if t.strip()]
                if _TERMS_FILE.exists() else [])

# ---------------------------------------------------------------- studios
CAPACITY = {1: 10, 2: 16}

# ---------------------------------------------------------------- pay
REVENUE_PER_VISIT = 27.80
STUDIO_REV_SHARE = {1: 0.24, 2: 0.16}
FLOOR_PAY = 28.00      # minimum per class, and the flat Starter rate
MAX_PAY = 83.00        # a class never pays more than this

# ---------------------------------------------------------------- schedule
# Regular (assigned) schedule. Everything else is a pickup.
# (studio, weekday, [start times], first date it applies, last date it applies)
# weekday: Monday = 0, Tuesday = 1, ... Saturday = 5, Sunday = 6. None = open-ended.
# When a slot stops being regular, set its last date instead of deleting it,
# so past classes keep their label.
REGULAR_SCHEDULE = [
    (2, 0, [time(15, 30), time(16, 30)], None, None),                         # Mon 3:30, 4:30 PM
    (1, 4, [time(8, 0), time(9, 0)], None, None),                             # Fri 8, 9 AM
    (2, 5, [time(11, 30), time(12, 30), time(13, 30)], None, date(2026, 5, 31)),  # Sat, until the switch
    (2, 5, [time(6, 30), time(7, 30)], date(2026, 6, 1), None),               # Sat 6:30, 7:30 AM
    (1, 5, [time(10, 0)], date(2026, 8, 1), None),                            # Sat 10 AM
    (1, 1, [time(15, 0), time(16, 0)], date(2026, 8, 18), None),              # Tue 3, 4 PM
]

# Regular shifts that ran at a different time (holidays, swaps). Labeled Regular.
# (studio, date, start time): note
SCHEDULE_EXCEPTIONS = {
    (1, date(2026, 5, 25), time(11, 0)): "Holiday schedule (Memorial Day)",
    (1, date(2026, 5, 25), time(12, 0)): "Holiday schedule (Memorial Day)",
    (1, date(2026, 5, 29), time(16, 0)): "Swapped from Fri 8/9am",
    (1, date(2026, 5, 29), time(17, 0)): "Swapped from Fri 8/9am",
    (1, date(2026, 9, 7), time(10, 0)): "Holiday schedule (Labor Day)",
}

# ---------------------------------------------------------------- forecast
FORECAST_WEEKS = 13          # about 3 months
RECENT_WEEKS = 6             # how far back the pickup habit is measured
RECENT_OCCURRENCES = 6       # recent classes used to price each regular slot

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def time_label(t: time) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def current_regular_slots() -> set:
    """Slot labels (e.g. 'Studio 2 | Mon 4:30 PM') for the schedule in effect now."""
    return {f"Studio {studio} | {DAY_ABBR[day]} {time_label(t)}"
            for studio, day, times, _, end in REGULAR_SCHEDULE if end is None
            for t in times}
