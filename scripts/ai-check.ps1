# One small real model request with the provider selected in backend\.env (FINZORIA_AI_PROVIDER). Never prints the key.
# Exit codes: 0 = PASSED (usable text), 1 = FAILED, 2 = NOT RUN (not configured / local guard),
# 3 = CONNECTED BUT NO USABLE TEXT (request worked, reply had no text; finish reason and token counts are printed).
#   powershell -ExecutionPolicy Bypass -File scripts\ai-check.ps1
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    $python = Assert-VenvPython
    Set-Location $BackendDir
    $env:PYTHONUNBUFFERED = "1"  # progress lines appear immediately
    $global:LASTEXITCODE = 0
    & $python -u (Join-Path "scripts" "ai_smoke_test.py")
    $exitCode = $LASTEXITCODE
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
