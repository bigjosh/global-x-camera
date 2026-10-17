# Capture timing firmware

`build.py` is an offline builder. It reads the pinned, already prepared ST camera example at `tmp/bringup/x-cube-n6-camera-capture` and writes a new build directory. It does not access the bench. The original bring-up application and vendor checkout remain unchanged; generated copies preserve each experiment's edits and source hashes.

The harness uses the ST VD6G sensor driver with HAL I2C and the DCMIPP dump pipe. It captures the **first native 1120 × 1364 RAW8 frame** into internal SRAM at `0x34000000` (1,527,680 bytes). It uses no UART, RTOS, ISP, frame settling, or external RAM. Image statistics run only after snapshot DMA completes. The parent experiment controller owns all hardware operations and image verification.

The initial C entry opens volatile debug access before sensor or clock initialization. This uses the same documented BSEC debug keys as the earlier awake marker; it does not program OTP or lifecycle state. The normal success and error paths stay awake for readback.

## Working normal-boot context

The original ST `SystemInit` was suitable for the earlier development-mode test, but the October 17 stop-before/stop-after experiment showed loss of debug access when it ran after normal ROM boot. The exact triggering write was not isolated. Its operations include resetting the ROM's XSPI routing, clearing SAU regions, and changing compensation configuration. `--minimal-system-init` retains only vector-table placement and FPU access, preserving the known ROM configuration.

`--rom-clocks` preserves CPU and bus clocks. The measured ROM PLL1 output is 1200 MHz: 64 MHz HSI × 75 / 4 / 1 / 1. IC1 divides this to nominal 400 MHz CPU. The capture setup selects IC17 = PLL1 / 4 (300 MHz DCMIPP), and IC18 = PLL1 / 60 (20 MHz CSI). `--direct-clocks` performs precisely the two relevant IC configurations and DCMIPP selector operation from the pinned HAL, avoiding the generic peripheral-clock configuration routine. It requires `--rom-clocks`. The measured I2C PCLK is recorded in the trace; fixed timing values must correspond to that clock.

Earlier diagnostic builds deliberately preserve the old full clock initialization, or stop before/after `SystemInit`. Do not select these merely because their build directory has a later timestamp.

The existing NOR maintenance helper has strict context checks, including CONTROL and ROM clock/routing state. Running floating-point library code can set FPCA/SFPA even while the application remains in privileged thread mode. The host's `prepare_maintenance.py` now validates privileged Thread mode and inactive lazy FP state, disables interrupts and I-cache through the reviewed fixed helper, and clears CONTROL's inactive FP context. After v8a, the frozen NOR INFO operation passed all ROM clock, mux and XSPI guards with no write-enable operation. A successful image capture alone does not prove maintenance readiness; run that preparation and preflight.

For staged applications, the current immutable maintenance helper is at `0x341A0000`, with status at `0x341A0400`. Its former address, `0x34190000`, overlaps the receiver application and must not be reused. The host verifies either zero-filled space or the exact frozen helper before loading it; this does not authorize overwriting arbitrary live application code.

An experimental retained-RAM maintenance gate was rejected: the ROM cleared both request words at `0x341F0F00` during hardware reset. Older build snapshots retain that unused check; current source removes it. Recovery relies on awake debug access, preserved ROM clocks and the validated maintenance preparation, not RAM retention.

## Build options and experimental boundaries

- `--i2c-timing` substitutes an offline TIMINGR value for the BSP's expensive runtime search. `--i2c-hz` also selects Fast-mode Plus configuration above 400 kHz. `i2c_timing.py` reproduces the pinned BSP calculation and documents its assumptions; rounded periods can produce rates above the nominal request.
- `--reset-us` selects both the low reset pulse and the short post-release delay. A shortened pulse is an experimental value, not a claimed datasheet minimum. The sensor READY poll tolerates a NACK while the device starts, then requires the actual READY state before proceeding.
- `--poll-us` selects the inter-read delay. Polls have a nominal 500 ms DWT deadline and a finite iteration bound. Individual HAL I2C transfers retain the BSP timeout; a stalled transfer can therefore exceed the polling deadline before control returns.
- `--newest-only` rejects old silicon instead of retaining its unused firmware/vertical-timing patches. It reduces the ROM payload by approximately 18 KiB and implements the project's newest-silicon-only decision.
- `--prepare-early` moves the vendor's output/size/exposure/orientation setup ahead of receiver configuration, while leaving the actual START command after snapshot DMA is armed. It is a separate ordering experiment.
- `--fix-dphy-irq` corrects ten pinned HAL D-PHY error branches that incorrectly disable an IER0 bit instead of the corresponding IER1 source. Error flags and callbacks remain recorded. A disabled source must not be mistaken for absence of subsequent errors; the first-frame sticky flags are also recorded.
- CRC, ECC and corrected-ECC interrupt sources are explicitly enabled by recent diagnostic builds; the pinned HAL did not enable them in its default configuration.
- `--gpio-level 0` or `1` selects a static sensor GPIO0 output for route qualification instead of exposure STROBE. `--coarse-lines` selects a direct coarse exposure register override. These are measurement experiments, not production exposure policy.
- `--lto` enables cross-file link-time optimization. It does not replace image validation or hardware A/B measurements.
- `--batch-config` uses contiguous GPIO and manual exposure/gain bursts for an explicitly selected coarse exposure. This is a fixed-profile experiment, avoiding repeated transactions and generic range/conversion reads.
- `--phy-testclk-us` replaces the HAL's millisecond tick delay for a test-clock pulse with a DWT microsecond delay. The HAL comments describe 15 ns, but a primary minimum has not yet been found; the shortened pulse is an empirical experiment. It does not change the separate PHY CCFR/E4 settings.
- `--frame-lines` overrides the sensor frame period after the vendor initialization, retaining the same native output dimensions. Compare START-to-first-STROBE separately from frame period; do not infer exposure timing from frame completion.
- `--pll-prediv1` selects sensor PLL predivider 1 and multiplier 67 at the fixed 12 MHz external clock, preserving 804 MHz PLL and 160.8 MHz pixel clocks. UM2602 gives an inclusive 6–12 MHz PLL reference range and lists these register defaults, while its example and the pinned embedded driver use 2/134. This disagreement makes the setting a separate qualification experiment. `--clock-diagnostics` reads applied clocks after the first frame, before stopping the stream; those values do not constitute a dedicated PLL-lock flag.
- `--phy-target-low-e2` corrects the pinned HAL's low oscillator-target byte write from PHY address E3 to E2. `--phy-ccfr 12` independently corrects both configuration-clock range writes for the preserved nominal 20 MHz CSI clock. These are separate A/B experiments; the E4 setting remains unchanged. Error recording stays enabled.
- `--prestart-dwell-us 5000` inserts a measured delay after final sensor configuration and before START, with events 150/151. `--i2c-follower` selects documented I2C_SYNC mode while preserving other VT_CTRL bits, writes the 16-bit FSYNC delay as zero, and sends one `0x0202 = 2` trigger after STREAMING. Events 152/153 and trace words 61/62 bracket the trigger. Its ACK is checked after the first frame, because the sensor acknowledges this command after transmission.
- `--skip-sensor-reset` is a cold-boot-only monolithic experiment. It checks that PO5 began as input/analog without pulls and preloads its output HIGH before enabling the output, preserving the sensor's natural startup during the ROM boot. It does not characterize a warm reset of an already streaming sensor.

## Staged loading experiment

`build.py --stage2` links the camera application at `0x34190000` and omits its sensor reset. The stage2 early hook preserves DWT, the event table and PE0 parity. `build_staged.py` accepts that completed build plus an exact saved first NOR sector, compiles `stage1.c`, `stage1.S` and `stage1.ld`, and produces a 64-KiB combined image. The checked stage2 begins at NOR offset `0x2000`; bytes outside the two payloads retain their original values.

Stage1 opens volatile debug access before camera or memory work, records a strict ROM-clock/controller preflight and reads stage2 through the ROM's existing single-line 32 MHz XSPI configuration. It validates an IEEE CRC32 and stack/entry bounds before branching. It does not reset the NOR controller, reroute XSPI, change NOR mode, write-enable, erase or program the NOR. Every failure remains awake with a result in RAM.

The initial variant holds XSHUTDOWN low for 102 nominal microseconds, releases it and overlaps loading with the sensor's approximately 6.5 ms READY interval. `build_staged.py --skip-sensor-reset` instead preserves the module's natural startup during ROM, checking PO5 input/analog mode and no pulls before preloading HIGH and enabling its output. Events 208/209 record this preservation path; they must not be labeled as reset release. The measured no-reset experiment produced a discernible first image. This policy requires a genuine cold cycle with verified rail discharge; it does not establish sensor recovery after an arbitrary MCU-only reset.

Events 200–206 record prefix entry, reset low, reset release, load start, load complete, CRC pass and handoff. Event 207 is stage2 entry. Prefix status starts at `0x341F3000`; the exact source enum in each frozen build is authoritative because newer builds append diagnostics. The original first 28 words remain in place. Words 28–37 describe reset policy and PO5 state; 38 records read width, 39 the early-sensor result, 40–50 the optional XSPI-clock experiment, and 51/52 I-cache state. The first build was 1,460 raw bytes / 2,496 ROM boot-image bytes, followed by a 15,040-byte stage2; later manifests record their actual sizes. Stage1's stack is `0x34188000`; stage2's manifest supplies its own stack and entry. The prefix leaves DLR/AR from the completed read untouched because writing AR would start another read.

`--word-reads` reads a 32-bit FIFO word only when at least four bytes are available and required, with byte handling for the tail. `--inline-crc --prefix-opt O2` inlines the unchanged software IEEE CRC calculation. This reduced the v20 receiver load from approximately 4.42 ms to 2.92 ms externally, near the 32 MHz single-line wire limit. The measured cold prefix already had instruction cache enabled (`CCR = 0x20201`); enabling it was not the cause of this improvement. The default remains 32 MHz. An optional `--xspi64` experiment has guarded source/pad checks and restores the original prescaler after its read, but it was unnecessary for the timing path and has not established production electrical margin.

## Starting the sensor before loading the receiver

`build_staged.py --early-sensor` links the integer-only, bounded I2C driver in `stage1_sensor.c`. It requires the no-reset policy, FIFO word reads and a receiver built with `build.py --receiver-only`. It checks the sensor model and CCA revision, waits for READY and BOOT acknowledgements/state, configures the fixed native image profile and writes START before loading the receiver. It preserves ROM clocks, sensor calibration, defect correction and the NOR configuration. The current fixed profile is 1428 coarse lines, frame length 4336, unit gains and RAW8 output. All read/programming traffic is ordinary volatile sensor configuration; there is no OTP access.

Stage2 verifies the `SEN1` handoff at `0x341F4000`, installs the PA0 strobe interrupt and arms DCMIPP snapshot DMA. Both its entry and completed receiver setup must precede START-write completion plus 4.5 nominal milliseconds; a miss records failure and aborts the timing experiment. This is a conservative experimental guard relative to the approximately 5.3 ms measured START-to-exposure interval, not a sensor datasheet guarantee. Stage2 then checks START ACK and STREAMING state while awaiting the first frame. The v22 inline-CRC build armed the receiver approximately 3.0 ms after START, leaving about 1.5 ms to this guard. The first captured LED-panel image began exposure approximately 24.51 ms after NRST release in that run; the bench report owns measurement qualification and repeatability.

The sensor status contains 32 reserved words: magic, phase, result, last I2C ISR, START begin/end cycles, READY/BOOT cycles, model/revision/ROM/line length, write transaction/data-byte counts, read transaction/data-byte counts and receiver-ready cycles in words 0–16. Word 17 records the optional deferred orientation diagnostic. Prefix phase 37 with result zero indicates START was sent; it does not by itself prove STREAMING or a successful image.

`--trim-sensor` combines model/revision into one documented contiguous read, removes repeated revision and frame-length operations, writes the complete documented eight-byte clock block and batches the ROI. It defers ROM, orientation and line-length diagnostics until after the first frame, requiring stage2 `--sensor-late-diagnostics`; line length must still equal 1236 for acceptance. BOOT state checks and image controls remain. Relative to the untrimmed prefix this removes six read transactions, six write transactions and nine read data bytes: 459 nominal SCL clocks, excluding START/STOP overhead and variable polling. Actual counters in each capture remain authoritative.

`--stage1-source-dir`, `--sensor-source` and the stage2 `--capture-source` allow an experiment to reuse exact frozen source instead of silently incorporating another concurrent edit. Every build manifest includes source and payload hashes. Build directories are immutable snapshots; hardware status is recorded separately by the controller.

## Probe semantics

PD0 rises at the application's earliest C hook. PE0 toggles for each recorded phase/event. It is a phase marker, not inherently an exposure-high waveform. PA0 is made an input before the adapter's sensor GPIO0 can drive it. GPIO1 is set high to select the populated adapter level translator's sensor-to-MCU direction. CCA GPIO_UPDATE is applied in standby, with STROBE offsets explicitly zero. PA0 rising/falling EXTI callbacks record IDs 50 and 51.

Sensor GPIO output behavior must be qualified against streaming state and controlled exposure changes. DCMIPP VSYNC corresponds to received frame start and occurs after exposure; it is not exposure onset. The PA0 strobe is initially a candidate exposure indication until the route, polarity, offsets and first-frame association have been verified. EXTI pending flags are cleared before enabling its IRQ, and initial PA0 state is retained.

The controlled 650/1301/1428-line sweep produced external strobe widths of approximately 5.004/10.008/10.984 ms, with a stable approximately 243 us from strobe fall to CSI VSYNC. This supports the exposure interpretation independently of software timing. EXTI adds interrupt latency, so its mirrored transition remains an upper-bound observation of the physical sensor edge; it is not a direct analog integration probe.

## Readback layout

The vector-first binary normally loads at `0x34180400`; its exact entry and stack addresses are in its manifest. Status begins at `0x341F0000` (64 little-endian words). Events start at `0x341F0100`, up to 200 records of four words: event ID, DWT cycle count, HAL milliseconds, and the current `SystemCoreClock` variable. External Saleae timestamps are the timing authority when clocks change or nominal HSI frequency differs from its actual frequency.

| Status word | Meaning |
|---|---|
| 0–4 | Magic `CTP1`, current stage, event count, result, accumulated camera error flags |
| 5–11 | Frame count, VSYNC count, error callback count, pixel minimum, maximum, sum, FNV-1a |
| 12–15 | Frame address, byte count, width, height |
| 16–20 | Initial RCC CFGR1, CFGR2, SCB CCR, BSEC debug control, AP unlock |
| 24–27 | Fault CFSR, HFSR, BFAR, MMFAR |
| 28–30 | PA0 before/after START and GPIO route configuration status |
| 32–36 | PCLK1 frequency, I2C TIMINGR, CR1, initial PA0 level, error record count |
| 38 | Error record width in words (12 in newer builds; older records used 8) |
| 40–43 | Write transactions/data bytes, read transactions/data bytes through START write |
| 44–47 | CSI SR0/SR1 after first frame, applied coarse exposure, sensor line length |
| 52–58 | Optional applied external, system PLL, pixel and MCU clocks; packed predivider/multiplier/output-divider/MIPI multiplier; MIPI divider; configured frame length |
| 61–63 | Receiver-only: elapsed cycles to receiver ready, elapsed cycles at stage2 entry, 1,800,000-cycle guard. I2C-follower builds instead use 61/62 for trigger begin/end. |

Stage 40 means capture finished; `0x80000000 | operation` indicates a checked operation failed. `0xFFFFFFFF` is the fault path. Event 24/25 bracket the START write, 26 is driver START return, 29 is VSYNC, 30 frame completion, 31 processing resumed after the first frame. Events 100–109 identify sensor-driver subphases. Error IDs are 70 for pipe and 71 for global callbacks; lane callbacks are `72 + HAL lane enum` (the enum is not necessarily zero-based).

Error records begin at `0x341F1000`: ID, DWT, HAL tick, error flags, entry SR0, entry SR1, DCMIPP CMSR2, previous stage, entry IER0, entry IER1, callback-time IER0, callback-time IER1. Old eight-word records omit the final four fields. The complete build manifest identifies the version.

Read the raw frame with a `.bin` destination through CubeProgrammer; the controller found that `.raw` was rejected by its upload command. Render and inspect the image as well as comparing the host-computed sum/hash with the firmware statistics.

These RAW8 captures validate startup and a visible first image, but truncate the sensor's 10-bit samples. RM0486 specifies that pipe0 pads RAW10 to 16 bits, requiring 3,055,360 bytes at native resolution. Simply increasing the current buffer would overwrite code, stacks and diagnostics; starting that larger buffer at `0x34200000` also exceeds the available space. Native RAW10 requires a separately reviewed memory/clock/power layout and is not established by the RAW8 timing experiments.

ST-derived code remains governed by the pinned package license and [the existing ST license copy](../bringup/ST-LICENSE.md). These are bench experiments, with no claim of production timing or retention qualification.
