# Install r2 on the existing Windows camera bench

This is a **load-and-handoff procedure for the existing modified
NUCLEO-N657X0-Q**, using the project's reviewed helpers. It is not a general
STM32 installer. The controls firmware is offline-qualified, not yet
hardware-qualified. No command here formats or deliberately writes the SD
card; the final normal reset can start a capture and save a new photo.

Use a checkout at tag **`knobs-2026-11-14-r2`** and the matching complete package.
Read the latest bench checkpoint in `AGENTS.md` first and establish the current
power, wiring, installed identity and idle state. Historical documentation is
not a fresh measurement of the board.

## Connections and tools

- Stable direct target power at **CN5 pin 5 / 5 V**, ground at **CN5 pin 6**.
  Bypass the trigger latch for programming so reset cannot cut the supply.
  Keep the modified prototype's CN9 source jumpers removed.
- **CN10/ST-LINK USB connected to this Windows PC; CN8/MCU USB disconnected.**
  CN10 is the programming port; CN8 is the photo-download port. On this
  modified board, ST-LINK USB is not the target's complete power supply.
- JP1 and JP2 in their normal flash-boot positions, pins 1–2.
- No other debugger, serial monitor or bench client using ST-LINK/its UART.
  Do not reset or replace a helper while any prior NOR/SD work is uncertain.
- Python 3 on `PATH`, running normally: **do not use `python -O`** because some
  existing bench-script guards use assertions.

The scripts select the existing ST-LINK serial
`002100203335511035383531`. They require these already qualified local tools:

| Tool/helper | Required location from repository root |
|---|---|
| STM32CubeProgrammer CLI 2.23.0 | `tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe` |
| pyserial | `tmp/bringup/vcp-deps/` |
| NOR read helper | `tmp/bringup/rom-nor-maintenance-readonly-20261017/` |
| Sector 0 writer | `tmp/bringup/rom-nor-programmer-v2-20261024/` |
| Sector 1 writer | `tmp/bringup/usb-ptp-20261108/nor-sector1/` |

The ZIP includes firmware/recovery artifacts, **not these tools or a qualified
replacement programmer**. If a helper is missing, stop before accessing the
board and restore the known bench setup; do not silently rebuild or substitute
a different loader. `nor.py --build` means the programmer helper in this table,
not the release's `package/` directory.

The following sequence uses the committed copy of the existing UART sender,
`docs/power/evidence/2026-10-28-isolated-nucleo/support/uart_recover.py`.
It retains the prepared November 13 installer's secondary-before-primary order,
and additionally backs up/verifies the following 4 KiB and performs independent
flash readbacks before reset. Do not substitute that older short installer for
these additional preservation checks.

## 1. Select files and check their identity — no hardware yet

Run PowerShell from the tagged repository root. Each output directory must be
new. The wrapper stops the sequence on a nonzero Python exit status.

```powershell
function Invoke-CameraPython {
    & python -X utf8 @args
    if ($LASTEXITCODE -ne 0) { throw "Camera step failed; preserve target state and inspect its logs." }
}

$new = "release/knobs-2026-11-14-r2/package"
$old = "firmware/usb-ptp/evidence/2026-11-13-d8-hold/package"
$out = "tmp/bringup/knobs-20261114-r2-install"
$uart = "docs/power/evidence/2026-10-28-isolated-nucleo/support/uart_recover.py"
$writer0 = "tmp/bringup/rom-nor-programmer-v2-20261024"
$writer1 = "tmp/bringup/usb-ptp-20261108/nor-sector1"

$expected = @{
    "sector0.bin" = "6ddf4499865264aec845150597aa6b8d44cb89e7d5e621dd324a0e1a9170b499"
    "sector1.bin" = "206da4c0a8bdcda6205d7ccdb3d9ac02548e9db6852b1fa47afa6327b76473d8"
    "stage1.bin" = "b866589cf472cac9820d961f3243cb8280759614826083757fae374ccee7e242"
}
foreach ($name in $expected.Keys) {
    $path = Join-Path $new $name
    if ((Get-FileHash -Algorithm SHA256 $path).Hash -ne $expected[$name]) {
        throw "Wrong release artifact: $name"
    }
}
if (Test-Path $out) { throw "Choose a new output directory." }
New-Item -ItemType Directory $out | Out-Null
```

If using the extracted ZIP, set `$new` to its absolute `package` directory;
keep the working directory at the tagged repository root. Verify the ZIP
against the release `SHA256SUMS` and its extracted files against the internal
checksum list. Keep the whole package, including its `recovery/` subdirectory.

`$old` names the **last recorded installed D8 fixed-settings image**, not a guess
about the board today. If the live identity or the full backup differs, stop
and identify it before choosing another exact reviewed package. Never remove
an `--expect` check just to make the procedure proceed.

## 2. Enter and verify the existing recovery park

Only after establishing that previous storage work has finished:

```powershell
Invoke-CameraPython $uart "$out/programming-uart"
Invoke-CameraPython firmware/usb-ptp/recovery.py --package $old --out "$out/programming-park"
```

The sender must finish normally; its completion alone does not prove recovery.
Require `programming-park/result.json` to report `passed: true`. The verifier
checks the exact live prefix and recovery context. A missed recovery must be
diagnosed before flash helpers are loaded.

## 3. Back up both complete sectors and the untouched following 4 KiB

```powershell
Invoke-CameraPython firmware/usb-ptp/nor.py read --offset 0 --expect "$old/sector0.bin" --out "$out/backup0"
Invoke-CameraPython firmware/usb-ptp/nor.py read --offset 65536 --expect "$old/sector1.bin" --out "$out/backup1"
Invoke-CameraPython firmware/usb-ptp/nor.py read --offset 131072 --out "$out/backup-next4k"
```

Require success from every command. Preserve all three `readback.bin` files
and logs. The first two reads must match the old package in full; the third
is a 4,096-byte preservation reference, never a write target in this procedure.

## 4. Program the secondary sector, then the primary sector

```powershell
Invoke-CameraPython firmware/usb-ptp/nor.py write --offset 65536 --build $writer1 --current "$out/backup1/readback.bin" --desired "$new/sector1.bin" --out "$out/write1"
Invoke-CameraPython firmware/usb-ptp/nor.py write --offset 0 --build $writer0 --current "$out/backup0/readback.bin" --desired "$new/sector0.bin" --out "$out/write0"
```

For each operation, require successful exit and `verified.json` with
`byte_for_byte_match: true`. The helper checks completion and flash/controller
safety before halting, and compares the full 64 KiB readback. Do not issue the
second write if the first fails or its state is uncertain. Do not reset between
the writes: the temporary mixed package is not a normal operating image.

## 5. Independently verify flash and preservation before activation

```powershell
Invoke-CameraPython firmware/usb-ptp/nor.py read --offset 0 --expect "$new/sector0.bin" --out "$out/verify0"
Invoke-CameraPython firmware/usb-ptp/nor.py read --offset 65536 --expect "$new/sector1.bin" --out "$out/verify1"
Invoke-CameraPython firmware/usb-ptp/nor.py read --offset 131072 --expect "$out/backup-next4k/readback.bin" --out "$out/verify-next4k"
```

All three must succeed; their `result.json` files must report `matches: true`.
This proves the two intended regions and the following 4 KiB, not camera
functionality or preservation of every other physical memory location.

## 6. Start normal firmware and hand off

```powershell
Invoke-CameraPython firmware/usb-ptp/reset.py --out "$out/activate-normal"
```

This releases a **powered normal reset**, not a power cycle or cold-boot test.
With CN8 disconnected, it can immediately begin a capture using the knob
positions. Leave stable power connected and let the operation finish; do not
interrupt capture/save to obtain a quick debugger reading.

For a load-only handoff, record the programmed hashes, backup/verification
results and reset event, explicitly mark functional tests not run, and return
the bench to the user. A successful flash comparison is not a successful
camera test. Do not label the present runtime or terminal state as observed
unless it was actually measured.

When live recovery qualification is part of the requested test campaign, first
establish completed storage work, then use new output directories:

```powershell
Invoke-CameraPython $uart "$out/post-uart"
Invoke-CameraPython firmware/usb-ptp/recovery.py --package $new --out "$out/post-park"
```

Require `passed: true` and record it. This leaves the target in recovery with
HOLD asserted; it does not automatically resume capture. A subsequent normal
reset is a separate action that can take another photo.

## Failure, timeout and restoration

**A timeout does not stop the MCU's flash operation.** Preserve stable power
and leave the running helper intact. Do not reset, halt, reload a helper, call
`nor.py read`, or retry a write while completion is uncertain. Even the read
wrapper halts the MCU and replaces its helper.

Inspect the current helper's RAM status with a non-halting read. Before helper
replacement, require a fresh `DONE` for this operation, matching command,
sequence and expected input/current CRCs, plus `result == 0`,
`(flags & 7) == 7`, and `(flags & 16) == 0`, as enforced by
`firmware/boot-timing/nor_bench.py`. A stale saved status or `DONE` alone is
insufficient. If safe completion cannot be established, preserve the state
for diagnosis; no automatic recovery reset or readback is appropriate.

After safe completion is established, independently read and compare the
actual flash before deciding whether another write is needed. Any retry uses
that fresh complete readback as `--current`, never the pre-write backup.

For restoration after a completed installation, establish the exact new
recovery park, read both current sectors and the following 4 KiB, then use the
same secondary-before-primary sequence with the preserved old sectors as
`--desired`. Independently verify those old sectors and the unchanged 4 KiB
before a normal reset. If installation stopped partway, do not assume either
whole package is installed; first establish safe completion and actual bytes.
Retain the original backups throughout diagnosis and restoration.

These procedures depend on the existing bench's helper builds and identity
checks. A portable installer with explicit preflight, recovery/status-only
diagnostics and automated preservation checks remains a future improvement.
