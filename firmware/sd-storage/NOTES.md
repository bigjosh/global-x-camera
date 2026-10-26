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

## 2026-10-25  Isolate the SD transmit launch phase without changing identification timing

**Why:** the 25 MHz four-bit write CRC failures remain unexplained after the separate slew and compensation trials. RM0486 Rev4 page1433 defines `CLKCR.NEGEDGE` as a CMD/DAT launch-phase selection. A RAM-only diagnostic leaves 100 kHz identification unchanged, then selects bit16 only after both command/data state machines are idle. At the already validated 150 MHz kernel and 25 MHz bus, the alternative launches on the kernel rising edge that generates the SD clock's falling edge. Existing negotiated-width telemetry records the complete `CLKCR` value, bound to the compiler option and manifest.
**Rejected:** treating the option name as an input sampling-edge control, changing SELCLKRX/BUSSPEED or slew/compensation with it, promoting the diagnostic to flash/Standby without qualification, or claiming a phase mismatch caused the errors before measuring the wire transaction. Explicit erase must preserve the selected phase and progressive writes must reject a missing phase bit. Historical/default executable bytes remain unchanged.
**Evidence:** `SD_CLOCK_NEGEDGE`, `capture-raw/build.py --sd-clock-negedge`, exact `bench.py` width/phase binding, actual-driver register-model/ARM compile tests and `capture-raw/test_sd_phase.py`; private control/candidate builds in `tmp/bringup/sd25-crc-20261025/`. The option alone performs no hardware operation and establishes no reliability result.
**Provenance:** recorded while preparing the root-owned 25 MHz CRC investigation; hardware execution depends on its observed failure and remains separate evidence.

## 2026-10-25  Follow intermittent read CRC failures with separate intermediate GPIO-speed trials

**Why:** after added probes, the unchanged 25 MHz control and the NEGEDGE candidate both completed writes, but subsequent reads still reported intermittent data-CRC failures. A successful write therefore does not qualify this physical link. The next RAM-only comparison keeps four bits, 25 MHz, NEGEDGE and unchanged compensation, varying only GPIO OSPEEDR from speed3 to speed1 or speed2. Each nondefault build records the exact six-pin speed encoding and proves unrelated GPIO bits unchanged.
**Rejected:** treating probe-dependent success as a fixed connection, declaring phase selection a successful CRC fix, combining a new compensation setting with these trials, or allowing intermediate speeds into flash/Standby before qualification. The existing speed0 experiment and its history remain separate; original default and phase1/speed3 executables must rebuild identically.
**Evidence:** `sd_gpio_proof` generalized exact-encoding checks, actual-driver model/ARM compile coverage for speeds1/2, and `capture-raw/test_sd_gpio.py`; frozen control and follow-up candidates under `tmp/bringup/sd25-crc-20261025/`. Root owns the physical traces/read failures and their final evidence record; this implementation performs no hardware operation.
**Provenance:** recorded at the bench owner's request after the control/NEGEDGE write-pass and read-failure observations. No successful intermediate-speed result was known at implementation time.

## 2026-10-25  Qualify the physical SD link independently of a successful write or probe configuration

**Why:** sustained reads failed after successful 25 MHz writes with both launch phases. Failed traces align with original RAM after whole four-bit nibble omissions, and pre-resistor writes contain narrow observed clock pulses. Intermediate slew settings did not fix reads; even a later 12.5 MHz read failed with the expanded probe setup. After the user inserted 27 ohms midway along CLK, two full images read back exactly and a fresh full write had correct payloads, all lane CRCs and accepted card status. That supports a clock-integrity hypothesis without establishing the analog cause or general reliability.
**Rejected:** declaring NEGEDGE alone a fix, interpreting digital samples as an analog ringing measurement, assuming a single successful write establishes reliable reads, or promoting 25 MHz before removing SD probes and checking both transfer paths and cold cycles. The resistor was tested midway, not at the recommended source placement; CMD probe observability also changed, limiting single-variable attribution.
**Evidence:** [frozen signal analysis and checkpoint](../capture-raw/evidence/2026-10-25-sd25-crc/CHECKPOINT.md), including full original-RAM comparisons for slots3/4 and slot5 wire validation. Source defaults remain byte-identical; the installed v23 image remains 12.5 MHz at this checkpoint.
**Provenance:** recorded from root-owned measurements after the user's reported 27-ohm installation; hardware is paused for the requested probe removal and further qualification.

## 2026-10-25  Retain 25 MHz with the tested clock resistor after probe-free qualification

**Why:** removing all six SD signal probes did not reintroduce CRC errors with the 27-ohm midpoint CLK resistor, four-bit 25 MHz, NEGEDGE, GPIO speed3 and unchanged compensation. Retained-pattern, fresh-scene, long-exposure PIO and cold-flash IDMA images all matched original RAM. Three subsequent cold Standby cycles passed full image readback and attributed SBF checks, with median 419.518 ms / 229.913 mJ on the JS-fed board branch. This supersedes the preceding pending-qualification checkpoint and selects the explicit profile for the current prototype.
**Rejected:** relying on probe capacitance, calling NEGEDGE alone the fix, weakening CRC or ownership guards, claiming the digital traces prove analog ringing, or generalizing three cycles to production/PVT reliability. The actual resistor remains midway along the clock wire; preferred source-end placement is not the measured configuration. Source-RAM equality applies to the separate awake tests, not the three Standby frames whose original RAM was lost.
**Evidence:** [completed probe-free qualification](../capture-raw/evidence/2026-10-25-sd25-crc/QUALIFICATION.md), its sanitized readback/energy reports and exact installed sector/prefix hashes; [selected build](../capture-raw/README.md#installed-profile-four-bit-sdmmc2-at-25-mhz). Historical defaults and the separate RAM-only slew/compensation restrictions remain unchanged.
**Provenance:** recorded after the user confirmed probe removal and the root-owned hardware tests completed. The three-cycle comparison also changes probe loading, launch phase and allocation position relative to the earlier 12.5 MHz baseline; it is not a controlled frequency-only attribution.

## 2026-10-25  Measure SD boundaries with opt-in fixed RAM slots instead of logging inside transfer polls

**Why:** the user requested real step-boundary timestamps with minimal logging overhead. The diagnostic build writes DWT timestamps to fixed event slots and counts low-frequency repeats such as ACMD41 attempts. Initialization, selected-width negotiation, initial write readiness, preannouncement, CMD25 response, observed DATAEND, CMD12, final readiness and deinitialization have separate boundaries. No printf, allocation, shared append cursor or per-FIFO-word/per-poll logging enters the normal transfer path. Generic read/SCR/sync events retain only the latest call; their counters preserve call counts, while whole-init/write events remain independent.
**Rejected:** inferring card-internal programming time from these CPU-observed boundaries, treating DATAEND as isolated bus payload time, accepting a stale prior DONE timestamp older than a repeated call's new BEGIN, or adding instrumentation overhead to historical builds. Failed operations retain ownership/error semantics and do not receive successful completion stamps; the trace is diagnostic evidence, not permission to reset or halt an uncertain transfer.
**Evidence:** `sd_card.c` opt-in `RAW_CYCLE_TRACE` hooks; [event allocation](../capture-raw/cycle_trace_sd.h); `test_cycle_trace_driver.py` verifies initialization retry counts, read/init separation, IDMA/PIO command order and absent success markers after failures against the actual driver model. It also compares every allocatable ARM object section against pre-instrumentation revision `51c25de2` with tracing disabled. The existing eleven-test driver matrix and three new trace tests pass; hardware timings belong in the capture experiment record.
**Provenance:** recorded during the user-requested cycle instrumentation. This implementation and its offline checks do not establish physical timing, a reliability improvement or a changed storage protocol.

## 2026-10-26  Set the R1b timeout before selecting the card

**Why:** CMD7 can hold DAT0 busy during identification, before the first SCR or block transfer has initialized DTIMER. Its reset value is zero; a valid select-card busy interval can therefore latch a controller timeout even after the card becomes ready. The explicit `SD_REVIEW_PROFILE=1` path sets a two-second timer at the actual 100 kHz identification clock before issuing identification commands. Historical profiles keep their previous executable path for reproducible comparisons.
**Rejected:** assuming CMD7 never asserts busy because this card usually selects immediately; extending only the software readiness loop after a hardware timeout; weakening the final card/controller idle proof. New initialization must still fail closed on a busy interval that exceeds the bound.
**Evidence:** `sd_card.c` initialization and `test_sd_driver.cpp` CMD7 R1b model. The same short busy interval fails with the historical zero timer and succeeds with the reviewed timer; an excessive interval retains controller ownership and refuses initialized/idle status. Offline one-bit/four-bit models pass for both profiles. RM0486 Rev4 section30.6.6 specifies programming DATATIME before R1b commands. No new hardware qualification is implied.
**Provenance:** recorded during the user-authorized SD correctness/performance review following the 12.5 MHz launch-phase experiment.

## 2026-10-26  Drain the complete N6 receive FIFO during a bounded abort

**Why:** the prior 64-word receive-abort bound was smaller than this controller's 256-word FIFO and could leave an otherwise recoverable failed read owned and non-idle. The explicit `SD_REVIEW_PROFILE=1` path drains at most256 remaining words after CMD12 completes, then resets the FIFO only under the existing active-DPSM/no-IDMA conditions and proves card/controller readiness. This supersedes the unresolved64-word cleanup limit recorded on October20; the original operation remains failed.
**Rejected:** an unbounded drain, flushing unread data before the manual's prescribed receive-drain step, resetting the controller, releasing ownership on an incomplete abort, or applying a newly reviewed path to historical profiles silently.
**Evidence:** `sd_card.c` `abort_transfer()`; actual-driver model tails64/65/255/256/257 in `test_sd_driver.cpp`. Valid tails through256 drain and reach idle under the reviewed profile; the impossible257-word fault case stays non-idle with a length cleanup error and no FIFO reset. RM0486 Rev4 section30.6.2 requires reading remaining receive FIFO data before FIFORST. Offline model success is not hardware fault-injection qualification.
**Provenance:** recorded during the user-authorized SD correctness/performance review; legacy profile retains its64-word bound for exact prior-build reproduction.

## 2026-10-26  Give the reviewed 50 MHz SD experiment an exclusively owned 100 MHz kernel clock

**Why:** the existing150 MHz SD kernel cannot produce50 MHz with its integer divide-by-two clock divider; truncating150/(2*50) to1 would accidentally select75 MHz. The explicit High Speed/review profile instead temporarily owns unusedIC5, derives100 MHz from the existing1.2 GHz PLL1 divided by12, and selects it only forSDMMC2. It rejects an enabledIC5, any MCO1/PER/SDMMC1 selector referring toIC5, a nondefault priorSDMMC2 mux, an activeSDMMC2 host, or a changed source-clock profile. Rejecting PER also covers its downstream consumers, including peripherals currently disabled. All checks readRCC only, so they cannot accidentally access an unclocked peripheral.
**Rejected:** changing sharedCPU/HCLK/camera clocks, borrowing an already enabled divider, assuming peripheral-clock gates prove an unused mux, silently generating75 MHz, or disablingIC5 before returningSDMMC2 toHCLK. ES0620 Rev5 section2.2.22 requires SDMMC mux defaults before a software reset and live source clocks during the change. An uncertain release retains clock ownership and its cleanup error; it is not permission for a warm reset. The helper does not changeGPIO slew, compensation, or nativeSD timing phase.
**Evidence:** `sd_clock_profile.h` keeps both sources live during mux changes, restores the originalIC5 register, and bounds enable/disable polls to4096. `test_sd_clock_profile.py` executes the actual helper with write-order assertions and refused-write/source/consumer fault cases, and compiles it asARM C against pinnedCMSIS. RM0486 Rev4 Fig59, RCC_IC5CFGR and RCC_CCIPR8 define the divider and source selections. Root's read-onlyRCC snapshot `tmp/bringup/sd125-negedge-20261026/rcc-snapshot/registers.json` reportsIC5 disabled, no competing selector and the expectedPLL1/HCLK profile. Hardware qualification belongs in the owningcapture evidence; these offline tests establish no50 MHz electrical result.
**Provenance:** implemented during the user-authorized deepSD review; the root agent owns the bench and provided the saved liveRCC snapshot after completeSD/source-RAM equality verification.

## 2026-10-26  Finish CMD12 busy before reconfiguring the data path

**Why:** DATAEND proves the completed payload, but the subsequent CMD12 R1b response can put DPSM back into Busy. Clearing DCTRL immediately after the response changes DBLOCKSIZE/DTMODE/DTDIR while DPSMACT may still be set, contrary to RM0486 Rev4 p1440. The reviewed profile first proves card READY/TRAN, physical DAT0 high, inactive CPSM/DPSM and released IDMA, checks retained data/DMA error flags, and only then clears DCTRL and transfer status. A late error never increments successful sector counts.
**Rejected:** equating CMDREND with R1b completion; clearing a late timeout/CRC/DMA error as successful cleanup; treating the expected DABORT from deliberate CMD12 as an independent corruption indication after full DATAEND/count validation. Historical profile behavior remains available for exact prior-build comparisons.
**Evidence:** `ready_after_transfer()` and completion paths in `sd_card.c`; actual-driver model covers PIO, IDMA and progressive writes with short final busy, prolonged busy, and late DCRCFAIL/DTIMEOUT/IDMATE. The reviewed path makes no DCTRL configuration writes during busy and keeps failures failed; legacy models reproduce the early DCTRL write and cleared late errors. RM0486 section30.6.6 and Table220 distinguish response, busy and completion flags. These are offline tests, not hardware fault injection.
**Provenance:** recorded during the user-authorized deep SD review after introducing a realistic CMD12 R1b model.

## 2026-10-26  Scope the CMD12 address exception to a completed read at media end

**Why:** the previous generic stop helper suppressed OUT_OF_RANGE for every CMD12, although its justification was a card noticing the next address after an open-ended read of the final sector. The reviewed profile permits that exception only after a complete CRC-good read whose requested extent ends exactly at card capacity. Mid-card reads, failed reads, and writes retain the card error.
**Rejected:** a blanket OUT_OF_RANGE mask on all stops; hiding an actual write error; using merely the requested end address without successful full-length read completion. The normal command helper now requests no exemption; only the validated read-completion call supplies it.
**Evidence:** reviewed `command_checked()` and `transfer()`; actual-driver cases for complete end-of-media read, mid-card read, aborted end-of-media read, PIO write and IDMA write. No data-error, ownership or final-readiness guard was relaxed.
**Provenance:** recorded during the user-authorized SD state-machine audit. This narrows acceptance of errors rather than changing the current card's successful wire sequence.


## 2026-10-26  Negotiate native SD High Speed and own its separate kernel clock explicitly

**Why:** the existing 150 MHz kernel cannot produce 50 MHz with the SDMMC integer divider; truncating the old division would produce 75 MHz. The opt-in reviewed profile owns otherwise unused IC5 at PLL1/12 = 100 MHz, negotiates four bits at 25 MHz, then checks and switches function group 1 with native CMD6 before selecting 50 MHz. Both 64-byte status blocks must pass controller CRC, exact length, function support/selection, all-group cancellation, version, busy and current checks. Zero current means a protocol error; the additional 200 mA ceiling is a conservative bench budget, not an SD requirement. Unsupported or ambiguous initialization fails without a silent lower-speed fallback.

**Rejected:** overclocking a card without CMD6, treating ACMD6 bus-width selection as High Speed, enabling UHS/BUSSPEED or changing voltage, assuming falling transmit phase is optimal at every speed, or hiding failed initialization behind successful cleanup. Initial and intermediate Default-Speed commands retain falling launch; final High-Speed 50 MHz uses NEGEDGE=0 because the STM32 datasheet's HS output-valid timing is referenced to rising SDCLK. SELCLKRX remains zero. The first trial retains the existing GPIO speed3 and compensation to keep those electrical changes separate; this does not claim compliance with all datasheet test conditions or production reliability.

**Evidence:** `sd_card.c`, `sd_card.h`, `sd_clock_profile.h`, the actual-driver `test_sd_high_speed.cpp`, clock-helper tests and `../capture-raw/test_sd_high_speed.py`; [independent primary-source review](../capture-raw/evidence/2026-10-26-sd-review/PROTOCOL-REVIEW.md). The first RAM-only candidate is frozen at `tmp/bringup/sd50-reviewed-20261026/ram-scene`, SHA256 `85c17427303e837c27f7d08c1b517db2415d94bbc523b9b196eed77b29b856d1`. These offline tests include complete 3730-sector IDMA and progressive PIO writes, CMD12 busy ordering, failed negotiation, duplicate init, refused clock gates, retained ownership, and cleanup failures. Hardware outcomes belong in the capture evidence and were pending when this entry was written.

**Provenance:** implemented during the user-authorized maximum-reliability and 50 MHz review. Legacy/default builds remain separate. Before ROM/warm recovery the experimental mux must be restored; verified fresh idle permits deinitialization, otherwise ownership remains explicit and recovery requires the separately authorized cold path. Public APIs reject a gated controller before any SDMMC-register read, including retries after clock-release failure.


## 2026-10-26  Isolate the datasheet High Speed GPIO slew profile after read CRC failures

**Why:** the bench owner reported a complete 50 MHz pattern write followed by repeat read CRC failures at different words, while 12.5 MHz readback matched the full original image. A successful write therefore still does not qualify this link. The separate RAM-only `SD_HIGH_SPEED_MIXED_SLEW` trial uses CLK OSPEEDR01 and CMD/DAT00, matching the pin-speed conditions of DS14791 Rev11 Table94 without combining a compensation change. PC2 is CLK; PC3/PC4/PC5/PC0 are CMD/DAT0/DAT1/DAT2; PE4 is DAT3. The exact masks are GPIOC0xFF3 with desired0x10 and GPIOE0x300 with desired0. PC1 and all other GPIO bits stay untouched, including the later four-bit PE4 setup.

**Rejected:** silently changing uniform-speed3 High Speed builds, changing SD clock or phase at the same time, enabling compensation in the same trial, promoting mixed slew to flash/Standby before qualification, or interpreting this as full datasheet/PVT compliance. The datasheet also specifies load and compensation conditions; this experiment deliberately retains the inherited compensation configuration for attribution.

**Evidence:** `sd_card.c`, the explicit `capture-raw/build.py --sd-high-speed-mixed-slew` option, exact compiler/manifest/GPIO proof admission and actual-driver tests covering both full-image transfer paths and refused GPIO writes. First frozen candidate: `tmp/bringup/sd50-reviewed-20261026/ram-mixed-slew/capture.bin`, SHA256 `ad99984dec021f0e22351309bb8d704ad33e716f4977661c2c34ff9f166728ff`. All 137 capture tests plus targeted actual-driver and real-CMSIS ARM checks passed. Hardware results remain separately recorded by the bench owner.

**Provenance:** the two uniform-speed3 read failures and successful 12.5 MHz source comparison were reported by the root bench owner; this implementing agent performed no hardware operation.

## 2026-10-26  Isolate IDMA reception while retaining SD clock flow control

**Why:** the root's sustained 50 MHz PIO reads failed CRC despite successful writes and different slew trials. CPU FIFO service can produce legitimate hardware-flow-control clock pauses; a separate IDMA-read profile tests reception without that CPU-fed service pattern and provides a path to faster host retrieval. The explicit reviewed RAM option keeps HWFC, clock phase, CRC, fixed-length CMD18/CMD12, memory security and fresh completion/ownership checks. It supports one-sector CMD17 and up to512 sectors per multiblock transaction, using the known secure AXI destination region and disabled D-cache.

**Rejected:** disabling HWFC to hide pauses, attributing digitally observed narrow pulses to a proven controller defect or analog ringing, changing BUSSPEED/DLYB, consuming a DMA destination before full completion, flushing FIFO or disabling IDMA during an active transfer, or treating a recovered failed read as valid data. The final DATAEND must be error-free, DPSM inactive and DCOUNT zero; a failed abort retains DMA/controller ownership. Default PIO source paths remain explicitly reproducible.

**Evidence:** `sd_card.c` `dma_destination_checks()`, `transfer_dma_read()` and `dma_read_request()`; `test_sd_idma_read.cpp` and actual-driver/real-CMSIS compile tests in `test_sd_driver.py`; [protocol and flow-control analysis](../capture-raw/evidence/2026-10-26-sd-review/PROTOCOL-REVIEW.md). RM0486 section30.7.1 permits cycle-aligned flow-control clock stopping; pp1401–1404 and pinned `HAL_SD_ReadBlocks_DMA()` support single-buffer IDMA reception. The independent reviewer repeated both ordinary reviewed and High Speed actual-driver tests successfully; hardware qualification was pending when recorded.

## 2026-10-26  Keep fixed compensation and combined electrical trials explicit and RAM-only

**Why:** separate inherited-compensation 50 MHz uniform-slew and mixed-slew trials still produced read CRC failures. The next isolated profile reuses the already guarded VDDIO5 fixed-compensation value `0x287`, retaining uniform speed3. After the bench owner reported that this also failed, a third explicit option admits mixed slew plus fixed compensation together. Each frozen candidate binds the exact flags, six-pin GPIO proof, compensation proof and High Speed clock/negotiation evidence; no failed trial becomes the default.

**Rejected:** silently combining electrical changes, admitting these profiles to flash/Standby, weakening CRC or cleanup checks, or describing a successful write as a qualified read link. The compensation setting is not restored by SD deinitialization. A later warm run with an "unchanged compensation" build inherits the modified register; a measured cold cycle is needed to recover the original inherited-compensation comparison state.

**Evidence:** `sd_card.h`, guarded existing compensation code in `sd_card.c`, explicit `--sd-high-speed-fixed-compensation` and `--sd-high-speed-combined-electrical` build/bench bindings, actual-driver fault tests and `capture-raw/test_sd_high_speed.py`. Frozen fixed profile SHA256 `416f854e487e545bafb2d81e0d5ca4ba0521e9daf315dfb26f9551e5d6441589`; combined profile `85e11d81a1ec38b280c8536dd43823fabcad940a8fb930b5ebb5cdf78cfe3b8a`. Root reported CRC failures with clean controller/clock release for both; exact hardware records belong in [review evidence](../capture-raw/evidence/2026-10-26-sd-review/README.md).

**Provenance:** implemented offline at the bench owner's request following each isolated failure. No hardware operation was performed by this implementing agent. These trials establish no production/PVT electrical qualification.

## 2026-10-26  Bound startup delays and cache SCR only within one card session

**Why:** the explicit `SD_STARTUP_OPT` reviewed four-bit profile removes about 10 ms of fixed initialization overhead while retaining 100 kHz identification, the 1 ms GPIO settling and line-high checks, and every final readiness check. It sends 1 ms of continuous initial clocks, or 100 clocks, before CMD0. After an idle divider change it allows 1 us before fresh CMD13. The separate CMD6 switch allowance remains unchanged. The CRC-validated SCR read during width negotiation is immutable for the same card, so the coordinator can reuse it instead of issuing another query.

**Rejected:** using VDDIO5SV as a voltage measurement, shortening a separately switched card's supply ramp, changing identification to 400 kHz in the same experiment, deleting final readiness polling, or carrying cached SCR across errors, deinit, card replacement or a new initialization. The supply assumption is specifically the prototype's shared, already valid 3.3 V rail before the retained GPIO delay. `sd_read_scr_fresh()` explicitly rechecks the wire; any fault invalidates the cache. Init and public startup-profile APIs reject an off controller gate before SDMMC register access.

**Evidence:** `sd_card.c`, `sd_card.h`, actual-driver `test_sd_startup.cpp`, and [startup timing/proof specification](../capture-raw/evidence/2026-10-26-sd-review/OPTIMIZATION-AUDIT.md). Tests cover independent POWER-to-CMD0 timing, wraparound, both ordinary run rates and High Speed, cached/fresh SCR bytes, fresh-read CRC failure, owner binding, width failure, deinit/reinit, refused clock writes, unavailable cycle counter and gated controller access. Real-CMSIS ARM compilation passed. The full driver/clock matrix passed 27 tests; the final startup-only gate tightening passed the three focused model/compiler tests. Hardware qualification and cold-supply evidence remain separate.

**Provenance:** implemented offline during the user-authorized SD review. Initial build admission is explicit RAM only; no default or frozen firmware was changed by enabling this option.

## 2026-10-26  Keep native-HS receive sampling on the documented SDMMC2 pad-feedback path

**Why:** the receive CRC failures at50 MHz also occurred with IDMA, so the review examined whether a receiver sampling adjustment was missing. RM0486 Table209/p1376 states that the current `SELCLKRX=00` feedback is already derived from the SDMMC_CK pin; CLKMUX/p1400 designates this path for DS/HS without a transceiver. Table206/p1371 explicitly omits the external CKIN input on SDMMC2. `NEGEDGE` is a transmit control and cannot select an opposite receive edge.

**Rejected:** selecting external-feedback01 on a controller without that input, treating tuned-feedback10 or an arbitrary DLYB tap as a documented native-HS fix, or claiming digital CRC failures identify an analog mechanism. DLYB can physically lock at50 MHz, but the manual associates tuned feedback with the variable-delay modes and directs it to block-gap flow control rather than the current in-transfer HWFC path. A new tuning experiment needs its own complete operating-mode/flow-control and ownership review.

**Evidence:** [primary-source RX review](../capture-raw/evidence/2026-10-26-sd-review/RX-SAMPLING-REVIEW.md), RM0486 Rev4 pp1371,1376–1378,1400,1425–1426,1433,1460–1463 and pinned ST HAL UHS/DDR mode paths. ES0620 Rev5 contains no alternate receive-phase CRC workaround. Root owns the failed physical read records; no sampling register was changed for this review.

**Provenance:** recorded during the root-owned50 MHz CRC investigation after PIO, mixed-slew, fixed-compensation, combined-electrical and IDMA-read trials remained unqualified. This is a documented-configuration conclusion, not proof of the electrical root cause.

## 2026-10-26  Isolate the Default-Speed clock transition after validated CSD and before CMD7

**Why:** the user approved testing whether selecting the card at the normal transfer clock reduces initialization command time. The explicit `SD_EARLY_RUN_CLOCK` option retains 100 kHz through CMD9, validates the CSD's decimal `TRAN_SPEED` encoding against the requested 12.5 or 25 MHz rate, then changes only the idle controller divider before CMD7. CPSM/DPSM must be inactive, IDMA disabled, and both the original and applied CLKCR/phase must match exactly. The hardware busy timer is rescaled and read back as two seconds at the new clock before CMD7 can assert R1b busy. Existing post-selection READY/TRAN checks remain; no READY/TRAN poll is issued while the card is still in Standby protocol state.

**Rejected:** moving before card identification/CSD validation, combining this with a faster identification clock, using a binary interpretation of `TRAN_SPEED`, retaining the 100 kHz timer count after increasing frequency, polling for TRANSFER before CMD7, changing launch/receive phase or electrical settings, admitting the High Speed experiment, or silently changing historical executable profiles. The former second readiness poll after the late divider change is unnecessary on this path because the retained post-CMD7 readiness check already runs after the early divider transition.

**Evidence:** `sd_card.c` `early_run_clock()` and `sd_card.h` ECK1 proof bind the CSD byte/decoded limit, command counts, clocks, timers and DWT boundaries. Actual-driver `test_sd_early_clock.cpp` covers all 256 speed encodings, insufficient supported speed, 12.5/25 MHz success, active host/IDMA refusal, refused/corrupted divider and timer writes, CMD9/CMD7 failures, R1b timeout and counter wrap. Real-CMSIS ARM compilation passed. Every allocatable ARM section remained byte-identical with the option disabled across six frozen pre-edit profiles; record `tmp/bringup/sd-early-clock-20261026/driver-disabled-identity.json`. The owning capture integration initially admits only the selected 12.5 MHz RAM experiment; hardware outcomes belong in its separate evidence record.

**Provenance:** implemented offline after the user's “lets try it” instruction. The root bench owner runs the isolated hardware comparison; this entry does not claim a measured saving or physical-link qualification.
