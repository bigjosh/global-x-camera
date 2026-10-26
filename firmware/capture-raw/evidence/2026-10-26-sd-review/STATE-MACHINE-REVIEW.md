# SDMMC state-machine review — 2026-10-26

This is an offline review of the actual driver in `firmware/sd-storage/sd_card.c`, its register-model tests, and the separate High Speed clock/negotiation implementation. It does not qualify electrical operation at 50 MHz. The measured 12.5 MHz phase experiment is recorded separately in [README.md](README.md).

## Findings and implemented corrections

The corrections below require **`SD_REVIEW_PROFILE=1`**. The default is zero, retaining the historical branches for exact rebuilds and controlled comparisons. None of these corrections changes the on-card RAW layout, removes a CRC check, retries an uncertain write, or labels a failed operation successful.

| Finding | Consequence | Reviewed behavior | Actual-driver model coverage |
| --- | --- | --- | --- |
| CMD7 could run with the reset value of DTIMER, before the first SCR/data operation configured it. | A legitimate select-card R1b busy interval can immediately time out in the host even if the card later becomes ready. | Set a two-second timer at the actual 100 kHz identification clock, while both state machines are inactive, before identification. | A short CMD7 busy interval fails with the historical zero timer and succeeds with the reviewed timer; an excessive interval stays failed, uninitialized and owned. |
| Receive-abort cleanup drained at most 64 words from a 256-word FIFO. | A recoverable read error could remain non-idle simply because cleanup stopped too soon. | After completed CMD12, drain no more than the FIFO's 256-word capacity; use FIFORST only under its existing active-DPSM/no-IDMA constraints; then prove readiness. | Tails of 64, 65, 255 and 256 words; a deliberately impossible 257-word tail fails closed without FIFO reset. The original data error is retained. |
| Normal completion cleared DCTRL immediately after CMD12's response. | CMD12 can have a new R1b busy interval; changing DBLOCKSIZE/DTMODE/DTDIR while DPSMACT is set violates the register's write restriction. | For PIO, IDMA and progressive writes, finish card/host readiness before clearing DCTRL. IDMA is released only after its preceding DATAEND and inactive DPSM proof. | Short and excessive final busy intervals in all three paths; the reviewed path has zero DCTRL configuration changes during busy. |
| A late data/timeout/DMA error during final R1b readiness could be cleared without being returned. | The caller could count a write successful after the controller reported an error. | `ready_after_transfer()` checks retained DCRCFAIL, DTIMEOUT, RXOVERR, TXUNDERR and IDMATE before success cleanup. It preserves the first failure and does not increment successful sectors. | Late DCRCFAIL, DTIMEOUT and IDMATE after CMD12, for PIO, IDMA and progressive writes. Error flags remain recorded instead of being cleared as success. |
| Every CMD12 suppressed the card's OUT_OF_RANGE bit. | A stop after a failed read or a write could hide an unrelated address error. | Only a complete, CRC-good read whose validated extent ends exactly at card capacity receives the exception. All ordinary/abort/write stops keep the bit fatal. | Complete final-sector read, mid-card read, aborted end-of-media read, PIO write and IDMA write. |

The receive-abort bound is a finite cleanup limit, not permission to continue consuming a stream indefinitely. If a command/abort cannot establish a quiescent host and card, ownership and the failure remain visible. If a late error occurs after physical readiness has been proved, `media_idle` can correctly describe an idle card while the operation still returns failure and ownership remains held. Idle is not the same as successful storage.

`DABORT` is deliberately different from the error flags above. The driver issues CMD12/CMDSTOP after validating full DATAEND/count completion; that intentional stop can produce DABORT. Its presence alone is not a new corruption indication in this specific completion path. An arbitrary abort flag does not establish payload completion, and none of the length/CRC/ownership prerequisites was removed.

The durable reasoning for these changes lives in [the storage NOTES](../../../sd-storage/NOTES.md), with one entry per decision.

## Command and response checks

The existing command helper remains bounded and requires a terminal response indication with CPSM inactive. The new fault cases execute that helper itself, rather than reproducing its logic in a separate parser:

- R1 command CRC failure is rejected and preserved in the failure record.
- R3 has no CRC7; a host CCRCFAIL indication is accepted for R3 only.
- Wrong RESPCMD values are rejected for R1, R6 and R7. R2's reserved command-index field is not compared.
- An already-active CPSM prevents launching another command. A CPSM stuck after launch reaches the software timeout and remains failed.
- CMD7 selection and CMD12 termination distinguish response completion from R1b busy completion.
- The error record keeps the first error, stage, command and status. Cleanup has a separate result; a successful cleanup does not erase the original failure.

These are additional model tests, not a change to command CRC acceptance. The R3 exception and R2 index behavior are protocol requirements, not weakened checks.

## Completion, DMA and power-off contract

The current sequence is coherent when its completion boundaries are kept separate:

1. Prove the card is READY/TRAN, DAT0 is high, CPSM/DPSM are inactive and IDMA is released before preparing a new operation.
2. Configure a bounded data timer and complete owned extent. For whole-slot writes, CMD55/ACMD23 announces the extent, and a single CMD25 starts it.
3. Feed only published, immutable source bytes. An already complete image uses IDMA; an incomplete image uses PIO and hardware flow control. The last sector remains withheld until the capture owner validates completion.
4. Require DATAEND, inactive DPSM, no applicable data/DMA error and the complete expected count. For IDMA also require DCOUNT zero, then release IDMA ownership.
5. Send CMD12 for an open-ended multiblock operation. ACMD23 is a preparation hint, not an automatic fixed-count stop.
6. Prove final card/host readiness, retain any late error, then clear the data-path configuration and count the operation successful.
7. Before deinitialization/power-off, obtain a fresh readiness proof. Gate/reset the host and release its clock ownership only from that verified state.

RM0486's DATAEND conditions settle an apparent receive-loop concern: for a normal RX transfer, DATAEND requires the FIFO to be empty as well as the transfer to be finished. The PIO block reader's early DATAEND/inactive check therefore does not itself discard unread FIFO data. TX DATAEND also includes the final block's CRC-status/busy completion; it is not just a DMA-memory-copy completion notification. The subsequent CMD12 response/busy interval remains a distinct step.

The IDMA checks for secure AXI SRAM, disabled data cache, RIF configuration-port security and DMA-master security remain necessary. Prior hardware evidence showed that missing configuration-port security could return zeros without an SD or IDMA bus error. Those checks are not redundant with a successful wire CRC. CPU WFI during IDMA remains separately unqualified and disabled in normal operation.

## High Speed audit

The opt-in `SD_HIGH_SPEED=1` path has a different clock contract from historical profiles: an exclusively owned 100 MHz IC5 kernel permits an exact 50 MHz SD clock. The existing 150 MHz kernel divided using integer `150/(2*50)` would select divider 1 and produce **75 MHz**, so merely admitting a `50000000` argument is unsafe.

The reviewed transition uses 100 kHz identification, 25 MHz Default Speed and one-bit SCR acquisition, explicit ACMD6 four-bit negotiation, then native CMD6 check and switch. Native CMD6 is distinct from CMD55/ACMD6: its arguments are `0x00FFFFF1` and `0x80FFFFF1`, and it returns a 64-byte status block. The status transfer must finish with CRC/length/controller checks before the host accelerates. Eight transition clocks are required; the implementation leaves 25 MHz running for at least one microsecond before changing the clock. The final phase and receive-clock policy are recorded in the protocol/clock review and exact build manifest, not inferred from the word NEGEDGE.

The CMD6 byte interpretation checked against the SD status tables is:

| Status bytes | Meaning checked |
| --- | --- |
| 0–1 | Maximum current, big-endian; zero indicates an error. The 200 mA admission ceiling is this prototype's policy, not a universal SD protocol limit. |
| 12–13 | Group 1 support bitmap; High Speed is bit 1. |
| 14–16 | Six selected-function nibbles. Any `0xF` result in switch mode cancels the entire switch, including when Group 1 itself appears selected. |
| 16 low nibble | Group 1 selection must be function 1. In check mode, a supported and ready requested function is returned here; it need not mean the card was already using High Speed. |
| 17 | Status version; only the implemented versions are accepted. |
| 28–29 | Group 1 busy bitmap for status version 1; bit 1 must be clear. |

Independent integration review identified two additional issues, both corrected in the reviewed source: the progressive-write wrapper rejected 50 MHz before it could delegate a completed frame to IDMA, and duplicate `sd_init()` calls could enter the new cleanup wrapper for a session the call had not acquired. The high-speed model now writes a complete 3,730-sector slot through each of the IDMA and progressive-PIO paths, verifies every modeled word, requires one announcement/CMD25/CMD12, and deinitializes successfully. Duplicate initialization returns STATE without issuing commands, changing the clock or releasing the existing session.

A failure after changing the bus clock/phase but before recording final qualification requires particular care. The guard now recognizes the applied 50 MHz clock independently of the success flag, and an injected final-CMD13 CRC failure demonstrates fresh idle cleanup and clock release while keeping qualification false and returning the original error. A failed IC5 release retains ownership; subsequent API calls fail before reading the gated SDMMC register bank. A status/parser/ready failure never silently falls back to a different operating mode or invents a successful qualification. If warm restoration cannot be proved, the failed state remains for the separately controlled recovery path.

The initial fixed-compensation diagnostic was admitted only with the explicit High Speed fixed-compensation flag, uniform speed3 and a RAM-only50MHz build. Its builder, C compile-time/runtime and host-manifest gates rejected mixed slew, flash and Standby combinations; the subsequent combined electrical trial required a separate explicit admission. It reuses the guarded VDDIO5 fixed-code path: PWR/SYSCFG clocks, reset state and both required supply-valid bits must be proved before the compensation register is accessed. Its proof records the exact before/after write. Independent host-profile tests passed all9 initial cases; the transport owner separately passed the actual-driver failure model and ARM compilation. This is an isolated experiment admission, not evidence that the electrical change improves reliability. Full3,730-sector High Speed PIO/IDMA model tests also include three final CMD12 busy polls, the100MHz timer basis and zero DCTRL writes during active busy. Both fixed-compensation hardware follow-ups subsequently failed reads; their preserved results are in [the evidence README](README.md#fixed-compensation-follow-up-failures).

## Independent IDMA receive review

The separate `SD_IDMA_READ=1` diagnostic keeps the existing read API and requires the reviewed profile. It uses one owned contiguous destination per transfer, at most512 sectors (16 at100kHz), while preserving HWFC, card CRC, CMD12 and fresh final readiness. The platform caller owns the destination throughout success or proven abort; a failed read never supplies valid image data.

The destination check requires word alignment, a64-bit nonoverflowing extent wholly inside secure AXI SRAM (`0x34000000` through `0x343fffff`), card capacity, privileged thread context and disabled data cache. RIFSC must be clocked before its registers are read; SDMMC2's DMA master must be secure/privileged CID1 and its configuration port secure. As with writes, the caller must provide the corresponding SRAM/RISAF permissions and prevent destination overlap with live code, proofs, other owners or the source image retained for comparison. The driver neither broadens those permissions nor assumes bus CRC detects a denied SRAM write. The diagnostic bench destination is separately bounded at`0x34200000`,262,144bytes.

Independent review caught a scope problem before qualification: the existing `SD_HOST_GUARD` expands to no check outside High Speed builds. The new receive path now independently checks the RCC SDMMC2 clock gate before any SDMMC register access, so lower-frequency reviewed controls also reject a stale owned-but-gated host. This correction is confined to the opt-in receive path.

Setup uses receive direction, block size512, DTEN disabled, destination base followed by a barrier and single-buffer IDMA enable, then CMD17 orCMD18 with CMDTRANS. This agrees with the pinned HAL receive setup. RM0486 section30.5.6 (pp1401–1404) states that single-buffer DATAEND follows both memory transfer and DPSM completion. The implementation therefore requires DATAEND, inactive DPSM, no data/IDMA error and DCOUNT zero before releasing IDMA. A barrier precedes returning ownership of the destination. Multiblock completion then sends the scoped CMD12, waits through its R1b busy/error checks and clears DCTRL only afterward.

Error handling reuses the existing IDMA abort sequence rather than the CPU FIFO drain: CMD12, bounded wait for inactive state machines, then release IDMA and prove final readiness. It never reads the FIFO from the CPU or resets it while IDMA owns it. A stuck abort retains IDMA, controller ownership and the original error. This is consistent with RM0486 section30.6.2; the helper's historical `abort_dma_write` name does not change the shared IDMA FIFO-ownership rules.

Independent actual-driver tests passed at reviewed25MHz and High Speed50MHz with fixed compensation. They check exact destination contents and guard bytes for1/2/64/512/513sectors; the513-sector request splits into CMD18+CMD17. Coverage also includes SDSC addressing, media-end stop exception, command/data/DMA failures, DATAEND+IDMATE precedence, residual DCOUNT, stalled/failed aborts, late CMD12 error flags, destination/cache/security/clock refusals and timestamp wrap. No PIO FIFO access, invalid active-DCTRL change or premature ownership release is accepted. These modeled passes establish implementation behavior, not electrical reliability or hardware throughput.

## Necessary checks versus potential savings

### Independently reviewed startup optimization

`SD_STARTUP_OPT` is a separate reviewed four-bit profile. It retains the1ms GPIO settling/high-input check, shortens the continuous100kHz initial clock train from10ms to1ms, and shortens the ordinary idle run-divider settling delay from1ms to1us. Fresh CMD13 readiness remains after the divider change, and the later CMD6 switch delay is separate. The initial train supplies at least100 clocks, exceeding the74-clock requirement, **only under the explicit fixed-board assumption that the card's shared3.3V supply is already valid before the retained GPIO interval**. The supply-valid register bit is not physical rail evidence; this is unsuitable without requalification for a newly switched or ramping card supply.

The SCR already read and validated during four-bit negotiation is cached for the same `sd_card_t` owner. It is populated only after complete length/CRC/status/structure checks and fresh readiness. Init, deinit and any driver fault invalidate both the cached value and owner; a different owner or explicit `sd_read_scr_fresh()` uses the wire again. Public cached access still requires initialized ownership, a live SDMMC clock gate, the High Speed clock guard when applicable, and no retained error. This removes the duplicate capture SCR transaction without removing initialization's capability checks or any final storage-readiness proof.

The64-byte SOP1 telemetry binds measured delays, run frequency, one wire SCR read and the expected cache-hit count. Successful operation admission requires the cache to have been invalidated during deinit. It is not an idle proof itself. Independent tests passed three host-admission/telemetry cases and two actual-driver model variants, covering reviewed12.5/25MHz and High Speed50MHz. The models check fine-grained clock timing, DWT wrap, cached/fresh data, deinit/reinit, different owners, gated access and SCR/width/command failures. Exact flash-prefix admission and cold hardware qualification are separate steps.

The final startup-only guard refinement also proves the AHB5 SDMMC gate before the first controller-register access during init and checks it at public API entry at the lower frequencies. Independent reruns passed refused-gate, unavailable-cycle-counter and gate-lost-before-deinit cases, with the model rejecting any gated controller access. A failed deinit retains ownership. If the initial gate enable itself is refused, the lower-frequency path leaves its selected kernel mux at zero and reports the retained clock failure; it does not claim to restore an arbitrary previously selected source. The current bench starts with mux zero. General admission from another clock source remains outside this bounded profile.

The review does not justify removing the final CMD12, card/host readiness, CRC, source ownership, error precedence or clock-access gates. They protect distinct failure cases. A successful write response is not proof that later power removal is safe; a logic trace is not proof that bytes came from the intended camera RAM.

Some repeated work is a possible optimization rather than a correctness problem:

- The startup profile above now retains the validated SCR within the same initialization ownership; historical profiles retain the original second read for reproducibility.
- Successive exclusive-owner API calls can each issue pre/post readiness commands. A future internal transaction token could avoid selected duplicate checks, but it must be invalidated on every state-changing command and error. Final readiness before shutdown remains required.
- Header scanning reads one 512-byte sector per candidate slot, with command/readiness overhead. An allocator redesign or verified scan hint could reduce that cost; neither is required for the current single-image transfer.
- CPU PIO service granularity and overlap affect throughput, particularly at 50 MHz. Those changes need separate source-publication, FIFO-starvation, CRC and readback evidence; the current conservative path should not be accelerated by reading unpublished pixels.

## Unresolved manual/vendor discrepancy

RM0486 Rev4 section 30.6.2 describes DTMODE `11` for open-ended CMD18/CMD25, terminated by STOP. The current driver and pinned STM32CubeN6 HAL use DTMODE `00` with an exact DLEN, followed by CMD12. The qualified wire traces show that this current path transferred the intended blocks and stopped successfully, but they do not establish general equivalence with the manual's prescribed mode.

**No DTMODE change is included in this review profile.** It is deliberately deferred to an isolated experiment after the initial 50 MHz work. Such an experiment must check DATAEND/DCOUNT semantics, CMD12/busy behavior, error aborts and complete image readback. The discrepancy is a test requirement, not a proven current corruption bug.

## Verification and limits

The focused actual-driver matrix passed for legacy one/four-bit paths and reviewed one-bit, four-bit and initial-falling-edge paths. It includes the command failures, CMD7 timer, full FIFO abort, scoped OUT_OF_RANGE exception and 15 final-busy/error combinations across PIO/IDMA/progressive writes described above. Historical behavior is intentionally represented in tests so the profile boundary is visible. The model cannot establish metastability, physical setup/hold time, card-controller internals, power-loss safety or arbitrary-card compatibility.

An independent run passed six targeted tests: the high-speed switch/failure model, all three reviewed one/four-bit/initial-phase variants, the clock helper's ownership/failure/restore model, and its ARM C compile against the pinned CMSIS headers. The high-speed cases also cover unsupported capability/current/version, busy function, every canceled-selection nibble, command/data errors, missing controller gate, wrong phase, invalid stored frequency, duplicate init, failed clock release and final-ready failure. The high-speed owner runs the complete legacy regression and driver ARM compile matrix separately.

Final exact-build hashes, hardware runs and measured time/energy belong to the root-owned experiment record. No high-speed hardware success, reliability rate or power saving follows from this offline review alone.

## Primary references

- ST [RM0486](https://www.st.com/resource/en/reference_manual/dm00769900.pdf), local verified Rev4: Table 220 (pp1394–1395), data transfers/aborts section30.6.2 (pp1415–1417), R1b section30.6.6 (p1422), DTIMER/DCTRL register restrictions (pp1438–1440). Local searchable copy: `tmp/capture-research/rm0486-compact.txt`.
- SD Association [Physical Layer Simplified Specification archives](https://www.sdcard.org/downloads/pls/archives/): local v2.00 section4.3.10, Tables4-10/4-12/4-13, printedpp35–38, checked against the v6.00 status layout. Private copies under `tmp/hardware-review/sd-breakout/`. The [official v6.00 file](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver6.00.pdf) uses a download content type that the web reader does not render; the local saved copy is the reviewed artifact.
- Pinned STM32CubeN6 HAL/LL source in `tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/STM32N6xx_HAL_Driver/`: transfer setup and stop-command reference behavior. Vendor code is evidence of implementation practice, not a reason to ignore the reference manual discrepancy above.
