param(
    [string]$DistPath = "dist",
    [string]$WorkPath = "build/pyinstaller",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$venvPython = if ($PythonPath) {
    $PythonPath
} else {
    Join-Path $projectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path $venvPython)) {
    throw "Missing .venv. Create the Windows virtual environment first."
}

$arguments = @(
    "-m",
    "PyInstaller",
    "build\ai_quiz_overlay.spec",
    "--noconfirm",
    "--clean",
    "--distpath",
    $DistPath,
    "--workpath",
    $WorkPath
)
& $venvPython @arguments

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$bundlePath = Join-Path $projectRoot $DistPath
$exe = Join-Path (Join-Path $bundlePath "奶蛙的荣光") "奶蛙的荣光.exe"
Write-Output ("BuiltExe=" + $exe)
& (Join-Path $PSScriptRoot "check_pe_arch.ps1") -ExePath $exe
& (Join-Path $PSScriptRoot "check_branding.ps1") -ExePath $exe
