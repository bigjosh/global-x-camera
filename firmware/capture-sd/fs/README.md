# FAT32 prototype storage

This directory vendors **FatFs R0.16 with official patches 1 and 2**, retrieved on
October 20, 2026. `../photo_fs.c` uses it to stream one PNG into a new short-name
file. It does not buffer or modify the captured frame. Hardware writing and
power-loss behavior are not established by the offline tests described here.

## Source and license

Upstream sources are [FatFs](https://elm-chan.org/fsw/ff/), its
[R0.16 archive](https://elm-chan.org/fsw/ff/arc/ff16.zip), and the
[official patch list](https://elm-chan.org/fsw/ff/patches.html).
`upstream-provenance.json` pins the exact downloaded archive/patch hashes, original
source hashes, and final committed source/configuration hashes. Downloads used
HTTPS with certificate verification enabled and explicit local destinations.
The original downloads are local ignored files; the small patch files are
committed under `patches/`. Source line endings are normalized to LF. The
copyright, redistribution condition, and disclaimer remain in the source headers
and [LICENSE.txt](LICENSE.txt).

`ff.c` contains only the two official upstream patches beyond R0.16. The local
configuration in `ffconf.h` enables explicit formatting, code page 437, one open
file lock, and the fixed date **2000-01-01**. This date is a placeholder, not an
RTC reading or capture timestamp. Long names, exFAT, trim, dynamic allocation,
RTOS locking, and multiple volumes are disabled.

## Application interface

Compile `../photo_fs.c`, `ff.c`, and `sd_diskio.c` with include paths for this
directory and `firmware/sd-storage`. The adapter calls the real `sd_card.h` driver.
Initialize the card once in the application before calling this layer; FatFs
`disk_initialize` deliberately does not initialize or reset the card again.

The application owns all mode selection:

1. `photo_fs_mount(&card)` mounts an existing FAT32 volume with 32 KiB clusters.
   It never formats, including when the card is blank or corrupt.
2. Only an explicit `photo_fs_format(&card)` creates a new MBR containing one
   FAT32 partition, two FAT copies, 32 KiB clusters, and 1 MiB data-area alignment.
   It destroys the previous filesystem. Mounting does not promise that arbitrary
   existing partition tables have only one partition; explicit formatting
   establishes that layout.
3. `photo_fs_open(conservative_max_png_bytes)` checks available cluster space,
   including one spare cluster for directory growth, and creates the first unused
   `IMG00001.TMP` through `IMG99999.TMP`. A number is skipped if either its PNG or
   TMP already exists. The create-new flag prevents overwriting an existing file.
   The capacity check does not reserve clusters; access must stay serialized.
4. Stream bytes with `photo_fs_append` or pass `photo_fs_write_callback` to the
   PNG encoder. The callback returns **one for complete success, zero for
   failure**, matching `png16_write_fn`; the other filesystem APIs return zero
   (`PHOTO_FS_OK`) for success. Every byte count is checked, including short writes and the
   declared maximum. Exceeding space, available names, or the declared maximum
   stops the save.
5. `photo_fs_finish()` performs file sync, close, card-ready sync, rename from TMP
   to PNG, and another card-ready sync. Only after all succeed is
   `report.completed` set to one. The card driver waits for its protocol and
   controller idle conditions; this is not proof against internal SD
   flash-translation-layer failure or a power cut.
6. `photo_fs_readback(name, offset, buffer, capacity, &got)` reads a generated PNG
   or TMP name in bounded caller buffers. It never opens the file for writing.
   `photo_fs_get_report()` exposes the name, bytes accepted, stage and FatFs
   result for diagnostics.

`photo_fs_abort()` closes and preserves the partial TMP when the driver has
established media idle. It never deletes data. A driver error can prevent even
this close; the caller must retain the frame and follow the system's error/park
policy, rather than treating failure as successful shutdown. This layer never
power-cycles, resets, reformats, retries a failed card, or deletes files as a
recovery action.

There is one static filesystem, one static open file, and one bound card. Calls
are synchronous and must be serialized. Transfers to the driver are split into
at most 64 sectors; arbitrary byte-aligned buffers are supported by that driver.
`GET_BLOCK_SIZE` reports the conservative value one because physical erase
alignment is unknown. No erase/trim commands are issued by the adapter.

The Cortex-M55 `-Os` object build uses **5,326 bytes of static BSS** for these
three files combined, including a 4 KiB format workspace. No heap allocation is
enabled. This excludes the caller's card state, encoder, stack, and C library.
The unlinked objects contain 10,525 bytes of text before link-time garbage
collection and library inclusion.

## Offline verification

On the Windows development host, run:

```powershell
python firmware/capture-sd/fs/tests/test_photo_fs.py
```

The test builds the actual C implementation and FatFs as a native library using
Clang, then supplies a sparse simulated card. It does not access the bench or
physical storage. **Fourteen tests passed** on October 20, 2026:

- Blank-media mount performs no writes and does not format.
- Streaming across sector/cluster boundaries commits the exact payload, and
  bounded readback returns the expected bytes.
- An independent Python MBR/BPB/FAT reader checks the single partition, cluster
  size, both FAT copies, directory entries and file contents.
- Existing PNG files survive subsequent saves; abort preserves TMP; occupied
  PNG/TMP names are skipped; remount preserves content and numbering.
- A sparse card using the bench card's reported 62,723,719,168-byte capacity can
  be formatted and used with this layout. This does not validate physical card
  capacity.
- Full-space preflight, maximum-length enforcement, invalid paths and concurrent
  operation guards reject unsafe requests.
- Injected write and sync failures do not report a completed PNG.
- The actual PNG encoder streams through the actual C filesystem callback in all
  three compression modes. Files are independently read from FAT32, decoded using
  PNG chunk CRC checks and zlib, and compared with every RAW10 sample shifted
  left six bits. Filesystem readback matches those bytes; the input frame remains
  unchanged. Direct callback tests cover success, bounds failure and disk failure.
- Vendored source/configuration hashes match the pinned manifest.

The same three C files also compile for Cortex-M55 with GCC 12.3 using
`-Os -Wall -Wextra -Werror`. These tests establish software behavior under the
modeled block-device contract. They do not establish hardware write throughput,
write energy, recovery from removal/power loss, long-term retention, or card
endurance. Two FAT copies are conventional filesystem redundancy, not a journal
or a guarantee that prior photos survive arbitrary power interruption.
