[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot 'backend'
$frontendRoot = Join-Path $repoRoot 'frontend'

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found."
    }
}

function Initialize-EnvFile {
    param(
        [Parameter(Mandatory)][string]$Example,
        [Parameter(Mandatory)][string]$Target
    )

    if (-not (Test-Path -LiteralPath $Target)) {
        Copy-Item -LiteralPath $Example -Destination $Target
    }
}

Assert-Command docker
Assert-Command uv
Assert-Command npm.cmd
Assert-Command node

Initialize-EnvFile (Join-Path $repoRoot '.env.example') (Join-Path $repoRoot '.env')
Initialize-EnvFile (Join-Path $backendRoot '.env.example') (Join-Path $backendRoot '.env')
Initialize-EnvFile (Join-Path $frontendRoot '.env.example') (Join-Path $frontendRoot '.env')

Push-Location $repoRoot
try {
    docker compose up -d --wait
}
finally {
    Pop-Location
}

Push-Location $backendRoot
try {
    uv sync --all-groups
    uv run alembic upgrade head
}
finally {
    Pop-Location
}

$frontendModules = Join-Path $frontendRoot 'node_modules'
if (-not (Test-Path -LiteralPath $frontendModules)) {
    Push-Location $frontendRoot
    try {
        npm ci
    }
    finally {
        Pop-Location
    }
}

$backendProcess = $null
$workerProcess = $null
$frontendProcess = $null

try {
    $backendProcess = Start-Process `
        -FilePath (Get-Command uv).Source `
        -ArgumentList @(
            'run', 'uvicorn', 'app.main:app',
            '--host', '127.0.0.1',
            '--port', '18000',
            '--reload'
        ) `
        -WorkingDirectory $backendRoot `
        -NoNewWindow `
        -PassThru

    $workerProcess = Start-Process `
        -FilePath (Get-Command uv).Source `
        -ArgumentList @(
            'run', 'celery',
            '-A', 'app.workers.celery_app:celery_app',
            'worker', '--loglevel=info', '--pool=solo',
            '-Q', 'ingestion,evaluation'
        ) `
        -WorkingDirectory $backendRoot `
        -NoNewWindow `
        -PassThru

    $apiReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($backendProcess.HasExited) {
            throw "Backend exited with code $($backendProcess.ExitCode)."
        }
        try {
            $health = Invoke-RestMethod `
                -Uri 'http://127.0.0.1:18000/api/health' `
                -TimeoutSec 2
            if ($health.status -eq 'ok') {
                $apiReady = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $apiReady) {
        throw 'Backend health check did not become ready within 30 seconds.'
    }

    $frontendProcess = Start-Process `
        -FilePath (Get-Command node).Source `
        -ArgumentList @('node_modules/vite/bin/vite.js') `
        -WorkingDirectory $frontendRoot `
        -NoNewWindow `
        -PassThru

    Write-Host ''
    Write-Host 'DocMind is running:' -ForegroundColor Green
    Write-Host '  Frontend: http://127.0.0.1:15173'
    Write-Host '  API:      http://127.0.0.1:18000/api/health'
    Write-Host '  Worker:   Celery ingestion worker'
    Write-Host 'Press Ctrl+C to stop API, worker, and frontend processes.'

    while (
        -not $backendProcess.HasExited -and
        -not $workerProcess.HasExited -and
        -not $frontendProcess.HasExited
    ) {
        Start-Sleep -Seconds 1
        $backendProcess.Refresh()
        $workerProcess.Refresh()
        $frontendProcess.Refresh()
    }

    if ($backendProcess.HasExited) {
        throw "Backend exited with code $($backendProcess.ExitCode)."
    }
    if ($workerProcess.HasExited) {
        throw "Worker exited with code $($workerProcess.ExitCode)."
    }
    if ($frontendProcess.HasExited) {
        throw "Frontend exited with code $($frontendProcess.ExitCode)."
    }
}
finally {
    if ($null -ne $backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id
    }
    if ($null -ne $workerProcess -and -not $workerProcess.HasExited) {
        Stop-Process -Id $workerProcess.Id
    }
    if ($null -ne $frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id
    }
}
