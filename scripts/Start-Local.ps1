param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDirectory = Join-Path $projectRoot '.local'
$localEnv = Join-Path $localDirectory 'cityhive.env'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop is required. Install it, start it, and rerun this script.'
}

function Test-DockerReady {
    & docker info --format '{{.ServerVersion}}' *> $null
    return $LASTEXITCODE -eq 0
}

if (-not (Test-DockerReady)) {
    $desktopCandidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'),
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')
    )
    $desktopExecutable = $desktopCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $desktopExecutable) { throw 'Start Docker Desktop and rerun this script.' }
    Start-Process -FilePath $desktopExecutable -WindowStyle Hidden
    Write-Host 'Waiting for Docker Desktop...'
    $readyDeadline = (Get-Date).AddMinutes(3)
    while (-not (Test-DockerReady)) {
        if ((Get-Date) -gt $readyDeadline) { throw 'Docker did not become ready. Check Docker Desktop, then rerun.' }
        Start-Sleep -Seconds 2
    }
}

function New-LocalSecret([int]$ByteCount) {
    $randomBytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($randomBytes).Replace('+','-').Replace('/','_')
}

if (-not (Test-Path -LiteralPath $localEnv)) {
    & docker volume inspect cityhive-local_local_db *> $null
    if ($LASTEXITCODE -eq 0) {
        throw 'Existing Cityhive local data was found without its configuration. Restore .local\cityhive.env from your backup; do not generate replacement database or document keys.'
    }
    if (-not (Test-Path -LiteralPath $localDirectory)) {
        New-Item -ItemType Directory -Path $localDirectory | Out-Null
    }
    $localDbPassword = (New-LocalSecret 30).TrimEnd('=')
    $localJwtSecret = (New-LocalSecret 48).TrimEnd('=')
    $localOwnerPassword = (New-LocalSecret 24).TrimEnd('=')
    $documentKey = New-LocalSecret 32
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $environmentText = @"
POSTGRES_PASSWORD=$localDbPassword
JWT_SECRET=$localJwtSecret
ADMIN_EMAIL=owner@cityhive.local
ADMIN_PASSWORD=$localOwnerPassword
IDENTITY_DOCUMENT_KEY=$documentKey
"@
    [System.IO.File]::WriteAllText($localEnv, $environmentText + "`n", $utf8)
    $loginText = @"
CITYHIVE LOCAL WORKSPACE
App: http://127.0.0.1:5179/
Owner email: owner@cityhive.local
Initial password: $localOwnerPassword

Choose WhatsApp at sign-in. The LOCAL test code arrives in:
http://127.0.0.1:8025/
Open the newest Cityhive local sign-in code email and enter its code.
No real WhatsApp/SMS is sent. All email stays in the local inbox.

This is the initial password; changing it in the app makes this note outdated.
Keep cityhive.env private and backed up with your local data. Its document key
is needed to read stored identity documents. Rerunning Start-Local preserves it.
"@
    [System.IO.File]::WriteAllText((Join-Path $localDirectory 'login.txt'), $loginText + "`n", $utf8)
    Write-Host 'Created private local configuration and initial owner sign-in instructions.'
}

$composeArguments = @('compose', '--project-name', 'cityhive-local', '--project-directory', $projectRoot,
    '--env-file', $localEnv, '-f', (Join-Path $projectRoot 'compose.local.yaml'))
$startArguments = @('up', '-d', '--wait', '--wait-timeout', '180')
if (-not $SkipBuild) { $startArguments += '--build' }
& docker @composeArguments @startArguments
if ($LASTEXITCODE -ne 0) { throw 'Local startup failed. Check the service output above; existing data and configuration were preserved.' }

Write-Host ''
Write-Host 'Cityhive is running: http://127.0.0.1:5179/'
Write-Host 'Local OTP/email inbox: http://127.0.0.1:8025/'
Write-Host ('Owner sign-in details: ' + (Join-Path $localDirectory 'login.txt'))
Write-Host 'Stop with scripts\Stop-Local.ps1. Data survives stops and restarts.'
