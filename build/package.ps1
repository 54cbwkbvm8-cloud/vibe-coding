param(
    [string]$BundlePath = "dist/奶蛙的荣光",
    [string]$ZipPath = "outputs/奶蛙的荣光_v1.0.0_onedir.zip"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Create the Windows virtual environment first."
}

& $python `
    (Join-Path $projectRoot "build\package.py") `
    --bundle $BundlePath `
    --zip $ZipPath
if ($LASTEXITCODE -ne 0) {
    throw "Packaging failed with exit code $LASTEXITCODE"
}
