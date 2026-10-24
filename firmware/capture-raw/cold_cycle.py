"""One root-owned cold cycle with JS raw and Saleae phase capture.

Dry-run by default. Requires root-authored, evidence-bound safe-start proof;
never uses ST-LINK, UART, a NOR helper, firmware writes, or automatic retries.
The current signature and pre-WFI marker do not prove physical Standby.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OWNER_SOURCE = HERE / "support/single_cycle.py"
OWNER_SHA = "45919bdaa9900f228a1666f2a421ebbd3d8db8e7166de15865f2aa405f72b322"
PHASE = ROOT / "firmware/capture-sd/phase_markers"
JS_HELPER = ROOT / "firmware/boot-timing/js110_session.py"
from phase_protocol import PHASE_PROTOCOL, APPROVED_PROTOCOLS
from phase_decode import summarize_folder


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def owner_module():
    if sha_file(OWNER_SOURCE) != OWNER_SHA:
        raise ValueError("Reviewed single-cycle owner helper changed")
    spec = importlib.util.spec_from_file_location("reviewed_cycle_owner", OWNER_SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_proof(path, build, *, now=None, raw=None, expected_end="standby"):
    path, build = Path(path).resolve(), Path(build).resolve()
    proof = json.loads(path.read_bytes() if raw is None else raw)
    if type(proof.get("schema")) is not int or proof["schema"] != 1 or proof.get("bench_owner") != "root":
        raise ValueError("Expected schema1 root-authored safe-start proof")
    if proof.get("start_kind") not in ("nor-maintenance-complete", "standby-plateau"):
        raise ValueError("Unknown safe-start kind")
    for field in ("safe_to_remove_power", "nor_idle", "storage_idle", "no_active_clients"):
        if proof.get(field) is not True:
            raise ValueError("Root safe-start qualification missing: " + field)
    at = datetime.fromisoformat(proof["observed_utc"].replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("Safe-start observation requires an explicit timezone")
    now = now or datetime.now(timezone.utc)
    if not 0 <= (now-at).total_seconds() <= 600:
        raise ValueError("Safe-start observation is future-dated or older than10minutes")
    for field in ("current_a", "input_voltage_v"):
        value = proof.get(field)
        if type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError("Safe-start measurement missing/nonfinite: " + field)
    if not 4.5 < proof["input_voltage_v"] < 5.5 or not .003 < proof["current_a"] < .25:
        raise ValueError("Safe-start current/supply outside reviewed bench range")
    if proof["start_kind"] == "standby-plateau" and not .006 < proof["current_a"] < .012:
        raise ValueError("Standby-signature starting current is outside6–12mA")
    sector = build / "staged/capture_sector_0.bin"
    manifest = json.loads((build / "staged/manifest.json").read_text(encoding="utf-8"))
    digest = sha_file(sector)
    if sector.stat().st_size != 65536 or digest != manifest.get("program_sha256") or digest != proof.get("sector_sha256"):
        raise ValueError("Safe-start proof does not bind the exact selected sector")
    receiver_path = build / "manifest.json"
    receiver = json.loads(receiver_path.read_bytes())
    if expected_end not in ("standby", "awake"):
        raise ValueError("Unknown expected completion observation")
    standby = expected_end == "standby"
    policy = "Standby after complete RAW slot" if standby else "Awake RAW terminal park"
    if (manifest.get("stage2_manifest_sha256") != sha_file(receiver_path)
            or receiver.get("kind") != "raw-slots"
            or receiver.get("flash") is not True or receiver.get("standby") is not standby
            or manifest.get("completion_policy") != policy
            or receiver.get("frame_bytes") != 1909600
            or receiver.get("phase_markers") not in APPROVED_PROTOCOLS):
        raise ValueError("Selected build does not declare the reviewed RAW/PD12/Standby phase protocol")
    code = build / "capture.bin"
    if (sha_file(code) != receiver.get("binary_sha256")
            or sha_file(code) != manifest.get("stage2_full_sha256")
            or code.stat().st_size != receiver.get("binary_bytes")):
        raise ValueError("Selected RAW receiver differs from its bound manifest")
    late = receiver.get("late_load", {})
    if (not 0 < late.get("early_bytes",0) <= 15804
            or late.get("after_arm") is not True
            or late.get("interrupts_enabled") is not True
            or late.get("layout_audit",{}).get("vectors_early") is not True
            or late.get("layout_audit",{}).get("early_irq_symbols") is not True
            or manifest.get("late_load") != late):
        raise ValueError("RAW cold-load layout is not qualified for this runner")
    if (sha_file(build / "staged/stage1.bin") != manifest.get("stage1_raw_sha256")
            or manifest.get("checked_recovery_literal_offsets") is None):
        raise ValueError("RAW recovery prefix identity proof is missing")
    evidence = proof.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Safe-start proof must include checked idle/verification evidence")
    for item in evidence:
        p = Path(item["path"])
        if not p.is_absolute(): p = path.parent / p
        if sha_file(p) != item.get("sha256"):
            raise ValueError("Safe-start evidence bytes changed: " + str(p))
    # Internal decoded observation contract comes only from the bound build.
    # The original root proof bytes are archived unchanged by main().
    proof["selected_phase_protocol"]=receiver["phase_markers"]
    return proof


def perform_cycle(owner, phase, proof, *, clock=time.monotonic, sleep=time.sleep, fresh=None,
                  expected_end="standby"):
    if fresh is None: fresh = owner_module().fresh_sample
    def sample(): return fresh(owner.latest(), int(clock()*1e9))
    def initial_ok(s):
        current = s["current"]["avg"]
        if proof["start_kind"] == "standby-plateau": return .006 < current < .012
        return abs(current-proof["current_a"]) <= max(.005, .2*proof["current_a"])
    initial, seen, deadline = [], None, clock()+6
    while clock() < deadline:
        s = sample()
        if s["sequence"] != seen:
            seen = s["sequence"]
            initial = initial+[s] if initial_ok(s) else []
            if len(initial) >= 6: break
        sleep(.1)
    if len(initial) < 6: raise RuntimeError("No stable proof-consistent starting current; no power switch")
    owner.log("proof_consistent_start", statistics=initial, start_kind=proof["start_kind"],
              scope="Current confirms signature only; root proof supplies idle qualification")
    owner.command("off")
    off_at = clock(); off_samples=[]; seen=None
    while clock()-off_at < 15:
        s = sample()
        if s["sequence"] != seen:
            seen = s["sequence"]
            if clock()-off_at >= 1:
                off_samples = off_samples+[s] if abs(s["current"]["avg"]) < .0001 else []
        sleep(.1)
    if len(off_samples)<3 or abs(sample()["current"]["avg"])>=.0001:
        raise RuntimeError("Off-current baseline missing; no explicit auto/retry")
    owner.log("off_baseline", off_seconds=clock()-off_at, statistics=off_samples[-3:])
    phase.start_wait()  # Wait for successful API start before target restoration.
    sample()  # Refuse an unexpectedly stopped/stale JS owner.
    owner.command("auto")
    on_at=clock(); active=False; terminal=[]; seen=None
    while clock()-on_at < 12:
        s=sample()
        if expected_end == "awake" and clock()-on_at >= 10:
            owner.log("awake_observation_complete", elapsed_after_on_command_s=clock()-on_at,
                      active_current_observed=active, terminal_state_qualified=False,
                      scope="Fixed powered observation only; exact terminal/storage proof still required")
            return
        if s["sequence"] != seen:
            seen=s["sequence"]
            active=active or s["current"]["avg"]>.03
            if expected_end == "standby" and active and clock()-on_at>3 and .006<s["current"]["avg"]<.012:
                terminal.append(s)
            else: terminal=[]
            if len(terminal)>=6:
                owner.log("terminal_current_signature", statistics=terminal,
                          elapsed_after_on_command_s=clock()-on_at,
                          terminal_state_qualified=False)
                return
        sleep(.1)
    raise RuntimeError("No active-then-terminal signature; keep powered, never retry")


class PhaseCapture:
    def __init__(self, output):
        self.output=output; self.process=None; self.logfile=None

    def start_wait(self):
        self.logfile=(self.output.parent/"phase-output.txt").open("w",encoding="utf-8")
        command=[sys.executable,str(PHASE/"capture.py"),str(self.output),
                 "--probes-confirmed","--seconds","10","--analog-power"]
        self.process=subprocess.Popen(command,cwd=ROOT,stdout=self.logfile,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Phase capture exited before handshake; inspect phase-output.txt")
            if (self.output/"started").is_file(): return
            time.sleep(.05)
        raise RuntimeError("No phase capture handshake within6s; do not retry")

    def finish(self):
        if self.process is None: return
        try: code=self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Phase PID{self.process.pid} stillactive; no secondcapture or forcedtermination")
        finally:
            if self.process.poll() is not None and self.logfile is not None: self.logfile.close()
        if code: raise RuntimeError("Phase capture/export failed; retained evidence, no retry")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--build",type=Path,required=True)
    ap.add_argument("--safe-start-proof",type=Path,required=True)
    ap.add_argument("--expected-end",choices=("standby","awake"),default="standby")
    ap.add_argument("--owner-confirmed",action="store_true")
    ap.add_argument("--probes-confirmed",action="store_true")
    ap.add_argument("--execute",action="store_true")
    a=ap.parse_args(); output=a.out.resolve()
    if not output.is_relative_to(ROOT/"tmp"): ap.error("Output must remain under repo/tmp")
    command=[sys.executable,str(JS_HELPER),"--control",str(output/"control.json"),
        "--response",str(output/"response.json"),"--log",str(output/"session.jsonl"),
        "--cycle-raw-dir",str(output/"raw"),"--raw-max-mib","2048",
        "--raw-queue-chunks","1024","--duration","60"]
    if not a.execute:
        print(json.dumps(dict(plan_only=True,command=command,build=str(a.build),
            safe_start_proof=str(a.safe_start_proof),expected_end=a.expected_end,phase_seconds=10,off_seconds=15,
            limits="No reset/NOR/storage commands; root-qualified safe start required; no automatic retry"),indent=2))
        return 0
    if not (a.owner_confirmed and a.probes_confirmed): ap.error("Execute requires owner and probe confirmation")
    if output.exists(): ap.error("New output directory required")
    proof_bytes=a.safe_start_proof.read_bytes()
    proof_sha=hashlib.sha256(proof_bytes).hexdigest()
    proof=validate_proof(a.safe_start_proof,a.build,raw=proof_bytes,expected_end=a.expected_end)
    module=owner_module(); owner=module.Owner(output,command); phase=PhaseCapture(output/"phase")
    failure=None
    try:
        owner.start()
        (output/"safe-start-proof.json").write_bytes(proof_bytes)
        owner.log("safe_start_bound",proof_sha256=proof_sha,
                  owner_source_sha256=OWNER_SHA,sector_sha256=proof["sector_sha256"])
        perform_cycle(owner,phase,proof,fresh=module.fresh_sample,expected_end=a.expected_end)
    except Exception as exc:
        failure=exc
        if output.is_dir(): owner.log("cycle_error",error=str(exc),action="No retry; cleanstop restores auto power")
    finally:
        # Close raw first: avoid buffering while a slow export/analysis runs.
        try: owner.stop()
        except Exception as exc:
            failure=failure or exc
            if output.is_dir(): owner.log("owner_cleanup_error",error=str(exc))
        try: phase.finish()
        except Exception as exc:
            failure=failure or exc
            if output.is_dir(): owner.log("phase_cleanup_error",error=str(exc))
    if failure: raise failure
    manifest=json.loads((output/"raw/manifest.json").read_text(encoding="utf-8"))
    if manifest.get("finalized") is not True: raise RuntimeError("Raw recording is not finalized/qualified for analysis")
    decoded=summarize_folder(output/"phase",standby=a.expected_end=="standby",
                             protocol=proof["selected_phase_protocol"])
    (output/"phase-summary.json").write_text(json.dumps(decoded,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    result=dict(recording_complete=True,expected_end=a.expected_end,phase_decode_passed=decoded["decode_passed"],
                terminal_state_qualified=False,image_integrity_verified=False,
                sector_sha256=proof["sector_sha256"],safe_start_proof_sha256=proof_sha,
                raw_manifest_sha256=sha_file(output/"raw/manifest.json"),
                phase_summary_sha256=sha_file(output/"phase-summary.json"),
                interpretation="Current signature and pre-WFI intent only; actualStandby/SBF/image need separate proof")
    (output/"result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
    return 0 if decoded["decode_passed"] else 2


if __name__=="__main__": raise SystemExit(main())
