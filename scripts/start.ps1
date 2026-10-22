# Local release: build the frontend, then serve it from FastAPI at http://127.0.0.1:8000
# The server is not started if the build fails.
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    $python = Assert-VenvPython
    Set-Location $FrontendDir
    Invoke-Native "Frontend build" { npm run build }
    Set-Location $BackendDir
    Write-Host "Starting Finzoria at http://127.0.0.1:8000 (press Ctrl+C to stop)."
    Invoke-Native "Backend server" { & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 }
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
