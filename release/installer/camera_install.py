#!/usr/bin/env python3
"""Guided, no-jumper installer for the pinned r2 camera firmware.

Default execution is interactive. --check is entirely offline. Target access
starts only after the cabling/idle acknowledgement. No power-switch API,
standard external loader, OTP change, SD command, or automatic write retry.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
TAG = "knobs-2026-11-14-r2"
TARGET_HASHES = (
    "6ddf4499865264aec845150597aa6b8d44cb89e7d5e621dd324a0e1a9170b499",
    "206da4c0a8bdcda6205d7ccdb3d9ac02548e9db6852b1fa47afa6327b76473d8",
)
HELPER_HASHES = {
    "reader/read.bin": "d6b63e6e993a9cb872cfe482c0fd4f8954f8edc398a7dfb1db25982b9e255b5d",
    "writer0/programmer.bin": "e69f0d0c3c49c2bad1ad5e7e8ff5907fcf3b251cb5b968629c18a9c57247f307",
    "writer1/programmer.bin": "5dcf3be40ef56443d0f9ecf011cb1f7acf4745ec449042cf0d9fe262be74949e",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".new")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_assets(assets=ASSETS):
    """Pin executable bytes independently of user-editable build manifests."""
    images = []
    for index, digest in enumerate(TARGET_HASHES):
        data = (assets / "firmware" / f"sector{index}.bin").read_bytes()
        if len(data) != 65536 or sha(data) != digest:
            raise ValueError(f"Firmware sector {index} is missing or differs from r2.")
        images.append(data)
    for name, digest in HELPER_HASHES.items():
        if sha((assets / "helpers" / name).read_bytes()) != digest:
            raise ValueError(f"Flash helper differs from the reviewed copy: {name}")
    from camera_recovery import load_profiles
    from camera_nor import validate_helpers
    load_profiles(assets / "profiles")
    validate_helpers(assets / "helpers")
    return images


def find_cube(explicit=None):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if path.is_dir():
            matches = [path / suffix for suffix in (
                "Contents/Resources/bin/STM32_Programmer_CLI",
                "Contents/MacOs/bin/STM32_Programmer_CLI",
                "bin/STM32_Programmer_CLI", "bin/STM32_Programmer_CLI.exe",
            ) if (path / suffix).is_file()]
            if len(matches) == 1:
                return matches[0]
        if not path.is_file():
            raise ValueError(f"STM32CubeProgrammer executable not found: {path}")
        return path
    names = ["STM32_Programmer_CLI", "STM32_Programmer_CLI.exe"]
    candidates = [Path(p).resolve() for n in names if (p := shutil.which(n))]
    # No drive-wide searches. These are ST's standard/application locations.
    roots = [Path.home() / "Applications", Path("/Applications")]
    if sys.platform == "win32":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(env):
                roots.append(Path(os.environ[env]) / "STMicroelectronics")
    for root in roots:
        if not root.exists():
            continue
        for suffix in (
            "STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI",
            "STM32CubeProgrammer.app/Contents/MacOs/bin/STM32_Programmer_CLI",
            "STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI",
            "STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/MacOs/bin/STM32_Programmer_CLI",
            "STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe",
        ):
            path = root / suffix
            if path.is_file():
                candidates.append(path.resolve())
    candidates = sorted(set(candidates))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError("Install STM32CubeProgrammer 2.23.0, then run again. "
                         "If installed elsewhere, use --cubeprogrammer with its CLI path. "
                         "Download: https://www.st.com/en/development-tools/stm32cubeprog.html")
    raise ValueError("More than one CubeProgrammer installation found. Select one with "
                     "--cubeprogrammer:\n" + "\n".join(map(str, candidates)))


class Console:
    def __init__(self):
        self.stage = 0
        self.last_pages = None

    def progress(self, percent, message):
        self.stage = percent
        print(f"{percent:3d}%  {message}", flush=True)

    def event(self, name, fields):
        if name == "nor_progress" and fields.get("pages_programmed"):
            pages = fields["pages_programmed"]
            key = (fields.get("sequence"), pages)
            if key != self.last_pages:
                print(f"      Flash write: {pages} pages programmed.", flush=True)
                self.last_pages = key


class Transport:
    def __init__(self, cli, serial_number, output, console=None):
        self.cli = Path(cli)
        self.serial = serial_number
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.console = console
        self.calls = 0
        self.uploads = 0
        self.halt_requests = 0
        self.default_timeout = 20

    def log(self, event, **fields):
        with (self.output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(utc=utc(), event=event, **fields), default=str) + "\n")
        if self.console:
            self.console.event(event, fields)

    def call(self, *args, success=None, timeout=None):
        self.calls += 1
        if "-halt" in args:
            self.halt_requests += 1
        argv = [str(self.cli), "-c", "port=SWD", "mode=HOTPLUG", "ap=1",
                "freq=1000", "sn=" + self.serial, *map(str, args)]
        self.log("cube_call", number=self.calls, argv=argv)
        kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      timeout=self.default_timeout if timeout is None else timeout)
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        path = self.output / f"cli-{self.calls:04d}.log"
        try:
            result = subprocess.run(argv, **kwargs)
        except subprocess.TimeoutExpired as exc:
            path.write_bytes(exc.stdout or b"")
            self.log("cube_timeout", number=self.calls)
            raise RuntimeError("Programmer timed out. The MCU may still be executing; "
                               "no target reset or retry was performed.") from exc
        path.write_bytes(result.stdout)
        text = result.stdout.decode("utf-8", errors="replace")
        self.log("cube_result", number=self.calls, returncode=result.returncode)
        if result.returncode or re.search(r"\bError\s*:", text, re.I) or (success and success not in text):
            raise RuntimeError(f"Programmer command failed. Details: {path}")
        return text

    def upload(self, address, length, label):
        self.uploads += 1
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(label))
        if not safe.lower().endswith(".bin"):
            safe += ".bin"
        path = self.output / f"read-{self.uploads:04d}-{safe}"
        self.call("-u", hex(address), str(length), path.resolve())
        data = path.read_bytes()
        if len(data) != length:
            raise RuntimeError("Incomplete target read; leaving target unchanged.")
        return data


class SessionLock:
    """Persistent per-probe interlock; an interrupted install is never retried."""
    def __init__(self, serial_number, output, root=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", serial_number):
            raise ValueError("Unexpected ST-LINK serial number.")
        root = Path(root) if root else Path.home() / ".global-x-camera" / "installer"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / (serial_number + ".json")
        self.state = dict(schema=1, serial=serial_number, started_utc=utc(),
                          logs=str(Path(output).resolve()), phase="waiting_for_recovery",
                          firmware_tag=TAG)
        try:
            with self.path.open("x", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError as exc:
            raise RuntimeError(f"An earlier install is unresolved: {self.path}. "
                               "Do not reset or retry. Preserve power and inspect that log first.") from exc

    def phase(self, phase):
        self.state.update(phase=phase, updated_utc=utc())
        save_json(self.path, self.state)

    def release(self):
        self.path.unlink()


def choose_probe(serial_number=None, explicit_port=None):
    from camera_recovery import discover_serial_ports, select_serial_port
    ports = discover_serial_ports()
    serials = sorted({p.serial_number for p in ports if p.serial_number})
    if serial_number is None:
        if len(serials) != 1:
            raise ValueError("Connect one ST-LINK USB cable to CN10. "
                             "If multiple boards are connected, select --serial explicitly. "
                             f"Detected ST-LINK serials: {serials}")
        serial_number = serials[0]
    return serial_number, select_serial_port(serial_number, explicit_port, ports=ports)


def wait_for_recovery(transport, port, assets, console, seconds=120, reset=False):
    from camera_recovery import RecoveryStream, request_recovery, verify_park
    if reset:
        console.progress(5, "Requesting an early recovery restart over ST-LINK...")
        request_recovery(port, transport.log)
        return verify_park(transport, assets / "profiles")
    # Queue the train BEFORE asking for target power. No BREAK/target reset.
    with RecoveryStream(port, transport.log, max_duration=seconds + 15) as stream:
        print("\nOK, now switch the camera's power switch to USB.", flush=True)
        print("I am sending the recovery signal and will detect the camera when it starts.", flush=True)
        print("If it was already on USB, wait for any photo/transfer to finish, then switch "
              "away from USB and back. Leave both cables attached.", flush=True)
        deadline = time.monotonic() + seconds
        next_notice = time.monotonic() + 15
        transport.default_timeout = 5
        last_error = None
        try:
            while time.monotonic() < deadline:
                stream.check()
                halts = transport.halt_requests
                try:
                    profile = verify_park(transport, assets / "profiles")
                    stream.check()
                    return profile
                except (RuntimeError, ValueError, OSError) as exc:
                    last_error = str(exc)
                    # After a halt or valid-code context check failure, preserve
                    # state for diagnosis instead of blindly polling again.
                    if transport.halt_requests != halts:
                        raise
                    transport.log("waiting_for_camera", reason=last_error)
                if time.monotonic() >= next_notice:
                    print("Still waiting for the camera's recovery response. Check the switch is now on USB.", flush=True)
                    next_notice = time.monotonic() + 15
                time.sleep(0.5)
        finally:
            transport.default_timeout = 20
        raise RuntimeError("No verified recovery response arrived. No flash was written. "
                           "Check both cables, the USB selector and the existing firmware. "
                           f"Last observation: {last_error}")


def program_and_verify(transport, nor, profile, images, output, console, lock):
    """No reset here. All backing data is saved before any NOR write."""
    output = Path(output)
    backup = output / "backup"
    backup.mkdir(exist_ok=False)
    lock.phase("backing_up")
    console.progress(15, "Camera is safely in recovery. Backing up existing firmware...")
    existing = [nor.read(0), nor.read(65536)]
    following = nor.read(131072)
    for index, data in enumerate(existing):
        (backup / f"sector{index}.bin").write_bytes(data)
    (backup / "following-4096.bin").write_bytes(following)
    save_json(backup / "identity.json", dict(profile=profile, following_sha256=sha(following),
                                             actual_sector_sha256=[sha(x) for x in existing]))
    for index, data in enumerate(existing):
        if sha(data) != profile[f"sector{index}_sha256"]:
            raise ValueError("Existing flash does not match the recognized firmware pair. "
                             "No flash write started; saved backup for diagnosis.")
    console.progress(25, "Backup saved. Installing the USB/photo-access section...")
    lock.phase("writing_sector1")
    nor.write(65536, existing[1], images[1])
    console.progress(50, "USB section verified. Installing the boot/capture section...")
    lock.phase("writing_sector0")
    nor.write(0, existing[0], images[0])
    console.progress(75, "Both writes completed. Reading both sections back independently...")
    lock.phase("independent_readback")
    for index in (0, 1):
        readback = nor.read(index * 65536)
        (output / f"verified-sector{index}.bin").write_bytes(readback)
        if readback != images[index]:
            raise RuntimeError(f"Sector {index} independent verification failed. Do not restart.")
    after = nor.read(131072)
    if after != following:
        raise RuntimeError("Flash following the firmware changed. Do not restart.")
    lock.phase("flash_verified")
    console.progress(90, "Both sections match exactly; neighboring flash is unchanged.")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="offline bundle checks only; no device access")
    p.add_argument("--install", action="store_true", help="same guided installation as default")
    p.add_argument("--non-interactive", action="store_true", help="AI/terminal mode; requires --confirm-idle")
    p.add_argument("--confirm-idle", action="store_true", help="operator confirms no capture/transfer/programming is active")
    p.add_argument("--restart", action="store_true", help="use existing ST-LINK BREAK reset instead of waiting for the power switch")
    p.add_argument("--cubeprogrammer", type=Path, help="full STM32_Programmer_CLI path if autodetection fails")
    p.add_argument("--serial", help="ST-LINK serial if more than one is connected")
    p.add_argument("--port", help="serial port override; must belong to the selected ST-LINK")
    p.add_argument("--wait-seconds", type=int, default=120, help="maximum wait for the user's USB switch (10–600 seconds)")
    p.add_argument("--output", type=Path, help="new log/backup folder (must not already exist)")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    console = Console()
    lock = None
    transport = None
    safe_to_unlock = True
    out = None
    try:
        images = validate_assets()
        if args.check:
            # Module validators additionally pin manifests/layouts without touching hardware.
            from camera_recovery import load_profiles
            load_profiles(ASSETS / "profiles")
            print("Offline firmware/helper/recovery files checked. No camera was accessed.")
            return 0
        if not 10 <= args.wait_seconds <= 600:
            raise ValueError("--wait-seconds must be between 10 and 600.")
        if args.non_interactive and not args.confirm_idle:
            raise ValueError("--non-interactive requires --confirm-idle after the operator checks the camera is idle.")
        import serial  # noqa: F401 - actionable dependency check before any device activity
        print("Global X Camera firmware installer — " + TAG, flush=True)
        print("This installer is offline-tested; this portable path has not yet been tested on a camera/Mac.")
        print("It installs exposure/ASA controls. It does not erase photos or require boot-jumper access.")
        while True:
            try:
                cli = find_cube(args.cubeprogrammer)
                break
            except ValueError as exc:
                if args.non_interactive:
                    raise
                print(f"\n{exc}")
                print("Choose MacOS Arm on an M-series Mac, or MacOS Intel on an Intel Mac.")
                print("Run ST's installer, then return here. No CubeIDE or compiler is needed.")
                answer = input("Press Enter to look again, paste the installed .app path, or type q to quit: ").strip()
                if answer.lower() == "q":
                    return 1
                if answer:
                    args.cubeprogrammer = Path(answer.strip("'\""))
        print("\nConnect USB cables between this computer and BOTH camera USB ports:")
        print("  ST-LINK / CN10: programming.   HOST / CN8: camera power and photos.")
        print("Finish any capture or photo transfer and close camera/serial/debugger apps.")
        print("Do not press the shutter during installation. Leave the existing boot jumpers unchanged.")
        if args.restart:
            print("For --restart, put the power switch on USB NOW and keep it there.")
        else:
            print("First leave the power switch on the BATTERY side, without pressing the shutter.")
            print("I will ask you to switch to USB after the recovery signal is ready.")
        if not args.non_interactive:
            input("Press Enter when both cables are attached and the camera is idle: ")
        serial_number, port = choose_probe(args.serial, args.port)
        out = (args.output or Path.home() / "global-x-camera-installs" /
               datetime.now().strftime("%Y%m%d-%H%M%S-%f")).expanduser().resolve()
        out.mkdir(parents=True, exist_ok=False)
        transport = Transport(cli, serial_number, out / "transport", console)
        lock = SessionLock(serial_number, out)
        save_json(out / "session.json", dict(started_utc=utc(), tag=TAG, probe_serial=serial_number,
                                             port=port, programmer=str(cli), hardware_tested_installer=False))
        console.progress(5, "ST-LINK connected. Preparing the startup recovery signal...")
        if args.restart:
            # Serial reset can mutate the target before any SWD halt is issued.
            # A failed/uncertain BREAK release must not look like a harmless
            # power-on wait timeout and permit a blind new installation.
            safe_to_unlock = False
            lock.phase("recovery_reset_requested")
        profile = wait_for_recovery(transport, port, ASSETS, console, args.wait_seconds, args.restart)
        # From here RAM helpers may run. Any failure retains the persistent interlock,
        # including failures during a read, so a later run cannot reset uncertain work.
        safe_to_unlock = False
        lock.phase("recovery_verified")
        save_json(out / "recognized-firmware.json", profile)
        from camera_nor import Nor
        nor = Nor(transport, ASSETS / "helpers", work_dir=out / "nor")
        program_and_verify(transport, nor, profile, images, out, console, lock)
        from camera_recovery import normal_reset, request_recovery, verify_park
        console.progress(95, "Checking that the new firmware still accepts UART recovery...")
        lock.phase("post_install_recovery_check")
        request_recovery(port, transport.log)
        new_profile = verify_park(transport, ASSETS / "profiles")
        if new_profile["prefix_sha256"] != "b866589cf472cac9820d961f3243cb8280759614826083757fae374ccee7e242":
            raise RuntimeError("Post-install recovery did not identify the r2 firmware.")
        save_json(out / "post-install-recovery.json", new_profile)
        lock.phase("normal_boot_release")
        normal_reset(port, transport.log)
        save_json(out / "complete.json", dict(completed_utc=utc(), tag=TAG, sector_sha256=TARGET_HASHES,
                                              independent_readbacks_match=True, following_4096_unchanged=True,
                                              post_install_uart_recovery=True, normal_powered_reset_released=True,
                                              normal_usb_operation_tested=False, photos_tested=False))
        lock.release()
        lock = None
        console.progress(100, "Firmware installed and verified. The camera is restarting for USB photo access.")
        print("Keep HOST connected and the switch on USB to access photos. ST-LINK may now be unplugged.")
        print("To take a photo later: finish transfers, unplug HOST, select battery power, then press the shutter.")
        print(f"Logs and the original firmware backup: {out}")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"\nSTOPPED: {exc or 'Cancelled by user.'}", file=sys.stderr, flush=True)
        if lock:
            if safe_to_unlock and (not transport or not transport.halt_requests):
                lock.release()
            else:
                print("Keep power/cables unchanged. Do not reset, retry, or delete the safety record.", file=sys.stderr)
                print(f"An unresolved session is recorded at: {lock.path}", file=sys.stderr)
        if out:
            print(f"Diagnostic logs: {out}", file=sys.stderr)
        if isinstance(exc, ModuleNotFoundError) and exc.name == "serial":
            print("Use Install.command to create the local Python environment with pyserial.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
