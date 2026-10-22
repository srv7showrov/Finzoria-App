# Creates a source archive of the committed code only (git archive), so local secrets
# (backend\.env), databases, node_modules, virtual environments and builds are never included.
# Output: release\finzoria-source-<commit>.zip
#   powershell -ExecutionPolicy Bypass -File scripts\package-source.ps1
. (Join-Path $PSScriptRoot "_common.ps1")

$startDir = Get-Location
$exitCode = 0
try {
    Set-Location $RepoRoot
    $global:LASTEXITCODE = 0
    $commit = (git rev-parse --short HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Not a Git repository." }
    $dirty = git status --porcelain
    if ($dirty) { Write-Host "Note: uncommitted changes are NOT included in the archive." -ForegroundColor Yellow }
    New-Item -ItemType Directory -Force -Path "release" | Out-Null
    $out = Join-Path "release" "finzoria-source-$commit.zip"
    Invoke-Native "git archive" { git archive --format=zip --prefix="finzoria/" --output=$out HEAD }
    Write-Host "Created $out" -ForegroundColor Green
} catch {
    Write-Failure $_
    $exitCode = 1
} finally {
    Set-Location $startDir
}
exit $exitCode
