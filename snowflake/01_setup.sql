-- =============================================================================
-- Najm Retail on Snowflake: one-time setup. Run as ACCOUNTADMIN in a worksheet.
-- Idempotent (IF NOT EXISTS / OR REPLACE where safe), so it can be re-run.
--
--   Databases   RAW (dlt writes)  ->  DEV / PROD (dbt writes)  ->  dashboards read PROD
--   Roles       LOADER            ->  TRANSFORMER              ->  REPORTER
--   Warehouses  LOAD_WH              TRANSFORM_WH                 BI_WH      (all X-Small)
--
-- Cost guardrails: X-Small only, auto-suspend after 60s, a resource monitor that
-- suspends everything at 75% of the credit budget.
-- =============================================================================

use role accountadmin;

-- -----------------------------------------------------------------------------
-- 1. Cost guardrail: resource monitor
--    Trial = $400 of credits. Set CREDIT_QUOTA to the credits your edition/region
--    buys with that (Admin > Cost Management shows the price per credit).
-- -----------------------------------------------------------------------------
create resource monitor if not exists najm_trial_monitor
    with credit_quota = 100
    frequency = never
    start_timestamp = immediately;

-- re-runnable: set quota and triggers even if the monitor already exists
alter resource monitor najm_trial_monitor set
    credit_quota = 100
    triggers
        on 50 percent do notify
        on 75 percent do suspend            -- finish running queries, then stop
        on 95 percent do suspend_immediate; -- kill running queries

-- Account level = covers every warehouse, including ones created later. (A monitor
-- set on the account cannot also be attached to individual warehouses.)
alter account set resource_monitor = najm_trial_monitor;

-- -----------------------------------------------------------------------------
-- 2. Warehouses: one per workload, so cost is attributable per purpose
-- -----------------------------------------------------------------------------
create warehouse if not exists load_wh
    warehouse_size = xsmall auto_suspend = 60 auto_resume = true initially_suspended = true
    comment = 'dlt ingestion into RAW';
create warehouse if not exists transform_wh
    warehouse_size = xsmall auto_suspend = 60 auto_resume = true initially_suspended = true
    comment = 'dbt builds (dev, CI, prod)';
create warehouse if not exists bi_wh
    warehouse_size = xsmall auto_suspend = 60 auto_resume = true initially_suspended = true
    comment = 'Lightdash dashboards and ad-hoc analysis';

-- New accounts come with COMPUTE_WH (5-minute auto-suspend), which worksheets and admin
-- sessions use by default: hold it to the same 60s guardrail.
alter warehouse if exists compute_wh set auto_suspend = 60;

-- -----------------------------------------------------------------------------
-- 3. Databases
-- -----------------------------------------------------------------------------
create database if not exists raw  comment = 'Landed source data, written only by dlt';
create database if not exists dev  comment = 'dbt development and CI schemas (one per developer / PR)';
create database if not exists prod comment = 'Production dbt models; dashboards read from here';

-- -----------------------------------------------------------------------------
-- 4. Roles (functional, least privilege) rolled up to SYSADMIN
-- -----------------------------------------------------------------------------
use role securityadmin;

create role if not exists loader      comment = 'Writes RAW (dlt)';
create role if not exists transformer comment = 'Reads RAW, writes DEV and PROD (dbt)';
create role if not exists reporter    comment = 'Reads PROD only (dashboards)';

grant role loader      to role sysadmin;
grant role transformer to role sysadmin;
grant role reporter    to role sysadmin;
grant role reporter    to role transformer;   -- dbt can test what dashboards will see

-- LOADER: owns the raw_* schemas it creates
grant usage on warehouse load_wh to role loader;
grant usage, create schema on database raw to role loader;

-- TRANSFORMER: read RAW (current and future objects), full control of DEV, build PROD
grant usage on warehouse transform_wh to role transformer;
grant usage on database raw to role transformer;
grant usage on all schemas in database raw to role transformer;
grant usage on future schemas in database raw to role transformer;
grant select on all tables in database raw to role transformer;
grant select on future tables in database raw to role transformer;
grant select on all views in database raw to role transformer;
grant select on future views in database raw to role transformer;
grant usage, create schema on database dev to role transformer;
grant usage, create schema on database prod to role transformer;

-- REPORTER: read PROD only
grant usage on warehouse bi_wh to role reporter;
grant usage on database prod to role reporter;
grant usage on future schemas in database prod to role reporter;
grant select on future tables in database prod to role reporter;
grant select on future views in database prod to role reporter;

-- -----------------------------------------------------------------------------
-- 5. Service users: key-pair authentication only (no passwords).
--    Generate keys with:  python snowflake/generate_keypair.py dlt_user dbt_user lightdash_user
--    then paste each public key below (the script prints these statements).
-- -----------------------------------------------------------------------------
create user if not exists dlt_user
    type = service default_role = loader default_warehouse = load_wh
    comment = 'dlt ingestion';
create user if not exists dbt_user
    type = service default_role = transformer default_warehouse = transform_wh
    comment = 'dbt (local prod builds, Dagster)';
create user if not exists lightdash_user
    type = service default_role = reporter default_warehouse = bi_wh
    comment = 'Lightdash dashboards';
-- GitHub Actions (slim CI + deploy). Its own key, stored only as a GitHub secret, so a
-- leaked CI secret is revoked by disabling this one user.
create user if not exists github_ci
    type = service default_role = transformer default_warehouse = transform_wh
    comment = 'GitHub Actions: slim CI and deploys';

grant role loader      to user dlt_user;
grant role transformer to user dbt_user;
grant role reporter    to user lightdash_user;
grant role transformer to user github_ci;

-- alter user dlt_user       set rsa_public_key = '<paste from generate_keypair.py>';
-- alter user dbt_user       set rsa_public_key = '<paste from generate_keypair.py>';
-- alter user lightdash_user set rsa_public_key = '<paste from generate_keypair.py>';
-- github_ci: snowflake/setup_github_ci.py generates its key in memory, sets the public key
-- and uploads the private key to the repository's GitHub secrets.

-- Your own login: give yourself the dev role. Names containing @ or . must be in
-- double quotes, and quoted names are case-sensitive (check with select current_user();)
-- grant role transformer to user "<YOUR_LOGIN_NAME>";

-- -----------------------------------------------------------------------------
-- 6. Check
-- -----------------------------------------------------------------------------
show warehouses like '%_wh';
show grants to role transformer;
