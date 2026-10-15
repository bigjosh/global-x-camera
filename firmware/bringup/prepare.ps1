[CmdletBinding()]
param(
    [string]$SourceDir = (Join-Path $PSScriptRoot '../../tmp/bringup/x-cube-n6-camera-capture')
)

$ErrorActionPreference = 'Stop'
$commit = 'e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a'
$upstream = 'https://github.com/STMicroelectronics/x-cube-n6-camera-capture.git'
$git = (Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$SourceDir = [IO.Path]::GetFullPath($SourceDir)
$patch = Join-Path $PSScriptRoot 'upstream.patch'
$application = Join-Path $PSScriptRoot 'capture_app.c'
$destination = Join-Path $SourceDir 'Src/capture_app.c'
$license = Join-Path $PSScriptRoot 'ST-LICENSE.md'
$licenseDestination = Join-Path $SourceDir 'Src/ST-LICENSE.md'

function Invoke-Git([string[]]$GitArguments) {
    & $git -c core.longpaths=true @GitArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git failed (exit $LASTEXITCODE): $($GitArguments -join ' ')"
    }
}

if (!(Test-Path -LiteralPath $SourceDir)) {
    Invoke-Git @('clone', '--no-checkout', $upstream, $SourceDir)
    Invoke-Git @('-C', $SourceDir, 'checkout', '--detach', $commit)
} elseif (!(Test-Path -LiteralPath (Join-Path $SourceDir '.git'))) {
    throw "SourceDir already exists without its own Git checkout; choose another directory: $SourceDir"
}

$head = (Invoke-Git @('-C', $SourceDir, 'rev-parse', 'HEAD') | Out-String).Trim()
if ($head -ne $commit) {
    throw "Existing checkout is at $head, expected $commit. No reset was attempted; choose a new SourceDir."
}

# Preserve edits to an earlier/local copy instead of overwriting them silently.
if (Test-Path -LiteralPath $destination) {
    if ((Get-FileHash -LiteralPath $destination).Hash -ne (Get-FileHash -LiteralPath $application).Hash) {
        throw "Existing $destination differs from the supplied capture_app.c. Preserve/reconcile it or use a new SourceDir."
    }
}
if ((Test-Path -LiteralPath $licenseDestination) -and
    (Get-FileHash -LiteralPath $licenseDestination).Hash -ne (Get-FileHash -LiteralPath $license).Hash) {
    throw "Existing $licenseDestination differs from the supplied ST license; no overwrite attempted."
}

# A reverse check recognizes a previous successful run, even with build output
# and unrelated local edits present. Never reset or clean the working checkout.
$reverseOutput = & $git -c core.longpaths=true -C $SourceDir apply --reverse --check $patch 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Bring-up patch already applied.'
} else {
    $forwardOutput = & $git -c core.longpaths=true -C $SourceDir apply --check $patch 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Patch does not apply cleanly; existing files were preserved.`n$($forwardOutput -join "`n")"
    }
    Invoke-Git @('-C', $SourceDir, 'apply', $patch)
    Write-Host 'Applied bring-up patch.'
}

if (!(Test-Path -LiteralPath $destination)) {
    Copy-Item -LiteralPath $application -Destination $destination
}
if (!(Test-Path -LiteralPath $licenseDestination)) {
    Copy-Item -LiteralPath $license -Destination $licenseDestination
}
Write-Host "Prepared $SourceDir at $commit. No device accessed."
