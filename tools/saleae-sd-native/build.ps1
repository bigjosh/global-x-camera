[CmdletBinding()]
param(
    [string]$BuildDirectory = (Join-Path $PSScriptRoot 'build'),
    [string]$SdkRoot = '',
    [switch]$CoreOnly,
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
$configure = @('-S', $PSScriptRoot, '-B', $BuildDirectory,
               '-G', 'Visual Studio 17 2022', '-A', 'x64')
if ($SdkRoot) { $configure += "-DSALEAE_SDK_ROOT=$SdkRoot" }
$configure += "-DSD_BUILD_PLUGIN=$(if ($CoreOnly) { 'OFF' } else { 'ON' })"
if ($Python) { $configure += "-DPython3_EXECUTABLE=$Python" }
& cmake @configure
if ($LASTEXITCODE) { throw "CMake configure failed: $LASTEXITCODE" }
& cmake --build $BuildDirectory --config Release
if ($LASTEXITCODE) { throw "Build failed: $LASTEXITCODE" }
& ctest --test-dir $BuildDirectory -C Release --output-on-failure
if ($LASTEXITCODE) { throw "Decoder tests failed: $LASTEXITCODE" }
if (!$CoreOnly) {
    Write-Output "Logic 2 analyzer directory: $(Join-Path $BuildDirectory 'Analyzers\Release')"
}
