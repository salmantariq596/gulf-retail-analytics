-- Known facts about the Gulf calendar that dim_date must get right.
-- Each row returned is a failed expectation.
{% set expectations = [
    ("UAE Friday 2021 is weekend (Fri-Sat until 2021)", "2021-12-31", "is_weekend_ae"),
    ("UAE Sunday 2021 is a workday", "2021-12-26", "not is_weekend_ae"),
    ("UAE Sunday 2026 is weekend (Sat-Sun since 2022)", "2026-11-22", "is_weekend_ae"),
    ("UAE Friday 2026 is a workday", "2026-11-20", "not is_weekend_ae"),
    ("KSA Friday is weekend", "2026-11-20", "is_weekend_sa"),
    ("KSA Sunday is a workday", "2026-11-22", "not is_weekend_sa"),
    ("Qatar Saturday is weekend", "2026-11-21", "is_weekend_qa"),
    ("1 Ramadan 1447 is 2026-02-18", "2026-02-18", "is_ramadan and hijri_date = '1447-09-01'"),
    ("Eid al-Fitr is not Ramadan", "2026-03-20", "not is_ramadan"),
    ("Eid al-Fitr is a UAE holiday", "2026-03-20", "holiday_name_ae = 'Eid al-Fitr'"),
    ("White Friday 2026", "2026-11-27", "holiday_name_ae = 'White Friday' and is_white_friday_week"),
    ("DSF covers 2026-12-20", "2026-12-20", "is_dubai_shopping_festival"),
    ("Saudi National Day is KSA-only", "2026-09-23", "holiday_name_sa = 'Saudi National Day' and holiday_name_ae is null"),
] %}

with

dates as (
    select * from {{ ref('dim_date') }}
),

checks as (
    {% for label, day, condition in expectations %}
        select
            '{{ label }}' as expectation,
            coalesce({{ condition }}, false) as is_met
        from dates
        where date_day = cast('{{ day }}' as date)
        {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select expectation
from checks
where not is_met
