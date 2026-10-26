# Early SD clock transition — October 26, 2026

Moving the 100 kHz → 12.5 MHz transition to after CMD9 and before CMD7
passed **three alternating A/B pairs (six capture/save/readback runs)**.
Every saved 1,909,600-byte image matched its original camera RAM exactly,
and independent PNG decoding matched the retrieved RAW samples. The observed
targeted sequence improvement is approximately **2.4 ms**, after accounting
for frame-validation work that moved between measured phases.

This is a **RAM-only experiment**. The installed startup/no-tail Standby
firmware was not replaced, the card was not erased, and no cold-power,
Standby, total-energy or new wire-level qualification is claimed.

## Sequence and safeguards

The control selects the card with CMD7, checks readiness, changes the clock,
and checks readiness again. The candidate first validates CSD `TRAN_SPEED`,
changes the clock while the card is in STBY and both host state machines are
idle, then selects with CMD7 and checks readiness. It removes the now
redundant second CMD13; it does not issue a readiness command while the card
is still in STBY.

The card reports a 25 MHz CSD limit. The candidate's `ECK1` record confirms
the CMD9 → clock switch → CMD7 order, one-bit `CLKCR` changing from
`0x302EE` to `0x30006`, and `DTIMER` changing from 200,000 to 25,000,000
clocks to retain a two-second timeout. Four-bit negotiation happens afterward.
Both profiles retain 100 kHz identification, falling-edge launch, four-bit
12.5 MHz transfers, GPIO speed 3 and inherited compensation. The sensor,
exposure, RAW slot format, LINE publication, asynchronous STOP and cycle
logger are unchanged. Tail waiting, receive-IDMA, DMA-WFI and electrical
experiments remain disabled.

The explicit build option is `--sd-early-run-clock`. Its builder, compiler
and host checks admit only the reviewed startup/no-tail 12.5 MHz RAM scene
profile. Historical profiles with the option disabled remain unchanged;
the rebuilt complete control executable is byte-identical to the prior
reviewed control.

## Measured timing

All intervals below are software timestamps at the qualified nominal
400 MHz DWT clock. “Post-CSD” starts at `SD_IDENTIFY_REGS_DONE` and ends at
`SD_WIDTH_BEGIN`; it includes selection, the divider transition and nearby
software work. It is not an isolated wire-transfer or card-programming time.

| Run | Slot | Post-CSD span | Nested frame validation | Post-CSD minus that validation | ACMD41 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control 1 | 31 | 2.486230 ms | 0 ms | 2.486230 ms | 193.848373 ms |
| Early 1 | 32 | 0.109878 ms | 0 ms | 0.109878 ms | 12.089318 ms |
| Control 2 | 33 | 2.949925 ms | 0.397470 ms | 2.552455 ms | 12.088850 ms |
| Early 2 | 34 | 0.119113 ms | 0 ms | 0.119113 ms | 15.369233 ms |
| Control 3 | 35 | 2.952718 ms | 0.402185 ms | 2.550533 ms | 12.088753 ms |
| Early 3 | 36 | 0.109878 ms | 0 ms | 0.109878 ms | 12.089270 ms |

| Comparison of three-run medians | Control | Early | Difference |
| --- | ---: | ---: | ---: |
| Raw post-CSD span | 2.949925 ms | 0.109878 ms | 2.840048 ms |
| Post-CSD span excluding fully nested frame validation | 2.550533 ms | 0.109878 ms | **2.440655 ms** |
| Wider CSD-ready → SD initialization complete | 5.396870 ms | 1.056620 ms | 4.340250 ms |

The second row subtracts only the measured `FRAME_CHECK_BEGIN` →
`FRAME_VALIDATED` interval when it lies completely inside the target window.
It does not model every interrupt or callback cost. The approximately
0.4 ms validation work still runs in the candidate; it moved later. Thus the
raw 2.84 ms window reduction is not all eliminated work, and even the adjusted
2.44 ms is an observed sequence improvement rather than a fixed pure-clock
saving. The wider interval also includes variable SCR/readiness behavior.

ACMD41 varies substantially, particularly on the first control. Slot scanning
also grows from slot 31 to slot 36, while card write/readiness latency changes.
These observations do not support attributing the whole-cycle difference or
an energy reduction to this change. The matched software boundaries and
callback adjustment support the narrower approximately 2.4 ms conclusion.

Exact per-run timings, counters, ordering, adjustment details and source
bindings are in [summary.json](summary.json). Each run under `runs/` retains
its capture proof, full-image comparison report, final idle READ proof,
recovery park, decoded trace and original 1 KiB trace. Candidate runs also
retain the original 64-byte ECK1 record. Root visually inspected control 1,
early 1 and early 3 as recognizable mesh/chair scenes; every run passed the
automated source-byte and PNG checks. Image bytes and PNGs remain private.

## Identities, instruments and final state

| Profile | Executable SHA-256 | Size |
| --- | --- | ---: |
| Control | `2829eae05cd96f5f7bfe36ac852d6904341c513aba51639a0e800bb171b735f5` | 29,660 bytes |
| Early | `4e69833f4e4813c659329226574ff68e6b7accf6da1af6cbb19726bfb3d450f5` | 29,976 bytes |

The archive includes both exact executables, manifests and relevant frozen
sources. [Disabled-profile identity checks](driver-disabled-identity.json)
also retain six matching ARM-object profile comparisons. All 160 RAW capture
tests passed during integration; separate actual-driver tests cover the early
clock/CSD/timeout logic.

The Logic API returned no devices even after the user reconnected the
analyzer and Windows reported it present. No waveform capture was created;
[analyzer-state.json](analyzer-state.json) preserves that limitation. The
existing probe wiring and 27-ohm midpoint CLK resistor were unchanged.

The target was left powered, awake and idle at the candidate's final RAM
READ terminal after slot 36 verification. JS110 stopped cleanly at
16:32:33.746227 UTC, restored range 128 and left target power on. Its last
4.875290 V / 83.794713 mA observation is awake READ-helper current, not Standby
or capture-cycle energy. See [final state](final-state.json),
[JS response](js-response.json) and the live [bench checkpoint](../../../../AGENTS.md).

## Replay

Run `python verify.py` here for offline hash, timestamp, ECK1, ordering,
summary-arithmetic and retained-report checks. It verifies all 94 frozen
files without hardware or private image access. It does not regenerate image
equality from hashes. `archive.py` performed that comparison against the
private camera, SD and slot bytes before freezing their reports and hashes;
it refuses to overwrite an existing `FREEZE.json`.

Private source material remains under
`tmp/bringup/sd-early-clock-20261026/`, including all image bytes, helper logs
and the complete JS session. The frozen source hashes bind those inputs
without publishing the photographs.
