# Capture → PNG16 → FAT32 prototype

**October 20 status: implemented and tested offline, not yet run on the board.**
The installed NOR image is still v45b. This work has not formatted or written the
physical SD card. Hardware work is blocked on restoring MCU debug access; see
[the checkpoint](../../docs/decisions/capture-png-sd-2026-10-20.md).

The user authorized destructive SD formatting for development and explicitly
left power-loss protection unqualified. Normal firmware never formats a card:
formatting is a separate, explicit bench operation. Existing PNG/TMP filenames
are skipped, older files are not overwritten, and full storage stops a save.

## Data and execution

The existing 1120 × 1364 RAW10 frame stays at `0x34000000`, right-aligned in
little-endian 16-bit words. The encoder preserves all ten bits and writes
grayscale PNG16 samples as `sample << 6`, with `sBIT=10`. It does not add a gamma
transform, black-level adjustment or fabricated capture timestamp. FAT directory
dates use the documented 2000-01-01 placeholder until an RTC is integrated.

The receiver completes and validates the first frame, stops capture and the
sensor, then loads the save module from NOR offset `0x6000`. The loader reuses
the verified XSPI1 finite-read configuration, checks the exact module CRC and
executes it in high SRAM. No SD initialization, PNG code load or compression is
added before the exposure. The receiver itself grows by 652 bytes; its added NOR
load time still needs measurement.

The module checks capture geometry, error history, frame count, RAW10 format,
DMA byte count, the frame canary and the capture checksum before saving. It uses
native **one-bit SDMMC2 at 25 MHz, 3.3 V**, matching the existing breakout wiring.
A 32 KiB output buffer combines small PNG chunks into larger filesystem writes.
There is no second frame buffer, heap, DMA-based storage path or RTOS.

Each save creates `IMG00001.TMP` (or the next unused number), writes the PNG,
syncs and closes it, waits for card readiness, renames it `.PNG`, then checks
readiness again. These steps do **not** establish atomicity or protect previously
saved files from an arbitrary power cut inside the card's flash translation
layer. Failed operations preserve diagnostics and leave the target powered.

The existing LED pins show red during boot, blue during acquisition and green
during the save. Success turns the LEDs off. The normal completion variant then
uses the existing CPU WFI loop; this is not regulator-off shutdown. An `--awake`
diagnostic variant parks without WFI to help investigate debug accessibility.

## Memory layout

| Region | Use |
|---|---|
| `0x34000000..0x342E9EFF` | Original RAW10 frame |
| `0x342E9F00..0x342E9F1F` | Capture overrun canary |
| `0x34300000` | Existing receiver |
| `0x34320000..0x3439FFFF` | Save code, encoder and filesystem workspace |
| `0x343A0000..0x343AFFFF` | Reserved 64 KiB save stack |
| `0x343B0000` | Stack top |
| `0x343C0000` | Existing post-capture maintenance helper |
| `0x343F9E00` | NOR save-loader proof |
| `0x343F9F00` | Explicit bench request |
| `0x343FA000` | Save report |
| `0x343FA200`, `0x343FA400` | SD driver and filesystem snapshots |

`save_entry.S` temporarily lowers MSPLIM from the receiver's 4 KiB stack limit
to the reserved 64 KiB floor, preserving the original limit for return. It fills
unused lower stack with a canary. The PNG compressor alone needs more than
5.5 KiB of stack. The linker rejects overlap and code larger than the 40 KiB
reserved NOR window.

The reviewed v4 module is 25,496 bytes of code/data and 234,936 bytes of BSS.
Its SHA-256 is
`6661d3b54ea9b1c10d6618b0e9da30a9791a12beda09987aac3f2b315fa5f4ba`.
Its ordinary entry is `0x34320001`, bench entry `0x34320051`, and terminal park
`0x3432006E`. These are offline build identities, not hardware qualification.

## Build

The scripts use the existing pinned CubeN6 headers and GCC toolchain from
`capture-timing/build_raw10.py`. Existing frozen v45b sources and manifests
remain the capture/recovery base. Builds create new directories and never
operate hardware:

```powershell
python firmware/capture-sd/build_module.py --out tmp/bringup/my-save-module
python firmware/capture-sd/build.py `
  --base tmp/bringup/capture-vcp-recovery-v45b-20261020 `
  --module tmp/bringup/my-save-module `
  --out tmp/bringup/my-capture-sd --awake
```

Omit `--awake` for the existing WFI completion policy. The builder checks input
hashes, module memory bounds and the byte identity of the early recovery code
and its literal references. Building does not admit a new sector into the
maintenance allowlist or authorize programming it without the normal exact
park/readback checks.

## RAM bring-up and readback

Use the existing `prepare_maintenance.py --layout raw10` only after an intact,
completed capture. The new bench runner accepts that exact uncached park, or
its own exact successful park. It refuses active/failed/unknown operations,
changed code, stale requests and non-idle media. It never resets the target,
changes power, sends NOR commands, or automatically retries an SD failure.

After an integrated automatic save, maintenance also requires
`--save-build <module-directory> --save-sha256 <reviewed-module-sha256>`.
It checks the exact live code, completed loader return, successful filesystem
result and deinitialized/idle card before its first halt. Recognized active or
failed storage records are rejected even if the capture trace already says
event 40. Automatic saves use nonce zero; they enter RAM bench operations only
through this checked maintenance park.

```powershell
python firmware/capture-sd/bench.py format `
  --build tmp/bringup/my-save-module --out tmp/bringup/sd-format-01 `
  --expected-sha256 <reviewed-module-sha256> --format-card --execute
python firmware/capture-sd/bench.py save `
  --build tmp/bringup/my-save-module --out tmp/bringup/sd-save-01 `
  --expected-sha256 <reviewed-module-sha256> --mode fast-none --execute
python firmware/capture-sd/bench.py read `
  --build tmp/bringup/my-save-module --out tmp/bringup/sd-read-01 `
  --expected-sha256 <reviewed-module-sha256> `
  --name IMG00001.PNG --offset 0 --length 32768 --execute
```

Each operation needs a new output directory. READ produces `data.bin`; repeated
bounded reads can retrieve a complete file without removing the card. Decode it
independently and compare every sample against the original RAM frame before
claiming success. The runner records host timing brackets and target diagnostics.

## Compression and measurements

Three modes are implemented: `stored` (uncompressed DEFLATE), `fast-none`
(fast compression with no PNG row filter), and `fast-sub` (fast compression
with the PNG Sub filter). Fast-none is a **provisional** default, not a measured
MCU time/energy winner. A previously captured LED-panel frame encodes to
3,060,848 / 728,031 / 867,924 bytes respectively; host results do not establish
MCU timing or SD throughput.

For the hardware comparison, use the same retained RAM frame and a new filename
for every mode. Report total save time, encoding wall time, callback/write time,
final flush/sync time, card busy time, file size and JS110 input energy. The
32-bit DWT counter is extended through encoder callbacks and the SD driver's
short progress hook, including long filesystem scans/formatting. Target timing
starts inside `save_main`; it excludes NOR module loading, entry-stack setup,
the final stack scan/cache teardown and subsequent sleep. End-to-end cold-cycle
timing must include those costs separately.

The JS110 boundary includes Nucleo overhead and is not a qualified isolated DUT
measurement. Host command timestamps alone do not provide electrical
synchronization. The existing slow statistics log is insufficient for a precise
per-save energy result.

For a new measurement, the sole JS110 owner can select
`js110_session.py --power-stream-log <new.jsonl>`. This adds sample sums from the
driver's power stream and restores the additional settings afterward.
`energy.py --stream-log <new.jsonl> --window <window.json> --out <report.json>`
integrates those samples, rejects gaps/nonfinite data, and reports bounds for
partial chunks and the supplied timing uncertainty. It refuses old current/
voltage-only logs as an energy source. See the window schemas in `energy.py`;
native sample-ID intervals are preferred when actual synchronization is known.

## Offline verification

```powershell
python firmware/png-encoder/test_png16.py
python firmware/capture-sd/fs/tests/test_photo_fs.py
python firmware/sd-storage/test_sd_driver.py
python firmware/capture-sd/bench.py --self-test
```

The PNG suite has 11 tests; the actual FatFs integration suite has 14, including
all three PNG modes independently decoded from a simulated FAT32 card; the SD
protocol model has 13; the RAM runner has 8 guard tests and the maintenance suite
has 20. These cover exact pixel
preservation, bounds, failure injection, readback, no-overwrite behavior and
bounded controller cleanup. They do not replace physical SD write, recovery,
timing, energy or power-loss qualification.
