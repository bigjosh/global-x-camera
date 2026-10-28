"""Narrow Windows WinUSB pipe recovery; no device reset or target access.

Default is an inert proposal. --execute is required to open the debugger interface.
No other USB interface, hub, GPIO, target memory, or firmware is accessed.
Microsoft APIs are synchronous here; a supervisor bounds the worker lifetime.
Successful pipe reset is NOT proof of ST-LINK responsiveness or power cycling.
See stlink-recovery.md for measured evidence, constraints, and Microsoft sources.
"""
from __future__ import annotations

import argparse
import ctypes as c
from ctypes import wintypes as w
import datetime
import json
from pathlib import Path
import subprocess
import sys

PARENT = r"USB\VID_0483&PID_3754\002100203335511035383531"
INSTANCE = r"USB\VID_0483&PID_3754&MI_00\7&26744555&0&0000"
INTERFACE = r"\\?\USB#VID_0483&PID_3754&MI_00#7&26744555&0&0000#{dee824ef-729b-4a0e-9c14-b7117d33a817}"
EXPECTED_ENDPOINTS = {0x01, 0x81, 0x82}


def emit(event: str, **fields):
    print(json.dumps({"time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "event": event, **fields}), flush=True)


def validate_identity():
    # All identifiers are fixed constants observed on this host, not user interpolation.
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$taskId='{INSTANCE}'; "
        "$taskParent=(Get-PnpDeviceProperty -InstanceId $taskId -KeyName DEVPKEY_Device_Parent).Data; "
        "$taskService=(Get-PnpDeviceProperty -InstanceId $taskId -KeyName DEVPKEY_Device_Service).Data; "
        "$taskClients=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^STM32_Programmer_CLI|^ST-LINK_gdbserver|^openocd|^STLinkServer' } | Select-Object Name,ProcessId); "
        "@{parent=$taskParent;service=$taskService;clients=$taskClients}|ConvertTo-Json -Compress -Depth 4"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, timeout=5, check=True)
    identity = json.loads(result.stdout)
    emit("identity", **identity)
    if identity["parent"].upper() != PARENT.upper() or identity["service"].upper() != "WINUSB":
        raise RuntimeError("Device parent serial or driver does not match this bench ST-LINK")
    if identity["clients"]:
        raise RuntimeError("A known ST-LINK client is running; no recovery attempted")


class InterfaceDescriptor(c.Structure):
    _pack_ = 1
    _fields_ = [(name, w.BYTE) for name in (
        "bLength", "bDescriptorType", "bInterfaceNumber", "bAlternateSetting",
        "bNumEndpoints", "bInterfaceClass", "bInterfaceSubClass", "bInterfaceProtocol", "iInterface")]


class PipeInfo(c.Structure):
    _fields_ = [("PipeType", c.c_int), ("PipeId", w.BYTE),
                ("MaximumPacketSize", w.USHORT), ("Interval", w.BYTE)]


def run_worker():
    validate_identity()
    kernel = c.WinDLL("kernel32", use_last_error=True)
    winusb = c.WinDLL("winusb", use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    winusb.WinUsb_Initialize.argtypes = [w.HANDLE, c.POINTER(c.c_void_p)]
    winusb.WinUsb_Initialize.restype = w.BOOL
    winusb.WinUsb_QueryInterfaceSettings.argtypes = [c.c_void_p, w.BYTE, c.POINTER(InterfaceDescriptor)]
    winusb.WinUsb_QueryInterfaceSettings.restype = w.BOOL
    winusb.WinUsb_QueryPipe.argtypes = [c.c_void_p, w.BYTE, w.BYTE, c.POINTER(PipeInfo)]
    winusb.WinUsb_QueryPipe.restype = w.BOOL
    for name in ("WinUsb_AbortPipe", "WinUsb_ResetPipe"):
        getattr(winusb, name).argtypes = [c.c_void_p, w.BYTE]
        getattr(winusb, name).restype = w.BOOL
    winusb.WinUsb_Free.argtypes = [c.c_void_p]
    winusb.WinUsb_Free.restype = w.BOOL

    def check(value, name):
        if not value:
            error = c.get_last_error()
            emit("api_failure", api=name, winerror=error, message=c.FormatError(error))
            raise c.WinError(error)

    handle = None
    usb = c.c_void_p()
    try:
        emit("opening_interface", path=INTERFACE)
        # No sharing: fail rather than interfere with another user's debugger client.
        handle = kernel.CreateFileW(INTERFACE, 0xC0000000, 0, None, 3, 0x40000000, None)
        if handle == c.c_void_p(-1).value:
            handle = None
            check(False, "CreateFileW")
        check(winusb.WinUsb_Initialize(handle, c.byref(usb)), "WinUsb_Initialize")
        descriptor = InterfaceDescriptor()
        check(winusb.WinUsb_QueryInterfaceSettings(usb, 0, c.byref(descriptor)), "WinUsb_QueryInterfaceSettings")
        emit("interface_descriptor", **{name: getattr(descriptor, name) for name, _ in descriptor._fields_})
        if descriptor.bInterfaceNumber != 0 or descriptor.bAlternateSetting != 0 or descriptor.bInterfaceClass != 0xFF:
            raise RuntimeError("Unexpected interface descriptor; refusing pipe changes")
        pipes = []
        for index in range(descriptor.bNumEndpoints):
            info = PipeInfo()
            check(winusb.WinUsb_QueryPipe(usb, 0, index, c.byref(info)), "WinUsb_QueryPipe")
            pipes.append((info.PipeId, info.PipeType))
            emit("pipe", index=index, pipe_id=f"0x{info.PipeId:02x}", pipe_type=info.PipeType,
                 max_packet_size=info.MaximumPacketSize, interval=info.Interval)
        if len(pipes) != 3 or {pipe for pipe, _ in pipes} != EXPECTED_ENDPOINTS or any(kind != 2 for _, kind in pipes):
            raise RuntimeError("Unexpected endpoint set; refusing pipe changes")
        for api in ("WinUsb_AbortPipe", "WinUsb_ResetPipe"):
            for pipe_id, _ in pipes:
                emit("api_start", api=api, pipe_id=f"0x{pipe_id:02x}")
                check(getattr(winusb, api)(usb, pipe_id), api)
                emit("api_success", api=api, pipe_id=f"0x{pipe_id:02x}")
        emit("pipe_recovery_complete", stlink_responsive="unverified", vbus_power_cycle=False)
        return 0
    finally:
        if usb.value:
            emit("free_interface", success=bool(winusb.WinUsb_Free(usb)))
        if handle is not None:
            emit("close_handle", success=bool(kernel.CloseHandle(handle)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if not 5 <= args.timeout <= 30:
        parser.error("timeout must be 5..30 seconds")
    if not args.execute:
        emit("proposal_only", parent=PARENT, interface=INTERFACE,
             operations=["verify parent serial and WinUSB driver", "refuse known active ST-LINK clients",
                         "exclusive overlapped open of MI_00", "query and validate MI_00 bulk endpoints",
                         "abort bulk transfers", "reset bulk pipes", "close interface"],
             warning="Does not reset ST-LINK firmware, USB device, target, or VBUS")
        return 0
    if args.worker:
        try:
            return run_worker()
        except Exception as exc:
            emit("failed", error=repr(exc))
            return 1
    worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--execute", "--worker"])
    try:
        code = worker.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        emit("worker_timeout", timeout_seconds=args.timeout, action="terminate this recovery worker only")
        worker.kill()
        try:
            worker.wait(timeout=2)
        except subprocess.TimeoutExpired:
            emit("worker_termination_unconfirmed", pid=worker.pid)
        return 124
    return code


if __name__ == "__main__":
    raise SystemExit(main())
