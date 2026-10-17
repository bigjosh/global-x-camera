[CmdletBinding()]
param(
    [string]$ToolchainBin = 'D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin',
    [string]$OutputDir = (Join-Path $PSScriptRoot '../../../../tmp/bringup/minimal-marker-20261017'),
    [string]$Python = 'C:/Users/joshd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
)
$ErrorActionPreference = 'Stop'
$bootDir = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$vendor = (Resolve-Path (Join-Path $bootDir '../../tmp/bringup/x-cube-n6-camera-capture')).Path
$pin = 'e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a'
if ((& git -C $vendor rev-parse HEAD) -ne $pin) { throw 'Unexpected vendor checkout revision' }
if (Test-Path -LiteralPath $OutputDir) { throw 'Choose a new output directory' }
[void](New-Item -ItemType Directory -Path $OutputDir)
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
$gcc = Join-Path $ToolchainBin 'arm-none-eabi-gcc.exe'
$cmsis = Join-Path $vendor 'STM32Cube_FW_N6/Drivers/CMSIS'
$flags = @('-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft')
& $gcc @flags '-std=c11' '-fsyntax-only' '-Wall' '-Wextra' '-Werror' '-DSTM32N657xx' "-I$(Join-Path $cmsis 'Device/ST/STM32N6xx/Include')" "-I$(Join-Path $cmsis 'Include')" (Join-Path $bootDir 'address_check.c')
if ($LASTEXITCODE -ne 0) { throw 'Pinned register checks failed' }
$elf = Join-Path $OutputDir 'first_gpio_tiny.elf'
$bin = Join-Path $OutputDir 'first_gpio_tiny.bin'
& $gcc @flags '-g3' '-nostdlib' '-nostartfiles' '-Wl,--build-id=none' '-Wl,--fatal-warnings' "-Wl,-Map,$OutputDir/first_gpio_tiny.map" "-I$bootDir" '-T' (Join-Path $bootDir 'first_gpio.ld') (Join-Path $PSScriptRoot 'first_gpio_tiny.S') '-o' $elf
if ($LASTEXITCODE -ne 0) { throw 'Assembly/link failed' }
& (Join-Path $ToolchainBin 'arm-none-eabi-objcopy.exe') '-O' 'binary' $elf $bin
if ($LASTEXITCODE -ne 0) { throw 'Binary export failed' }
& (Join-Path $ToolchainBin 'arm-none-eabi-objdump.exe') '-d' $elf | Set-Content (Join-Path $OutputDir 'first_gpio_tiny.lst') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Disassembly failed' }
& (Join-Path $ToolchainBin 'arm-none-eabi-nm.exe') '--numeric-sort' $elf | Set-Content (Join-Path $OutputDir 'first_gpio_tiny.symbols.txt') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Symbol inspection failed' }
& $Python (Join-Path $bootDir 'add_boot_header.py') $bin (Join-Path $OutputDir 'first_gpio_tiny_boot.bin')
if ($LASTEXITCODE -ne 0) { throw 'Boot header packaging failed' }
Get-Item $bin | Select-Object Name,Length
Get-FileHash $bin -Algorithm SHA256 | Select-Object Hash
Write-Host 'Only local files built; no device was accessed. GPIO reset-default assumptions require bench validation.'
