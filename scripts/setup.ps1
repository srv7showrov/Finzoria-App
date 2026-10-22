# Finzoria one-time setup. Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# "-ExecutionPolicy Bypass" applies to this one command only; it does not change system settings.
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    Set-Location $BackendDir
    $python = Get-VenvPython
    if (-not (Test-Path $python)) {
        if (Test-OnWindows) {
            Invoke-Native "Creating the Python virtual environment" { py -3 -m venv .venv }
        } else {
            Invoke-Native "Creating the Python virtual environment" { python3 -m venv .venv }
        }
    }
    Invoke-Native "Installing Python packages" { & $python -m pip install -r requirements-dev.txt }
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Created backend\.env from .env.example. Add your key there in an editor (never in chat)."
    }

    Set-Location $FrontendDir
    Invoke-Native "Installing frontend packages (npm ci)" { npm ci }

    Write-Host "Setup complete." -ForegroundColor Green
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
