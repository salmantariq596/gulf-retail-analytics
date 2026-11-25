# Deploy the dbt project's explores and metrics to the local Lightdash, against PROD.
#   .\bi\lightdash\deploy.ps1            # update the existing project
#   .\bi\lightdash\deploy.ps1 -Create    # first time: create the project
# Lightdash connects to Snowflake as lightdash_user (role REPORTER, read-only on PROD).
param([switch]$Create)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$envFile = Join-Path $PSScriptRoot '.env'

# Secrets come from the Windows user environment and bi/lightdash/.env, never the repo
foreach ($k in 'SNOWFLAKE_ACCOUNT', 'SNOWFLAKE_PRIVATE_KEY_PASSPHRASE') {
    Set-Item "env:$k" ([Environment]::GetEnvironmentVariable($k, 'User'))
}
$env:SNOWFLAKE_LIGHTDASH_PRIVATE_KEY_PATH = Join-Path $HOME '.snowflake\keys\lightdash_user.p8'
# The CLI renders profiles.yml before parsing it as YAML, where "C:\Users" is an invalid
# escape: (and the parse error echoes the rendered file, secrets included). Forward slashes.
foreach ($k in 'SNOWFLAKE_PRIVATE_KEY_PATH', 'SNOWFLAKE_LOADER_PRIVATE_KEY_PATH', 'SNOWFLAKE_LIGHTDASH_PRIVATE_KEY_PATH') {
    $v = [Environment]::GetEnvironmentVariable($k, 'Process')
    if (-not $v) { $v = [Environment]::GetEnvironmentVariable($k, 'User') }
    if ($v) { Set-Item "env:$k" ($v -replace '\\', '/') }
}
$dotenv = @{}
Get-Content $envFile | Where-Object { $_ -match '^\s*([^#=]+)=(.*)$' } | ForEach-Object { $dotenv[$Matches[1].Trim()] = $Matches[2].Trim() }

$env:LIGHTDASH_URL = 'http://localhost:8080'
$env:LIGHTDASH_API_KEY = $dotenv['LD_ADMIN_API_KEY']
$env:CI = 'true'                                   # no interactive prompts
$env:NODE_OPTIONS = '--experimental-require-module --no-warnings'  # CLI needs require(esm) on Node < 22.12
$env:PATH = "$root\.venv\Scripts;$env:PATH"         # the CLI runs the project's dbt

# Generated metric tables must match the MetricFlow definitions before they are published
python "$root\scripts\semantic_export.py" --check
if ($LASTEXITCODE -ne 0) { throw 'Lightdash export is stale: run python scripts/semantic_export.py' }

# dbt and the CLI log warnings to stderr; judge success by exit code, not by stderr output
$ErrorActionPreference = 'Continue'
$dbtDir = Join-Path $root 'dbt'
# Only the marts are for consumers; staging/intermediate models stay out of Lightdash
$common = @('--project-dir', $dbtDir, '--profiles-dir', $dbtDir, '--target', 'lightdash', '--select', 'path:models/marts')
if ($Create) {
    lightdash deploy --create 'Gulf Retail (PROD)' @common
} else {
    if ($dotenv['LD_PROJECT_UUID']) { $env:LIGHTDASH_PROJECT = $dotenv['LD_PROJECT_UUID'] }
    lightdash deploy @common
}
if ($LASTEXITCODE -ne 0) { throw "lightdash deploy failed ($LASTEXITCODE)" }
