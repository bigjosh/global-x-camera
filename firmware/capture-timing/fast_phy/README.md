# Guarded freerun data-lane sequencing experiment

This offline builder derives a matched pair from the exact v34c sector
`14b6015e0c5705ce5bde655470977851e32cce01fa0164ccda163b892dca3222`.
It does not access instruments, the debugger, or flash. The first candidates are
now qualified on the bench: the v35 STREAMING sequence removed startup and
through-first-frame D-PHY errors while retaining the first physical exposure.
The v36 shutdown extension then completed five cold starts with zero errors
through sensor STOP: three default-exposure runs and two minimum-exposure runs.
The frozen build manifests still say `hardware_status: untested`; that records
their status when built. Subsequent qualification is recorded in the
[October 17 fast-PHY evidence](../evidence/2026-10-17-fast-phy/README.md).

The first matched pair retains the qualified PE1 recovery guard and the original
freerun sensor configuration, including 1428 coarse exposure lines (about 11 ms).
Its prefix sources are copied byte-for-byte from v34c. The later short-exposure
variants change only the two manual-coarse bytes in the sensor setup; gain,
format, frame period and recovery guard are preserved. Receiver-size and CRC compiler
constants change; the raw prefix remains 4432 bytes, its wrapped image 5472 bytes,
and the recovery park remains `0x3418078c`. Offline comparison confirms the entire
entry/recovery code and its literal pool through `0x34180a58` are byte-identical.
The earliest prefix byte difference is at `0x34180c30`, the receiver-size constant.

The receiver differs only by `FAST_DATA_STREAMING=0` or `1` between controls:

- `--data-enable early` releases clock and data modules together, as v25 did.
- `--data-enable streaming` releases the clock module early with `PCR=0x03`;
  after START acknowledgement and STREAMING, it enables data modules (`0x0f`).

Both configure the receiver within the original 4.5 ms post-START budget. That
budget now applies to configuration completion, not VC arming. Both observe data
STOP continuously for 100 nominal microseconds after STREAMING, then arm the VC
snapshot. This follows data-enable-before-VC-START ordering. The STOP interval is
an empirical observation guard inherited from v33, not a specified PHY T_INIT.
Its wait has both a 50 ms timeout and a finite iteration bound.

There are no extra sensor I2C transactions, follower configuration, or FSYNC
commands. Exposure is still sensor-autonomous: v25 measurements put its first
STROBE about 80–100 microseconds before the host observed STREAMING. About 11 ms
of integration then remains before the measured first readout at the default
exposure. First-frame capture also passed at 5, 21 and 40 coarse lines, including
the documented minimum request of 5 lines. In v35, the smallest measured
arm-to-first-VSYNC margin was 95.04 microseconds at 5 lines. The current v36
minimum is 51.36 microseconds, with its two 5-line runs spanning 51.36–70.88
microseconds. These are observed margins on this board/configuration, not
guaranteed worst-case bounds.

The diagnostic adds about 1 KiB to the receiver, loaded while the sensor starts.
Its code and RAM records can add small timing overhead. The matched control is
necessary to separate sequencing effects from instrumentation. No new error flag
clear or mask is added; the original error sources remain enabled for startup and
capture, and the inherited HAL still performs its usual IRQ handling. Raw
snapshots precede that handler so a cleared flag cannot hide an observed error.

## Measured v35 qualification

The matched 1428-line controls measured START-write-complete to first STROBE at
5302.56 microseconds with early data enable and 5303.20 microseconds with
STREAMING data enable. The 0.64 microsecond difference supports no meaningful
added exposure-start delay from the new receiver sequencing. Absolute cold-start
times also contain the varying ROM/rail portion; compare the sensor-relative
interval when assessing this change.

The matched minimum-exposure control agrees: at 5 lines, early data enable took
5361.28 microseconds from START completion to first STROBE, versus 5361.44
microseconds for STREAMING (a 0.16 microsecond difference). Both measured a
45.92 microsecond STROBE and preserved frame ordinal1. The roughly 60 microsecond
increase compared with the 1428-line case occurs in both controls; it is shared
sensor/exposure behavior, not added delay from receiver sequencing. Early mode
reported its raw startup lane-state error before any STROBE, while STREAMING
reported none until sensor STOP.

| STREAMING coarse lines | START complete → first STROBE | Arm → first VSYNC | First VSYNC / frame STROBE ordinal |
|---:|---:|---:|---|
| 1428 | 5303.20 µs | 11022.88 µs | 1 / 1 |
| 5 | 5361.44 µs | 95.04 µs | 1 / 1 |
| 21 | 5304.80 µs | 204.96 µs | 1 / 1 |
| 40 | 5299.20 µs | 349.12 µs | 1 / 1 |

These runs returned complete frames with the original byte-count/canary/format
checks passing, zero FAST overflow, and zero startup/through-first-frame error
reports. The default capture was also visually checked. The 5-line first STROBE
width measured 45.92 microseconds. A single frame count was not used as proof of
first-exposure capture: the VSYNC and frame records both tracked STROBE ordinal1.

The early control retained its startup lane-state error. v35 STREAMING still
reported a separate error during sensor STOP, after snapshot439 (pipe already
stopped) and before snapshot436 (sensor STOP returned). The v36 option below
removed that shutdown error in its initial default-exposure run. Its minimum-
exposure and repeat runs also passed as detailed below. Startup/first-frame and
whole-cycle shutdown results remain separately recorded.

## Frozen first candidates

Outputs reside under `tmp/bringup/capture-phy-fast-v35-{early,streaming}-20261017`.

| Variant | Receiver bytes | Receiver SHA-256 | Sector SHA-256 |
|---|---:|---|---|
| Early | 12996 | `4c79db5322d18674f2e85555465858ba300463bf407ffd5976b862cd650c42cf` | `de30f24ffbc992a485f5e250c8fc25bc214d309082eb1a83b82e5c845daf6cdb` |
| STREAMING | 13044 | `329da55a2d3f438c428648bec310da0be27971f04a4434eaabf46e3747a602bb` | `6a4e45dd95c1b226499fe980065736254d812dbdf62e6e87c9abeecca7188764` |

Both receiver failure parks are `0x343014a2`. Failure first disables interrupts,
records the failure and resets only DCMIPP to stop DMA, retaining CSI history.
The autonomous PE1 recovery guard is inherited; a host must separately review and
allowlist each new complete prefix before using an early-recovery maintenance
helper. This builder does not update any maintenance allowlist.

## Diagnostic reads

Before reading high SRAM, the owner must verify the fixed `RCC_MEMENR` register
at `0x5602824c` has bits 0–3 all set. Then the fixed FAST buffer is
`0x343f8000`, exactly **544 words / 2176 bytes**. A manifest is not authorization
to read an arbitrary address. `inspect.py` only decodes an already-read binary;
it performs no hardware access, checks the exact layout and receiver file hash,
and ignores stale records beyond the current count.

The first 32 words are the header. Words 0/8 are `FPY1` magic / schema1; 1 is the
latest event (40 on successful completion), 2 is record count, 3 overflow,
4/5 accumulated observed SR0/SR1, 6 mode (early0/STREAMING1), and 7 the number of
snapshots that skipped unsafe CSI reads.

| Header words | Meaning |
|---|---|
| 9 / 10 | START ACK / STREAMING observation timestamps |
| 11 / 12 | Data-enable begin / end timestamps (no-op boundary in early control) |
| 13 / 14 / 15 | PA0 / frame count / VSYNC count before data enable |
| 16–19 | Failure phase, result, PRIMASK, quiescence proof |
| 20 / 21 | Qualified data-STOP SR1 / timestamp |
| 22 / 23 / 24 | Arm timestamp / STROBE ordinal / PA0 before arm |
| 25–29 | Failure RCC enable state, DCMIPP P0FCTCR/CMSR2, reset before/after |
| 30 / 31 | STROBE ordinal at first VSYNC / first frame complete |

Up to 32 records follow, each 16 words:
`event, cycles, tick, SR0, SR1, IER0, IER1, PRCR, PCR, CR, LMCFGR,
RCC_APB5RSTR, PA0, frame_count, VSYNC_count, STROBE_ordinal`.
CSI registers are read only if CSI reset is released and its peripheral and IC18
clocks are enabled. `PRCR=0xffffffff` explicitly denotes skipped CSI reads.

Key events are 405/406 (before/after PEN), 425 (START ACK), 426 (STREAMING),
437/438 (before/after data enable), 409 (STOP qualified), 441/422 (before/after
arm), 429/430 (VSYNC/frame), 420 (raw CSI IRQ before HAL), 435 (before pipe stop),
439 (after pipe stop, before sensor stop), 436 (after sensor stop), and 440 (final).

For first-image qualification, require zero diagnostic overflow, the first
VSYNC and frame associated with STROBE ordinal1, the external waveform's matching
first exposure, and the original byte-count, canary, format and image-content
checks. One returned frame alone does not prove it was the first exposure.

Run the isolated offline checks with `python firmware/capture-timing/fast_phy/test_fast_phy.py`.

## Optional v36 sensor-stop isolation — measured whole-cycle passes

`--shutdown-data-off` adds a step only after successful `HAL_DCMIPP_CSI_PIPE_Stop`
and FAST snapshot439. The default remains off; a complete default-off rebuild
matches the original v35 STREAMING sector byte-for-byte.

The initial 1428-line v36 run completed with **zero raw error records and zero
HAL camera errors across startup, first-frame capture and sensor STOP**. It
reached stage40 with one complete frame, first STROBE ordinal1, valid native-frame
integrity, and a visually recognizable detailed workshop image. START completed
18.89744 ms after reset release; first STROBE occurred at 24.19728 ms, a
5299.84 µs sensor-relative interval. Frame completion was at 46.060 ms.

The current-run shutdown proof reached stage4/result0, with valid clock/reset
guards and all four idle conditions satisfied. Recorded values were SR0=`0`,
P0FCTCR=`0x04`, CMSR1=`0x03`, P0FSCR=`0x2b`, PRCR=`0x02`, and PCR=`0x0f`→`0x03`.
Its timestamps matched FAST439→442→443→436. Evidence originates from
`tmp/bringup/phy-fast-v36-shutdown-install-01/{cold,fast}`; consolidated records
are in the [fast-PHY evidence](../evidence/2026-10-17-fast-phy/README.md).

Two subsequent 5-line v36 cold boots also completed with zero errors through
sensor STOP, first STROBE ordinal 1, complete valid native frames, applied coarse
exposure of 5 lines, and correlated current-run shutdown proofs. START-to-first-STROBE was
5361.60 and 5358.88 µs. The measured arm-to-first-VSYNC margin was **70.88 and
51.36 µs**, respectively; **51.36–70.88 µs is the observed v36 minimum-exposure
range**, smaller than the 95.04 µs observed in the earlier v35 test. These are
bench observations, not a production worst-case guarantee. The first short run
configured the receiver in 3562.6525 nominal microseconds after START completion,
inside the unchanged 4.5 ms configuration budget. Its dark image still showed
the expected lamps/window scene without obvious corruption.

Restoring the default 1428-line v36 image also produced a clean capture:
START-to-STROBE 5300.80 µs, first STROBE 24.54224 ms after reset release, and frame
completion 46.40496 ms. The short repeat is recorded under
`tmp/bringup/phy-fast-v36-coarse5-cold-02`; the restore is under
`tmp/bringup/phy-fast-v36-default-restore-02`.

The final default-exposure cold boot also passed, with START-to-STROBE 5299.20 µs,
first STROBE 24.24112 ms after reset release and frame completion 46.10384 ms.
The detailed scene was visually checked again. Across **all five v36 cold starts
(three at 1428 lines and two at 5 lines)**, raw error records and HAL errors were
zero through sensor STOP; every run preserved the first physical exposure and
passed complete-frame integrity and current-run shutdown-proof checks. Default
START-to-STROBE ranged from 5299.20 to 5300.80 µs; the two minimum-exposure values
were 5358.88 and 5361.60 µs.

The final installed default image also passed the autonomous recovery check:
PE1 low selected state 3/reason 1 after 40,004 cycles and parked at `0x3418078c`;
the exact prefix matched and CCR=`0x201` confirmed both caches disabled. Releasing
the request selected PE1 high/state 2 and completed the final normal capture.
After the JS110 helper exited successfully, its output bank remained at 3.3 V,
OUT0 HIGH (normal boot), and its original range setting 128 was preserved.
An independent 3.02-second observation after release confirmed stable target 5 V,
main VDDIO and auxiliary 3.3 V rails, reset released, and steady markers. The board
was left powered with the verified v36 default image and normal boot selected.
The [archived qualification and final-state evidence](../evidence/2026-10-17-fast-phy/README.md)
includes the final normal run, recovery-park proof, normal-branch proof and
post-release rail verification.

The opt-in step verifies that CSI and DCMIPP peripheral clocks, IC18/IC17 kernel
clocks, and released resets permit safe reads. It then requires all four fields
below to be clear before modifying the PHY:

| Register / field | Mask | Required condition |
|---|---:|---|
| CSI SR0 / VC0STATEF | `0x00020000` | VC0 idle |
| DCMIPP P0FCTCR / CPTREQ | `0x00000008` | No capture requested |
| DCMIPP CMSR1 / P0CPTACT | `0x00008000` | No active frame capture |
| DCMIPP P0FSCR / PIPEN | `0x80000000` | Pipe disabled |

It also requires PEN set and PCR=`0x0f`. It records snapshot442, clears only
PCR.DL0EN/DL1EN (`0x0c`), executes a barrier, and verifies PCR=`0x03`, then records
snapshot443. Clock, power, PEN and error enables/flags are left unchanged by this
step. The existing sensor STOP and snapshot436 follow. A failed prerequisite
enters the existing quiesced failure path, phase `0xa5`.

Proof is a separate **16-word / 64-byte** region at **`0x343f8900`**, beyond the
existing FAST buffer's end at `0x343f8880`. Its schema is:

| Words | Meaning |
|---|---|
| 0 / 1 / 2 | `FSD1` magic / schema1 / stage |
| 3 / 4 / 5 | RCC APB5ENR / DIVENR / APB5RSTR before peripheral reads |
| 6 / 7 / 8 / 9 | CSI SR0 / DCMIPP P0FCTCR / CMSR1 / P0FSCR |
| 10 / 11 / 12 | PRCR / PCR before / PCR after data disable |
| 13 / 14 / 15 | Disable begin cycle / end cycle / signed result |

Stages are 1 initialized, 2 safe peripheral access, 3 idle proof accepted,
4 disable complete. Results `-1..-4` mean unsafe clocks/reset, active VC/pipe,
unexpected PEN/PCR, or unexpected post-disable PCR respectively.

Initialization happens at the post-capture call, not during startup. An earlier
failure may therefore leave an old proof in SRAM. Do not treat a standalone
stage4 record as proof of current completion: require current-image/TRACE
validation and the matching FAST439→442→443→436 sequence with the disable
timestamps inside its 442/443 boundaries. `inspect.py --shutdown-input <file>`
correlates the two already-read buffers; it performs no hardware reads.

Frozen outputs are `tmp/bringup/capture-phy-fast-v36-shutdown-20261017` and
`capture-phy-fast-v36-shutdown-coarse5-20261017`. Both use the same 13392-byte
receiver; only manual exposure differs between prefixes. Hardware qualification
is recorded separately by the bench owner.
