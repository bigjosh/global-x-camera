# SD transport decisions

## 2026-10-20  Use final DATAEND and idle state rather than waiting for DBCKEND

**Why:** the original native read helper received all bytes without data errors but falsely timed out waiting for `DBCKEND` and a post-transfer FIFO condition. On this controller, `DATAEND` identifies final completion while `DBCKEND` describes nonfinal suspension. Completion must combine the correct terminal flag, idle data state, expected word count and absence of errors.
**Rejected:** requiring the nonfinal flag after a completed transfer or interpreting that software timeout as card corruption.
**Evidence:** commit `6224f912`; [v2 failure/v3 correction](../sd-smoke/README.md); `sd_card.c` final transfer checks.
**Provenance:** migrated 2026-10-24 from the measured read-only helper correction and its retained driver invariant.

## 2026-10-20  Fill the N6 transmit FIFO far enough to start a multiblock write

**Why:** the first format stalled after 144 words because a refill policy treated `TXFIFOHE` as only a 16-word opportunity. The N6 has a 256-word FIFO, and its selected `BUSSPEED=0` startup waits for a full FIFO or all remaining bytes. Bounded 128-word refill bursts and explicit cleanup corrected this; the failed operation was not retroactively called idle.
**Rejected:** reusing the smaller FIFO assumption; treating card READY alone as proof that the host data state machine had stopped.
**Evidence:** commit `5fd94243`; [initial failure and correction](../../docs/decisions/capture-png-sd-2026-10-20.md#first-format-failure-and-correction); `sd_card.c`.
**Provenance:** migrated 2026-10-24 from the hardware failure, register evidence and reference-manual review.

## 2026-10-20  Keep incomplete receive-abort cleanup failed closed

**Why:** the receive abort path drains at most 64 words even though this N6 FIFO holds 256. A read fault with more queued data can therefore leave `media_idle=0`; successful cleanup is not established merely because an abort was attempted. The unresolved case needs isolated qualification before changing the tested path.
**Rejected:** automatic reset/retry or treating a failed read report as permission to remove power; no proven general cleanup fix was selected.
**Evidence:** commit `5fd94243`; [recorded limitation](../capture-sd/README.md#verification-and-remaining-qualification); `sd_card.c` `abort_transfer()`.
**Provenance:** migrated 2026-10-24 from the explicit October 20 limitation, checked against the current source; it remains an open implementation constraint.

## 2026-10-24  Check the SDMMC configuration port as well as the DMA master security

**Why:** the first IDMA write reported success while every saved image byte was zero. The nonsecure SDMMC2 configuration port overrode the secure/privileged CID1 DMA-master setting, so protected SRAM reads did not yield the frame. Configuring and checking both attributes restored exact SD-to-camera-RAM equality without relaxing SRAM protection.
**Rejected:** checking only RIMC/master security; accepting controller success as image equality; making protected SRAM broadly accessible to hide the problem.
**Evidence:** commit `a0b8ce70`; [discovery](../../docs/decisions/raw-sd-slots-2026-10-24.md#discovery-sdmmc-dma-security); [failed zeros and corrected readback](../capture-raw/evidence/2026-10-24-raw-slots/README.md).
**Provenance:** migrated 2026-10-24 from full image readbacks and RIF diagnostics.

## 2026-10-24  Announce the complete owned extent but still explicitly terminate CMD25

**Why:** the user requested exact-count ACMD23 preparation and one multiblock image write to reduce transaction overhead. `CMD55`/`ACMD23` is a preparation hint, unlike fixed-count CMD23; success still requires CMD12 and fresh card/controller readiness. The whole-image API therefore owns the complete destination extent and never silently splits it or retries an unsupported hint.
**Rejected:** using the announcement as an automatic stop or physical NAND reservation; considering DATAEND alone sufficient; silently falling back after an announcement failure. Announced but unwritten sectors can become undefined on failure.
**Evidence:** commit `b1f7c89b`; [driver contract](README.md#opt-in-whole-transaction-with-preannouncement); [same-experiment comparison and confounders](../capture-raw/evidence/2026-10-24-preerase/README.md).
**Provenance:** migrated 2026-10-24 from the explicit experiment request, protocol review and measured implementation.

## 2026-10-24  Use PIO hardware flow control while a single write waits for its producer

**Why:** longer exposures can leave an incomplete image when SD is ready. In the selected cycle-aligned one-bit configuration, PIO with `HWFC_EN` can pause the SD clock when its TX FIFO empties and resume the same CMD25 as complete immutable sectors appear. A fully published object still uses IDMA. An unavailable IDMA linked-list node instead raises an error and disables flow control; it is not a wait queue.
**Rejected:** feeding unpublished memory; using a clear ABR bit as producer backpressure; toggling IDMA ownership mid-transfer; issuing a new CMD25 for every arriving chunk.
**Evidence:** commit `14d05d9a`; [progressive transfer contract](README.md#progressive-publication-within-one-multiblock-write); [long-exposure qualification and starvation limit](../capture-raw/evidence/2026-10-24-magic-slots/README.md).
**Provenance:** migrated 2026-10-24 from the manual-backed design and qualified before-FRAME write. Prolonged physical FIFO starvation was modeled, not established by that hardware run.

## 2026-10-24  Recheck the producer deadline after a callback returns

**Why:** camera STOP/I2C fault handling can spend seconds inside a progress/publication callback despite its normal short-service target. Checking the streaming timeout only before that call could accept a late prefix, launch IDMA or send additional FIFO data after the deadline. The revised driver checks again immediately afterward and returns through bounded CMD12/idle cleanup if a transaction is active.
**Rejected:** assuming every callback meets its nominal 50 ms service target, parking inside it, or treating a returned prefix as timely without another clock check.
**Evidence:** commit `14d05d9a`; [callback timing contract](README.md#progressive-publication-within-one-multiblock-write); `test_sd_driver.cpp` simulated 3.1-second callbacks before CMD25 and during an active write.
**Provenance:** migrated 2026-10-24 from the integration audit and actual-driver model tests; this correction is not a new hardware fault-injection result.

## 2026-10-24  Configure the hardware busy timer for whole-card erase

**Why:** CMD38 inherited the preceding SCR read's two-second timer at 25 MHz. Even after the card reported READY and DAT0 high, the host retained timeout/busy state; a longer software loop could not clear it. Explicit erase now selects 100 kHz and a hardware timer exceeding the requested software deadline, restoring the prior settings only after fresh idle proof.
**Rejected:** diagnosing the 600-second software timeout as a ten-minute physical erase; merely polling longer, blind reset/re-erase, or restoring fast clocks while ownership is uncertain. Ordinary erase is not secure sanitization.
**Evidence:** commit `14d05d9a`; [R1b constraint and corrected operation](README.md#scr-and-explicit-whole-card-erase); [failed erase, bounded recovery and sampled verification](../capture-raw/evidence/2026-10-24-magic-slots/README.md).
**Provenance:** migrated 2026-10-24 from preserved failure/recovery records and the corrected hardware test.

## 2026-10-24  Negotiate four-bit mode explicitly and keep historical builds one-bit

**Why:** the replacement carrier exposes DAT1/DAT2/DAT3, and the user requested a four-bit comparison against the completed one-bit SanDisk baseline. Host width alone cannot change the card's transfer protocol. The opt-in build first reads SCR in one-bit mode, validates capability, obtains CMD55/ACMD6(2) acknowledgments, then changes the idle host to four bits and proves readiness. Separate bounded telemetry preserves the existing card-status ABI and records which steps completed.
**Rejected:** silently enabling four-bit mode in historical builds; merely setting host WIDBUS; falling back after an ambiguous ACMD6 response; changing SD clock, voltage or high-speed mode at the same time. Erase and streaming checks must preserve the selected width instead of resetting it to one bit. A successful software model does not qualify the physical wiring.
**Evidence:** `sd_card.c` initialization, width telemetry, erase and streaming guards; `test_sd_driver.cpp` actual-driver model for both widths, including failed negotiation and deinit/CMD0/reinitialization; [build and pin contract](README.md#explicit-four-bit-build). Hardware results belong in the capture evidence, separately from these offline checks.
**Provenance:** recorded during the user-authorized replacement-carrier bring-up; the earlier one-bit choice remains the default when `SD_BUS_WIDTH` is omitted.

## 2026-10-24  Test GPIO slew separately from SD clock and compensation

**Why:** the replacement carrier's 25 MHz four-bit reads succeeded while its first progressive write failed with a CRC-status error; the subsequent 12.5 MHz pattern write and full readback passed. DS14791 Rev10 Table93 characterizes 25 MHz SDMMC with OSPEEDR `00`. An explicit RAM-only speed-zero build tests all six driven SD pins together while retaining 25 MHz, the same transport and unchanged compensation. A separate SRAM proof captures the applied masks and before/after register values without requiring later reads of potentially gated peripherals.
**Rejected:** silently changing historical/default builds, altering clock and slew together, assuming a slower edge always improves the actual wiring, or folding the ES0620 compensation erratum into the same experiment. Frozen startup has no explicit VDDIO5CCCR workaround, and the inherited ROM setting was not established by this source review. The diagnostic leaves it untouched.
**Evidence:** `SD_GPIO_SPEED`, `sd_gpio_proof`, actual-driver register-model tests and `capture-raw/test_sd_gpio.py`; private `tmp/bringup/sd-fourbit-20261024/ram-pattern25-slew0-v21/` and matching long-exposure build. Hardware outcomes belong to the owning four-bit experiment record.
**Provenance:** recorded during the root-owned replacement-carrier qualification; 12.5 MHz full equality was reported by the bench owner, and the speed-zero candidate had not been executed when this entry was added.

## 2026-10-24  Test fixed VDDIO5 compensation only after proving its access prerequisites

**Why:** the separate 25 MHz speed-zero trial failed its first header read, while a 12.5 MHz speed-three pattern write/readback passed. ES0620 sections 2.2.19–2.2.20 identify unsafe VDDIO5 compensation access without valid supplies and a fixed-code workaround for output-edge distortion. A final isolated 25 MHz, speed-three RAM trial writes only the secure VDDIO5CCCR `0x287`, after proving PWR clock, existing SV3, enabled SV5, SYSCFG clock and reset state. The separately recorded clock enable is part of this experiment's state change.
**Rejected:** combining clock, slew and compensation changes, inventing missing SV3, reading an unclocked register, enabling automatic compensation, assuming the ROM left the reset code, or promoting the diagnostic to flash before hardware qualification.
**Evidence:** `sd_card.c` guarded compensation path; `test_sd_driver.cpp` actual-driver mock rejects each missing gate and refused write; `capture-raw/test_sd_compensation.py` manifest/telemetry validation; private `ram-pattern25-comp-v22` and `ram-long25-comp-v22` frozen builds. The unchanged default rebuild is byte-identical to `ram-pattern-v19b`; hardware outcomes belong in the owning capture evidence.
**Provenance:** recorded during the user-authorized carrier qualification. No successful compensation hardware result was known when this entry was added.

## 2026-10-25  Do not treat driver timing counters as isolated card programming time

**Why:** `transfer_cycles` covers the SDMMC data phase, including hardware-managed per-block busy/stalls, not only payload clocking. IDMA `write_cycles` surrounds readiness, setup, transfer, CMD12 and final readiness, whereas progressive PIO's counter equals its timed data phase. `ready_cycles` accumulates CMD13 loops from multiple operations, including initialization, reads, writes, sync and deinit. Card-internal programming can overlap later data reception and is not separately observable in these fields. The three v23 Standby cycles retained external markers but lost the SRAM counters.
**Rejected:** subtracting `ready_cycles` from `write_cycles` to claim wire time, adding them as disjoint intervals, comparing PIO/IDMA counters as identical boundaries, or calling the approximately 21.76 ms nonpayload residual pure NAND-programming delay. Exact exposed busy needs separate DAT0-aware observation; internal programming overlap remains distinct.
**Evidence:** `sd_card.c` functions `ready`, `transfer_dma_write`, `write_dma_common` and `sd_write_blocks_stream_preerase`; [12.5 MHz budget](../capture-raw/README.md#write-time-budget-at-125-mhz); [three-cycle measurements](../capture-raw/evidence/2026-10-25-sd-fourbit/README.md). Budget arithmetic uses 1,909,760 bytes and the configured four-bit/12.5 MHz bus; no new hardware operation was performed.

**Evidence reference correction:** the IDMA wrapper's actual name is `dma_request`; `write_dma_common` above is an incorrect label. The counter-boundary reasoning is unchanged.
