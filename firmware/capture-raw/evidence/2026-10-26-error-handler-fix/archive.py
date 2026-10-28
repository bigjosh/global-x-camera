"""Offline snapshots for the post-frame error-handler placement fix.

Only explicit completed artifacts are copied. Verify never opens instruments,
serial ports, block devices, subprocesses or the network. Build/test/bench
scripts in snapshots are evidence, not commands executed by this verifier.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BUILDS = {
    "flash-normal-v2": "232af9173262473021453f40ea944dfa4cafc2657443cd0b83ea9c8c8bb3b02c",
    "flash-postframe-v3": "7f21f21e8cf48f8a0cabc4bffb842b55e5960af136496133500e67f25b4ded08",
}
ENGINE_SHA = "247ad0ddd76963039ed01a2e14beb3499ee9097a8df86f62ad5751047835454e"
BUILD_BINARIES = {"capture.bin", "stage1.bin", "stage1-unrelocated.bin", "stage1_boot.bin",
                  "stage2.bin", "stage2-full.bin", "capture_sector_0.bin"}
BUILD_EXTENSIONS = {".c", ".h", ".s", ".ld", ".inc", ".lst", ".map", ".json"}
POSTFRAME_DIRS = {"postframe-live-proof", "postframe-after-recovery", "postframe-after-park",
                 "postframe-after-sbf", "interrupt-live-proof", "interrupt-recovery", "interrupt-park",
                 "install-diagnostic", "install-normal"}
POSTFRAME_FILES = {"cold_led_trace.py", "make_cold_trace.py", "read_postframe.py",
                  "interrupt_after_frame.py", "interrupt-request.json", "postframe-complete-analysis.json"}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def entries(folder):
    return [dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size,
                 sha256=sha(p.read_bytes())) for p in sorted(folder.rglob("*"))
            if p.is_file() and p != folder / "SHA256SUMS.json" and "__pycache__" not in p.parts]


def seal(folder):
    write(folder / "SHA256SUMS.json", dict(schema=1, files=entries(folder)))


def verify_hashes(folder):
    expected = read(folder / "SHA256SUMS.json")["files"]
    actual = entries(folder)
    require(expected == actual, "Missing, changed, or extra archive files: " + str(folder))
    return dict(files=len(actual), bytes=sum(v["bytes"] for v in actual))


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def freeze_offline(source):
    destination = HERE / "snapshots" / "offline"
    require(not destination.exists(), "Offline snapshot already exists; never overwrite it")
    destination.mkdir(parents=True)
    for name in BUILDS:
        for path in sorted((source / name).rglob("*")):
            if path.is_file() and (path.suffix.lower() in BUILD_EXTENSIONS or
                    path.name in BUILD_BINARIES or path.name == "symbols.txt"):
                copy_file(path, destination / "inputs" / name / path.relative_to(source / name))
    review = source / "independent-review"
    for name in ("review.json", "recovery-gate-review.json", "review_recovery.py"):
        copy_file(review / name, destination / "review" / name)
    for name in BUILDS:
        for path in sorted((review / name).rglob("*")):
            if path.is_file() and path.suffix.lower() in {".bin", ".lst", ".json", ".py"}:
                copy_file(path, destination / "review" / name / path.relative_to(review / name))
    for name in ("build.py", "error_build.py", "error_signal.c", "error_signal.h",
                 "error_codes.h", "test_error_build.py", "test_error_signal.py", "test_error_codes.py"):
        copy_file(ROOT / "firmware/capture-raw" / name, destination / "host-source" / name)
    for source_name, target_name in (("error-relocate-all-tests.txt", "capture-tests.log"),
                                   ("error-relocate-tests.txt", "error-tests.log")):
        copy_file(ROOT / "tmp" / source_name, destination / "tests" / target_name)
    prior = ROOT / "tmp/bringup/error-blinks-20261026/flash-v2/staged"
    for name in ("stage1.bin", "manifest.json"):
        copy_file(prior / name, destination / "prior-build" / name)
    write(destination / "summary.json", dict(schema=1,
        frozen_utc=datetime.now(timezone.utc).isoformat(), kind="offline qualification",
        hardware_qualified=False, builds=list(BUILDS), capture_tests=182, error_tests=20,
        pending=["Diagnostic installed/cold boot after real full-frame DMA", "Five code-4 sets and shutdown",
                 "UART recovery after shutdown and during signaling", "Final production image installation"],
        exclusions=["ELF and object files", "Camera/photo payloads", "Live or unfinished bench results",
                    "Superseded/intermediate build candidates"]))
    seal(destination)
    result = replay_offline(destination)
    seal(HERE)
    return result


def replay_offline(snapshot):
    verify_hashes(snapshot)
    spec = importlib.util.spec_from_file_location("frozen_error_copy_audit", snapshot / "host-source/error_build.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    old = (snapshot / "prior-build/stage1.bin").read_bytes()
    old_m = read(snapshot / "prior-build/manifest.json")
    require(len(old) == 6500 and sha(old) == old_m["stage1_raw_sha256"], "Prior build identity")
    checks = {}
    for name, expected_sector in BUILDS.items():
        folder = snapshot / "inputs" / name
        m = read(folder / "manifest.json")
        pm = read(folder / "staged/manifest.json")
        binary = (folder / "capture.bin").read_bytes()
        prefix = (folder / "staged/stage1.bin").read_bytes()
        sector = (folder / "staged/capture_sector_0.bin").read_bytes()
        require(len(sector) == 65536 and sha(sector) == expected_sector == pm["program_sha256"], "Sector identity " + name)
        require(sha(binary) == m["binary_sha256"] == pm["stage2_full_sha256"], "Receiver identity " + name)
        require(len(prefix) == 6720 and sha(prefix) == pm["stage1_raw_sha256"], "Prefix identity " + name)
        require(m["late_load"]["early_bytes"] == 15804, "Early load changed")
        require(m["error_blinks"] and m["flash"] and m["standby"] and m["sd_clock_hz"] == 25000000 and
                m["sd_bus_width"] == 4 and m["sd_startup_opt"] and m["sd_review_profile"] and
                not m["raw_dma_tail_wait"] and not m["dma_sleep"], "Selected profile changed")
        diagnostic = name == "flash-postframe-v3"
        require(m["error_after_frame_test"] is diagnostic, "Diagnostic identity differs")
        if diagnostic:
            offset = m["error_after_frame_enable"] - m["load"]
            require(struct.unpack_from("<I", binary, offset)[0] == 1, "Diagnostic enable is not one")
            require(m["error_after_frame_proof"] == 0x343FD3C0 and m["error_after_frame_proof_bytes"] == 64,
                    "Diagnostic proof moved")
        else:
            require(m["error_after_frame_enable"] is None, "Production contains diagnostic enable")
        for filename, expected in m["source_hashes"].items():
            require(sha((folder / filename).read_bytes()) == expected, "Generated source differs: " + filename)
        for filename, expected in pm["sources"].items():
            require(sha((folder / "staged" / Path(filename).name).read_bytes()) == expected, "Prefix source differs")
        replay = audit.audit_engine(folder / "staged")
        recorded = dict(m["error_runtime_copy"])
        expected_sha = recorded.pop("sha256")
        require(replay == recorded, "Copied engine dependency audit differs")
        blob = prefix[0x1440:0x1440+1536]
        require(sha(blob) == ENGINE_SHA == expected_sha, "Copied engine differs")
        changes = [i for i, (a, b) in enumerate(zip(old, prefix)) if a != b]
        require(all(i in set(range(0xC9C, 0xCA0)) | set(range(0x1354, 0x1358)) for i in changes)
                and prefix[len(old):] == bytes(220), "Recovery/prefix instructions changed")
        require(pm["recovery_gpio"] == old_m["recovery_gpio"], "Recovery metadata changed")
        for stem in ("capture", "stage1"):
            source = folder if stem == "capture" else folder / "staged"
            for ext in (".bin", ".lst"):
                require((source / (stem+ext)).read_bytes() ==
                        (snapshot / "review" / name / (stem+ext)).read_bytes(), "Independent objcopy/objdump differs")
        checks[name] = dict(sector_sha256=expected_sector, engine_sha256=ENGINE_SHA,
                            early_bytes=15804, prefix_bytes=6720, diagnostic=diagnostic)
    gates = read(snapshot / "review/recovery-gate-review.json")
    require(gates["passed"] and gates["offline"] and gates["hardware_clients_constructed"] is False and
            gates["gate_checks"] == 18 and gates["positive_pairs"] == 2 and gates["negative_pairs"] == 7,
            "Recovery admission evidence differs")
    require("Ran 182 tests" in (snapshot / "tests/capture-tests.log").read_text() and
            "\nOK" in (snapshot / "tests/capture-tests.log").read_text(), "Capture test log differs")
    require("Ran 20 tests" in (snapshot / "tests/error-tests.log").read_text() and
            "\nOK" in (snapshot / "tests/error-tests.log").read_text(), "Error test log differs")
    return dict(schema=1, offline_replay_passed=True, hardware_qualified=False, checks=checks,
                scope="Exact source/code hashes and copied-engine dependency replay; no hardware result inferred")


def freeze_postframe(source):
    destination = HERE / "snapshots/postframe"
    require(not destination.exists(), "Postframe snapshot already exists; never overwrite it")
    destination.mkdir(parents=True)
    compressed = []
    omitted = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        selected = relative.parts[0] in POSTFRAME_DIRS
        selected |= len(relative.parts) == 1 and (path.name in POSTFRAME_FILES or
            path.name.startswith(("postframe-complete-", "postframe-interrupt-current", "postframe-interrupt-ready")))
        if not selected:
            continue
        if "private" in path.name or path.suffix.lower() not in {".py", ".json", ".jsonl", ".log", ".bin"}:
            omitted.append(str(relative)); continue
        target = destination / "inputs" / relative
        if len(relative.parts) == 1 and path.suffix == ".jsonl":
            data = path.read_bytes()
            records = [json.loads(line) for line in data.decode().splitlines()]
            require(records[-1]["event"] == "stopped", "Refusing unfinished current recording")
            target = target.with_suffix(target.suffix + ".gz")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
            compressed.append(dict(path=relative.as_posix(), compressed_path=target.relative_to(destination).as_posix(),
                                   bytes=len(data), sha256=sha(data)))
        else:
            copy_file(path, target)
    copy_file(source / "independent-review/postframe-hardware-review.json", destination / "review/postframe-hardware-review.json")
    copy_file(ROOT / "tmp/bringup/error-blinks-20261026/analyze_led_current.py", destination / "host-source/analyze_led_current.py")
    write(destination / "compression.json", dict(schema=1, files=compressed))
    write(destination / "summary.json", dict(schema=1,
        frozen_utc=datetime.now(timezone.utc).isoformat(), kind="Post-frame diagnostic hardware qualification",
        hardware_scope="Real full-frame DMA and STOP, production engine code4, shutdown and UART recovery",
        production_installed=True, normal_cycle_qualified=False,
        omitted_private_files=omitted,
        pending=["Normal production capture/error-path observation and final recovery/closure"],
        limitations=["No SD transaction in diagnostic capture", "No optical/LED GPIO probe",
                     "Read-only ST-LINK reads during current trace", "Whole-session startup NaNs remain invalid",
                     "Guarded power flags retain trial_entry_proven:false", "No power-loss or new energy qualification"]))
    seal(destination)
    result = replay_postframe(destination)
    seal(HERE)
    return result


def check_park(folder, prefix):
    value = read(folder / "result.json")
    require(value["passed"] and value["prefix_sha256"] == prefix and
            value["context"]["PC"] == 0x3418078C and value["context"]["PRIMASK"] == 1 and
            value["context"]["CONTROL"] == 0 and not value["ccr"] & 0x30000 and not value["fpccr"] & 1,
            "UART recovery context differs")
    uart = value["vcp_status"]
    require(uart["good_pulses"] >= 3 and not uart["bad_pulses"] and uart["request"] == 1,
            "UART request was not qualified")
    return dict(good_pulses=uart["good_pulses"], bad_pulses=0, prefix_sha256=prefix)


def check_install(folder, build):
    expected = (HERE / "snapshots/offline/inputs" / build / "staged/capture_sector_0.bin").read_bytes()
    require((folder / "nor-after/readback.bin").read_bytes() == expected and
            (folder / "write/readback.bin").read_bytes() == expected, "NOR installation readback differs")
    before = (folder / "following-before/readback.bin").read_bytes()
    after = (folder / "following-after/readback.bin").read_bytes()
    require(len(before) == 4096 and before == after, "Following NOR bytes changed")
    return dict(sector_sha256=sha(expected), full_independent_readback=True, following_4096_unchanged=True)


def replay_postframe(snapshot):
    verify_hashes(snapshot)
    inputs = snapshot / "inputs"
    result = dict(schema=1, post_frame_error_qualified=True, normal_cycle_qualified=False, checks={})
    checks = result["checks"]
    engine = (HERE / "snapshots/offline/inputs/flash-normal-v2/staged/stage1.bin").read_bytes()[0x1440:0x1A40]
    for name in ("postframe-live-proof", "interrupt-live-proof"):
        folder = inputs / name
        proof = read(folder / "verified.json")
        words = struct.unpack("<16I", (folder / "post-frame.bin").read_bytes())
        require(list(words) == proof["post_frame_words"] and proof["passed"], "Post-frame record differs")
        require(words[0] == 0x45504631 and words[4:10] == (1,1,1909600,1909600,1,0) and
                words[12:16] == (0,0,4,0x4550444E), "Full FRAME/STOP/guards before code4 not established")
        require(words[10] != words[11] and words[11] == struct.unpack_from("<I", engine)[0] and
                proof["prefix_overwritten"], "Source prefix overwrite not observed")
        require((folder / "runtime-engine.bin").read_bytes() == engine and
                proof["runtime_engine_sha256"] == ENGINE_SHA, "Persistent engine changed after DMA")
        require(struct.unpack("<3I", (folder / "copy-proof.bin").read_bytes()) == (0x45435031,0x343C8000,1536),
                "Fresh copy proof differs")
        require(not proof["cfsr"] and not proof["hfsr"] and not proof["reset"] and not proof["halt"] and
                not proof["target_writes"], "Fault/live-read scope differs")
        raw = proof["raw_proof"]
        require(raw["RP_RESULT"] == 0x20E and raw["RP_STATE"] == 15 and not raw["RP_SD_BEGIN"] and
                not raw["RP_CARD_READ_LO"] and not raw["RP_CARD_WRITE_LO"] and not raw["RP_WRITTEN_SECTORS"],
                "Diagnostic performed SD activity or lost the failure result")
        checks[name] = dict(frame_bytes=1909600, full_frame_stopped=True, source_overwritten=True,
                            copied_engine_exact=True, cfsr=0, hfsr=0, intended_code=4, no_sd_transaction=True)
    for item in read(snapshot / "compression.json")["files"]:
        data = gzip.decompress((snapshot / item["compressed_path"]).read_bytes())
        require(len(data) == item["bytes"] and sha(data) == item["sha256"], "Compressed current bytes differ")
    analysis = read(inputs / "postframe-complete-analysis.json")
    spec = importlib.util.spec_from_file_location("frozen_led_current_analysis", snapshot / "host-source/analyze_led_current.py")
    analyzer = importlib.util.module_from_spec(spec); spec.loader.exec_module(analyzer)
    class Trace:
        def read_bytes(self):
            return gzip.decompress((inputs / "postframe-complete-current.jsonl.gz").read_bytes())
        def __str__(self):
            return analysis["source"]
    replayed = analyzer.analyze(Trace(), analysis["launch_host_utc"], 4)
    require(replayed == analysis and analysis["complete_pattern_observed"] and
            analysis["measured"]["groups"] == [4]*5 and all(analysis["timing_consistency"].values()) and
            analysis["whole_session_ok"] is False and not analysis["fault_window_nonfinite_current"] and
            not analysis["fault_window_nonfinite_voltage"], "Current waveform replay/scope differs")
    checks["current_pattern"] = dict(groups=[4]*5, whole_session_ok=False, fault_window_finite=True,
        low_plateau_A=analysis["low_current_plateau"]["median_current_A"],
        interval_uncertainty_s=analysis["method"]["interval_uncertainty_s"])
    prefix = read(HERE / "snapshots/offline/inputs/flash-postframe-v3/staged/manifest.json")["stage1_raw_sha256"]
    checks["after_shutdown_uart"] = check_park(inputs / "postframe-after-park", prefix)
    checks["during_signal_uart"] = check_park(inputs / "interrupt-park", prefix)
    request = read(inputs / "interrupt-request.json")
    require(request["post_frame_verified"] and not request["sd_transaction"] and
            0 < request["seconds_after_power_on"] < request["nominal_blink_duration_s"], "Not an in-signal request")
    flags = read(inputs / "postframe-after-sbf/result.json")
    require(flags["passed"] and flags["sbf"] and flags["pdds"] and not flags["stopf"] and
            flags["trial_entry_proven"] is False and not flags["reset_or_power_changed"] and not flags["cpucr_written"],
            "Guarded power flag scope differs")
    checks["guarded_flags"] = dict(sbf=True,pdds=True,stopf=False,trial_entry_proven=False)
    checks["diagnostic_install"] = check_install(inputs / "install-diagnostic", "flash-postframe-v3")
    checks["production_install"] = check_install(inputs / "install-normal", "flash-normal-v2")
    return result


def freeze_normal(source):
    destination = HERE / "snapshots/normal"
    require(not destination.exists(), "Normal snapshot already exists; never overwrite it")
    destination.mkdir(parents=True)
    dirs = {"normal-live-proof", "normal-after-recovery", "normal-after-park", "normal-after-sbf"}
    compressed = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        selected = relative.parts[0] in dirs
        selected |= len(relative.parts) == 1 and (path.name.startswith(("normal-current", "normal-ready", "normal-analysis"))
                    or path.name == "observe_normal.py")
        if not selected or "private" in path.name or path.suffix.lower() not in {".py", ".json", ".jsonl", ".log", ".bin"}:
            continue
        target = destination / "inputs" / relative
        if len(relative.parts) == 1 and path.suffix == ".jsonl":
            data = path.read_bytes()
            records = [json.loads(line) for line in data.decode().splitlines()]
            require(records[-1]["event"] == "stopped", "Refusing unfinished normal current recording")
            target = target.with_suffix(target.suffix + ".gz")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
            compressed.append(dict(path=relative.as_posix(), compressed_path=target.relative_to(destination).as_posix(),
                                   bytes=len(data), sha256=sha(data)))
        else:
            copy_file(path, target)
    for kind in ("recovery", "park"):
        before = ROOT / ("tmp/bringup/error-handler-fix-initial-" + kind + "-20261026")
        for path in sorted(before.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".log", ".bin"}:
                copy_file(path, destination / "inputs" / ("initial-"+kind) / path.relative_to(before))
    copy_file(source / "independent-review/final-hardware-review.json", destination / "review/final-hardware-review.json")
    write(destination / "compression.json", dict(schema=1, files=compressed))
    write(destination / "summary.json", dict(schema=1, frozen_utc=datetime.now(timezone.utc).isoformat(),
        kind="Installed production error path and final closure", requested_error_fix_qualified=True,
        successful_normal_save=False, no_sd_writes=True,
        installed_sector=BUILDS["flash-normal-v2"], final_state="Powered at exact normal early UART park after guarded flag read",
        additional_normal_boot=False, known_outstanding="Resistor-free 25 MHz CMD17 CRC failure remains",
        limitations=["Normal cycle reproduced real SD read failure; no new image saved",
                     "cleanup_error10 remains a failed-operation record, not idle/success permission",
                     "Whole-session startup NaNs remain invalid; finite error window separately checked",
                     "Current steps infer LEDs without optical/GPIO probe; interval uncertainty +/-20ms",
                     "Guarded flags retain trial_entry_proven:false", "No new power-loss/energy qualification"]))
    seal(destination)
    result = replay_normal(destination)
    seal(HERE)
    return result


def replay_normal(snapshot):
    verify_hashes(snapshot)
    inputs = snapshot / "inputs"
    observation = read(inputs / "normal-live-proof/observation.json")
    proof = observation["raw_proof"]
    require(observation["debug_reads"] and not observation["halt"] and not observation["cfsr"] and not observation["hfsr"] and
            observation["runtime_engine_sha256"] == ENGINE_SHA, "Normal fault observation differs")
    require(proof["RP_STATE"] == 15 and proof["RP_RESULT"] == 0x324 and proof["RP_STAGE"] == 3 and
            proof["RP_CLOCK_HZ"] == 25000000 and proof["RP_SD_ERROR"] == 14 and proof["RP_CLEANUP_ERROR"] == 10 and
            proof["RP_SCAN_HEADERS"] == 2 and not proof["RP_WRITTEN_SECTORS"] and not proof["RP_CARD_WRITE_LO"] and
            proof["RP_CAMERA_READY"] == proof["RP_DMA_BYTES"] == 1909600 and proof["RP_FRAMES"] == 1 and not proof["RP_CANARY"],
            "Normal failure history/capture result differs")
    card = struct.unpack("<38I", (inputs / "normal-live-proof/reads/card.bin").read_bytes()[48:200])
    require(card[14:18] == (14,5,17,2) and card[26] == 10, "CMD17 data-CRC failure/cleanup record differs")
    scb = struct.unpack("<16I", (inputs / "normal-live-proof/reads/scb.bin").read_bytes())
    require(scb[10:12] == (0,0), "Normal error raised another fault")
    engine = (inputs / "normal-live-proof/reads/runtime-engine.bin").read_bytes()
    require(sha(engine) == ENGINE_SHA, "Normal persistent engine changed")
    item, = read(snapshot / "compression.json")["files"]
    raw = gzip.decompress((snapshot / item["compressed_path"]).read_bytes())
    require(len(raw) == item["bytes"] and sha(raw) == item["sha256"], "Normal current bytes differ")
    analysis = read(inputs / "normal-analysis.json")
    spec = importlib.util.spec_from_file_location("normal_frozen_current_analysis", HERE / "snapshots/postframe/host-source/analyze_led_current.py")
    analyzer = importlib.util.module_from_spec(spec); spec.loader.exec_module(analyzer)
    class Trace:
        def read_bytes(self): return raw
        def __str__(self): return analysis["source"]
    replayed = analyzer.analyze(Trace(), analysis["launch_host_utc"], 4)
    require(replayed == analysis and analysis["complete_pattern_observed"] and
            analysis["measured"]["groups"] == [4]*5 and all(analysis["timing_consistency"].values()) and
            analysis["whole_session_ok"] is False and not analysis["fault_window_nonfinite_current"] and
            not analysis["fault_window_nonfinite_voltage"], "Normal waveform replay/scope differs")
    prefix = read(HERE / "snapshots/offline/inputs/flash-normal-v2/staged/manifest.json")["stage1_raw_sha256"]
    uart = check_park(inputs / "normal-after-park", prefix)
    flags = read(inputs / "normal-after-sbf/result.json")
    require(flags["passed"] and flags["sbf"] and flags["pdds"] and not flags["stopf"] and
            flags["trial_entry_proven"] is False and not flags["reset_or_power_changed"] and not flags["cpucr_written"],
            "Normal guarded power flag scope differs")
    stop = json.loads(raw.decode().splitlines()[-1])
    require(stop["event"] == "stopped" and not stop["cleanup_errors"] and stop["device_context_closed"],
            "Normal instrument closure did not complete")
    return dict(schema=1, requested_error_fix_qualified=True, successful_normal_save=False,
                actual_error=dict(command=17,error=14,stage=5,sta=2,cleanup_error=10),
                full_frame_bytes=1909600,cfsr=0,hfsr=0,groups=[4]*5,
                low_plateau_A=analysis["low_current_plateau"]["median_current_A"],
                uart=uart,guarded_flags=dict(sbf=True,pdds=True,stopf=False,trial_entry_proven=False),
                whole_session_ok=False,fault_window_finite=True,device_context_closed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze-offline")
    freeze.add_argument("--source", type=Path, required=True)
    bench = sub.add_parser("freeze-postframe")
    bench.add_argument("--source", type=Path, required=True)
    normal = sub.add_parser("freeze-normal")
    normal.add_argument("--source", type=Path, required=True)
    sub.add_parser("verify")
    sub.add_parser("seal")
    args = parser.parse_args()
    if args.command == "freeze-offline":
        result = freeze_offline(args.source.resolve())
    elif args.command == "freeze-postframe":
        result = freeze_postframe(args.source.resolve())
    elif args.command == "freeze-normal":
        result = freeze_normal(args.source.resolve())
    elif args.command == "verify":
        outer = verify_hashes(HERE)
        result = dict(outer=outer, offline=replay_offline(HERE / "snapshots/offline"))
        if (HERE / "snapshots/postframe").exists():
            result["postframe"] = replay_postframe(HERE / "snapshots/postframe")
        if (HERE / "snapshots/normal").exists():
            result["normal"] = replay_normal(HERE / "snapshots/normal")
    else:
        for folder in (HERE / "snapshots").iterdir():
            if folder.is_dir():
                verify_hashes(folder)
        seal(HERE)
        result = dict(sealed=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
