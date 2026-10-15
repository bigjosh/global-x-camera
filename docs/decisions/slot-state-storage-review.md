# Fixed image slots and persistent state tables

October 14, 2026. **Provisional prototype choice: RAM slot table backed by redundant append-only NAND journals and protected checkpoints.** The user asked to “pencil in the journal system” and retain both off-NAND table storage and in-slot state as future directions. Exact physical format, reserve size, recovery protocol and storage-control redundancy remain to design and qualify. [D-31](storage-redundancy-review.md) treats pixels and photo attributes as one object stored once; storage-control structures have implementation-defined redundancy. Existing accepted requirements in [D-17 and D-26–D-31](2026-10-13-project-baseline.md) still apply.

## Fixed-slot working model

Use one fixed-size slot per capture. Each slot contains a fixed number of NAND blocks sufficient for image data and image metadata. Track two independent attributes:

| Attribute | Proposed values and meaning |
|---|---|
| Occupancy | FREE, PARTIAL, FULL |
| Media health | GOOD, BAD |

For a new capture, scan the table for the first FREE and GOOD slot. D-33 provisionally refines the search to start after the last durably allocated slot and wrap at the end; it does not finalize the storage implementation. Persist PARTIAL before writing image data, and persist FULL only after successful completion of the required save checks. USB deletion can release a FULL slot. A read error predictive of future media failure permanently marks the image slot BAD for future allocation without deleting its existing image.

PARTIAL corresponds conceptually to the accepted USED-without-DONE state; FULL corresponds to a valid completed commit. This is not a choice of bit encoding. An interrupted photo remains occupied and its bytes are retained without automatic erase or overwrite until explicit deletion; the interruption may have corrupted the current write. D-32 subsequently approves USB retrieval and explicit deletion of PARTIAL objects, with best-effort image data and EXIF and/or PTP error/incomplete warnings. Protocol details remain to implement.

The user raised concern about wear from rewriting redundant NAND state tables on every change and suggested FRAM as an alternative. After the partial-programming discussion below, the user provisionally selected journaling. The subsequent D-31 decision supersedes the earlier per-photo metadata duplication proposal: object contents are stored once, while storage-control redundancy and the on-media layout depend on the implementation.

## Provisional prototype approach

Keep the lookup table in ordinary MCU RAM while powered. Persist changes in **redundant append-only NAND storage-control journals, with protected checkpoints and rotation across reserved erase blocks**. The replica count and physical layout remain to qualify; the two-stream layout below is an illustrative wear calculation. Reconstruct the RAM table from a checkpoint plus a bounded journal tail at startup. FRAM remains a strong alternative if measured startup, energy or firmware complexity justifies another chip.

| Persistence option | Benefits | Costs and obligations |
|---|---|---|
| NAND journal and checkpoints | Uses the existing image-storage device; distributes wear; a small state update consumes a fresh page instead of erasing/replacing the table. | Requires safe log/checkpoint recovery, metadata bad-block handling, reserved blocks, and bounded startup time. Independently redundant copies should occupy different physical erase blocks; exact count/layout remain to qualify. |
| Small external SPI FRAM | Nonvolatile small writes without flash erase/program waiting; a small table can be read quickly on startup. Power can be removed between captures. | Extra component, pins/board area and qualification. Interrupted multi-byte updates still require checksums, generations and a recoverable commit scheme. Retention and power sequencing must meet the actual product conditions. |
| Reserved sectors of existing boot NOR | Potentially avoids another component and separates the catalog from the NAND device. | Still needs append-only records, wear distribution and power-loss recovery; must isolate catalog sectors from firmware updates and boot assets. Exact boot-memory part/layout is not frozen. |
| MCU backup SRAM | Useful optional cache while backup power exists. | Not authoritative storage for the requirement to retain photos and their catalog for ten years fully unpowered. Ordinary RAM is only a powered-session cache. |

A 16–32 KiB FRAM is a plausible sizing starting point, not a selected density. For example, 256 slots require only 96 bytes for the bare three state bits per slot; identities, generations, CRCs, block mapping, duplication and transaction records need substantially more space. RAMXEED currently lists the **MB85RS128TY (16 KiB)** and **MB85RS256TY (32 KiB)** SPI families at **1.8–3.6 V** in SOP-8. Stock, price, an evaluation board and final retention qualification have not been checked. A switched supply avoids a new always-on memory load; qualify ramp behavior and I/O backfeed.

FRAM does not make an entire table update atomic. Use independently valid A/B records or another transactional layout so one incomplete update cannot destroy the last valid state. CRC, photo/slot identity, generation and commit rules remain necessary; check the exact device's power-loss behavior.

## NAND wear estimate

Illustrative assumptions: 200 photos per full use, 1,000 complete reuse cycles, three normal occupancy transitions per photo, one fresh NAND page per transition per replica, two replicas, 64 pages per erase block, and even rotation over 16 total reserved blocks (eight per replica).

| Quantity | Calculation | Result |
|---|---|---|
| Image saves | 200 × 1,000 | 200,000 |
| Normal state changes | 200,000 × 3 | 600,000 |
| Journal page programs | 600,000 × 2 | 1,200,000 |
| Total filled-block equivalents | 1,200,000 / 64 | 18,750 |
| Filled-block/erase-cycle equivalents per physical journal block | 18,750 / 16 | About 1,172 |

This is a **base estimate before overhead**, not a final endurance proof. Durable delete intent adds records beyond the three visible state changes; headers, checkpoints, retirement, commit protocol, retries, interrupted operations and failed metadata blocks also increase traffic. Allow margin and measure the implemented protocol.

Sixteen reserved blocks occupy 2 MiB with 128 KiB blocks or 4 MiB with 256 KiB blocks. Include this once in the overall metadata/bad-block reserve; do not count it as free extra capacity. The archived Winbond and Micron candidate datasheets give headline endurance of 60,000 and 100,000 cycles respectively. The arithmetic suggests a journal need not create a wear bottleneck, but those headline numbers do not establish ten-year retention after the required cycling profile or qualify an unselected NAND part.

## Follow-up: individual bit updates and wear

October 14 clarification: the user asked whether successive 1-to-0 changes in the same page are possible and whether each costs a full erase/program cycle. These device constraints informed the subsequent provisional journal choice.

At the logical level, an erased SLC NAND cell reads 1 and programming can change it to 0; restoring it to 1 requires erasing its entire block. NAND does not provide an independently erasable page or a general-purpose bit-write interface. The host loads bytes into a volatile page buffer and issues an array-program operation. Multiple edits to the buffer before a single execute are not multiple physical NAND programs and are not durable until execution completes.

Repeated programming of one page between erases is called partial-page programming, and is allowed only under the exact device's limits. A one-bit data change still counts as a page-program operation against that limit. With on-die ECC, changing protected data also changes its parity code; even a data-only 1-to-0 change may require an impossible 0-to-1 change in already-programmed parity. Sector alignment, one-time programming of protected sectors, spare-area coverage and page order therefore matter.

| Device evidence | Consequence |
|---|---|
| Alliance AS5F family Rev.3.1, October 2024, includes AS5F14G04SND-10LIN. Parameter-page table 11-3, page 39, byte 110 is 01h programs per page; partial-program attributes are 00h. | Treat the evaluation candidate as one array program per page between erases. Do not transfer another vendor's four-program allowance to it or assume disabling ECC removes that limit. Confirm the exact delivered revision before implementing its driver. |
| W25N04KW Rev C, printed pages 17 and 63: four partial programs per page total, including spare/parity; with ECC enabled, a main sector and its corresponding protected spare data must be programmed together. Printed pages 39/66 require increasing page order. | Four does not mean unlimited bit changes or four arbitrary rewrites of a previously programmed ECC sector. Consume fresh supported units and follow exact sequencing. |

A partial program is **not automatically one complete program/erase endurance cycle**: it does not erase the block. Nevertheless, program pulses cause electrical stress and can disturb other cells. Wear cannot be calculated by counting only changed bits, nor is there a universal conversion of one partial program into a fraction of an erase cycle. Track both block erase/cycling history and the independent per-page program limit; the device's endurance rating assumes supported programming sequences.

For the illustrative 64-page block, programming each fresh page once and then erasing the block for reuse is one block program/erase cycle, not 64 block erase cycles. This is why the journal estimate divides page programs by pages per block. Its estimate does not rely on repeatedly programming individual bits within a page.

For the proposed state table, use a fresh page for each durable record under the conservative layout; do not encode later PARTIAL/FULL/BAD transitions by revisiting bits in an already-programmed ECC page. Journaling is now the provisional choice; the alternatives below remain future research.

Sources:
- [Alliance AS5F Rev.3.1](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.1_O.pdf), pages 29–33, 36 and 39: load/execute distinction, block erase and parameter-page limit.
- [Winbond W25N04KW Rev C](https://media.digikey.com/pdf/Data%20Sheets/Winbond%20PDFs/W25N04KW_Ver_C_8-12-22.pdf), printed pages 17, 37–39, 63 and 66: ECC, buffer versus array operations, partial-program count and page order.
- [Winbond AN0000040](https://du4vjmorpxp6c.cloudfront.net/winbond-application-notes/qspi-nand/an40-how-to-work-with-winbond-serial-nand-flash-build-in-ecc-v1.pdf), page 1: ECC parity can already be programmed even when user data looks blank. This application note illustrates the ECC pitfall using W25N01GV; exact-part rules above govern the candidate devices.
- Micron TN-29-17, *NAND Flash Design and Use Considerations*, program-disturb section, describes increased partial-page programming as increasing disturb exposure. The indexed manufacturer-authored excerpt was readable; its historical PDF mirror was unavailable during this check. It supplies general mechanism context, not exact-part limits.

## State and recovery details to resolve in implementation

- **FREE must mean erased and verified safe to program.** Make the host deletion authorization durable before starting erase; publish FREE only after all reusable slot blocks pass the required erase/status checks. A deletion/reclaim transaction may therefore need an internal pending state even if the user-visible occupancy model has only three states. Recover interrupted deletion without resurrecting a deleted photo or allocating partially erased media.
- **BAD is permanent for allocation.** Deleting a photo from a BAD slot does not make it reusable. A later good read does not undo retirement. Keep retained images readable until explicit deletion; the journal is metadata management, not image relocation.
- **Preserve prior valid metadata until replacements are verified.** Append records to fresh pages according to the exact NAND's ECC and partial-program rules. Never assume a state can safely be changed by reprogramming the same page. Validate required copies before acknowledging a completed operation. During checkpoint rotation, retain a recoverable old checkpoint/log until the replacement is complete.
- **Recovery must distinguish committed transitions from torn or conflicting records.** Use identity/generation, integrity checks and an explicit commit protocol. A newer sequence number alone is not proof of a completed transaction. An incomplete allocation must not revert to reusable FREE if image programming could already have started. Conservatively reserve uncertain slots until recovery establishes safe state.
- **Bound cold-start work.** Recover from a small checkpoint and bounded tail; include finding them and handling damaged metadata in the startup design. Do not depend on an unbounded whole-chip scan to meet the 50 ms exposure requirement. Metadata reads are allowed; this proposal does not add background image-payload reads.
- **Construct fixed slots from known-good physical blocks.** The fixed number of blocks need not be physically contiguous. An immutable mapping established at initialization can exclude factory-bad blocks without later moving images. Protect that mapping. Naively discarding every contiguous group that contains one factory-bad block can undermine the 200-photo capacity target.
- **Allocation policy is provisional (D-33).** Circular FREE-and-GOOD search replaces the fixed-start proposal for now; it only spreads wear among available free slots. The accepted 1,000 complete-fill reuse target and arbitrary single-slot churn are different workloads. Exact allocation and journal wear must still be qualified.
- **Two copies within one device do not protect against whole-chip loss.** FRAM would also become a catalog dependency unless recovery records elsewhere are deliberately designed. Exact storage-control placement/redundancy and degraded-record handling remain open; image descriptors that are photo attributes belong to the single stored object under D-31.

For the factory-bad-block capacity example, the archived W25N04KW has 4,096 blocks and specifies a minimum of 4,016 valid blocks. Fifteen 128 KiB blocks can hold the 1,916,420-byte RAW10 payload plus about 49 KiB of metadata. Contiguous groups yield floor(4,096 / 15) = 273 groups; 80 bad blocks scattered across distinct groups could reduce this to 193 even before metadata reserve. A known-good-block mapping avoids that particular loss mechanism. This is an illustrative geometry, not the final layout.

## Future directions retained October 14

The user's instruction is to keep both alternatives open, independently or in combination:

1. **Store the slot table outside the image NAND.** Investigate FRAM, suitably isolated boot NOR or another nonvolatile location. Preserve the same power-off retention, transaction integrity, permanent retirement and startup requirements.
2. **Make each slot describe its own state.** Investigate the user's proposed all-FF = FREE, final-page completion marker = FULL, otherwise programmed = PARTIAL scheme, with a first-page scan to find a candidate free slot. Investigate using the device's existing bad-block marking mechanism for GOOD/BAD where its exact programming and preservation rules permit. This is a research direction, not an approved allocation test or a finished implementation.

A promising refinement is a protected non-FF allocation header written and verified before any payload, followed by image/metadata pages and a dedicated fresh commit page programmed last. The commit must be validated against the current slot/allocation identity and generation with integrity checks; a bare magic constant is insufficient. Structural references and transaction identifiers may repeat, but this does not require a second copy of name, time or other photo attributes, which belong to the single stored object under D-31. A valid commit establishes completion of the save transaction, not perpetual payload integrity. Current-read ECC/CRC checks still apply. Reserved control-record pages, implementation-defined structural redundancy and their capacity cost remain to design.

**First-page FF is only a candidate hint.** It cannot establish that every block is erased: deletion might erase the first block and then lose power, leaving later blocks and an old commit record. Erasing the header block last reduces that particular case but does not solve interrupted erase of the header block itself. Even reading all user bytes as FF does not prove successful erase completion or healthy ECC/spare state. A failed, suspect or unreadable metadata page must not be interpreted as FREE.

A future layout needs durable deletion intent and recovery rules until every reusable block has completed erase/status checks and reusable state is established. This may use protected in-slot records plus a small external deletion/retirement ledger, or another proven scheme. Merely erasing again when a first page looks FF is not authorized while the slot might contain an undeleted current photo. PARTIAL captures remain retained until explicit deletion.

**Reverse-order erase refinement, October 14:** the user proposes deleting slot blocks from last to first. This is a sound ordering invariant if firmware waits for successful completion/status of each block before issuing the next erase: beginning the first block's erase then implies that all later blocks have completed their erases. Successfully completing the first block's erase means the whole slot has completed erase. Record this as a refinement of FD-05; it does not change the provisional journal choice.

The remaining distinction is between **a successfully completed first-block erase** and **a first page that merely reads FF after reboot**. Power loss during that final block erase can leave the first page blank while other cells in the same block remain programmed or insufficiently erased. Thus reverse order eliminates the later-block counterexample but does not by itself validate the first block. Recovery must establish that block's reusable state through a durable completion protocol or a separately qualified recovery/re-erase rule. Do not equate a single blank read with successful completion or assume all reads from uncertain media are trustworthy. The provisional journal can retain host deletion intent until all erase checks complete and FREE is durable. Whether the future in-slot scheme can safely eliminate that ledger remains open.

[Macronix AN0363](https://www.macronix.com/Lists/ApplicationNote/Attachments/1924/AN0363V1%20-%20Managing%20Unexpected%20NAND%20Flash%20Power%20Loss%20In%20Embedded%20Systems.pdf), page 5, explains that after an interrupted erase some cells may have reached the erased state while slower cells remain between states. This is general NAND recovery evidence; qualify the exact selected device's recovery procedure.

**Factory markers identify physical blocks, not whole image slots.** For the Alliance candidate, the documented marker is in the first spare-area location of the first page of each block, read before any program or erase operation. These are specific reserved bytes; do not assume entire reserved pages are freely available for repeated status updates. Preserve original factory markers and the immutable slot-to-block map. Adding a runtime marker to a live page may violate one-program/ECC restrictions and must not corrupt an existing photo.

For the provisional journal, keep permanent runtime slot retirement in protected healthy management storage. A retired slot remains readable and stays excluded from future allocation after deletion. A future use of vendor-supported grown-bad markers must retain those semantics and must not cause a generic skip-bad reader to hide images or renumber their physical mapping. Blank factory markers alone do not prove GOOD, and failure to persist a new retirement record cannot silently authorize reuse.

Only metadata pages need be inspected for the proposed scan; a full payload scan is not selected. Bound and measure the worst-case metadata scan alongside startup against the 50 ms exposure requirement. Do not treat a typical per-page read time or an early free slot as a worst-case guarantee.

Sources: [Alliance Rev.3.1](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.1_O.pdf), pages 39 and 43, for program count and factory-marker location; the [prior interrupted-operation review](../review/camera-memory-review.md#mem-002---power-fail-recovery-must-respect-partial-program-and-erase-rules) for the historical Macronix warning about interrupted program/erase retention; [Winbond AN0000040](https://du4vjmorpxp6c.cloudfront.net/winbond-application-notes/qspi-nand/an40-how-to-work-with-winbond-serial-nand-flash-build-in-ecc-v1.pdf), page 1, for the distinction between blank-looking user data and already-programmed ECC. The recovery refinements are engineering analysis; their exact-part implementation remains unqualified.

## Circular allocation — provisional October 14, 2026

**Provisionally accepted, D-33:** search for the next FREE and GOOD slot starting just after the last durably allocated slot, wrapping at the end. The user accepted this “for now,” while explicitly leaving the page/block storage design and off-NAND allocation-table alternatives open. Skip FULL, PARTIAL and BAD slots; preserve the accepted stop-when-full behavior. This changes the starting point of the original first-FREE-and-GOOD proposal, not its eligibility rules.

**Cursor recovery in the provisional journal:** each durable allocation record identifies its slot and transaction order. For example, a valid PARTIAL allocation of slot 37 sets the RAM next-search position to 38, wrapping at the last slot. Advance on durable allocation, even if the photo never reaches FULL. A delete does not reset the cursor. Checkpoint the next-search position with the slot table before retiring older journal records; on startup, restore both and replay subsequent valid allocations. This adds a small checkpoint field without a separate NAND write per capture solely for the cursor. Recover the table and cursor from the same validated transaction history; a newer sequence number or torn record alone is not a valid update. The cursor chooses where the search starts; only safely established FREE and GOOD state authorizes reuse, so a stale cursor cannot permit overwriting an occupied slot.

This spreads reuse among currently free healthy slots when several are available. It does not move retained objects or guarantee equal lifetime wear across occupied and free slots; if only one slot is free, there is no allocation alternative. Journal-block wear distribution remains a separate storage-system obligation. Track/qualify actual erase counts rather than treating the 1,000 complete device-reuse requirement as a bound on every possible partial-delete workload.

[Macronix AN0289](https://www.macronix.com/Lists/ApplicationNote/Attachments/1913/AN0289V1-Wear%20Leveling%20in%20NAND%20Flash%20Memory.pdf), page 1, explains why repeated reuse of a few blocks can reach local endurance limits while other blocks remain lightly used. Circular free-slot search is the provisional project choice derived from that principle; no extra relocation, image refresh or numerical endurance guarantee is adopted.

## Sources and remaining work

Primary references checked October 14, 2026:

- [RAMXEED FeRAM product list](https://www.ramxeed.com/products/feram/feram-products.html): current small SPI families, density, voltage and packaging.
- [Infineon FRAM power-interruption explanation](https://community.infineon.com/t5/Non-Volatile-RAM-F-RAM-NVSRAM/What-is-the-operation-of-FRAM-when-power-is-interrupted/td-p/475691): a write can stop after the last complete byte; do not assume transaction atomicity.
- [Infineon FRAM overview](https://www.infineon.com/products/memories/f-ram-ferroelectric-ram): nonvolatile memory without flash-style erase/program delays.
- [Archived W25N04KW Rev C](../../datasheets/memory/W25N04KW_datasheet_RevC.pdf), printed pages 6 and 65: geometry, endurance headline and factory-valid-block count.
- [Archived Micron MT29F4G01ABBFD Rev F](../../datasheets/memory/Micron_MT29F4G01ABBFD_1v8_SPI_NAND_RevF.pdf), page 1: geometry and endurance headline.
- [Archived W25Q128JV Rev M](../../datasheets/memory/W25Q128JV_datasheet_RevM.pdf), printed page 4: sector erase geometry/endurance for the historical boot-NOR candidate.
- [STM32N657X0 product information](https://www.st.com/en/microcontrollers-microprocessors/stm32n657x0.html) and [archived DS14791](../../datasheets/processor/STM32N657X0_DS14791_datasheet.pdf), section 3.4.5: SRAM/backup SRAM and its power dependency.

**Current status:** the journal system (D-30) and circular allocation (D-33) are provisional prototype choices. The user explicitly requires a later storage implementation review before freezing how pages and blocks are used, or choosing another location for allocation tables. Off-NAND table storage (FD-04) and in-slot state/possible bad-block-marker reuse (FD-05) remain open. D-31 settles that the photo object itself is stored once; no first-page-FF shortcut is adopted.

**Required follow-up before freezing storage:** select the exact NAND geometry and interface; specify slot-to-block mapping, object/control page placement, ECC/OOB use and allowed program order; define allocation, commit, deletion, retirement and power-loss recovery; size and protect journal/checkpoint reserves; verify cursor reconstruction, startup bounds, usable capacity and wear. Compare an off-NAND table implementation if it materially simplifies those requirements. The existing cursor explanation is an implementation direction, not a completed page/block format or a decision against FRAM/other nonvolatile table storage.

**Next discussion:** the role of directional light sensing. D-35 selects a self-assembled NUCLEO-N657X0-Q prototype and defers custom-PCB manufacturer/assembler selection. Photographic flash remains deferred under D-34/FD-06. Storage and power implementation/qualification remain tracked engineering work; neither is declared complete.
