# Capture to PNG on SD — October 20 implementation log

## User-approved scope

Implement autonomous capture → 16-bit grayscale PNG → FAT32 SD, then optimize
compression for total save time and energy. The user authorizes formatting the
connected SD card during development and delegates routine decisions. Sudden
power-loss protection is explicitly **unqualified for this prototype**; earlier
NAND durability expectations are not claims about this implementation.

PNG samples are `sensor_sample << 6`, with `sBIT=10`. All ten sensor bits must
round-trip exactly. Keep the currently qualified capture dimensions, 1120 ×
1364, rather than changing sensor geometry during storage integration.

## Implementation decisions

- Preserve the PE6 ST-LINK recovery guard and current sensor/receiver sequence.
- Establish a complete capture on the installed firmware before integrating SD.
- Load the storage/PNG module after capture. Avoid putting its full code size
  into the NOR transfer before receiver arming.
- Reserve explicit high-SRAM code, workspace and stack boundaries. Never reuse
  the standalone SD diagnostic's low-SRAM workspaces over the captured frame.
- Retain the original RAW10-in-16-bit RAM frame; stream PNG rows through bounded
  buffers instead of allocating a second complete image.
- Use native one-bit SDMMC2 at an initially verified 25 MHz, at 3.3 V.
- Use pinned upstream FatFs, FAT32, one partition and 32 KiB clusters. Formatting
  is an explicit bench operation; a mount failure does not automatically erase
  photos during normal camera operation.
- Create a new numbered `.TMP`, close/synchronize it, then rename it `.PNG`.
  Check card readiness before success/sleep. This labels incomplete saves;
  neither rename nor two FAT copies is an atomic power-loss guarantee.
- Keep filenames unique and stop on full storage. Do not overwrite older files.
- Begin with bounded synchronous multi-sector transfers; add overlap or IDMA
  only when measured improvement justifies its complexity.
- Compare stored DEFLATE with fast lossless compression using identical frames.
  Report encode time, bytes, SD busy/write time, total save time and measured
  energy separately. The present JS110 boundary includes board overhead and
  remains unsuitable for claiming isolated production-camera consumption.

## Validation still required

Real capture integrity and visual content; destructive SD write/readback;
FAT32 formatting/mounting; PNG decode and exact pixel comparison; autonomous
cold boot/save/recovery; repeated distinct files; timing and energy comparison;
documentation of final installed firmware and reproducible builds.

The baseline before this work is commit `6224f91`: v45b boot recovery and
read-only SD checks passed through 25 MHz, but capture-to-SD was not implemented.

## Completed offline implementation

The [implementation and bench workflow](../../firmware/capture-sd/README.md)
now include:

- Native one-bit SDMMC2 multiblock read/write, bounded CMD12/ready handling,
  explicit driver error/idle state, and a monotonic timing service hook.
- Licensed, pinned FatFs R0.16 with official patches 1 and 2; FAT32 with
  32 KiB clusters and two FAT copies; create-new filenames, explicit format,
  streamed writes, close/sync/rename, and bounded file readback.
- Licensed, pinned miniz 3.1.0; stored DEFLATE, fast unfiltered compression,
  and fast Sub-filter compression. PNG contains grayscale16 and `sBIT=10`.
- A 32 KiB output buffer, no heap or second full frame, 64 KiB reserved save
  stack with MSPLIM adjustment and canary, and code/diagnostic address guards.
- A separate CRC-checked NOR module loaded after capture. Storage ownership is
  published before the legacy capture-complete marker so maintenance cannot
  mistake an active save for an idle frame.
- Explicit RAM bench commands and exact code/park checks; no automatic reset,
  power cycle, overwrite, format or retry following a storage failure.
- Optional JS110 power-sample logging and offline interval-energy analysis.
  Slow current/voltage averages are not presented as measured per-save energy.

Fast unfiltered compression is provisional. On the retained earlier LED-panel
frame, stored / fast-none / fast-sub produced 3,060,848 / 728,031 / 867,924 bytes.
These are host-verified sizes; the MCU time and energy winner is **not yet
measured**. Compare the modes with the same retained frame, alternating order
and several repeats once hardware access returns.

The v4 module is 25,496 bytes, SHA-256
`6661d3b54ea9b1c10d6618b0e9da30a9791a12beda09987aac3f2b315fa5f4ba`.
The integrated v47b diagnostic sector builds successfully, SHA-256
`93f1ed2687bb5a128b74d6ea43df7f564330c882e8e5bd9b932d454c8b091231`.
Neither is programmed or hardware-qualified. V47b intentionally stays awake
after success for initial inspection. Its receiver is 14,996 bytes, 652 bytes
larger than v45b; the effect on pre-capture NOR loading remains to be measured.

Offline checks passed: 11 PNG tests, 14 actual-FatFs integration tests including
PNG round-trip through all three modes, 13 modeled SD protocol cases, 8 RAM
runner guard tests, 20 maintenance tests, 10 energy-analysis tests and 22
Joulescope helper tests.
The new module compiles with warnings treated as errors. The inherited camera
sources retain their existing vendor/compiler warnings.

## Hardware blocker and exact bench state

No new NOR image was programmed, no current frame was retrieved, and **no SD
format or write was performed** during this implementation pass. Installed NOR
therefore remains v45b with the previously verified sector SHA-256
`2323caa6b0ef142a6f46adbfdb078f9070877f7665f97337145de75eec60b3d2`.
It has not been reread this pass because AP1 access is unavailable.

After a normal JS110 off/on trial, AP1 could not access the MCU. Cold and warm
recovery requests using C0, a phase-adjusted 0x80 request, and a bounded
under-reset attempt did not restore access. AP0 still identified the STM32N6
but could not read core/SRAM. There was no `DEV_USB_COMM_ERR`, and no shared USB
hub or unrelated device was reset.

The recorded PE6/NRST signals show the requested UART patterns spanning reset.
Occasional 80–105 µs UART gaps can defeat the 100 µs guard, but successful
historical traces have comparable gaps; waveform replay did not explain the
repeated failures. Debug opening precedes the detector in this prefix, so AP1
failure alone does not prove a missed recovery signature. The exact prefix/ROM
state and actual guard-entry clock remain unknown. The available probes did
not observe target supply rails, so complete DUT discharge is also unproven.
Do not attribute the failure to WFI without evidence.

The pending user action is to move **only JP2/BOOT1 to pins 2–3**, leaving the
power and SD wiring unchanged, so ROM development mode can restore access.
After that, preserve diagnostic state where possible, compare NOR to the
known v45b image, and install the independently reviewed v46 awake baseline
before integrating SD writes. V46's receiver differs from v45b in only the
completion instruction/proof value; its recovery guard is unchanged. Its
sector is `3f64bb86b73c44ba403a2a150f058eb0daf661c4b1ac41e6ca4634073bdd7cae`.

The root-owned JS110 helper stopped cleanly at **2026-10-20 05:03:27 UTC**,
restoring starting range **128/auto**, with no further off command. Its last
input measurement was 4.884 V and 66.38 mA; this is at JS IN+, not proof of the
DUT rail. VCP BREAK was released and COM8 closed by the stimulus helpers.
No instrument owner remains from this pass. Recheck ownership and actual
wiring before resuming.

Local detailed recovery evidence remains under
`tmp/bringup/capture-sd-20261020/`; cold traces are under
`tmp/bringup/vcp-install-20261019/sd-capture-baseline-cold-01/` and
`sd-baseline-recovery-01/`. No camera imagery or SD contents are published by
this checkpoint.
