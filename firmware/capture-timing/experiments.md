# Capture startup experiments: results and open qualification

October 17, 2026. This report covers 40 runs: the original 17 through v16, 11 further cold-start experiments through v24, a second independent v24 cold cycle, six native RAW10 captures (v24b and five v25 starts), the v26 dark-calibration diagnostic, two independent v27 MIPI experiments, the v28 temperature prestart diagnostic and one native TIM5 latency-validation capture. Hardware execution and image inspection were performed by the root bench controller; this report and archive were assembled offline.

The fastest visually checked autonomous result in this set is **23.31024 ms from NRST release to the first sensor exposure strobe** (v24). Its first complete 1120 × 1364 RAW8 image reached RAM at 45.16672 ms, and the root controller confirmed a discernible LED panel. The distinction matters: the agreed 50 ms target concerns the start of exposure, not completion. These are individual measurements on the delivered board, not a worst-case specification or proof that optimization is finished.

The best verified **native RAW10** result is **23.32416 ms to exposure and 45.18208 ms to the complete frame** (v25 repeat). All five selected native v25 starts passed data, memory and visual checks; they are described separately below so the faster RAW8 diagnostic is not mistaken for the native-precision profile.

The [final optimization report](optimization-results-2026-10-17.md) gives the selected configuration, current bench state and scoped engineering stopping assessment. This page preserves the individual experiments and their limitations.

## Evidence and timing definitions

The [compact archive](evidence/2026-10-17-through-v16/README.md) contains exact timing/result JSON, digital traces, capture settings, available rail-validation summaries, build manifests and hash-verified source snapshots. [The ledger](evidence/2026-10-17-through-v16/ledger.json) preserves every first and subsequent strobe separately. [Visual reviews](evidence/2026-10-17-through-v16/visual-review.json) are separate root-controller assertions: the LED grid was discernible for all included runs **except v9-cold, which was not visually reviewed**. Raw result fields are unchanged.

External Saleae timestamps are authoritative. PE0 toggles once per ordered RAM event; the analyzer requires an exact sequence match. On cold starts, time zero is the observed NRST rising edge. A RAM launch starts after debugger-controlled preparation and is timed from its first recorded application event; it is not a cold-start result. The sensor's zero-offset STROBE reaches PA0 through the adapter translator and is mirrored by an interrupt to PE0. Thus the measured onset includes positive translator/interrupt/logging delay, whose universal maximum is not established; the isolated TIM5 result below measures a microsecond-scale sample bracket. The 0.16 µs analyzer sample interval alone does not establish optical accuracy.

The sensor manual identifies zero-offset STROBE as the exposure interval. DCMIPP VSYNC reports frame reception, and frame completion reports the snapshot reaching RAM. They are not interchangeable. The v16 exposure sweep below strengthens the association of the **first** strobe with the **first** saved image. See [measurement method and limitations](exposure-measurement.md), [UM2602 §18.2](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf), and [RM0486 §39.4.7](../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf).

The [v17–v24 supplement](evidence/2026-10-17-v17-through-v24/README.md) follows the same format and adds small raw RAM records and programming-verification metadata. Its extractor checks that the intended sector, verified readback and prefix/monolithic manifest identify the same SHA-256; these records do not include the NOR contents. All 11 additional first frames were visually checked by the root controller. Original pre-execution visual fields remain unchanged, with actual inspection assertions kept separately.

## Application changes, tested by RAM launch

All times in this table are milliseconds after the first application event, excluding ROM and payload loading. These revisions contain multiple changes, so differences are observed net improvements rather than isolated causal estimates for every edit.

| Run | Principal change or purpose | First strobe | First frame complete |
| --- | --- | ---: | ---: |
| v3 | ROM-clock-preserving baseline; first exposure trace and recognizable image | 150.075 | 171.929 |
| v5 | Explicit 100 kHz I2C timing for the retained clock tree; newest sensor revision path | 62.243 | 84.098 |
| v6 | 400 kHz I2C and 50 µs polling interval | 33.915 | 55.770 |
| v7 | 1 MHz I2C; correct the HAL's D-PHY interrupt-disable register | 31.260 | 53.117 |
| v8a | Reduce the requested sensor reset hold from 10 ms to 100 µs | 18.175 | 40.032 |
| v9 | Link-time optimization and direct clock setup; raw payload 15,324 bytes | 18.151 | 40.008 |

The reset-hold reduction and finer readiness polling remove artificial waiting. In v8a, sensor release to observed READY is 6.464 ms. The v9 build shrinks raw code from v8a's 25,132 bytes to 15,324 bytes, while its application-only timing remains similar. A smaller payload primarily helps the subsequent cold-boot path.

## Autonomous cold starts

Each included cold capture passed its archived three-rail discharge/restoration check. The probes cover target 5 V, target 3.3 V and main MCU VDDIO; they do not directly measure every internal or always-on rail. All values below are milliseconds after NRST release. ROM denotes NRST to the earliest PD0 application marker, including the ROM's required payload work.

| Run | Principal change | ROM | First strobe | First frame complete | Visual check |
| --- | --- | ---: | ---: | ---: | --- |
| v9-cold | Entire small application loaded before sensor release | 18.872 | 37.080 | 58.937 | Not reviewed |
| v11-cold | Small first stage releases sensor, then loads second stage during sensor startup | 15.257 | 32.660 | 54.517 | LED grid |
| v13-cold | Replace millisecond PHY test-clock hold with 1 µs | 15.829 | 31.942 | 53.799 | LED grid |
| v14-cold | Batch sensor configuration and use explicit coarse exposure lines | 15.509 | 30.377 | 52.234 | LED grid |
| v15-cold | Configure and arm receiver while waiting for sensor readiness | 15.208 | **30.041** | **51.897** | LED grid |
| v16-base | Matched diagnostic baseline for the parameter sweep | 15.753 | 30.577 | 52.434 | LED grid |
| v16-coarse650 | 650 coarse exposure lines | 15.265 | 30.080 | 45.957 | LED grid |
| v16-coarse1301 | 1301 coarse exposure lines | 15.557 | 30.394 | 51.274 | LED grid |
| v16-frame2168 | 2168 frame lines | 15.626 | 30.458 | 52.368 | LED grid |
| v16-frame8666 | 8666 frame lines | 15.373 | 30.210 | 52.067 | LED grid |
| v16-pll1 | PLL predivider 1 / multiplier 67 in place of 2 / 134 | 15.712 | 30.584 | 52.441 | LED grid |

ROM-to-PD0 varies by about 0.62 ms across the staged runs. Consequently an isolated total-time difference of a few tenths of a millisecond must not be attributed to a sensor setting without checking phase-relative timing. v15's post-PD0 path is 14.833 ms; v16-base's is 14.824 ms despite its slower absolute result.

The v15 critical path is approximately 15.208 ms ROM, 0.110 ms to sensor release, 6.526 ms to observed READY, 2.894 ms of remaining setup through the START write, then 5.302 ms to the first strobe. Second-stage loading and receiver configuration overlap sensor startup. Moving work into that interval is useful; adding its duration again would overestimate the serial path.

The 1 µs PHY test-clock experiment is supported by ST's related STM32MP25 Linux implementation using a 1 µs delay and the N6 HAL comment specifying a much shorter hold. It remains a tested implementation change, not a newly established N6 electrical minimum. [ST Linux implementation](https://github.com/STMicroelectronics/linux/blob/v6.6-stm32mp/drivers/media/platform/st/stm32/stm32-csi.c), [N6 HAL implementation](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/main/Src/stm32n6xx_hal_dcmipp.c).

## Cold-start changes after v16

All times below are milliseconds after NRST release. Each run retained a complete first frame, matching firmware/host integrity statistics, a passing three-rail cold-cycle check and a discernible LED panel confirmed by the root controller.

| Run | Principal change | ROM to PD0 | First strobe | First frame complete |
| --- | --- | ---: | ---: | ---: |
| v17-E2 | Correct PHY oscillator-target low-byte address to E2 | 15.715 | 30.557 | 52.413 |
| v17-CCFR | Correct both PHY range values for nominal 20 MHz configuration clock | 15.616 | 30.471 | 52.327 |
| v18 | Preserve sensor's natural cold startup; no redundant software reset | 15.907 | 29.355 | 51.212 |
| v18b | Same no-reset idea in a monolithic ROM-loaded application | 19.006 | 27.429 | 49.286 |
| v19 | Read staged payload as 32-bit FIFO words, unchanged nibble CRC | 15.675 | 29.552 | 51.408 |
| v20 | START sensor before loading/arming the receiver | 16.498 | 24.670 | 46.526 |
| v21-dwell | Wait 5 ms after final setup and before START, matched v16 basis | 15.578 | 35.472 | 57.328 |
| v21-follower | Documented I2C_SYNC trigger mode, matched v16 basis | 15.528 | 30.831 | 52.687 |
| v22 | Inline CRC and optimize the prefix for speed | 16.333 | 24.506 | 46.362 |
| v23 | Batch/reduce critical I2C transactions; defer diagnostic reads | 16.304 | 23.902 | 45.758 |
| v24 | Exact v23 sources, prefix optimized for size | 15.712 | **23.310** | **45.167** |

The module's fitted pull-up permits sensor boot while the MCU executes its ROM. The no-reset prefix checks PO5 is input/analog with no pulls, preloads its latch HIGH, then enables its output without a deliberate LOW pulse. The hardware record shows the expected initial mode and a valid first image. This avoids restarting an already-ready sensor. It is qualified here for a discharged cold cycle, not a warm MCU-only reset with an unknown sensor state.

Once that reset was removed, the staged code load no longer hid inside sensor readiness. The monolithic v18b was faster than v18 because its ROM-loaded payload avoided the slower custom copy, despite the later PD0 marker. The v19 word-read change alone did not help: the software CRC remained the bottleneck and the prefix load took 5.444 ms in that run.

v20 moved the fixed sensor setup into the small prefix and wrote START before copying the receiver. The approximately 5.3 ms internal sensor interval then hid the load and receiver setup. Stage2 must install the strobe IRQ and arm snapshot DMA before START end plus 4.5 nominal milliseconds; failure stops the experiment instead of accepting a later frame. v20 barely passed that guard: receiver-ready was approximately 4.487 ms after START by nominal DWT accounting. This motivated v22 rather than treating a visible image as sufficient margin.

Inlining the unchanged CRC and selecting `-O2` reduced the externally measured receiver load from 4.427 ms to 2.913 ms at the unchanged 32 MHz NOR clock. v22 armed the receiver at approximately 2.987 nominal milliseconds after START, leaving about 1.5 ms to the guard. The actual cold prefix already had I-cache enabled; enabling cache was not the improvement. Hardware CRC and 64 MHz NOR reads were therefore unnecessary for the current critical path.

v23 removed duplicate revision/frame operations, combined model/revision and contiguous clock/ROI transfers, and moved ROM/orientation/line-length diagnostic reads after the frame. It retained model/revision qualification, BOOT ACK/state checks and all selected image controls. The line length still must equal 1236 for acceptance. The static transaction reduction is six reads, six writes and nine read data bytes, or 459 SCL clocks before variable polling/START/STOP costs. Prefix size also fell by 400 bytes. v24 reduces that prefix by another 432 bytes with `-Os`, while its externally measured load remains 2.936 ms, effectively the same as v23's 2.935 ms. ROM-to-marker variability means the full 0.592 ms total difference cannot be attributed solely to those 432 bytes.

The v24 phase chain is approximately 15.712 ms ROM-to-PD0, 2.294 ms to completed START and 5.304 ms to first strobe. The receiver load is overlapped with the final interval and must not be added again. This is a measured critical-path decomposition, not a lower bound on every possible firmware design.

An [independent second v24 cold cycle](evidence/2026-10-17-v24-repeat/README.md) produced its first strobe at 23.67008 ms and complete frame at 45.52640 ms. The root controller again confirmed the LED panel and all three observed rails passed discharge/restoration. The two starts establish basic repeatability, with 0.360 ms spread in this tiny sample; they do not establish a worst-case bound.

## What the v16 sweep establishes

These runs share one generated source/configuration base. The sensor reports 12 MHz external clock, 804 MHz system PLL and 160.8 MHz pixel/MCU clocks throughout. Applied coarse exposure and configured frame length are retained in the ledger.

| Variant | Coarse lines | Frame lines | START write end → first strobe, µs | First strobe width, µs | First → second strobe period, µs |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 1428 | 4336 | 5293.12 | 10984.00 | 33328.32 |
| coarse650 | 650 | 4336 | 5293.44 | 5004.00 | 33328.32 |
| coarse1301 | 1301 | 4336 | 5308.48 | 10007.68 | 33328.32 |
| frame2168 | 1428 | 2168 | 5309.12 | 10984.00 | 16664.16 |
| frame8666 | 1428 | 8666 | 5306.40 | 10984.00 | 66610.40 |
| pll1 | 1428 | 4336 | 5336.80 | 10983.84 | 33328.16 |

Changing coarse exposure changes the first strobe width and first image arrival, with the same approximately 243 µs strobe-end-to-VSYNC interval and 10.629 ms readout for the exposure sweep. This is causal evidence that the first pulse is the exposure associated with the first image. Widths fit `(coarse + 1) × 1236 / 160.8` µs closely on this unit, but the extra-line relationship is an empirical observation, not a documented universal correction. The original driver's integer line-time arithmetic turns its requested 10 ms into 1428 lines; 1301 lines is the approximately 10 ms alternative.

Changing frame length changes the subsequent frame period as expected but does not materially change the first 5.3 ms wait. Likewise, the alternative PLL divider/multiplier is confirmed in applied readbacks and preserves the resulting clocks, but provides no measured startup improvement. These tests reject those specific explanations for the delay; they do not prove the delay unavoidable.

The later 5 ms pre-START dwell also leaves a 5.304 ms START-to-first-strobe wait, adding the dwell to total latency instead of hiding startup. I2C_SYNC mode gives 5.527 ms from START completion to the first strobe, including the subsequent explicit trigger. Neither tested strategy shortens the first-exposure path. These negative results narrow the scheduling hypotheses but do not establish a documented fixed sensor minimum.

## Receiver errors remain an open qualification item

Every result has `camera_error = 0x8000`, the D-PHY control/state-sequence error. Where detailed events are available, the first occurs before the first exposure. No recorded callback occurs during first-frame reception; some runs also produce an error when stopping, after the frozen snapshot. For example v11's second error is about 35 ms after first-frame completion and cannot retroactively corrupt that frozen RAM buffer. v3 predates complete error-event recording, so its error history must not be reconstructed from a zero event count.

This is not proof that errors are harmless. The HAL disables the corresponding lane interrupt after the first callback, so absence of further callbacks is not an exhaustive error census. Later builds retain raw status at first-frame completion, and CRC/ECC monitoring is explicitly enabled. The observed LED grid and firmware/host image-integrity match demonstrate useful images; resolving the startup state-sequence error is still needed before a robust configuration is accepted. The [CSI investigation](csi-startup-errors.md) records the wrong interrupt-register macro, E2/E3 PHY programming defect and CCFR/clock discrepancy.

The isolated v17 E2-address and CCFR corrections both preserve a discernible first frame, but neither removes the startup lane-1 ECTRL event. Both retain `camera_error = 0x8000`, first-frame SR0 `0x00020000` and SR1 `0xE6180000`, matching the earlier baseline. They are recorded negative results, not a reason to suppress the error. The subsequent through-v24 runs also retain this startup flag; their absence of recorded CRC/ECC errors is evidence about these captures, not an exhaustive electrical qualification.

## First full-resolution RAW10 capture

The isolated v24b build captures native 1120 × 1364 RAW10 into 3,055,360 bytes of right-aligned 16-bit samples. All runtime code, stack and diagnostics moved above the image; the prefix enables and checks the required SRAM banks before handing over. The first observed exposure began at **24.66704 ms after NRST**, and its image completed at **46.52496 ms**. This run uses the conservative v22 sensor prefix, not the smaller RAW8 v24 prefix, so the latency difference is not a controlled measurement of RAW10 overhead.

The byte counter was exact, the canary intact, and MCU/host checksums matched. All upper six sample bits were zero, all four low-two-bit combinations appeared, and samples spanned 61–639. The root controller viewed a discernible LED panel using a fixed RAW10 >> 2 preview. A pre-exposure D-PHY control-sequence error remains; image validation does not dismiss it. See the [native capture archive](evidence/2026-10-17-native-raw10-v24b/README.md) and [RAM/format design](raw10-relocation.md).

The original capture wrapper failed only during subsequent offline timing analysis: initial power-down produced a 160 ns NRST high bounce, followed much later by the real boot release. Reanalyzing the unchanged trace after a point within the verified discharged interval selected the real boot and matched all 40 external event edges. The archive preserves the original failure log and explicit correction note. No new hardware measurement or edited trace was substituted.

The smaller native v25 build combines the trimmed sensor sequence and `-Os` prefix with the same validated memory bootstrap. Its two cold starts began exposure at **23.89520 ms and 23.32416 ms**, with complete frames at **45.75312 ms and 45.18208 ms**. Both passed the exact byte count, canary, sample-bit and MCU/host checksum checks, and both first images showed the LED panel to the root reviewer. The best native RAW10 result is therefore **23.32416 ms**; the separate RAW8 timing-harness best remains **23.31024 ms**. Neither is a worst-case guarantee.

Almost all of the 0.57104 ms variation between native repeats occurred before the first application marker (0.56992 ms difference). The START-to-first-strobe intervals were 5.30096 and 5.30224 ms. Both runs retained the pre-exposure D-PHY sequence error. The [v25 repeat archive](evidence/2026-10-17-native-raw10-v25/README.md) preserves both full event sequences, rail checks, source hashes and separate visual assertions.

The [final three-start supplement](evidence/2026-10-17-native-raw10-v25-final-repeats/README.md) adds native v25 exposures at **24.01344, 23.83360 and 23.91440 ms**, with complete frames at **45.87136, 45.69152 and 45.77232 ms**. All three passed data/memory/rail checks and showed the LED panel to the root reviewer. Across all five selected-build cold starts, exposure lies at **23.32416-24.01344 ms** (median **23.89520 ms**), and first-frame completion at **45.18208-45.87136 ms**. Their START-to-strobe intervals span only 5.30080-5.30432 ms; most overall variation precedes the first application marker. The earlier archive remains unchanged, and the supplement retains both later firmware-restoration records.

## Dark-calibration diagnostic

The [v26 archive](evidence/2026-10-17-v26-darkcal/README.md) records a matched v24 RAW8 experiment with automatic dark calibration disabled and its register read back before START. START completion at 18.75248 ms led to first strobe at 24.04896 ms, or **5.29648 ms** later; the first frame completed at 45.89008 ms. This does not shorten the approximately 5.3 ms sensor interval. The root controller still saw the LED panel, but the gray pedestal increased substantially: byte minimum 113 rather than approximately 15. Automatic dark calibration remains the normal setting. The two added I2C transactions precede START and must not be confused with the sensor's post-START interval.

## Independent MIPI experiments

The [v27 archive](evidence/2026-10-17-v27-mipi/README.md) tests two documented controls separately while preserving automatic dark calibration. Noncontinuous MIPI clock at the original 804 Mbps produced a 5.29680 ms START-to-first-strobe interval, with exposure at 23.63792 ms and frame completion at 45.49440 ms after NRST. Requesting 1000 Mbps with the matched receiver table entry produced a 5.29760 ms interval, exposure at 23.62832 ms and frame completion at 45.48480 ms. Both images were visually checked. Neither setting removes the startup `0x8000` state-sequence flag, and neither offers a useful first-exposure improvement.

The requested 1000 Mbps run reported MIPI multiplier 39 and output divider 1 with its unchanged 804 MHz system PLL. Thus its nominal register-derived rate was **979.875 Mbps**, from `804 × 39 / 1 / 32`; it was not assumed to be 1000 or 1005 Mbps. The pinned ST nearest-rate algorithm selects the nominal 1000 receiver entry for this value. The sensor's applied divider readbacks and the actual first image are preserved alongside all errors.

## Temperature prestart diagnostic

The [v28 archive](evidence/2026-10-17-v28-temperature/README.md) tests the documented standby temperature command after BOOT and before normal image configuration. It waits for acknowledgement, confirms SW_STANDBY and reads the temperature result, preserving all subsequent calibration and capture settings. The operation adds **1.83712 ms**. START completes at 20.09376 ms, first strobe follows at **25.39168 ms**, and the complete image arrives at **47.24816 ms** after NRST. Its **5.29792 ms** post-START interval is unchanged. The root controller saw a discernible LED panel, and integrity/rail checks passed. This negative result rejects that particular shared-analog-preparation strategy; it does not expose the sensor firmware's internal sequence.

## Hardware-timer check of the exposure marker

The [native v29b TIM5 archive](evidence/2026-10-17-native-raw10-tim5-v29b/README.md) independently latches both PA0 strobe edges in a previously unused timer while preserving the EXTI-to-PE0 marker. It produced a visually confirmed native frame: first external marker at **23.732160 ms**, complete frame at **45.589920 ms** after NRST. Four edge records passed ordered association and capture validity, with no overcapture or record overflow.

For the first edge, the measured synchronized-timer-input to PE0 bracket is **0.6743-3.9855 microseconds**, placing that timer edge at **23.728175-23.731486 ms** after NRST. The largest upper delay endpoint across four records is approximately **4.1001 microseconds**. This is far below the millisecond-scale startup differences, but it is not an exact correction to earlier runs or a universal IRQ-latency guarantee. Sensor output, translator and timer-input synchronization delays are excluded, and the added counter reads slightly perturb this diagnostic's callback.

The decoder verifies the timer/core 3:4 clock ratio and uses independent non-strobe event intervals for an empirical frequency envelope with an explicit endpoint allowance. The initial longer-interval calibration failed pulse-width consistency; that rejected calculation and all observed rates remain in the archive. The final envelope is not a pointwise or universal clock bound. Image checks and the unchanged startup D-PHY flag are retained separately from marker qualification.

## Remaining qualification and stopping interpretation

Startup PHY sequencing and the sensor's internal START-to-exposure work remain unexplained. Natural cold power-up, exposure/frame timing, PLL division, pre-START dwell, I2C triggering, dark calibration, MIPI clock/rate and temperature prestart have been tested as described above. Native RAW10 acquisition and the enlarged RAM layout now have seven successful cold-capture validations, including five with the selected normal-capture prefix and one isolated timer diagnostic. These RAM dumps do not implement the final 16-bit grayscale PNG export path.

The traces alone do not prove an absolute silicon minimum or a statistical 90% confidence interval. The [final optimization report](optimization-results-2026-10-17.md) combines them with the documented-command review, ROM loading experiments and bounds on remaining host work for a scoped engineering judgment. The approximately 5.3 ms sensor interval is experimentally unchanged across the tested controls, rather than a documented immutable delay. Product rail sequencing, the startup D-PHY flag, temperature/voltage/unit variation and complete take/save/shutdown behavior remain separate qualification work.

## Archive limitations

Raw timing/result records are byte-identical to their source records. Build metadata still says `hardware_status: untested` because it was emitted before execution; the separate capture records provide the later observations. Most manifest-declared sources were archived only after exact SHA-256 matching. The historical v3 `capture.c` was subsequently edited and its original bytes were unavailable, so that one source is explicitly missing rather than replaced with today's file. Manifests and sources are an evidence collection, not a complete standalone toolchain or binary release. Original frame data, previews, full analog streams, Saleae sessions and NOR backups remain outside this compact archive.
