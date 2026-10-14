# Fixed image slots and persistent state tables

October 14, 2026. **User-proposed working direction; backing storage and exact metadata redundancy remain undecided.** This follows the [additional redundancy discussion](storage-redundancy-review.md). Existing accepted requirements in [D-17 and D-26–D-29](2026-10-13-project-baseline.md) still apply. No new hardware part or on-media format is selected here.

## User proposal

Use one fixed-size slot per capture. Each slot contains a fixed number of NAND blocks sufficient for image data and image metadata. Track two independent attributes:

| Attribute | Proposed values and meaning |
|---|---|
| Occupancy | FREE, PARTIAL, FULL |
| Media health | GOOD, BAD |

For a new capture, scan the table for the first FREE and GOOD slot. Persist PARTIAL before writing image data, and persist FULL only after successful completion of the required save checks. USB deletion can release a FULL slot. A read error predictive of future media failure permanently marks the image slot BAD for future allocation without deleting its existing image.

PARTIAL corresponds conceptually to the accepted USED-without-DONE state; FULL corresponds to a valid completed commit. This is not a choice of bit encoding. An interrupted photo remains occupied and its bytes are retained without automatic erase or overwrite until explicit deletion; the interruption may have corrupted the current write. The user specifically described deletion of FULL slots; the host interface for explicitly deleting PARTIAL captures still needs definition.

The user raised concern about wear from rewriting redundant NAND state tables on every change and suggested FRAM as an alternative. This note records that proposal without treating the earlier two-copy NAND layout as approved.

## Recommendation for discussion

Keep the lookup table in ordinary MCU RAM while powered. Persist changes in **two append-only NAND metadata journals, with protected checkpoints and rotation across reserved erase blocks**. Reconstruct the RAM table from a checkpoint plus a bounded journal tail at startup. FRAM remains a strong alternative if measured startup, energy or firmware complexity justifies another chip.

| Persistence option | Benefits | Costs and obligations |
|---|---|---|
| NAND journal and checkpoints | Uses the existing image-storage device; distributes wear; a small state update consumes a fresh page instead of erasing/replacing the table. | Requires safe log/checkpoint recovery, metadata bad-block handling, reserved blocks, and bounded startup time. Two copies must occupy different physical erase blocks. |
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

## State and recovery details to resolve in implementation

- **FREE must mean erased and verified safe to program.** Make the host deletion authorization durable before starting erase; publish FREE only after all reusable slot blocks pass the required erase/status checks. A deletion/reclaim transaction may therefore need an internal pending state even if the user-visible occupancy model has only three states. Recover interrupted deletion without resurrecting a deleted photo or allocating partially erased media.
- **BAD is permanent for allocation.** Deleting a photo from a BAD slot does not make it reusable. A later good read does not undo retirement. Keep retained images readable until explicit deletion; the journal is metadata management, not image relocation.
- **Preserve prior valid metadata until replacements are verified.** Append records to fresh pages according to the exact NAND's ECC and partial-program rules. Never assume a state can safely be changed by reprogramming the same page. Validate required copies before acknowledging a completed operation. During checkpoint rotation, retain a recoverable old checkpoint/log until the replacement is complete.
- **Recovery must distinguish committed transitions from torn or conflicting records.** Use identity/generation, integrity checks and an explicit commit protocol. A newer sequence number alone is not proof of a completed transaction. An incomplete allocation must not revert to reusable FREE if image programming could already have started. Conservatively reserve uncertain slots until recovery establishes safe state.
- **Bound cold-start work.** Recover from a small checkpoint and bounded tail; include finding them and handling damaged metadata in the startup design. Do not depend on an unbounded whole-chip scan to meet the 50 ms exposure requirement. Metadata reads are allowed; this proposal does not add background image-payload reads.
- **Construct fixed slots from known-good physical blocks.** The fixed number of blocks need not be physically contiguous. An immutable mapping established at initialization can exclude factory-bad blocks without later moving images. Protect that mapping. Naively discarding every contiguous group that contains one factory-bad block can undermine the 200-photo capacity target.
- **First-free selection has a wear tradeoff.** Repeatedly deleting and replacing one early slot can concentrate image-block wear. The accepted 1,000 complete-fill reuse target and arbitrary single-slot churn are different workloads. Record this as a later allocation/qualification issue; do not silently substitute round-robin allocation for the user's proposal.
- **Two copies within one device do not protect against whole-chip loss.** FRAM would also become a catalog dependency unless recovery records elsewhere are deliberately designed. Exact metadata placement, image descriptor redundancy and degraded-copy handling remain open.

For the factory-bad-block capacity example, the archived W25N04KW has 4,096 blocks and specifies a minimum of 4,016 valid blocks. Fifteen 128 KiB blocks can hold the 1,916,420-byte RAW10 payload plus about 49 KiB of metadata. Contiguous groups yield floor(4,096 / 15) = 273 groups; 80 bad blocks scattered across distinct groups could reduce this to 193 even before metadata reserve. A known-good-block mapping avoids that particular loss mechanism. This is an illustrative geometry, not the final layout.

## Sources and next decision

Primary references checked October 14, 2026:

- [RAMXEED FeRAM product list](https://www.ramxeed.com/products/feram/feram-products.html): current small SPI families, density, voltage and packaging.
- [Infineon FRAM power-interruption explanation](https://community.infineon.com/t5/Non-Volatile-RAM-F-RAM-NVSRAM/What-is-the-operation-of-FRAM-when-power-is-interrupted/td-p/475691): a write can stop after the last complete byte; do not assume transaction atomicity.
- [Infineon FRAM overview](https://www.infineon.com/products/memories/f-ram-ferroelectric-ram): nonvolatile memory without flash-style erase/program delays.
- [Archived W25N04KW Rev C](../../datasheets/memory/W25N04KW_datasheet_RevC.pdf), printed pages 6 and 65: geometry, endurance headline and factory-valid-block count.
- [Archived Micron MT29F4G01ABBFD Rev F](../../datasheets/memory/Micron_MT29F4G01ABBFD_1v8_SPI_NAND_RevF.pdf), page 1: geometry and endurance headline.
- [Archived W25Q128JV Rev M](../../datasheets/memory/W25Q128JV_datasheet_RevM.pdf), printed page 4: sector erase geometry/endurance for the historical boot-NOR candidate.
- [STM32N657X0 product information](https://www.st.com/en/microcontrollers-microprocessors/stm32n657x0.html) and [archived DS14791](../../datasheets/processor/STM32N657X0_DS14791_datasheet.pdf), section 3.4.5: SRAM/backup SRAM and its power dependency.

**Current decision requested:** use the redundant NAND journal for the prototype, keeping FRAM as an alternative if timing, energy or implementation complexity warrants it. The user's fixed-slot proposal is recorded; neither its exact physical format nor the backing-medium recommendation is approved by this note.
