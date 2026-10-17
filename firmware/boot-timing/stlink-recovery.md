# ST-LINK recovery without unplugging USB

On October 17, 2026 at 05:14:42 UTC, clearing only the ST-LINK debugger's WinUSB pipes recovered the bench from `DEV_USB_COMM_ERR`. A subsequent CubeProgrammer hot-plug connection on AP1 reported firmware V3J15M6, read the MCU registers, and found PC `0x34180874` in the existing diagnostic's loop. No USB port restart, administrator privilege, cable action, target power cycle, flash operation, or target reset was used by the recovery helper. The separate verification command halted the core to inspect it; that is not part of pipe recovery.

This demonstrates recovery from this particular failure, not every possible debugger hang. All pipe calls succeeding is insufficient evidence by itself: verify a bounded programmer connection/read afterward. The preceding CN10 USB reconnect had not resolved the error. The failing external flash-loader initialization remains a separate problem and should not be repeatedly retried just because the transport can now be recovered.

Evidence: [pipe recovery log](evidence/stlink-recovery-20261017/pipe-recovery.jsonl), [subsequent programmer read](evidence/stlink-recovery-20261017/programmer-read.log).

## Guarded recovery helper

`python firmware/boot-timing/stlink_recover.py` prints the planned operations without opening any device. Add `--execute` to run them, optionally `--timeout 15` (allowed range 5–30 seconds).

The helper is deliberately specific to this bench:

- Parent device serial `002100203335511035383531`, USB VID/PID `0483:3754`.
- Only debugger interface MI_00, with Windows instance `USB\VID_0483&PID_3754&MI_00\7&26744555&0&0000` and WinUSB service.
- Exclusive overlapped open; refuses known active CubeProgrammer, ST-LINK GDB server, OpenOCD or STLinkServer processes. Other chats must still coordinate bench ownership before running it.
- Validates interface 0 and exactly three bulk endpoints: `0x81`, `0x01`, `0x82`.
- Aborts pending transfers on those pipes, then resets their stall/data-toggle state, frees the WinUSB handle and closes the file handle. COM8 and other USB devices are not opened.
- A separate worker process bounds the synchronous recovery calls; on timeout, only that worker is terminated. A termination request is not claimed as a completed USB reset, and any uncertain cleanup is reported.

Moving the cable to a different port can change the Windows child instance/interface path. The helper then fails its exact identity check; re-inventory the device and deliberately update the fixed identifiers instead of broadening matching to every ST-LINK or USB device. Do not run recovery while a programmer operation is still active. Never kill another chat's instrument or debugger session to satisfy this precondition.

The helper sends no debugger protocol commands and never touches target memory, boot settings, flash, OTP, or power controls. `WinUsb_Initialize` initializes this handle's interface policy state; no driver replacement or global Windows setting is needed. Microsoft's [initialization documentation](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_initialize) requires an overlapped file handle. [AbortPipe](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_abortpipe) cancels pending pipe transfers, and [ResetPipe](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_resetpipe) clears the stall/data-toggle state. Neither is a debugger firmware power cycle.

## Why unplugging CN10 may not restart the debugger

The stock-board schematic has two diode-fed inputs to the debugger's U10 regulator: CN10 USB through D1, and the target's global 5 V rail through D2. With the target powered from CN8 through JS110, D2 can keep the debugger powered while CN10 is unplugged. Removing all CN9 jumpers does not break this D2 path. The [debugger isolation investigation](../../docs/power/nucleo-debug-isolation.md#supply-path-and-proposed-separation) records the schematic sources and the remaining delivered-board verification limits. This is a circuit explanation, not a measurement of debugger VDD during the failed reconnect.

Windows recorded ST-LINK arrival at 01:08:44 local time (05:08:44 UTC) on October 17; that confirms enumeration, not loss of its supply. The port remained connected at USB high speed and exposed debugger MI_00 and COM8 MI_01, with no mass-storage function.

## Other recovery routes and limits

The current process is not elevated. Windows provides `pnputil /restart-device` and an administrator-only hub-port cycle IOCTL, but neither was used. Targeting the exact composite ST-LINK node would also affect its COM port. The [Microsoft cycle-port recovery description](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/how-to-recover-from-usb-pipe-errors) describes a software disconnect and re-enumeration without electrical disconnection; do not claim that such a call removes VBUS. See [PnPUtil](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/pnputil-command-syntax) and [hub-cycle requirements](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbioctl/ni-usbioctl-ioctl_usb_hub_cycle_port). The [libusb Windows limitations](https://github.com/libusb/libusb/wiki/Windows#known-restrictions) likewise distinguish WinUSB from a true USB device reset.

Read-only hub queries identified ST-LINK on port 1 of a Genesys `05E3:0610` hub, sharing that hub with JS110 and an RP2040 serial device. Its descriptor reports four ports and `wHubCharacteristics=0x00E0`, which indicates ganged rather than independent power switching. **Do not reset or power-cycle the whole hub:** it would disturb the measurement instrument and other hardware. Descriptor claims alone are not a verified physical power-switching capability.

If pipe recovery fails, further USB re-enumeration or hardware reset requires a separately tested recovery method. No fully autonomous electrical debugger power cycle is established by this result.
