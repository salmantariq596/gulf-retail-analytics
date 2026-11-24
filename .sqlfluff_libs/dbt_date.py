"""SQLFluff lint stubs for dbt_date macros."""


def day_of_week(date, isoweek=True):
    return f"isodow({date})"


def day_name(date, short=True, language="default"):
    return f"dayname({date})"


def month_name(date, short=True, language="default"):
    return f"monthname({date})"


def iso_week_of_year(date=None, tz=None):
    return f"weekofyear({date})"
