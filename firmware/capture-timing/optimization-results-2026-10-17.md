# Cold-start capture optimization results

The selected native-resolution build is **v25**, with 1120 × 1364 RAW10 samples, manual unity gains, automatic dark calibration and the normal 804 Mbps camera-link setting. All five completed cold starts produced recognizable first images of the LED panel, with exposure starting **23.324–24.013 ms after MCU NRST release**. The first full image reached RAM in **45.182–45.871 ms** at the test exposure of approximately 10.984 ms.

The timing cross-check and final baseline restoration are complete. I judge the stopping criterion met: **approximately 90% engineering confidence that the achieved delay is within 10% of the minimum reachable through documented, reversible software on this delivered hardware**. This judgment applies to the Nucleo/module, current ROM/fuse configuration and discharged cold start. It does not cover warm-reset recovery or the final button-to-exposure power sequence.

## What changed

The important improvement was changing the order of work. The sensor's fitted reset pull-up lets it reach READY while the MCU runs its boot ROM. The first stage preserves that natural cold startup instead of resetting the sensor again. It sends the required BOOT/configuration/START commands, then copies and CRC-checks the receiver code while the sensor performs its internal START transition. The receiver is ready before the first exposure and captures the first complete frame.

Earlier software also spent substantial time calculating I2C timing, holding reset, polling on millisecond boundaries and configuring generic clocks. The harness now uses a checked precomputed bus timing value, fine bounded polling, the retained ROM clock tree, newest-silicon initialization, batched register transfers and a small size-optimized first stage. Inlining CRC makes the second-stage copy run at the 32 MHz NOR wire limit. Raising NOR speed would only shorten work already hidden by sensor startup.

The first native RAW10 test required relocating all live receiver code, vectors, stack and diagnostics above a **3,055,360-byte** padded image buffer. Each native capture checks the exact byte counter, an overflow canary, sensor format, valid ten-bit sample range, and matching MCU/host byte checksums. Images were separately inspected: checksums alone do not prove that the sensor saw the scene.

## Measured critical path

The best v25 run has this decomposition, using external Saleae timestamps:

| Phase | Duration | Implication |
| --- | ---: | --- |
| NRST release to first CPU marker | 15.698 ms | ROM startup and loading the small prefix dominate. |
| First CPU marker to completed sensor START write | 2.324 ms | Includes approximately 0.804 ms BOOT transition and required register traffic. |
| START write to first observed exposure strobe | 5.302 ms | Internal sensor transition; stable across the tested controls. |
| Total | **23.324 ms** | First exposure, not frame completion. |

The receiver is armed about **2.09 ms before the first strobe** in that run. Its code copy and setup are inside the final interval above and must not be added again. The post-frame diagnostic hash takes hundreds of milliseconds with this deliberately simple uncached harness; that is not exposure latency or a proposed production processing budget.

The five v25 exposure-start measurements were 23.89520, 23.32416, 24.01344, 23.83360 and 23.91440 ms. The latest run used the restored selected image, not the timer diagnostic. These are five observations on one unit, not a production reliability estimate.

### Independent timing cross-check

The separate TIM5 diagnostic latched the same sensor STROBE edges in hardware while retaining the external PE0 mirror. All four observed edges passed capture-validity and association checks, with no timer overcapture. The first edge-to-PE0 delay lay between **0.674 and 3.986 µs**; the largest upper bracket across all four edges was **4.101 µs**, rounded upward. This is negligible beside the millisecond-level optimization budget. It is an observed bracket relative to the timer's synchronized input, not a universal interrupt-latency or direct optical-onset guarantee.

Independent DWT/Saleae intervals showed a changing measured clock rate during startup despite unchanged nominal settings. A nearby non-strobe interval supplies the local conversion; all rate observations and an empirical allowance are preserved. The first measured hardware pulse was 10,983.945 µs versus 10,984.000 µs externally. The rejected long-interval calibration is retained as a diagnostic finding. See [the timer method and results](timer-probe.md).

## Attempts that did not improve the remaining sensor transition

Matched experiments changed coarse exposure, frame period, system-PLL divider/multiplier, pre-START settling time, I2C-triggered operation, dark calibration, continuous/noncontinuous link clock and link bitrate. The first START-to-strobe interval remained approximately **5.3 ms**. The higher-link-rate experiment requested 1000 Mbps and read back a multiplier/divider combination corresponding to 979.875 Mbps; it is not described as a separately measured physical lane frequency.

Disabling dark calibration raised the black pedestal without reducing startup. Reading temperature immediately after BOOT added approximately 1.837 ms and did not pre-activate anything that shortened START. Those settings were discarded. Two isolated receiver-PHY register corrections also failed to remove the existing startup state-sequence flag. All outcomes, including negative results, are retained in [the experiment ledger](experiments.md) and its linked immutable archives.

## Remaining headroom and confidence scope

The previous tiny-marker experiment and measured payload-size slope imply only about **0.93 ms** of potential load saving even under the unrealistic assumption that the current 4008-byte native prefix could shrink to a 372-byte marker that performs none of the sensor work or validation. The remaining host setup is already approximately 2.3 ms, including the required BOOT action and fast, batched I2C traffic. Plausible further host-side changes appear to save roughly 1–1.5 ms in total, including that deliberately generous prefix estimate.

Beating the current 23.324 ms result by enough to put it more than 10% above the achievable minimum would require saving approximately **2.12 ms**. A credible improvement of that size would therefore need to shorten the sensor's internal START transition or change the boot hardware/configuration. Public documentation provides no independent analog/PLL prestart action or BOOT bypass; the supported controls with plausible effects on that transition have now been exercised without a useful reduction.

This is an engineering argument about remaining optimization headroom, not a mathematical lower bound or a probability calculated from repeated successes. The sensor's internal firmware is opaque. Different hardware, retained power, another boot configuration, undocumented vendor facilities or a changed image-quality requirement could alter the result. The measurement cross-check and five successful native cold starts support stopping this software optimization pass; they do not establish a universal hardware limit.

## Qualification limits and installed state

- The startup D-PHY state-sequence error remains present. First-frame status and enabled CRC/ECC checks showed no CRC/ECC errors in the accepted captures, but this does not replace link robustness qualification.
- The no-reset strategy requires validating actual camera supplies, oscillator and XSHUTDOWN sequencing. The existing probes verify three board rails; they do not directly observe all camera rails.
- Cold-start variation, temperature, battery/regulator behavior and multiple units need later product testing. Reset-to-exposure success alone does not prove the agreed 50 ms **button-to-exposure** requirement.
- The experiment firmware stays awake with debug access after capture. It is a capture/timing harness, not the final NAND/PTP/shutdown firmware.

Original NOR contents remain backed up. No OTP, fuse, lifecycle or permanent board change was made. The final installed first 64 KiB is the selected v25 image, SHA-256 **`c43721b29f437546d3090632495f4527f4ba34d4af773a23214cdd86a0adb817`**, programmed and verified before the fifth cold start. Its local build is `tmp/bringup/capture-raw10-trim-os-v25-20261017`; the final capture is `tmp/bringup/capture-opt-v25-raw10-restore-05/cold`.

The JS110 controller exited normally and restored its original automatic range with the target powered. An independent 23.689-second Saleae capture spanning release showed the three monitored rails, NRST and the early CPU marker remained high. A subsequent read-only debugger connection succeeded and read the expected capture-trace magic. The board remains in normal flash boot with the selected firmware installed; no instrument session is left owned by the experiment scripts. See [the final bench-state record](evidence/2026-10-17-final-bench-state/README.md).
