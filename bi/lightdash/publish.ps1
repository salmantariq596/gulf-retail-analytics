# Regenerate the dashboard YAML (dashboards.py) and upload it to the local Lightdash.
#   .\bi\lightdash\publish.ps1
# Content in Lightdash is replaced by the files here: edit dashboards.py, not the UI.
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$dotenv = @{}
Get-Content (Join-Path $PSScriptRoot '.env') | Where-Object { $_ -match '^\s*([^#=]+)=(.*)$' } | ForEach-Object { $dotenv[$Matches[1].Trim()] = $Matches[2].Trim() }

$env:LIGHTDASH_URL = 'http://localhost:8080'
$env:LIGHTDASH_API_KEY = $dotenv['LD_ADMIN_API_KEY']
$env:LIGHTDASH_PROJECT = $dotenv['LD_PROJECT_UUID']
$env:CI = 'true'
$env:NODE_OPTIONS = '--experimental-require-module --no-warnings'

& "$root\.venv\Scripts\python.exe" (Join-Path $PSScriptRoot 'dashboards.py')
if ($LASTEXITCODE -ne 0) { throw 'dashboards.py failed' }

# `lightdash upload` needs Node 24+; run the pinned CLI from a small image (cli.Dockerfile)
# instead of requiring a newer Node on this machine.
$ErrorActionPreference = 'Continue'   # docker and the CLI log to stderr
$image = 'najm-lightdash-cli:3.392.0'
docker image inspect $image *> $null
if ($LASTEXITCODE -ne 0) {
    docker build -q -f (Join-Path $PSScriptRoot 'cli.Dockerfile') -t $image $PSScriptRoot 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw 'building the Lightdash CLI image failed' }
}
docker run --rm -v "$(Join-Path $PSScriptRoot 'content'):/content" `
    -e LIGHTDASH_URL=http://host.docker.internal:8080 -e LIGHTDASH_API_KEY -e LIGHTDASH_PROJECT -e CI=true `
    $image upload --force --include-charts --path /content 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { throw "lightdash upload failed ($LASTEXITCODE)" }
