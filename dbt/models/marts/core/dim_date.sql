-- One row per calendar day, 2020-2030, with the Gulf calendar built in:
-- Hijri (Umm al-Qura) date, Ramadan, holidays and weekends per country
-- (the UAE weekend moved from Fri-Sat to Sat-Sun on 2022-01-01), retail events.
with

spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2020-01-01' as date)",
        end_date="cast('2031-01-01' as date)"
    ) }}
),

days as (
    select cast(date_day as date) as date_day from spine
),

hijri as (
    select * from {{ ref('hijri_calendar') }}
),

country_weekends as (
    select * from {{ ref('country_weekends') }}
),

gulf_holidays as (
    select * from {{ ref('gulf_holidays') }}
),

retail_events as (
    select * from {{ ref('retail_events') }}
),

weekends as (
    select
        days.date_day,
        {{ pivot_by_country('country_weekends.country_code', 'true', 'is_weekend', agg='bool') }}
    from days
    inner join country_weekends
        on
            {{ dbt_date.day_of_week('days.date_day', isoweek=true) }} = country_weekends.iso_day_of_week
            and days.date_day between country_weekends.valid_from and country_weekends.valid_to
    group by days.date_day
),

holidays as (
    select
        holiday_date as date_day,
        {{ pivot_by_country('country_code', 'holiday_name', 'holiday_name') }}
    from gulf_holidays
    group by holiday_date
),

events as (
    select
        days.date_day,
        max(case when retail_events.event_type = 'white_friday' then 1 else 0 end) = 1 as is_white_friday_week,
        max(case when retail_events.event_type = 'dsf' then 1 else 0 end) = 1 as is_dubai_shopping_festival,
        max(case when retail_events.event_type = 'back_to_school' then 1 else 0 end) = 1 as is_back_to_school,
        max(case when retail_events.event_type = 'eid' then 1 else 0 end) = 1 as is_eid_al_adha_period
    from days
    inner join retail_events
        on days.date_day between retail_events.start_date and retail_events.end_date
    group by days.date_day
),

final as (
    select
        cast(
            extract(year from days.date_day) * 10000
            + extract(month from days.date_day) * 100
            + extract(day from days.date_day) as integer
        ) as date_key,
        days.date_day,
        cast(extract(year from days.date_day) as integer) as calendar_year,
        cast(extract(quarter from days.date_day) as integer) as calendar_quarter,
        cast(extract(month from days.date_day) as integer) as month_of_year,
        cast({{ dbt_date.month_name('days.date_day', short=false) }} as varchar) as month_name,
        cast({{ dbt.date_trunc('month', 'days.date_day') }} as date) as month_start_date,
        cast(extract(day from days.date_day) as integer) as day_of_month,
        cast({{ dbt_date.day_of_week('days.date_day', isoweek=true) }} as integer) as iso_day_of_week,
        cast({{ dbt_date.day_name('days.date_day', short=false) }} as varchar) as day_name,
        cast({{ dbt_date.iso_week_of_year('days.date_day') }} as integer) as iso_week_of_year,

        hijri.hijri_date,
        hijri.hijri_year,
        hijri.hijri_month,
        hijri.hijri_day,
        hijri.hijri_month_name_en,
        hijri.hijri_month_name_ar,
        hijri.hijri_month = 9 as is_ramadan,
        hijri.hijri_month = 9 and hijri.hijri_day >= 21 as is_ramadan_last_10_nights,
        {% for cc in var('countries') %}
            coalesce(weekends.is_weekend_{{ cc | lower }}, false) as is_weekend_{{ cc | lower }},
            holidays.holiday_name_{{ cc | lower }},
            holidays.holiday_name_{{ cc | lower }} is not null as is_holiday_{{ cc | lower }},
        {% endfor %}
        coalesce(events.is_white_friday_week, false) as is_white_friday_week,
        coalesce(events.is_dubai_shopping_festival, false) as is_dubai_shopping_festival,
        coalesce(events.is_back_to_school, false) as is_back_to_school,
        coalesce(events.is_eid_al_adha_period, false) as is_eid_al_adha_period
    from days
    inner join hijri on days.date_day = hijri.date_day
    left join weekends on days.date_day = weekends.date_day
    left join holidays on days.date_day = holidays.date_day
    left join events on days.date_day = events.date_day
)

select * from final
