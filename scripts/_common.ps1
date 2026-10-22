# Shared helpers, dot-sourced by the other scripts. Compatible with Windows PowerShell 5.1 and PowerShell 7.
$ErrorActionPreference = "Stop"

$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:BackendDir = Join-Path $script:RepoRoot "backend"
$script:FrontendDir = Join-Path $script:RepoRoot "frontend"

function Test-OnWindows {
    # $IsWindows does not exist in Windows PowerShell 5.1, which only runs on Windows.
    return ($PSVersionTable.PSEdition -eq "Desktop") -or [bool]$IsWindows
}

function Get-VenvPython {
    if (Test-OnWindows) { return Join-Path $script:BackendDir ".venv\Scripts\python.exe" }
    return Join-Path $script:BackendDir ".venv/bin/python"
}

function Assert-VenvPython {
    $python = Get-VenvPython
    if (-not (Test-Path $python)) {
        throw "Python virtual environment not found at $python. Run scripts\setup.ps1 first."
    }
    return $python
}

# Runs a native command and throws if it exits with a nonzero code.
# PowerShell does not stop on native-command failures by itself.
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$What,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )
    $global:LASTEXITCODE = 0
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$What failed with exit code $LASTEXITCODE."
    }
}

function Write-Failure {
    param([Parameter(Mandatory = $true)]$ErrorRecord)
    Write-Host "FAILED: $($ErrorRecord.Exception.Message)" -ForegroundColor Red
}
