# Capture to PNG on SD — October 20 implementation log

**Current selection: v50 autonomous capture → PNG16 → FAT32, awake completion.**
The installed first-sector SHA-256 is
`9ffc2c1cbaacf9f60258343ac6a061b35fb62f8b62b42c1a5b50ccc5f432f5cd`.
It uses the v8b cached, `-Os`, dedicated fast-loop compressor with no PNG row
filter. Four normal cold boots have saved distinct files; the first automatic
file passed complete readback and exact comparison of every sensor sample.
Early VCP recovery passed between the second and third normal boots.

The selected same-frame benchmark saves took **1.6831–1.6842 s** and produced
**919,353 bytes**, with conditional save-duration energy bounds of
**0.7675–0.8129 J**. These are save-module results, not full cold-cycle
measurements or isolated production-camera power. Completion remains awake;
WFI recovery, regulator-off shutdown and sudden power-loss protection remain
unqualified.

The [final selection and integration](#selected-v8b-compressor-and-v50-integration)
supersede the earlier blocked/v45b and RAM-only/v46 checkpoints below.
Historical sections retain what was known at each step. The
[hardware archive](../../firmware/capture-sd/evidence/2026-10-20-hardware/README.md)
contains the exact builds, proof records and replayable measurements without
publishing camera images.

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

## Initial validation plan

The initial plan was to verify real capture integrity and visual content; destructive SD write/readback;
FAT32 formatting/mounting; PNG decode and exact pixel comparison; autonomous
cold boot/save/recovery; repeated distinct files; timing and energy comparison;
documentation of final installed firmware and reproducible builds. The hardware
checkpoint below records which parts now pass and which remain open.

The baseline before this work is commit `6224f91`: v45b boot recovery and
read-only SD checks passed through 25 MHz, but capture-to-SD was not implemented.

## Earlier offline implementation checkpoint

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

## Earlier hardware blocker and bench state

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

## Additional UART retries at user request

On October 20 at 05:44–05:45 UTC, the user requested a few more UART recovery
attempts before changing BOOT1. After checking shared-bench ownership, four
additional warm attempts used 32,768 repetitions of `0xC0` at 1 Mbaud, 8N1.
Each UART burst spanned a nominal 100 ms BREAK-controlled reset, with varied
lead time to shift the UART gaps relative to startup. Saleae captured PE6
and NRST, and `check_park.py` attempted exact recovery verification afterward.

| Attempt | Requested UART lead before BREAK | Measured principal NRST LOW interval | UART continues after reset release | AP1 result |
| --- | ---: | ---: | ---: | --- |
| 1 | 7 ms | 101.393 ms | 223 ms | Cannot connect |
| 2 | 23 ms | 101.308 ms | 208 ms | Cannot connect |
| 3 | 61 ms | 103.594 ms | 167 ms | Cannot connect |
| 4 | 89 ms | 102.463 ms | 140 ms | Cannot connect |

Every capture contains the expected 32,768 LOW pulses, each 6.88–7.04 µs
long, with median HIGH intervals of 3.04 µs. Interior HIGH gaps occasionally
reach 107–114 µs; an individual 100 µs detector-window miss remains possible.
The changed timing and correct waveforms do not establish the cause of the
repeated failures. ST-LINK reported 3.27 V and failed to obtain the core ID
on every attempt, before the first SRAM read. There was no
`DEV_USB_COMM_ERR`; no WinUSB transport recovery was indicated.

Full local captures and stimulus logs are under
`tmp/bringup/vcp-retry-20261020-01-signal/` through `-04-signal/`;
matching `-01-park/` through `-04-park/` folders hold the failed CLI logs.
The [compact evidence record](../../firmware/capture-sd/evidence/2026-10-20-uart-retries/results.json)
preserves measurements, source hashes and CLI outcomes.

No halt or memory write was reached. No NOR programming, SD write/format,
or JS110 power switching occurred. COM8 is closed, BREAK released, and both
observed lines ended HIGH. The installed image remains v45b; its contents
could not be reread. The previously requested **JP2/BOOT1 pins 2–3** move
remains pending so ROM development mode can bypass the inaccessible image.

## Hardware resumed — earlier v5/v6b checkpoint

This historical checkpoint records successful RAM-driven PNG saves and complete
file readback, followed by v6b cache and compression comparisons. At that point
v46 remained installed and the storage modules were invoked separately from RAM.
The later v50 checkpoint establishes autonomous operation.
Detailed evidence remains local under `tmp/bringup/sd-resume-20261020/`; no
camera images or card contents are copied into the repository by this update.

### Recovery and working capture baseline

After the user moved JP2/BOOT1 to development mode, warm reset still did not
restore usable access. A controlled cold power cycle did. Before programming,
the complete first 64 KiB of the 68 KiB NOR read matched the saved v45b image.
V46 was then programmed and its complete 64 KiB readback matched, while the
following 4 KiB remained unchanged. The sector SHA-256 is
`3f64bb86b73c44ba403a2a150f058eb0daf661c4b1ac41e6ca4634073bdd7cae`;
`development-nor/verified.json` records verification at 06:02:45 UTC.
The user returned BOOT1 to normal flash boot.

V46 changes completion to an awake loop and preserves the early PE1/PE6
recovery branch. Normal cold capture and subsequent illuminated captures
reached stage 40/result 0, one frame, zero reported camera errors, and exact
host-versus-firmware frame checksums. The initial frame's sample range was
62–71; illumination was then restored and the illuminated captures span
61–1023, with no invalid upper RAW10 bits. The lighting issue was resolved
without changing the sensor geometry or capture sequence. These checks
establish a complete 1120 × 1364 RAM frame; they do not by themselves verify
every aspect of visual image quality. Sources are
`v46-normal-read-01/capture-result.json`,
`v46-lit-read-01/capture-result.json` and
`v46-lit-read-02/capture-result.json`. Captured frames remain local.

### First format failure and correction

The first v4 RAM format attempt failed during CMD25 multiblock writing after
four successfully written sectors. Its report records 144 words supplied in
the failed transfer, `DPSMACT` still set, error 15 and `media_idle=0`; it is
not a successful or safe-to-retry format. The driver had treated HALF-empty
as a 16-word refill opportunity. On this STM32N6's 256-word TX FIFO,
`BUSSPEED=0` waits for a full FIFO or all remaining transfer bytes before
starting transmission. Stopping at 144 words therefore prevented progress.
The corrected v5 driver fills until FULL or the last word, with a bounded
loop, and includes explicit FIFO handling during error cleanup.
[RM0486 Rev 4, SDMMC FIFO operation, pp. 1396–1398 and 1439](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=1396)
supports this interpretation; the local failure is
`format-01/result.json`.

A separate bounded status diagnostic then issued only CMD13 and read
`0x900`: READY_FOR_DATA and TRANSFER state. DAT0 was HIGH. The host data path
still had `DPSMACT` set, so this did not retroactively make the failed
driver's report idle. The explicit card-ready evidence in
`card-status-proof.json` was reviewed before a controlled cold restart,
followed by a fresh capture and maintenance preparation. This exception
required independent evidence; the normal runner continues to refuse
automatic reset, power cycling or retry after an uncertain storage failure.

### Successful v5 format and first PNG save

Save-module v5 is 25,524 bytes, SHA-256
`e40500661067fb13aba5fc2d1fbb5ea5de376d0518a95da8aaaf4c618767637d`.
It was loaded and verified in reserved RAM while v46 remained the installed
NOR capture firmware. These are separately invoked bench operations.

| Operation | Measured target time | Result |
| --- | ---: | --- |
| Explicit FAT32 format | 18.5666 s | 29,979 sectors written, 32 KiB clusters, result 0, card idle and deinitialized |
| Fast unfiltered PNG save | 18.8667 s | `IMG00001.PNG`, 746,618 bytes, filesystem complete, card idle and deinitialized |

The format and save used native one-bit SDMMC2 at 25 MHz.
`format-v5-01/result.json` and `save-v5-fast-none-01/result.json` record
zero card errors and successful completion. The save preserved the input
frame's FNV checksum. Its measured encoding interval was 18.0532 s, including
0.5563 s spent in output callbacks; these intervals overlap and must not be
added as independent costs. File finishing took 23.49 ms. These are initial
diagnostic timings at nominal 400 MHz with D-cache disabled and I-cache enabled,
not an optimized
save-time result or a measured energy comparison.

Full file readback through 23 hardware reads now passes. Independent PNG
decode validates every chunk CRC, grayscale16 format and `sBIT=10`; all
**1,527,680 pixels exactly equal the retained RAW10 samples shifted left six
bits**. `download-v5-fast-none-01/verified.json` records the 746,618-byte file
SHA-256 `466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330`
and source-frame SHA-256
`5bf987c93eb0db31c916c8d8eeb996a32504f447170f5232d097d776fb9c844c`.
The image and raw frame remain local. This is an end-to-end integrity check
for one separately invoked RAM save/readback, not yet autonomous boot/save.
This was the initial save/readback milestone; the later repeated-save and
compression results follow below. Power-loss behavior and integrated normal
boot/save remain unqualified.

### V6b cache experiment and repeated saves

The v6b cache module is 25,900 bytes, SHA-256
`747e8527571d3b961fb43d426b328951ccde97478cdefc6d9773e22c66a4fd9e`,
from `tmp/bringup/save-module-v6b-cache-20261020/`. Its D-cache-disabled
comparison module is 25,680 bytes, SHA-256
`32ce836e0abdb804922af058c0d5c4e5c6c9fcc9a3b50d50e136667859090bb0`,
from `tmp/bringup/save-module-v6b-nocache-20261020/`.
These RAM modules do not replace the v46 capture firmware in NOR.

Both require D-cache disabled on entry. The cached module additionally refuses
an enabled inherited MPU; it does not install a new memory map. It validates
the retained frame, enables its owned D-cache using the CMSIS invalidation
sequence, and enables I-cache for code execution. Capture DMA has already
stopped and SD transfers are CPU-polled. On completion it checks the stack,
cleans/invalidates/disables its owned D-cache, recomputes the frame checksum
uncached, finalizes the report, disables I-cache, and only then publishes
terminal DONE after barriers. Cached intermediate reports are not terminal
proof. The bench gate checks exact module bytes, request nonce, terminal proof,
card/filesystem state and the cache report before allowing another operation.

All tests below use the same illuminated 3,055,360-byte RAW frame, SHA-256
`5bf987c93eb0db31c916c8d8eeb996a32504f447170f5232d097d776fb9c844c`.
The PNG is a grayscale16 representation of all 1,527,680 sensor samples.

| Frozen v6b configuration | Saved files | PNG bytes | COMPLETE target time |
| --- | --- | ---: | ---: |
| Fast-none, D-cache disabled | `IMG00005.PNG` | 746,618 | 19.0995 s |
| Fast-none, D-cache enabled | `IMG00006.PNG` | 746,618 | 2.0945 s |
| Fast-none, three further cached runs | `IMG00008`, `IMG00010`, `IMG00015` | 746,618 each | 2.0872–2.1046 s |
| Fast-sub, three cached runs | `IMG00009`, `IMG00011`, `IMG00013` | 861,840 each | 2.1743–2.1937 s |
| Stored, three cached runs | `IMG00007`, `IMG00012`, `IMG00014` | 3,060,848 each | 3.6066–3.6129 s |

The first cached comparison is about 9.1 times faster, with identical PNG
bytes and preserved input checksum. Every listed operation reported success,
zero card errors, card idle and deinitialized, matching pre/post/post-clean
frame FNV `2297667238`, and final `CCR=0x201` with both caches disabled.
The later three rounds change mode order and create separate filenames; they
are not repeated overwrites of one file.

The comparison uses **COMPLETE**, which includes stack checking, cache cleanup
and final uncached frame validation. The earlier **TOTAL** field stops before
those steps. In `energy-v6b-cache-none-01/result.json`, TOTAL is 1.71331 s,
COMPLETE is 2.09449 s, and the uncached post-clean frame check alone takes
380.714 ms. Encoding takes 1.53855 s, including 0.28179 s inside output
callbacks; those intervals must not be added. COMPLETE starts inside
`save_main`, so it still excludes NOR module loading, entry BSS/stack
initialization, return and the final park. It is not a cold power-to-save time.

The corresponding D-cache-disabled comparison is
`energy-v6b-nocache-none-01/result.json`; repeated runs are
`energy-v6b-cache-<mode>-round<1..3>/result.json`, all under the checkpoint
directory. The `energy-` names identify collection runs; they do not by
themselves establish a measured per-save energy or an electrically synchronized
boundary. JS110 analysis and the final mode decision remain to be consolidated.

### Larger readback and exact pixel proof

V6b reuses encoder scratch storage for a 256 KiB READ buffer, while SAVE keeps
its 32 KiB output buffer. The host gets both address and capacity from the
exact module manifest. There is still one complete RAW frame and no second
image buffer.

[`readback.py`](../../firmware/capture-sd/readback.py) retrieves a complete file
through bounded guarded READ requests, validates PNG structure and every chunk
CRC, then independently decodes the pixels against the original RAM frame.
It never resets, formats, deletes or automatically retries on error.

- `download-v6b-cache-none-01/verified.json`: `IMG00006.PNG`, 746,618 bytes,
  three hardware reads, SHA-256
  `466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330`.
  This is byte-identical to the v5 output.
- `download-v6b-cache-sub-01/verified.json`: `IMG00009.PNG`, 861,840 bytes,
  four hardware reads, SHA-256
  `4b0980480cf8fe348ec6c6fdd4a9f0f59ac1de933bfd5554a2cf10927c7e04b9`.

Both pass grayscale16, `sBIT=10`, all chunk CRCs and exact equality of all
1,527,680 decoded pixels to `RAW10 << 6`. This proves these two complete
readbacks; it is not a claim that every file in the timing table has received
full host verification. Images and raw card contents remain local.

### Selected v8b compressor and v50 integration

**Decision:** use the v8b dedicated fast compressor, no PNG row filter,
D-cache enabled and `-Os`, in the integrated awake v50 prototype. Preserve
all ten sensor bits in grayscale16 PNG and retain the 32 KiB filesystem sink.
The canonical module build is byte-identical to the tested binary:
27,420 bytes, SHA-256
`91e1edfa43f95a9608b94457cfbf900c6f51d5ecd10d2b3b7667c84d40cd3844`.
Frozen v7/v6b builds remain identifiable historical comparisons.

V7 first made the uncompressed baseline a direct stored-DEFLATE stream, with
one block per row and a single zlib header/Adler footer. Bypassing miniz's
unnecessary dictionary/literal work reduced its COMPLETE time from the old
v6b 3.61 s to 1.95–1.96 s. The output grew slightly, from 3,060,848 to
3,080,000 bytes. Complete readback of `IMG00016.PNG` in
`download-v7-stored-01/verified.json` confirmed exact pixels.

The dedicated miniz fast loop was previously disabled by the conservative
unaligned-access configuration. Simply enabling it would retain misaligned
typed-pointer traversal and a four-byte distance copy into a nominal
two-byte field. The reviewed local patch uses byte-pointer traversal,
forced-inline bytewise little-endian reads and exactly two distance bytes.
The builder adds `-mno-unaligned-access` and retains `-Os`. Original upstream
hashes and the license remain untouched; the
[local patch record](../../firmware/png-encoder/vendor/miniz/LOCAL_PATCHES.json)
and [exact diff](../../firmware/png-encoder/vendor/miniz/fast-loop-byte-safe.patch)
describe the altered vendor code. Canonical tests include dictionary-wrap/
tail cases, independent decoding, input/workspace guards and 432 standalone
ASan/UBSan scenarios with the fast path explicitly enabled.

| Same retained frame, frozen build/mode | Runs | PNG bytes | COMPLETE time | Conditional COMPLETE energy bounds across runs |
|---|---:|---:|---:|---:|
| V7 direct stored DEFLATE | 2 | 3,080,000 | 1.9541–1.9616 s | 0.9585–0.9774 J |
| V7 general fast compressor, no filter | 2 | 746,618 | 2.0899–2.1387 s | 0.9056–0.9829 J |
| **V8b dedicated fast loop, no filter** | **2** | **919,353** | **1.6831–1.6842 s** | **0.7675–0.8129 J** |
| V8b direct stored DEFLATE | 1 | 3,080,000 | 2.3158 s | 1.1307–1.1820 J |

The selected fast matcher produces about 23% more bytes than the earlier
general compressor, but its encode time excluding callbacks falls from about
1.25 s to 0.696 s. The new output is still about 70% smaller than stored PNG
and saves faster on these runs. V8b also has different alignment compiler
settings; this is a comparison of complete builds, not a pure matcher-only
experiment. SD callback/busy time varied, especially in the intervening
stored run. One image/card is insufficient to claim a universal latency,
noise-scene ratio or lifetime energy bound.

The later v5 energy run used legacy TOTAL and took 18.7987 s; the initial
successful v5 save took 18.8667 s. These establish the roughly 18.8-second
uncached starting point. They should not be described as full cold cycles or
as sharing the exact later COMPLETE boundary. COMPLETE includes the
approximately 380.7 ms uncached final integrity scan, but excludes module
loading, entry setup and final return.

The complete selected benchmark PNG, `IMG00023.PNG`, was read back in four
chunks and verified against all 1,527,680 samples of the same retained frame:
919,353 bytes, SHA-256
`2e29c4193146c4e3cbbe5a9f7dbdc7ec2c2c634e546c0181d613249b8795cec6`.
See `download-v8b-fast-none-01/verified.json`.

#### Compiler experiments and strict context checks

The `-O2` candidate completed a functional save but its final context gate
rejected `CONTROL=0x0C` at the exact terminal park. Disassembly showed
compiler-generated FP/vector instructions in the compressor initialization;
FPCA and SFPA were set, while execution remained privileged on MSP. The core
was not reset. Fresh successful terminal/filesystem/card-idle/cache-off
proof and `FPCCR.LSPACT=0` were established before setting `CONTROL=0` and
verifying the resulting context. The general strict gate was not weakened.
This run is excluded from qualified time/energy comparisons.

`-O3` was compiled and reviewed offline but never executed. An initial cache
spill-order concern was reviewed against M55's allocation-only cache-disable
behavior; no hardware claim depends on resolving that optimization. The
selected build retains `-Os`.

#### Energy interpretation

The finalized log has contiguous finite power samples and zero dropped
chunks. The direct power channel is integrated; averaged current and voltage
are not multiplied. The final raw-log SHA-256 is
`a78b316350d47d6d0cf6666317db02bd1369651909edc126deab5392b20f82e9`.

The table's energy bounds assume COMPLETE cycles at the reported 400 MHz
and an explicitly chosen ±50 ms UTC alignment uncertainty. The secondary
analysis evaluates every possible placement of that fixed duration inside
the enlarged host bracket, plus chunk partial-overlap extrema/sum bounds.
It does not select a favorable waveform feature. The measured driver mapping
residual was within this assumption, but there is no external absolute
synchronization proof. Whole host-bracket energies include setup/polling tails
and must not be relabeled as target-save energy.

No baseline is subtracted from the COMPLETE bounds. Calibration, clipping,
CPU-clock error and current bypassing the Joulescope are outside them. The
boundary includes Nucleo overhead. These are conditional save-stage bounds,
not full cold-cycle or production-camera energy. The
[final energy archive](../../firmware/capture-sd/evidence/2026-10-20-hardware/energy-analysis/README.md)
includes portable replay and all assumptions.

#### Installed automatic pipeline and cold-cycle proof

V50 embeds v8b and retains the awake completion policy. Its first 64 KiB
sector is
`9ffc2c1cbaacf9f60258343ac6a061b35fb62f8b62b42c1a5b50ccc5f432f5cd`.
The receiver completes and stops capture/sensor activity, then loads the
CRC-checked save module from NOR offset `0x6000`. The module is not loaded
before exposure. The preserved early recovery branch still bypasses capture
and storage when requested.

| Normal cold boot | Automatic file | Bytes | Save-module COMPLETE |
|---|---|---:|---:|
| `v50-auto-cold-01` | `IMG00024.PNG` | 869,254 | 1.7403 s |
| `v50-auto-cold-02` | `IMG00025.PNG` | 905,179 | 1.6865 s |
| `v50-auto-cold-03`, after recovery | `IMG00026.PNG` | 918,279 | 1.7101 s |
| `v50-final-normal-cold` | `IMG00027.PNG` | 970,610 | 1.7692 s |

The first three `v50-auto-proof-0N/verified.json` records and
`v50-final-auto-proof/verified.json` report success, zero card errors and
idle/deinitialized media. These are different captured
frames and include their card-initialization costs; they are not pooled with
the fixed-frame RAM benchmark. The first file received complete four-chunk
host readback: PNG SHA-256
`58666a754ae3e646efb75dbb5179e31f85921cb0b10629a25875dc194f60b9dd`,
RAW SHA-256
`d84b3e53d5cd8d97861deb4a72c92df91d465c5d3be6212be239187782d29fee`.
All PNG CRCs, grayscale16/`sBIT=10` and all 1,527,680 exact sensor samples
passed. See `download-v50-auto-01/verified.json`. The image is dark but the
LED panel is discernible at the existing fixed short exposure. Exposure
tuning and the potentiometer were not implemented during this task.

After the second normal cold boot, `v50-recovery-cold-01` and
`v50-recovery-proof-01` passed the exact early recovery gate: nine good pulses,
zero bad pulses, PE6 request/source selected, `CCR=0x201`, `CONTROL=0` and
idle XSPI. This requested branch performed no NOR or card write. The third
normal cold boot then returned to automatic capture/save.

The original v5 `IMG00001.PNG` was fully read again after those first three
normal cold saves and recovery. Its 746,618 bytes retain the original SHA-256
`466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330`
and exact pixels, recorded by `download-old-image-after-v50/verified.json`.
This establishes preservation through the completed tested operations, not
resilience to arbitrary power loss.

The fourth normal boot saved `IMG00027.PNG` and left the application in its
awake completion loop at `0x343022D8`, explicitly resumed after inspection.
LED phase is 0 with active-low off mask `0x501`; the SD card is idle,
deinitialized and no longer controller-owned. At **06:55:51 UTC** the JS110
helper stopped cleanly, restoring its starting range 128. Last measured
input was 4.881844 V/80.1278 mA; the target remains powered. COM8 is closed,
BREAK released and both boot jumpers remain on pins 1–2.
The [final-state record](../../firmware/capture-sd/evidence/2026-10-20-hardware/results/final-state.json)
supersedes earlier stopped-bench and pending-jumper instructions.

Full cold power-to-file timing still needs a defined electrical boundary.
V50 remains awake with LEDs off after successful save; WFI/debug recovery,
regulator-off shutdown, arbitrary power loss, retention and production power
remain unqualified. A final review also retained a safe-failure limitation:
the RX abort drain bound is 64 words versus a 256-word FIFO. With more
queued receive data, an error can leave `media_idle=0`, which blocks
automatic reset/retry and requires diagnosis. Qualify that cleanup later;
the tested binary was not changed for it.

### Recovery investigation remains open

The awake baseline is operational, but it does not establish why the earlier
sleeping image and warm recovery requests lost access. Read-only checks from
the completed v46 capture found `RCC_MISCENR=0x41`,
`RCC_MISCLPENR=1`, `RCC_MISCRSTR=0`, `RCC_MEMENR=0x17FF`,
`RCC_MEMLPENR=0`, `SCB_SCR=0`, and **`DBGMCU_CR=0`** despite the prefix's
attempt to set `DBGCLKEN|DBG_SLEEP`. BSEC debug authorization read back as
`0xB451B400` and `0xB4`, with HDPL `0x51`. Sources are
`v46-awake-clocks.log` and `v46-awake-debug.log`.

An offline source and assembly review found no receiver/HAL initialization
that clears `DBGMCU_CR`. The duplicate receiver debug setup is compiled out.
Also, the [October 17 PD0 diagnostic](../../firmware/boot-timing/experiments/pd0-dump/README.md)
had already read zero in firmware immediately after setting the register,
before the host attached. The recurring zero therefore cannot be attributed
to receiver HAL or CubeProgrammer from the current evidence.

The following are documented mechanisms and testable hypotheses, not a
diagnosis of the observed failure:

- Sleep clock gating can make SRAM/debug access unavailable when the intended
  debug override has not taken effect. RM0486 §14.6.9 warns that debugger
  access to an unclocked domain can require POR, because system reset does
  not reset the debug interface. §§78.5.3 and 78.12.20 distinguish debug reset
  and low-power debug behavior. The measured zero override and SRAM
  low-power enables make this relevant; they do not prove WFI caused the
  original loss. [RM0486 Rev 4](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf)
- ES0620 §2.2.18 documents incorrect NRST reset behavior on affected silicon,
  potentially requiring a full power cycle. The specified software-reset
  workaround needs isolated qualification; its sample retained-word address
  overlaps this application's frame buffer and must not be copied directly.
  §2.2.17 also says BSEC debug authorization is writable once per cold reset.
  §2.2.22 describes a separate software-reset/peripheral-clock ROM failure.
  None alone proves the cause of these BREAK/NRST failures.
  [ES0620 Rev 5](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf)
- The pulse guard uses cycle thresholds for a nominal 400 MHz clock before
  its later clock-profile check; initial DWT access also precedes explicit
  debug-clock setup. These are candidates for hardening, not measured warm
  boot defects. UM3234 §3.12.1 describes the nominal cold-boot clock profile.
  [UM3234](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf)

The review used cached primary manuals:
`tmp/capture-research/rm0486-compact.txt`,
`tmp/hardware-review/mcu/STM32N6_ES0620_errata.txt`, and
`tmp/hardware-review/mcu/STM32N6_UM3234_boot_ROM.txt`.
Keep the installed v50 completion awake for storage work. A later isolated diagnostic can compare
DBGMCU identity/control/status through its documented aliases and save
firmware readbacks before host attachment and before sleep. No speculative
reset or sleep experiment should interrupt active or uncertain storage I/O.
