# RAW slot decisions

## 2026-10-24  Store packed RAW objects and defer image encoding to retrieval

**Why:** the user chose direct packed RAW storage to remove conversion, compression and filesystem work from the battery-powered capture path. Fixed image geometry permits consecutive logical sectors and later host reconstruction. The subsequent explicit preference retained this architecture for simplicity and its expected fit with future NAND even without a demonstrated magic-layout speed gain.
**Rejected:** continuing PNG/FAT32 as the active prototype capture format; interpreting this choice as proof that RAW always wins for every scene or storage device.
**Evidence:** commits `a0b8ce70`, `14d05d9a`, `18299c29`; [selection and later user rationale](../../docs/decisions/raw-sd-slots-2026-10-24.md); [historical PNG tradeoff](../png-encoder/NOTES.md#2026-10-20--select-the-faster-complete-save-rather-than-the-smallest-png).
**Provenance:** migrated 2026-10-24 from the user's explicit choices and contemporaneous implementation records; no inferred performance rationale added.

## 2026-10-24  Initially use explicit FREE records rather than an unqualified blank-sector guess

**Why:** the first RAW prototype had no established whole-card erased-value precondition. A generation-bound, CRC-checked FREE header distinguished an initialized slot from unknown or torn media; PARTIAL consumed a failed attempt instead of risking an older photo. A 3731-sector stride avoided the roughly 9% capacity loss of rounding each image to 4096 sectors.
**Rejected:** treating arbitrary blank-looking sectors as free; automatically formatting on mount failure; overwriting PARTIAL objects.
**Evidence:** commit `a0b8ce70`; [original decision](../../docs/decisions/raw-sd-slots-2026-10-24.md#format-and-allocation); [legacy format](README.md#legacy-version-1-format-and-interface).
**Provenance:** migrated 2026-10-24 from the original design record and implementation. The next entry deliberately supersedes this allocation format.
**Superseded:** see 2026-10-24 Replace separate state headers with explicitly erased magic slots.

## 2026-10-24  Replace separate state headers with explicitly erased magic slots

**Why:** the user deliberately simplified the prototype to one forward write of each sector. Explicit successful whole-card commissioning erase and the card's SCR-reported `DATA_STAT_AFTER_ERASE` provide the new allocation precondition. Only four erased bytes at the first word mean FREE; all other words remain occupied, and read errors stop allocation. Leading/trailing markers eliminate the separate PARTIAL/FULL header rewrites and reduce a slot to 3730 sectors.
**Rejected:** retaining a superblock, generation or allocation table in this prototype; inferring the erased byte from an empty-looking slot; treating unknown non-erased data as reusable. Logical erase/markers do not guarantee SD internal power-loss atomicity or pixel integrity.
**Evidence:** commit `14d05d9a`; [magic format and limitations](README.md#front-metadata-magic-slots-selected-october-24); [explicit erase constraint](../sd-storage/NOTES.md#2026-10-24--configure-the-hardware-busy-timer-for-whole-card-erase).
**Provenance:** migrated 2026-10-24 from the user's revision, recorded design and hardware qualification; this is a conscious reversal of the earlier header choice under a new commissioning precondition.

## 2026-10-24  Put all reserved metadata in the first sector and distinguish the new layout

**Why:** moving the existing 152 padding bytes after the leading marker lets a future directory obtain occupancy and all metadata with one sector read, without another sector, copy or header rewrite. `GXR2` distinguishes image offset 156 from legacy `GXRS` offset 4; their unchanged stride permits mixed old/new photos without erasing them.
**Rejected:** leaving metadata at the tail; reusing the same marker for incompatible image offsets; treating a first-sector listing as proof that the trailing completion marker exists. Unknown markers cannot be extracted by guessing an offset, even with partial recovery requested.
**Evidence:** commit `18299c29`; [format and one-sector reader](README.md#front-metadata-magic-slots-selected-october-24); [mixed-card/readback evidence](../capture-raw/evidence/2026-10-24-front-metadata/README.md).
**Provenance:** migrated 2026-10-24 from the user's explicit directory-read request, implementation and qualification.

## 2026-10-24  Reserve metadata now and defer its field schema

**Why:** the layout change needed space and read semantics, while timestamp, orientation, exposure and validity encodings had not been settled. The capture initializes the reservation explicitly and the reader exposes opaque bytes, avoiding invented capture dates from retained RAM or zero placeholders. Deletion/reclamation, allocation hints and durable pixel checksums also remain separate design work.
**Rejected:** silently choosing a metadata schema or interpreting zero as a valid date; presenting completion markers as end-to-end checksums. Product retention/ECC/retrieval policy remains separate from this prototype's implementation limits.
**Evidence:** commit `18299c29`; [metadata scope](../../docs/decisions/raw-sd-slots-2026-10-24.md#october-24-follow-up-reserve-metadata-in-the-first-sector); [product decisions](../../docs/decisions/NOTES.md).
**Provenance:** migrated 2026-10-24 from the expressly recorded deferral; no missing field rationale invented.
