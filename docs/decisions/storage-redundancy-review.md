# Additional storage redundancy

October 14, 2026. **Journal persistence provisionally selected; broader redundancy layout still a recommendation.** The user asked what additional redundancy to use after accepting [D-29's request-driven reads without relocation](2026-10-13-project-baseline.md), then provisionally selected the journal under D-30. The existing ECC, CRC-32C, mandatory commit verification, source-preserving read behavior and explicit-only deletion remain in force.

**Follow-up:** the [slot-state storage review](slot-state-storage-review.md) records the provisional RAM table plus redundant NAND journals/checkpoints. Off-NAND table storage and in-slot status/possible vendor bad-block-marker reuse remain future directions. The exact duplication of every descriptor and recovery format below are not frozen by the provisional journal choice.

## Recommendation

For the prototype, **store one copy of each image payload, with two separately protected copies of critical metadata in different physical erase blocks**. Keep the selected NAND's required ECC and the original-image CRC-32C. Do not add image mirroring or software parity across images at this stage.

Metadata redundancy protects the information needed to identify/recover photos and avoid unsafe reuse; it does not repair missing pixels. Two metadata copies on one NAND chip do not protect against whole-chip, controller, power-system or common firmware failure.

| Information | Proposed protection |
|---|---|
| Per-photo identity/generation, slot mapping, image length/format, original image CRC, capture metadata or BAD sentinels | Two independently readable, ECC-protected and CRC-32C-checked metadata records in different erase blocks. Both identify the same photo generation; an old header from a previous use of the slot must not identify a new photo. |
| Allocation and USED/DONE commit state | Redundant, versioned records with explicit transaction/commit validity. An intact header alone is not proof that image saving completed. Preserve interrupted occupied allocations under the existing policy. |
| Explicit deletion state | Redundant durable deletion records tied to the photo identity/generation. Do not lose a deletion merely because one metadata block fails, or let stale indexes resurrect a deleted photo. |
| Permanent retired-slot/bad-block allocation state | Redundant protected persistent records; do not make a retired slot free after reboot or deletion because one map copy was lost. Preserve manufacturer factory-bad information. |
| Image pixels | One original payload plus device-required ECC and the accepted image CRC-32C. No extra payload copy or cross-image parity. |

Metadata CRC detects corruption; ECC and a surviving independent copy provide recovery opportunities. Store records in byte ranges actually covered by the selected device's ECC. Do not assume arbitrary spare/OOB bytes are protected or available for repeated marker programming.

## Recovery and write obligations

Place the two copies in different physical erase blocks, not just different pages of the same block. Give records identity, version/generation, a checksum and transaction validity. Read back and verify the required metadata copies before declaring a successful capture commit or acknowledging a completed deletion. This does not turn capture-time full-payload readback into a mandatory operation when its approved switch is off.

If one copy fails its integrity/commit checks and the other is valid, use the valid copy under the qualified version/transaction rules. Two valid but unexplained conflicting records are not a majority vote: preserve data, avoid unsafe allocation and apply the existing metadata-failure policy rather than guessing. A sequence number alone is not proof of a completed update.

Use append-only updates and safe metadata checkpoint rotation/compaction as needed, with old valid state retained until replacement metadata is verified. Exact layout and interruption cleanup remain to design. These are management-record operations, not image relocation, image refresh or background payload scans. A catalog cache may be rebuilt from valid metadata without reading all photo payloads.

Size the metadata reserve and rotate writes to avoid concentrating the 1,000 full reuse cycles onto a few cells. Qualify power interruption during both-copy creation, commit, deletion, retirement and metadata compaction; losing one copy must not silently free occupied/retired storage or hide every image. Initial layout, write counts and energy depend on the final NAND geometry and must be measured.

## Capacity tradeoff

The selected image contains **1,916,420 bytes** of packed RAW10 before metadata. For the current **4 Gbit / 512 MiB planning device**:

- Two copies of 200 payloads require **766,568,000 bytes, approximately 731.1 MiB**, before headers, bad blocks or reserves. This cannot meet 200 photos in 512 MiB.
- The bare duplicated-payload ceiling is **140 photos**, ignoring all overhead.
- Under the earlier illustrative 2 MiB-per-payload slot and 20% reserve model, duplication gives approximately **102 photos**, versus 204 single-copy slots. This is a planning calculation, not a qualified layout.
- Metadata duplication consumes much less capacity than a second 1.916 MB payload per photo, but NAND page/block allocation and write-energy overhead must still be budgeted.

Additional payload parity could cost less space than full mirroring, but would add coding/recovery complexity. Parity spanning photos can require reading other images to recover a requested photo and complicates independent deletion and whole-slot retirement. Per-image parity remains a possible future study; no parity overhead, code or implementation is selected.

## Evidence and boundaries

- Current [image/capacity requirements](../../spec.md) supply the payload size and planning capacity; the arithmetic above is derived here.
- The [camera/memory review](../review/camera-memory-review.md) already identifies protected metadata, redundant allocation state, torn writes and exact-part partial-program rules as engineering requirements. Its recovered parallel-NAND details are historical; they do not select the current serial-NAND layout.
- [Winbond's technical FAQ](https://www.winbond.com/hq/support/faq/technical/?__locale=en), checked October 14, describes built-in ECC and media failure/bad-block handling. That is device-management context, not a vendor endorsement of this proposed two-copy metadata format. Exact-part documentation takes precedence over generic FAQ rules.
- This proposal does not establish ten-year retention through 1,000 cycles. Both metadata and pixels still require exact-part qualification. It preserves fresh whole-image NAND-to-RAM reads only on host image requests, current-read warning export, permanent predictive-error retirement and explicit-only photo deletion.

**Remaining proposal:** one image payload copy with independently protected critical metadata; no added image mirroring or software parity for the prototype. Redundant journal persistence is provisionally selected under D-30. Exact per-photo metadata duplication, physical layout and recovery protocol remain engineering work; see the [slot-state review](slot-state-storage-review.md).
