param(
    [string]$BundlePath = "dist/奶蛙的荣光",
    [string]$WorkPath = "build/pyinstaller"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $BundlePath).Path
$files = Get-ChildItem $root -Recurse -File
$total = $files | Measure-Object -Property Length -Sum

Write-Output ("BundlePath=" + $root)
Write-Output ("FileCount=" + $total.Count)
Write-Output ("TotalBytes=" + $total.Sum)

$requiredPatterns = @(
    "奶蛙的荣光.exe",
    "python311.dll",
    "Qt6Core.dll",
    "qwindows.dll",
    "logo@1x.png",
    "logo@2x.png",
    "logo@3x.png",
    "assistant_ball_1024.png",
    "assistant_ball@1x.png",
    "assistant_ball@2x.png",
    "assistant_ball@3x.png",
    "app_icon.ico",
    "THIRD_PARTY_NOTICES.md",
    "onnxruntime.dll",
    "sherpa-onnx-c-api.dll",
    "libportaudio64bit.dll",
    "_webrtcvad.cp311-win_amd64.pyd",
    "_cffi_backend.cp311-win_amd64.pyd"
)
foreach ($pattern in $requiredPatterns) {
    $found = $files | Where-Object { $_.Name -eq $pattern } | Select-Object -First 1
    Write-Output ("Required_" + $pattern + "=" + [bool]$found)
    if (-not $found) {
        throw "Missing required bundle file: $pattern"
    }
}

$forbiddenNames = @(
    "config.json",
    "api_key.bin",
    ".env",
    "settings.json",
    "app.log",
    "app.log.1",
    "app.log.2",
    "app.log.3",
    "model.int8.onnx",
    "tokens.txt",
    "official-web-host.exe",
    "official-web-manifest.json",
    "official-web-component.zip",
    "official_web_browser_host.py",
    "official_web_diagnostics.py",
    "official_web_diagnostic_build.py",
    "QtWebEngineProcess.exe",
    "Qt6WebEngineCore.dll",
    "Qt6WebEngineQuick.dll",
    "Qt6WebChannel.dll",
    "stage14_soak_results.json",
    "voice-selftest.json"
)
$forbidden = $files | Where-Object {
    $_.Name -in $forbiddenNames -or
    (
        $_.Extension -in @(".lnk", ".wav", ".mp3", ".m4a") -or
        ($_.Extension -eq ".zip" -and $_.Name -ne "base_library.zip")
    ) -or
    $_.FullName -match (
        "\\work\\|\\personalization\\|\\web_session\\|" +
        "\\screenshot\\|截图|录音|recording|probe|" +
        "\\QtWebEngine|official-web-component|" +
        "official_web_diagnostic|official_web_browser_host"
    )
}

Write-Output ("ForbiddenFileCount=" + @($forbidden).Count)
if (@($forbidden).Count -gt 0) {
    $forbidden | ForEach-Object {
        Write-Output ("ForbiddenPath=" + $_.FullName)
    }
    throw "Sensitive or development files were bundled."
}

$warningFile = Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) $WorkPath) "ai_quiz_overlay\warn-ai_quiz_overlay.txt"
if (Test-Path $warningFile) {
    $criticalWarnings = Get-Content $warningFile |
        Select-String -Pattern "missing module named (ai_quiz_overlay|PySide6|httpx)"
    Write-Output ("CriticalImportWarningCount=" + @($criticalWarnings).Count)
    if (@($criticalWarnings).Count -gt 0) {
        $criticalWarnings
    }
}
