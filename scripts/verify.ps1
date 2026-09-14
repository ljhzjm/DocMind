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

function Invoke-InDirectory {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Command,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    Push-Location $Path
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed: $Command $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

Assert-Command docker
Assert-Command uv
Assert-Command npm.cmd

Invoke-InDirectory $repoRoot 'docker' @('compose', 'config', '--quiet')
Invoke-InDirectory $repoRoot 'docker' @('compose', 'up', '-d', '--wait')

Invoke-InDirectory $backendRoot 'uv' @('sync', '--all-groups')
Invoke-InDirectory $backendRoot 'uv' @('run', 'ruff', 'format', '--check', '.')
Invoke-InDirectory $backendRoot 'uv' @('run', 'ruff', 'check', '.')
Invoke-InDirectory $backendRoot 'uv' @('run', 'mypy', 'app', 'tests')
Invoke-InDirectory $backendRoot 'uv' @('run', 'pytest')

Invoke-InDirectory $frontendRoot 'npm.cmd' @('ci')
Invoke-InDirectory $frontendRoot 'npm.cmd' @('run', 'format:check')
Invoke-InDirectory $frontendRoot 'npm.cmd' @('run', 'lint')
Invoke-InDirectory $frontendRoot 'npm.cmd' @('test')
Invoke-InDirectory $frontendRoot 'npm.cmd' @('run', 'build')

Write-Host ''
Write-Host 'All DocMind verification checks passed.' -ForegroundColor Green