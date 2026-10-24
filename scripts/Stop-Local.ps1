$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localEnv = Join-Path $projectRoot '.local\cityhive.env'
if (-not (Test-Path -LiteralPath $localEnv)) { throw 'No local setup exists. Run scripts\Start-Local.ps1 first.' }
& docker compose --project-name cityhive-local --project-directory $projectRoot --env-file $localEnv -f (Join-Path $projectRoot 'compose.local.yaml') stop
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the local services. Inspect Docker Desktop.' }
Write-Host 'Cityhive stopped. Database, encryption key and login configuration are preserved.'
