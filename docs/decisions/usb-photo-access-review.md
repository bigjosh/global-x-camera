# USB photo access and explicit deletion

October 14, 2026. **Research and proposal, not a replacement decision.** The user approved 1,000 complete storage reuse cycles, moved to error correction, and asked whether hosts know a protocol for transferring photos and identifying images to delete without filesystem emulation.

## Answer and recommendation

**Yes: Picture Transfer Protocol (PTP) provides object-level camera access.** A host can enumerate photos, obtain their information/data and send an explicit object-delete request. A host-visible disk filesystem is not required. Recommend evaluating **PTP over USB** first for this camera; MTP is a broader related object-transfer alternative. This recommendation would replace the earlier host-visible drive requirement if approved. USB-powered operation, the inactive shutter and no erase merely on connection/download remain settled.

| Route | What the host accesses | Consequence for this camera |
|---|---|---|
| PTP | Camera photo objects, read requests and explicit delete requests | Fits the internal photo catalog; no FAT/exFAT emulation or host sector writes required. A camera/import interface, not an ordinary mounted disk. |
| MTP | A broader object/file-transfer interface, including deletion | Also avoids exposing a disk filesystem. Evaluate if its host/file-management behavior is needed; do not assume every host/application handles PTP and MTP identically. |
| USB Mass Storage | A block device on which the host interprets a filesystem | Familiar drive workflow. A synthesized read-only filesystem cannot support ordinary file deletion. Writable emulation must correctly interpret and persist host filesystem updates and preserve unrelated photos through interruption. |

These are interface choices; the device still needs its own durable NAND allocation, image/metadata records, ECC and recovery. Transport alone does not make packed RAW10 a recognized picture file.

## Proposed mapping, pending approval

- Use stable photo identifiers/handles to enumerate committed records and serve object metadata and image bytes. Generate the selected export format and valid EXIF during USB access as already planned; omit BAD fields. File format/container, thumbnail behavior and precise host compatibility remain to test.
- Treat a host's explicit photo-delete operation as authorization to delete that selected photo. Persist the resulting deletion state safely, then reclaim NAND blocks without damaging other photos. Logical deletion and physical block erasure may occur at different times. Per-photo deletion, as distinct from a separate explicit erase action, is not yet an approved product behavior.
- Download/read success does not itself trigger deletion or prove the host has durably backed up the photo. The host application can offer a user-selected delete-after-import workflow that sends a separate delete request. Report transfer/delete failures to the host.
- Keep capture disabled in USB mode even though PTP includes optional remote-camera operations. Advertise only supported operations. Preserve the accepted incomplete USED/not-DONE policy and avoid accidental reclamation when other photos are deleted.

PTP improves the semantic fit: firmware receives a specific image-delete request rather than inferring intent from filesystem block changes. This is an engineering recommendation, not proof that a complete PTP stack is already integrated or smaller than every possible MSC implementation. A minimal list/download/delete interoperability test on the Nucleo and intended hosts should precede freezing the implementation.

## Primary evidence checked October 14

- [USB-IF Still Image Capture Device class](https://www.usb.org/document-library/still-image-capture-device-definition-10-and-errata-16-mar-2007) defines the USB still-image transport class.
- [Microsoft WPD driver overview](https://learn.microsoft.com/en-us/windows-hardware/drivers/portable/wpd-drivers-overview) documents built-in class-driver support for PTP, MTP and MSC over USB. This establishes available OS infrastructure, not automatic compatibility of unfinished firmware or every image format/application.
- [Apple ImageCaptureCore camera API](https://developer.apple.com/documentation/imagecapturecore/iccameradevice?language=objc) exposes PTP commands, downloads and deletion capabilities. [Image Capture's user guide](https://support.apple.com/en-gb/guide/image-capture/-imgcp1003/mac) documents camera import and optional deletion afterward; available options depend on the connected device.
- [ST USBX documentation](https://dev.st.com/stm32cube-docs/mw-usbx/2.1.0/en/docs/markup/getting_started.html) provides device-side PIMA/MTP classes and object-data interfaces, so there is existing middleware to investigate. The chosen firmware framework, exact STM32N6 port and host interoperability remain unqualified; no firmware-stack decision is implied.
- Eclipse ThreadX USBX's [object-delete handler](https://github.com/eclipse-threadx/usbx/blob/master/common/usbx_device_classes/src/ux_device_class_pima_object_delete.c) calls the application's deletion callback and returns a result to the host. Its [object-data path](https://github.com/eclipse-threadx/usbx/blob/master/common/usbx_device_classes/src/ux_device_class_pima_object_data_get.c) uses application callbacks to obtain object information/data. These support a custom record store instead of requiring a FAT volume in this interface layer.

## Discussion queue

1. **Current:** whether to replace drive emulation with a PTP camera interface and explicit per-photo host deletion.
2. **Next:** ECC, end-to-end integrity checks, handling corrected versus uncorrectable reads, and any optional maintenance while USB-powered. PTP/MTP/MSC do not replace NAND error correction. Previously accepted unreadable-photo behavior remains host-visible USB error reporting; ten-year retention must not depend on periodic power or refresh.

The [decision register](2026-10-13-project-baseline.md) remains authoritative. D-12 has not yet been superseded.
