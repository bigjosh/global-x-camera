# Stored photo objects and storage-system redundancy

October 14, 2026. **Accepted object policy, D-31:** an image and its photo metadata form one stored object. Store that object once; do not separately duplicate its pixels, name, timestamp, orientation or other photo attributes. Redundancy in the storage structures belongs to the chosen storage implementation. The [journal system remains provisional under D-30](slot-state-storage-review.md).

The user's clarification supersedes the earlier recommendation for one image payload plus two copies of critical photo metadata: “consider the image and the meta data about the image (name, time, etc) to be a single stored object - and we do not duplicate any of it.”

## Object and storage responsibilities

| Information | Policy |
|---|---|
| Stored photo object | Pixels and photo attributes are one logical object stored once. Its serialized representation and exported USB file format remain to implement. |
| Storage control structures | Slot/block mapping, occupancy/health, allocation/commit transactions, deletion, permanent retirement, journals and checkpoints may use implementation-defined redundancy. No universal copy count is selected here. |
| Integrity mechanisms | Device-required ECC, the original-image CRC-32C and required final commit verification remain. These checks/codes are not additional copies of the photo object. |

Storage records may repeat structural references, transaction identities, generations and integrity information needed for recovery. This does not authorize a second backup of photo attributes in a redundant catalog or journal.

D-31 does not change the approved image-payload CRC-32C coverage or replace it with a whole-object checksum. Serialization and integrity protection for the remaining object fields must be designed without duplicating those fields. A single logical object may span multiple NAND pages/blocks and does not imply one atomic hardware write.

## Recovery obligations remain

- Make allocation durable before programming the object, then establish and verify a valid final commit before treating it as successfully saved.
- Preserve prior objects and interrupted-save bytes. Only explicit host deletion removes data; recovery must not silently free occupied or retired storage.
- Keep permanent retirement separate from permission to read existing objects. Later read success or deletion does not undo BAD.
- Freshly read original NAND into RAM on each USB image-data request and apply accepted ECC/checksum/warnings. No background payload scan, relocation or refresh is added.
- Design and qualify storage-control redundancy, transaction/erase recovery, checkpoint rotation, wear, capacity and startup bounds. Verify all records required by the implementation before acknowledging success.

The provisional journal may keep protected records in different erase blocks. Its replica count, reserve size and recovery format remain implementation details to qualify; D-31 does not impose a fixed pair of photo-metadata copies or remove D-30's provisional journal redundancy. Multiple records on one NAND do not protect against failure of that whole chip.

## Superseded proposal and capacity context

The earlier recommendation duplicated photo descriptors/capture attributes separately from pixels. It is **not selected**. Its arithmetic remains context: two copies of 200 raw image payloads alone require 766,568,000 bytes, about 731.1 MiB, exceeding the 512 MiB planning capacity before overhead. Object replication is not selected.

## PARTIAL objects and next discussion

**Approved, D-32:** return whatever image data can be read from FULL or PARTIAL objects on host request. Mark incompleteness and read errors through EXIF and/or PTP; retain _RECOVERED naming and explicit-only deletion. Missing final checksum/optional attributes or inability to generate EXIF must not suppress safely attributable readable bytes. PARTIAL retrieval does not certify a successful original save.

**Current discussion:** slot allocation and wear distribution. Circular first-FREE-and-GOOD search after the previous allocation is recommended, not approved; it keeps existing photos in place and spreads reuse among currently free healthy slots. See the [slot-state review](slot-state-storage-review.md).

See the [decision register](2026-10-13-project-baseline.md), [slot-state implementation/future directions](slot-state-storage-review.md), [accepted read policy](ecc-read-error-review.md), and [specification](../../spec.md).
