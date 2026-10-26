"""Offline immutable snapshots of the error-blink qualification evidence.

No hardware, serial, subprocess or network access. `snapshot` copies only the
explicit completed-artifact selection below; `verify` checks exact public bytes
and replays independent firmware, install, recovery and current-trace checks.
Qualification pending in a snapshot is never promoted by hash verification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
NEW_PREFIX = "7f8017fd70bd9b77cfabcf212d072201ec8e134c3a44a0555a2108d7cc454c32"
OLD_PREFIX = "0592a543cb1e75b176e97f715f139a0a13d8a4d791ba44efd0ec94dc4f5b6754"
NEW_SECTOR = "5ad1bc968606b17e513680bcdf6abf9c73ca3ccf24a236a37b8ecc89d4e9c661"
OLD_SECTOR = "c68593cebeddf5b9c24f85249505ae719dd1ea73d11f309e3a8553e9c1a9fa47"
NEW_RECEIVER = "471fddf2c71b7d8bba8e47debf8379a8fd72c7f3daae59dcdf10dc8eed1198af"
RAM_BINARY = "ad66bde3018dc0689f321a30286c4a5c7f344594836539a70fc6e45a5929a7e5"
INITIAL_DIRS = {
    "flash-v2", "ram-test", "install", "initial-park", "initial-recovery",
    "fault2-initial", "fault2-park", "fault2-prelaunch-recovery", "fault2-recovery",
    "fault2-run", "fault2-sbf", "fault7-park", "fault7-prepared", "fault7-recovery",
    "fault7-repeat", "fault7-repeat-park", "fault7-repeat-recovery", "fault7-repeat-sbf",
    "new-prefix-park", "new-prefix-recovery",
}
INITIAL_FILES = {
    "analyze_led_current.py", "led_current_trace.py", "launch_prepared.py", "run_fault.py",
    "rebuild-prefix.py", "install.py", "build-ram.log", "build-v1.log", "build-v2.log",
    "prefix-rebuild.log", "offline-tests.log", "fault7-current.jsonl",
    "fault7-current-analysis.json", "fault7-repeat-current.jsonl",
    "fault7-repeat-current-analysis.json", "fault7-ready.json", "fault7-repeat-ready.json",
}
BUILD_BINARY_NAMES = {
    "capture.bin", "stage1.bin", "stage1-unrelocated.bin", "stage1_boot.bin",
    "stage2.bin", "stage2-full.bin", "capture_sector_0.bin",
}
PENDING = [
    "Normal cold capture and complete saved-image verification with this installed image",
    "Error signal from the exact production ROM-loaded prefix, then UART recovery",
    "Final instrument closure and live bench checkpoint",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def identity(path):
    data = Path(path).read_bytes()
    return dict(bytes=len(data), sha256=digest(data))


def entries(folder):
    return [dict(path=p.relative_to(folder).as_posix(), **identity(p))
            for p in sorted(folder.rglob("*")) if p.is_file()
            and p != folder / "SHA256SUMS.json"]


def verify_hashes(folder):
    expected = read(folder / "SHA256SUMS.json")["files"]
    actual = entries(folder)
    expected_by_path = {v["path"]: v for v in expected}
    actual_by_path = {v["path"]: v for v in actual}
    require(len(expected) == len(expected_by_path) and actual_by_path == expected_by_path,
            "Missing, changed or extra files in " + str(folder))
    return dict(files=len(actual), bytes=sum(v["bytes"] for v in actual))


def selected(source, extra_dirs):
    for path in sorted(source.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(source)
        if len(rel.parts) == 1:
            if path.name in INITIAL_FILES or path.name in {
                "install.log", "new-prefix-park.log", "fault2-run.log", "fault2-sbf.log",
                "fault7-prepare.log", "fault7-repeat-prepare.log", "fault7-repeat-sbf.log"}:
                yield path
            continue
        if rel.parts[0] not in INITIAL_DIRS | set(extra_dirs):
            continue
        build = rel.parts[0] in {"flash-v2", "ram-test"}
        keep = path.suffix.lower() in {".json", ".jsonl", ".log", ".py"}
        keep |= build and (path.suffix.lower() in {".c", ".h", ".s", ".ld", ".inc", ".lst", ".map"}
                          or path.name in BUILD_BINARY_NAMES or path.name == "symbols.txt")
        # Only the known initial diagnostic directories contain approved binary
        # register/code dumps. Extra capture/readback directories retain proof
        # JSON and logs, never photo/RAM/SD payloads.
        keep |= not build and rel.parts[0] in INITIAL_DIRS and path.suffix.lower() == ".bin"
        if keep:
            yield path


def check_recovery(path, prefix):
    v = read(path)
    require(v["passed"] and v["prefix_sha256"] == prefix, "Recovery identity differs")
    require(v["context"]["PC"] == 0x3418078C and v["context"]["PRIMASK"] == 1
            and v["context"]["CONTROL"] == 0 and not v["ccr"] & 0x30000
            and not v["fpccr"] & 1, "Recovery context differs")
    pulse = v["vcp_status"]
    require(pulse["good_pulses"] >= 3 and pulse["bad_pulses"] == 0
            and pulse["request"] == 1 and pulse["source_bits"] & 2, "UART guard did not pass")
    return dict(prefix_sha256=prefix, good_pulses=pulse["good_pulses"], bad_pulses=0)


def check_sbf(path, prefix):
    v = read(path)
    require(v["passed"] and v["prefix_sha256"] == prefix and v["sbf"] is True
            and v["pdds"] is True and v["stopf"] is False
            and not v["reset_or_power_changed"] and not v["cpucr_written"], "Guarded flags differ")
    require(v["trial_entry_proven"] is False, "Do not strengthen the flag attribution")
    return dict(sbf=True, pdds=True, stopf=False, trial_entry_proven=False,
                interpretation=v["interpretation"])


def replay(snapshot, waveforms=True):
    src, review = snapshot / "inputs", snapshot / "review"
    result = dict(schema=1, qualification_complete=False, pending=PENDING, checks={})
    checks = result["checks"]
    for name, expected in (("flash-v2", NEW_RECEIVER), ("ram-test", RAM_BINARY)):
        build = src / name
        m = read(build / "manifest.json")
        require(identity(build / "capture.bin") == dict(bytes=m["binary_bytes"], sha256=expected)
                and m["binary_sha256"] == expected, name + " binary identity differs")
        require(m["error_blinks"] and m["sd_clock_hz"] == 25000000 and m["sd_bus_width"] == 4
                and m["sd_review_profile"] and m["sd_startup_opt"] and not m["raw_dma_tail_wait"],
                name + " selected profile differs")
        for filename, sha in m["source_hashes"].items():
            require(identity(build / filename)["sha256"] == sha, "Build source differs: " + filename)
        checks[name] = dict(binary_sha256=expected, source_files=len(m["source_hashes"]))
    m = read(src / "flash-v2/staged/manifest.json")
    prefix = (src / "flash-v2/staged/stage1.bin").read_bytes()
    sector = (src / "flash-v2/staged/capture_sector_0.bin").read_bytes()
    require(len(prefix) == m["stage1_raw_bytes"] == 6500 and digest(prefix) == m["stage1_raw_sha256"] == NEW_PREFIX,
            "Prefix identity differs")
    require(len(sector) == m["program_bytes"] == 65536 and digest(sector) == m["program_sha256"] == NEW_SECTOR,
            "Sector identity differs")
    early = (src / "flash-v2/staged/stage2.bin").read_bytes()
    require(len(early) == m["stage2_bytes"] == 15804 and digest(early) == m["stage2_sha256"], "Early receiver differs")
    old = (review / "old-prefix-objcopy.bin").read_bytes()
    require(len(old) == 5140 and digest(old) == OLD_PREFIX and prefix == (review / "new-prefix-objcopy.bin").read_bytes(),
            "Independent objcopy bytes differ")
    changed = [i for i, (a, b) in enumerate(zip(old, prefix)) if a != b]
    expected = list(range(0xE6, 0xEC)) + list(range(0xC9C, 0xCA0)) + list(range(0x1354, 0x1358))
    r = read(review / "prefix-review.json")
    require(changed == expected == [int(v, 16) for v in r["changed_offsets"]], "Unexpected prefix changes")
    for offset in r["recovery_literal_offsets"]:
        i = int(offset, 16)
        require(old[i:i+4] == prefix[i:i+4], "Recovery literal differs")
    require(r["passed"] and r["recovery_schema_identical"] and r["unchanged_disassembly_rows"] == 1782,
            "Independent review failed")
    checks["prefix_review"] = dict(prefix_sha256=NEW_PREFIX, bytes=6500, old_bytes=5140,
        early_receiver_bytes=15804, preserved_literals=len(r["recovery_literal_offsets"]), changed_offsets=r["changed_offsets"])
    allow = read(review / "allowlist-tests.json")
    require(allow["passed"] and allow["new_and_old_exact_pairs_pass"]
            and all(set(v.values()) == {"rejected"} for v in allow["negative_cases"].values()), "Exact allowlist regression")
    checks["exact_allowlists"] = allow
    install = src / "install"
    complete = read(install / "complete.json")
    require(complete["passed"] and complete["old_sector_sha256"] == OLD_SECTOR
            and complete["new_sector_sha256"] == NEW_SECTOR and complete["independent_full_readback"]
            and complete["following4096_unchanged"], "Install completion differs")
    for directory, expected_sha, count in (("nor-before", OLD_SECTOR, 65536), ("nor-after", NEW_SECTOR, 65536)):
        b = (install / directory / "readback.bin").read_bytes()
        v = read(install / directory / "verified.json")
        require(len(b) == count and digest(b) == expected_sha and v["sha256"] == expected_sha,
                "Physical NOR readback differs")
    require((install / "nor-after/readback.bin").read_bytes() == sector
            == (install / "write/readback.bin").read_bytes(), "Program/independent NOR bytes differ")
    following = (install / "following-before/readback.bin").read_bytes()
    require(len(following) == 4096 and following == (install / "following-after/readback.bin").read_bytes(),
            "Following NOR page changed")
    d = read(install / "completion-diagnostic/result.json")
    require(d["pending_operations"] == 0 and d["first_failure_result"] == 0, "NOR completion diagnostic failed")
    checks["installation"] = dict(sector_sha256=NEW_SECTOR, full_bytes_equal=65536,
        following_bytes_unchanged=4096, following_sha256=digest(following))
    for name, prefix_hash in (("fault2-park", OLD_PREFIX), ("fault7-repeat-park", OLD_PREFIX),
                              ("new-prefix-park", NEW_PREFIX)):
        checks[name] = check_recovery(src / name / "result.json", prefix_hash)
    for name in ("fault2-sbf", "fault7-repeat-sbf"):
        checks[name] = check_sbf(src / name / "result.json", OLD_PREFIX)
    for name, code in (("fault2-run", 2), ("fault7-repeat", 7)):
        v = read(src / name / "launch.json")
        require(v["binary_sha256"] == RAM_BINARY and v["code"] == code
                and v["expected_ms"] == 2500*code+6400 and not v["nor_write"] and not v["sd_write"],
                "Synthetic fault launch differs")
    error = read(src / "fault2-run/active-error.json")
    require(error["result"] == 257 and error["media_idle"] == 0 and error["terminal"] == 0,
            "Error test was incorrectly labeled successful/idle")
    checks["ram_fault_scope"] = dict(codes=[2, 7], synthetic=True, no_sd_or_nor_writes=True,
        storage_idle_not_claimed=True, production_prefix_error_pending=True)
    if waveforms:
        spec = importlib.util.spec_from_file_location("frozen_error_current_analysis", src / "analyze_led_current.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    for name, full in (("fault7-current", False), ("fault7-repeat-current", True)):
        saved = read(src / (name + "-analysis.json"))
        trace = src / (name + ".jsonl")
        require(identity(trace) == dict(bytes=saved["source_bytes"], sha256=saved["source_sha256"]), "Trace hash differs")
        require(saved["complete_pattern_observed"] is full and saved["whole_session_ok"] is False,
                "Partial pattern or startup NaN limitation was lost")
        if waveforms:
            actual = module.analyze(trace, saved["launch_host_utc"], 7)
            actual.pop("source"); expected_analysis = dict(saved); expected_analysis.pop("source")
            require(actual == expected_analysis, "Current analysis does not replay exactly: " + name)
        checks[name] = {k: saved[k] for k in ("complete_pattern_observed", "measured", "timing_consistency",
            "low_current_plateau", "whole_session_ok", "fault_window_nonfinite_current", "fault_window_nonfinite_voltage", "limits")}
    result["waveforms_recomputed"] = waveforms
    return result


def seal(folder):
    for snapshot in sorted((folder / "snapshots").iterdir()):
        if snapshot.is_dir():
            verify_hashes(snapshot)
    write(folder / "SHA256SUMS.json", dict(schema=1, files=entries(folder)))
    return verify_hashes(folder)


def snapshot(source, review, out, name, extra_dirs):
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]*", name), "Invalid snapshot name")
    target = out / "snapshots" / name
    require(not target.exists(), "Refusing to overwrite an immutable snapshot")
    target.mkdir(parents=True)
    copies = []
    for label, files, base in (("inputs", selected(source, extra_dirs), source),
                               ("review", (p for p in sorted(review.iterdir()) if p.suffix in {".bin", ".json", ".lst"}), review)):
        for p in files:
            before = identity(p)
            dest = target / label / p.relative_to(base)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            require(identity(p) == before == identity(dest), "Source changed while copying: " + str(p))
            copies.append(dict(source=str(p.resolve()), path=dest.relative_to(target).as_posix(), **before))
    write(target / "source-copies.json", copies)
    summary = replay(target)
    summary["created_utc"] = datetime.now(timezone.utc).isoformat()
    summary["source"] = str(source.resolve())
    summary["review_source"] = str(review.resolve())
    write(target / "summary.json", summary)
    write(target / "SHA256SUMS.json", dict(schema=1, files=entries(target)))
    return dict(snapshot=name, qualification_complete=False, pending=PENDING, **seal(out))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("snapshot", "verify", "seal", "inspect"))
    p.add_argument("--out", type=Path, default=HERE)
    p.add_argument("--source", type=Path)
    p.add_argument("--review", type=Path)
    p.add_argument("--name", default="initial")
    p.add_argument("--extra-dir", action="append", default=[])
    a = p.parse_args()
    if a.action == "snapshot":
        require(a.source and a.review, "snapshot requires --source and --review")
        result = snapshot(a.source, a.review, a.out, a.name, a.extra_dir)
    elif a.action == "inspect":
        target = a.out / "snapshots" / a.name
        if read(target / "summary.json").get("kind") in {"qualification-addendum", "closure-addendum"}:
            from qualification import replay as qualified_replay, replay_closure
            result = (replay_closure if read(target / "summary.json")["kind"] == "closure-addendum" else qualified_replay)(target)
        else:
            result = replay(target)
    elif a.action == "seal":
        result = seal(a.out)
    else:
        result = verify_hashes(a.out)
        result["snapshots"] = {}
        for path in sorted((a.out / "snapshots").iterdir()):
            if path.is_dir():
                verify_hashes(path)
                saved = read(path / "summary.json")
                if saved.get("kind") in {"qualification-addendum", "closure-addendum"}:
                    from qualification import replay as qualified_replay, replay_closure
                    fresh = (replay_closure if saved["kind"] == "closure-addendum" else qualified_replay)(path)
                else:
                    fresh = replay(path)
                require(all(saved[k] == v for k, v in fresh.items()), "Saved summary differs from offline replay")
                result["snapshots"][path.name] = dict(qualification_complete=fresh["qualification_complete"],
                    checks=len(fresh["checks"]), waveform_replay=fresh["waveforms_recomputed"], pending=fresh["pending"])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
