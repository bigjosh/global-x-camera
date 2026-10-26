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
