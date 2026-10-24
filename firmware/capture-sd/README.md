# Capture → PNG16 → FAT32 prototype

**October 23 baseline completed; original v59 restored.** Three unchanged-v59
cold power signatures measured median **2.714624 s / 1.288948 J** on the
JS110-fed board branch. Temporary instrumented firmware measured repeated
same-frame saves at **2.099228–2.104129 s**, with median SD driver write
throughput **2.64996 MB/s**. IMG61–64 passed full PNG readback and every pixel
matched the retained RAW frame. Original v59 was independently read back after
restoration, UART recovery passed, and the final cold boot returned to about
8.07 mA. That final image and SBF were not reread. See the
[baseline report, phase inference limits and final bench state](evidence/2026-10-23-one-bit-baseline/README.md).
The SD wiring remains native one-bit; four-bit operation has not been tested.

**October 20: autonomous cold capture → PNG16 → SD → Standby is installed.**
The installed **v59 Standby image** has verified first-sector SHA-256
`7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63`.
It captures one frame and saves a new numbered PNG using the selected
**v8b fast-loop compressor, no row filter, D-cache enabled, `-Os`**.
Successful save now shuts down peripherals and enters MCU Standby. Four
tested Standby cycles each recovered through the existing PE6 UART request
and ST-LINK BREAK/NRST on the first attempt; the retained hardware SBF flag
confirmed Standby entry after every cycle. No boot-jumper changes were needed.
See [low-power evidence and reproducible build](evidence/2026-10-20-low-power/README.md)
and [shutdown implementation](low_power/peripherals.md).

**October 20 follow-up:** after the two [CN10-disconnected power cycles](evidence/2026-10-20-stlink-off/README.md),
the user inspected the SD card and reported that the photos check out. This
resolves the pending user image check for those runs; it is not an automated
byte-for-byte/CRC readback or a new SBF measurement. The original measurement
archive retains its contemporaneous pending status.

## Current power-up to Standby flow

```mermaid
flowchart TD
    A[Power applied / reset released] --> B[STM32 boot ROM loads small bootstrap from NOR]
    B --> C{Early recovery request?}
    C -->|Yes| R[Enable debugging and park; no photo]
    C -->|No| D[Initialize memory, sensor and receiver; red LED]
    D --> E[Expose and capture one RAW10 frame into RAM; blue LED]
    E --> F[Validate frame; stop capture and sensor streaming]
    F --> G[Load and check save module from NOR]
    G --> H[Green LED; initialize SD and mount FAT32; choose unused image number]
    H --> I[Convert samples to 16-bit gray; compress PNG while streaming to TMP file]
    I --> J[Sync and close; wait for card; rename to PNG; wait again]
    J --> K[Deinitialize SD; clean caches and recheck frame integrity; LEDs off]
    K --> L[Load shutdown module; check successful save and idle peripherals]
    L --> M[Disable receiver, camera interface and NOR interface; LEDs off]
    M --> N[Enter MCU Standby; board-controlled switched rails turn off]
```

This is the successful path in v59. Failure paths preserve diagnostics and
leave power on instead of pretending shutdown succeeded. Exposure does not wait
for SD initialization or PNG/save-module loading. PNG encoding shifts each
10-bit sample left six bits and uses the selected fast compressor without a row
filter. MCU Standby ends this boot; another photo requires reset/power cycling.
The external LTC regulator remains enabled. The last board-branch idle current
was about 8.23 mA, so this is not full external power removal.

Three complete cold cycles measured **1.410–1.424 J** and **2.96–2.98 s**
from observed current onset to the stable Standby plateau. Terminal board
current was **8.10–8.21 mA**, versus about **80.03 mA** awake. These are
JS110-fed Nucleo-branch measurements, not isolated production-camera
consumption. See [measurement method and limits](cycle-energy.md).

The three measured-cycle files, IMG00040–42.PNG (1.78–1.79 MB), passed full
post-Standby readback, all PNG chunk CRCs and independent decoding. The
original IMG00001.PNG remains byte-identical. These checks use a
[guarded RAM-only READ bridge](low_power/readback_recovery/README.md);
Standby's lost RAW frame cannot be compared again.

The prior v50 awake baseline's first automatic file, `IMG00024.PNG`, was read back in full: every one of
its 1,527,680 pixels exactly matched the retained sensor frame. Three further
cold boots saved distinct files. A requested recovery cold boot reached the
exact early recovery park without writing NOR or the card.

Same-frame v8b benchmark saves took **1.6831–1.6842 s**, versus roughly
**18.8 s** for the initial uncached v5 save, and produced **919,353 bytes**.
These are save-stage measurements, not cold power-to-photo times. Finalized
power analysis gives conditional save-duration bounds of **0.7675–0.8129 J**
across the two runs. See [measurement scope](#timing-and-energy-scope),
[the implementation log](../../docs/decisions/capture-png-sd-2026-10-20.md)
and [hardware evidence](evidence/2026-10-20-hardware/README.md).

The user authorized destructive SD formatting for development and explicitly
left sudden power-loss protection unqualified. Normal firmware never formats
a card. Existing PNG/TMP filenames are skipped, older files are not
overwritten, and full storage stops a save.

## Data and execution

The 1120 × 1364 RAW10 frame stays at `0x34000000`, right-aligned in little-endian
16-bit words. PNG preserves every sensor bit as grayscale16 `sample << 6`,
with `sBIT=10`. There is no gamma transform, black-level correction or fabricated
capture timestamp. FAT dates use a documented 2000-01-01 placeholder until an
RTC is integrated.

The receiver completes and validates its first frame, stops capture and the
sensor, then loads the save module from NOR offset `0x6000`. The loader reuses
the verified finite XSPI1 read configuration, checks the exact module CRC and
executes it in high SRAM. No SD initialization, PNG module load or compression
is added before exposure. V59 loads its 3,764-byte shutdown module from NOR
offset `0xE000` only after save completes. Its early receiver is 15,560 bytes,
564 bytes larger than v50; its effect on exposure timing still needs a separate
measurement. The existing first-frame deadline guard remains unchanged.

The module checks capture geometry, error history, frame count, RAW10 format,
DMA byte count, frame canary and checksum. It uses native **one-bit SDMMC2 at
25 MHz, 3.3 V**, matching the existing breakout. A 32 KiB sink combines small
PNG chunks into filesystem writes. There is no second frame buffer, heap,
storage DMA or RTOS.

Each save creates `IMG00001.TMP` or the next unused number, writes the PNG,
syncs/closes it, waits for card readiness, renames it `.PNG`, then checks
readiness again. This identifies incomplete saves but does **not** establish
atomicity or protect older files from an arbitrary power cut inside the card's
flash translation layer. Failures preserve diagnostics and leave power on.

Red indicates boot, blue acquisition and green saving; success turns the LEDs
off and enters Standby. Standby loses the frame and high-SRAM diagnostics and
disables ordinary debug access. Recovery therefore sends the qualified UART
pulse train across an NRST pulse, then verifies the exact early recovery park.
It does not resume the completed capture. The LTC regulator is not switched
off by this firmware; Nucleo standby overhead remains.

Both the late-loader `LPL1` and completion `LPM1` records own the terminal path.
The ordinary maintenance helpers refuse these states even if capture or SAVE
has completed. Never bypass those guards to halt an active shutdown.

## Selected compressor and measured tradeoff

The original miniz stored mode still performed unnecessary dictionary/literal
work. V7 replaced it with direct streaming stored-DEFLATE blocks, one per row.
That reduced the uncompressed path to **1.9541–1.9616 s** for 3,080,000 bytes,
with a complete readback and exact pixels.

V8b enables the dedicated fast matcher, replacing misaligned typed-pointer
accesses with byte-pointer traversal and defined bytewise little-endian reads.
Its match-distance token writes exactly two bytes. The original license and
upstream records remain intact; the [local patch is explicit](../png-encoder/README.md#dependency-provenance).
It accepts a larger compressed file than the older general match loop in
exchange for lower CPU cost.

| Frozen module and mode | Runs | PNG bytes | COMPLETE target time |
|---|---:|---:|---:|
| V7 direct stored DEFLATE | 2 | 3,080,000 | 1.9541–1.9616 s |
| V7 general fast compressor, no filter | 2 | 746,618 | 2.0899–2.1387 s |
| **V8b dedicated fast loop, no filter** | **2** | **919,353** | **1.6831–1.6842 s** |
| V8b direct stored DEFLATE | 1 | 3,080,000 | 2.3158 s |

These use the same retained frame, a powered previously used card, and new
filenames. V8b also adds strict-alignment compiler settings, so this compares
complete builds rather than an isolated matcher-only change. Card/callback
time varied. Fast-none is selected for the prototype because it beat the
direct stored path on measured complete time, conditional energy and size
for this frame. Scene noise and card behavior can change that result.

The selected benchmark file `IMG00023.PNG` received full host verification:
919,353 bytes, SHA-256
`2e29c4193146c4e3cbbe5a9f7dbdc7ec2c2c634e546c0181d613249b8795cec6`.
Every PNG chunk CRC and all 1,527,680 pixels passed.

The `-O2` experiment completed its filesystem operation, but the strict final
CPU-context check rejected `CONTROL=0x0C`. Compiler-generated FP/vector
instructions set FPCA/SFPA. After exact successful code/terminal/card-idle/
cache-off proof and `FPCCR.LSPACT=0`, `CONTROL=0` was restored and verified
without reset. The strict guard was not relaxed. That run is excluded from
qualified comparison tables. `-O3` was built but never executed.

## Automatic capture/save and recovery

V50 embeds the selected v8b module after the preserved early recovery and
sensor/receiver sequence.

| Cold boot | New file | Bytes | Save-module COMPLETE |
|---|---|---:|---:|
| First | `IMG00024.PNG` | 869,254 | 1.7403 s |
| Second | `IMG00025.PNG` | 905,179 | 1.6865 s |
| Third normal boot, after recovery | `IMG00026.PNG` | 918,279 | 1.7101 s |
| Final normal boot | `IMG00027.PNG` | 970,610 | 1.7692 s |

These are newly captured frames, not repetitions of the fixed benchmark image.
Each save reported success, zero card errors and idle/deinitialized media.
The first file's complete four-chunk readback verified grayscale16/`sBIT=10`,
all PNG CRCs and exact equality to the original sensor samples. Its SHA-256 is
`58666a754ae3e646efb75dbb5179e31f85921cb0b10629a25875dc194f60b9dd`.
The LED panel is discernible in this dark image at the existing fixed short
exposure; exposure tuning and the potentiometer were not part of this change.
Images and RAW frames remain local.

After the second normal boot, C0 VCP recovery passed on a cold cycle: nine good
pulses, zero bad pulses, request selected, exact early park, `CCR=0x201`,
`CONTROL=0`, and idle XSPI. This branch performed no NOR or card write.
See the [first automatic readback proof](evidence/2026-10-20-hardware/results/download-v50-auto-01/verified.json)
and the hardware archive for repeated boot/recovery records and final state.

After the first three cold saves and recovery, the original `IMG00001.PNG`
was read in full again: all pixels and its original SHA-256
`466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330`
still matched. This verifies preservation through these completed operations;
it is not an arbitrary-power-loss test.

The historical v50 final normal boot left `IMG00027.PNG` complete, LEDs off (phase 0,
active-low off mask `0x501`) and the CPU awake at the `0x343022D8` completion
loop, explicitly resumed after inspection. The card was idle and deinitialized.
At **06:55:51 UTC**, the JS110 helper stopped cleanly and restored range 128;
the last measured input was 4.881844 V at 80.1278 mA. At that checkpoint the target remained
powered, COM8 was closed, BREAK released and JP1/JP2 on pins 1–2.
See [historical bench state](evidence/2026-10-20-hardware/results/final-state.json);
the [v59 archive](evidence/2026-10-20-low-power/README.md) supersedes it.

## Timing and energy scope

The initial v5 save took 18.8667 s; the later same-frame energy run took
18.7987 s. Both used D-cache disabled. V6b cache ownership reduced the
comparable fast-none COMPLETE interval from 19.0995 s to about 2.09 s;
v7/v8b then improved the encode path. Older v5 TOTAL measurements do not
include all of v6b's subsequently added completion diagnostics.

**COMPLETE** includes stack checking, owned-cache cleanup and the uncached
final frame checksum. **TOTAL** ends before those steps. The uncached frame
recheck alone takes about 380.7 ms. COMPLETE starts inside `save_main`, so it
excludes NOR module loading, entry BSS/stack initialization and final return/
parking. It is not a full cold power-to-file time. Encoder wall time includes
output callbacks; encoding, callback, SD and busy intervals overlap and must
not be added as independent costs.

Finalized JS110 power-sample analysis bounds the selected COMPLETE interval at
**0.7675–0.8129 J**, versus **0.9585–0.9774 J** for the two v7 direct-stored
runs. These are conditional bounds using the reported 400 MHz clock and an
explicitly assumed **±50 ms UTC alignment uncertainty**. The analysis includes
every possible placement of that fixed duration inside the enlarged host
bracket, using chunk sums/extrema. It does not choose a favorable waveform
alignment. Whole host-bracket energy includes setup and polling tails and
has a different scope.

The power stream finalized with contiguous finite power samples and zero
dropped chunks. The bounds exclude calibration, clipping, CPU-clock error and
current bypassing the JS110. The measured boundary includes Nucleo overhead.
They are neither isolated DUT energy nor full cold-cycle energy; no baseline
is subtracted from the COMPLETE bounds. See the
[final analysis and portable replay](evidence/2026-10-20-hardware/energy-analysis/README.md).

For future collection, the sole JS110 owner can use
`js110_session.py --power-stream-log <new.jsonl>`. This adds driver power-sample
sums and restores additional settings afterward. `energy.py` rejects gaps,
nonfinite data and old current/voltage-only logs, and bounds partial chunks
with supplied timing uncertainty. `energy_sliding.py` adds all-placement
fixed-duration bounds. Native sample IDs are preferred when external markers
actually establish synchronization.

## Memory and cache ownership

| Region | Use |
|---|---|
| `0x34000000..0x342E9EFF` | Original RAW10 frame |
| `0x342E9F00..0x342E9F1F` | Capture overrun canary |
| `0x34300000` | Receiver |
| `0x34320000..0x3439FFFF` | Save code, encoder and filesystem workspace |
| `0x343A0000..0x343AFFFF` | Reserved 64 KiB save stack |
| `0x343B0000` | Stack top |
| `0x343C0000..0x343C1FFF` | V59 late shutdown code; mutually exclusive with the historical maintenance helper |
| `0x343F9B00`, `0x343F9C00`, `0x343F9D00` | Late-loader, completion and peripheral-shutdown proofs |
| `0x343F9E00` | NOR save-loader proof |
| `0x343F9F00` | Explicit bench request |
| `0x343FA000` | Save report |
| `0x343FA200`, `0x343FA400` | Card and filesystem snapshots |

`save_entry.S` temporarily lowers MSPLIM from the receiver's 4 KiB stack limit
to the reserved 64 KiB floor, preserving it for return, and fills lower stack
with a canary. The compressor alone needs more than 5.5 KiB of stack.
The standalone linker rejects overlap and code exceeding its 40 KiB NOR
module window; the v59 packer additionally limits SAVE to the 32 KiB before
the late module at `0xE000`.

The selected module is **27,420 bytes** of code/data and **300,472 bytes** of
BSS, SHA-256
`91e1edfa43f95a9608b94457cfbf900c6f51d5ecd10d2b3b7667c84d40cd3844`.
Its entry is `0x34320001`, bench entry `0x34320051`, terminal park
`0x3432006E`. READ reuses encoder scratch for 256 KiB chunks; SAVE retains a
32 KiB output buffer. Exact buffer addresses come from the reviewed manifest.

D-cache must be disabled on entry; the cached variant also rejects an enabled
inherited MPU. After frame validation, it enables its own D-cache through the
CMSIS invalidation sequence. Capture DMA has stopped and SD is CPU-polled.
After card/filesystem completion it checks stack canaries, cleans/invalidates/
disables its owned D-cache, and checks the frame again uncached. It finalizes
diagnostics, disables I-cache, then publishes DONE after barriers. Intermediate
cached progress is not proof of completed I/O. Qualified reports have matching
pre/post/post-clean checksums and final `CCR=0x201`, both caches disabled.

## Reproducible build

The pinned CubeN6 headers and GCC toolchain come from
`capture-timing/build_raw10.py`. Frozen v45b remains the capture/recovery base.
Builders create new directories and never operate hardware:

```powershell
python firmware/capture-sd/build_module.py --out tmp/bringup/my-save-module --data-cache
python firmware/capture-sd/build.py `
  --base tmp/bringup/capture-vcp-recovery-v45b-20261020 `
  --module tmp/bringup/my-save-module `
  --out tmp/bringup/my-capture-sd --awake
```

`-Os` is default, with explicit `-mno-unaligned-access`. The canonical cached
build reproduces the tested v8b binary exactly. `--optimization O2/O3` are
experimental alternatives. Keep `--awake` for this historical awake-build
example; omitting it without `--completion` selects the unqualified legacy
WFI path. V59 uses `--completion standby`; its exact portable recipe is in
the [low-power archive](evidence/2026-10-20-low-power/README.md).
The builder verifies input hashes, memory bounds and
byte identity of early recovery code/literals. A successful build does not
waive the exact maintenance park, allowlist or programming readback checks.

## Guarded RAM operations and readback

`prepare_maintenance.py --layout raw10` requires an intact completed capture.
After an automatic save, also pass
`--save-build <module-directory> --save-sha256 <reviewed-module-sha256>`.
It verifies exact live code, loader return, successful filesystem result and
idle/deinitialized media before its first halt. Active/failed records are
rejected even if the capture trace says event 40. Nonce-zero automatic saves
enter subsequent RAM operations only through this checked maintenance park.

The bench runner accepts that exact park or its own exact successful park,
and refuses active/failed/unknown state, altered code, stale requests and
non-idle media. It never resets, changes target power, sends NOR commands or
automatically retries a storage failure.

```powershell
python firmware/capture-sd/bench.py format `
  --build tmp/bringup/my-save-module --out tmp/bringup/sd-format-01 `
  --expected-sha256 <reviewed-module-sha256> --format-card --execute
python firmware/capture-sd/bench.py save `
  --build tmp/bringup/my-save-module --out tmp/bringup/sd-save-01 `
  --expected-sha256 <reviewed-module-sha256> --mode fast-none --execute
python firmware/capture-sd/readback.py `
  --build tmp/bringup/my-save-module --expected-sha256 <reviewed-module-sha256> `
  --out tmp/bringup/sd-download-01 --name IMG00023.PNG --bytes 919353 `
  --frame <local-raw-frame.bin> --execute
```

Every operation needs a new output directory. READ capacity is manifest
controlled: current modules allow 256 KiB, older modules only 32 KiB. Full-file
readback checks PNG structure/CRCs and every pixel against the retained RAW
frame, using the same gates for each chunk. Offline revalidation is
`readback.py --file <PNG> --frame <RAW-frame>`. Images remain local.

The first v4 format failed because TX refills stopped at 144 words before
the N6's 256-word FIFO startup condition. V5 corrected this with bounded
fill-until-full/final-word behavior. Independent CMD13/DAT0 ready evidence
preceded the controlled restart; the failed record was never silently treated
as idle. See [the incident](../../docs/decisions/capture-png-sd-2026-10-20.md#first-format-failure-and-correction).

## Verification and remaining qualification

```powershell
python firmware/png-encoder/test_png16.py
python firmware/capture-sd/fs/tests/test_photo_fs.py
python firmware/sd-storage/test_sd_driver.py
python firmware/capture-sd/test_save_cache.py
python firmware/capture-sd/bench.py --self-test
```

Canonical encoder tests pass 16 cases, including 432 ASan/UBSan C scenarios;
actual-FatFs integration passes 14. Tests cover exact pixels, all three modes,
dictionary/tail boundaries, alias checks, failure injection, no-overwrite
behavior, cleanup and refusal to halt uncertain storage operations.

V59 Standby entry and UART reset recovery are bench-qualified for the tested
cycles. A current-threshold-to-Standby energy measurement does not independently
identify electrical power-good, exposure, or filesystem completion timestamps.
LTC regulator-off shutdown, arbitrary power loss, long retention,
card-to-card variation and isolated production power remain unqualified.
The RX abort drain bound is still 64 words versus the N6's 256-word FIFO:
a read fault with more queued data can leave `media_idle=0` and require
separate diagnosis. It fails closed; it does not reset/retry automatically.
That cleanup path needs later isolated qualification, without changing the
currently tested binary.
