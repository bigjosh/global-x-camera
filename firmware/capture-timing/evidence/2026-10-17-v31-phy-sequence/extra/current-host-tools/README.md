# Native follower / physical receiver-release experiment

This isolated builder creates a matched pair from the frozen native RAW10 v25
image. It performs no hardware operations and changes no shared baseline source.
The question is whether the existing lane-1 ECTRL indication is caused by the
receiver observing the sensor's START transition. This is a sequencing diagnostic,
not a proposed latency-optimized production image.

## Matched sequence

Both images preserve the v25 resolution, RAW10 transport and padded16 RAM format,
gain, exposure, clocks, continuous MIPI clock, calibration, memory enable sequence,
read-only NOR loader, debug opening and post-frame checks. They change the sensor
to documented I2C follower mode (`VT_CTRL=2`, `FSYNC_IN_DELAY=0`) and verify the
default continuous-clock register remains `DPHYTX_CTRL=0x1C`.

The prefix asserts only `RCC.APB5RSTSR.CSIRSTS`, using RCC registers without
accessing CSI. Readback must show the CSI
reset bit and no changes to other reset bits. CSI remains in reset while the
prefix configures the sensor, issues START, and loads/checksums the receiver.

- **Early control:** release/configure the receiver after the load, before polling
  START acknowledgement and the sensor's STREAMING state.
- **Late treatment:** first observe START acknowledgement and STREAMING; only
  then release/configure the receiver.

The same checked receiver configuration follows in both variants. Before lane
merger writes, the diagnostic requires `PEN=0`, `CSIEN=0` and `ACTCLF=0`. It records
before and after the actual `PEN=1` write. Both data-lane STOP flags must then be
observed continuously for 100 nominal microseconds within a bounded 50 ms wait.
This is an observation guard, not a claim that this interval is the PHY's specified
T_INIT. Clock-lane STOP is not required with continuous clock.

After the guard, the receiver arms one snapshot, verifies that no frame/VSYNC has
occurred and PA0 is low, and sends I2C FSYNC (`0x0202=2`). It waits for frame
completion before checking FSYNC acknowledgement. Frame wait is bounded at 2 s;
START/FSYNC command waits are bounded at 500 ms. The successful path preserves
the native byte-count/canary/content checks, applied-clock diagnostics and sensor
stop. Snapshot overflow is a terminal failure, including at the final success
checkpoint.

No additional flag clearing, error masking or error-code suppression is used.
The inherited HAL still acknowledges and masks errors through its existing IRQ
handler; a raw snapshot is taken **before** that handler runs. Therefore callback
count alone is not sufficient: inspect accumulated flags and raw snapshots too.

## Diagnostic layout

`0x343F8000`, schema 1, contains 1,568 words: a 32-word header and at most 128
12-word records. It ends at `0x343F9880`, outside the native frame, code, stack and
other diagnostic regions.

Each record is `event_id, DWT_cycles, HAL_tick, SR0, SR1, IER0, IER1, PRCR, PCR,
CR, LMCFGR, RCC_APB5RSTR`. Recording never clears a peripheral flag. CSI reads are
allowed only when its RCC reset is released and both its peripheral clock and
IC18 are enabled. Otherwise `PRCR=0xFFFFFFFF` explicitly marks an unread record:
the other CSI fields are zero placeholders and must not be interpreted as
measurements. RCC reset remains a live read. Header words:

| Word | Meaning |
|---|---|
| 0 | `0x4C505231` (`LPR1`) |
| 1 | Latest snapshot ID; 40 only after successful completion |
| 2 / 3 | Record count / overflow count |
| 4 / 5 | OR of all observed SR0 / SR1 |
| 6 | Mode: 0 early, 1 late |
| 7 | Number of snapshots that deliberately skipped CSI access |
| 8–15 | Prefix sensor words24–31: initial PHY state, reset proof and follower readbacks |
| 16 / 17 | Failure phase / signed result encoded as uint32 |
| 18 / 19 | Failure PRIMASK / `0x51554945` (`QUIE`) quiescence proof |
| 20 / 21 | Qualified data-lane STOP SR1 / DWT timestamp |
| 22 | STREAMING observation timestamp |
| 23 / 24 | FSYNC write begin/end timestamps |
| 25–27 | Failure APB5 enable state, pre-reset P0FCTCR and CMSR2 |
| 28 / 29 | Failure APB5 reset state before/after DCMIPP-only reset |

Key snapshot IDs: 299 receiver entry; 301/302 before/after CSI reset release;
303 before merger; 304 before CSIEN; 305/306 before/after PEN; 307 sensor
STREAMING; 308 changed SR1 during STOP polling; 309 qualified STOP; 310 armed;
311/312 FSYNC begin/end; 313 frame complete; 314 FSYNC acknowledged; 315 before
stop; 316 after stop; 317 final checkpoint; 320 raw CSI IRQ entry.

## Failure and recovery boundary

Receiver failures first disable interrupts, then record the original TRACE failure stage (`0x80000000|phase`),
result, raw history and pre-reset DMA status. They then assert **only DCMIPP
reset**, without resetting CSI or erasing the collected history, disable
interrupts, and enter the exported `late_failure_idle` single-instruction loop.
`RCC.APB5RSTR` is at `0x5602823C`; DCMIPP reset is mask `0x4`. The compiled image
does not program or erase NOR. The build manifest includes the exact loop
address/bytes, image hash and recovery schema so the separate host helper can
accept only reviewed terminal states after matching the full live receiver.

This guard does not accept inherited HardFault/assert states or prefix failures.
New prefix sensor failures return stage1 result17 before its NOR read and before
DMA. Those remain debug-accessible but require a separately reviewed prefix
recovery procedure; do not pass them through the receiver's recovery guard.

## Frozen offline candidates, October 17

Both builds compiled successfully. All 19 receiver and all 5 prefix source files
are byte-identical between the pair; only the receiver mode compile definition
differs. Prefix disassembly contains no FP instructions or BKPT. The builder
checks boot vectors, image sizes, CRC, preserved NOR bytes outside payloads, and
the exact terminal loop opcode. Hardware results are recorded separately.

| Variant | Build directory under `tmp/bringup` | Receiver bytes | Receiver SHA-256 |
|---|---|---:|---|
| Early | `capture-phy-early-v30d-guarded-20261017` | 13,020 | `4ddd5a6c5167ebba4064b92a00d54adbacd7e08cdf3695d2d2dc8b81357b9af6` |
| Late | `capture-phy-late-v30d-guarded-20261017` | 13,032 | `5882d058f46ec11211cfe39dc1d10319a7eab9ffcd4e6ab2117074b2feefcf22` |

Both packaged prefixes are 5,312 bytes. Both failure loops are at `0x3430146A`
with bytes `FE E7`. Early sector SHA-256:
`0194db3a0cbe1cdaf85926ef8ce729ca90b415d0030f620d42dd6aa3f99e1a49`.
Late sector SHA-256:
`f6b5eafded82193c2edfa1339cb65f44c75d0fcf59ee555101e712f394260793`.

### Superseded v30b/v30c diagnostic access

Do not program v30b or v30c. The early v30b physical trace reached exactly 24
marker transitions, ending at stage2 handoff event207. Its next operation was
`late_init` snapshot299, which attempted to read CSI while the prefix still held
CSI peripheral reset. The debugger then could not retrieve the core ID. This
localizes a likely APB access stall; it is not a result about sensor sequencing
or the D-PHY error. Root owns recovery and its measured evidence.

The exact pre-stall event order was
`200,208,209,300,220,100,101,102,103,104,105,106,107,12,15,108,109,24,25,203,204,205,206,207`.
v30c added an IRQ-race fix for failure proof but retained the unsafe access and
was not selected for hardware. v30d retains that failure-proof fix, avoids all
CSI reads under peripheral reset or before clock setup, removes prefix CSI
reads, and guards pre-reset DCMIPP diagnostic reads by clock/reset state too.

Source rationale is in the repository's
[sensor contract](../../../research_notes/Camera%20lane%20startup%20mismatch/sensor_contract.md),
[receiver protocol](../../../research_notes/Camera%20lane%20startup%20mismatch/receiver_protocol.md)
and [probing notes](../../../research_notes/Camera%20lane%20startup%20mismatch/probing.md).

## v31 noncontinuous-clock pair

The parent controller reported that v30d early received a valid image with the
usual startup ECTRL, while v30d late reached exposure but timed out waiting for
a frame. The late run observed both data STOP flags and no error, but never
observed ACTCLF. This motivates a separate noncontinuous-clock pair: the late
receiver may need a fresh clock-lane HS entry. These observations alone do not
prove that mechanism.

Build with the additional `--sensor-clock noncontinuous` option. The default
remains `continuous`. The only source changes from each corresponding v30d build
are a bounded `DPHYTX_CTRL 0x0956=0x0C` write before START, its expected readback,
and the receiver's expected copied sensor-status value. All other sources and
the terminal recovery schema are unchanged. The sensor write uses phase55 and
the existing prefix result17 failure path. No error flag is suppressed.

| Variant | Build directory under `tmp/bringup` | Receiver bytes | Receiver SHA-256 |
|---|---|---:|---|
| Early | `capture-phy-early-v31-noncontinuous-20261017` | 13,020 | `2d582f1c26ba7df95c00d5a7184d62fd41b6fbd15c61bbafdcb2362faf29d239` |
| Late | `capture-phy-late-v31-noncontinuous-20261017` | 13,032 | `9c6c93b7fd4ca8703318785c0903020811249b675ef25bb442eeead4d7ce1794` |

Both packaged prefixes are 5,344 bytes and both recovery loops remain at
`0x3430146A`, bytes `FE E7`. Early sector SHA-256:
`ebacc819564188004918929f5fe89f176603ad1179a2de48ee3ff6e374d8a961`.
Late sector SHA-256:
`2d25639052369b58211e30b55a685ef06a8af34181a4a74e735b152029b29566`.
Offline build, source-diff, vector, terminal-opcode and prefix no-CSI/no-FP/BKPT
checks passed; these are candidate identities, not hardware success claims.
