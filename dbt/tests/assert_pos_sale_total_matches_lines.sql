-- Source reconciliation: every till header total must equal the sum of its lines,
-- counting each (sale_id, line_number) once (re-sent duplicate lines excluded).
-- If this fails, the duplicate rule (keep one copy per line number) is wrong.
with

lines as (
    select
        sale_id,
        line_number,
        min(line_total_incl_vat) as line_total_incl_vat
    from {{ ref('stg_pos__sale_lines') }}
    group by sale_id, line_number
),

line_totals as (
    select
        sale_id,
        sum(line_total_incl_vat) as lines_total
    from lines
    group by sale_id
)

select
    s.sale_id,
    s.total_incl_vat,
    l.lines_total
from {{ ref('stg_pos__sales') }} as s
left join line_totals as l on s.sale_id = l.sale_id
where abs(s.total_incl_vat - coalesce(l.lines_total, 0)) > 0.01
