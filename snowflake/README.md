# Snowflake runbook (Phase 5)

The trial gives 30 days or $400 of credits, whichever ends first. Everything below is prepared so the trial is spent on deployment, not setup.

## Before the trial (free)

1. **Disk:** the full dataset needs about 6 GB on the drive that holds Docker's disk image. Docker Desktop → Settings → Resources → Advanced → *Disk image location* lets you move it off a full C: drive.
2. **Generate 3 years of data** (~2.5 h, runs next to the dev data and never over it):
   ```powershell
   .\snowflake\full_load.ps1 -Step generate
   ```

## Day 1 of the trial

1. Sign up for the trial (choose a region close to the Gulf, e.g. AWS me-central-1 / GCP me-central2, if offered).
2. In a worksheet, as ACCOUNTADMIN, run [`01_setup.sql`](01_setup.sql). Adjust `credit_quota` first. It creates:
   - **Databases:** `RAW` (dlt writes), `DEV` (one schema set per developer or PR), `PROD` (deploys only)
   - **Roles:** `LOADER` → `TRANSFORMER` → `REPORTER`, least privilege, with future grants so new tables are covered
   - **Warehouses:** `LOAD_WH`, `TRANSFORM_WH`, `BI_WH`, all X-Small with 60-second auto-suspend
   - **Resource monitor:** notify at 50%, suspend at 75%, kill at 95%
   - **Service users** `dlt_user`, `dbt_user`, `lightdash_user`: **key-pair only, no passwords**
3. Generate keys and attach them:
   ```powershell
   $env:SNOWFLAKE_PRIVATE_KEY_PASSPHRASE = "<choose one>"
   .\.venv\Scripts\python.exe snowflake\generate_keypair.py dlt_user dbt_user lightdash_user
   # paste the printed ALTER USER statements into a worksheet
   ```
   Private keys go to `~/.snowflake/keys/`, outside the repo. `*.p8` is git-ignored and pre-commit blocks private keys.
4. Set the session env vars and load:
   ```powershell
   $env:SNOWFLAKE_ACCOUNT = "<account identifier>"
   $env:SNOWFLAKE_LOADER_PRIVATE_KEY_PATH = "$HOME\.snowflake\keys\dlt_user.p8"
   $env:SNOWFLAKE_PRIVATE_KEY_PATH = "$HOME\.snowflake\keys\dbt_user.p8"
   .\snowflake\full_load.ps1 -Step load
   .\snowflake\full_load.ps1 -Step build
   ```

## Environments

| Target | Database | Schemas | Who |
|---|---|---|---|
| `dev` (DuckDB) | local file | `dev_staging`, `dev_marts`, ... | everyday development, free |
| `sf_dev` | `DEV` | `<DBT_DEV_SCHEMA>_staging`, `_marts`, ... | testing on Snowflake |
| `ci` | `DEV` | `ci_pr_<n>_*` | GitHub Actions (Phase 7) |
| `prod` | `PROD` | `staging`, `marts`, ... | deploys only |

`macros/generate_schema_name.sql` produces clean schema names in prod and prefixed ones everywhere else. Prod also lives in its own database, so a dev run can never overwrite it.

## Tuning checklist

- [x] Query profile of a typical dashboard query on `fct_sales_lines`: clustered on `business_date`, a one-month query scans 3 of 68 partitions vs 85 of 85 unclustered → [`docs/cost.md`](../docs/cost.md#clustering-fct_sales_lines)
- [x] Credits for the full build and for one incremental day → [`docs/cost.md`](../docs/cost.md)
- [x] First incremental run after the full build: only the 3-day window is rewritten (164k of 23.9M sales lines). `fct_inventory_daily` still computes its full upstream window, which is a known tuning opportunity (see cost.md)
