# Development: FastAPI on :8000 in a new window, Vite on http://localhost:5173 (proxies /api).
# Close the backend window when you are finished.
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    $python = Assert-VenvPython
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        throw "Frontend packages are not installed. Run scripts\setup.ps1 first."
    }
    $shell = if (Test-OnWindows) { "powershell" } else { "pwsh" }
    $backendCommand = "Set-Location -LiteralPath '$BackendDir'; & '$python' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
    Start-Process $shell -ArgumentList "-NoExit", "-Command", $backendCommand | Out-Null
    Set-Location $FrontendDir
    Invoke-Native "Vite dev server" { npm run dev }
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
