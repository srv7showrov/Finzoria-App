# Deterministic fixture run (no AI model, temporary database). Writes docs\evidence\fixture-run.md.
# Exit codes: 0 = PASSED, 1 = FAILED.
#   powershell -ExecutionPolicy Bypass -File scripts\fixture-run.ps1
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    $python = Assert-VenvPython
    Set-Location $BackendDir
    $global:LASTEXITCODE = 0
    & $python (Join-Path "scripts" "fixture_run.py")
    $exitCode = $LASTEXITCODE
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
