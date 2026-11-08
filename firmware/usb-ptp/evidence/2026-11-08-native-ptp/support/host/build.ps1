param([string]$OutDir = (Join-Path $PSScriptRoot '..\..\..\tmp\usb-ptp-host'))
$ErrorActionPreference = 'Stop'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'MSVC x64 build tools are not installed.' }
$msvc = Get-ChildItem (Join-Path $vs 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Include') -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'um\PortableDeviceApi.h') } | Sort-Object Name -Descending | Select-Object -First 1
if (-not $sdk) { throw 'Windows SDK with PortableDeviceApi.h is not installed.' }
$OutDir = [IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
$savedPath = $env:PATH
try {
    $env:INCLUDE = @((Join-Path $msvc.FullName 'include'),(Join-Path $sdk.FullName 'ucrt'),(Join-Path $sdk.FullName 'shared'),(Join-Path $sdk.FullName 'um'),(Join-Path $sdk.FullName 'winrt')) -join ';'
    $env:LIB = @((Join-Path $msvc.FullName 'lib\x64'),(Join-Path $sdkRoot "Lib\$($sdk.Name)\ucrt\x64"),(Join-Path $sdkRoot "Lib\$($sdk.Name)\um\x64")) -join ';'
    $bin = Join-Path $msvc.FullName 'bin\Hostx64\x64'
    $env:PATH = "$bin;$savedPath"
    & (Join-Path $bin 'cl.exe') /nologo /std:c++17 /EHsc /W4 /O2 /utf-8 /DUNICODE /D_UNICODE (Join-Path $PSScriptRoot 'wpd_camera.cpp') "/Fe:$OutDir\wpd_camera.exe" "/Fo:$OutDir\wpd_camera.obj" /link ole32.lib oleaut32.lib PortableDeviceGuids.lib propsys.lib windowscodecs.lib
    if ($LASTEXITCODE -ne 0) { throw "Compiler failed: $LASTEXITCODE" }
    & (Join-Path $OutDir 'wpd_camera.exe') selftest
    if ($LASTEXITCODE -ne 0) { throw 'Offline self-test failed.' }
    Get-FileHash (Join-Path $OutDir 'wpd_camera.exe') -Algorithm SHA256
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
    $env:PATH = $savedPath
}
