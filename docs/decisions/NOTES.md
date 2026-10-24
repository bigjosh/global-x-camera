# Product storage and retrieval decisions

## 2026-10-13  Preserve prior photos even if the current capture is lost

**Why:** the user accepts losing the current photo on abrupt power loss but requires previously saved photos to survive. Used-but-not-completed data remains occupied and potentially corrupt, not automatically reusable. The same preservation priority means stop when full and reclaim only through explicit host deletion.
**Rejected:** guaranteed completion of the current capture as a requirement; automatic erase/overwrite, automatic retake, or treating an interrupted save as successful. Marker presence alone does not establish device-level power-loss safety.
**Evidence:** [F-02](failure-response-review.md#f-02-abrupt-power-loss--approved); [D-09/D-17](2026-10-13-project-baseline.md); commits `cf9302c9`, `d787e62d`.
**Provenance:** reconstructed from explicit user approvals. The later SD bring-up explicitly leaves power-loss protection unqualified; this policy is a product requirement, not a claim of current compliance.

## 2026-10-13  Make full payload readback configurable without waiving completion checks

**Why:** bring-up needs full readback/comparison, while normal capture should be able to avoid its time and energy cost. Required device completion/status and storage commit checks remain separate from the optional full-image scan; a program-status result is not a readback ECC result.
**Rejected:** making full readback permanently mandatory or interpreting its disable switch as permission to skip essential integrity/transaction checks.
**Evidence:** [D-08](2026-10-13-project-baseline.md); [failure policy](failure-response-review.md); commit `cf9302c9`; later measured implementation choices live in [capture notes](../../firmware/capture-sd/NOTES.md).
**Provenance:** reconstructed from explicit user instruction in review transcript message 034 and the accepted scope clarification.

## 2026-10-13  Abort faults to shutdown rather than retrying into an unexpectedly late photograph

**Why:** the approved fault map ends a failed capture cycle in the lowest attainable state and requires another power cycle. Low battery at any point gets one red flash when energy permits; camera initialization and capture use distinct codes. Missing time/orientation instead records BAD and omits those export fields, preserving the photo rather than inventing attributes.
**Rejected:** automatic capture retries/queues, a fabricated timestamp, or making the 50 ms deadline a separate runtime fault. No additional boot-hang/watchdog response was selected for the prototype; exact thresholds and shutdown circuitry remain engineering work.
**Evidence:** [complete failure response map](failure-response-review.md); commits `853b0348`, `490ab98f`.
**Provenance:** reconstructed from the user's explicit checklist and approved shutdown definition. The delay-avoidance rationale is stated in the contemporaneous review; no implemented fault-code coverage is inferred.

## 2026-10-14  Qualify retention after reuse without requiring powered refresh

**Why:** the accepted storage workload is ten years at room temperature fully unpowered, including photos saved after 1,000 complete fill/download/explicit-erase cycles. Battery exhaustion must not shorten photo retention. Nominal device endurance and fresh-device retention headlines do not establish their simultaneous applicability, and management records matter as much as pixels.
**Rejected:** periodic refresh/power as a prerequisite; calling 1,000 downloads 1,000 erases; using a headline erase rating as proof of ten-year worn-media retention. Hot-car storage is outside the defined room-temperature requirement.
**Evidence:** [retention/reuse review](storage-retention-review.md); commits `dce01178`, `a4c13f2b`.
**Provenance:** reconstructed from explicit user approvals and their documented qualification boundary. Neither NAND research nor SD functional tests demonstrate this lifetime.

## 2026-10-14  Use PTP objects and explicit deletion instead of emulating a writable disk

**Why:** PTP gives the camera direct photo enumeration/read/delete requests that fit its internal object store. A synthesized read-only disk cannot implement normal deletion, while writable filesystem emulation must interpret arbitrary host sector updates and preserve unrelated photos. A download does not prove the host has durably backed up the image.
**Rejected:** the original host-visible drive requirement, automatic erase after connection/download, or treating host reads as delete authorization. Logical deletion must be durable before success is acknowledged; reclamation can follow safely.
**Evidence:** [USB interface review](usb-photo-access-review.md); commit `b37b8355`.
**Provenance:** reconstructed from the explicit PTP/per-photo deletion approval and documented comparison. PTP remains a product interface direction, not implemented USB access on the current bench firmware.

## 2026-10-14  Return recoverable damaged data instead of discarding the photo on an integrity error

**Why:** the user values whatever image content remains readable. The NAND policy uses device-appropriate ECC and stored CRC-32C; corrected/checksum-valid content is distinct from residual damage. FULL or PARTIAL objects may be exported with `_RECOVERED` and EXIF UserComment and/or PTP diagnostics; missing optional metadata or final checksum must not suppress safely attributable bytes.
**Rejected:** blanket transfer failure on checksum mismatch, claiming a PARTIAL object was successfully saved, or replacing the expected checksum with one over damaged data. Real transport failures and untrustworthy mappings still need explicit errors.
**Evidence:** [ECC and best-effort recovery policy](ecc-read-error-review.md); commits `7c5204e8`, `0fa03407`, `9f8d63f9`.
**Provenance:** reconstructed from explicit user approvals/refinements. These are NAND/product policies; current SD magic markers do not implement a stored payload checksum or this USB warning path.

## 2026-10-14  Read each requested original into RAM and retire unreliable slots without relocating photos

**Why:** every host image-data request should reflect a fresh read of the original NAND, so repeated reads may differ. A predictive media error permanently excludes the whole image slot from future allocation, including after deletion, while preserving its current image for further reads. Retirement and deletion are independent states.
**Rejected:** background image scans, refreshing/copying a marginal image to another slot, substituting an earlier RAM read, or erasing/withholding a retained photo merely because its slot is BAD. A checksum failure alone does not establish a physical-media cause.
**Evidence:** [host-requested reads and retirement](ecc-read-error-review.md); commit `127384a8`.
**Provenance:** reconstructed from the user's detailed clarification rejecting the earlier relocation proposal. Vendor marginal-read requirements still need exact-part reconciliation; retirement does not restore retention.

## 2026-10-14  Store pixels and photo attributes once as one object

**Why:** the user defines image data and its name/time/orientation metadata as one stored object and expressly rejects duplicating either. Storage-control mapping, journals/checkpoints, transaction identities and integrity codes have separate implementation responsibilities; their redundancy does not authorize a backup catalog of duplicated photo attributes.
**Rejected:** the earlier proposal for one image payload plus duplicated critical photo metadata; a universal structural replica count. Exact storage-control redundancy remains implementation-dependent.
**Evidence:** [object/redundancy policy](storage-redundancy-review.md); commit `651ab999`; the current SD layout decision is owned by [raw-slot notes](../../firmware/raw-slots/NOTES.md).
**Provenance:** reconstructed from explicit user correction, not inferred from current code. The single-object policy predates the SD format and survives that change.

## 2026-10-14  Pencil in NAND journals while retaining external-table and self-describing-slot alternatives

**Why:** rewriting a shared NAND state table for every photo transition would concentrate wear. The provisional approach keeps a RAM table backed by redundant append-only journals/checkpoints, with a circular cursor recovered from durable allocations rather than a separate pointer write. The user deliberately left the page/block protocol and table location open.
**Rejected:** freezing the illustrative reserve size/replica count; treating FRAM as atomic or backup SRAM as authoritative unpowered retention; presenting provisional circular allocation as a finalized storage architecture. Off-NAND tables and in-slot state remain alternatives.
**Evidence:** [slot-state review](slot-state-storage-review.md); commits `772fb1a5`, `8c058a29`.
**Provenance:** reconstructed from explicit provisional acceptance and later deferral. This is historical NAND design direction; the active SD format subsequently chose self-describing slots as recorded in [raw-slot notes](../../firmware/raw-slots/NOTES.md).

## 2026-10-14  NAND 1-to-0 bit changes are not a general mutable state-table primitive

**Why:** a tiny change still consumes an array page-program operation, and ECC parity may require impossible 0-to-1 changes even when user data only clears bits. The reviewed original Alliance parameter-page limit was one program per page; another vendor's four-partial-program allowance cannot be borrowed. Block erases and page-program limits are separate accounting rules.
**Rejected:** repeatedly changing FREE/PARTIAL/FULL bits in an already programmed ECC page; counting wear only by changed bits; assuming disabling ECC removes the exact device's program restrictions.
**Evidence:** [partial programming and wear analysis](slot-state-storage-review.md#follow-up-individual-bit-updates-and-wear); commit `756c5694`.
**Provenance:** reconstructed from exact-part documentation analysis. Confirm the delivered revision before a NAND backend; no NAND driver operation is qualified by this note.

## 2026-10-14  Reverse-order NAND erase improves ordering but a blank first page is still only a hint

**Why:** erasing blocks last-to-first and waiting for each successful completion means starting the first-block erase implies later blocks finished. After power loss during that final erase, however, a first page can read FF while other cells in its block are not safely erased. Factory bad-block markers also identify physical blocks, not arbitrary reusable slot-state storage.
**Rejected:** single blank-page reads as proof of successful erase; overwriting factory/OOB markers without exact ECC/program rules; freeing an undeleted or uncertain slot. Durable delete/recovery state is still needed until the full reusable state is established.
**Evidence:** [reverse-order erase and marker analysis](slot-state-storage-review.md#future-directions-retained-october-14); commit `36d4be07`.
**Provenance:** reconstructed from the user refinement and Macronix interrupted-erase analysis. The later simplified SD allocator deliberately leaves arbitrary power-loss protection unqualified; it does not repeal this NAND constraint.

## 2026-10-15  Generate lossless PNG16 on USB power and defer host-integration details

**Why:** the user selected 16-bit grayscale PNG because lossless compression can occur on USB power while retaining all ten sensor bits. Native storage and export representation are separate; object size, warning filename timing, memory and real-host PTP compatibility need bring-up rather than speculative finalization.
**Rejected:** the earlier TIFF recommendation as the selected export; lossy eight-bit JPEG as the only preserved representation; assuming an EXIF comment guarantees a visible host warning. Encoding/host details were consciously deferred, not removed from the interface requirement.
**Evidence:** [PNG and USB deferral](usb-photo-access-review.md#exported-image-format--png-selected-october-15); commits `29981446`, `712d7181`; later encoder specifics belong in [capture-SD notes](../../firmware/capture-sd/NOTES.md).
**Provenance:** reconstructed from explicit format selection and deferral. Subsequent `sample << 6` implementation and RAW storage evolution do not imply PTP is complete.
