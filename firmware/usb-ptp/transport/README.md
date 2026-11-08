# USB Still Image transport

The transport uses STM32N6 HAL PCD with the integrated USB1 high-speed PHY,
the pinned ST USB Device Chapter9 core, and a small Still Image class. It does
not implement PTP object/storage operations; those belong to the application.
The USBX PIMA class in the local camera SDK returns
`UX_FUNCTION_NOT_SUPPORTED` in standalone mode, so reusing it would require
adding an RTOS.

`build_sources.py` exports `sources()`, `includes()` and `defines()` for the
application build. Existing platform dependencies include HAL PWR/PWR_EX,
RCC/RCC_EX, CORTEX and RIF. HAL tick must advance during startup timeouts.
The SDK/Arm compiler paths follow the repository's existing builders. The
optional CLI compiles three profiles offline without touching hardware.

```text
python firmware/usb-ptp/transport/build_sources.py --out tmp/transport-build
python -m unittest discover -s firmware/usb-ptp/transport -p "test_*.py"
```

## Application contract

Include `usb_ptp_transport.h`. Install IRQ177 in the secure vector table as
`USB1_OTG_HS_IRQHandler`; default priority is6. Alternatively compile
`USB_PTP_USE_IRQ=0` and call `usb_ptp_transport_poll()` regularly. The initial
speed is high-speed, with full-speed host fallback. `USB_PTP_FORCE_FS=1`
provides an isolation test. DMA is disabled, so USB FIFO servicing has no
data-cache ownership issue. All USB callbacks must do bounded flag/buffer work.

`usb_ptp_transmit(pointer,length,end_transfer)` retains the pointer until the
completion callback or `usb_ptp_tx_busy()==0`. It accepts up to65535bytes;
each intermediate chunk must be an exact multiple of the negotiated maximum
packet (512HS/64FS). The final chunk adds a zero-length packet when required.
This separates an exact-packet-length PTP data container from the subsequent
response container. Allocate each source buffer through the next32-bit word
because the HAL loads FIFO data in words, including a partial final word.

The receive callback presents one packet. Its internal buffer is stable until
the application calls `usb_ptp_receive_enable()`; the endpoint NAKs meanwhile.
The event sender copies up to24bytes to a private interrupt-IN buffer. Reset,
cancel and device-reset callbacks signal application work; they never touch SD.
`usb_ptp_cancel_transfer()` stops and flushes only the pending bulk-IN transfer,
preserving USB data toggles and the pending OUT packet. After success the
application returns to idle and rearms receive; host-initiated cancellation
completes through GetDeviceStatus, with no canceled-transaction bulk response.
`usb_ptp_abort_bulk()` is a convenience wrapper that also rearms receive.
Only bus reset, configuration and host ClearFeature reset the appropriate PID.

The class accepts interface-recipient CancelRequest0x64, DeviceReset0x66 and
GetDeviceStatus0x67, validates their fields, and exposes PTP status via callback.
Cancel's six-byte dataset must contain0x4001 followed by transactionID.
Unsupported requests stall EP0. No capture, delete-all or filesystem access is
introduced by this transport.

## Board initialization and debug

This follows local ST camera demo `Src/main.c:392` and
`Lib/uvcl/Src/uvcl.c:254`: USB1 secure/privileged, VDD33USB monitor and valid
supply, HSE48MHz divided by2, PHY FSEL24MHz, embedded HS PHY and VBUS sensing
disabled. Only HSE enable and USB clock muxes change; system PLLs, SD and GPIO
configuration remain the application's responsibility. The application must
only connect this device stack when a host is intended; VBUS auto-detection is
not supplied by this module. No ULPI or Arduino GPIO connection is required.

U42 is the removed unused alternative camera LD1117 regulator, not the USB
PHY supply. Its removal does not prevent CN8 USB. CN8's power/protection paths
can bypass the Joulescope even with CN9 open, so USB connection is a new power
configuration; use the current bench checkpoint, not old power traces.

`usb_ptp_debug` records initialization stage/error, requests, resets,
configuration, packet counts, negotiated speed and register snapshots.
Stages1..6 are security/supply, HSE, PHY, PCD, core, connected. Errors1..5
are USB supply timeout, HSE timeout, PCD initialization, USB core registration,
and USB start failure. Stage loops use the existing HAL millisecond tick.

Current configurable identity0483:572A is a local ST-board development
identity, not a Global-X production VID/PID allocation. Replace it before
distribution. The serial is stable for this one prototype. Descriptors advertise
one interface6/1/1, bulkIN0x81/bulkOUT0x01 and interruptIN0x82, self-powered
with a500mA maximum for the supported USB-powered configuration.

The official upstream core is vendored unchanged at the commit and per-file
hashes in `vendor/st-usbd/UPSTREAM.json`, with its complete license retained.
No USB host enumeration or hardware behavior is implied by offline compilation.
