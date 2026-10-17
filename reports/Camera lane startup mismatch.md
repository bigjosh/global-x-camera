# Receiver readiness without delaying exposure

Research and bench evidence, October 17, 2026: NUCLEO-N657X0-Q, CAM-6G3-073CLR, VD56G3 revision `0x3110`.

## Current result: use observed Stop to release lane 1

**The preferred v41 sequence raises minimum-exposure receiver margin to 546.08–548.16 µs**, versus the earlier v36 minimum of 51.36 µs, without postponing sensor START or exposure. Two minimum-exposure cold starts returned the first physical image with complete native-frame integrity, zero sampled raw CSI errors through shutdown, and current-run readiness/shutdown proofs. START-return to first STROBE was 5360.64–5361.92 µs. These are externally correlated firmware markers, with the measurement limits below. See the [receiver-readiness evidence](../firmware/capture-timing/evidence/2026-10-17-receiver-ready/README.md) and [implementation](../firmware/capture-timing/ready_phy/README.md).

The sequence uses the PHY's receive/wait-for-Stop control rather than waiting for I²C polling to notice STREAMING:

1. Preserve early sensor START and overlap the receiver-code load with sensor startup.
2. Enable clock and data modules early. Set PMCR to `3` before releasing PHY digital reset, then immediately write `2`: lane 0 is released, while lane 1 remains in ForceRx/wait-for-Stop.
3. Require both enabled data lanes to report Stop continuously for 40000 nominal 400 MHz cycles, approximately 100 µs. Recheck Stop, clear only the ForceRx bits, verify the readback and arm capture. No error masks or clears are added.
4. Perform START-ACK and STREAMING verification after arming. Preserve the v36 idle-checked data shutdown before sensor STOP.

In the first v41 trial, both data Stop flags were initially low after PEN. Both were observed high at START +4931.10 µs, ForceRx release was observed at +5053.22 µs, and capture armed approximately 292 µs before exposure. Clock-active was present before lane 1 release. **Clock-active is corroborating recorded evidence; this firmware does not implement an ACTCLF wait or gate.** Earlier clock-only/PCR3 traces did not expose ACTCLF before data enable, so polling it there would risk deadlock.

This gives a measured state-based boundary: enable the modules in a controlled state, then release lane 1 after observed Stop and the chosen guard. It does **not** establish a datasheet-guaranteed earliest time across temperature, voltage or sensor revisions. STM32 documents ForceRx and StopState, but does not specify whether its Stop indication already incorporates D-PHY initialization timing. The 100 µs software guard is an empirical choice, not a newly inferred STM32 requirement. [Primary-source comparison](../firmware/capture-timing/ready_phy/readiness-sources.md).

A timing discriminator deliberately delayed PHY digital-reset release. Measured PEN moved from START +3718.90–3726.45 µs to +3934.10 µs, a 208–215 µs shift including the slightly larger program load. The first both-Stop observation stayed near START +4931.10–4935.30 µs, moving only 0.86–4.20 µs. First-frame margin remained 548.00 µs and the image/error checks passed. This supports a sensor/START-relative readiness event rather than a fixed receiver-initialization delay. The shifted build is a diagnostic; the preferred v41 image has no added delay.

The preferred sequence completed four cold-start captures: two at minimum exposure and two at the default exposure, all retaining the first physical image with complete frame integrity and no sampled raw CSI errors. At default exposure, START return to first STROBE was 5298.24–5303.36 µs; reset release to first STROBE was 23.804–23.819 ms, and reset release to complete first frame was 45.667–45.682 ms. The default image was visually checked against the illuminated bench scene. These are bench observations with the [existing marker measurement limits](../firmware/capture-timing/exposure-measurement.md).

The final default v41 sector remains installed, SHA-256 `c92ee95920009b188aef53645fce8e9bb6cb8bd34d78cf789d252037be16af2f`. Its exact PE1-low early recovery park passed live code, CPU/cache and XSPI checks, followed by another clean PE1-high cold capture. The JS110 was released with 3300 mV GPIO supply, OUT0 HIGH and automatic current range restored. A separate 3.02-second capture confirmed powered rails and stable reset/markers after release. No jumper or probe changes were required.

## Why the lane distinction matters

| Experiment | Minimum-exposure result |
| --- | --- |
| Original v36 ACK+STREAMING, then 100 µs Stop dwell | First frame, no recorded errors; prior smallest margin 51.36 µs |
| v38 ACK gate, no extra Stop dwell; defer STREAMING read | First frame, no recorded errors; 265.76–279.04 µs margin |
| v39 early control, release both ForceRx bits immediately | First frame but startup lane 1 ECTRL remains |
| v39 hold both ForceRx bits through 100 µs Stop dwell | No reported PHY error, but no VSYNC/frame during 2 seconds of continuing sensor exposures |
| v41 hold only lane 1 through 100 µs Stop dwell | First frame, no recorded errors; 546.08–548.16 µs margin |
| v42 hold both lanes, release on first observed both-Stop | First frame, no recorded errors; 651.68 µs margin; zero extra dwell remains an experimental discriminator |

The failed both-lane hold crossed the clock lane's Stop-to-non-Stop transition while ForceRx was still asserted. Clock-active never appeared afterward. Releasing both sooner, while clock Stop was still high, worked. Holding only lane 1 also worked, with clock-active present before releasing it. This supports a missed clock-start transition when lane 0 is held too long; it does not establish an undocumented internal mapping between lane 0 ForceRx and the clock receiver.

We prefer v41's larger margin with the 100 µs guard over adopting the fastest single trial. Its successful state history is more useful than choosing a fixed delay such as START +5 ms. First-frame association and raw error history remain mandatory: the failed v39 trial demonstrates that quiet error flags and a completed Stop proof alone do not establish successful reception.

## Previous v36 checkpoint

**The startup error is avoided without measurably delaying exposure. The matching shutdown sequence also avoids the later stop error.** The v35/v36 integration keeps the optimized free-running sensor start, enables the clock receiver early, and enables the data receivers after START acknowledgement and STREAMING. v36 additionally disables the data receivers after capture and pipe shutdown, before stopping the sensor. Raw CSI history and the existing interrupt enables are retained; success does not depend on clearing or masking an error. ([Current evidence](../firmware/capture-timing/evidence/2026-10-17-fast-phy/README.md), [implementation and diagnostics](../firmware/capture-timing/fast_phy/README.md))

## Previous v36 sequence and timing

1. Start the sensor as early as before and load the receiver program during sensor startup.
2. Configure the receiver with `PCR=0x03`: clock receiver enabled, both data receivers disabled, then release PHY digital reset.
3. After sensor START acknowledgement and STREAMING, set only `DL0EN/DL1EN`, making `PCR=0x0F`.
4. Observe data Stop continuously for 100 nominal microseconds, then arm the first-frame snapshot. Exposure is already running independently; this observation interval does not postpone it.
5. After the first frame, stop the pipe and verify that the virtual channel is idle, no capture is requested or active, and the pipe is disabled. Clear only the data-enable bits (`PCR=0x03`), then issue sensor STOP.

The matched long-exposure control and treatment measured **5302.56 and 5303.20 µs** from sensor START-command return to first STROBE. At the documented CCA minimum of five coarse lines, they measured **5361.28 and 5361.44 µs**. Differences of **0.64 and 0.16 µs** do not show a meaningful sequencing penalty in these trials. Reset-to-exposure is reported separately because ROM/startup variation is larger.

The final v36 image passed **five cold starts**, three at default exposure and two at minimum exposure, with zero recorded CSI errors through shutdown:

| Exposure setting | Runs | START return → first STROBE | Reset release → first STROBE | Reset release → complete first frame |
| --- | ---: | ---: | ---: | ---: |
| 1428 coarse lines, about 11 ms | 3 | 5299.20–5300.80 µs | 24.197–24.542 ms | 46.060–46.405 ms |
| 5 coarse lines, about 46 µs | 2 | 5358.88–5361.60 µs | 23.755–24.257 ms | 34.634–35.136 ms |

These are externally correlated firmware/STROBE markers, with the latency limits described in the [measurement method](../firmware/capture-timing/exposure-measurement.md); they are not direct oscilloscope measurements of sensor pixels or MIPI packet edges.

The short-exposure test matters: delayed reception must still catch the **first physical exposure**, not silently discard it and accept a later frame. v35 passed at 5, 21, 40 and 1428 coarse lines. At five lines, the measured pulse was **45.92 µs**, and receiver arming preceded first VSYNC by **95.04 µs**. The raw buffer contained the complete native image with intact byte count/checksum/canaries, and first VSYNC/frame records both referred to STROBE ordinal 1. A short frame was visibly dark but contained the expected illuminated scene features. The minimum is specified for the CCA sensor revision in [UM2602 Rev8, Table38](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf#page=38); the generic driver's older 21-line limit is not the CCA minimum.

The v36 minimum-exposure cold starts returned the first image with arm-marker-to-VSYNC-marker intervals of **51.36–70.88 µs**. The extra shutdown diagnostic code is loaded with the receiver before entry, although the shutdown function itself executes only after capture. Its receiver-configuration work still finishes within the existing 4.5 ms budget.

This is a successful bench sequence on one board and sensor revision. The 100 µs observation interval is an empirical guard, not a newly inferred D-PHY requirement. The **51.36 µs smallest measured margin** still needs qualification across production clock, temperature and supply corners. Keep additional work and sensor transactions out of that interval. The guarded firmware preserves the qualified PE1 recovery entry before sensor and receiver work.

## Independent lane enables make the sequence possible

The STM32 exposes separate clock/data receiver controls. The earlier v33 experiments established this ordering using explicit follower triggers; v35/v36 transfer it to the faster free-running path and arm during exposure or its pre-readout interval. The existing error masks and handler remain unchanged. ([RM0486 §§40.9.2, 40.10.1](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), [earlier v33 implementation](../firmware/capture-timing/late_phy/README.md#v33-clock-lane-early-data-lanes-after-streaming))

| Control or observation | What it establishes |
| --- | --- |
| `CSI_CR.CSIEN` | Host processing enable; not PHY reset |
| `CSI_PRCR.PEN=0` | PHY digital section held in reset |
| `CSI_PCR.CLEN` | Independent clock receiver enable |
| `CSI_PCR.DL0EN/DL1EN` | Independent data-module enable/shutdown |
| Sensor STREAMING | Firmware state; no explicit LP-11 guarantee |
| Receiver Stop flags | Presently recognized states, not transition history |

Clock-active status remains clear in the clock-only snapshots and first appears after data enable. **We observed successful sequencing, not an earlier measured clock lock.** Sensor readiness likewise does not establish an electrical state independently of the receiver observations. ([Sensor command states](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf), [raw v33 evidence](../firmware/capture-timing/evidence/2026-10-17-v33-delayed-data/README.md))

## Comparisons separate startup from image transfer

The earlier v30–v33 experiments preserve native geometry, gain and exposure, using documented I²C follower operation. The newer v35/v36 experiments use the optimized free-running path and matched exposure settings.

| Experiment | Result |
| --- | --- |
| [v30d: whole receiver early, continuous clock](../firmware/capture-timing/evidence/2026-10-17-v30d-phy-sequence/README.md) | Startup lane-1 error; valid first image |
| v30d: whole receiver late | No startup error, but no frame or clock-active indication |
| [v31: noncontinuous clock](../firmware/capture-timing/evidence/2026-10-17-v31-phy-sequence/README.md) | Same contrast: early works with warning; late loses first image |
| [v32: late receiver, second trigger](../firmware/capture-timing/evidence/2026-10-17-v32-second-trigger/README.md) | First image lost; second received after clock/data Stop, without receiver reset or rearming |
| [v33: clock early, data late](../firmware/capture-timing/evidence/2026-10-17-v33-delayed-data/README.md) | Three first-image successes; no recorded startup/transfer errors |
| v35: same lane ordering, optimized free-running startup | First image retained at default and minimum exposures; startup error absent, no measurable exposure delay; sensor-stop error remains |
| v36: v35 plus idle-checked data-receiver shutdown before sensor STOP | First image retained; zero recorded errors through shutdown |

The older v21 trace also places ECTRL before FSYNC, so the exposure trigger is unnecessary for the startup error. v35's finer snapshots isolate its remaining ECTRL to sensor STOP, after the host pipe has stopped. v36 avoids that receiver observation by shutting down the idle data modules first; this does not establish electrical compliance of the sensor's shutdown transition. The original ST-based smoke application already saw the same error class. ([v21 timing](../firmware/capture-timing/evidence/2026-10-17-v17-through-v24/captures/v21-follower-cold/timing.json), [original comparison](../firmware/capture-timing/csi-startup-errors.md), [earlier v33 phase checks](../firmware/capture-timing/evidence/2026-10-17-v33-delayed-data/extra/analysis/phy-v33-phase-verification.json))

## The electrical mismatch remains an inference

The sensor specifies camera pins low in reset, but does not document their complete transition into qualified D-PHY Stop or expose an explicit force-LP-11 control. Normal high-speed entry, in receiver `(P,N)` order, is `11 → 01 → 00 → HS-0 → synchronization → data`. Observing only part of initialization or an unexpected intermediate state could explain ECTRL. The comparisons support that explanation, but **do not establish sensor noncompliance or a particular invalid edge**. Physical pair polarity must be verified before interpreting `01` versus `10`. ([VD56G3 datasheet](https://www.st.com/resource/en/datasheet/vd56g3.pdf), [UM2602](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf), [NXP D-PHY explanation](https://www.nxp.com/docs/en/application-note/AN13573.pdf))

The STM32 names D-PHY v1.2; the complete normative specification is member-only. No explicit sensor PHY version was found. Public manufacturer material supports diagnosis rather than a compliance conclusion. These bench trials do not qualify every exposure, board, temperature or power sequence. ([STM32 datasheet](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), [MIPI access policy](https://www.mipi.org/specifications/d-phy))

## Probing can explain the edge but is optional for integration

The LP8 can observe nominal 0/1.2 V LP states using its **1.2 V family, approximately 0.6 V threshold**, rather than our existing 3.3 V setting. With USB 3 and analog disabled it supports four digital channels at 500 MS/s or eight at 100 MS/s. Each input adds **10 pF**, however, and genuine high-speed signaling also reads as `00`. A digital trace cannot establish LP-only behavior. Attachment requires verified access/polarity and an unprobed/attached comparison. No MIPI probes were added. ([Saleae specifications](https://downloads.saleae.com/specs/logic_pro_8_data_sheet.pdf), [thresholds](https://www.saleae.com/support/specifications-hardware/electrical-characteristics/supported-voltages))

The DS1054Z can inspect LP ramps/skew, but its 50 MHz bandwidth and passive probes cannot qualify the 804 Mb/s eye. The AD3 was unnecessary for these software experiments. ([Rigol specifications](https://www.rigol.com/dam/global/downloads/brochures/en/data-sheet/oscilloscopes/DS1000Z_DataSheet_EN.pdf))

The earlier v30 diagnostic access stall was fixed with reset/clock guards, and that investigation ended by restoring v25. That historical restoration is superseded by the guarded v36 integration above. At that previous checkpoint, the default-exposure v36 sector was installed (`40743205503bdb465d0549b7764f1590c48b7aaac621bf096aa4b9618957c1bd`). Its PE1-low recovery park was checked against live code and CPU/cache state, then PE1-high normal boot captured another clean first frame. The JS110 session was released with its original 3300 mV/HIGH recovery output and auto range restored; subsequent measurements confirmed the target rails remained powered. No boot-jumper or probe changes were needed. See the [current evidence record](../firmware/capture-timing/evidence/2026-10-17-fast-phy/README.md). ([Earlier recovery evidence](../firmware/capture-timing/evidence/2026-10-17-v30d-phy-sequence/README.md#recovery-evidence), [historical v25 restoration](../firmware/capture-timing/evidence/2026-10-17-phy-sequence-final-state/README.md))
