# Runs backend tests, then the frontend typecheck and production build. Stops at the first failure.
#   powershell -ExecutionPolicy Bypass -File scripts\check.ps1
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    $python = Assert-VenvPython
    Set-Location $BackendDir
    Invoke-Native "Backend tests" { & $python -m pytest }
    Set-Location $FrontendDir
    Invoke-Native "Frontend typecheck and build" { npm run build }
    Write-Host "All checks passed." -ForegroundColor Green
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
