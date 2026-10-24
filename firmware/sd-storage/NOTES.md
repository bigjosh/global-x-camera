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
