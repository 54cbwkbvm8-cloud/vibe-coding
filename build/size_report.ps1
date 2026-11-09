param(
    [Parameter(Mandatory = $true)]
    [string]$BundlePath
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $BundlePath).Path
$files = Get-ChildItem $root -Recurse -File

$groups = @(
    @{
        Name = "Qt/PySide6"
        Pattern = "\\PySide6\\|\\shiboken6\\"
    },
    @{
        Name = "sherpa-onnx"
        Pattern = "\\sherpa_onnx\\|\\sherpa_onnx-.*dist-info\\"
    },
    @{
        Name = "PortAudio"
        Pattern = "_sounddevice_data\\portaudio-binaries\\"
    },
    @{
        Name = "WebRTC VAD / cffi"
        Pattern = "_webrtcvad|webrtcvad_wheels|_cffi_backend"
    },
    @{
        Name = "Python runtime"
        Pattern = "\\python311.dll$|\\base_library.zip$|\\libcrypto"
    }
)

$rows = foreach ($group in $groups) {
    $measured = $files |
        Where-Object { $_.FullName -match $group.Pattern } |
        Measure-Object Length -Sum
    [pscustomobject]@{
        Name = $group.Name
        Files = [int]$measured.Count
        MiB = if ($null -eq $measured.Sum) {
            0
        } else {
            [math]::Round($measured.Sum / 1MB, 2)
        }
    }
}

$total = $files | Measure-Object Length -Sum
$rows += [pscustomobject]@{
    Name = "ALL"
    Files = [int]$total.Count
    MiB = [math]::Round($total.Sum / 1MB, 2)
}
$rows | Format-Table -AutoSize
