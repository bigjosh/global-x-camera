# PNG readback after early recovery

This is a separate RAM-only read path for the bench owner. It does not alter
the installed NOR image or weaken the ordinary capture-maintenance guards.
Run the existing exact early-UART recovery check first; this runner repeats
that check immediately before its first RAM write. Archive Standby/SBF evidence
before starting, because expanded SRAM will be initialized.

`run.py` accepts only explicit reviewed prefix/sector pairs in
`APPROVED_RECOVERY`: the current v66c normal Standby image and historical
v59/v65 early-recovery identities. There is no arbitrary-build override. It hashes both files,
then repeats the live exact-prefix/park check and binds that result to the
selected identity before any RAM write. This allowlist is an offline safety
review, not a claim that a particular trial completed or preserved an image.

The superseded, uninstalled v63 candidate was removed after its receiver proof
was found to overlap LED1. V65 relocated RCP2 to `0x343F8A80`, but its late loader
still required the old SAVE schema and refused shutdown before reading the
late module. Its verified early recovery remains accepted for historical READ
access; this does not qualify v65 Standby. V66c fixes that loader gate using
the current schema and exact profile/check mask. Its complete fixed memory
map, early recovery bytes/literals, SRAM initializer and corrected loader were reviewed.
The helper still loads the same frozen schema-1 v8b **READ** executable and
bridge; it does not adopt the newer normal-profile SAVE code or relax their
read-only completion checks. Normal versus diagnostic capture hashes do not
change the independent host PNG validation described below.

On October 24 the v66c path passed full readback of IMG68–71 and original
IMG1, with zero card writes. The three final capture files decoded completely;
IMG1 retained its original SHA-256. Independent NOR readback afterward still
matched v66c. See the [qualified record and final bench state](../../evidence/2026-10-24-normal-profile/README.md).

The 1,324-byte bridge uses the unchanged `raw10_memory_init()` from the frozen
prefix to enable expanded SRAM, verifies the existing ROM clock profile and
LED dependency, and enables/checks DWT. It has no sensor, CSI, NOR-command or
SD-command path. The checked proof and exact uncached terminal park authorize
loading the byte-identical v8b module. The host writes only operation 3 / READ,
with strict generated PNG filenames and a fresh nonce. It does not expose
FORMAT, SAVE, mount-only, delete, arbitrary entry points, reset or power control.

Each READ opens the existing file with `FA_READ`, seeks, reads up to 256 KiB,
closes, waits for the card, and deinitializes SDMMC. FatFs `f_sync()` performs
metadata writes only for `FA_MODIFIED`; this read-only open/seek/read path does
not set it. The host additionally requires zero written sectors/write cycles,
zero filesystem bytes written, successful card cleanup, caches off and the
exact module park before another request. Every unexpected or failed result
stops the process without a reset or retry. Existing LPL/LPM records stay in
place so generic maintenance remains blocked.

The whole file is read until a short read/EOF, within the 3.1 MB prototype
bound. Independent host decoding checks every PNG chunk CRC, the 1120×1364
16-bit grayscale format, sBIT=10 and low six bits of every decoded pixel.
**The original raw frame is lost after Standby:** successful decoding is not
an exact comparison with that original capture. `--known-sha` can verify a
previously downloaded file byte for byte.

Build and inspect offline:

```powershell
python firmware/capture-sd/low_power/readback_recovery/build.py `
  --recovery-build tmp/bringup/capture-sleep-20261020/v59-standby/staged `
  --out tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1
python firmware/capture-sd/low_power/readback_recovery/test_readback.py
python firmware/capture-sd/low_power/readback_recovery/run.py `
  --bridge tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1 `
  --module tmp/bringup/save-module-v8b-fast-loop-cache-20261020 `
  --recovery-build tmp/bringup/capture-sleep-20261020/v59-standby/staged `
  --out tmp/bringup/capture-sleep-20261020/recovery-png-readback `
  --name IMG00038.PNG --name IMG00039.PNG
```

Only the exclusive bench owner may add `--execute` after independent review,
with the board already at the exact early recovery park. This is not a tool
for making an unknown or active-storage state safe. Missing files are errors,
not automatic permission to continue.

All runtime files, including images, must stay below the ignored `tmp/` tree.
The bridge is SHA-256
`9d0a4553845dbf033264bde3629e2601aac561799cac9e34ed841f32485abdb6`,
entry `0x341E0001`, park `0x341E0016`; v8b is
`91e1edfa43f95a9608b94457cfbf900c6f51d5ecd10d2b3b7667c84d40cd3844`.
