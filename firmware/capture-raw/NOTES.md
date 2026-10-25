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
