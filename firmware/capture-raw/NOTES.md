# RAW capture integration decisions

## 2026-10-24  Retain the whole linear frame while storage consumes completed prefixes

**Why:** camera delivery is much faster than the present one-bit card interface. The earlier 2.65 MB/s driver rate could drain only about 58 KiB during a roughly 22 ms frame, and cold card initialization can finish after capture. Reusing a small circular buffer would overrun despite overlap; the retained frame acts as a bounded producer/consumer queue without copies. Pipe0's documented double buffering switches whole frames, not the intra-frame line-wrapping mode available to pixel pipes.
**Rejected:** assuming that a sector-sized or double buffer eliminates the image RAM requirement; assuming future long exposures or faster cards have the same initialization/frame ordering.
**Evidence:** commits `cff6da2c`, `a0b8ce70`; [initial buffer calculation](../capture-packed/README.md#what-this-permits-for-sd-storage); [selected implementation](README.md).
**Provenance:** migrated 2026-10-24 from the documented calculation and implemented ownership model. The rate calculation was a model, not a separate measured overlap result.

## 2026-10-24  Publish LINE prefixes conservatively and withhold completion until STOP

**Why:** Pipe0 LINE is described near the memory output, but the manual does not explicitly guarantee all AXI writes are globally visible. A CPU barrier cannot drain another bus master. Holding back one 64-line group gives a conservative 89,600-byte first publication; immediate ISR tail snapshots test visibility before a slow SD consumer could hide premature publication. Validated FRAME, successful sensor STOP and guards release the final sector/marker.
**Rejected:** using `P0DCCNTR` as a live producer pointer; publishing the first 512 bytes merely because a line event occurred; counting stale LINE flags; declaring the engineering margin a guaranteed AXI-drain bound.
**Evidence:** commits `a0b8ce70`, `14d05d9a`, `18299c29`; [LINE reasoning and tests](LINE.md); [long-exposure snapshots/readback](evidence/2026-10-24-front-metadata/README.md).
**Provenance:** migrated 2026-10-24 from manual review, producer tests and sampled hardware evidence. Finer publication and prolonged FIFO starvation remain unqualified.

## 2026-10-24  Return camera faults to the active storage owner before cleanup

**Why:** acquisition and SD calls overlap. A camera callback that parks or starts unrelated teardown can strand an active CMD25/IDMA operation. Progress and IRQ paths therefore latch faults; the SD owner performs bounded stop/idle handling before outer capture cleanup. Asynchronous sensor STOP preserves command order and can hide its acknowledgement delay during IDMA, while completion remains gated on its success.
**Rejected:** parking inside camera progress callbacks, SD reentry, or treating camera reset as proof that SD is idle. The original asynchronous STOP option required IDMA because a blocking I2C poll could starve CPU-fed FIFO writes; the later progressive path must retain its bounded callback contract.
**Evidence:** commits `a0b8ce70`, `14d05d9a`; [ownership and failure cleanup](LINE.md); [transport callback contract](../sd-storage/README.md#progressive-publication-within-one-multiblock-write).
**Provenance:** migrated 2026-10-24 from integration decisions and executable failure tests; physical camera-failure cleanup is not promoted from simulation to a hardware qualification.

## 2026-10-24  Leave shallow WFI during IDMA disabled after failed trials

**Why:** the first experiment correctly refused absent SRAM/security/SD sleep clocks before WFI. The follow-up enabled the intended clocks and removed debug sleep emulation but stalled, losing core/high-SRAM access; warm reset did not restore it. Its actual sleep/wake state and root cause remain unresolved. Polling IDMA is the qualified fallback, distinct from final post-save Standby.
**Rejected:** relaxing sleep prerequisites, promoting the revised experiment to flash, or calling a current plateau successful completion. BSEC retention and M55 local power controls remain hypotheses, not fixes.
**Evidence:** commit `a0b8ce70`; [failed v9/v14b records](evidence/2026-10-24-raw-slots/README.md); [selected implementation and deferred optimizations](../../docs/decisions/raw-sd-slots-2026-10-24.md#selected-implementation-and-deferred-optimizations).
**Provenance:** migrated 2026-10-24 from preserved failures. A future attempt should first qualify an idle-card WFI before sleeping during an active write.

## 2026-10-24  Keep early loading fixed and relocate only reviewed CRC literals

**Why:** loading combined camera/storage code before arming can exceed the existing first-frame budget. RAW builds retain the 15,804-byte early range and load verified storage code after arm. Changing the early length or embedded CRC caused GCC to move prefix instructions/literals, so the builder keeps the known layout and relocates only two independently checked CRC data words across ELF, binary and listing.
**Rejected:** enlarging early loading, weakening recovery byte identity, patching arbitrary instructions, or accepting pattern flash builds that change the conservative recovery boundary. Pattern qualification uses RAM builds.
**Evidence:** commit `a0b8ce70`; [RAW-specific cold-start constraint](README.md#cold-start-constraint); [earlier split-loading rationale](../capture-timing/NOTES.md#2026-10-17--load-and-check-later-code-during-sensor-startup); `build.py`.
**Provenance:** migrated 2026-10-24 from linker/disassembly checks and the preserved build decision; fixed size is not itself a new timing guarantee.

## 2026-10-24  Clear the retained late-loader proof before every boot's camera setup

**Why:** `RLOK` lies outside `.bss` and can survive warm reset. An early camera failure could otherwise trust the previous boot's successful late load and call code not loaded/verified in this boot. V15 clears the marker at dispatch before any such failure path.
**Rejected:** treating retained success as fresh proof; relying on normal `.bss` initialization for this fixed-address record.
**Evidence:** commit `a0b8ce70`; [freshness correction](README.md#cold-start-constraint); [v15 follow-up qualification](evidence/2026-10-24-raw-slots/README.md); executable stale-marker regression tests.
**Provenance:** migrated 2026-10-24 from code review and offline failure coverage. The v15 cold smoke passed; the early-failure scenario was tested offline.

## 2026-10-24  Align the front-metadata image without copying and share overlapping guards

**Why:** DCMIPP requires a 16-byte image address while SDMMC accepts a word-aligned source. A slot base at `0x34000004` places the image after its 156-byte prefix at `0x340000A0`. Moving the trailer to the slot's final word makes the 32-byte camera and persistent end guards overlap by 28 bytes; one nine-word sequence lets both checks coexist until the trailer replaces only the first word.
**Rejected:** copying the frame to obtain alignment, seeding conflicting independent guards, or writing the trailer before FRAME/STOP validation. Metadata must be initialized before publication, including on retained nonzero SRAM.
**Evidence:** commit `18299c29`; [geometry and hardware qualification](README.md#selected-layout-v18-front-metadata-slots); `test_magic_integration.py`; [format rationale](../raw-slots/NOTES.md#2026-10-24--put-all-reserved-metadata-in-the-first-sector-and-distinguish-the-new-layout).
**Provenance:** migrated 2026-10-24 from the layout implementation, all-nine-word corruption tests and complete SD/RAM comparisons.

## 2026-10-24  Isolate SD clock experiments in RAM and bind the measured frequency

**Why:** the replacement four-bit carrier initialized and read existing data successfully at 25 MHz, but its first progressive write reported a data-CRC error. A RAM-only 12.5 MHz option changes the clock without changing the SD driver, GPIO slew, card width, capture geometry or cleanup policy. The default remains 25 MHz and rebuilds byte-identically; manifest, compiler flag, terminal/card clock and the negotiated CLKCR divider must agree before accepting a result.
**Rejected:** changing several electrical/protocol variables at once, treating read success as write qualification, weakening CRC/idle checks, or silently promoting a diagnostic lower frequency to flash/Standby. A lower-clock result alone would not identify the underlying electrical cause.
**Evidence:** `build.py --sd-clock-hz`, `runtime.c` compile-time restrictions, `bench.py` clock binding, `test_sd_clock.py`; private `tmp/bringup/sd-fourbit-20261024/pattern-fault-status/diagnostic.json` and `ram-pattern125-v20/manifest.json`. Durable hardware measurements remain the responsibility of the owning experiment record.
**Provenance:** recorded during replacement-carrier qualification; no lower-clock hardware result was established when this entry was added.

## 2026-10-24  Admit the explicit 12.5 MHz fallback for four-bit flash qualification

**Why:** the 12.5 MHz/default-slew pattern save passed full camera-RAM equality, while separate 25 MHz default-slew, low-slew and fixed-compensation trials failed CRC checks. The bench owner selected 12.5 MHz with unchanged speed-three pins and no compensation modification for the final comparison. Builds may now explicitly select this clock for flash/Standby; the prior 25 MHz default and exact frequency/compiler/divider checks remain. This supersedes the earlier RAM-only clock restriction, not the separate RAM-only slew and compensation restrictions.
**Rejected:** extending the experiment with further electrical variables before completing the requested comparison, disabling CRC/idle guards, making the lower frequency an implicit default, or treating a single pattern equality result as complete cold-cycle qualification. Exact recovery-prefix review and hardware scene/long-exposure/Standby verification remain separate gates.
**Evidence:** `build.py`, `runtime.c`, `bench.py`, `inspect_flash.py`, `test_sd_clock.py`, `test_inspect_flash.py`; frozen `tmp/bringup/sd-fourbit-20261024/flash125-v23`, `ram-scene125-v23`, `ram-long125-v23`. Owning hardware evidence records the trial outcomes; this change performs no programming or bench operations.
**Provenance:** recorded under the exclusive bench owner's request to qualify the lower-clock fallback after the bounded compensation trial failed.

## 2026-10-25  Admit the exact 25 MHz NEGEDGE profile for guarded cold qualification

**Why:** after the user added 27 ohms midway along CLK and removed the SD signal probes, the bench owner reported complete SD-to-original-RAM equality for the retained slot5 image, a fresh normal scene in slot6 and a long-exposure/snapshot capture in slot7. This supports moving the explicit four-bit/25 MHz/NEGEDGE/GPIO-speed3/unchanged-compensation profile into awake flash qualification, then separate Standby trials. The default options and existing v23 executable bytes remain unchanged. Exact width/clock/phase telemetry, storage ownership and CRC guards remain required.
**Rejected:** treating RAM success as cold-boot or general reliability qualification, attributing the improvement to NEGEDGE alone, silently selecting the phase in historical builds, promoting nondefault slew or compensation experiments, or accepting an arbitrary self-consistent recovery prefix. The new prefixes retain every recovery instruction/literal and the 15,804-byte early load; only the two reviewed receiver-CRC data words change. Awake inspection still refuses Standby and requires the configured phase in live evidence before any halt.
**Evidence:** `build.py`, `runtime.c`, `bench.py`, `test_sd_phase.py`, `test_inspect_flash.py`; private `tmp/bringup/sd25-crc-20261025/promotion-proposal/overlay-build-validation.json` proves v23 and existing phase-RAM byte identity and prefix differences. Canonical `promoted-flash25-awake` and `promoted-flash25-standby` builds and exact recovery tests support guarded qualification. Physical findings and the probe/resistor limits belong to [the SD link investigation](evidence/2026-10-25-sd25-crc/CHECKPOINT.md).
**Provenance:** appended at the exclusive bench owner's request after the no-probe RAM readbacks passed. This admission performs no hardware operation and claims no completed cold-cycle, energy or long-term reliability result.

## 2026-10-25  Use fixed RAM timestamp slots and an awake profiling completion

**Why:** the user requested real phase timings with minimal logger overhead. One timer read and fixed volatile store per event avoids formatting, allocation, a shared append index and hot FIFO-loop logging. Separate ISR/main IDs avoid writer races; coarse counters describe repeats. The existing prefix telemetry provides boot/sensor/load milestones without altering recovery code. Standby loses this SRAM, so the opt-in trace profile parks at the existing successful awake terminal until the guarded host reads it. The ordinary build remains byte-identical and the qualified Standby image was restored after testing.
**Rejected:** printf logging, per-word/poll instrumentation, treating logger DONE as storage-idle permission, adding early NOR load bytes, joining unrelated runs, or claiming the awake log measures power-on/ROM/Standby or pure card programming time. Historical PNG records occupy 0x343FA000, so the new 1 KiB record uses 0x343FB000. The added 1,144 late-code bytes and runtime hooks have nonzero profiling cost.
**Evidence:** `build.py --cycle-trace`, `cycle_trace.h`, `inspect_flash.py`, integration/driver/assembly tests; [101-event cold trace and source-RAM-equal slot12](evidence/2026-10-25-cycle-trace/README.md). Exact UART recovery passed and all 64 KiB of both installation and restoration read back correctly.
**Provenance:** recorded during the user's explicit instrumentation request; one diagnostic cycle, not a new repeated energy/reliability qualification.

## 2026-10-25  Preserve reported clock tags separately from the qualified DWT frequency

**Why:** the first retained CTP1 trace reported 64 MHz at receiver event2, before main updates SystemCoreClock. Frozen startup initializes that variable to HSI_VALUE even though the ROM clock path remains at the checked 400 MHz. Event207 hardcodes400 MHz and event3 follows SystemCoreClockUpdate. Scaling event2 by64 MHz would fabricate a timing discontinuity.
**Rejected:** blindly trusting a software frequency tag, accepting arbitrary clock changes, or relaxing the device's live clock/build gates. The offline decoder admits only the exact207→2→3 bracket with tick0, successful prefix and matching ROM clock-register evidence; it keeps both reported and qualified frequencies and rejects other mismatches.
**Evidence:** `cycle_trace.py`, its strict-clock regression tests and [same-run retained prefix records](evidence/2026-10-25-cycle-trace/prefix-telemetry.json). This was a host-decoder correction; the captured firmware and original data were unchanged.

## 2026-10-26  Restore the qualified 12.5 MHz profile for fully probed SD capture

**Why:** the user requested a slower bus after the newly probed 25 MHz capture
showed a real card CRC rejection. Reusing exact v23 preserves an already
reviewed recovery prefix and storage implementation. One new cold capture
then transmitted all3,730 sectors with matching four-lane CRCs and positive
card status. The selected profile also restores the default clock phase;
the builder does not admit 12.5 MHz NEGEDGE.

**Rejected:** claiming this is a clock-only experiment, silently extending
the phase/build allowlist, treating analyzer acceptance as SD readback, or
claiming general link reliability from one successful capture. The card was
not erased and partial earlier slots remain occupied.

**Evidence:** [clock/capture record](../../tools/saleae-sd-native/evidence/2026-10-26-sd125.json),
exact NOR installation/readback in `tmp/bringup/sd125-probed-20261026/`, and
the updated [bench checkpoint](../../AGENTS.md).

## 2026-10-26  Apply falling-edge launch during identification as well as fast SD transfers

**Why:** the user requested host output changes on falling and input sampling on rising at12.5MHz. NEGEDGE is a transmit selector; SELCLKRX=00 already provides the rising feedback receive path. The new explicit init-phase option sets launch timing before POWER enables and preserves all historical default/25MHz executables. One cold awake capture and complete source-RAM/SD equality qualified this specific physical configuration.
**Rejected:** calling NEGEDGE an RX-edge selector, leaving initialization on a different phase while describing all commands as falling-launched, inferring data integrity from card acceptance alone, or claiming analog/production reliability from digital capture.
**Evidence:** [same-run wire, frame and readback proof](evidence/2026-10-26-sd-review/README.md). Prefix review retained all20recovery literals, instructions and15,804-byte early load; only two receiver-CRC words changed.

## 2026-10-26  Bound an optional final-sector wait before selecting the SD transport

**Why:** the 50 MHz warm-pattern experiment reported a fully captured image whose final sector remained withheld for sensor STOP. Selecting progressive PIO at that instant committed the whole image to the slower CPU-fed path. The opt-in RAM coordinator can spend up to 10 ms seeking complete publication only when FRAME is already validated and all but the last sector are available. Normal publication still owns STOP, guards and trailer release; a missed allowance falls back to PIO without becoming a camera failure. Long-exposure frames remain eligible for immediate progressive writing.

**Rejected:** publishing the trailer before successful STOP, waiting for an incomplete frame, changing transport inside an active CMD25, adding duplicate preannouncement commands, treating a publication fault as a timeout, or silently enabling this experiment in frozen/default or flash profiles. The DWT loop is wrap-safe, but one bounded normal publication callback may straddle its deadline; actual elapsed time is retained rather than claimed to be an absolute 10 ms wall-time maximum.

**Evidence:** `magic_runtime.inc`, `runtime.h`, `test_dma_tail_wait.py`, the existing `test_magic_integration.py`, and [the optimization audit and telemetry schema](evidence/2026-10-26-sd-review/OPTIMIZATION-AUDIT.md). Offline semantic and publication tests passed when recorded; hardware speed, energy and link qualification remain separate.

## 2026-10-26  Bind receive-IDMA and frame-tail-wait experiments separately from normal capture

**Why:** the deep SD review identified two independent experiments: remove CPU receive-FIFO service gaps during diagnostic reads, and give an already validated frame's last-sector publication up to 10 ms to complete before selecting progressive PIO. The host admits receive IDMA only for reviewed RAM READ operations; tail wait is a separate RAM capture option requiring magic slots, LINE publication, IDMA and asynchronous STOP. A full or completed tail wait must choose IDMA, while timeout retains the normal publication path and can fall back to PIO. The 64-byte tail record is checked against its exact compiler flag, layout, wrap-safe timestamps, eligibility and result; it is telemetry, never an idle proof.

**Rejected:** enabling either experiment implicitly, enabling both together, allowing receive-IDMA diagnostics to format or capture through the bench helper, waiting for long-exposure frames before beginning progressive writes, weakening FRAME/STOP/guard publication, or allowing a diagnostic record to authorize recovery. Flash/Standby promotion remains separate qualification work.

**Evidence:** `build.py`, `runtime.c`, `bench.py` diagnostic and telemetry admission, `test_diagnostic_profiles.py`; actual tail-helper and IDMA-read models are owned in `test_dma_tail_wait.py` and `../sd-storage/test_sd_idma_read.cpp`. Frozen fixed-compensation50 tail+trace capture SHA256 `018f15dae3a866bc0184ca4226316216f9d6869ae28976e123a8445d9cbec4e9`, separate receive-IDMA read `2093b8baeffb5bebc2d7465781d83f322184ca0619d957b419f23458d7257668`, reviewed12.5 tail+trace fallback `b668a8ddd8178b85c9f73a5cb2439aef6e5fd397df24674bd1a775f8a18f2040`. All148 capture tests passed. The fixed50 control rebuilt with both diagnostics disabled is byte-identical to SHA256 `416f854e487e545bafb2d81e0d5ca4ba0521e9daf315dfb26f9551e5d6441589`.

**Provenance:** recorded during the root-owned50 MHz reliability experiments. Build/test success is not a hardware throughput, energy or read-link qualification; those measurements remain in the experiment evidence.

## 2026-10-26  Select reviewed12.5 MHz startup improvements without the tail wait for cold qualification

**Why:** complete RAM-source/SD comparisons passed for normal startup+tail, long-exposure progressive publication, and startup without tail. In the root-owned12.5 MHz comparison, the tail trial waited10.00455 ms and then used PIO; its321.562 ms storage phase was effectively unchanged from the no-tail trial's321.701 ms. The observed total was386.271 ms with tail versus377.752 ms without, with two additional scanned headers in the later no-tail run. Tail waiting therefore added delay at this bus rate. The separate50 MHz tail/IDMA write success does not resolve50 MHz read CRC failures or justify selecting that frequency for normal operation.

**Rejected:** enabling tail wait in the selected12.5 MHz firmware, generalizing the50 MHz write result into read-link qualification, silently enabling receive-IDMA/WFI, or broadly admitting every experimental profile to flash. Builder, compiler and inspection gates admit only the exact four-bit12.5 MHz reviewed/startup profile with falling launch during identification and transfer, speed3, unchanged compensation, magic/LINE/polling-IDMA/asynchronous-STOP capture, and no tail/read-IDMA/WFI/trace/preinit/pattern diagnostics. This supersedes the prior RAM-only restriction for this exact startup profile; tail wait remains RAM-only.

**Evidence:** root-reported full source comparisons for slots24/25/26 under `tmp/bringup/sd50-reviewed-20261026/`; [selected immutable identities](evidence/2026-10-26-sd-review/selected-no-tail-builds.json), exact `startup_flash_profile()` and compiler guards, `inspect_flash.py` SOP1 timing/cache validation, and153 passing capture tests. The final guarded RAM no-tail executable is `2829eae05cd96f5f7bfe36ac852d6904341c513aba51639a0e800bb171b735f5`. New awake/Standby candidates preserve15,804 early bytes and require independent exact-prefix review before root programming. Historical12.5 falling capture/prefix/sector remain byte-identical with startup disabled.

**Provenance:** recorded after the bench owner reported all three complete image comparisons and selected no-tail cold qualification. At this entry's creation, the new flash builds existed offline; installation, cold image equality, Standby/SBF and energy measurements remained root-owned qualification steps. Warm RAM timings are not cold-start or battery-energy measurements.

## 2026-10-26  Keep the earlier SD clock transition explicit and separate callback rescheduling from savings

**Why:** three alternating RAM A/B pairs passed complete camera-source/SD equality after moving the clock transition before CMD7. The raw post-CSD window fell by 2.840048 ms at the median, but approximately 0.4 ms of frame validation moved outside that window. Subtracting only fully nested measured frame-validation intervals leaves an observed 2.440655 ms sequence improvement. ACMD41, SCR/readiness and slot scanning also varied, so this does not establish a whole-cycle or energy gain. Exact build/host admission and a separate ECK1 record keep the experiment reviewable while the installed cold-qualified firmware remains unchanged.

**Rejected:** silently promoting the RAM result to flash/Standby, reporting rescheduled camera work as eliminated work, subtracting unrelated or partially overlapping intervals, or attributing card initialization variation to the divider change. The driver owns the CSD/state/timeout rationale; this entry owns experiment admission and interpretation.

**Evidence:** [six-run evidence and replay](evidence/2026-10-26-sd-early-clock/README.md), `build.py --sd-early-run-clock`, `bench.py`, `test_sd_early_clock.py`, and [SD transport notes](../sd-storage/NOTES.md). The disabled-option control remains byte-identical to `2829eae05cd96f5f7bfe36ac852d6904341c513aba51639a0e800bb171b735f5`; all 160 capture tests passed. No NOR programming, card erase, cold-power cycle or new energy integration occurred in these tests.

## 2026-10-26  Supplement dark-scene storage tests with sensor patterns and same-speed source comparisons

**Why:** the requested twenty-image 25 MHz campaign passed complete original-camera-RAM equality, but its nearly black scene exercised only a narrow sample range. Two additional sensor-generated diagonal grayscale captures broadened the data patterns while retaining the complete MIPI-to-RAM-to-SD path. Each passed full readback at the same25MHz rate and independent PNG sample checks; the first normal slot was also reread unchanged after all later writes. Four long exposures tested progressive publication with80 immediate LINE snapshots. Firmware proof records retain clock, ownership and controller errors for every operation.

**Rejected:** treating a plausible PNG or card acceptance alone as byte integrity, quietly lowering the read clock, hiding retries, calling dark frames broad data-pattern coverage, or generalizing these twenty observed RAM trials into analog signal-margin measurements, formal SD compliance, cold-flash/Standby qualification or energy savings. The current installed12.5MHz Standby build remains unchanged; this campaign intentionally measures digital storage correctness.

**Evidence:** [twenty-image campaign, supplemental patterns and preservation reread](evidence/2026-10-26-sd25-twenty/README.md), independently rechecked proof/hash archive and the final live checkpoint in [AGENTS.md](../../AGENTS.md). User reported the replacement card and removal of the LP8 probes; no wire capture occurred in this campaign.

## 2026-10-26  Promote the tested25 MHz startup profile to normal flash and Standby

**Why:** the user explicitly selected25MHz as active firmware after twenty full source-RAM/readback comparisons, two sensor patterns, a preservation reread and an additional lit-scene image passed on the current card with probes removed. The exact reviewed startup/no-tail flash admission now allows25MHz alongside12.5MHz. Cold awake slot47 passed original-RAM equality; the normal Standby slot48 passed full readback/PNG decoding and warm recovery, with SBF=1/PDDS=1 and the flag reader's attribution limitation retained. Independent64KiB NOR readbacks and unchanged following4KiB checks passed for both images. Canonical build commands now select25MHz explicitly; historical defaults remain unchanged.

**Rejected:** leaving active firmware at12.5MHz after explicit promotion, broadly admitting experimental flash profiles, enabling the earlier clock switch/tail wait/receive-IDMA/DMA-WFI/electrical experiments as part of a frequency promotion, weakening exact recovery or completion guards, or presenting warm stress tests as cold/Standby evidence. Analog margins, production reliability, power-loss behavior and a new energy baseline remain separate work.

**Evidence:** [active25MHz promotion and reproducible qualification](evidence/2026-10-26-sd25-active/README.md),162 capture tests,32 SD driver/clock/trace tests and14 recovery tests. A separate12.5MHz rebuild remained byte-identical. Exact new recovery prefixes preserve all20 literals,1,774 disassembly rows and the15,804-byte early load; only receiver CRC words differ. Installed Standby sector `c68593cebeddf5b9c24f85249505ae719dd1ea73d11f309e3a8553e9c1a9fa47`.

## 2026-10-26  Display bounded error codes then shut down through a separate failure path

**Why:** the user requested the agreed red codes, repeated five times with 100 ms on, 400 ms between pulses and 2,000 ms between sets, followed by shutdown while preserving UART recovery. Keeping the old solid-red awake park would continue draining power. A self-contained ROM-loaded engine can also handle sensor initialization or late-loader failure without calling unverified receiver/storage code. The last set ends with 400 ms dark; the inter-set dark interval is 2,000 ms total. Codes 1 and 6 remain reserved because their battery/index detectors do not exist; code 8 is a new explicit prototype category for internal/guard failures rather than misleadingly calling them camera or SD failures.

**Rejected:** replacing successful-save idle/commit checks with a permissive failure gate, reporting a reset SD controller as proof that the card is idle, entering late code on a stale `RLOK`, recursively cleaning storage from a camera callback, keeping NOR in deep power-down across ROM restart, or claiming unchanged cold-start latency. The failure engine may forcibly abandon the current transaction after bounded ordinary cleanup, as required by the new shutdown instruction, but preserves its nonzero error/ownership history. It does not qualify SD power-loss preservation. Invalid deep-mode prerequisites fall back to LEDs-off shallow WFI; arbitrary ROM failures, hangs and unrecoverable HardFaults remain outside the signaling guarantee. The existing post-arm allocation scan and full linear-frame buffering remain unchanged.

**Evidence:** [error behavior and timing](ERROR_SIGNALS.md), `error_signal.c`, `error_codes.h`, `error_build.py` and six passing scheduler/safety tests in `test_error_signal.py`. The independently reviewed candidate retains all 20 recovery literals and 1,782 unchanged disassembly rows outside the six failure-loop bytes and two CRC words. Its prefix grows from 5,140 to 6,500 bytes; the early receiver remains 15,804 bytes. Exact new prefix/sector admission is recorded in `../capture-timing/recovery_gpio/check_park.py` and `../capture-sd/low_power/readback_recovery/run.py`; all 14 existing readback tests and both gates' altered/truncated/cross-pair rejection checks pass. Hardware qualification and final installed state belong to the experiment evidence and bench checkpoint, not this admission decision.

## 2026-10-26  Runtime error code must survive frame DMA; prefix-only tests missed the overlap

**Why:** a real CMD17 data CRC failure after the user removed the CLK resistor
correctly selected code4, but camera DMA had overwritten the prefix-resident
blink engine. The processor executed image bytes at0x34181846, incurred an
unaligned access, and entered the permanent solid-red HardFault loop. The
handler interval0x34181840..0x34181D64 lies inside the packed frame interval
0x340000A0..0x341D2400. This supersedes the preceding decision's assumption
that one prefix engine can serve both early and runtime failures. It violated
the existing no-prefix-code-after-DMA constraint in capture-timing.

**Rejected:** calling prefix code after receiver arm; treating pre-capture
synthetic signaling or safe separately linked RAM tests as qualification of
flash errors after DMA; interpreting solid red as a specific SD code; or
inferring that removal of the resistor is the proven electrical cause from
one CRC report. Runtime error code must be in verified persistent executable
RAM outside frame and guard ranges, with an error regression after real DMA
or equivalent full-frame overwrite. The early prefix path may remain separate.
Implementation/reinstallation is deferred until after the requested no-reset
diagnosis; the installed image remains defective at this checkpoint.

**Evidence:** [saved registers, stack, correct SD record and overlap diagnosis](evidence/2026-10-26-error-handler-overlap/README.md).
Current PC0x34301E2C, stacked PC0x34181846/LR0x34302307/r0=4,
CFSR0x01000000/HFSR0x40000000, and live instruction13CE match the exact
failure chain. SD error14/stage5/CMD17/STA2 confirms a data CRC failure;
cleanup_error10 remains explicit. No reset, power change, target write or
firmware download occurred during diagnosis. Prior frozen tests are retained
as historical evidence with their uncovered lifetime gap, not rewritten.

## 2026-10-26  Copy and verify the error engine into reserved SRAM before receiver work

**Why:** only176 bytes remained in the fixed early receiver range, while the
error engine occupies1316 bytes. Copying the self-contained engine, padded
to1536 bytes, from the ROM-loaded prefix to reserved343C8000..343C8600 before
any terminal/camera path keeps the15,804-byte early load and recovery guard
unchanged. Each boot revokes prior proof, rejects enabled D-cache, copies and
compares every word, invalidates I-cache, then publishes fresh ECP1. Runtime
calls use that destination; only pre-arm copy/context failure may use the
prefix. The linker reservation excludes the frame, stack and other helpers.

**Rejected:** continuing post-arm calls into the prefix, trusting a retained
copy after reset, duplicating the engine in the tightly bounded early load,
or assuming relative code is relocatable without inspecting its linked
branches/literals. Build audit rejects external dependencies, including M55
hardware-loop targets. Prefix padding grows the ROM image to6720 raw bytes;
no new boot-latency or energy claim is inferred from unchanged early-load size.

**Evidence:** [corrected builds and complete qualification](evidence/2026-10-26-error-handler-fix/README.md).
182 capture tests,33 reader/recovery tests and18 exact/rejected identity cases
passed. An explicit post-frame flash regression acquired1,909,600 bytes,
validated FRAME/STOP/guards, confirmed old prefix overwrite and exact copied
engine bytes, then displayed code4 and entered Standby. Separate normal
firmware reproduced the real CMD17 CRC failure with the resistor removed and
also displayed five four-blink sets before about8.06mA. CFSR/HFSR stayed zero;
UART recovery worked during signaling and after both shutdowns. Guarded
SBF1/PDDS1/STOPF0 observations retain their attribution limits. Full NOR
readbacks and following4KiB checks passed; the uninjected normal build is
installed. The resistor-free SD link remains unreliable and is not qualified
by this error-handling fix. Existing photos were not reread; no SD erase or
image-sector write occurred in these tests.

## 2026-10-28  Compare post-STOP power using bounded RAM-only holds before SD initialization

**Why:** board-level power attribution needs matched observable states, not a
guess from the shape of a complete-cycle trace. Explicit RAM-only modes wait
for complete validated FRAME/STOP, hold for 200 ms between markers 11/12, then
perform the normal save. Controls separate stopped sensor from sensor reset,
and reset sensor with retained receiver from receiver/PHY disabled while
retaining APB/kernel clocks. Exact RAM proofs bind the conditions to the frozen
build and preserve existing camera, storage and terminal guards. Separate
normal/preinitialized/long-exposure experiments measure scheduling effects.

**Rejected:** inserting delays inside an active SD transaction, promoting
diagnostic holds into normal flash firmware, interpreting sensor reset as
removal of all camera power, or attributing the entire retained board current
to the MCU. The optional Ethernet pair is identity-checked and bounded, but its
first control failed MDIO turnaround before any BMCR write; do not infer a
PHY power-down saving or retry with unchecked register writes. Its helper
restores GPIO configuration and records exact BMCR cleanup when successful.

**Evidence:** `build.py`, `runtime.c`, `magic_runtime.inc`, `power_csi.inc`,
`power_phy.inc`, `bench.py`, and `test_power_probe.py`;
[aligned ablation results](../../docs/power/evidence/2026-10-28-aligned-ablation/README.md).
The normal installed NOR/recovery prefix was not modified. Measurements and
same-image SD readback checks are scoped in the linked evidence rather than
treated as production electrical qualification.

## 2026-10-28  Qualify recovery before disabling both debug-in-sleep and the UART listener

**Why:** a temporary RAM stub deliberately masked and cleared all interrupts,
then performed a matched busy interval followed by shallow WFI with
`DBG_SLEEP` clear and no rail/clock changes. The current trace showed a lower
plateau, but the first HOTPLUG observation failed before reading any proof.
With the UART interrupt disabled, a UART pattern alone could not request its
software reset. ST-LINK hardware-reset attempts reported success without
restoring verified AP1 access. A cold cycle with UART stimulus finally restored
the exact unchanged flash early park; the retained sleep proof was abandoned.

**Rejected:** calling that plateau proven WFI entry or total CPU power,
claiming a live PC/register check that never succeeded, treating a successful
reset CLI message as recovery, assuming SRAM survives ROM reset, or carrying
this IRQ-masking diagnostic into production shutdown. Future experiments must
first qualify an independent recovery path and a usable evidence channel.
Normal firmware's UART recovery remains unchanged; this restriction belongs
to the temporary diagnostic, which is not a normal build option.

**Evidence:** [aligned ablation evidence and recovery limits](../../docs/power/evidence/2026-10-28-aligned-ablation/README.md);
private `tmp/bringup/power-ablation-20261028/sleep-probe/`, `sleep01/`, and
its subsequent recovery records. The prepared stub was independently read
back before launch; no post-launch proof, live WFI PC or unchanged-register
qualification was obtained.

## 2026-10-28  Correct the shallow-sleep recovery attribution: no runtime UART listener was identified

**Why:** a subsequent source review found that normal recovery uses the
experimentally observed ST-LINK BREAK-to-NRST behavior and a polled C0 pulse
detector in the early prefix. The normal capture runtime does not contain the
UART interrupt-driven software-reset listener assumed in the preceding entry.
Although the temporary sleep probe masked interrupts and its warm recovery
attempts failed, that does not establish a causal connection between the two.
The cause of unavailable AP1 after the attempted resets remains unresolved.

**Rejected:** retaining the unsupported claim that masking a UART listener
caused recovery failure; inventing a new listener as a purported restoration
of existing functionality; or treating the lower current plateau as qualified
sleep entry. Use finite timer-driven wake and an awake proof park for the next
diagnostic, with cold recovery remaining the separately demonstrated fallback.

**Evidence:** the early prefix's `recovery_gpio.c`,
[VCP recovery design](../capture-timing/recovery_vcp/README.md), current
`runtime.c`, and the [separate evidence correction](../../docs/power/evidence/2026-10-28-aligned-ablation/CORRECTION.md).
Earlier sealed measurement bytes and the historical interpretation remain
unchanged; this later entry supersedes that specific causal explanation.

## 2026-10-28  Sample MDIO before the PHY advances on rising MDC

**Why:** the original Ethernet probe sampled MDIO after the 5 us MDC-high
wait. A standalone address scan returned `000F` and `8263` at address0:
exactly the expected `0007/C131` shifted left one bit with an idle1 appended.
The apparent second-register turnaround failure was its first data bit.
LAN8742 timing allows PHY output to change immediately after MDC rises.
Sampling the stable value before that edge returned correct IDs and repeated
BMCR3000; separate isolated-board A/B/A runs verified power-down and exact
BMCR restoration. The source helper now uses that qualified sample placement.

**Rejected:** interpreting the initial error as an absent/unpowered PHY,
wrong pin map or missing MCU-generated oscillator without evidence; retrying
unchecked writes; or treating the earlier host model as timing coverage when
it replaced `phy_clock_bit`. The new host model keeps that routine and tests
the old sample placement as an intentional failing mutation. Exact BMCR
restoration is not proof of identical negotiation state/current waveform,
because clearing power-down resets the PHY internally. This experimental
source fix is not installed in NOR, and its integrated capture/save profiles
still need hardware reruns after camera/SD reconnection.

**Evidence:** [isolated Nucleo results and frozen mdio02/mdio03/phy01/phy02 records](../../docs/power/evidence/2026-10-28-isolated-nucleo/README.md);
LAN8742 [§5.6.5/table5-15](https://www.microchip.com/content/dam/mchp/documents/OTH/ProductDocuments/DataSheets/DS_LAN8742_00001989A.pdf#page=112);
`power_phy.inc`, `test_power_phy.py`, and 13 passing MDIO/power-probe unit tests.
Both corrected RAM Ethernet profiles compile offline. Historical campaign
sources and evidence bytes remain unchanged; the normal installed firmware
and all hardware were untouched by this source maintenance.

## 2026-10-28  Keep the unused Nucleo Ethernet PHY powered down during normal capture

**Why:** isolated-board measurements showed the unused LAN8742 is a material
board load, and the user requested firmware power-down before making physical
board changes. The corrected MDIO method supports a bounded one-shot helper
after receiver arm and the checked late load, before SD initialization. It
verifies identity and stable BMCR, sets power-down once, verifies it twice,
then restores its GPIO configuration and only the clock bits it added. A
stable already-down PHY is accepted without a write. Keeping the PHY down
through save and shutdown preserves the benefit; clearing power-down would
reset the PHY internally and reintroduce an unrelated camera load.

**Rejected:** treating optional Ethernet failure as a failed photo; retrying
uncertain writes; restoring BMCR at the end of the cycle; running the 200 ms
hold-and-restore attribution experiment in production; adding MDIO work to
the exposure-start path; or inferring PHY state during RAM READ operations.
Warnings remain in the separate `ETH1` proof and capture continues. An
unverified write or GPIO/clock cleanup is not a qualified power saving.
Clock/profile changes require requalification. Fixed early-load size alone
does not prove unchanged startup timing because late payload and BSS grow.

**Evidence:** `board_eth_powerdown.inc`, `test_board_eth_powerdown.py`,
`test_board_eth_bench.py`, the [selected build instructions](README.md#build-the-selected-profile-explicitly),
and [installation/qualification evidence](evidence/2026-10-28-ethernet-powerdown/README.md).
The RAM candidate saved slot 126 and passed full original-camera-RAM equality;
baseline slot 122 also passed on the selected twisted CLK/GND wiring. The
normal Standby receiver `69c5a5c0cc434eb7496371d9e5b9c007db346b8bb7b9a1a650c90f0eade79d28`
was installed with independent physical NOR readback. Its recovery instructions,
referenced literals and relocated error engine are preserved; only two prefix
receiver-CRC words change. Full cold-cycle image checks and power comparisons
are recorded separately in the campaign evidence as they complete. This
production helper supersedes the preceding entry's installed-firmware status;
the separate attribution probe and its historical evidence remain unchanged.

## 2026-10-28  Keep the sensor-to-SD attribution gap an explicit diagnostic

**Why:** the user requested a visible separation between camera capture/STOP
and SD initialization so the synchronized current trace can distinguish their
activity. The optional 200 ms gap waits for the existing FRAME validation and
acknowledged sensor STOP before the first SD command. It retains the normal
Ethernet power-down, storage, recovery and error paths, adds finite waits and
a separate `GAP1` proof, and brackets the interval with existing-pin marker
events 11/12. A FLASH form permits cold card startup to be measured, while an
awake RAM form preserves the frame and proof for verification.

**Rejected:** adding this delay to normal capture; substituting the older
hold-and-PHY-restore experiment; beginning the gap at an assumed exposure
deadline; inferring STOP solely from a current drop; or treating a zero host
command count as proof the card consumes no power. The card remains powered
but uninitialized by the host, the stopped camera/receiver rails remain on,
and the CPU waits awake. This interval is an aggregate attribution baseline,
not an isolated SD idle-current or sensor-only measurement. A warm RAM run
does not establish cold SD initialization behavior. Total diagnostic energy
includes the deliberate extra wait and is not a production improvement.

**Evidence:** `sd_init_gap.inc`, `test_sd_init_gap.py`, build/host admission
checks and [diagnostic instructions](README.md#diagnostic-gap-between-sensor-stop-and-sd-initialization).
Offline tests cover completion, counter wrap/stall, readiness timeout, capture
failure, unexpected storage ownership/commands and marker failure. With the
option disabled, the rebuilt receiver, prefix and 64 KiB sector exactly match
the installed Ethernet candidate (`69c5a5c0...`, `2b9724bc...`, `a10e4894...`).
The gap build retains the 15,804-byte early load and relocated error engine;
only the two approved receiver-CRC literals change in its recovery prefix.
Exact build records and hardware qualification belong in the
[gap campaign evidence](evidence/2026-10-28-sd-init-gap/README.md); these offline
checks alone make no current, energy, image-integrity or installed-state claim.

## 2026-10-28  Qualify sensor auto-stop in RAM without extending the recovery prefix

**Why:** Context 0 repeat count 1 and next context 4 are documented to end a
context sequence, but UM2602 also describes a first-two-frame exception. The
firmware must measure the sensor's actual frame counter and exposure strobes
instead of inferring single-frame behavior from the STM32's one-frame snapshot.
The opt-in RAM experiment preserves normal frame validation, counts actual
sensor STOP writes, observes autonomous FSM 2 with a finite timeout, and checks
stable FSM/counter/strobes again after the SD save. Sensor count and STROBE
count are independent observations; both must be one to qualify one exposure.

**Rejected:** Promoting an unmeasured assumption of exactly one frame; silently
issuing a fallback STOP on the tested success path; treating a two-frame
diagnostic outcome as a capture error or a one-frame success; adding an
intentional waiting gap; and extending the cold recovery prefix merely to
answer this sensor-behavior question. Exploratory cold builds encountered the
fixed early-load and error-engine boundaries. Their artifacts are preserved,
but the unqualified layout adaptations were removed and FLASH/Standby use of
`--sensor-autostop` is explicitly rejected. Cold-boot integration is deferred.

**Evidence:** `sensor_autostop_transform.py`, `sensor_autostop.inc`,
`test_sensor_autostop.py`, and the host proof validation in `bench.py`.
[Campaign evidence](evidence/2026-10-28-sensor-autostop/README.md) owns measured
results, original-frame/SD comparisons and qualification limits. Frozen RAM
diagnostic `ram-auto-v2` is SHA-256
`5bf9e515bb28d74efa3cdee21c9a9f373fedbc3c36b73dd954e136f6df348e65`;
its separate manifest-description correction does not alter the bytes. The
disabled default must reproduce the existing normal RAM binary and all three
normal FLASH identities (receiver, prefix and sector). No new recovery
allowlist or production auto-stop selection is part of this decision.

## 2026-10-28  Integrate strict single-frame capture with one minimal prefix transaction

**Why:** After the RAM qualification, the user explicitly requested automatic
single-frame behavior in normal firmware. This supersedes the preceding
decision to defer cold integration. The existing manual-exposure array already
writes mode 2 at `0x044C`, and no intervening context command changes it. Reuse
the later duplicate write for the consecutive little-endian context values
`01 00 04 00` at `0x048C` rather than adding a new boot-prefix section. The
production observer requires exactly one frame and one exposure strobe,
zero explicit STOP writes, and stable standby after the save.

**Rejected:** Expanding or relocating the recovery/error-engine architecture;
silently relaxing the historical prefix checker; and claiming that a
post-START register read proves the earlier counter was zero. The first
attempt to use a four-byte `write_value` call expanded its shared helper and
moved recovery code, so it was rejected. The existing byte-array writer avoids
that change. A separate full-image prefix fingerprint and two fixed CRC-word
locations bound the production change. AST schema 2 explicitly labels its
post-START readback and counts from reset. The old explicit-STOP profile and
AST schema-1 RAM experiment remain exactly reproducible.

**Evidence:** `sensor_autostop_transform.py`, `sensor_autostop.inc`,
`single_frame_prefix.py`, the late-code layout audit and native-C tests in
`test_sensor_single_frame.py`. The [single-frame promotion
campaign](evidence/2026-10-28-sensor-single-frame/README.md) owns cold
qualification and installed-state results. Its offline packaged audits prove
unchanged recovery instructions and all twenty recovery literals, unchanged
fixed error bridge/engine, and the original 15,804-byte early receiver load.
All five historical binary identity comparisons passed; 261 source-bound
offline regression tests passed with no source changes during the run.

## 2026-10-30  Reintroduce SD DMA sleep only after complete-frame publication and finite wake qualification

**Why:** The user explicitly requested CPU sleep during DMA on the current SD
hardware. The older disabled experiment cannot simply be enabled: its failed
WFI attempts remain unresolved evidence. The new opt-in magic-slot profile
retains the current single-frame/Ethernet-down/25 MHz configuration, adds BSEC
run/sleep-clock checks, and uses the existing 1 ms SysTick for bounded wake and
wall-time accounting. BSEC was retained in the successful isolated-board WFI
probe; this difference is a hypothesis, not proof of the old failure's cause.
Sleep requires an already validated frame and stopped sensor, so camera
deadlines never depend on a CPU cycle counter that pauses in WFI.

**Rejected:** Forcing a completed frame by delaying the existing streaming
path; sleeping while the PIO producer still needs service; treating WFI counts
as proof of actual clock gating; interpreting DWT sleep spans as wall time;
adding storage interrupts before the timer-wake path is qualified; expanding
the fixed early boot/recovery image; and installing a candidate based only on
offline tests. The address-taken millisecond callback lives in late-loaded
storage code to preserve the 15,804-byte early receiver boundary. The
RAM-only no-write probe deliberately retains a failed photo outcome even
when its sleep test passes.

**Evidence:** `dma_sleep.inc`, `dma_sleep_probe.inc`, the opt-in integration in
`magic_runtime.inc`, driver/host/native tests, and campaign
`tmp/bringup/sd-dma-sleep-20261030/`. Hardware qualification was initially
blocked by zero measured Joulescope input voltage and absent ST-LINK; no
candidate was installed at that boundary. Measured results and final installed
state must be recorded separately before promoting the option.

## 2026-11-07  Assert PD7 before the existing boot guard and float it only at Standby entry

**Why:** the user selected Arduino D9/CN14.2 (PD7) to hold the new button/MOSFET
latch on through capture and saving. A fixed 76-byte stackless hook after the
existing padded error engine asserts HIGH before the original reset handler,
then resumes its exact startup and UART-recovery path. Only the reset vector
redirects entry; original recovery instructions, twenty literals, loader and
bridge stay at their reviewed addresses. The option remains explicit and
disabled builds reproduce the qualified October 28 firmware.

**Rejected:** inserting early HOLD code into a shared C routine that could
relocate the tightly bound recovery layout; allowing a LOW glitch while
changing PD7 to output; releasing HOLD during UART park, capture/save or error
flashes; and relying solely on implicit Standby pin behavior. Success and error
shutdown explicitly select input/no-pull immediately before WFI, preserving
ODR HIGH. Refused Standby retains HOLD; an unexpected WFI return immediately
reasserts it. GPIO assertion cannot persist through hardware reset or precede
ROM execution, and firmware cannot guarantee the external RC's rail ordering.

**Evidence:** `gpio_hold_prefix.py`, `gpio_hold_transform.py`, opt-in builder
and host package audits, and their mutation/native tests. The
[offline evidence](evidence/2026-11-07-gpio-hold/README.md) freezes both
candidate builds, exact machine-code checks, 318-test regression result plus
the separately enabled linked-artifact test, and unchanged rollback hashes.
The copied error engine remains position independent and within its original
1,536-byte reservation; early receiver loading remains 15,804 bytes.
The user disconnected the board for assembly, so no new image was installed,
no live recovery admission was added, and physical GPIO/RC/AUX shutdown
qualification is consciously deferred until reconnection. No DMA-sleep or
potentiometer-ADC implementation is bundled into this change.

## 2026-11-08  Keep HOLD code unchanged while recording the accepted no-delay latch policy

**Why:** the user selected an SPDT trigger capacitor and explicitly omitted
the separate Q2-gate C1/D1 shutdown delay. PD7's existing input/no-pull
release lets R2=100kohm discharge Q2's gate without changing any firmware
instruction. Contract schema 2 therefore records that an extra off delay is
not required by the accepted prototype policy, while explicitly retaining
unqualified AUX-before-main shutdown ordering. The exact schema-1 contract
remains recognizable for historical package inspection; it is not rewritten
or silently interpreted as the newer hardware choice.

**Rejected:** treating the old manifest's off-delay requirement as current
user policy; changing executable release behavior unnecessarily; altering
frozen November 7 evidence; or admitting arbitrary combinations of old/new
contract fields. Both schemas require exact values and types. Neither
metadata acceptance nor an offline package audit adds a live recovery
allowlist entry or establishes the state of the physical latch.

**Evidence:** `gpio_hold_transform.py`, the strict contract checks in
`bench.py`/`inspect_flash.py`, and the updated HOLD tests. All 320 offline
capture tests passed, including the real linked Standby release code.
Rebuilds in `tmp/bringup/gpio-hold-spdt-20261108/` reproduced both November 7
HOLD candidates byte for byte and the disabled October 28 receiver, prefix
and sector byte for byte. Independent package audits passed for both current
and both frozen candidates; all 173 files bound by the November 7 archive's
SHA256SUMS remained unchanged. The [power notes](../../docs/power/NOTES.md)
own the external circuit decision. No instrument, installed firmware, NOR,
SD, or live recovery permission was changed.

The startup check remains an estimate: the [October 17 cold-boot size
matrix](../boot-timing/optimization-results-2026-10-17.md) measured
22.563–23.228ms from the target supply's 0.5V crossing to first GPIO for a
1,472-byte ROM image. Its observed 0.262ms/KiB slope predicts about
24.19–24.86ms for the 7,840-byte HOLD image. Use roughly 25ms as an estimate
and 30ms as a planning budget, not a worst-case guarantee. The later
[2.2-ohm runs](../../docs/power/evidence/2026-11-06-series-resistor-tested/README.md)
reached exposure at 24.584–25.268ms from current onset, a different reference
and later firmware event. The new SPDT latch is not connected yet; its
LiPo/ramp, capacitor tolerance/bias, physical PD7 transition and minimum
press duration are unmeasured. Reset-only or RAM-entry timing cannot replace
power-on-to-HOLD measurement. No ADC or DMA-sleep work is bundled here.


## 2026-11-09  Make PA2/A3 HOLD canonical while preserving exact UART recovery

**Why:** the user moved the exposure potentiometer to Arduino A0–A2 and
selected adjacent A3/CN4.4/PA2 for the power latch. Schema 3 binds this pin,
while exact schemas 1/2 remain historical PD7 profiles. Startup preloads HIGH,
selects push-pull/no-pull low-speed output, and branches to the original reset
handler without a stack. Only PA2's fields change. Capture, saving, error
flashes, recovery, awake completion and refused-Standby paths keep HOLD HIGH;
success/error WFI paths float it, and an unexpected return reasserts it.

**Rejected:** retaining PD7 as the current wire plan; driving the old A3 pot
LOW after it became HOLD; moving existing UART guard instructions/literals;
or using the original HOLD tail address because the native USB selector
already occupies it. The 76-byte PA2 entry is instead at 0x34181DF0 inside
unused fixed error-copy padding. Actual error instructions end at 0x34181DC8,
with 40 bytes of zero fill before HOLD and four after it. The complete
1,536-byte copy remains fixed; only its real error engine is executable in
that copied context. Branches and PC-relative references into the boot-only
padding are refused, as are changed boundary symbols, hook bytes or fill.
The USB tail at 0x34181E40 remains available. No GPIO-HOLD pin alias is accepted
as hardware qualification or added to any live recovery allowlist.

**Evidence:** [offline build, audits and regression results](evidence/2026-11-09-a3-hold/README.md),
`gpio_hold_prefix.py`, `gpio_hold_transform.py`, `error_build.py`, and strict
package inspection. PA2 success/error release groups are 70 bytes with WFI
at offset 40; all original early startup/UART/loader/bridge bytes (apart from
the reset vector and two receiver CRC words) remain identical to October 28.
All twenty UART literals and 15,804-byte early receiver loading are unchanged.
The user confirms the board is disconnected: pin transitions, latch timing,
rail ordering and live recovery remain unmeasured, and no instrument, NOR,
SD or installed firmware was touched. The disabled-HOLD receiver, prefix and
sector reproduce October 28 exactly; historical PD7 artifacts stay unchanged.

## 2026-11-09  Keep the exposure-pin migration diagnostic-only

**Why:** after the A3 HOLD and A0–A2 pin migration, the user explicitly chose
“Remap existing diagnostic; integrate exposure control later.” Normal captures
therefore retain their fixed exposure. The diagnostic uses A0 LOW, A1 wiper
and A2 HIGH; it does not apply readings to the sensor.

**Rejected:** expanding this wiring update to include the planned exponential
shortest-exposure-to-1-second mapping, or treating the remapped ADC diagnostic
as commissioned capture control. ADC settling, endpoint calibration and its
effect on the cold-start budget remain part of that later integration.

**Evidence:** user's November 9 clarification; the current
[control diagnostic](../control-smoke/README.md) and
[offline combined candidate](../usb-ptp/evidence/2026-11-09-a3-hold/README.md).
This confirmation changes no firmware binary or hardware state.

## 2026-11-13  Move HOLD to PE9/D3 after the external A3 toggle failure

**Why:** the user moved the latch wire to Arduino D3 and requested camera
firmware plus a hardware smoke test before changing schematic/assembly
instructions. The official MB1940 C02 schematic identifies D3/CN13.4 as PE9,
on the MCU's main VDD supply. Contract schema 4 binds this exact pin, while
schemas 1/2 (PD7) and 3 (PA2) retain their original meanings. Existing masked
GPIOE users (recovery PE1/PE6, marker PE0, SD PE4) preserve PE9.

**Rejected:** continuing to rely on a pin whose output was not observed
physically, diagnosing the cause of A3 damage from internal IDR/ODR alone,
changing an entire GPIO port, moving the UART guard, or silently reinterpreting
old contract schemas. The early PE9 preload requires a wider instruction but
uses former alignment padding: the complete hook remains 76 bytes at
0x34181DF0 and leaves four zero bytes before the USB selector. Boot-only
padding is still unreachable from the copied error engine. Only PE9 floats
at the final Standby boundary; active, error-display, recovery and refused
paths keep HOLD HIGH, and unexpected WFI return reasserts it.

**Evidence:** [D3 offline build and qualification](evidence/2026-11-13-d3-hold/README.md)
freezes the exact sources and binaries, full package audit, 324 passing tests
without skips, six historical HOLD package checks, and unchanged no-HOLD
October28 receiver/prefix/sector comparisons. The control-smoke folder owns
the physical A3 observations; the combined USB campaign owns installation,
external D3 levels and UART recovery. This capture-only work performed no
hardware access and makes no new latch/rail timing claim. Schematic and
assembly edits are intentionally deferred until the requested smoke test.

## 2026-11-13  Move HOLD to PD12/D8 and retire its physical phase-marker output

**Why:** after the D3 migration, the user explicitly requested a simple move
to D8 and reload, with no further testing. The existing phase header maps
D8/CN14.1 (also CN15.21) to PD12. Schema5 binds that pin while preserving
schemas1–4 for historical packages. Startup assertion and final Standby
release retain the same policy and fixed boot/recovery layout.

**Rejected:** leaving the PD12 phase generator active on a power-HOLD pin,
where its LOW initialization and pulses would interrupt the latch. The
HOLD profile substitutes no-GPIO phase functions; the callers' RAM counters
and independent PD0 exposure mirror remain unchanged. No new test campaign
or additional behavioral changes are included in this user-requested reload.

**Evidence:** `gpio_hold_prefix.py`, `gpio_hold_transform.py`,
`phase_gpio_hold.inc` and the explicit disabled phase-marker build metadata.
Build/package checks are required before reload. The root campaign at
`tmp/bringup/d8-hold-20261113/` owns the final combined package, programming
readback and installed-state record; this offline work does not claim a new
capture, latch timing or power measurement. Schematics remain deferred.

## 2026-11-13  Integrate calibrated knob polarity without changing the early recovery layout

**Why:** after the live dual-knob endpoint/center comparison, the user asked
for exposure and analog gain control. The exposure pot increases electrically
clockwise while ASA increases counterclockwise; invert only exposure so both
physical controls increase their setting counterclockwise. The user then
accepted a0.5s maximum instead of1s. Constant1280-pixel lines permit the full
requested half-second with coarse62813/frame64813 and a2000-line reserve;
1236-pixel lines with that reserve reach only about488.366ms. The selector
already occupies a checked RAM image, so it owns ADC sampling and a fixed
sensor timing helper; the capture prefix needs only two audited relocations
at composition. All UART, D8 HOLD and copied error-engine bytes remain exact.

**Rejected:** overflowing16-bit coarse/frame fields at1s, silently clipping
the new0.5s label to488ms, driving suspect PA2, moving the fixed recovery code,
claiming ASA calibration from an analog-gain setting, or turning the default
capture build into a package that silently depends on an absent selector.
The explicit controls option requires the combined package; disabled builds
reproduce the previous D8 receiver/prefix/sector exactly.

**Evidence:** `knob_transform.py`, `knob_capture.inc`, the shared selector ABI
in `../usb-ptp/capture_controls.h`, and root campaign
`tmp/bringup/knobs-capture-20261113/`. Final capture-v3 receiver35032bytes has
SHA256 `8cd86fa71e1cd2422897558567b9c66035c66ca103cea537e50ad3ebd4d5caaa`;
mandatory HOLD/error/UART audits pass.327 offline tests passed with4 optional
linked checks skipped; all25 tests in the two linked HOLD suites then passed
against that exact candidate, covering the skips. Default reproduction is
recorded in `baseline-repro.json`. No hardware or Git access occurred here.

## 2026-11-13  Freeze configured or applied controls metadata before its first publication

**Why:** the152-byte front reservation fits the128-byte CKN1 record plus24zero
bytes without changing image offset156 or the3730-sector slot. Streaming can
publish image data before FRAME validation, especially at long exposure. A
single snapshot immediately before the first nonzero publication can honestly
be state3/configured or state4/applied; post-FRAME checks later update only the
RAM control record. Actual coarse/line/frame/margin and applied analog0068/
digital006A readbacks must match before the capture receives full validation.

**Rejected:** changing an already-offered first sector, blocking all streaming
until FRAME merely to upgrade metadata, presenting configured values as applied
readback, or rewriting historical all-zero metadata as though it had controls.
Existing3s producer/final waits and post-FRAME1s automatic-stop budget remain;
nominal timing uses the frozen160.8MHz clock and is not a calibrated measurement.

**Evidence:** actual-source native tests exercise bounds, read errors, gain
mismatch, CRC rejection, record state and snapshot immutability. Host reporting
uses the known CKN1 schema and preserves configured/applied distinction. Exact
sensor offsets are corroborated by ST's driver and UM2602; the helper records
actual EXP_COARSE_INTG_MARGIN and checks frame >= coarse + margin +7 rather
than inventing a register write to resolve conflicting documented defaults.

## 2026-11-13  Leave controls hardware qualification to the user's requested test

**Why:** once the half-second controls candidate and offline checks were ready,
the user explicitly requested loading it without another verification campaign
and said they would test it. The capture-v3 executable remains frozen; the
combined-package owner records installation separately.

**Rejected:** extending this handoff into automated maximum-exposure/gain,
saved-image, timing or energy experiments, or presenting offline checks and
programming readback as qualification of those behaviors on the camera.

**Evidence:** the user's "no verify - just load and i will test" instruction;
the frozen capture-v3 identities and reproduction command in README.md. No
additional functional test or executable change accompanied this note.
