param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath
)

$resolved = (Resolve-Path $ExePath).Path
$bytes = [IO.File]::ReadAllBytes($resolved)
$peOffset = [BitConverter]::ToInt32($bytes, 0x3C)
$machine = [BitConverter]::ToUInt16($bytes, $peOffset + 4)
$machineHex = "{0:X4}" -f $machine
$optionalHeaderOffset = $peOffset + 24
$optionalMagic = [BitConverter]::ToUInt16($bytes, $optionalHeaderOffset)
$subsystem = [BitConverter]::ToUInt16($bytes, $optionalHeaderOffset + 68)

Write-Output ("ExePath=" + $resolved)
Write-Output ("PEMachine=" + $machineHex)
Write-Output ("OptionalHeaderMagic=" + ("0x{0:X4}" -f $optionalMagic))
Write-Output ("Subsystem=" + $subsystem)

if ($machineHex -eq "8664" -and $subsystem -eq 2) {
    Write-Output "Architecture=X64"
    Write-Output "WindowMode=WindowsGUI"
    exit 0
}

if ($machineHex -eq "AA64") {
    Write-Output "Architecture=ARM64"
} else {
    Write-Output "Architecture=UNKNOWN"
}
exit 1
