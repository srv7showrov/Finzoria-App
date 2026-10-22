# Real-agent acceptance demo (temporary database, simulation clock) using backend\.env. Never prints the key.
# Exit codes: 0 = PASSED, 1 = FAILED, 2 = NOT RUN (credentials not configured), 130 = interrupted (Ctrl+C).
# Prints progress for every stage. Uses roughly 10-20 model requests; try scripts\tool-check.ps1 first.
#   powershell -ExecutionPolicy Bypass -File scripts\agent-demo.ps1
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    $python = Assert-VenvPython
    Set-Location $BackendDir
    $env:PYTHONUNBUFFERED = "1"  # progress lines appear immediately
    $global:LASTEXITCODE = 0
    & $python -u (Join-Path "scripts" "agent_demo.py")
    $exitCode = $LASTEXITCODE
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
