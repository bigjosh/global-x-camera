"""Collect an explicit, completed boot matrix offline; never accesses hardware.

Usage: python firmware/boot-timing/experiments/collect_matrix_evidence.py \
  --manifest tmp/bringup/matrix-collection.json \
  --out firmware/boot-timing/evidence/matrix-20261017

Manifest example (paths are repository-relative unless absolute):
{
  "schema_version": 1,
  "source_root": "tmp/bringup",
  "captures": ["opt-matrix-baseline-01", "opt-matrix-plus8k-01"],
  "program_trials": ["nor-program-plus8k-01"],
  "guard_trials": [{"name": "nor-guard-after-baseline-03",
    "before": "tmp/bringup/rom-nor-maintenance-readonly-20261017/following-sector-before.bin"}],
  "analysis": "tmp/bringup/opt-matrix-analysis.json",
  "chart_provenance": "firmware/boot-timing/assets/opt-payload-size-matrix.provenance.json"
}

Guard trials and chart provenance may be omitted. When charts are requested,
their sidecar must bind the current chart bytes to the passed final analysis.
The analysis must contain exactly the listed captures, all passed. No directory
scan selects runs. Known compact files are copied byte-for-byte; large raw
captures and ALL NOR content buffers remain local with size/SHA-256 provenance.
Destination must be new. Failure leaves an explicitly incomplete staging folder
instead of publishing a partial evidence directory. Run only after capture,
programming, analysis and plotting have finished.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

REPO = Path(__file__).resolve().parents[3]
COMPACT_LIMIT = 2 * 1024 * 1024
CAPTURE_FILES = (
    "capture-config.json", "cycle-outcome.json", "independent-review.json",
    "digital.csv", "cycle-log.jsonl", "boot-summary.json", "started", "stop",
    "rom-read/calls.jsonl", "rom-read/cli-01.log", "rom-read/cli-02.log",
    "rom-read/secure-trace.bin", "rom-read/nonsecure-trace.bin", "rom-read/events.json",
)
TRIAL_FILES = ("calls.jsonl", "request.json", "command.bin", "clear-status.bin",
               "status.json", "status.bin", "verified.json")
TRIAL_PATTERN = re.compile(r"(?:cli-\d{2}(?:-timeout)?\.log|status-\d{2}\.bin)\Z")
SOURCE_SCRIPTS = (
    "firmware/boot-timing/experiments/analyze_matrix.py",
    "firmware/boot-timing/experiments/plot_matrix.py",
    "firmware/boot-timing/experiments/collect_matrix_evidence.py",
    "firmware/boot-timing/nor_bench.py",
    "firmware/boot-timing/inspect_cycle.py",
    "firmware/boot-timing/experiments/rom-trace/compare_phases.py",
    "tmp/bringup/read_rom_traces.py",
    "tmp/bringup/read_nor_guard.py",
    "tmp/bringup/final_debug_access.py",
    "tmp/bringup/verify_final_power.py",
)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def resolve_in_repo(repo, value):
    path = Path(value)
    path = (path if path.is_absolute() else repo / path).resolve()
    if not path.is_relative_to(repo):
        raise ValueError(f"Source/destination must stay in the repository: {path}")
    return path


def attributes(path):
    if os.name != "nt":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
    kernel.GetFileAttributesW.restype = ctypes.c_uint32
    result = kernel.GetFileAttributesW(str(path))
    if result == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def set_attributes(path, value):
    if value is None:
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.SetFileAttributesW.restype = ctypes.c_int
    if not kernel.SetFileAttributesW(str(path), value):
        raise ctypes.WinError(ctypes.get_last_error())


def stamp(path):
    value = path.stat()
    return value.st_size, value.st_mtime_ns


def identity(path, repo):
    before = stamp(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if stamp(path) != before:
        raise RuntimeError(f"Source changed while hashing: {path}")
    return {"path": path.relative_to(repo).as_posix(), "bytes": before[0],
            "sha256": digest.hexdigest(), "mtime_ns": before[1],
            "windows_attributes": attributes(path)}


class Plan:
    def __init__(self, repo):
        self.repo = repo
        self.sources = {}
        self.copies = {}
        self.local = {}
        self.guards = []

    def source(self, value):
        path = resolve_in_repo(self.repo, value)
        if path not in self.sources:
            if not path.is_file():
                raise FileNotFoundError(path)
            self.sources[path] = identity(path, self.repo)
        return path, self.sources[path]

    def json(self, value):
        path, info = self.source(value)
        if info["bytes"] > COMPACT_LIMIT:
            raise ValueError(f"Unexpectedly large compact JSON: {path}")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise RuntimeError(f"Source changed before JSON read: {path}")
        return json.loads(data.decode("utf-8-sig"))

    def copy(self, value, destination):
        path, info = self.source(value)
        if info["bytes"] > COMPACT_LIMIT:
            raise ValueError(f"Refusing oversized compact artifact: {path}")
        destination = Path(destination)
        if destination.is_absolute() or ".." in destination.parts:
            raise ValueError(f"Invalid destination: {destination}")
        previous = self.copies.get(destination)
        if previous is not None and previous != path:
            raise ValueError(f"Copy destination collision: {destination}")
        self.copies[destination] = path
        return info

    def local_only(self, value, role):
        path, info = self.source(value)
        entry = self.local.setdefault(path, {**info, "roles": []})
        if role not in entry["roles"]:
            entry["roles"].append(role)
        return info


def named(values, prefix):
    if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
        raise ValueError("Run names must be an explicit string list")
    if len(set(values)) != len(values):
        raise ValueError("Duplicate run names")
    if any(not re.fullmatch(re.escape(prefix) + r"[a-z0-9-]+", x) for x in values):
        raise ValueError(f"Invalid run name; expected {prefix}...")
    return values


def trial_files(plan, folder, relative):
    selected = list(TRIAL_FILES)
    # The run itself was explicitly selected; only these small log/status names
    # can be selected inside it. No recursive glob or NOR content file copying.
    selected.extend(path.name for path in folder.iterdir()
                    if path.is_file() and TRIAL_PATTERN.fullmatch(path.name))
    for name in sorted(set(selected)):
        path = folder / name
        if path.is_file():
            plan.copy(path, relative / name)


def prepare(repo, manifest_path):
    plan = Plan(repo)
    manifest = plan.json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("Expected collection manifest schema_version 1")
    source_root = resolve_in_repo(repo, manifest.get("source_root", "tmp/bringup"))
    captures = named(manifest.get("captures"), "opt-matrix-")
    trials = named(manifest.get("program_trials", []), "nor-program-")
    if not captures:
        raise ValueError("At least one explicit capture is required")
    plan.copy(manifest_path, "selection.json")
    analysis_path = resolve_in_repo(repo, manifest["analysis"])
    analysis = plan.json(analysis_path)
    runs = analysis.get("runs", [])
    if analysis.get("passed") is not True or not runs or any(run.get("passed") is not True for run in runs):
        raise ValueError("Final analysis must report every run passed")
    run_paths = [resolve_in_repo(repo, run["folder"]) for run in runs]
    expected_paths = [resolve_in_repo(repo, source_root / name) for name in captures]
    if len(run_paths) != len(expected_paths) or set(run_paths) != set(expected_paths):
        raise ValueError("Final analysis does not contain exactly the selected captures")
    if len({run.get("label") for run in runs}) != len(runs):
        raise ValueError("Analysis contains duplicate labels")
    plan.copy(analysis_path, "analysis/matrix-analysis.json")

    for name, folder in zip(captures, expected_paths):
        outcome = plan.json(folder / "cycle-outcome.json")
        review = plan.json(folder / "independent-review.json")
        if outcome.get("passed") is not True or review.get("passed") is not True:
            raise ValueError(f"Capture has not passed: {name}")
        if any(outcome.get(field) != 0 for field in
               ("cycle_returncode", "capture_returncode", "inspection_returncode")):
            raise ValueError(f"Capture did not complete successfully: {name}")
        for required in ("capture-config.json", "digital.csv", "cycle-log.jsonl"):
            plan.source(folder / required)
        for filename in CAPTURE_FILES:
            path = folder / filename
            if path.is_file():
                plan.copy(path, Path("captures") / name / filename)
        for filename in ("analog.csv", "boot.sal"):
            info = plan.local_only(folder / filename, f"{name}: large raw capture")
            if info["bytes"] == 0:
                raise ValueError(f"Empty raw capture: {name}/{filename}")
        matching_run = next(run for run, path in zip(runs, run_paths) if path == folder)
        if matching_run.get("independent_review_sha256") != plan.source(folder / "independent-review.json")[1]["sha256"]:
            raise ValueError(f"Analysis review hash is stale: {name}")

    for name in trials:
        folder = resolve_in_repo(repo, source_root / name)
        request = plan.json(folder / "request.json")
        status = plan.json(folder / "status.json")
        verified = plan.json(folder / "verified.json")
        if status.get("result") != 0 or status.get("magic") != 0x444F4E45:
            raise ValueError(f"Programming trial did not finish successfully: {name}")
        if status.get("flags", 0) & 16 or status.get("flags", 0) & 7 != 7:
            raise ValueError(f"Programming trial has uncertain final state: {name}")
        if verified.get("byte_for_byte_match") is not True or verified.get("bytes") != 65536:
            raise ValueError(f"Programming trial lacks full readback verification: {name}")
        if request.get("sequence") != status.get("sequence") or status.get("command") != 3:
            raise ValueError(f"Programming request/status mismatch: {name}")
        readback = plan.local_only(folder / "readback.bin", f"{name}: full NOR readback")
        if readback["bytes"] != 65536 or readback["sha256"] != verified.get("sha256") or readback["sha256"] != request.get("desired_sha256"):
            raise ValueError(f"Programming readback hash mismatch: {name}")
        for role in ("current", "desired"):
            info = plan.local_only(request[f"{role}_source"], f"{name}: {role} NOR image")
            if info["bytes"] != 65536 or info["sha256"] != request.get(f"{role}_sha256"):
                raise ValueError(f"Programming input hash mismatch: {name}/{role}")
        trial_files(plan, folder, Path("program-trials") / name)

    guards = manifest.get("guard_trials", [])
    guard_names = named([guard["name"] for guard in guards], "nor-guard-")
    for guard, name in zip(guards, guard_names):
        folder = resolve_in_repo(repo, source_root / name)
        status = plan.json(folder / "status.json")
        before = plan.local_only(guard["before"], f"{name}: guard before programming")
        after = plan.local_only(folder / "following-sector.bin", f"{name}: guard after programming")
        if status.get("result") != 0 or status.get("magic") != 0x444F4E45 or status.get("read_count") != 4096 or status.get("flash_offset") != 65536:
            raise ValueError(f"Invalid guard-read completion: {name}")
        if before["bytes"] != 4096 or after["bytes"] != 4096 or before["sha256"] != after["sha256"]:
            raise ValueError(f"Guard content changed: {name}")
        if resolve_in_repo(repo, guard["before"]).read_bytes() != (folder / "following-sector.bin").read_bytes():
            raise ValueError(f"Guard byte comparison failed: {name}")
        plan.guards.append({"trial": name, "matches": True, "comparison": "byte-for-byte",
                            "flash_start": "0x00010000", "bytes": 4096,
                            "before": before, "after": after,
                            "limit": "Only the immediately following 4 KiB was compared."})
        trial_files(plan, folder, Path("guard-trials") / name)

    if manifest.get("chart_provenance"):
        sidecar_path = resolve_in_repo(repo, manifest["chart_provenance"])
        sidecar = plan.json(sidecar_path)
        if sidecar["analysis"]["sha256"] != plan.source(analysis_path)[1]["sha256"]:
            raise ValueError("Chart provenance references a different analysis")
        if resolve_in_repo(repo, sidecar["analysis"]["path"]) != analysis_path:
            raise ValueError("Chart analysis path mismatch")
        if set(sidecar.get("plotted_labels", [])) != {run["label"] for run in runs} or sidecar.get("omitted_labels"):
            raise ValueError("Chart provenance does not cover all passed runs")
        plan.copy(sidecar_path, "analysis/chart-provenance.json")
        if not sidecar.get("outputs"):
            raise ValueError("Chart provenance has no outputs")
        for record in sidecar["outputs"]:
            path, info = plan.source(record["path"])
            if path.suffix.lower() not in (".png", ".svg") or info["sha256"] != record["sha256"] or info["bytes"] != record["bytes"]:
                raise ValueError(f"Chart identity mismatch: {path}")
            plan.copy(path, Path("analysis/charts") / path.name)
        for key in ("plot_script", "analysis_script"):
            record = sidecar[key]
            path, info = plan.source(record["path"])
            if info["sha256"] != record["sha256"] or info["bytes"] != record["bytes"]:
                raise ValueError(f"Chart source identity mismatch: {path}")
            plan.copy(path, Path("source") / path.name)
    for value in manifest.get("decoded_rom", []):
        path = resolve_in_repo(repo, value)
        if path.parent != source_root / "matrix-rom-analysis" or path.suffix != ".json":
            raise ValueError(f"Unexpected decoded ROM summary path: {path}")
        plan.json(path)
        plan.copy(path, Path("analysis/decoded-rom") / path.name)
    final_state = manifest.get("final_state", {})
    if final_state.get("powered"):
        name = named([final_state["powered"]], "opt-final-")[0]
        folder = resolve_in_repo(repo, source_root / name)
        state = plan.json(folder / "powered-state.json")
        if state.get("passed") is not True or state.get("no_power_or_debug_stimulus_in_verification") is not True:
            raise ValueError("Final powered-state verification did not pass")
        for filename in ("powered-state.json", "boot-summary.json", "capture-config.json", "digital.csv", "started"):
            plan.copy(folder / filename, Path("final-state/powered") / filename)
        for filename in ("analog.csv", "boot.sal"):
            info = plan.local_only(folder / filename, "final powered-state raw capture")
            record = state["files"][filename]
            if info["bytes"] != record["bytes"] or info["sha256"] != record["sha256"]:
                raise ValueError(f"Final powered-state source mismatch: {filename}")
    if final_state.get("debug"):
        name = named([final_state["debug"]], "opt-final-")[0]
        folder = resolve_in_repo(repo, source_root / name)
        state = plan.json(folder / "status.json")
        if state.get("debug_marker_record_verified") is not True or state.get("no_halt_or_reset") is not True:
            raise ValueError("Final non-halting debug verification did not pass")
        for filename in ("status.json", "calls.jsonl", "cli-01.log", "debug-status.bin"):
            plan.copy(folder / filename, Path("final-state/debug") / filename)
    for filename in SOURCE_SCRIPTS:
        path = repo / filename
        if path.is_file():
            plan.copy(path, Path("source") / path.name)
    return plan, manifest


def collect(repo, manifest_path, output):
    repo = repo.resolve()
    manifest_path = resolve_in_repo(repo, manifest_path)
    output = resolve_in_repo(repo, output)
    if output.exists():
        raise FileExistsError(f"Evidence destination must be new: {output}")
    plan, selection = prepare(repo, manifest_path)
    source_root = resolve_in_repo(repo, selection.get("source_root", "tmp/bringup"))
    if output.is_relative_to(source_root) or any(path.is_relative_to(output) for path in plan.sources):
        raise ValueError("Evidence destination overlaps selected source files")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(output.name + ".incomplete-" + uuid.uuid4().hex[:8])
    stage.mkdir()
    copied = []
    try:
        (stage / ".gitattributes").write_bytes(b"* -text -whitespace\n")
        for relative, source in plan.copies.items():
            expected = plan.sources[source]
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            set_attributes(target, expected["windows_attributes"])
            actual = identity(target, repo)
            for field in ("sha256", "bytes", "mtime_ns", "windows_attributes"):
                if actual[field] != expected[field]:
                    raise RuntimeError(f"Source changed or copy mismatch: {source} ({field})")
            copied.append({"copy": relative.as_posix(), "source": expected})
        for path, expected in plan.sources.items():
            if stamp(path) != (expected["bytes"], expected["mtime_ns"]):
                raise RuntimeError(f"Source changed during collection: {path}")
        provenance = {"schema_version": 1, "complete": True, "collected_utc": utc_now(),
                      "hardware_access": False, "captures": selection["captures"],
                      "program_trials": selection.get("program_trials", []),
                      "copied_artifacts": copied, "local_only_artifacts": list(plan.local.values()),
                      "guard_comparisons": plan.guards,
                      "raw_copy_integrity": "SHA256/size/mtime/Windows-attributes checked",
                      "limits": ["Capture analysis is supplied, not recomputed by this collector.",
                                 "All raw NOR content, analog.csv and boot.sal remain local.",
                                 "Hashes identify retained large files; their contents are not embedded.",
                                 "A passed programming trial does not establish power-loss recovery."]}
        (stage / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)
    except Exception as exc:
        (stage / "COLLECTION_FAILED.json").write_text(json.dumps({"complete": False,
            "failed_utc": utc_now(), "error": repr(exc)}, indent=2) + "\n", encoding="utf-8")
        raise
    return {"destination": str(output), "copied_files": len(copied),
            "copied_bytes": sum(item["source"]["bytes"] for item in copied),
            "local_only_files": len(plan.local), "captures": len(selection["captures"]),
            "program_trials": len(selection.get("program_trials", [])),
            "guard_trials": len(plan.guards), "hardware_access": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    args = parser.parse_args()
    print(json.dumps(collect(args.repo_root, args.manifest, args.out), indent=2))


if __name__ == "__main__":
    main()
