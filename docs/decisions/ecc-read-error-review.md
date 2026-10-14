# ECC, damaged-photo recovery and block retirement

October 14, 2026. **ECC plus CRC-32C is approved, with best-effort export of damaged photos and permanent exclusion of their blocks from future allocation.** This supersedes the earlier recommendation to fail every checksum-failing image request. PTP and explicit per-photo deletion remain accepted in [D-25](2026-10-13-project-baseline.md).

User decision: “yes lets lock in the ECC and checksum policy and record it. for marginal, we should give back as much of the image as was readable - knowing that the image might appear corrupt when viewed on the host. ideally we should also indicate that there was a read error with more info somehow - maybe in an exif tag in the image? we should also mark the blocks that image was using as BAD so new images will skip them.”

## Discussion order

1. **Settled:** device-appropriate ECC, CRC-32C, best-effort damaged-photo export, and BAD/retired blocks excluded from future writes.
2. **Current:** how the host identifies a recovered/damaged export. EXIF was suggested by the user; EXIF UserComment plus a visible filename suffix is recommended below, not yet selected.
3. Safe handling of retained data on marginal/retired blocks, including any USB-powered relocation and interruption recovery; then additional redundancy.

## Accepted read policy

Use the selected NAND's required ECC, preferably its on-die engine for serial NAND, and inspect the result of **every completed page read**. Mode bits, protected byte ranges, status encoding and thresholds must follow the exact part/revision. A successful SPI transaction is not an integrity check.

Generate and store **CRC-32C for the original image at capture/save time**, then compare the reconstructed image against that stored checksum on USB retrieval. Protect image identity, length and essential metadata too. ECC corrects errors within its capability; CRC-32C detects residual corruption and assembly/addressing mistakes with finite detection strength. Never replace the original checksum with one computed from suspect data and call the original image verified. CRC representation and metadata coverage remain format implementation details.

| Read outcome | Accepted response |
|---|---|
| No ECC errors and original checksum matches | Return the photo normally. |
| Routine ECC correction and checksum matches | Return the corrected, verified photo normally; retain available health status. Correction alone does not mean damaged pixels or require retiring every block. |
| Device-defined marginal correction status, checksum matches | Return the complete verified photo, distinguish a storage-health warning from corrupt-image data, and retire the blocks used by that image from future allocation. Follow device-required handling of retained contents; retirement alone does not refresh them. |
| Uncorrectable ECC or checksum mismatch after bounded, documented recovery | Return as much image data as can be recovered, explicitly identified as damaged/unverified. Preserve the NAND record and original checksum, report available error details, and retire the blocks used by that image. Keep unaffected photos accessible. |
| Required identity/length/allocation metadata cannot be trusted, or no usable photo representation can be formed | Do not guess addresses or expose unrelated data. Preserve records, report the failure, and recover only safely attributable data. Apply F-10 for catalog/allocation damage that cannot be localized. |
| Link failure, truncation or host cancellation | Follow the real transport-error/cancellation flow; never claim all advertised bytes were transferred. Never auto-delete source data. |

Here, **marginal** refers to the selected part's defined high-correction status; it is distinct from routine corrected reads and uncorrectable data. The user's damaged-image direction also covers residual ECC/checksum failures. Exact numeric thresholds and retry limits follow the final part and qualification.

## Best-effort export and diagnostics

Retain available data even when some returned bytes cannot be trusted. Recoverable ranges must remain at their original image positions: do not concatenate good pages and shift all subsequent pixels. If a range yields no bytes, use an explicitly documented placeholder representation to preserve geometry; its fill value/encoding is still to select. Returned-but-unverified bytes should not be silently treated as verified or discarded solely because ECC failed. A whole-image CRC mismatch alone cannot locate bad pixels; report the location as unknown unless independent evidence localizes it. Missing optional time/orientation retains the BAD/omit-EXIF behavior.

Prefer preparing the entire approximately 1.916 MB RAW10 image and its integrity classification in RAM before export, if the firmware memory budget permits. Form a valid export container/header around recovered pixels where possible; visible pixel corruption is acceptable, but not every application is guaranteed to display every damaged export. Preserve source bytes for later attempts and explicit user deletion. Generating an export does not rewrite the source image or its original CRC.

**Recommended warning representation, pending selection:** use a visible `_RECOVERED` filename suffix for damaged/unverified exports and an EXIF **UserComment (0x9286)** when the chosen export format supports EXIF. Include integrity state, original CRC/check result, counts of uncorrectable pages, known affected image ranges, missing/fill ranges and block-retirement status. Record unknown locations or counts as unknown. Distinguish `verified-after-correction`, `verified-storage-marginal` and `damaged/unverified`; do not label a checksum-valid corrected image as visually corrupt. Detailed encodings and any diagnostic sidecar remain open.

EXIF can carry the information but does not guarantee a visible warning in every importer/viewer; a filename suffix provides another cue, although hosts may rename files. Export format, tag encoding, PTP object metadata/size, stable handles and host behavior need testing. No vendor-specific PTP extension or sidecar is selected.

## PTP transfer status versus image integrity

PTP defines failure responses including `GeneralError` (0x2002) and `IncompleteTransfer` (0x2007). A failed transfer can cause the host to discard received bytes, so it cannot be the sole warning mechanism for an image the user wants to keep.

A **complete, explicitly identified recovered-image object can finish its PTP transfer successfully while documenting that the original image failed integrity checks**. This reports delivery of the advertised recovery object, not an intact original capture. Genuine transfer failure, or inability to construct a safe object, still uses the applicable error/abort path. Validate object information and payload length consistently; do not silently truncate an ordinary photo object or claim an unverified source passed its CRC.

The inspected USBX PIMA GetObject implementation sends final OK only on callback success and stalls Bulk IN on callback error. Callback errors do not automatically become clean GeneralError/IncompleteTransfer responses. Test or adapt that path, including subsequent requests, disconnects and host handling of recovered files. A native host dialog with detailed NAND diagnostics is not assumed.

## Accepted BAD/retirement policy

Permanently exclude **all storage blocks allocated to the affected image** from new-photo allocation when it is marginal or fails integrity, as requested. This deliberately retires potentially healthy blocks alongside the suspect ones. Routine below-threshold correction with a valid checksum is not that trigger. USB faults, missing optional metadata or firmware failures alone are not evidence of NAND failure.

BAD means **unavailable for future allocation**, not erased, unreadable by policy, or automatically deleted. Keep the image's record and mapping readable; existing photos sharing a retired erase block remain accessible and protected. Explicit deletion may remove a photo, but must not make its retired blocks eligible for new writes. Reduced usable capacity and eventual full behavior must include these retirements.

Persist retirement in a protected, power-loss-safe allocation/bad-block record using healthy reserved storage. Do not blindly program a physical spare-area bad-block marker into live image pages: reserved-byte, ECC and partial-program rules depend on the exact part. Preserve manufacturer factory markers; factory-bad blocks were never valid image allocations. The logical retirement record must survive restart, explicit deletion and normal reuse without causing scans to discard old photos. Failure to establish trustworthy allocation state prevents unsafe new allocations under F-10.

Retirement protects **future writes**; it does not repair current contents or by itself satisfy a vendor's marginal-data refresh requirement. Safe USB relocation, spare-space handling and interrupted-maintenance recovery remain to decide. No automatic source erasure or relocation is authorized by this retirement decision.

## Evidence checked October 14

- [Alliance AS5F Rev.3.1, October 2024](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.1_O.pdf), p42, describes clean, corrected, uncorrectable and maximum-correction ECC states for the family containing **AS5F14G04SND-10LIN**. ECC status updates after completion and is cleared when ECC is disabled. The newer C variant is a distinct device; do not apply its layout blindly.
- [Micron MT29F4G01ABBFD Rev F](../../datasheets/memory/Micron_MT29F4G01ABBFD_1v8_SPI_NAND_RevF.pdf), pp45–47, requires refresh for its 7–8-bit corrected status and permits it at 4–6 bits. [Winbond W25N04KW Rev C](../../datasheets/memory/W25N04KW_datasheet_RevC.pdf), PDF pp20–23, requires refresh/removal above its threshold and describes the buffered-read/ECC mode requirements. These are candidate-specific constraints; they do not select either device or a shared numeric threshold.
- [USBX PIMA header](https://raw.githubusercontent.com/eclipse-threadx/usbx/master/common/usbx_device_classes/inc/ux_device_class_pima.h) defines the PTP response constants. [Microsoft's portable-device error reference](https://learn.microsoft.com/en-us/windows/win32/wpd_sdk/error-constants) describes the shared `0x2007` transfer-error meaning in its MTP table. [USBX GetObject implementation](https://raw.githubusercontent.com/eclipse-threadx/usbx/master/common/usbx_device_classes/src/ux_device_class_pima_object_data_get.c) supplies the stack behavior above. Source was inspected on this date; the exact firmware release still needs pinning and testing.
- [Adobe's EXIF namespace reference](https://github.com/adobe/xmp-docs/blob/master/XMPNamespaces/exif.md) identifies UserComment as EXIF tag 37510/0x9286. It establishes an available comment field, not universal host warning behavior.

## Boundaries

Ten-year room-temperature retention without power or refresh still applies through 1,000 complete reuse cycles. Best-effort recovery is a failure response, not satisfaction of that retention guarantee. The retirement reserve and capacity loss need qualification. Capture-time optional full payload readback and mandatory save/commit verification remain unchanged; this decision concerns later reads of stored photos. Exact NAND selection, physical layout, metadata protection, diagnostic presentation, maintenance and additional redundancy remain implementation or discussion work. No hardware or firmware compliance is claimed.
