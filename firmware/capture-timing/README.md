# Reset-to-first-exposure investigation

This directory records the October 17, 2026 work on NUCLEO-N657X0-Q with CAM-6G3-073CLR, sensor revision 0x3110. The target is the **first exposure after a discharged cold start**, measured from the external MCU NRST rising edge. These experiments do not measure a complete take/save/shutdown product cycle.

Start with [the final optimization results](optimization-results-2026-10-17.md): five native RAW10 cold starts reached first exposure in **23.324–24.013 ms**. Supporting details are in [the experiment ledger](experiments.md), [exposure measurement method](exposure-measurement.md), and [native RAW10 memory layout](raw10-relocation.md). Exact build manifests, source snapshots, digital traces, numeric results and separate visual-review assertions are in [evidence](evidence). Original images, analog traces, Saleae recordings and NOR backups remain local under `tmp/bringup` and `hardware/local-backups`.

## Current architecture

The sensor begins its natural cold startup while the STM32 ROM runs. A small, ROM-loaded first stage checks the expected hardware state, configures the sensor and issues START. It then loads and CRC-checks the receiver code while the sensor transitions to streaming. The receiver arms the first-frame snapshot before exposure begins. This hides the receiver load inside sensor startup instead of serializing the two operations.

The test retains the ROM clock profile, precomputed I2C timing, bounded readiness polling, manual unity gains, native resolution and all captured error history. It avoids redundant sensor resets, generic clock initialization and unnecessary critical-path register transactions. It keeps the debug port accessible after capture so firmware changes do not require boot-jumper changes.

The no-reset policy is qualified only for the observed discharged cold cycle. It is not a general warm-reset recovery procedure. Camera rail/oscillator/XSHUTDOWN sequencing still needs direct electrical qualification. The observed startup D-PHY state-sequence error remains an open qualification issue; a recognizable image is not evidence that every link condition is correct.

The follow-up [lane-startup investigation](../../reports/Camera%20lane%20startup%20mismatch.md) separates sensor firmware readiness, receiver clock acquisition and data-lane state tracking. Its [isolated diagnostic builds](late_phy/README.md) preserve raw PHY history. Second-trigger experiments are explicitly excluded from first-frame latency claims; completed captures and quiet error flags must be considered separately.

The installed [early GPIO recovery guard](recovery_gpio/README.md), revision v34c, adds PE1/CN15.24 as a default-normal, internally pulled-up recovery input before camera or additional NOR loading. Normal capture, externally requested recovery and actual flash reprogramming from early recovery passed on October 17. With the user's diode, use the JS110 shared GPIO supply at 3300 mV and OUT0 high for normal boot or low for recovery. Supply-off did not reliably release the pin. Preserve this guard in all subsequent experimental images; detailed checks and provenance are in the [qualification evidence](evidence/2026-10-17-diode-recovery-smoke/guard-qualification/qualification-summary.json).

## Bench ownership and reversible maintenance

Only one controller may use the physical instruments or debugger. Follow the repository [instrument instructions](../../AGENTS.md). Current power is CN8 USB → CN9 pin 3 → JS110 IN+ → OUT+ → CN9 pin 2, with CN9 shunts absent. The current BOOT jumper position demonstrably boots flash; leave it unchanged and select recovery through PE1. Saleae and Joulescope are controlled through APIs.

`cold_experiment.py` records a physical off/on cycle, validates discharge/restoration of all three probed rails, retrieves the completed image, checks byte integrity, and correlates every PE0 event. Correlation begins inside the measured discharged interval so threshold bounce during the preceding power-down cannot be mistaken for a boot. No debugger traffic occurs during the boot/capture interval.

`variant_cycle.py` accepts the exact currently programmed first-64-KiB image and an immutable candidate manifest. It abandons only a completed capture into a checked maintenance context, runs the frozen NOR helper's read-only INFO check, programs and verifies the candidate, then conducts the cold experiment. Any failed stage stops the sequence. Never reset, halt or power-cycle an unfinished flash operation.

RAW10 capture relocates live code, stack and diagnostics above the full 3,055,360-byte frame. Subsequent maintenance must use `--current-layout raw10`; its cache helper is at 0x343C0000. RAW8 maintenance uses 0x341A0000. The frozen NOR helper subsequently overwrites part of the old frame buffer, so retrieve the image first. Read the [maintenance review](maintenance-review.md) and [RAW10 layout](raw10-relocation.md) before modifying this workflow.

## Builds and interpretation

Builders are offline and pin the vendor source revision and exact input hashes. [Build notes](build-notes.md) describe the local toolchain and experiment flags. RAW10 builds derive from a checked receiver/prefix pair; arbitrary source-directory substitutions are rejected. Build-time `hardware_status: untested` fields remain unchanged: later capture records establish which exact image was actually exercised.

External timestamps are authoritative. Nominal-clock DWT conversions differ slightly from measured time on this unit. STROBE is observed through an interrupt mirror; a separate [hardware timer cross-check](timer-probe.md) bounded the observed mirror delay to about 4.1 µs in that run. Its independent clock calibration and limits are recorded with the result. First exposure, first received frame and post-frame checksum completion are separate events. Frame readback/PNG conversion and diagnostic work after capture do not belong in the exposure-start budget.

The offline analyzer and ledger tests can be run with `python -m unittest discover -s firmware/capture-timing -p "test_*.py"`. They validate event association and reporting, not hardware behavior. Hardware evidence and first-frame visual checks are required for each timing claim.
