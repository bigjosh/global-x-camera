[CmdletBinding()]
param(
    [string]$SourceDir = (Join-Path $PSScriptRoot '../../tmp/bringup/x-cube-n6-camera-capture'),
    [string]$ToolchainBin,
    [string]$MakeExe,
    [string]$ShellExe
)

$ErrorActionPreference = 'Stop'
$SourceDir = (Resolve-Path -LiteralPath $SourceDir).Path
$pluginRoot = 'D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins'

function Find-Application([string]$Name) {
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { $command.Source }
}

function Find-PluginTool([string]$Pattern, [string]$Name) {
    if (Test-Path -LiteralPath $pluginRoot) {
        Get-ChildItem -LiteralPath $pluginRoot -Directory -Filter $Pattern |
            Sort-Object Name -Descending | ForEach-Object {
                $candidate = Join-Path $_.FullName "tools/bin/$Name"
                if (Test-Path -LiteralPath $candidate -PathType Leaf) { $candidate }
            } | Select-Object -First 1
    }
}

if (!$ToolchainBin) {
    $compiler = Find-Application 'arm-none-eabi-gcc.exe'
    if (!$compiler) { $compiler = Find-PluginTool '*gnu-tools-for-stm32*' 'arm-none-eabi-gcc.exe' }
    if (!$compiler) { throw 'Arm GCC not found. Supply -ToolchainBin with its bin directory.' }
    $ToolchainBin = Split-Path -Parent $compiler
}
if (!$MakeExe) {
    $MakeExe = Find-Application 'make.exe'
    if (!$MakeExe) { $MakeExe = Find-PluginTool '*externaltools.make.win32*' 'make.exe' }
    if (!$MakeExe) { throw 'GNU Make not found. Supply -MakeExe.' }
}
if (!$ShellExe) {
    $ShellExe = Find-Application 'sh.exe'
    if (!$ShellExe) {
        $git = Find-Application 'git.exe'
        if ($git) {
            $candidate = Join-Path (Split-Path -Parent (Split-Path -Parent $git)) 'bin/sh.exe'
            if (Test-Path -LiteralPath $candidate) { $ShellExe = $candidate }
        }
    }
    if (!$ShellExe) { throw 'Git for Windows sh not found. Supply -ShellExe.' }
}

$ToolchainBin = (Resolve-Path -LiteralPath $ToolchainBin).Path
$MakeExe = (Resolve-Path -LiteralPath $MakeExe).Path
$ShellExe = (Resolve-Path -LiteralPath $ShellExe).Path
$compiler = Join-Path $ToolchainBin 'arm-none-eabi-gcc.exe'
$nm = Join-Path $ToolchainBin 'arm-none-eabi-nm.exe'
foreach ($file in @($compiler, $nm, $MakeExe, $ShellExe, (Join-Path $SourceDir 'Src/capture_app.c'))) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required file missing: $file" }
}

$oldPath = $env:PATH
$shellDirectory = Split-Path -Parent $ShellExe
$gitUtilities = Join-Path (Split-Path -Parent $shellDirectory) 'usr/bin'
$pathEntries = @($ToolchainBin, (Split-Path -Parent $MakeExe), $shellDirectory)
if (Test-Path -LiteralPath $gitUtilities) { $pathEntries += $gitUtilities }

Push-Location -LiteralPath $SourceDir
try {
    # Process-only PATH makes recipes find GCC and Git's mkdir without changing
    # machine/user settings. A basename avoids spaces in make's SHELL value.
    $env:PATH = ($pathEntries -join ';') + ';' + $oldPath
    & $MakeExe 'BOARD=NUCLEO-N657X0-Q' 'SENSOR_LIST=VD56G3' '-j8' "SHELL=$(Split-Path -Leaf $ShellExe)"
    if ($LASTEXITCODE -ne 0) { throw "Build failed (exit $LASTEXITCODE)." }

    $elf = Join-Path $SourceDir 'build/Project.elf'
    if (!(Test-Path -LiteralPath $elf -PathType Leaf)) { throw "Build did not produce $elf" }
    $symbols = & $nm --defined-only $elf
    if ($LASTEXITCODE -ne 0) { throw "Symbol inspection failed (exit $LASTEXITCODE)." }
    $forbidden = @($symbols | Where-Object {
        $_ -match '\b(Fuse_Programming|HAL_BSEC_OTP_Program|BSP_XSPI_NOR_(Write|Erase)\w*)$'
    })
    if ($forbidden.Count -gt 0) {
        throw "Unexpected persistent-write functions linked; do not load this image:`n$($forbidden -join "`n")"
    }
    Write-Host "Built $elf; persistent-write symbol check passed. No device accessed."
} finally {
    $env:PATH = $oldPath
    Pop-Location
}
