# PTP photo-store backend

This portable C layer reads the existing fixed RAW slots and emits a lossless
16-bit grayscale PNG on request. It owns no device or bus: the caller supplies
synchronous read, write, readiness, read-recovery and service callbacks. It is
single-owner and cannot be reentered from those callbacks.

## Integration

1. Initialize the SD transport and obtain its SCR `DATA_STAT_AFTER_ERASE` bit.
   Call `photo_store_open` with the actual logical sector capacity and erased
   byte. Opening never formats, repairs or writes the card.
2. `photo_store_scan` reads one header sector per slot and visits every recognized
   `GXR2` or legacy `GXRS` object, including those beyond deletion holes. Handle
   `slot_index + 1` stays stable while that card and slot object remain present.
   Preserve the recognized layout if later header-error recovery is needed.
   Unknown occupied markers are counted and hidden, never declared free.
   A failed header read aborts the scan; a partially built list is not complete.
3. `photo_store_info` freshly checks the first and last sectors. Current opaque
   metadata contains no approved date/orientation schema; callers must leave
   those PTP/EXIF values absent. `GX_0000001.png` names slot handle 1, not a date.
4. For each requested photo, call `photo_store_load` into a full slot RAM buffer.
   It discards all previous RAM contents. A failed burst is cleared before
   single-sector retries; `recover` must first establish a safely usable idle
   transport. Unreadable sectors become zeros, with explicit counters. If safe
   recovery fails, remaining sectors stay zero and no further card I/O occurs.
   Do not implement `recover` as an unconditional reset during uncertain writes.
5. `photo_store_png` converts from the completed immutable RAM result and writes
   callback chunks of at most 2,241 bytes. It uses no further SD reads. The
   caller can service USB and cancel in the output callback. Never substitute a
   partial USB transfer for a successful complete PTP response.
6. Only an explicit per-photo delete invokes `photo_store_delete`. On success,
   remove the handle from the catalogue. Capture remains disabled during USB.

Callbacks return **1 for success**, 0 for failure/cancel. Backend APIs return
`PHOTO_OK` (0) for success and negative errors. A successful load can carry
recovery warnings; inspect `photo_info_t.flags`, not just its return value.

## Representation and memory

| Item | Bytes |
|---|---:|
| Complete source slot RAM | 1,909,760 |
| Packed RAW10 payload (1120 × 1364) | 1,909,600 |
| Row scratch supplied by caller | 2,241 |
| Store I/O scratch | 16,384 |
| One `photo_info_t` | 188 |
| Each generated PNG | **3,064,188** |

The store adds callback pointers and six 32-bit counters to its scratch space;
pointer width determines its total size. There is no heap allocation. PNG
working locals use approximately 650 bytes, separate from callback stack use.
Source/SD buffers must meet the actual adapter's alignment/cache requirements;
the portable layer requires word alignment for its source-slot buffer.

PNG uses grayscale16, `sample << 6`, `sBIT=10`, no filter, and one stored-DEFLATE
block per row. This deliberately leaves image compression off for the first
USB implementation. It avoids a second 3,055,360-byte unpacked image, needs no
compression workspace, and makes the advertised object length independent of
scene or read-error warnings. Native PNG CRC and zlib Adler checks protect the
generated export's transport representation; they are **not stored RAW payload
checksums** and cannot establish the original pixels were intact.

The fixed-size `eXIf` TIFF holds `ExifIFD/UserComment`, including completion
marker status, failed-read attempts, zero-filled sector count, first failed
read LBA and the absent stored-checksum limitation. Dates and orientation are
omitted. Any encountered read error or missing completion marker marks the
in-memory info recovered, and `photo_store_filename` then returns a
`_RECOVERED.png` suffix. PTP must refresh/publish that name itself; this backend
cannot rename a download already opened by the host. Do not advertise random
access to freshly regenerated partial PNGs without ensuring every part uses
the same immutable snapshot and warning metadata.

## Deletion and reuse

Deletion writes the SCR erased-byte pattern into **only** the requested slot.
It clears sectors 1–3729 in reverse groups of at most 32 sectors, proves fresh
readiness, then clears sector 0, proves readiness again and verifies the whole
header sector. The completion marker is cleared before the header becomes
free. This preserves the capture allocator's first-four-erased-bytes rule and
prevents an old completion marker from making a later partial reuse appear
complete. It does not change the capture format or add a metadata journal.

These are logical sector writes, not physical flash erase commands. They avoid
assuming CMD38 erase-group alignment for a 3,730-sector slot. USB-powered delete
transfers about 1.91 MB and may be slower than a separately qualified aligned
erase. No neighboring photo, unused end-of-card sectors, or unknown occupied
object is rewritten. Cancellation/failure before the final header keeps that
slot occupied, though an explicitly deleted photo may already be partly lost.
SD internal power-loss atomicity remains unqualified; a failed final header
write may leave ambiguous allocation state. This does not promise forensic
secure erasure, retention, ECC retirement, or NAND-specific bad-block behavior.

## Offline verification

Run from the repository root:

```powershell
python -X utf8 -m unittest discover -s firmware/usb-ptp/storage -p test_photo_store.py -v
```

The suite compiles the actual C code with warnings as errors and exercises a
memory-backed card. Seventeen cases cover geometry, mixed layouts, deletion
holes, unknown markers, metadata opacity, fresh reads, failed-DMA sanitizing,
sector recovery, safe-recovery refusal, cancellation, deletion failure/order,
neighbor preservation and reallocation. Late-error cases demonstrate that a
final sync/readback failure can follow an actually cleared header, while an
earlier cancellation can leave an occupied partial photo. PNG verification independently parses
all CRCs, zlib and TIFF fields and compares every pixel for both formats. A
generated fixture also decoded through the native Windows WIC decoder as
1120 × 1364 native grayscale16 with all low six bits zero. These are offline
checks, not USB-device integration, SD electrical or power-loss qualification.
