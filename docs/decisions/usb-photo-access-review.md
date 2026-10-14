# USB photo access and explicit deletion

October 14, 2026. **PTP with explicit per-photo deletion is approved.** The user said: “yes lets lock in PTP with explicit per-photo deletion.” This replaces the earlier host-visible drive/emulated-filesystem requirement. The user has moved on to ECC and read-error handling, including reporting failures over PTP.

## Accepted interface

Use **Picture Transfer Protocol (PTP) over USB**. A host can enumerate photos, obtain their information/data and send an explicit per-photo delete request. A host-visible disk filesystem is not required. PTP replaces the earlier drive-emulation requirement; MTP and USB Mass Storage below are retained comparisons. USB-powered operation, the inactive shutter and no erase merely on connection/download remain settled.

| Route | What the host accesses | Consequence for this camera |
|---|---|---|
| PTP | Camera photo objects, read requests and explicit delete requests | Fits the internal photo catalog; no FAT/exFAT emulation or host sector writes required. A camera/import interface, not an ordinary mounted disk. |
| MTP | A broader object/file-transfer interface, including deletion | Also avoids exposing a disk filesystem. Evaluate if its host/file-management behavior is needed; do not assume every host/application handles PTP and MTP identically. |
| USB Mass Storage | A block device on which the host interprets a filesystem | Familiar drive workflow. A synthesized read-only filesystem cannot support ordinary file deletion. Writable emulation must correctly interpret and persist host filesystem updates and preserve unrelated photos through interruption. |

These are interface choices; the device still needs its own durable NAND allocation, image/metadata records, ECC and recovery. Transport alone does not make packed RAW10 a recognized picture file.

## Accepted behavior and implementation obligations

- Use stable identifiers/handles to enumerate committed FULL objects and interrupted PARTIAL objects using catalog/allocation metadata. Identify PARTIAL objects as incomplete and allow retrieval and explicit deletion. Each image-data request freshly reads the original NAND image fully into RAM, checks it, and serves that request's result; do not pre-scan image payloads, reuse an earlier request's pixels, refresh or relocate images. Return all safely attributable readable image data despite media errors or missing commit/optional attributes. Generate the selected export format and EXIF where possible; omit BAD/unknown fields and use EXIF and/or PTP warnings as required by D-32. Missing EXIF or an unviewable partial image must not by itself prevent recovery. File format/container, thumbnail behavior and precise host compatibility remain to test.
- Treat a host's explicit per-photo delete operation as authorization to delete that selected photo. Persist deletion state safely, then reclaim NAND blocks without damaging other photos. Logical deletion and physical block erasure may occur at different times. Acknowledging deletion must mean the logical deletion is durable; physical erase scheduling and interrupted-erase recovery remain implementation work.
- Download/read success does not itself trigger deletion or prove the host has durably backed up the photo. The host application can offer a user-selected delete-after-import workflow that sends a separate delete request. Report transfer/delete failures to the host. Distinguish successful delivery of an explicitly identified recovered image from verification of the original image; host-visible integrity diagnostics must preserve the user's ability to keep recovered bytes.
- Current-read error/incomplete warnings use EXIF and/or PTP under D-32; retain _RECOVERED naming, but PTP can supply a filename before the payload read detects a new error. Qualify object-information updates and real host behavior; the returned EXIF must describe the actual RAM buffer. No background image scan is permitted to precompute warning names.
- Keep capture disabled in USB mode even though PTP includes optional remote-camera operations. Advertise only supported operations. Preserve the accepted incomplete USED/not-DONE policy and avoid accidental reclamation when other photos are deleted.

PTP gives firmware a specific image-delete request instead of filesystem block changes. The protocol choice is approved, but the stack is not integrated or qualified. Test list/download/delete, errors and disconnect recovery on the Nucleo and intended hosts before freezing implementation. The generated photo format remains to be selected; packed RAW10 alone is not a generally recognized picture file.

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
7. **Current:** slot allocation and wear distribution.

The [decision register](2026-10-13-project-baseline.md) remains authoritative. D-25 supersedes the drive-presentation portion of D-12 and selects explicit per-photo deletion; USB power and inactive-shutter requirements remain unchanged.
