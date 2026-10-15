param(
    [string]$GdbExe = 'arm-none-eabi-gdb',
    [string]$SourceDir = (Join-Path $PSScriptRoot '../../tmp/bringup/x-cube-n6-camera-capture'),
    [string]$OutputDir = (Join-Path $PSScriptRoot '../../tmp/bringup')
)
$ErrorActionPreference = 'Stop'
$elf = (Resolve-Path -LiteralPath (Join-Path $SourceDir 'build/Project.elf')).Path.Replace('\', '/')
$null = New-Item -ItemType Directory -Force -Path $OutputDir
$outputPath = (Resolve-Path -LiteralPath $OutputDir).Path.Replace('\', '/')
$raw = "$outputPath/frame-640x480-y8.raw"
$scriptPath = "$outputPath/capture-run.gdb"
$template = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'capture.gdb') -Raw
$scriptText = $template.Replace('@ELF@', $elf).Replace('@OUTPUT@', $outputPath)
[IO.File]::WriteAllText($scriptPath, $scriptText, [Text.UTF8Encoding]::new($false))
Write-Host 'Using the ST-Link GDB server already listening on port 61234.'
& $GdbExe -batch -x $scriptPath
if ($LASTEXITCODE -ne 0) { throw 'Capture failed; inspect the debugger output and serial diagnostics.' }
if ((Get-Item -LiteralPath $raw).Length -ne 307200) { throw 'Unexpected framebuffer size.' }
Write-Host "Captured $raw; MCU reset to development ROM."
