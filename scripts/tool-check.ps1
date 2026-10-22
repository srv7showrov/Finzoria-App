# Live read-only tool check: ONE assistant turn, at most 2 model requests (one read_financial_summary round trip +
# the final answer), on a temporary database. Verifies the tool result and the answer. Never prints the key.
# Exit codes: 0 = PASSED, 1 = FAILED, 2 = NOT RUN (credentials not configured), 130 = interrupted (Ctrl+C).
#   powershell -ExecutionPolicy Bypass -File scripts\tool-check.ps1
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    $python = Assert-VenvPython
    Set-Location $BackendDir
    $env:PYTHONUNBUFFERED = "1"  # progress lines appear immediately
    $global:LASTEXITCODE = 0
    & $python -u (Join-Path "scripts" "agent_demo.py") --tool-check
    $exitCode = $LASTEXITCODE
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
