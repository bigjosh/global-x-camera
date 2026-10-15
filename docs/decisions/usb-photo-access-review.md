# USB photo access and explicit deletion

October 14, 2026. **PTP with explicit per-photo deletion is approved.** The user said: “yes lets lock in PTP with explicit per-photo deletion.” This replaces the earlier host-visible drive/emulated-filesystem requirement. ECC/read-error policy was subsequently settled. On October 15 the user selected **16-bit grayscale PNG**, accepting lossless compression because export occurs on USB power (D-40).

**D-43 — USB detail review deferred, October 15:** defer PNG/PTP implementation details until firmware bring-up. Keep the selected PNG/PTP behavior and early bring-up checks for host interoperability, current-read warning/filename timing, compressed object size and RAM use. This postpones implementation choices, not those requirements. The next review is the ≤50 ms cold-power-to-exposure-start target; physical prototype modifications remain paused until the board is in hand.

Bring-up should prove two interactions early: real-host PNG list/download/delete with current-read recovery warnings, and a memory/size strategy compatible with PTP object-information requests before image data. Re-encoding one checked RAM snapshot can reduce output buffering but does not by itself settle an earlier advertised length if a later fresh NAND read produces different damaged data. These are retained engineering checks, not reasons to reopen the accepted format now.

## Accepted interface

Use **Picture Transfer Protocol (PTP) over USB**. A host can enumerate photos, obtain their information/data and send an explicit per-photo delete request. A host-visible disk filesystem is not required. PTP replaces the earlier drive-emulation requirement; MTP and USB Mass Storage below are retained comparisons. USB-powered operation, the inactive shutter and no erase merely on connection/download remain settled.

| Route | What the host accesses | Consequence for this camera |
|---|---|---|
| PTP | Camera photo objects, read requests and explicit delete requests | Fits the internal photo catalog; no FAT/exFAT emulation or host sector writes required. A camera/import interface, not an ordinary mounted disk. |
| MTP | A broader object/file-transfer interface, including deletion | Also avoids exposing a disk filesystem. Evaluate if its host/file-management behavior is needed; do not assume every host/application handles PTP and MTP identically. |
| USB Mass Storage | A block device on which the host interprets a filesystem | Familiar drive workflow. A synthesized read-only filesystem cannot support ordinary file deletion. Writable emulation must correctly interpret and persist host filesystem updates and preserve unrelated photos through interruption. |

These are interface choices; the device still needs its own durable NAND allocation, image/metadata records, ECC and recovery. Transport alone does not make packed RAW10 a recognized picture file.

## Accepted behavior and implementation obligations

- Use stable identifiers/handles to enumerate committed FULL objects and interrupted PARTIAL objects using catalog/allocation metadata. Identify PARTIAL objects as incomplete and allow retrieval and explicit deletion. Each image-data request freshly reads the original NAND image fully into RAM, checks it, and serves that request's result; do not pre-scan image payloads, reuse an earlier request's pixels, refresh or relocate images. Return all safely attributable readable image data despite media errors or missing commit/optional attributes. Generate the selected export format and EXIF where possible; omit BAD/unknown fields and use EXIF and/or PTP warnings as required by D-32. Missing EXIF or an unviewable partial image must not by itself prevent recovery. D-40 selects PNG; encoder details, thumbnail behavior and precise host compatibility remain to test.
- Treat a host's explicit per-photo delete operation as authorization to delete that selected photo. Persist deletion state safely, then reclaim NAND blocks without damaging other photos. Logical deletion and physical block erasure may occur at different times. Acknowledging deletion must mean the logical deletion is durable; physical erase scheduling and interrupted-erase recovery remain implementation work.
- Download/read success does not itself trigger deletion or prove the host has durably backed up the photo. The host application can offer a user-selected delete-after-import workflow that sends a separate delete request. Report transfer/delete failures to the host. Distinguish successful delivery of an explicitly identified recovered image from verification of the original image; host-visible integrity diagnostics must preserve the user's ability to keep recovered bytes.
- Current-read error/incomplete warnings use EXIF and/or PTP under D-32; retain _RECOVERED naming, but PTP can supply a filename before the payload read detects a new error. Qualify object-information updates and real host behavior; the returned EXIF must describe the actual RAM buffer. No background image scan is permitted to precompute warning names.
- Keep capture disabled in USB mode even though PTP includes optional remote-camera operations. Advertise only supported operations. Preserve the accepted incomplete USED/not-DONE policy and avoid accidental reclamation when other photos are deleted.

PTP gives firmware a specific image-delete request instead of filesystem block changes. The protocol choice is approved, but the stack is not integrated or qualified. Test list/download/delete, errors and disconnect recovery on the Nucleo and intended hosts before freezing implementation. D-40 selects 16-bit grayscale PNG, generated with lossless compression on USB power from the checked RAW10 buffer.

## Exported image format — PNG selected October 15

**D-40 — USB export, approved October 15:** generate 16-bit grayscale PNG with lossless compression while USB-powered. Preserve all ten sensor bits; NAND retains the single uncompressed packed-RAW10 photo object. For each host image-data request, read NAND freshly into RAM, check it, then encode that result with the accepted metadata/recovery warnings. Exact reversible sample mapping, encoder/workspace, PTP length handling and host interoperability remain implementation work.

The user said: “16-bit grey PNG for now. compression is OK since we will be doing it while on USB power.” This selects PNG over the earlier TIFF recommendation. The alternatives below remain comparison evidence.

PNG implementation work: define reversible sample scaling and significant-bit metadata (`sBIT=10`), describe linear sensor samples correctly, and carry the accepted EXIF fields/UserComment in `eXIf`. Omit unavailable time/orientation fields. Compression settings are not frozen. Determine the compressed size for PTP object information/transfer from the same checked RAM snapshot, or use another protocol-correct size strategy; budget buffering or repeat encoding without another NAND payload read. No background image scans or substitution of older image reads is permitted. Qualify filename/error-warning timing with the actual host.

| File option | All ten sensor bits retained? | Benefits and tradeoffs |
|---|---|---|
| Uncompressed 16-bit grayscale TIFF | Yes, with a documented reversible sample mapping | Simple fixed-size encoder, straightforward pixel inspection and Exif metadata. Approximately 3.07 MB per native image plus metadata. Deliberate sample scaling/linear interpretation is needed; test the intended viewers and PTP importers. |
| Monochrome DNG | Yes | Raw-camera interpretation, including black/white levels, plus Exif. More tags and validation than a basic TIFF. An initial uncompressed 16-bit implementation has the same pixel size. Custom monochrome-camera compatibility still needs testing in intended raw editors. |
| **16-bit grayscale PNG — selected, D-40** | Yes | Lossless DEFLATE and variable output size; supports significant-bit and Exif metadata. More encoding work than an uncompressed TIFF; application handling of metadata varies. |
| Ordinary 8-bit grayscale JPEG | No | Convenient viewing and smaller, lossy files. Requires rendering/tone mapping and compression. Consider a later convenience rendition, not the only export when retaining all original precision matters. |

Native image arithmetic: 1124 × 1364 = 1,533,136 pixels; packed RAW10 payload = **1,916,420 bytes**. A 16-bit export uses **3,066,272 pixel bytes** (3.07 decimal MB / 2.92 MiB), excluding headers, metadata and any preview. This is USB output size, not an increase in NAND allocation. Export generation occurs under USB power, after the accepted fresh whole-image NAND-to-RAM read and integrity check. A second full expanded-image RAM buffer is not inherently required: uncompressed samples can be expanded in chunks from the checked buffer. Firmware still needs a complete RAM and transfer-length budget.

Implementation findings, not additional approvals:

- A 16-bit TIFF containing unscaled values 0–1023 will generally look very dark. Define reversible full-range scaling and correct linear-light interpretation; do not silently label raw linear pixels as display-encoded sRGB. PNG provides `sBIT=10` for original precision after scaling. DNG can retain original sample codes and describe black/white levels explicitly.
- A monochrome DNG can use one sample per pixel with LinearRaw interpretation; no Bayer demosaicing is involved. A packed 10-bit DNG is not a direct copy of MIPI RAW10 packing. Initial 16-bit unpacking avoids that packing mismatch.
- TIFF, DNG, PNG and Exif/JPEG have recognized PTP object-format identifiers, but that does not guarantee import, thumbnail, deletion or warning display in every host application. Windows WIC explicitly supports 16-bit grayscale TIFF/PNG and 8-bit grayscale JPEG; a decoder table is not an end-to-end camera qualification.
- Build a valid recovered-image container around available pixels where possible, with clearly identified missing ranges and the accepted warnings. Do not discard readable bytes merely because a valid picture cannot be constructed. No change to D-28/D-32: `_RECOVERED` and Exif UserComment and/or PTP diagnostics remain required as applicable; optional missing metadata must not block recovery. Warning-name timing when PTP requests object information before reading payload remains open for every format.
- A later USB-only preview could be derived from the same NAND object without storing another photo copy. It is not selected now; exposing multiple PTP objects for one photo would require explicit deletion semantics.

Sources checked October 15:

- [Microsoft WIC native codec formats](https://learn.microsoft.com/en-us/windows/win32/wic/-wic-codec-native-pixel-formats): TIFF, PNG and JPEG decoder/encoder tables.
- [Adobe DNG 1.7.1 specification](https://helpx.adobe.com/content/dam/help/en/camera-raw/digital-negative/jcr_content/root/content/flex/items/position/position-par/download_section_733958301/download-1/DNG_Spec_1_7_1_0.pdf): raw interpretation, packing, black/white levels and Exif structure.
- [W3C PNG specification, third edition](https://www.w3.org/TR/png-3/): 16-bit grayscale, lossless coding, significant bits and `eXIf`.
- [libgphoto2 PTP definitions](https://github.com/gphoto/libgphoto2/blob/master/camlibs/ptp2/ptp.h): Exif/JPEG `0x3801`, PNG `0x380B`, TIFF `0x380D`, DNG `0x3811` (PTP 1.1); TIFF/EP is a separate code.
- [CIPA Exif specification](https://www.cipa.jp/std/documents/e/DC-X008-Translation-2019-E.pdf): UserComment tag and character-code prefix.

## Primary evidence checked October 14

- [USB-IF Still Image Capture Device class](https://www.usb.org/document-library/still-image-capture-device-definition-10-and-errata-16-mar-2007) defines the USB still-image transport class.
- [Microsoft WPD driver overview](https://learn.microsoft.com/en-us/windows-hardware/drivers/portable/wpd-drivers-overview) documents built-in class-driver support for PTP, MTP and MSC over USB. This establishes available OS infrastructure, not automatic compatibility of unfinished firmware or every image format/application.
- [Apple ImageCaptureCore camera API](https://developer.apple.com/documentation/imagecapturecore/iccameradevice?language=objc) exposes PTP commands, downloads and deletion capabilities. [Image Capture's user guide](https://support.apple.com/en-gb/guide/image-capture/-imgcp1003/mac) documents camera import and optional deletion afterward; available options depend on the connected device.
- [ST USBX documentation](https://dev.st.com/stm32cube-docs/mw-usbx/2.1.0/en/docs/markup/getting_started.html) provides device-side PIMA/MTP classes and object-data interfaces, so there is existing middleware to investigate. The chosen firmware framework, exact STM32N6 port and host interoperability remain unqualified; no firmware-stack decision is implied.
- Eclipse ThreadX USBX's [object-delete handler](https://github.com/eclipse-threadx/usbx/blob/master/common/usbx_device_classes/src/ux_device_class_pima_object_delete.c) calls the application's deletion callback and returns a result to the host. Its [object-data path](https://github.com/eclipse-threadx/usbx/blob/master/common/usbx_device_classes/src/ux_device_class_pima_object_data_get.c) uses application callbacks to obtain object information/data. These support a custom record store instead of requiring a FAT volume in this interface layer.

## Discussion queue

1. **Settled:** PTP camera interface and explicit per-photo host deletion.
2. **Settled:** [ECC/CRC-32C, damaged-photo recovery and block retirement](ecc-read-error-review.md). Complete recovered-image objects may transfer successfully while carrying integrity warnings; real transfer failures still report errors.
3. **Settled:** `_RECOVERED` filename suffix plus EXIF UserComment for damaged exports.
4. **Settled:** fresh full-image NAND-to-RAM reads only on host image-data requests, no relocation/refresh, and predictive-error slot retirement without deleting the image.
5. **Settled:** one stored object contains pixels and photo attributes, without duplication; storage-control redundancy depends on implementation (D-31). Journaling remains provisional (D-30).
6. **Settled, D-32:** best-effort retrieval and explicit deletion of PARTIAL objects, returning readable image data with EXIF and/or PTP warnings. Ten-year retention remains a qualification requirement; repeated reads of an already marginal image are not guaranteed to succeed.
7. **Provisional allocation, D-33:** circular FREE-and-GOOD search with journal/checkpoint cursor recovery. Detailed page/block design and off-NAND table alternatives remain open. D-37 settles the firmware starting point; runtime/USB middleware and host interoperability remain implementation decisions.
8. **Settled, D-40:** 16-bit grayscale PNG with lossless compression while USB-powered. RAW10 NAND storage remains unchanged; exact encoding, metadata, sample mapping, memory and PTP size/host behavior remain to implement.

The [decision register](2026-10-13-project-baseline.md) remains authoritative. D-25 supersedes the drive-presentation portion of D-12 and selects explicit per-photo deletion; USB power and inactive-shutter requirements remain unchanged.
