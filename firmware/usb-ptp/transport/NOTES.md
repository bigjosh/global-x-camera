# Transport decisions

## 2026-11-08  Keep bare-metal PTP above ST's USB Device core and N6 HAL PCD

**Why:** the working camera smoke demo already establishes the Nucleo's
integrated USB1 PHY preparation. The bundled USBX PIMA initializer explicitly
rejects `UX_DEVICE_STANDALONE`; its working path creates RTOS threads. A small
Still Image endpoint class over the standard ST Chapter9 core fits the current
bare-metal camera and avoids adding a scheduler merely to export stored photos.
The core was absent from the local SDK, although the UVC adapter supports it;
only its three source files, four headers and license are vendored and pinned.

**Rejected:** assuming standalone UVC implies standalone PIMA, adding ThreadX
to the capture path, rewriting standard USB enumeration from scratch, and
enabling USB DMA before basic transfers are qualified. Transport callbacks
only signal application work; SD reads/deletes and PNG conversion stay outside
interrupt context. Intermediate chunks cannot terminate a PTP transfer, and
the final exact-packet chunk explicitly sends a zero-length packet before its
response container.

**Evidence:** `usb_ptp_transport.c`, `build_sources.py`, the upstream commit
and hashes in `vendor/st-usbd/UPSTREAM.json`, and local ST example
`tmp/bringup/x-cube-n6-camera-capture/Src/main.c:392` plus
`Lib/uvcl/Src/uvcl.c:254`. Three Arm compilation profiles (IRQ, polling and
forced full-speed) passed with warnings as errors; hardware qualification
belongs to the parent USB campaign. U42 is unrelated to USB, as recorded in
`docs/power/power-cost-comparison.md`; CN8 bypass power paths remain described
in `docs/power/nucleo-debug-isolation.md`.

## 2026-11-08  Cancel a transfer without reopening endpoints or resetting DATA PID

**Why:** the first live host-cancel test reached the cancellation callback, but
subsequent downloads stalled. ST's `USB_ActivateEndpoint` writes DATA0 after an
endpoint was closed; the host did not request a matching pipe reset. Stop and
flush pending bulk IN through `HAL_PCD_EP_Abort`/`USB_FlushTxFifo`, disable old
FIFO refill, clear stale endpoint interrupts and retain endpoint activation and
both data toggles. The current protocol has no host-to-device data operation,
so pending packet-sized OUT and the shared RX FIFO stay intact.

**Rejected:** close/open as a cancellation primitive, flushing the shared RX
FIFO while EP0 is servicing status, and a bulk TransactionCancelled response
for host cancellation. Host cancellation completes through control status:
Busy during cleanup, OK when idle, preserving the PTP session. A device-origin
failure and host ClearFeature have separate protocol semantics.

**Evidence:** [USB Still Image specification, section7.2.1.1 and Figure7.2-1](https://www.pjrc.com/tmp/usb_still_img10.pdf),
local ST `stm32n6xx_ll_usb.c` functions `USB_ActivateEndpoint` and
`USB_EPStopXfer`; nine native class/core tests and all three Arm compilation
profiles in `tmp/bringup/usb-ptp-20261108/transport-cancel-compile/`.
The parent USB campaign owns live qualification; offline tests alone do not
prove endpoint timing on the board.

## 2026-11-08  Preserve the exact vendored USB core bytes through Git checkout

**Why:** UPSTREAM.json binds each ST source/header/license to an upstream
SHA256. Windows automatic line-ending conversion can otherwise make a fresh
checkout fail that identity check even when the C program is equivalent.
The vendor folder now disables text normalization, as the frozen evidence does.

**Rejected:** rewriting upstream hashes for local line endings, modifying the
vendor's whitespace/license text to satisfy a generic diff check, or changing
the repository-wide Windows Git configuration.

**Evidence:** `vendor/st-usbd/.gitattributes`, `UPSTREAM.json`, staged-blob hash
verification during the USB release commit, and `test_vendor_files_unchanged`.
