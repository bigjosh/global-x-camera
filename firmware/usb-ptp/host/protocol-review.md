# PTP host compatibility requirements

## Baseline operation set

Microsoft's published PTP minidriver minimum is `GetDeviceInfo` (0x1001),
`OpenSession`/`CloseSession` (0x1002/3), `GetStorageIDs`/`GetStorageInfo`
(0x1004/5), `GetObjectHandles`/`GetObjectInfo`/`GetObject` (0x1007/8/9), and
`GetThumb` (0x100A). It states that driver does not use `GetNumObjects`.
These are legacy WIA requirements, useful baseline guidance rather than a
complete prediction of current Explorer/Photos traffic.
[Microsoft required commands](https://learn.microsoft.com/en-us/windows-hardware/drivers/image/ptp-required-commands).

Project additions are `DeleteObject` (0x100B) for explicit per-photo deletion
and preferably `GetNumObjects` (0x1006). `GetPartialObject` (0x101B) can support
host range access, but must preserve snapshot/size semantics. Advertise only
implemented operations and events. Remote capture, upload, and FormatStore are
not part of the approved USB user flow. An unsupported request must produce a
bounded valid response, not hang the next transaction.

## USB transport boundaries

Use Still Image interface class/subclass/protocol `06/01/01`, bulk OUT, bulk IN,
and interrupt IN. Containers use little-endian length/type/code/transaction
fields; phases remain distinct. A data-container length exactly divisible by
the bulk maximum packet size needs a terminating ZLP before its response.

Required control requests include Cancel (`0x64`, host-to-interface `0x21`, six
data bytes: `uint16 0x4001`, transaction `uint32`), Device Reset (`0x66`, `0x21`,
no data), and Get Device Status (`0x67`, `0xA1`). Status starts with `uint16`
total length and response code: OK `0x2001`, busy `0x2019`, or cancelled `0x201F`.
The 2007 errata changes `wIndex` to the interface number. Cancel clears active
transaction buffers before status becomes OK. Device Reset also closes open
sessions. Reconnect must discard stale transaction state.
[USB-IF SIC 1.0 and errata](https://www.usb.org/document-library/still-image-capture-device-definition-10-and-errata-16-mar-2007),
sections 5.2, 6.1, 7.1 and annex B. Local reference extraction is under
`tmp/bringup/usb-ptp-20261108/references/usb-still-image/`.

Microsoft's documented recovery first tries Get Device Status, clears stalled
endpoints when successful, then tries class Device Reset if status fails.
Malformed initial DeviceInfo/ObjectInfo can prevent driver initialization.
Implement and test these control paths, not only successful downloads.
[Microsoft error recovery](https://learn.microsoft.com/en-us/windows-hardware/drivers/image/ptp-error-recovery).

## Images and thumbnails

The installed SDK maps PNG to PTP `0x380B` and BMP to `0x3804` in
`PortableDevice.h`. Windows WIC has a native PNG codec and 16-bit grayscale
pixel format. The native client independently decoded the photo backend's
3,064,188-byte PNG fixture, including its eXIf chunk, with all low six sample
bits zero. Explorer/Photos importing and thumbnail handling remain separate
hardware acceptance tests.
[WIC PNG codec](https://learn.microsoft.com/en-us/windows/win32/wic/png-format-overview),
[native pixel formats](https://learn.microsoft.com/en-us/windows/win32/wic/-wic-codec-native-pixel-formats).

Until a thumbnail path is qualified, report zero thumbnail fields and answer
GetThumb truthfully with NoThumbnailPresent (`0x2010`). The optional
[`thumbnail_bmp` helper](../thumbnail/README.md) provides a deterministic BMP
candidate; local WIC decode does not establish that the WPD PTP driver accepts
that thumbnail format. A JPEG-only requirement was not established from the
primary documents reviewed, so neither BMP interoperability nor a JPEG mandate
is claimed here.

Windows may query properties before downloading, cache names, or request
objects in a different order. The firmware must keep advertised length stable
for its representation and keep saved-photo identity distinct from a reusable
storage location. WPD warnings can be hidden by applications; `_RECOVERED` and
PNG metadata remain useful on the actual exported photo. Do not fabricate
capture dates to populate a listing.
