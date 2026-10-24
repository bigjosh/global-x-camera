"""One root-owned v59 cold-cycle recording. Dry-run unless --execute.

Start only after the bench owner has put unchanged v59 into its known quiet
terminal state. This runner does not use ST-LINK, UART, Saleae or firmware
writes. Its current guard is a bench signature, not a saved-file/SBF proof.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "firmware/boot-timing/js110_session.py"
SECTOR = "7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63"


def stamp():
    return dict(utc=datetime.now(timezone.utc).isoformat(), monotonic_ns=time.monotonic_ns())


def fresh_sample(sample, now_ns):
    if not sample or not 0 <= now_ns-sample["received"]["monotonic_ns"] < 2_000_000_000:
        raise RuntimeError("Missing/stale statistics; no further power-off is permitted")
    for signal in ("current", "voltage", "power"):
        value = sample[signal]["avg"]
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise RuntimeError("Nonfinite statistics; no further power-off is permitted")
    if not 4.5 < sample["voltage"]["avg"] < 5.5:
        raise RuntimeError("JS input supply is outside the expected 5 V range")
    return sample


def perform_cycle(owner, *, clock=time.monotonic, sleep=time.sleep):
    """Only this small state machine sends off/auto; never retries a cycle."""
    def sample():
        return fresh_sample(owner.latest(), int(clock()*1e9))

    initial, seen = [], None
    deadline = clock()+6
    while clock() < deadline:
        s = sample()
        if s["sequence"] != seen:
            seen = s["sequence"]
            initial = initial+[s] if .006 < s["current"]["avg"] < .012 else []
            if len(initial) >= 6:
                break
        sleep(.1)
    if len(initial) < 6:
        raise RuntimeError("No stable starting plateau; no power cycle was started")
    owner.log("starting_plateau", statistics=initial)
    owner.command("off")
    off_at = clock()
    off_samples, seen = [], None
    while clock()-off_at < 15:
        s = sample()
        if s["sequence"] != seen:
            seen = s["sequence"]
            # Exclude the first mixed half-second after switching off.
            if clock()-off_at >= 1:
                off_samples = off_samples+[s] if abs(s["current"]["avg"]) < .0001 else []
        sleep(.1)
    if len(off_samples) < 3 or abs(sample()["current"]["avg"]) >= .0001:
        raise RuntimeError("Off-current baseline was not observed; helper restoration may re-enable power")
    owner.log("off_baseline", statistics=off_samples[-3:], off_seconds=clock()-off_at)
    owner.command("auto")
    on_at = clock()
    active, terminal, seen = False, [], None
    while clock()-on_at < 12:
        s = sample()
        if s["sequence"] != seen:
            seen = s["sequence"]
            active = active or s["current"]["avg"] > .03
            if active and clock()-on_at > 3 and .006 < s["current"]["avg"] < .012:
                terminal.append(s)
            else:
                terminal = []
            if len(terminal) >= 6:
                owner.log("terminal_plateau", statistics=terminal,
                          elapsed_after_on_command_s=clock()-on_at,
                          terminal_state_qualified=False)
                return
        sleep(.1)
    raise RuntimeError("No active-then-terminal signature; leave power on and inspect, never retry automatically")


class Owner:
    def __init__(self, output, command):
        self.output, self.command_line = output, command
        self.process, self.output_file = None, None
        self.last_statistics = None
        self.ready_record = None
        self.stopped_record = None
        self.log_offset = 0
        self.log_tail = b""

    def log(self, event, **values):
        record = dict(event=event, **stamp(), **values)
        with (self.output/"cycle.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, allow_nan=False)+"\n")
        print(json.dumps(record, allow_nan=False), flush=True)

    def poll(self):
        path = self.output/"session.jsonl"
        if path.exists():
            with path.open("rb") as f:
                f.seek(self.log_offset)
                data = f.read()
                self.log_offset = f.tell()
            lines = (self.log_tail+data).split(b"\n")
            self.log_tail = lines.pop()
            for line in lines:
                if not line:
                    continue
                record = json.loads(line)
                if record.get("statistics") is not None:
                    self.last_statistics = record["statistics"]
                if record.get("event") == "ready":
                    self.ready_record = record
                if record.get("event") == "stopped":
                    self.stopped_record = record

    def start(self):
        self.output.mkdir(parents=True, exist_ok=False)
        self.output_file = (self.output/"helper-output.txt").open("w", encoding="utf-8")
        self.process = subprocess.Popen(self.command_line, cwd=ROOT,
            stdout=self.output_file, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.log("helper_started", pid=self.process.pid, command=self.command_line)
        deadline = time.monotonic()+6
        while time.monotonic() < deadline:
            self.poll()
            if self.ready_record:
                if self.ready_record.get("starting_range") != 128:
                    raise RuntimeError("Expected retained auto range128; refusing a different initial power state")
                if self.last_statistics is not None:
                    return
            if self.process.poll() is not None:
                raise RuntimeError("JS helper exited before ready; inspect helper-output.txt")
            time.sleep(.1)
        raise RuntimeError("JS helper did not become ready within6 seconds")

    def latest(self):
        self.poll()
        if self.process.poll() is not None or self.stopped_record:
            raise RuntimeError("JS helper stopped unexpectedly; no further power commands")
        return self.last_statistics

    def command(self, state):
        ident = state+"-"+str(time.monotonic_ns())
        temp = self.output/"control-write.tmp"
        temp.write_text(json.dumps(dict(id=ident,state=state)), encoding="utf-8")
        temp.replace(self.output/"control.json")
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            try:
                r = json.loads((self.output/"response.json").read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                r = {}
            if r.get("id") == ident:
                self.log("command_"+state, response=r)
                if not r.get("ok"):
                    raise RuntimeError("Helper refused/failed command "+state)
                if state in ("off","auto") and r.get("range") != (0 if state=="off" else 128):
                    raise RuntimeError("Retained range did not match requested state")
                return r
            if self.process.poll() is not None:
                raise RuntimeError("Helper exited before acknowledging "+state)
            time.sleep(.1)
        raise RuntimeError("Mailbox timeout for "+state+"; do not retry the power command")

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                self.command("stop")
            except Exception as exc:
                self.log("stop_request_error", error=str(exc))
        try:
            code = self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Helper PID{self.process.pid} remains active; do not start another owner or force terminate")
        finally:
            if self.process.poll() is not None and self.output_file is not None:
                self.output_file.close()
        self.poll()
        if code or not self.stopped_record or not self.stopped_record.get("ok"):
            raise RuntimeError("Helper did not stop with complete logging/settings restoration")
        if self.stopped_record.get("range") != 128:
            raise RuntimeError("Starting auto range was not restored")


def offline_analysis(output):
    # Run only after the child closes the recording. No live-recording scans.
    if any((output/name).exists() for name in ("measurement-context.json","spec.json","analysis.json")):
        raise FileExistsError("Refusing to overwrite existing analysis evidence")
    sys.path.insert(0, str(ROOT/"firmware/capture-sd"))
    import numpy as np
    import cycle_energy
    raw = output/"raw"
    with cycle_energy.Archive(raw) as archive:
        if archive.rate != 2000000 or archive.decimation != 1:
            raise ValueError("Unexpected native sample geometry")
        step = archive.rate//10
        intervals, start = [], None
        for at in range(archive.start, archive.end-step+1, step):
            data = archive.get("current", at, at+step)
            quiet = np.isfinite(data).all() and float(np.max(np.abs(data))) < .0001
            if quiet and start is None:
                start = at
            elif not quiet and start is not None:
                if at-start >= 10*archive.rate:
                    intervals.append((start,at))
                start = None
        if start is not None and archive.end-start >= 10*archive.rate:
            intervals.append((start,archive.end))
        if len(intervals) != 1:
            raise ValueError("Expected exactly one observed >=10s off baseline")
        begin = intervals[0][0]+2*archive.rate
        end = archive.end-step
    context = dict(schema=1, terminal_state_qualified=False,
        scope="Current/power signature only; no per-cycle SBF or file verification",
        last_verified_firmware_sector_sha256=SECTOR, firmware_reverified_this_recording=False,
        bench_owner="root", no_debug_or_uart_commands_in_runner=True,
        raw_manifest_sha256=hashlib.sha256((raw/"manifest.json").read_bytes()).hexdigest(),
        cycle_log_sha256=hashlib.sha256((output/"cycle.jsonl").read_bytes()).hexdigest())
    (output/"measurement-context.json").write_text(json.dumps(context,indent=2)+"\n")
    criteria = dict(bin_s=.001,off_baseline_s=.5,off_abs_max_a=.0001,onset_a=.12,
        pretrigger_s=.1,plateau_min_s=1.0,plateau_mean_min_a=.007,
        plateau_mean_max_a=.01,plateau_peak_abs_max_a=.0105,
        plateau_mean_span_a=.002,current_valid_abs_max_a=9.5)
    spec = dict(criteria=criteria,cycles=[dict(name=output.name+" (unverified plateau)",
        start_sample_id=begin,end_sample_id=end,terminal_state_qualified=False,
        terminal_evidence=str(output/"measurement-context.json"))])
    (output/"spec.json").write_text(json.dumps(spec,indent=2)+"\n")
    analysis = cycle_energy.analyze(raw,spec,allow_unqualified_plateau=True)
    (output/"analysis.json").write_text(json.dumps(analysis,indent=2,allow_nan=False)+"\n")
    return analysis


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--owner-confirmed",action="store_true",
                        help="Bench owner checked no competing JS/firmware session")
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--analyze-only",action="store_true")
    args=parser.parse_args()
    output=args.out.resolve()
    if not output.is_relative_to(ROOT/"tmp"):
        parser.error("Output must remain below this repo's tmp directory")
    if args.analyze_only:
        if args.execute:
            parser.error("Do not combine --execute and --analyze-only")
        offline_analysis(output)
        return 0
    command=[sys.executable,str(HELPER),"--control",str(output/"control.json"),
        "--response",str(output/"response.json"),"--log",str(output/"session.jsonl"),
        "--cycle-raw-dir",str(output/"raw"),"--raw-max-mib","2048",
        "--raw-queue-chunks","1024","--duration","40"]
    if not args.execute:
        print(json.dumps(dict(plan_only=True,command=command,
            requirements="No other owner; v59 already at known low-current terminal state; CN8/JS route verified"),indent=2))
        return 0
    if not args.owner_confirmed:
        parser.error("--execute requires --owner-confirmed")
    if output.exists():
        parser.error("Output directory already exists; every recording needs a new directory")
    owner=Owner(output,command)
    failure=None
    try:
        owner.start()
        perform_cycle(owner)
    except Exception as exc:
        failure=exc
        if output.is_dir():
            owner.log("cycle_error",error=str(exc),action="No retry; request clean helper stop and preserve target auto power")
    finally:
        try:
            owner.stop()
        except Exception as exc:
            failure=failure or exc
            if output.is_dir():
                owner.log("cleanup_error",error=str(exc))
    if failure:
        raise failure
    analysis=offline_analysis(output)
    print(json.dumps(dict(recording_complete=True,terminal_state_qualified=False,
        analysis=str(output/"analysis.json"),onset_to_plateau_energy_j=analysis["cycles"][0]["onset_to_plateau_energy_j"])))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
