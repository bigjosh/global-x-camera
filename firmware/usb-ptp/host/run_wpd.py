"""Run one explicit native-WPD action with a timeout and UTF-8 JSON evidence.

The wrapper does not choose a device or object, retry, reset, power-cycle, or
delete anything automatically. A timeout kills only its child host process;
this is not proof that the device is idle or a deletion did not finish.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = pathlib.Path(__file__).resolve().parents[3]
    parser.add_argument("--exe", type=pathlib.Path, default=root / "tmp/usb-ptp-host/wpd_camera.exe")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--log", type=pathlib.Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command or args.timeout <= 0:
        parser.error("Provide one action after -- and a positive timeout")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids overwriting evidence from an earlier attempt.
    with args.log.open("x", encoding="utf-8") as log:
        start = time.monotonic()

        def record(event: str, **fields) -> None:
            item = {"event": event, "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "elapsed_s": time.monotonic() - start, **fields}
            line = json.dumps(item, ensure_ascii=False)
            log.write(line + "\n")
            log.flush()
            print(line, flush=True)

        record("host_start", argv=[str(args.exe.resolve()), *command], timeout_s=args.timeout,
               executable_sha256=hashlib.sha256(args.exe.read_bytes()).hexdigest())
        proc = subprocess.Popen([str(args.exe.resolve()), *command], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            stdout, stderr = proc.communicate()
        for line in stdout.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = {"unparsed": line}
            # WPD stdout is collected after completion; these are receipt times,
            # not per-transfer packet timestamps.
            record("native_output", payload=payload)
            if isinstance(payload, dict) and payload.get("event") == "download_complete":
                path = pathlib.Path(payload["path"])
                if path.is_file():
                    record("download_hash", path=str(path.resolve()), size=path.stat().st_size,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if stderr:
            record("native_stderr", text=stderr)
        record("host_end", returncode=proc.returncode, timed_out=timed_out,
               device_idle_proven=False if timed_out else None)
        return 124 if timed_out else proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
