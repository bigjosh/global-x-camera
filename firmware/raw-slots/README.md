# Fixed RAW image slots

## Front-metadata magic slots selected October 24

The selected format is implemented in `magic_slots.c/.h`, with read-only
inspection/extraction in `magic_slots.py`. The user retained fixed RAW slots for
their simplicity and expected fit with future NAND storage, independent of the
small and inconclusive SD timing/energy difference. The former 152 bytes of tail
padding now precede the image, reserving space for photo metadata that can be read
alongside the occupied marker in one logical-sector read. This changes neither
the slot capacity nor the number of sectors written.

New objects use `GXR2` to distinguish them from the previously qualified `GXRS`
objects, whose image starts 152 bytes earlier. The reader supports both formats
on the same card. The older superblock-based version-1 implementation and parser
remain unchanged below so historical evidence is still readable. Source changes
do not establish installed firmware or physical qualification; see the capture
firmware's current bench checkpoint.

Commissioning explicitly erases the **entire card** through the SD driver's
erase operation and waits for successful card readiness. Every allocation scan
uses the erased byte reported by that card's SCR `DATA_STAT_AFTER_ERASE`: value 0
means byte `0x00`, value 1 means byte `0xff`. The byte is never inferred from a slot
that happens to look empty. The old `raw_slots_format()` only writes headers and
does **not** establish this new format's erased-card precondition. Erase is a
separate operator-authorized operation, never automatic on boot or a mount error.
There is no on-card generation, superblock or allocation table. The new metadata
region is reserved and currently initialized to zero; a schema for timestamps,
orientation and other fields is deferred. Zero is not a valid-date indication.
An interrupted commissioning erase is not a completed format and must be repeated
successfully before use. Ordinary SD erase is not a secure data-sanitization claim.

Each slot is **3730 consecutive 512-byte logical sectors**, starting at LBA
`slot_index * 3730`; slot zero begins at **LBA 0**. The final fraction of a slot
at the end of the card is unused. Each image writes every sector of its slot once.

| Offset within slot | Bytes | Contents |
| --- | ---: | --- |
| 0 | 4 | Leading magic: ASCII `GXR2` (`0x32525847` little endian) |
| 4 | 152 | Opaque photo-metadata reservation; zero until a schema is implemented |
| 156 | 1,909,600 | Packed MIPI RAW10, 1120 × 1364 samples, 1400 bytes per row |
| 1,909,756 | 4 | Completion magic: ASCII `GXRE` (`0x45525847` little endian), the final four bytes of the slot |

The first sector contains the leading magic, all 152 metadata bytes and the first
356 image bytes. There is no trailing padding. Metadata is part of the same stored
object and is written once with the image; it does not need a separate header write
or a second copy. The storage core accepts arbitrary metadata bytes and does not
mistake future nonzero fields for damaged padding.

The previous `GXRS` layout remains readable: image offset 4, completion marker at
1,909,604, then 152 zero padding bytes. It has the same 3730-sector stride and
allocation rule. Existing objects can be preserved while new captures append
`GXR2` objects; this layout change alone does not require erasing the card. Both
markers are distinct from either supported erased-byte pattern. The allocator
also skips unknown or damaged non-erased markers.

Allocation reads one complete sector per slot, beginning at slot zero, and
compares only its first four bytes. Four copies of the SCR-reported erased byte
mean FREE; **every other word is occupied**, including unknown or damaged magic.
A read error stops the search and never creates free space. Search returns the
first FREE slot, or reports full without overwriting occupied images. This is a
linear scan and grows with the number of occupied slots. No slot reclamation or
per-photo deletion is implemented. Sequential logical addresses do not establish
the physical NAND placement or write amplification inside the card.

The leading magic and metadata are prepared before publication to storage. The
camera writes image samples immediately after the 156-byte prefix. DCMIPP Pipe0
requires a **16-byte-aligned image address**,
whereas SDMMC IDMA requires a four-byte-aligned source. A no-copy layout uses
slot buffer `0x34000004` and camera destination `0x340000A0`. The caller owns the
changed frame bounds and guard checks. It prepares the trailing magic only after
the complete frame passes required capture validation, then
publishes the final sector to the transport. This permits a one-pass forward write
with no separate PARTIAL/FULL sector write or later overwrite of the first block.
The completion marker is not a checksum and cannot detect arbitrary corruption
within the pixels or guarantee atomicity under unexpected card power loss.

```c
magic_slots_t slots;
magic_slots_open(&slots, &card, scr_reported_erased_byte);
magic_slots_find_free(&slots);
/* Prepare GXR2 and the 152 metadata bytes before their publication. The transport
   consumes only published bytes,
   withholding the final sector until capture validation and GXRE preparation. */
magic_slots_write(&slots, slot_buffer, progressive_writer, writer_context);
```

Check every return value. `open()` validates capacity and the supplied erased
byte but does not perform a disk write or certify commissioning. `write()` invokes
the callback exactly once for the complete selected 3730-sector extent. On return
it checks transport success, card idle, the exact written-sector count and both RAM
markers; it does not scan/copy/checksum the image or interpret metadata. Successful
transport must include fresh readiness, and the capture owner's guard/STOP and
shutdown checks remain required. The callback owns producer pacing and SD command
sequencing. Repeated old blocking-write calls would create separate transactions;
they do not constitute one progressively fed CMD25. A failed attempt retains the
slot as active/failed in RAM and is never retried or marked FREE by this layer.

Host extraction requires the recorded erased byte and known capacity. An ordinary
image file can supply its own extent; an explicitly identified physical device
requires `--sectors`. The utility opens only the named source, read-only, and
refuses to overwrite existing output files. The qualified prototype card reports
`0x00`; substitute the actual SCR-reported byte for another card:

```powershell
python firmware/raw-slots/magic_slots.py card.img --erased-byte 0x00 list --all
python firmware/raw-slots/magic_slots.py card.img --erased-byte 0x00 list --all --check-completion
python firmware/raw-slots/magic_slots.py card.img --erased-byte 0x00 extract 0 photo.png
python firmware/raw-slots/magic_slots.py card.img --erased-byte 0x00 extract 0 photo.raw10 --kind raw
```

Default `list` uses `read_header()`/`parse_header()` and reads exactly one sector
per slot. It reports FREE or OCCUPIED, the detected layout and the new format's
opaque `metadata_hex`; `metadata_schema` remains null. It explicitly reports
`completion_checked=false` and `completion_marker_valid=null`. Directory listing
cannot establish a complete image without reading the final sector.

`list --check-completion` and the two-sector `read_slot()` inspect the footer too.
Two valid markers classify an object COMPLETE. Valid leading magic without a
trailing magic is PARTIAL; unknown non-erased leading magic is OCCUPIED. None of
those states makes space reusable. `--allow-partial` permits recovery of known
`GXRS` or `GXR2` PARTIAL objects with an explicit corruption warning. Unknown magic
is refused even with this flag: silently guessing an image offset could shift
every recovered pixel. FREE objects are never extracted. The reader does not
synthesize a missing sector or report a short read as free space. RAW output
uses each object's detected image offset and strips markers, metadata and any old
tail padding. PNG output reconstructs
16-bit grayscale samples as `sample << 6`, with `sBIT=10`; its text comment contains
derived inspection results and the raw metadata reservation when present; it does
not invent capture times from the reserved zeros.

Run both format generations' host tests with the command at the end of this file.
The new C-core tests exercise both erased polarities, damaged first words, full
and truncated slots, read/write errors, exact sector counts, word-aligned/no-copy
buffers, arbitrary nonzero metadata and idle/marker failure gates. Python checks
mixed `GXRS`/`GXR2` cards, exact one-sector header reads, distinct image offsets,
the resulting container, every RAW10 sample, PNG chunk CRCs and all exported pixels. These are
offline tests, not physical erase, streaming or power-loss qualification.

Reference: [ST RM0486 Rev4](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf),
DCMIPP base alignment on page 1923 and SDMMC IDMA alignment on page 1451.

## Legacy version-1 format and interface

This storage core saves the hardware-qualified packed RAW10 frame directly to
consecutive SD logical sectors. It performs no image conversion, compression or
full-frame checksum pass. Capture timing, producer publication, cache ownership,
DMA selection and shutdown belong to the caller. The ordinary PNG/FAT32 format
is replaced only by an **explicit format operation**; `raw_slots_open()` never
formats or overwrites an unknown card.

The implementation is tested offline against the actual compiled C core and an
independent Python reader. Hardware results belong to the integrated capture
firmware's measurement record; these unit tests do not establish hardware timing
or power-loss protection.

## Interface and pipeline

```c
raw_slots_t slots;                 /* outside the capture buffer */
raw_slots_open(&slots, &card);     /* card already initialized */
slots.write_payload = sd_write_blocks_dma; /* optional; default uses PIO */
raw_slots_find_free(&slots);      /* scans one header per slot */
raw_slots_begin(&slots, &metadata); /* durable protocol completion of PARTIAL */
/* Append completed, DMA-visible sectors in producer order. The callback is
   synchronous; camera acquisition can continue independently in interrupts. */
raw_slots_append(&slots, completed_buffer, completed_sector_count);
/* ... until 3729 whole sectors have been accepted ... */
raw_slots_finish(&slots, final_352_bytes);
/* Only successful card idle/deinit and the capture owner's completion checks
   authorize the caller's later shutdown. Check every return value. */
```

The example names an optional DMA transport; it is supplied by the SD driver,
not this directory. Both transports have the same synchronous return contract.
All payload sectors go directly from the caller's buffer to that transport. Only
the final 352 image bytes are copied, into a 512-byte aligned scratch sector whose
160 padding bytes are zero. The metadata sector also uses this aligned scratch
area. The storage object requires 32-byte alignment because its `io` member is
aligned for IDMA. Payload buffers must satisfy the selected transport's alignment
and cache visibility rules. The caller must never publish bytes still being
written by the camera.

`raw_slots_finish()` requires exactly 3729 prior whole sectors, writes the final
sector, checks fresh card ready, writes FULL, then checks fresh card ready again.
The driver never enables an optional card write cache. “Ready” means the card
reports READY/TRANSFER, DAT0 is high and the host is idle. It does not guarantee
that an SD card's internal flash translation layer survives arbitrary power loss.
An error leaves the operation active/failed; it is never permission to cut power.

The opt-in whole-image path keeps the same on-card format. After `begin()`,
set `write_payload = sd_write_blocks_dma_preerase` and call
`raw_slots_write_padded()` once with the entire immutable, 32-byte-aligned
**1,909,760-byte** buffer. The core checks its last 160 bytes are zero and makes
one callback for all 3730 payload sectors; it does not copy the frame or include
its header in the announced range. The caller must allocate the padding and
validate camera completion and any frame guard before writing those zero bytes.

`raw_slots_write_padded()` leaves the slot PARTIAL. After any remaining capture,
sensor-STOP and guard checks pass, `raw_slots_commit()` requires all 3730 sectors,
checks fresh READY, writes the separate FULL header, and checks READY again.
The original `append()`/`finish()` sequence remains available and unchanged in
purpose. The [SD driver](../sd-storage/README.md) documents the preannouncement
and transaction-completion contract; this option alone makes no speed or energy
claim.

There is no full-image checksum in this format version. The SD link checks each
transfer's CRC, while the metadata CRC detects damaged headers. This avoids a
CPU pass through the frame but does not provide an independent end-to-end check
of retained pixel bytes. Hardware qualification must compare complete SD readback
against the source frame. Extraction can decode intact headers/payload; unknown
pixel corruption cannot be detected by this format alone.

## On-card format, version 1

All integers are little-endian. Logical sectors are 512 bytes. Header CRC is
standard reflected CRC-32/ISO-HDLC (polynomial `0xedb88320`, initial/final xor
`0xffffffff`), matching Python `zlib.crc32`, over bytes 0–507. Its little-endian
value occupies bytes 508–511. Reserved bytes are zero and checked when reading.

The superblock is at **LBA 0**. LBAs 1–7 are unused. Slot `i` starts at
**`8 + i * 3731`** and consists of one metadata/header sector followed by
**3730 payload sectors**. The image is 1120 × 1364 samples, **1,909,600 bytes**,
1400 bytes per row. Four RAW10 samples occupy five bytes: the four high-eight-bit
values, then their low-two-bit pairs, with the first sample in bits 1:0. There are
no row headers or padding; the final sector has 352 payload bytes and 160 zeros.

### Superblock

| Byte offset | Length | Meaning |
| --- | --- | --- |
| 0 | 8 | ASCII `GXRWVOL1` |
| 8 | 4 | Format version, 1 |
| 12 | 4 | 1 = FORMATTING, 2 = READY |
| 16 | 8 | Nonzero format generation |
| 24 | 8 | Card capacity in logical sectors |
| 32 | 4 | First slot LBA, 8 |
| 36 | 4 | Slot stride in sectors, 3731 |
| 40 | 4 | Formatted slot count |
| 44 | 4 | Image payload bytes, 1909600 |
| 48, 52 | 4 each | Width 1120, height 1364 |
| 56 | 4 | Packed bytes per row, 1400 |
| 60 | 4 | Packing identifier, 1 = MIPI RAW10 |
| 64 | 4 | Header/sector bytes, 512 |
| 68–507 | 440 | Reserved zeros |
| 508 | 4 | Header CRC |

### Slot header

| Byte offset | Length | Meaning |
| --- | --- | --- |
| 0 | 8 | ASCII `GXRAWSL1` |
| 8 | 4 | Format version, 1 |
| 12 | 4 | ASCII bytes `FREE`, `PART`, or `FULL` |
| 16 | 8 | Format generation matching the superblock |
| 24 | 4 | Zero-based slot index |
| 28 | 4 | Image payload bytes, 1909600 |
| 32 | 4 | Payload LBA = header LBA + 1 |
| 36, 40 | 4 each | Width 1120, height 1364 |
| 44 | 4 | Packed bytes per row, 1400 |
| 48 | 4 | Packing identifier, 1 |
| 52 | 4 | Metadata validity flags: bit 0 = timestamp, 1 = exposure, 2 = gains, 3 = orientation |
| 56 | 8 | Capture identifier, caller supplied |
| 64 | 8 | Capture time in microseconds, caller supplied |
| 72 | 4 | Exposure in microseconds |
| 76, 80 | 4 each | Analog and digital gain × 1000 |
| 84 | 4 | Orientation, application-defined; `0xffffffff` = unavailable |
| 88 | 4 | Completed bytes: 1909600 for FULL; zero otherwise |
| 92–507 | 416 | Reserved zeros |
| 508 | 4 | Header CRC |

For FREE, bytes 52–87 are all zero. Unknown metadata has its corresponding
validity bit clear; other metadata flags are preserved for the caller. Exposure
can be a nominal value calculated from sensor integration registers rather than
an external timing measurement. There is no allocation table or
payload duplication. Header states describe a single logical stored object.

## Allocation and formatting decisions

The caller explicitly requests `raw_slots_format(fs, card, generation_lo,
generation_hi, slot_limit)`. `slot_limit=0` uses all complete slots that fit;
a smaller limit is permitted for bounded bring-up, and is recorded in the
superblock. The final deployment format should use full capacity. Capacities
larger than 2^32 sectors are rejected by this 32-bit-LBA version.

Formatting first writes FORMATTING, waits for card ready and reads it back.
It then writes every FREE header, servicing `sd_progress()` and incrementing
`formatted_slots` after each. Finally it waits for ready, publishes READY,
waits again and verifies that superblock. A new generation must differ from a
readable previous generation; after interrupted formatting use a new generation.
An interrupted format with FORMATTING or an invalid superblock cannot mount.
This ordering is a logical consistency rule, not a sudden-power-loss guarantee
for the card's FTL.

Formatting discards the prior logical layout but **does not securely erase old
payload bytes**. It initializes only the new format and FREE headers. This avoids
writing the entire 62 GB card for a format operation. A subsequent capture
overwrites every payload byte in its selected slot.

Allocation scans from slot zero. It skips valid FULL and PARTIAL slots and stops
at the first explicit FREE header. A blank, torn, wrong-generation or otherwise
invalid header fails closed; it is never treated as free space. FULL and PARTIAL
slots are preserved. When all slots are occupied, allocation reports FULL and
does not overwrite photos. A failed capture can leave a PARTIAL slot consumed;
deletion/reclamation is not implemented here. The scan is linear and therefore
gets slower as the card fills. A persistent hint or index can later accelerate
it without changing the per-slot format, but must not become an unsafe authority
for overwriting slots.

The 3731-sector stride avoids the roughly 9% capacity loss of rounding each image
to 4096 sectors. No undocumented SD internal erase geometry is assumed. Future
four-bit operation or a faster SD card changes the transport, not this image
layout. A different image geometry requires a new format/version, not silently
reusing these fixed slots.

## Host retrieval

The utility opens the source **read-only**. It accepts a raw card image or an
operator-identified device path. It never enumerates, selects, mounts, formats,
deletes from or writes to host disks. On Windows, reading a physical card may
require an elevated terminal. Confirm the correct card/device yourself before
passing a device path; these examples use an ordinary image file.

```powershell
python firmware/raw-slots/raw_slots.py card.img list
python firmware/raw-slots/raw_slots.py card.img list --all --limit 10
python firmware/raw-slots/raw_slots.py card.img extract 0 image00000.png
python firmware/raw-slots/raw_slots.py card.img extract 0 image00000.raw10 --kind raw
```

PNG export reconstructs every sample and applies **`sample << 6`**, emits 16-bit
grayscale PNG with `sBIT=10`, and includes slot metadata in a PNG text chunk.
RAW export omits the 160 sector-padding bytes. Existing output files are refused.
A dump containing just the superblock and first complete slots can be read as a
prefix image: extraction checks every requested read, but does not infer physical
capacity from the source file's length. Superblock capacity is a recorded value,
not an independently validated capacity measurement. Listing a truncated dump
reports missing slots as errors; use `--limit` for the available prefix.
PARTIAL extraction needs `--allow-partial` and reports that unwritten sectors may
still contain older data; FREE or invalid slots are never extracted. A nonzero
tail padding is reported but does not hide recoverable image bytes. USB/PTP
retrieval is not part of this utility.

Run the tests with a host C compiler (`clang` or `gcc`) on PATH:

```powershell
python -m unittest discover -s firmware/raw-slots -p "test_*.py" -v
```

The tests compile and execute `raw_slots.c` against an in-memory SD transport,
inject errors at format/payload/sync boundaries, and produce an interoperability
fixture. The Python tests independently inspect the resulting FREE/PARTIAL/FULL
headers, check all 1,527,680 decoded samples, verify every PNG chunk CRC and sample,
and exercise damaged-header and partial-extraction behavior. Tests use temporary
files only and never access the bench or a real disk.
