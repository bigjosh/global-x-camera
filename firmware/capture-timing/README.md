# Reset-to-first-exposure investigation

This directory records the October 17, 2026 work on NUCLEO-N657X0-Q with CAM-6G3-073CLR, sensor revision 0x3110. The target is the **first exposure after a discharged cold start**, measured from the external MCU NRST rising edge. These experiments do not measure a complete take/save/shutdown product cycle.

Start with [the last instrument-qualified lane-sequencing result](../../reports/Camera%20lane%20startup%20mismatch.md): guarded v41 releases lane 0 early and holds only lane 1 in ForceRx until observed data Stop plus a 100 µs guard. It avoids startup and sensor-stop CSI errors while preserving exposure timing and the first physical image; minimum-exposure arm-to-VSYNC margin increased from 51.36 µs to 546.08–548.16 µs. The [earlier optimization results](optimization-results-2026-10-17.md) established native RAW10 exposure in **23.324–24.013 ms** before this integration. Supporting details are in [the experiment ledger](experiments.md), [exposure measurement method](exposure-measurement.md), and [native RAW10 memory layout](raw10-relocation.md). Exact build manifests, source snapshots, digital traces, numeric results and separate visual-review assertions are in [evidence](evidence). Original images, analog traces, Saleae recordings and NOR backups remain local under `tmp/bringup` and `hardware/local-backups`.

## October 20 checkpoint — VCP recovery installed; SD read smoke passed

The [v45b PE6 recovery update](recovery_vcp/README.md) is installed and fully
readback-verified. Repeated `0xC0` bytes at 1 Mbaud selected the exact early
debug park after a cold power cycle and after warm reset; read-only NOR INFO
also passed from recovery. Initial warm attempts failed, so recovery is
verified in these observed states, not guaranteed for every state. The v44
receiver is unchanged. Normal capture/sleep and total startup timing have not
been requalified. The guard keeps its 100 us deadline but increases ROM load
size by 480 bytes.

The native one-bit [SD smoke helper v3](../sd-smoke/README.md) passed two reads
at 100 kHz and a subsequent six-read check across 100 kHz, 12.5 MHz and 25 MHz.
The data matched byte-for-byte with no data CRC errors. Three early CMD8
timeouts persisted through the first wiring correction; a second correction
allowed card identification. V3 fixes v2's false completion timeout by requiring
DATAEND, idle state, all 128 words and no errors, without requiring DBCKEND.
The card reports 62,723,719,168 bytes (62.723719168 GB), which has not been
validated as usable capacity. No SD writes or erases were attempted, and write
throughput, complete-save performance and energy remain unmeasured.

The target remains powered at the helper's verified awake park, `0x341E05E4`.
The JS110 helper closed cleanly with its starting range 128 restored; VCP BREAK
is released and COM8 closed. CH0/NRST and CH6/PE6 are the only confirmed probes;
CH1–5 have no newly confirmed locations. No further probe move is needed for the
completed smoke test. Re-enter verified prefix recovery before another helper.
The October 18 stopped-bench/supply checkpoint below is historical.

## October 18 checkpoint — v44 installed, LEDs confirmed by user

The [v44 phase-LED/shallow-sleep update](status_leds/README.md) is **programmed**, with complete 65,536-byte NOR readback matching SHA-256 a325b36ed6d3f893ebe0d1153f476fd06fc51c648a1fe55aac15d353c959b4d8. Local proof: tmp/bringup/status-leds-v44-program-20261018/write/verified.json. The user subsequently reported **“LEDs working great”** and is continuing board modifications. This is visual user confirmation, not an instrumented capture, sleep or recovery qualification. V41 remains the last instrument-qualified capture/recovery image.

The latest confirmed supply is CN8 directly through a CN9 shunt, with JS110 no longer inline. PE1 sampled HIGH while OUT0 was retained LOW, and all six Saleae channels read near zero while the debugger reported about 3.28 V at the target. These observations do not establish working recovery selection, timing probes or automated power control.

Before the user's visual confirmation, MCU-only reset reached the exact v44 prefix failure S1ER17 at sensor phase 2, waiting for state 0x0028 == 1 before receiver loading. This inherited path is cold-start-only. GPIOG's masked LED value was 0x101, matching red on with blue/green off. From that checked terminal state, a controlled PO5 sensor-reset write took effect (ODR/IDR confirmed low) despite the CLI's write-only BSRR readback error. After MCU reset, AP1 could not read the core ID. A later default-AP0 hardware reset pulse succeeded; subsequent AP1 access still failed and probe availability later changed. No DEV_USB_COMM_ERR was reported. Cause is unestablished; these observations do not prove the CPU reached WFI or that sleep caused the access loss.

**Bench work is stopped while the user modifies the board.** Recheck ownership, supply route, shared ground, recovery diode and probes before further operations. Instrumented v44 capture integrity, LED timing, actual CPU sleep, intended debug retention and PE1 recovery remain pending. Do not infer what power/reset action preceded the user's visual confirmation.

## Current architecture

The sensor begins its natural cold startup while the STM32 ROM runs. A small, ROM-loaded first stage checks the expected hardware state, configures the sensor and issues START. It then loads and CRC-checks the receiver code while the sensor transitions to streaming. The receiver enables clock and data modules early, releases lane 0 immediately after PHY digital reset, and retains ForceRx only on lane 1. After both data Stop flags remain observed for 40000 nominal cycles, it releases lane 1 and arms the first-frame snapshot. START acknowledgement and STREAMING verification follow arming. This hides the receiver load inside sensor startup and removes I²C polling from the readiness gate. Clock-active is checked in the recorded evidence; the firmware does not wait on ACTCLF.

The test retains the ROM clock profile, precomputed I2C timing, bounded readiness polling, manual unity gains, native resolution and all captured error history. It avoids redundant sensor resets, generic clock initialization and unnecessary critical-path register transactions. Qualified v41 kept the debug port accessible after capture. V44 intends to retain debugging in shallow sleep; instrumented confirmation remains pending.

The no-reset policy is qualified only for the observed discharged cold cycle. It is not a general warm-reset recovery procedure. Camera rail/oscillator/XSHUTDOWN sequencing still needs direct electrical qualification. The current startup sequence preserves clock acquisition while holding lane 1 in receive/wait-for-Stop mode; after capture it retains v36's idle data-module shutdown before sensor STOP. The first-readout margin and Stop-state semantics need production corner qualification. Holding both lanes through the same 100 µs dwell failed to receive any frame, despite zero recorded PHY errors. This establishes a working receiver sequence, not the exact sensor electrical transition or general link compliance.

The follow-up [lane-startup investigation](../../reports/Camera%20lane%20startup%20mismatch.md) separates sensor firmware readiness, receiver clock acquisition and data-lane state tracking. Its [earlier isolated diagnostic builds](late_phy/README.md), [v35/v36 integration](fast_phy/README.md), and [current readiness experiments](ready_phy/README.md) preserve raw PHY history. Second-trigger experiments are explicitly excluded from first-frame latency claims; completed captures and quiet error flags must be considered separately. Current qualification requires first-STROBE association, complete image integrity and raw error checks through startup, frame and shutdown.

The [early GPIO recovery guard](recovery_gpio/README.md), introduced and qualified in v34c and preserved through v41, adds PE1/CN15.24 as a default-normal, internally pulled-up recovery input before camera or additional NOR loading. Normal capture, externally requested recovery and actual flash reprogramming from early recovery passed on October 17. With the user's diode, use the JS110 shared GPIO supply at 3300 mV and OUT0 high for normal boot or low for recovery. Supply-off did not reliably release the pin. Preserve this guard in all subsequent experimental images; detailed checks and provenance are in the [original qualification evidence](evidence/2026-10-17-diode-recovery-smoke/guard-qualification/qualification-summary.json) and [current integration evidence](evidence/2026-10-17-receiver-ready/README.md).

## Bench ownership and reversible maintenance

Only one controller may use the physical instruments or debugger. Follow the repository [instrument instructions](../../AGENTS.md). The October 17 qualified route was CN8 USB through CN9 pin 3, JS110 IN+/OUT+, then CN9 pin 2, with CN9 shunts absent. The latest October 18 setup instead bypasses JS110 through a CN9 shunt, and the user is modifying the board. Recheck wiring and ownership before tests; leave the working flash-boot jumper position unchanged. PE1 recovery and timing probes require renewed verification. Saleae and Joulescope are controlled through APIs.

`cold_experiment.py` records a physical off/on cycle, validates discharge/restoration of all three probed rails, retrieves the completed image, checks byte integrity, and correlates every PE0 event. Correlation begins inside the measured discharged interval so threshold bounce during the preceding power-down cannot be mistaken for a boot. No debugger traffic occurs during the boot/capture interval.

`variant_cycle.py` accepts the exact currently programmed first-64-KiB image and an immutable candidate manifest. It abandons only a completed capture into a checked maintenance context, runs the frozen NOR helper's read-only INFO check, programs and verifies the candidate, then conducts the cold experiment. Any failed stage stops the sequence. Never reset, halt or power-cycle an unfinished flash operation.

RAW10 capture relocates live code, stack and diagnostics above the full 3,055,360-byte frame. Subsequent maintenance must use `--current-layout raw10`; its cache helper is at 0x343C0000. RAW8 maintenance uses 0x341A0000. The frozen NOR helper subsequently overwrites part of the old frame buffer, so retrieve the image first. Read the [maintenance review](maintenance-review.md) and [RAW10 layout](raw10-relocation.md) before modifying this workflow.

## Builds and interpretation

Builders are offline and pin the vendor source revision and exact input hashes. [Build notes](build-notes.md) describe the local toolchain and experiment flags. RAW10 builds derive from a checked receiver/prefix pair; arbitrary source-directory substitutions are rejected. Build-time `hardware_status: untested` fields remain unchanged: later capture records establish which exact image was actually exercised.

External timestamps are authoritative. Nominal-clock DWT conversions differ slightly from measured time on this unit. STROBE is observed through an interrupt mirror; a separate [hardware timer cross-check](timer-probe.md) bounded the observed mirror delay to about 4.1 µs in that run. Its independent clock calibration and limits are recorded with the result. First exposure, first received frame and post-frame checksum completion are separate events. Frame readback/PNG conversion and diagnostic work after capture do not belong in the exposure-start budget.

The offline analyzer and ledger tests can be run with `python -m unittest discover -s firmware/capture-timing -p "test_*.py"`. They validate event association and reporting, not hardware behavior. Hardware evidence and first-frame visual checks are required for each timing claim.
