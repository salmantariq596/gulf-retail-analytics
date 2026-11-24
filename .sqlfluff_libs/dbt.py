"""SQLFluff lint stubs for dbt's cross-database macros."""


def date_trunc(datepart, date):
    return f"date_trunc('{datepart}', {date})"


def dateadd(datepart, interval, from_date_or_timestamp):
    return f"({from_date_or_timestamp} + interval ({interval}) {datepart})"


def current_timestamp():
    return "current_timestamp"


def datediff(first_date, second_date, datepart):
    return f"date_diff('{datepart}', {first_date}, {second_date})"
