# PNG/FAT32 capture decisions

## 2026-10-20  Use bounded streaming FAT32 saves with explicit incomplete-file labels

**Why:** the user requested directly inspectable PNG photos on the prototype card. A bounded 32 KiB sink streams encoding without a second image allocation. Explicit formatting creates the selected FAT32 volume; normal saves create a unique TMP and rename only after sync/close/card-ready checks, preserving earlier files and visibly incomplete saves.
**Rejected:** automatically formatting a mount failure, overwriting an existing photo, buffering a second complete PNG, or treating rename/two FAT copies as arbitrary power-loss atomicity.
**Evidence:** commits `ecc3108d`, `5fd94243`; [implementation choices](../../docs/decisions/capture-png-sd-2026-10-20.md#implementation-decisions); [filesystem contract](fs/README.md).
**Provenance:** migrated 2026-10-24 from the user's approved prototype scope and implementation. [RAW storage](../raw-slots/NOTES.md#2026-10-24--store-packed-raw-objects-and-defer-image-encoding-to-retrieval) later superseded this active capture format; historical readers/evidence remain useful.

## 2026-10-20  Enable D-cache only under explicit SAVE ownership

**Why:** same-frame fast-none SAVE fell from 19.0995 s uncached to 2.0945 s cached with identical PNG bytes. Capture DMA had already finished, allowing the SAVE module to own D-cache while encoding and using PIO storage. It must enter from verified cache/MPU state and clean/invalidate/disable its cache before publishing completion; intermediate cached progress cannot authorize maintenance. `volatile`/DSB do not publish dirty reports to the debugger, and clearing M55's `CCR.DC` alone does not evict valid cache lines.
**Rejected:** blanket cache enabling around DMA, inheriting an unknown MPU/cache configuration, or using a successful I/O report to bypass context checks. The O2 trial's `CONTROL=0x0C` refusal was investigated without weakening the generic gate; Os remained selected.
**Evidence:** commit `5fd94243`; [cache experiment](../../docs/decisions/capture-png-sd-2026-10-20.md#v6b-cache-experiment-and-repeated-saves); [compiler-context experiment](../../docs/decisions/capture-png-sd-2026-10-20.md#compiler-experiments-and-strict-context-checks).
**Provenance:** migrated 2026-10-24 from exact same-frame hardware comparisons and preserved refusal records; this is a historical SAVE-module result, not a whole cold-cycle measurement.

## 2026-10-20  Use Standby after verified teardown and retain ownership through late shutdown

**Why:** the successful Standby branch settled near 8.2 mA at the board input versus about 77 mA peripheral-off awake and 62 mA for the intermediate Stop candidate. A monolithic shutdown addition crossed the first-frame guard, so bulk teardown moved into a separately checked late module. `LPL1`/`LPM1` keep maintenance from halting between SAVE success and shutdown; completion requires idle peripherals/media and safe context.
**Rejected:** treating SAVE-complete or an ARMED record as completed shutdown; releasing ownership before teardown; equating evaluation-board Standby with the product's externally switched-off current target. Standby loses frame/high-SRAM evidence.
**Evidence:** commit `e63a002a`; [implementation discoveries](../../docs/decisions/capture-png-sd-2026-10-20.md#post-save-standby-and-complete-cycle-energy--october-20); [qualified Standby archive](evidence/2026-10-20-low-power/README.md).
**Provenance:** migrated 2026-10-24 from measured candidates, the failed monolithic build and implemented ownership guards. Recovery policy lives with the [recovery implementation](../capture-timing/NOTES.md#2026-10-20--use-a-measured-pe6-pulse-signature-for-st-link-selected-recovery).

## 2026-10-20  Drive NOR nCS high before gating its interface and preserve ROM accessibility

**Why:** PN1 read low in AF9 despite an idle NOR controller; the cause was unresolved. Preloading high and handing only nCS to GPIO produced verified high readback before disabling XSPI and changing other pins. NOR must remain readable by ROM before the early recovery guard can execute, so deep-power-down is unsuitable for this shutdown path. BSEC clock retention also follows the documented low-power erratum.
**Rejected:** inferring chip-select level from controller idle, sending NOR deep-power-down without a pre-ROM wake path, or blindly gating every peripheral clock.
**Evidence:** commit `e63a002a`; [shutdown discoveries](../../docs/decisions/capture-png-sd-2026-10-20.md#implementation-decisions-and-discoveries); `low_power/peripherals.c`.
**Provenance:** migrated 2026-10-24 from measured pin handoff and the recorded erratum/boot constraints; the AF9 low-level root cause remains unknown.

## 2026-10-20  Do not retain GPIO pulls into devices whose Standby supply turns off

**Why:** on the stock Nucleo tree, Standby disables the switched camera/SD/NOR supplies while the SD GPIO bank and camera reset bank remain powered. The default high-impedance/no-pull state prevents those still-powered MCU pins from sustaining switched-off devices. This is a different boundary from leaving the complete board input powered.
**Rejected:** enabling GPIO pull retention as a harmless low-power tweak, or assuming D2/R23 removal also changes these target supply paths. Actual rail decay and signal leakage still need measurement.
**Evidence:** commit `e63a002a`; [schematic-derived supply paths](low_power/peripherals.md#stock-mb1940-c02-supply-paths); `low_power/completion.c`; [qualified shutdown record](../../docs/decisions/capture-png-sd-2026-10-20.md#post-save-standby-and-complete-cycle-energy--october-20).
**Provenance:** migrated 2026-10-24 from the documented schematic/code review, corroborated by the October 20 storage-agent final summary. A later chat summary saying the card remains supplied in Standby conflicts with this record and is not adopted as a hardware fact.

## 2026-10-24  Make expensive diagnostic scans optional without weakening completion checks

**Why:** repeated full-frame fingerprints dominated two roughly 450 ms phases; one uncached FNV alone took 380.690 ms while cache cleanup took 0.034 ms. The user approved a normal profile that omits those scans, optional register dumps and stack watermarks while retaining geometry, canaries, capture/SD errors, code CRC, commit, cache and idle ownership checks.
**Rejected:** treating skipped checks as passed, mixing receiver/SAVE/shutdown profiles, or retaining obsolete schema-1 success assumptions. The RCP2/LED overlap and later stale loader gate were fixed rather than bypassed; the failed v65 shutdown is not a successful baseline.
**Evidence:** commits `6a9f4f42`, `24627360`; [measured scan breakdown](README.md#why-the-frame-checks-take-so-long); [normal-profile qualification and refusals](evidence/2026-10-24-normal-profile/README.md).
**Provenance:** migrated 2026-10-24 from the user's approval, measurements and implementation. Commit date 2026-10-23 is local; the final qualification record is dated October 24 UTC.
