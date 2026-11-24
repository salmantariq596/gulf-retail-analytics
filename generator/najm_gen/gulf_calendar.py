"""Gulf retail calendar: weekends, Hijri-based holidays and seasonal demand.

Ramadan/Eid dates are the announced Umm al-Qura / UAE dates (±1 day by moon
sighting). The same dates are exported as a dbt seed in Phase 2.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# Python weekday(): Mon=0 ... Fri=4, Sat=5, Sun=6
WEEKEND_DAYS = {"AE": {5, 6}, "SA": {4, 5}, "QA": {4, 5}}

RAMADAN = {
    2022: (date(2022, 4, 2), date(2022, 5, 1)),
    2023: (date(2023, 3, 23), date(2023, 4, 20)),
    2024: (date(2024, 3, 11), date(2024, 4, 9)),
    2025: (date(2025, 3, 1), date(2025, 3, 29)),
    2026: (date(2026, 2, 18), date(2026, 3, 19)),
    2027: (date(2027, 2, 8), date(2027, 3, 9)),
}
EID_AL_FITR = {
    2022: date(2022, 5, 2), 2023: date(2023, 4, 21), 2024: date(2024, 4, 10),
    2025: date(2025, 3, 30), 2026: date(2026, 3, 20), 2027: date(2027, 3, 10),
}
EID_AL_ADHA = {
    2022: date(2022, 7, 9), 2023: date(2023, 6, 28), 2024: date(2024, 6, 16),
    2025: date(2025, 6, 6), 2026: date(2026, 5, 27), 2027: date(2027, 5, 16),
}
NATIONAL_DAYS = {
    "AE": [(12, 2, "UAE National Day"), (12, 3, "UAE National Day")],
    "SA": [(9, 23, "Saudi National Day"), (2, 22, "Saudi Founding Day")],
    "QA": [(12, 18, "Qatar National Day")],
}


def white_friday(year: int) -> date:
    """Last Friday of November (the Gulf's 'Black Friday')."""
    d = date(year, 11, 30)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def is_ramadan(d: date) -> bool:
    r = RAMADAN.get(d.year)
    return bool(r and r[0] <= d <= r[1])


def is_dsf(d: date) -> bool:
    """Dubai Shopping Festival, mid-December to end of January."""
    return (d.month == 12 and d.day >= 15) or (d.month == 1 and d.day <= 29)


def holidays_for(d: date, country: str) -> list[str]:
    names = []
    eid = EID_AL_FITR.get(d.year)
    if eid and eid <= d <= eid + timedelta(days=3):
        names.append("Eid al-Fitr")
    adha = EID_AL_ADHA.get(d.year)
    if adha and adha - timedelta(days=1) <= d <= adha + timedelta(days=3):
        names.append("Eid al-Adha" if d >= adha else "Arafat Day")
    for m, dd, name in NATIONAL_DAYS[country]:
        if d.month == m and d.day == dd:
            names.append(name)
    if d == white_friday(d.year):
        names.append("White Friday")
    return names


@lru_cache(maxsize=None)
def sales_multiplier(country: str, d: date) -> float:
    """Demand multiplier vs an ordinary weekday."""
    m = 1.0
    if d.weekday() in WEEKEND_DAYS[country]:
        m *= 1.35
    if d.month in (7, 8):
        m *= 0.85  # summer: residents travel
    r = RAMADAN.get(d.year)
    if r and r[0] <= d <= r[1]:
        m *= 1.30 if (r[1] - d).days < 10 else 0.92  # last 10 nights: pre-Eid shopping
    eid = EID_AL_FITR.get(d.year)
    if eid and eid <= d <= eid + timedelta(days=3):
        m *= 1.50
    adha = EID_AL_ADHA.get(d.year)
    if adha:
        if adha <= d <= adha + timedelta(days=3):
            m *= 1.30
        elif adha - timedelta(days=7) <= d < adha:
            m *= 1.10
    wf = white_friday(d.year)
    if d == wf:
        m *= 3.0
    elif wf - timedelta(days=3) <= d <= wf + timedelta(days=3):
        m *= 1.5
    if country == "AE" and is_dsf(d):
        m *= 1.25
    if any(d.month == mm and d.day == dd for mm, dd, _ in NATIONAL_DAYS[country]):
        m *= 1.40
    if (d.month == 8 and d.day >= 15) or (d.month == 9 and d.day <= 7):
        m *= 1.15  # back to school
    return m


def seasonal_events(start: date, end: date, country: str) -> list[tuple[str, date, date]]:
    """Marketing-worthy events (name, campaign start, campaign end) for a country."""
    events: list[tuple[str, date, date]] = []
    for y in range(start.year - 1, end.year + 2):
        if y in RAMADAN:
            events.append((f"Ramadan {y}", RAMADAN[y][0] - timedelta(days=7), EID_AL_FITR[y] + timedelta(days=2)))
        if y in EID_AL_ADHA:
            events.append((f"Eid al-Adha {y}", EID_AL_ADHA[y] - timedelta(days=10), EID_AL_ADHA[y] + timedelta(days=2)))
        wf = white_friday(y)
        events.append((f"White Friday {y}", wf - timedelta(days=10), wf + timedelta(days=3)))
        events.append((f"Back to School {y}", date(y, 8, 10), date(y, 9, 10)))
        if country == "AE":
            events.append((f"DSF {y}/{(y + 1) % 100:02d}", date(y, 12, 15), date(y + 1, 1, 29)))
        m, dd, name = NATIONAL_DAYS[country][0]
        nd = date(y, m, dd)
        events.append((f"{name} {y}", nd - timedelta(days=10), nd + timedelta(days=1)))
    return [e for e in events if e[2] >= start and e[1] <= end]
