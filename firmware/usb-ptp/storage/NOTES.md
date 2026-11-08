# PTP storage decisions

## 2026-11-08  Generate deterministic PNG directly from a fresh packed RAW snapshot

**Why:** USB must browse existing RAW slots and retrieve all readable image data
without adding battery-powered capture work. Keeping one 1,909,760-byte slot in
RAM and emitting grayscale16 rows preserves `sample << 6` while fitting beside
USB firmware. Stored DEFLATE and a fixed-size EXIF UserComment give an exact
3,064,188-byte object length before reading pixels. Failed transfers are not
trusted; unreadable sectors are zero-filled and described, with no invented
dates or pixel-integrity claim. The existing RAW format has no payload checksum.

**Rejected:** holding packed and full unpacked images simultaneously; assuming
compressed length from a previous read; claiming completion markers detect
silent corruption; caching successful image reads indefinitely; hiding errors
by sending stale failed-DMA contents; inventing an opaque metadata schema.
Compression remains a later USB performance choice. Freshly regenerated
partial-object downloads need a stable snapshot across their component reads.

**Evidence:** `photo_store_load`, `photo_store_png` and `test_photo_store.py`;
independent full-pixel/CRC/zlib/TIFF tests for GXR2 and GXRS; native Windows WIC
decoded the actual C-generated PNG as grayscale16 with zero low six bits.
The source format and sample mapping remain owned by
[RAW slots](../../raw-slots/NOTES.md) and [PNG encoder](../../png-encoder/NOTES.md).

## 2026-11-08  Clear an explicitly deleted slot tail first and release its header last

**Why:** fixed 3,730-sector slots need reusable holes without overwriting other
photos. The existing allocator only checks the first four bytes for the
SCR-reported erased pattern. Logical writes confined to the requested slot,
tail first and header last after a readiness barrier, remove the old completion
marker before making the slot reusable. A complete first-sector scan continues
past holes, and slot index plus one provides stable handles during USB mode.

**Rejected:** merely clearing the header and leaving an old completion marker;
issuing an unqualified arbitrary-range CMD38 that might include adjacent erase
groups; stopping enumeration at the first free slot; automatically erasing
unknown occupied objects. A new journal and power-loss-atomic SD deletion are
deferred under the user's accepted unqualified prototype power-loss policy.

**Evidence:** `photo_store_delete`, `photo_store_scan` and injected failure/
cancellation tests prove logical write boundaries, header-last ordering, fresh
readiness barriers, unaffected neighbors and reuse for both SCR erase patterns.
This is an offline implementation; it does not establish SD controller
power-loss behavior or physical erase granularity.

## 2026-11-08  Treat a late delete error as an uncertain catalogue state

**Why:** the final header write can succeed before its readiness check or
readback fails. The storage API correctly returns an error, but that return
value does not prove the object still occupies its slot. Conversely, cancelling
after tail clearing leaves an occupied header and an already damaged/partial
photo. A successful cancellation response cannot restore the requested data.
Any protocol reconciliation must first establish safe card readiness/recovery,
then use a fresh header read; an error or unknown marker is not proof of FREE.

**Rejected:** automatically retrying deletion, resetting an uncertain active
write, removing the catalogue handle solely from an error code, or claiming a
retained handle guarantees preserved pixels. A journal/atomic delete remains
outside the prototype's accepted power-loss qualification scope.

**Evidence:** three explicit offline cases in `test_photo_store.py` reproduce
final-sync failure, final-readback failure and cancellation after tail clearing.
Neighbors remain unchanged in the mock; a subsequent successful header read
distinguishes the absent object from the occupied partial one. These tests do
not claim corresponding physical-card failure behavior was observed.
