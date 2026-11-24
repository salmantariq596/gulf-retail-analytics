# Snowflake cost note

Trial budget: $400 of credits / 30 days. Guardrails: X-Small warehouses only, 60-second auto-suspend, and a resource monitor that suspends at 75%.

Fill in from Admin → Cost Management, or query:

```sql
select warehouse_name, sum(credits_used) as credits
from snowflake.account_usage.warehouse_metering_history
where start_time >= dateadd(day, -1, current_timestamp())
group by 1 order by 2 desc;
```

| Run | Warehouse | Duration | Credits | Notes |
|---|---|---|---|---|
| Full 3-year load (dlt) | LOAD_WH | | | |
| Full build `dbt build --full-refresh` | TRANSFORM_WH | | | |
| One incremental day (dlt + dbt) | LOAD_WH + TRANSFORM_WH | | | |
| Slim CI run (Phase 7) | TRANSFORM_WH | | | |
| Dashboards, one day of use | BI_WH | | | |

**Projected monthly cost of running this daily:** _(incremental day credits × 30 × price per credit)_
