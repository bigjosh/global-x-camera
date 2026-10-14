# ECC and read-error handling

October 14, 2026. **Recommendation for discussion; the detailed policy below is not yet approved.** PTP with explicit per-photo deletion is accepted in [D-25](2026-10-13-project-baseline.md). Existing requirements already include device-appropriate ECC, stored integrity metadata/checksums, mandatory final commit verification, and reporting unreadable existing photos over USB. This review proposes how to implement and distinguish read outcomes.

## Discussion order

1. **Current:** ECC, checksum verification and the response to each read result.
2. USB-powered repair/relocation of marginal data, including no-spare-space and interrupted-repair behavior.
3. Any additional image redundancy and detailed metadata protection/diagnostics.

## Recommended read policy

Use the selected NAND's required ECC, preferably its on-die engine for the serial-NAND candidates, and inspect the result of **every completed page read**. Mode bits, protected byte ranges, status encoding and thresholds must follow the exact part/revision. An SPI transaction completing successfully does not prove the stored data is correct.

Generate and store a checksum when capturing/saving the original image; **CRC-32C is the proposed algorithm**, not yet selected. Protect the image identity, length and essential stored metadata too. On USB retrieval, apply ECC and compare the reconstructed image with its stored checksum. ECC corrects errors within its capability; the checksum detects remaining corruption and assembly/addressing mistakes with its finite detection strength. Neither is proof that every possible corruption is detectable. Do not generate a replacement checksum from suspect read data and treat that as validation.

| Read outcome | Proposed response |
|---|---|
| No ECC errors and checksum matches | Return the photo normally. |
| ECC corrects errors and checksum matches | Return the corrected photo successfully; record available health status. Correction alone is not a failed download. |
| Correctable but at/above the device's marginal threshold | Return the verified photo; flag the block/photo for device-required repair/relocation handling. Do not silently ignore the threshold. The next discussion settles safe maintenance, spare-space handling and interruption recovery. |
| Uncorrectable ECC, checksum mismatch or invalid required record metadata | Permit bounded re-reading and only device-documented recovery; never loop indefinitely or invent a vendor retry mode. If still invalid, fail that image's PTP request, retain the stored record and leave unaffected photos accessible. Retry count is not fixed here. |
| Transfer interruption or host cancellation | Do not report a completed image or delete it merely because some/all bytes were sent. Use the protocol's applicable transfer-error/cancellation flow. |

A read failure does not authorize photo deletion, marking its space free, or destructive recovery. User-requested per-photo deletion remains a separate accepted operation. Existing F-10 rules govern allocation/catalog corruption that cannot be safely localized. Missing optional time/orientation metadata retains the accepted BAD/omit-EXIF behavior and is not an image-integrity failure by itself.

For this approximately 1.916 MB RAW10 image, prefer reading into a complete RAM buffer, checking ECC and the stored checksum, then transmitting from that verified buffer **if the final firmware memory budget permits**. This avoids knowingly beginning a download of corrupt data. An alternative streaming implementation must fail correctly if corruption is discovered late; it must never send final success for a checksum-failing image. Buffer allocation, export-container expansion and host timeouts need qualification. USB-time validation is separate from configurable post-write payload readback during battery-powered capture.

## PTP error reporting

**PTP can report failure of an image operation.** Standard response codes include `GeneralError` (`0x2002`) and `IncompleteTransfer` (`0x2007`); select the response/abort sequence valid for the operation and phase. The latter means an incomplete transfer whose received data should be discarded. A host may display only a generic import/transfer failure; there is no assumed standard dialog exposing the NAND page, ECC status or checksum detail. Any detailed health log or diagnostic extension is a separate interface decision.

A stack implementation needs verification, not just a list of error constants. The inspected USBX PIMA `GetObject` path sends final OK only on success and **stalls Bulk IN on error**; returning an error from the data callback does not by itself establish a clean on-wire `GeneralError`/`IncompleteTransfer` response. Test or adapt the selected stack so it reports failures, terminates partial transfers and permits subsequent valid requests without false success. Test real host behavior; camera firmware cannot guarantee that an application removes every partial local file.

## Evidence checked October 14

- [Alliance AS5F Rev.3.1, October 2024](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.1_O.pdf), p42, describes clean, corrected, uncorrectable and maximum-correction ECC states for the family containing **AS5F14G04SND-10LIN**. ECC status updates after completion and is cleared when ECC is disabled. The newer C variant is a distinct device; do not apply its layout blindly.
- [Micron MT29F4G01ABBFD Rev F](../../datasheets/memory/Micron_MT29F4G01ABBFD_1v8_SPI_NAND_RevF.pdf), pp45–47, requires refresh for its 7–8-bit corrected status and permits it at 4–6 bits. [Winbond W25N04KW Rev C](../../datasheets/memory/W25N04KW_datasheet_RevC.pdf), PDF pp20–23, requires refresh/removal above its threshold and describes the buffered-read/ECC mode requirements. These are candidate-specific constraints; they do not select either device or a shared numeric threshold.
- [USBX PIMA header](https://raw.githubusercontent.com/eclipse-threadx/usbx/master/common/usbx_device_classes/inc/ux_device_class_pima.h) defines the PTP response constants. [Microsoft's portable-device error reference](https://learn.microsoft.com/en-us/windows/win32/wpd_sdk/error-constants) describes the shared `0x2007` transfer-error meaning in its MTP table. [USBX GetObject implementation](https://raw.githubusercontent.com/eclipse-threadx/usbx/master/common/usbx_device_classes/src/ux_device_class_pima_object_data_get.c) supplies the stack behavior above. Source was inspected on this date; the exact firmware release still needs pinning and testing.

## Boundaries

Ten-year room-temperature retention without power or refresh must hold through 1,000 complete reuse cycles. Responding to a marginal read while already USB-powered must not become a requirement for periodic connections during that unpowered interval. Do not equate a recoverable bit correction with a dead block; follow the exact device's health and retirement rules. Physical marker placement, protected metadata, bad-block handling, maintenance policy and additional redundancy remain to engineer. No automatic repair/erase or new redundancy scheme is approved by this recommendation.
