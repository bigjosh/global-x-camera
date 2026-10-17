# Measuring reset to the first usable exposure

Research and bench method, October 17, 2026. Hardware operation belongs to the root bench controller. The later qualification results precede the original proposed wiring and measurement method below.

## Later first-pulse qualification: v16 exposure sweep

The initial proposal below is now supported by the controlled captures in `tmp/bringup/capture-opt-v16-{base,coarse650,coarse1301}-cycle-01/cold`. The root controller subsequently confirmed visible LED-grid images for all six v16 variants. Those assertions are recorded separately from the unchanged raw results in [the archived visual reviews](evidence/2026-10-17-through-v16/visual-review.json). See [the interim report](experiments.md) and [compact ledger](evidence/2026-10-17-through-v16/ledger.json).

| Applied coarse lines | First pulse, µs | START write end to first rise, µs | First fall to VSYNC, µs | VSYNC to frame complete, µs |
| ---: | ---: | ---: | ---: | ---: |
| 1428 | 10984.00 | 5293.12 | 243.04 | 10629.44 |
| 650 | 5004.00 | 5293.44 | 243.04 | 10629.44 |
| 1301 | 10007.68 | 5308.48 | 243.20 | 10629.44 |

Applied clock readbacks remain 12 MHz external, 804 MHz system PLL and 160.8 MHz pixel clock. Changing exposure changes the **first** pulse duration and the first frame's arrival by the corresponding amount while preserving the readout interval. This causally supports association of the first strobe with the first captured image. It also rejects exposure duration as the dominant cause of the approximately 5.3 ms START-to-integration wait over this tested range. A stop-time lane0 error in the 1301 run follows the completed first snapshot.

UM2602 §18.2 Figure17 explicitly labels the internal strobe interval as exposure and defines GPIO offsets relative to its edges. With both offsets zero, the GPIO is an exposure indicator. Nevertheless the measured PE0 transition follows translation, EXTI entry, HAL dispatch and event logging. The observed onset is an upper bound on the physical edge; the current experiment does not provide a measured maximum interrupt latency. Do not present sub-microsecond optical accuracy or subtract an assumed interrupt delay.

At nominal line time 1236/160.8 = 7.686567 µs, these three pulse widths fit `(coarse + 1) × line_time` within 0.23 µs. This is an empirical observation, **not a documented general extra-line rule**. Do not correct the exposure onset or silently change firmware exposure arithmetic on that basis. The relevant user target is millisecond-scale, but uncertainty should still be stated.

If a tighter latency bound is needed, DS14791 lists PA0 as TIM2_CH1/AF1 and TIM5_CH1/AF2. A hardware input-capture timestamp on the existing PA0 route could remove ISR delay without another probe, provided timer frequency, counter epoch, polarity, overcapture and synchronization to DWT are qualified. That measurement is proposed, not implemented here.

## Compact offline experiment ledger

`summarize.py` reads explicitly selected capture directories, each containing `timing.json` and `ram/capture-result.json`. It verifies the event sequence matches, preserves first and later pulses separately, classifies errors relative to exposure and frame readout, includes applied clocks, and hashes both source records. It does not access instruments, images, memory dumps or NOR snapshots. Visual qualification is copied from the source record and never inferred.

```text
python firmware/capture-timing/summarize.py CAPTURE_DIR [CAPTURE_DIR ...] --json-out NEW_LEDGER.json --markdown-out NEW_LEDGER.md
```

The output options are optional and refuse to overwrite existing files. Specify the nested `cold` directory for experiments that store their capture there. JSON times are in microseconds; the displayed table uses milliseconds. Its error counts mean before first VSYNC, during the first readout, and after first-frame completion. The raw error details and separate optical phases remain in JSON. Four ledger tests plus eight event-correlation tests pass using unittest discovery with `-s firmware/capture-timing -p test_*.py`.

## Measure three distinct events

| Event | Evidence | What it establishes |
| --- | --- | --- |
| Integration starts | Sensor STROBE, with its programmed offsets zero, observed through a qualified path | The requested optical start time |
| Frame reaches receiver | DCMIPP VSYNC event | CSI start-of-frame reached the selected pipe |
| Complete frame is in RAM | DCMIPP FRAME event and integrity checks | The final pixel was written through AXI |

DCMIPP's software VSYNC means the input frame start; its FRAME event follows the final output pixel write. These differ from sensor integration. Record all three, along with the start and completion of the I2C START_STREAM transaction. A command ACK or STREAMING state alone cannot establish exposure onset. [RM0486 Rev 4, §39.4.7, p1834](../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf).

The sensor's zero-offset STROBE represents integration. GPIO controls occupy `0x0467+i`; mode `2` selects STROBE, mode `5` selects a fixed output, bit 4 sets its value, and bit 5 inverts polarity. Explicitly write signed line delays `0x0471` and `0x0472` to zero. GPIO operation normally requires STREAMING. On CCA, configure context 0 and issue standby command `0x0201=6` (GPIO_UPDATE), then poll its ACK. Context changes introduce a one-frame GPIO update delay. Qualify the **first** pulse against the first received image; a later pulse is insufficient. [UM2602 Rev 8, §§18–19, pp47–49 and56–65](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf).

## Existing cable can potentially carry STROBE to PA0

The P-board schematic netlist connects sensor `GPIO0_S` to U1's A port, sensor `GPIO1_S` to U1 DIR, and U1's B port to FFC J1 pin 5. The cable mapping inferred from the matching power, I2C and reset nets reaches Nucleo CN6 pin 18, MCU **PA0**. The firmware calls this `EN_CAM`; that name does not prove it enables this adapter's rails. [P-board schematic, sheet2](https://www.st.com/resource/en/schematic_pack/steval-cam-m0i-schematic.pdf), [UM3417 Rev 4, table14](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf).

The published BOM fits U1, R1 and R4; R12/R16 are absent. Combined with the schematic, R4 supplies the LDO enable from P3V3 and R1 selects P3V3 for the translator's B supply. This supports using PA0 as an input while the adapter remains powered. It is a schematic/BOM inference, pending the delivered-board signal test. [P-board BOM](https://www.st.com/resource/en/bill_of_materials/steval-cam-m0i-bom.pdf).

U1 is a 74LVC1T45: **DIR high means A to B**, so sensor GPIO1 must output high to send sensor GPIO0 toward the MCU. [Nexperia](https://www.nexperia.cn/product/74LVC1T45GF).

Proposed qualification sequence:

1. Make MCU PA0 an input before enabling any sensor output. Keep it an input for the whole test; do not call a middleware power routine that changes it back to an output.
2. Initially keep sensor GPIO0 an input. Configure GPIO1 as output high (`0x0468=0x15`) to select sensor-to-host translation.
3. Test sensor GPIO0 fixed low (`0x0467=0x05`) and fixed high (`0x0467=0x15`), observing PA0. On CCA use the documented GPIO_UPDATE command while in standby and wait for ACK. If outputs remain inactive in standby, repeat this diagnostic with controlled streaming; do not call the net faulty merely because standby outputs are inactive.
4. Use bounded waits, retain all register readbacks and PA0 observations. Never attempt a standby-only command while streaming. If the route is unproven, capture data and CSI timings can still be useful, but exposure must remain explicitly unqualified.
5. Configure GPIO0 STROBE, GPIO1 high, zero offsets, and apply the final configuration before the first stream start. The pinned driver's `VD6G_Boot()` writes `config_save.gpio_ctrl[]` through `VD6G_Gpios()` during initialization, so apply the test settings after `VD6G_Init()` has completed. `VD6G_Start()` does not rewrite the GPIO configuration in this revision. Recheck the call sites when changing driver versions.
6. Arm PA0 rising/falling edge capture before START_STREAM. Timestamp the input event and immediately mirror it to PE0 or record its event among externally visible phase edges. Make the ISR short; do not perform I2C or print from it.

The translator and firmware mirror add latency. A firmware-observed edge is an **upper bound** on the physical sensor edge until interrupt latency is bounded. Record priority, interrupt masking and any higher-priority handlers. If polling, preserve the longest interval between polls. The existing 6.25 MS/s LP8 contributes 0.16 µs sample quantization, usually far below software uncertainty. The mirrored route avoids treating an unverified 1.8 V sensor signal as a 3.3 V logic input on the analyzer.

If the cable route cannot be qualified, the P-board exposes GPIO2 through J3 and J4, and GPIO3/4/5 at TP2/3/4. J3 is not populated in the BOM. A direct additional probe would require checking the actual pad and sensor voltage threshold first; it is a fallback, not a prerequisite for continuing software optimization. [P-board schematic, sheets2–3](https://www.st.com/resource/en/schematic_pack/steval-cam-m0i-schematic.pdf), [BOM](https://www.st.com/resource/en/bill_of_materials/steval-cam-m0i-bom.pdf).

## Prove the first frame contains the LED panel

Use manual exposure and unity gain before streaming. Retain the first complete hardware snapshot; do not discard settling frames for the timing result. Reduced-resolution images can be an early diagnostic, but the accepted winner must retain the selected sensor mode and image-quality requirements. A shorter exposure can speed completion without advancing its start, so plot those quantities separately.

For each candidate, retain:

- Cold-start rail discharge and restoration, NRST release, first CPU marker, sensor command boundaries, integration edges, receiver start and completed-frame event.
- Sensor identity/revision, exact image dimensions and format, programmed and applied exposure/gain, relevant state/error registers, CSI/DCMIPP errors and frame counters.
- A frozen frame buffer with byte count, min/max, sum, firmware checksum and host SHA-256; verify host checksum equals firmware checksum before interpreting it.
- An unenhanced preview and a visual check that the expected LED pattern is discernible. A nonzero min/max range alone also accepts noise, corrupt DMA or stale RAM, so it is not the success criterion.

Keep the snapshot DMA stopped while retrieving the buffer through bounded HOTPLUG AP1 RAM reads. Read the diagnostic header first and derive the frame address/length from a validated manifest and header, not an arbitrary address. Use `-u <RAM address> <length> <output file>` without an external NOR loader. No reset is needed to retrieve a completed frame. If D-cache is enabled, ensure DMA/CPU coherency before computing the firmware checksum; the host reads physical SRAM. Retain the original bring-up path unchanged as a known image reference.

The pinned exposure helper truncates line time to integer microseconds before dividing the requested exposure. At a 1236-cycle line and 160.8 MHz pixel clock, the line is approximately 7.68657 µs, so its 10,000 µs request becomes 1428 lines (approximately 10.977 ms), rather than exactly 10 ms. Use a direct documented line count and read applied exposure for precise comparisons. This is source analysis, not a measured pulse width. See `VD6G_GetLineTimeInUs()` and `VD6G_SetExposureTime()` in the pinned driver; record the exact version used by the experiment.

## Phase timing without changing probe wiring

Use PD0 for the earliest CPU marker. Use PE0 edges for short event boundaries and retain an ordered RAM table of event ID, raw cycle count, HAL tick, clock epoch and error/status snapshot. Correlate RAM event order with Saleae transitions after the run. Do not serialize text or a diagnostic packet stream before exposure: their transmission would become part of the path being optimized.

DWT counts processor cycles, not elapsed time across clock changes. Either use an independently verified fixed-frequency timer or record every clock change and integrate each interval at its actual frequency. A `SystemCoreClock` value written after switching clocks cannot reconstruct the earlier mixed-frequency interval. External phase-edge timestamps are the reference for those intervals. Event logging should be short, bounded and measured; retaining a diagnostic baseline separately from a minimally instrumented final image reveals observer overhead.

The existing delayed PD0 packet format can export diagnostics if debugger access fails, but transmit only after the image is frozen and the timing measurement is complete. Preserve post-capture debug access and keep the maintenance helper memory regions separate from the frame/trace data.

## A defensible stopping decision

The request's confidence threshold concerns remaining optimization headroom, not merely repeatability. A stable result does not establish a global optimum. Define the scope as this delivered board/sensor revision, reversible software changes, no OTP changes, and the required image mode.

Build a critical-path ledger from measured phase boundaries. For each phase, retain its fastest qualified observation, mandatory hardware dependency, best supported minimum and uncertainty. Overlappable work belongs in parallel branches: add only serial dependencies. Include ROM startup, necessary payload loading, sensor readiness/boot/calibration, indispensable register traffic, and stream-to-integration latency. An unmeasured large phase remains an open optimization opportunity.

Let `L` be a defensible lower bound on achievable reset-to-exposure time and `T` the qualified result including timing uncertainty. A conservative interpretation of the requested 10% headroom is **`T <= 1.10 × L`**. Do not use the fastest observed complete run itself as `L`; that would assume the conclusion. If an undocumented sensor wait dominates, sweep it, retain the failure boundary, and distinguish a part-specific empirical bound from a datasheet guarantee.

For the final candidate, repeat independent, fully discharged cold starts and alternate it with a known baseline to detect drift. Confirm real first-frame images at the winner and at the boundary settings; do not count faster corrupt captures as successes. Twenty-two all-passing independent trials give a one-sided 90% binomial lower confidence bound just above 90% for per-run success (`0.1^(1/22)`), under the identical-trial assumption. This is a useful minimum reliability check, **not** 90% confidence of optimality or a production worst-case qualification. Temperature, supply and unit coverage remain separate.

Stop only after the remaining credible improvements together are below the allowed headroom, or identify the specific external evidence/action needed to resolve a genuine blocker. Report an engineering confidence judgment honestly; do not manufacture a numerical probability from a few timings.

## Offline event correlation

`analyze.py` correlates a saved six-channel Saleae digital CSV with the ordered events in `capture-result.json`. It does not access any hardware. For an autonomous cold start:

```text
python firmware/capture-timing/analyze.py path/to/digital.csv --result path/to/capture-result.json --out path/to/event-analysis.json
```

Cold mode requires exactly one NRST rising edge in the selected time interval and exactly one subsequent PD0 rising edge. Use `--after-s` and `--before-s` to select one complete run from a longer recording. PE0 is a toggle for **every** event; it is not a latched completion signal. The analyzer requires an exact one-to-one match between transitions and RAM events, beginning with a rise from the initialized low state, and refuses missing or extra edges.

RAM launches can begin with PD0 already high. Use `--mode ram --after-s <time-before-launch>` in that case. At most one initial PE0 falling edge is discarded as initialization. Such a run has no autonomous reset-to-capture measurement. DWT intervals are converted only after the clock-ready event and while adjacent recorded frequencies agree; later clock changes still require explicit additional instrumentation if introduced.

The output labels PA0 pulses and reports their observed widths. It deliberately leaves exposure qualification false: the script cannot prove the physical route, correct sensor strobe settings, first-frame association, interrupt latency, or visual LED-panel content. Those are separate evidence requirements above. Eight offline tests cover odd/even toggle counts, missing/extra edges, ambiguous resets, RAM launch anchoring, startup clock changes, nominal-clock disagreement, strobe pairing/error reporting, and CSV initial-state handling. See [the CSI and first-strobe investigation](csi-startup-errors.md) for the subsequent v3/v5 observations.

## RAM bench runner review, October 17

The initial `bench.py` uses bounded HOTPLUG AP1 operations, verifies the immutable cache helper and payload hashes, checks the expected ROM clock state and privileged thread mode, and writes internal RAM rather than NOR. The reviewed v2 payload ends below the cache helper at `0x34190000`; the frame buffer ends below the code/stack region. The observed v2 loss of AP1 visibility occurred after payload startup, with cache preparation reporting both caches off. No memory overlap in those regions explains that failure. Stop-stage builds are needed to isolate the transition that loses access.

Recommended hardening, sent to the bench owner before further timing claims:

- Clear the cache-helper status before each launch and verify actual cache state after execution. Otherwise a retained `CACH` result can appear to prove a helper invocation that did not run.
- Clear the capture trace before launching a new payload. A retained completed trace must not be attributed to a new build. A target build identity or run nonce is preferable when independently reading an already-running image; the host-supplied build hash alone proves no such association.
- Validate the entry point and initial stack against the binary vectors and reserved RAM bounds before writes. The build script validates its output, but the runner should not treat a matching payload hash as validation of every manifest field.
- Treat a retrieved image with a matching checksum separately from a qualified capture. Nonzero camera/receiver errors and unexpected frame counters require investigation even if the firmware reached stage 40.
- The polling timeout is not a global operation deadline: each debugger subprocess and the later full-frame retrieval have their own bounds. Preserve those bounds and describe them accurately.
- Never infer elapsed startup time merely because two adjacent `SystemCoreClock` fields match. Before the clock-ready event, the C startup value can differ from the ROM's actual clock and the interval can cross several frequencies.

These are an offline review of the initial runner, not a claim that any subsequent version still contains the same gaps. The bench owner controls fixes and hardware verification.
