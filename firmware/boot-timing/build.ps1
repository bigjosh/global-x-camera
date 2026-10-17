[CmdletBinding()]
param(
    [string]$ToolchainBin,
    [string]$SourceDir = (Join-Path $PSScriptRoot '../../tmp/bringup/x-cube-n6-camera-capture'),
    [string]$OutputDir = (Join-Path $PSScriptRoot 'build')
)

$ErrorActionPreference = 'Stop'
$sourcePin = 'e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a'
$SourceDir = (Resolve-Path -LiteralPath $SourceDir).Path
$head = & git -C $SourceDir rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head -ne $sourcePin) {
    throw "Expected the bring-up vendor checkout at $sourcePin. No checkout changes made."
}
if (!$ToolchainBin) {
    $command = Get-Command arm-none-eabi-gcc.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { $ToolchainBin = Split-Path -Parent $command.Source }
    if (!$ToolchainBin) {
        $pluginRoot = 'D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins'
        if (Test-Path -LiteralPath $pluginRoot) {
            $compiler = Get-ChildItem -LiteralPath $pluginRoot -Directory -Filter '*gnu-tools-for-stm32*' |
                Sort-Object Name -Descending | ForEach-Object {
                    $candidate = Join-Path $_.FullName 'tools/bin/arm-none-eabi-gcc.exe'
                    if (Test-Path -LiteralPath $candidate) { $candidate }
                } | Select-Object -First 1
            if ($compiler) { $ToolchainBin = Split-Path -Parent $compiler }
        }
    }
    if (!$ToolchainBin) { throw 'Arm GCC not found. Supply -ToolchainBin.' }
}
$ToolchainBin = (Resolve-Path -LiteralPath $ToolchainBin).Path
$gcc = Join-Path $ToolchainBin 'arm-none-eabi-gcc.exe'
$objcopy = Join-Path $ToolchainBin 'arm-none-eabi-objcopy.exe'
$objdump = Join-Path $ToolchainBin 'arm-none-eabi-objdump.exe'
$nm = Join-Path $ToolchainBin 'arm-none-eabi-nm.exe'
$size = Join-Path $ToolchainBin 'arm-none-eabi-size.exe'
foreach ($tool in @($gcc, $objcopy, $objdump, $nm, $size)) {
    if (!(Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Missing tool: $tool" }
}
[void](New-Item -ItemType Directory -Path $OutputDir -Force)
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
$cmsis = Join-Path $SourceDir 'STM32Cube_FW_N6/Drivers/CMSIS'
$device = Join-Path $cmsis 'Device/ST/STM32N6xx/Include'
$common = @('-mcpu=cortex-m55', '-mthumb', '-mcmse', '-mfloat-abi=soft')

# Verify all hard-coded register addresses and offsets against pinned ST CMSIS.
& $gcc @common '-std=c11' '-fsyntax-only' '-Wall' '-Wextra' '-Werror' '-DSTM32N657xx' "-I$device" "-I$(Join-Path $cmsis 'Include')" (Join-Path $PSScriptRoot 'address_check.c')
if ($LASTEXITCODE -ne 0) { throw 'Register/address verification failed.' }

$elf = Join-Path $OutputDir 'first_gpio.elf'
$bin = Join-Path $OutputDir 'first_gpio.bin'
$map = Join-Path $OutputDir 'first_gpio.map'
& $gcc @common '-g3' '-nostdlib' '-nostartfiles' '-Wl,--build-id=none' '-Wl,--fatal-warnings' "-Wl,-Map,$map" '-T' (Join-Path $PSScriptRoot 'first_gpio.ld') (Join-Path $PSScriptRoot 'first_gpio.S') '-o' $elf
if ($LASTEXITCODE -ne 0) { throw 'Minimal FSBL build failed.' }
& $objcopy '-O' 'binary' $elf $bin
if ($LASTEXITCODE -ne 0) { throw 'Binary export failed.' }
& $objdump '-d' '-s' $elf | Set-Content -LiteralPath (Join-Path $OutputDir 'first_gpio.lst') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Disassembly failed.' }
& $nm '--numeric-sort' $elf | Set-Content -LiteralPath (Join-Path $OutputDir 'first_gpio.symbols.txt') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Symbol inspection failed.' }
& $size $elf
if ($LASTEXITCODE -ne 0) { throw 'Size inspection failed.' }

$bytes = [IO.File]::ReadAllBytes($bin)
$stack = [BitConverter]::ToUInt32($bytes, 0)
$reset = [BitConverter]::ToUInt32($bytes, 4)
if ($stack -ne 0x34181000 -or ($reset -band 1) -ne 1 -or $reset -lt 0x34180440 -or $reset -ge 0x34180C00) {
    throw 'Unexpected initial stack or Thumb reset vector.'
}
$metadata = [ordered]@{
    source_commit = $sourcePin
    compiler = (& $gcc '--version' | Select-Object -First 1)
    payload_address = '0x34180400'
    initial_stack = ('0x{0:X8}' -f $stack)
    reset_vector = ('0x{0:X8}' -f $reset)
    payload_bytes = $bytes.Length
    payload_sha256 = (Get-FileHash -LiteralPath $bin -Algorithm SHA256).Hash.ToLowerInvariant()
    is_rom_bootable_image = $false
    note = 'Raw payload only: STM32 image header/signing and external-flash programming are separate steps. No hardware accessed.'
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDir 'build-info.json') -Encoding utf8
Write-Host "Built $elf and $bin; register addresses and vector words checked. No device accessed."
