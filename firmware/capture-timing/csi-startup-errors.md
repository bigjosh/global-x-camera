# CSI startup errors and first-exposure qualification

Offline analysis, October 17, 2026. This note records the initial v3/v5 evidence and the controlled tests proposed from it; later experiments can supersede these hypotheses.

The [public-source review of October 17](../../reports/STM32%20camera%20startup%20error%20reports.md) found an exact `0x8000` ST forum report, relevant startup guidance from an ST employee, and independent acknowledgment of the duplicate E3 write. It found no documented cure or formal benign-startup exception for our exact board/module. The review separates those reports from our already-negative PHY/clock experiments and identifies raw-error history and clock activity during lane-merger setup as the next useful diagnostic checks.

## Retrospective check of the original ST-based smoke test

The October 15 RAM smoke test **already observed the same D-PHY control-error class**. Its original local `tmp/bringup/serial.log`, lines 41, 83, 125 and 167, records four completed captures with `Errors pipe=0 global=0 CSI=1 final=0 flags=0x00008000`. The reproduction run's debugger log agrees. This was also recorded in the [bring-up results](../bringup/README.md#observed-result--october-15-2026). These were our adapted capture application using the pinned ST demo middleware/HAL, not a hardware run of the untouched UVC application.

The [smoke-test line-error callback](../bringup/capture_app.c) counts the event and preserves the accumulated error code, but discards the lane argument and has no event timestamp. Thus the historical evidence establishes the same **error class**, not necessarily the same lane or exact startup subphase. The saved image was a fourth-frame snapshot after three continuous settling frames. `final=0` is the difference in callback counts across that final snapshot; it does not say that startup was error-free or certify CRC/ECC monitoring.

In the pinned HAL, both lane-control branches clear their hardware flag through `CSI_FCR1`, accumulate `HAL_DCMIPP_CSI_ERROR_DPHY_CTRL` (`0x8000`), then invoke the line callback. Clearing acknowledges the detected event; it does not perform a link reset or repair. The unmodified demo does not override the weak no-op line callback, so that path does not print an application warning. Our smoke wrapper provides a strong callback and prints the accumulated result. The original HAL's attempted interrupt-disable writes the wrong register, IER0 rather than IER1, as detailed below; do not describe the original smoke test as having successfully masked the lane interrupt. The optimized harness uses the corrected generated HAL copy.

| Sequence element | Original ST-based smoke test | Selected v25 cold capture |
| --- | --- | --- |
| Sensor preparation | Two full probe/init passes; approximately 480 ms of requested fixed reset/release waits in total | Preserve natural sensor cold startup during ROM boot; no repeated sensor reset |
| Receiver versus sensor START | Configure PHY and arm PIPE1 before sensor setup and START | Complete setup/START first; load and arm PIPE0 during the internal sensor startup interval |
| Saved image | Fourth frame; 640 × 480 Y8 output from RAW8 input | First frame; native 1120 × 1364 RAW10 |
| Observed error class | `0x8000` | `0x8000`, now specifically traced to lane 1 before exposure |

Both paths use two physical data lanes, the same required sensor polarity mapping, nominal 804 Mbps sensor output with the receiver's 800-Mbps range, and a nominal 20 MHz CSI configuration clock. The questionable PHY E2/E3 and CCFR programming is inherited from ST's pinned HAL. Longer waits and receiver-before-START ordering therefore did not prevent the historical error. This comparison rules out attributing the error class solely to the later aggressive startup optimization; it does not identify the electrical cause.

## Later v11 cold-boot evidence

`tmp/bringup/capture-opt-v11-cold-01` has two callbacks, but they bracket the image rather than both occurring during it. Relative to externally observed NRST release:

| Event | Time, ms | Status |
| --- | ---: | --- |
| Startup lane1 ECTRL |32.30224|SR0=00020000, SR1=76181000|
| First STROBE rise |32.66032|358.08 µs after the startup callback|
| First STROBE fall |43.64432|10.984 ms pulse|
| First VSYNC |43.88752|243.20 µs after falling edge|
| First frame complete |54.51696|Snapshot is frozen|
| Stop-time lane0 ECTRL |89.58736|SR0=00001100, SR1=66100010|

The first-frame snapshot reads SR0=00020000 and SR1=E6180000, with no payload CRC/ECC or D-PHY error flag set at that instant. Startup lane1 interrupts have already been disabled by the corrected HAL, so raw status matters. The second callback occurs35.0704 ms after frame completion and cannot itself show corruption of that frozen image. The root bench owner visually confirmed the LED panel. This is evidence of a usable image, not proof that startup lane-state behavior is electrically correct.

## PHY setup issues found in the source

The pinned HAL writes both high and low bytes of `osc_freq_target` to internal PHY registerE3, despite its own comment namingE3/E2. ST's [STM32MP25 Linux CSI implementation](https://github.com/STMicroelectronics/linux/blob/v6.6-stm32mp/drivers/media/platform/st/stm32/stm32-csi.c#L548-L568) writes the low byte toE2 and high byte toE3. It also uses a1 µs test-clock pulse and computes CCFR from the actual configuration-clock frequency. This is primary vendor implementation evidence, though the MP25 code alone does not qualify an N6 hardware change.

The ROM-preserving experiment supplies nominal20 MHz to CSI PHY. RM0486 §40.6.1 gives CCFR=ceil((F_MHz−17)×4), hence0x0C. The pinned HAL uses0x28 at two separate PFCR writes. A correction must change both; the first MODIFY_REG mask must include CCFR. Preserve the HSFR and direction fields.

HAL and the cited Linux code both use PHY E4=0x11 with an unresolved comment referring to a13–38 range. No complete public E4 table was recovered. The Linux implementation provides precedent for computedCCFR with unchangedE4, but do not invent an alternateE4 value. A hypothetical24 MHz/CCFR0x1C combination falls inside that comment's numeric range; no N6-specific guaranteed configuration-clock operating range was established, so it is not an automatically safe substitute. RM0486 §37.5.3 calls20 MHz the default, not an explicit maximum.

Test changes independently:1 µs pulse, E2/E3 address fix, and CCFR correction. Retain the original vendor file and generated-source hashes. Compare raw error flags at first frame and stop; a masked callback is never a successful repair.

## What the recorded error means

The pinned HAL's `0x8000` is `HAL_DCMIPP_CSI_ERROR_DPHY_CTRL`. It combines the two data-lane control errors. The actual lane is given by CSI_SR1: bit 4 is ECTRLDL0F and bit 12 is ECTRLDL1F. RM0486 describes these as an incorrect lane-state sequence. They are distinct from short packet, header ECC, payload CRC, and start-of-transmission synchronization errors. [RM0486 Rev 4, pp2058 and2061](../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf).

The v5 error callback ID is `72 + lane`, where the HAL enum is lane0 = 1 and lane1 = 2. Therefore ID74 denotes **lane 1**. Both recorded v5 errors are lane1 errors, not one error on each lane.

| v5 observation | Raw status | Interpretation |
| --- | --- | --- |
| First error, approximately 61.881 ms after main entry | SR0 `0x00020000`, SR1 `0x76181000` | VC0 running; lane1 ECTRL set; clock and both data lanes report stop state by the time of the snapshot |
| First exposure indication | Approximately 62.243–73.2269 ms | First error precedes the rise by approximately 362 µs |
| First VSYNC and frame completion | Approximately 73.4696 and84.0979 ms | Complete first snapshot arrives after the first pulse |
| Second error, approximately 119.1698 ms | SR0 `0x00001100`, SR1 `0x64101000` | SOF0/EOF0 status present, lane1 ECTRL set, all three stop-state flags clear during stopping |

These timings come from the root bench owner's v5 capture. The error register is latched; stop-state bits describe the later sampling instant, not the exact invalid transition. The first observation is consistent with a startup lane transition that settles before exposure. It does **not** prove that the transition is harmless or specify its electrical cause.

## HAL defects and diagnostic gaps

The pinned `stm32n6xx_hal_dcmipp.c` handles each D-PHY error by calling `__HAL_DCMIPP_CSI_DISABLE_IT`. That macro writes **IER0**, while these interrupt enables reside in **IER1**. The proper D-PHY macro writes IER1. In particular:

- Lane0 ECTRL's bit4 incorrectly disables IER0 TIM0IE.
- Lane1 ECTRL's bit12 incorrectly disables IER0 EOF0IE.
- The intended D-PHY source remains enabled, explaining why a later occurrence can still produce a callback.

The capture-firmware agent prepared a generated HAL copy with the ten D-PHY disable calls corrected; the original vendor source remains unchanged. After this fix, the HAL intentionally disables an error source after its first callback. Therefore **absence of a second callback is not evidence that a second error disappeared**. Preserve raw SR1 at completion and stop, and/or deliberately rearm the source after recording the first event for a controlled diagnostic. Do not clear history or relabel a suppressed callback as a clean link.

`HAL_DCMIPP_CSI_SetConfig()` enables sync, short-packet, data-ID, FIFO and D-PHY errors, but the pinned implementation does not enable the CRC/ECC/corrected-ECC interrupts. A cumulative `ErrorCode` without those bits does not establish error-free image transport. Enable those diagnostic interrupt sources before streaming or inspect their raw sticky flags after the first frame. Record SR0/SR1 and IER0/IER1 **before** invoking the HAL handler, which clears flags and changes enables. Retain frame-completion status separately from later stream-stop errors.

The local ES0620 errata text has no CSI/D-PHY-specific entry. That absence is not an explanation of the observed condition. The current upstream HAL source also contains configuration details that differ from prose/comments; use reviewed, targeted experiments rather than assuming an upstream refresh fixes this startup behavior. [ST HAL source](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/main/Src/stm32n6xx_hal_dcmipp.c).

## Sequence hypotheses and controlled tests

The original `VD6G_Start()` first runs `VD6G_Setup()`, which writes output-lane polarity/mapping, lane count, bitrate, output format, image dimensions and exposure mode, and only then sends START_STREAM. The receiver is already active at that point in v3/v5.

1. **Separate sensor setup from streaming.** Configure those sensor settings while in standby, then initialize/arm the receiver, then send START_STREAM. This removes host observation of any setup-induced lane transition without hiding an error flag. Some sensor settings may take effect only at stream start; a failed improvement remains useful evidence.
2. **Timestamp the actual error phase.** Preserve events around receiver PHY enable, sensor setup, START_STREAM, first strobe, first CSI SOF, frame completion and stream stop. Sampling all raw flags before HAL makes startup and shutdown errors distinguishable from in-frame errors.
3. **Test asynchronous startup only with a reception deadline.** Starting the sensor and initializing the receiver during the sensor's internal startup can overlap work. Receiver/DMA readiness must precede the **first** CSI SOF under the shortest required exposure, not merely under this approximately 11 ms test exposure. Starting the receiver after a transient is legitimate sequencing, but success requires the first frame and active error diagnostics. Do not silently discard a frame or rely solely on a nominal timer.
4. **Audit PHY clocks without speculative writes.** The HAL hardcodes CCFR `0x28`, while RM0486 gives a formula based on the actual CSI configuration clock. The v3 generated clock function selects ROM PLL1/60, not the custom high-speed baseline's clock tree. Read the actual PLL/IC configuration before deciding this is a mismatch. The sensor uses 804 Mbps while the receiver selects its 800-Mbps range; preserve those settings while isolating sequence changes. The separate PHY-register comments and writes also deserve review, but they are not established causes of the observed ECTRL event.

No primary source recovered so far specifies the VD56G3's exact electrical lane state throughout every standby-to-stream subphase. Treat LP-state explanations as hypotheses until measured or documented.

## The external trace resolves the apparent exposure mismatch

The v3 matched event analysis is in `tmp/bringup/capture-opt-rom-v3-trace/events-analysis.json`; the image and firmware records are in `tmp/bringup/capture-opt-ram-rom-v3-image/`. The root inspected the unenhanced preview and identified the LED panel. The snapshot contains 1,527,680 bytes, one VSYNC and one frame-completion callback, and its MCU/host checksums agree. Receiver error qualification remains separate.

| Quantity | External Saleae measurement | DWT divided by nominal 400 MHz |
| --- | ---: | ---: |
| First PA0 pulse width | 10.983680 ms | 10.893520 ms |
| Second PA0 pulse width | 10.984000 ms | 10.899765 ms |
| First falling edge to receiver VSYNC | 242.400 µs | 240.355 µs |
| VSYNC to frame completion | 10.628640 ms | 10.542410 ms |

Long intervals throughout the capture have a similar approximately 0.8–0.9% scale difference. The external trace is the wall-clock reference; the nominal `SystemCoreClock` value is not a measured oscillator frequency. HSI tolerance/drift is a plausible explanation, but DWT stoppage or other clock behavior must also be excluded before claiming a calibrated CPU clock.

The original exposure helper requests 1428 lines for 10,000 µs. At 1236 clocks/line and nominal 160.8 MHz, that is approximately 10.976418 ms. The external first pulse differs by approximately 7.3 µs, rather than the apparent 83 µs obtained by using nominal-clock DWT time. This small residual is approximately a line time, but **no documented universal extra-line correction has been established**. Sensor oscillator tolerance, effective line duration and strobe quantization must be considered separately from the MCU clock scale.

`analyze.py` now reports observed cycles per external second and warns when a >=1 ms interval differs from nominal DWT conversion by more than 0.5%. Those are diagnostic comparisons, not automatic clock calibration.

## Minimal first-exposure qualification experiment

Use two otherwise identical fresh captures with direct manual coarse exposure values such as 650 and1301 lines at register `0x044e`; both exceed the short-exposure special regime. After the first frame, record APPLIED_COARSE_EXPOSURE (`0x0064`, 16-bit), applied analog/digital gain, line length, GPIO0/1 controls, zero strobe start/end offsets, sensor identity and error registers. Readback adds no work before the first exposure if done after capture.

For each run, require:

- Receiver snapshot armed before START_STREAM; trace starts before the command, with no unobserved earlier pulse or SOF.
- First PA0 pulse changes by approximately **651 line periods** between the two settings. This causal relationship also qualifies the existing cable route as the exposure-controlled sensor output, provided the register readbacks match.
- First receiver VSYNC follows that first pulse's fall by the same small interval, and the first frame completes before a later frame could replace it. Do not discard startup frames.
- The first stored image is recognizable, MCU/host integrity agrees, and receiver payload-error flags are clean. A change in brightness is supporting evidence only; LED PWM can complicate brightness ratios.
- Repeat the test at the chosen production exposure range and record interrupt-priority/masking limits. PA0-to-PE0 mirroring remains an upper bound on the physical sensor edge until ISR latency is bounded.

A fixed-low/fixed-high sensor GPIO test is another useful route check; it must respect the sensor's streaming/GPIO-update rules. The exposure sweep and frame phase relationship give stronger evidence that the **first** observed pulse belongs to the first optical capture. They do not by themselves turn a RAM launch into a cold-reset measurement.
