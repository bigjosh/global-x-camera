param(
    [string]$GdbExe = 'arm-none-eabi-gdb',
    [string]$SourceDir = (Join-Path $PSScriptRoot '../../tmp/bringup/x-cube-n6-camera-capture'),
    [string]$OutputDir = (Join-Path $PSScriptRoot '../../tmp/bringup/probe-stimulus')
)
$ErrorActionPreference = 'Stop'
$elf = (Resolve-Path -LiteralPath (Join-Path $SourceDir 'build/Project.elf')).Path.Replace('\', '/')
$null = New-Item -ItemType Directory -Force -Path $OutputDir
$outputPath = (Resolve-Path -LiteralPath $OutputDir).Path.Replace('\', '/')
$scriptPath = "$outputPath/probe-smoke-run.gdb"
$template = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'probe_smoke.gdb') -Raw
$scriptText = $template.Replace('@ELF@', $elf).Replace('@OUTPUT@', $outputPath)
[IO.File]::WriteAllText($scriptPath, $scriptText, [Text.UTF8Encoding]::new($false))
Write-Host 'Run while Saleae records. Using ST-Link GDB server on port 61234.'
& $GdbExe -batch -x $scriptPath
if ($LASTEXITCODE -ne 0) { throw 'GPIO stimulus failed; inspect debugger log.' }
Write-Host 'GPIO stimulus completed; MCU reset to development ROM.'
