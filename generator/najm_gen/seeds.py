"""Export calendar seeds for dbt from the same calendar the generator uses,
so the warehouse and the simulated demand can never disagree.

    python -m najm_gen.seeds          # writes dbt/seeds/{hijri_calendar,gulf_holidays,retail_events}.csv
"""

from __future__ import annotations

import csv
from datetime import date, timedelta

from hijridate import Gregorian

from .config import REPO_ROOT
from .gulf_calendar import EID_AL_ADHA, RAMADAN, holidays_for, white_friday

SEED_DIR = REPO_ROOT / "dbt" / "seeds"
FIRST, LAST = date(2018, 1, 1), date(2030, 12, 31)
HIJRI_MONTHS = [
    ("Muharram", "محرم"), ("Safar", "صفر"), ("Rabi al-Awwal", "ربيع الأول"), ("Rabi al-Thani", "ربيع الآخر"),
    ("Jumada al-Ula", "جمادى الأولى"), ("Jumada al-Akhirah", "جمادى الآخرة"), ("Rajab", "رجب"),
    ("Shaban", "شعبان"), ("Ramadan", "رمضان"), ("Shawwal", "شوال"), ("Dhu al-Qadah", "ذو القعدة"),
    ("Dhu al-Hijjah", "ذو الحجة"),
]


def _days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def hijri_calendar() -> list[dict]:
    rows = []
    for d in _days(FIRST, LAST):
        h = Gregorian(d.year, d.month, d.day).to_hijri()
        en, ar = HIJRI_MONTHS[h.month - 1]
        rows.append(dict(date_day=d.isoformat(), hijri_year=h.year, hijri_month=h.month, hijri_day=h.day,
                         hijri_month_name_en=en, hijri_month_name_ar=ar,
                         hijri_date=f"{h.year:04d}-{h.month:02d}-{h.day:02d}"))
    return rows


def gulf_holidays() -> list[dict]:
    """Single-day public holidays and retail peaks, per country."""
    start, end = date(2022, 1, 1), date(2027, 12, 31)
    return [dict(holiday_date=d.isoformat(), country_code=cc, holiday_name=name)
            for d in _days(start, end) for cc in ("AE", "SA", "QA") for name in holidays_for(d, cc)]


def retail_events() -> list[dict]:
    """Multi-day trading periods used for seasonality analysis."""
    rows = []
    for y in range(2022, 2028):
        if y in RAMADAN:
            s, e = RAMADAN[y]
            rows.append(dict(event_name=f"Ramadan {y}", event_type="ramadan", country_code="",
                             start_date=s.isoformat(), end_date=e.isoformat()))
            rows.append(dict(event_name=f"Last 10 nights of Ramadan {y}", event_type="ramadan_peak", country_code="",
                             start_date=(e - timedelta(days=9)).isoformat(), end_date=e.isoformat()))
        if y in EID_AL_ADHA:
            a = EID_AL_ADHA[y]
            rows.append(dict(event_name=f"Eid al-Adha {y}", event_type="eid", country_code="",
                             start_date=(a - timedelta(days=1)).isoformat(),
                             end_date=(a + timedelta(days=3)).isoformat()))
        wf = white_friday(y)
        rows.append(dict(event_name=f"White Friday week {y}", event_type="white_friday", country_code="",
                         start_date=(wf - timedelta(days=3)).isoformat(), end_date=(wf + timedelta(days=3)).isoformat()))
        rows.append(dict(event_name=f"Dubai Shopping Festival {y}/{(y + 1) % 100:02d}", event_type="dsf",
                         country_code="AE", start_date=date(y, 12, 15).isoformat(),
                         end_date=date(y + 1, 1, 29).isoformat()))
        rows.append(dict(event_name=f"Back to school {y}", event_type="back_to_school", country_code="",
                         start_date=date(y, 8, 15).isoformat(), end_date=date(y, 9, 7).isoformat()))
    return rows


def _write(name: str, rows: list[dict]) -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEED_DIR / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"  {name}.csv: {len(rows):,} rows")


def main() -> None:
    _write("hijri_calendar", hijri_calendar())
    _write("gulf_holidays", gulf_holidays())
    _write("retail_events", retail_events())


if __name__ == "__main__":
    main()
