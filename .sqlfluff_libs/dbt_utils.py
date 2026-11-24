"""SQLFluff lint stubs for dbt_utils macros (render to plausible SQL; never executed)."""


def generate_surrogate_key(field_list):
    return "md5(concat(" + ", ".join(str(f) for f in field_list) + "))"


def date_spine(datepart="day", start_date="", end_date=""):
    return "select cast('2020-01-01' as date) as date_day"
