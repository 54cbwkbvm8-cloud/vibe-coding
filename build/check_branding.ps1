param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,
    [string]$IconOutput = "work/阶段6_exe_icon.png"
)

$ErrorActionPreference = "Stop"
$resolvedExe = (Resolve-Path $ExePath).Path
$info = (Get-Item $resolvedExe).VersionInfo

$expected = @{
    FileDescription = "奶蛙的荣光"
    FileVersion = "1.0.0.0"
    ProductName = "奶蛙的荣光"
    ProductVersion = "1.0.0.0"
    OriginalFilename = "奶蛙的荣光.exe"
}

foreach ($name in $expected.Keys) {
    $actual = $info.$name
    Write-Output ("Version_" + $name + "=" + $actual)
    if ($actual -ne $expected[$name]) {
        throw "Unexpected $name. Expected '$($expected[$name])', got '$actual'."
    }
}

Add-Type -AssemblyName System.Drawing
$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($resolvedExe)
if ($null -eq $icon) {
    throw "No executable icon could be extracted."
}

$outputPath = [System.IO.Path]::GetFullPath(
    (Join-Path (Split-Path -Parent $PSScriptRoot) $IconOutput)
)
$outputDirectory = Split-Path -Parent $outputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$bitmap = $icon.ToBitmap()
$bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
$bitmap.Dispose()
$icon.Dispose()

Write-Output ("ExtractedIcon=" + $outputPath)
