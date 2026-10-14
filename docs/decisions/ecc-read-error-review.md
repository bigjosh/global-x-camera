# ECC, host-requested reads and slot retirement

October 14, 2026. **Every USB host image-data request reads the original NAND image into RAM, checks it, and exports that request's result with warnings. There is no image relocation, refresh, background payload scan or reuse of an earlier read in place of a new NAND read.** Predictive media errors permanently retire the image slot from future writes without deleting its current image. Only an explicit host deletion authorizes removal of photo data. This approved direction replaces the previously proposed USB copy-out policy.

The user's clarification includes: “we should always read the image from NAND into RAM, check it, and then send to host what we have - with error flags or warnings included.” The user also said: “we never bother moving the image” and “So we read imagines into RAM from NAND only when USB host requests them.” A successful read followed by a later failed read of the same image is explicitly accepted.

## Discussion order

1. **Settled:** ECC/CRC-32C, best-effort export, read warnings, explicit-only deletion and permanent slot retirement.
2. **Settled:** fresh, whole-image NAND-to-RAM reads only on host image-data requests; no image relocation or background refresh.
3. **Settled:** [D-31's single-object policy](storage-redundancy-review.md): pixels and photo attributes are stored once; storage-control redundancy depends on the implementation. D-30's journal remains provisional.
4. **Settled, D-32:** PARTIAL objects are available for best-effort USB retrieval and explicit deletion. Return whatever safely attributable image data can be read and indicate read errors/incompleteness through EXIF and/or PTP.
5. **Current:** slot allocation and wear distribution; circular FREE-and-GOOD allocation is proposed, not approved.

## PARTIAL objects and universal best-effort retrieval — approved October 14

The user approved the PARTIAL-object proposal: “yes - we always send whatever image data we can read to the USB host. If we encounter any errors while reading, we indicate those in EXIF and/or over the PTP protocol so the host knows there may be corruption.”

Expose FULL and interrupted PARTIAL objects for retrieval and explicit per-object deletion. On each host image-data request, freshly attempt all image ranges safely attributable to the requested object, stage the result in RAM, and return the readable data even if other ranges fail or the save never reached its final commit. A media read error must not by itself discard already recovered bytes or suppress attempts to obtain other ranges.

PARTIAL means incomplete even if every readable page passes ECC. A missing final checksum means the original full image cannot be verified; report that condition without inventing/replacing its expected CRC. Preserve the positions of recovered bytes and distinguish unwritten, unreadable and unknown ranges. Placeholder encoding, object lengths and export container details remain implementation work; placeholders are not captured image data.

Missing optional photo attributes or inability to generate EXIF must not prevent delivery of recoverable image bytes. Keep absent attributes unknown/omitted; a generated export identifier must be distinguishable from recovered original metadata. Use EXIF and/or PTP to report known incompleteness, read errors and verification limitations. Retain the previously selected _RECOVERED naming convention for recovery exports; do not rely on naming alone to convey the current-read error details.

Best-effort export does not turn PARTIAL into FULL, certify a successful original save, duplicate/relocate the NAND object, or delete it. Both FULL and PARTIAL objects remain stored until explicit host deletion, with permanent retirement unchanged. Actual transport failures still report failure. If no image data can be obtained, report that result; if allocation boundaries are untrustworthy, do not guess addresses or expose another object's bytes.

## Accepted request-driven read sequence

1. When the host requests image data, establish safe object boundaries/mapping and read all attributable original NAND image ranges into RAM, including for PARTIAL objects. Missing commit or optional attributes do not prevent recovery from known ranges. A new request repeats this NAND read even for an image already downloaded successfully. Do not substitute an earlier RAM buffer or a copied NAND image.
2. Apply the selected NAND's required ECC and inspect every completed page-read status, continuing other attributable ranges after a failed read. Compare the payload with the original stored CRC-32C when available; a missing/invalid expected CRC is unverified, not a match. Preserve existing expected CRC and attributes; do not derive replacement expected values from suspect data.
3. Finish read attempts and integrity classification before sending image bytes to the host. Within this one transfer, serve the prepared RAM snapshot so its pixels, CRC result and EXIF diagnostics describe the same read.
4. Return as much safely attributable image content as can be read. Report corrections, marginal status, uncorrectable data or checksum failure as appropriate; do not call a checksum-valid corrected image damaged.
5. If the read provides evidence predictive of reduced future NAND reliability, persist permanent retirement for all blocks in that image slot. This affects future allocation, not current read access or photo existence.
6. Retain the current NAND photo until the host explicitly deletes it. Retired slots remain unavailable for new images after deletion, even if a later read of the old photo succeeds.

Whole-image RAM staging is mandatory, not conditional on available memory. Budget the approximately 1.916 MB packed RAW10 payload plus export buffers, metadata and USB state. Qualify request latency and host timeouts. A streaming-from-NAND fallback is not selected. Actual inability to identify safe object ranges or complete transport uses the USB error path; inability to form a viewable image or EXIF does not by itself suppress readable image data.

Reading catalog/allocation/commit metadata for enumeration and recovery remains necessary; it must not trigger image-payload scans or thumbnail generation from NAND without a host image-data request. Capture-time configurable payload readback and mandatory save/commit verification remain unchanged: this decision governs later USB retrieval of stored photos.

## ECC, integrity and warning classification

Use the exact part's ECC mode, protected byte ranges, status encoding and reliability thresholds. ECC repairs errors within its capability; CRC-32C detects residual corruption and assembly/addressing mistakes with finite detection strength. A completed SPI transaction is not proof of integrity. Protect identity, length and essential metadata as well as image pixels.

| Read outcome | Accepted response |
|---|---|
| Committed complete object, no detected errors and original CRC matches | Export the current RAM image normally. |
| PARTIAL object, including clean readable pages or unavailable final checksum | Export recovered data with incomplete/unverified diagnostics. Do not claim a successful original save or require a final checksum to return readable bytes. |
| Routine ECC corrections and original CRC matches | Export the verified corrected image with correction diagnostics. Correction alone does not imply corrupt pixels or automatically retire the slot; apply the device-specific predictive-error classification. |
| Device-defined marginal correction status, CRC matches | Export the verified image with a storage-health warning and retire the whole image slot from future writes. Leave the source in place. |
| Uncorrectable NAND data or CRC mismatch after bounded, documented recovery | Export available data as damaged/unverified, keeping original geometry and checksum history. Retire the slot if the error indicates future media unreliability; known uncorrectable NAND media errors qualify. A CRC mismatch alone does not identify the physical cause. |
| Allocation boundaries cannot be established safely | Do not guess addresses or expose unrelated bytes. Return any independently attributable ranges; preserve data and report the limitation/failure. Apply F-10 for catalog/allocation corruption that cannot be localized. |
| USB interruption, cancellation or incomplete transmission | Use the applicable transport error/cancellation response. Do not claim a complete transfer, delete the image or retire media solely because USB failed. |

The latest user clarification refines the earlier broader “marginal/damaged image” retirement wording: the trigger is a read error indicative of future block unreliability. Define and qualify the exact predictive-error classifier for the selected part; do not treat every host/firmware/checksum error as a proven physical media defect. A single whole-image CRC cannot locate bad pixels or a failed block by itself. Once retirement is established, later successful reads do not clear it.

## Best-effort export and diagnostics

Keep recovered ranges at their original image positions; do not concatenate good pages and shift later pixels. Preserve returned-but-unverified bytes as suspect data rather than silently discarding them. If no bytes can be obtained for a range, use an explicitly documented placeholder representation to preserve geometry; its fill encoding remains to select. Mark unknown locations/counts as unknown. Missing optional time/orientation retains BAD/omit-EXIF behavior.

Use the agreed **`_RECOVERED` filename suffix before the extension and EXIF UserComment (0x9286)** for an export carrying a read-error warning. The earlier explicit approval was: “yes lets use the _RECOVERED suffix and EXIF comment for damaged images.” D-32 extends recovery to PARTIAL objects and requires read errors/incompleteness through EXIF and/or PTP. Keep the selected naming convention; missing EXIF must not block recoverable-data delivery. The comment must distinguish verified-after-correction, verified-but-media-marginal and damaged/unverified results, so a warning name is not a claim that corrected pixels remain corrupt.

Diagnostics describe this request's actual RAM buffer: original CRC/check result, correction/uncorrectable status, known affected/missing ranges and slot-retirement state. Distinguish historical retirement from this read's integrity outcome. Prefer EXIF UserComment when supported by the chosen export container, with PTP reporting where appropriate or EXIF is unavailable. Exact format, tag encoding and host warning behavior remain to qualify. No separate sidecar or vendor-specific PTP extension is selected.

Form a valid export header/container where possible; visible pixel corruption is acceptable, but universal viewer support is not guaranteed. Export generation never modifies the stored image, its original CRC or location.

## PTP delivery and filename timing

A complete recovered-image object may finish its PTP transfer successfully while declaring that the source image failed integrity. Genuine transfer failure or inability to identify safe data ranges still uses the proper error/abort path; incomplete source content alone must not suppress best-effort delivery. `GeneralError` (0x2002) and `IncompleteTransfer` (0x2007) are available response codes, but an incomplete-transfer failure can cause a host to discard bytes and is not the sole warning mechanism for content intended to be kept.

PTP object information, including filename and length, is a separate request from image payload. A host may fetch or cache the name before the fresh NAND read discovers a new error. Therefore same-download filename warning behavior requires explicit qualification of object-information updates/events and real hosts; an updated camera-side name does not guarantee the host renames a file already chosen. EXIF in the returned buffer can describe the current read. Do not solve filename timing by introducing background image scans, serving stale cached pixels or silently changing the approved request-driven policy.

The inspected USBX PIMA GetObject path sends OK on callback success and stalls Bulk IN on callback error; callback errors do not automatically serialize clean standard error responses. Object size, filename updates, error handling and subsequent requests need integration tests. No guarantee of a native host dialog with detailed NAND diagnostics is implied.

## Accepted slot retirement and deletion

Persist retirement for **the whole image slot and all blocks used by that slot** when the approved predictive-error condition occurs. Retired means unavailable for future image writes. It does not mean erase now, delete the photo, refuse future host reads or move it to another slot. If a physical erase block is shared, protect every retained photo in it and exclude that block from new allocation.

Keep permanent retirement separate from USED/DONE state and explicit photo deletion. Before deletion, the existing image already occupies its slot. After deletion, a retired slot remains unusable; a healthy deleted slot may be reclaimed safely. Reduced capacity and eventual full behavior must include all retirements.

Persist retirement/deletion metadata safely in healthy management storage; these metadata writes are permitted and are distinct from moving or rewriting image data. Preserve factory markers and obey exact-part spare-area/ECC/partial-program restrictions; do not casually overwrite markers in live image pages. If allocation/retirement metadata cannot be trusted, prevent unsafe new allocations under F-10.

The USB copy-out proposal is **rejected/superseded**, not awaiting approval. There is no relocation destination, replacement image copy, automatic image refresh or read-triggered source erase. Later host reads always retry the original stored image; they can be better, worse or equally readable. Exact hardware remains unqualified, so future success of an already marginal record is not promised.

## Evidence checked October 14

- [Alliance AS5F Rev.3.1, October 2024](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.1_O.pdf), p42, describes clean, corrected, uncorrectable and maximum-correction ECC states for the family containing **AS5F14G04SND-10LIN**. ECC status updates after completion and is cleared when ECC is disabled. The newer C variant is a distinct device; do not apply its layout blindly.
- [Micron MT29F4G01ABBFD Rev F](../../datasheets/memory/Micron_MT29F4G01ABBFD_1v8_SPI_NAND_RevF.pdf), pp45–47, requires refresh for its 7–8-bit corrected status and permits it at 4–6 bits. [Winbond W25N04KW Rev C](../../datasheets/memory/W25N04KW_datasheet_RevC.pdf), PDF pp20–23, requires refresh/removal above its threshold and describes the buffered-read/ECC mode requirements. These are candidate-specific constraints; they do not select either device or a shared numeric threshold.
- [USBX PIMA header](https://raw.githubusercontent.com/eclipse-threadx/usbx/master/common/usbx_device_classes/inc/ux_device_class_pima.h) defines the PTP response constants. [Microsoft's portable-device error reference](https://learn.microsoft.com/en-us/windows/win32/wpd_sdk/error-constants) describes the shared `0x2007` transfer-error meaning in its MTP table. [USBX GetObject implementation](https://raw.githubusercontent.com/eclipse-threadx/usbx/master/common/usbx_device_classes/src/ux_device_class_pima_object_data_get.c) supplies the stack behavior above. Source was inspected on this date; the exact firmware release still needs pinning and testing.
- [Adobe's EXIF namespace reference](https://github.com/adobe/xmp-docs/blob/master/XMPNamespaces/exif.md) identifies UserComment as EXIF tag 37510/0x9286. It establishes an available comment field, not universal host warning behavior.
- [USBX GetObjectInfo implementation](https://raw.githubusercontent.com/eclipse-threadx/usbx/master/common/usbx_device_classes/src/ux_device_class_pima_object_info_get.c) sends the filename in object metadata separately from GetObject. The host-caching consequence above is an integration concern to test, not a claim about every host.

## Boundaries

Ten-year room-temperature retention without power/refresh through 1,000 complete reuse cycles remains the storage qualification requirement. Best-effort rescue after detected errors does not satisfy that guarantee. The Micron/Winbond candidate requirements cited above call for refresh/removal at specified marginal conditions; the approved no-relocation policy does not perform that maintenance or restore original media reliability. Account for this in exact-part qualification without silently adding maintenance.

Memory sizing, predictive-error thresholds, permanent retirement metadata, reserve/capacity loss, same-request filename behavior and storage-control redundancy remain to engineer. Photo-object duplication is excluded by D-31. Payload reads occur only on host image requests during USB retrieval; existing capture verification and metadata reads are separate. No hardware or firmware compliance is claimed.
