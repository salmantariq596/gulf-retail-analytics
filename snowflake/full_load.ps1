<#
.SYNOPSIS
    Phase 5: generate the full 3-year dataset and load it into Snowflake RAW.

.DESCRIPTION
    Runs NEXT TO the 3-month dev dataset, never over it:
      Postgres database  najm_pos_full          (dev: najm_pos)
      landing files      data/landing_full       (dev: data/landing)
      generator state    data/generator_state/full.pkl
      mock API           port 8001               (dev: 8000)

    Steps (each can be run on its own with -Step):
      generate   ~2.5 h, no Snowflake needed: do this BEFORE starting the trial
      load       dlt -> Snowflake RAW (needs the trial, keys and env vars below)
      build      dbt build --target prod

    Needs ~6 GB free on the drive that holds Docker's disk image.

    Env vars for load/build (set them in your session, never in a file in the repo):
      SNOWFLAKE_ACCOUNT                   e.g. xy12345.me-central2.gcp
      SNOWFLAKE_LOADER_PRIVATE_KEY_PATH   ~/.snowflake/keys/dlt_user.p8
      SNOWFLAKE_PRIVATE_KEY_PATH          ~/.snowflake/keys/dbt_user.p8
      SNOWFLAKE_PRIVATE_KEY_PASSPHRASE

.EXAMPLE
    .\snowflake\full_load.ps1 -Step generate
    .\snowflake\full_load.ps1 -Step load
    .\snowflake\full_load.ps1 -Step build
#>
param(
    [ValidateSet("generate", "resume", "load", "build")]
    [Parameter(Mandatory = $true)]
    [string]$Step
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$env:PYTHONIOENCODING = "utf-8"

# Full-scale dataset lives beside the dev one
$env:POSTGRES_DB = "najm_pos_full"
$env:GEN_OUTPUT_DIR = "data/landing_full"
$env:GEN_STATE_PATH = "data/generator_state/full.pkl"
$env:MOCK_API_BASE_URL = "http://127.0.0.1:8001"

switch ($Step) {
    "generate" {
        # state is saved after every day, so an interrupted run can continue with -Step resume
        $t = Get-Date
        .\.venv\Scripts\najm-gen.exe backfill --profile full --checkpoint-every 1
        "Generated in {0:N0} min" -f ((Get-Date) - $t).TotalMinutes
    }
    "resume" {
        $t = Get-Date
        .\.venv\Scripts\najm-gen.exe run --checkpoint-every 1
        "Resumed run finished in {0:N0} min" -f ((Get-Date) - $t).TotalMinutes
    }
    "load" {
        foreach ($v in "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_LOADER_PRIVATE_KEY_PATH") {
            if (-not (Get-Item "env:$v" -ErrorAction SilentlyContinue)) { throw "Set $v first" }
        }
        $env:NAJM_WAREHOUSE = "snowflake"
        $env:ONLINE_DATA_DIR = (Resolve-Path "data/landing_full/online").Path
        $api = Start-Process -PassThru -WindowStyle Hidden .\.venv\Scripts\python.exe `
            -ArgumentList "-m", "uvicorn", "mock_api.main:app", "--app-dir", "generator", "--port", "8001"
        try {
            Start-Sleep -Seconds 4
            $t = Get-Date
            .\.venv\Scripts\najm-ingest.exe all
            "Loaded in {0:N0} min" -f ((Get-Date) - $t).TotalMinutes
        }
        finally { Stop-Process -Id $api.Id -ErrorAction SilentlyContinue }
    }
    "build" {
        foreach ($v in "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_PRIVATE_KEY_PATH") {
            if (-not (Get-Item "env:$v" -ErrorAction SilentlyContinue)) { throw "Set $v first" }
        }
        Set-Location dbt
        $env:DBT_TARGET = "prod"
        ..\.venv\Scripts\dbt.exe deps
        ..\.venv\Scripts\dbt.exe source freshness
        $t = Get-Date
        ..\.venv\Scripts\dbt.exe build --full-refresh
        "Built in {0:N0} min; record the credits in docs/cost.md" -f ((Get-Date) - $t).TotalMinutes
    }
}
