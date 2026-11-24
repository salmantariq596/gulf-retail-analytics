from datetime import date

import pytest

from najm_gen.gulf_calendar import (WEEKEND_DAYS, holidays_for, is_dsf, is_ramadan, sales_multiplier,
                                    white_friday)


def test_white_friday_is_last_friday_of_november():
    assert white_friday(2024) == date(2024, 11, 29)
    assert white_friday(2025) == date(2025, 11, 28)
    assert white_friday(2026) == date(2026, 11, 27)


def test_weekends_differ_by_country():
    friday = date(2026, 11, 20)
    sunday = date(2026, 11, 22)
    assert friday.weekday() in WEEKEND_DAYS["SA"] and friday.weekday() in WEEKEND_DAYS["QA"]
    assert friday.weekday() not in WEEKEND_DAYS["AE"]
    assert sunday.weekday() in WEEKEND_DAYS["AE"] and sunday.weekday() not in WEEKEND_DAYS["SA"]


def test_ramadan_and_eid():
    assert is_ramadan(date(2026, 3, 1))
    assert not is_ramadan(date(2026, 3, 20))
    assert "Eid al-Fitr" in holidays_for(date(2026, 3, 20), "AE")


def test_dsf_only_boosts_uae():
    d = date(2025, 12, 20)  # a Saturday: weekend in both countries, so only DSF differs
    assert is_dsf(d)
    assert sales_multiplier("AE", d) / sales_multiplier("QA", d) == pytest.approx(1.25)


def test_white_friday_is_the_biggest_day():
    wf = white_friday(2026)
    assert sales_multiplier("AE", wf) > 2.5
    assert sales_multiplier("AE", wf) > sales_multiplier("AE", date(2026, 11, 10)) * 2
