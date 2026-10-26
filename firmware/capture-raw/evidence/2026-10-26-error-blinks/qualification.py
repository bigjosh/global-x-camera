"""Offline final-test addendum. Photos are checked locally and never copied.

Run `python -B qualification.py --source <private error-blinks directory>`
only after the named tests are complete. The new snapshot cannot overwrite
an existing one; initial evidence and its pending conclusions stay immutable.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil

import archive as a

DIRS = {"normal-cold", "pre-slot50", "pre-headers", "standby-recover",
        "standby-park", "standby-flag", "standby-read-start", "standby-readback",
        "prefix-complete", "prefix-complete-recover", "prefix-after-recover",
        "prefix-after-park", "prefix-after-sbf"}
FILES = {"cold.py", "read_flash_image.py", "prefix_fault.py",
         "prefix-complete-current.jsonl", "prefix-complete-current-analysis.json",
         "prefix-complete-current-ready.json", "final-offline-tests.log"}
READER = "30c6a539a506a1b5ec963c382f190987aef6f8f68a0baa2e533c70a1a651b866"


def private_image(source):
    import numpy as np
    from PIL import Image
    folder = source / "standby-readback"
    v = a.read(folder / "readback-validation.json")
    slot = (folder / "slot.bin").read_bytes()
    raw = (folder / "frame.bin").read_bytes()
    png = (folder / "scene.png").read_bytes()
    a.require(len(slot) == 3730*512 and len(raw) == 1909600
              and slot[:4] == b"GXR2" and slot[-4:] == b"GXRE"
              and slot[156:-4] == raw and slot[4:156] == bytes(152), "Private slot structure differs")
    a.require(a.digest(slot) == v["slot_sha256"] and a.digest(raw) == v["raw_sha256"]
              and a.digest(png) == v["png_sha256"], "Private image identity differs")
    b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 5).astype(np.uint16)
    samples = np.empty((len(b), 4), dtype=np.uint16)
    for i in range(4):
        samples[:, i] = (b[:, i] << 2) | ((b[:, 4] >> (2*i)) & 3)
    samples = samples.reshape(1364, 1120)
    decoded = np.asarray(Image.open(folder / "scene.png"), dtype=np.uint16)
    a.require(np.array_equal(decoded, samples << 6), "PNG samples differ from packed RAW10")
    pieces = []
    for p in sorted(folder.glob("payload-*/verified.json"), key=lambda p: int(p.parent.name.split("-")[1])):
        proof = a.read(p)
        data = (p.parent / "sectors.bin").read_bytes()
        a.require(a.digest(data) == proof["read_sha256"] and len(data) == proof["proof"]["read_count"]*512,
                  "Private read chunk differs")
        pieces.append(data)
    a.require(b"".join(pieces) == slot, "Complete card read chunks differ from slot image")
    return dict(passed=True, slot=51, bytes=len(raw), slot_bytes=len(slot),
        raw_sha256=a.digest(raw), slot_sha256=a.digest(slot), png_sha256=a.digest(png),
        complete_card_chunks_equal_slot=True, independent_png_samples_equal_raw10_shift6=True,
        all_152_metadata_bytes_zero=True, original_camera_ram_comparison=False,
        minimum_sample=int(samples.min()), maximum_sample=int(samples.max()),
        checked_utc=datetime.now(timezone.utc).isoformat(),
        scope="Local private-byte comparison; public replay validates proofs and hashes, not missing photo pixels")


def replay(snapshot):
    source = snapshot / "inputs"
    initial = snapshot.parent / "initial"
    binding = a.read(snapshot / "initial-binding.json")
    a.require(a.identity(initial / "SHA256SUMS.json") == binding, "Initial immutable snapshot binding differs")
    result = dict(schema=1, kind="qualification-addendum", qualification_complete=False,
                  pending=["Final instrument closure and live bench checkpoint"], checks={})
    checks = result["checks"]
    proof = a.read(source / "normal-cold/boot-proof.json")
    a.require(proof["cold_boot_confirmed"] and proof["binary_sha256"] == a.NEW_RECEIVER
              and proof["sector_sha256"] == a.NEW_SECTOR and proof["no_debugger_or_uart_during_boot"],
              "Normal cold boot identity differs")
    events = a.read(source / "normal-cold/events.json")
    a.require([v["name"] for v in events] == ["before", "off", "measured_off", "off_15s", "on", "completion_signature"],
              "Cold event sequence differs")
    e = {v["name"]: v for v in events}
    for name in ("measured_off", "off_15s"):
        r = e[name]["response"]
        a.require(r["ok"] and r["range"] == 0 and abs(r["statistics"]["current"]["avg"]) < 1e-5,
                  "Cold power-off observation differs")
    a.require((datetime.fromisoformat(e["on"]["utc"]) - datetime.fromisoformat(e["off"]["utc"])).total_seconds() >= 15,
              "Cold off period shorter than 15 seconds")
    stats = e["completion_signature"]["response"]["statistics"]
    a.require(.007 < stats["current"]["avg"] < .01, "Normal completion signature differs")
    checks["normal_cold"] = dict(receiver_sha256=a.NEW_RECEIVER, sector_sha256=a.NEW_SECTOR,
        completion_current_mA=1000*stats["current"]["avg"],
        completion_voltage_V=stats["voltage"]["avg"], individual_target_rails_probed=False)
    pre = a.read(source / "pre-headers/summary.json")
    a.require(pre["passed"] and pre["layout"]["erased_byte"] == 0, "Pre-capture header proof differs")
    slot51 = next(v for v in pre["slots"] if v["slot"] == 51)
    a.require(slot51["header"]["state"] == "FREE" and slot51["data"]["sha256"] == a.digest(bytes(512)),
              "Slot51 was not entirely erased before capture")
    v = a.read(source / "pre-headers/slot-51/verified.json")
    a.require(v["passed"] and v["read_sha256"] == slot51["data"]["sha256"]
              and v["proof"]["read_lba"] == 51*3730 and v["proof"]["read_count"] == 1,
              "Pre-header operation extent differs")
    checks["new_slot_attribution"] = dict(slot=51, first_sector_erased=True,
        preceding_slot50_not_claimed=True, first_sector_sha256=slot51["data"]["sha256"])
    validation = a.read(source / "standby-readback/readback-validation.json")
    private = a.read(snapshot / "private-image-check.json")
    a.require(validation["passed"] and validation["slot"] == 51 and validation["full_slot_read"]
              and validation["png_samples_match_read_raw"] and validation["start_magic_valid"]
              and validation["completion_marker_valid"] and validation["original_sensor_frame_comparison"] is False,
              "Saved-image validation scope differs")
    a.require(private["passed"] and private["original_camera_ram_comparison"] is False
              and private["complete_card_chunks_equal_slot"]
              and private["independent_png_samples_equal_raw10_shift6"], "Private check did not pass")
    for field in ("raw_sha256", "slot_sha256", "png_sha256", "minimum_sample", "maximum_sample"):
        a.require(private[field] == validation[field], "Image check binding differs: " + field)
    count = 0
    for p in sorted((source / "standby-readback").glob("payload-*/verified.json"),
                    key=lambda p: int(p.parent.name.split("-")[1])):
        record = a.read(p); r, card = record["proof"], record["card"]
        a.require(record["passed"] and record["binary_sha256"] == READER
                  and r["operation"] == 3 and r["read_lba"] == 51*3730+count
                  and r["read_bytes"] == r["read_count"]*512 and r["clock_hz"] == 25000000,
                  "Read extent/profile differs")
        a.require(all(r[k] == 0 for k in ("result", "sd_error", "cleanup_error", "initialized", "controller_owned"))
                  and r["media_idle"] == 1 and all(card[k] == 0 for k in ("error", "error_sta", "cleanup_error"))
                  and card["bus_width_proof"]["negotiated_width"] == 4, "Read operation retained an error")
        count += r["read_count"]
    a.require(count == 3730, "Card read did not cover the complete slot")
    checks["normal_saved_image"] = private
    checks["normal_uart_recovery"] = a.check_recovery(source / "standby-park/result.json", a.NEW_PREFIX)
    checks["normal_guarded_flags"] = a.check_sbf(source / "standby-flag/result.json", a.NEW_PREFIX)
    plan = a.read(source / "prefix-complete/plan.json")
    a.require(plan["prefix_sha256"] == a.NEW_PREFIX and plan["code"] == 2
              and plan["entry"] == 0x34181821 and plan["nominal_ms"] == 11400
              and not plan["sd_write"] and not plan["nor_write"], "Prefix injection plan differs")
    for sub in ("prepare", "launch"):
        a.require(a.identity(source / "prefix-complete" / sub / "prefix.bin") == dict(bytes=6500, sha256=a.NEW_PREFIX),
                  "Exact live production prefix differs")
    a.require((source / "prefix-complete/launch/result.bin").read_bytes() == bytes([17, 0, 0, 0]),
              "Synthetic stage1 result differs")
    checks["production_prefix_injection"] = dict(code=2, entry="0x34181821", prefix_sha256=a.NEW_PREFIX,
        synthetic=True, injection="Stage1 result17 then direct debugger entry at the installed failure bridge",
        real_camera_failure_tested=False, sd_or_nor_write=False)
    saved = a.read(source / "prefix-complete-current-analysis.json")
    trace = source / "prefix-complete-current.jsonl"
    a.require(a.identity(trace) == dict(bytes=saved["source_bytes"], sha256=saved["source_sha256"]), "Prefix current trace differs")
    spec = importlib.util.spec_from_file_location("frozen_prefix_current_analysis", initial / "inputs/analyze_led_current.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    fresh = module.analyze(trace, saved["launch_host_utc"], 2)
    fresh.pop("source"); saved_replay = dict(saved); saved_replay.pop("source")
    a.require(fresh == saved_replay and saved["complete_pattern_observed"]
              and saved["measured"]["groups"] == [2]*5 and saved["whole_session_ok"] is False,
              "Production-prefix current analysis did not replay")
    checks["production_prefix_pattern"] = {k: saved[k] for k in ("complete_pattern_observed", "measured",
        "timing_consistency", "low_current_plateau", "whole_session_ok", "limits")}
    checks["production_prefix_uart_recovery"] = a.check_recovery(source / "prefix-after-park/result.json", a.NEW_PREFIX)
    checks["production_prefix_guarded_flags"] = a.check_sbf(source / "prefix-after-sbf/result.json", a.NEW_PREFIX)
    result["waveforms_recomputed"] = True
    return result


def collect(source, out):
    target = out / "snapshots/qualification"
    a.require(not target.exists(), "Refusing to overwrite the immutable qualification addendum")
    pixels = private_image(source)
    target.mkdir(parents=True)
    copies = []
    for p in sorted(source.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(source)
        keep = len(rel.parts) == 1 and (p.name in FILES or p.name.startswith(("normal-cold", "standby-", "prefix-complete", "prefix-after")) and p.suffix == ".log")
        keep |= len(rel.parts) > 1 and rel.parts[0] in DIRS and p.suffix.lower() in {".json", ".jsonl", ".log"}
        keep |= rel.as_posix() in {"prefix-complete/prepare/prefix.bin", "prefix-complete/launch/prefix.bin",
                                  "prefix-complete/launch/result.bin"}
        if not keep:
            continue
        before = a.identity(p); dest = target / "inputs" / rel
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
        a.require(a.identity(p) == before == a.identity(dest), "Source changed while copying: " + str(p))
        copies.append(dict(source=str(p.resolve()), path=dest.relative_to(target).as_posix(), **before))
    a.write(target / "source-copies.json", copies)
    a.write(target / "private-image-check.json", pixels)
    a.write(target / "initial-binding.json", a.identity(out / "snapshots/initial/SHA256SUMS.json"))
    summary = replay(target)
    summary["created_utc"] = datetime.now(timezone.utc).isoformat()
    a.write(target / "summary.json", summary)
    a.write(target / "SHA256SUMS.json", dict(schema=1, files=a.entries(target)))
    return dict(snapshot="qualification", qualification_complete=False, pending=summary["pending"], **a.seal(out))


def replay_closure(snapshot):
    source = snapshot / "inputs"
    bindings = a.read(snapshot / "snapshot-bindings.json")
    for name in ("initial", "qualification"):
        a.require(a.identity(snapshot.parent / name / "SHA256SUMS.json") == bindings[name],
                  "Previous immutable snapshot binding differs")
    result = dict(schema=1, kind="closure-addendum", qualification_complete=True, pending=[], checks={})
    checks = result["checks"]
    plan = a.read(source / "prefix-interrupt/plan.json")
    launch = a.read(source / "prefix-interrupt/run-event.json")
    request = a.read(source / "prefix-interrupt/recovery-request.json")
    delta = (datetime.fromisoformat(request["requested_utc"]) - datetime.fromisoformat(launch["before_run"])).total_seconds()
    a.require(plan["prefix_sha256"] == a.NEW_PREFIX and plan["code"] == 2
              and plan["entry"] == 0x34181821 and request["no_storage_transaction"]
              and delta == request["seconds_after_before_run"] and 0 < delta < request["nominal_sequence_s"] == 11.4,
              "Recovery request was not during the nominal error sequence")
    for sub in ("prepare", "launch"):
        a.require(a.identity(source / "prefix-interrupt" / sub / "prefix.bin") == dict(bytes=6500, sha256=a.NEW_PREFIX),
                  "Interrupted test did not use the exact live prefix")
    checks["recovery_during_error"] = a.check_recovery(source / "prefix-interrupt-park/result.json", a.NEW_PREFIX)
    checks["recovery_during_error"]["request_after_start_s"] = delta
    uart = a.read(source / "prefix-interrupt-recover/uart-events.json")
    a.require([v["event"] for v in uart] == ["opened", "break_on", "break_off", "stimulus_complete", "closed"],
              "UART recovery event sequence differs")
    initial = snapshot.parent / "initial/inputs"
    after = (source / "final-nor/nor-after/readback.bin").read_bytes()
    following = (source / "final-nor/following-after/readback.bin").read_bytes()
    a.require(len(after) == 65536 and a.digest(after) == a.NEW_SECTOR
              and following == (initial / "install/following-before/readback.bin").read_bytes(),
              "Final physical NOR or adjacent bytes changed")
    checks["final_physical_nor"] = dict(sector_sha256=a.NEW_SECTOR, bytes=65536, following_4096_unchanged=True)
    checks["fresh_park_before_final_cold"] = a.check_recovery(source / "final-cold/park/result.json", a.NEW_PREFIX)
    proof = a.read(source / "final-cold/boot-proof.json")
    a.require(proof["cold_boot_confirmed"] and proof["binary_sha256"] == a.NEW_RECEIVER
              and proof["sector_sha256"] == a.NEW_SECTOR and proof["no_debugger_or_uart_during_boot"],
              "Final cold boot identity differs")
    events = {v["name"]: v for v in a.read(source / "final-cold/events.json")}
    for name in ("measured_off", "off_15s"):
        r = events[name]["response"]
        a.require(r["ok"] and r["range"] == 0 and abs(r["statistics"]["current"]["avg"]) < 1e-5,
                  "Final cold off state not established")
    a.require((datetime.fromisoformat(events["on"]["utc"]) - datetime.fromisoformat(events["off"]["utc"])).total_seconds() >= 15,
              "Final off period shorter than 15 seconds")
    checks["final_cold_signature"] = dict(expected_next_slot=52, image_reread=False, sbf_reread=False,
        verified_image_slot=51, scope="Final low-current signature only; not a second verified image or SBF attribution")
    stop = a.read(source / "final-js-stop.json")
    last = json.loads((source / "js3-session.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    a.require(stop == last and stop["event"] == "stopped" and stop["ok"]
              and stop["starting_range"] == stop["range"] == 128 and stop["restore_error"] is None,
              "Joulescope did not close cleanly preserving range")
    a.require(datetime.fromisoformat(stop["utc"]) > datetime.fromisoformat(proof["observed_utc"]),
              "Instrument closure predates final cold boot")
    stats = stop["statistics"]
    a.require(.007 < stats["current"]["avg"] < .01 and 4.8 < stats["voltage"]["avg"] < 5.1,
              "Final low-current signature differs")
    checks["final_instrument_closure"] = dict(stopped_utc=stop["utc"], range_restored=128,
        target_left_on=True, input_voltage_V=stats["voltage"]["avg"], current_A=stats["current"]["avg"])
    tests = (source / "final-offline-tests.log").read_text(encoding="utf-8")
    a.require("Ran 178 tests" in tests and tests.rstrip().endswith("OK"), "Final offline test run did not pass")
    checks["final_offline_tests"] = dict(passed=178)
    checks["bench_checkpoint"] = dict(**a.identity(snapshot / "checkpoint/AGENTS.md"),
        scope="Parent-written historical checkpoint, not a fresh live hardware observation")
    result["waveforms_recomputed"] = False
    return result


def collect_closure(source, out, checkpoint):
    target = out / "snapshots/closure"
    a.require(not target.exists(), "Refusing to overwrite the immutable closure snapshot")
    target.mkdir(parents=True)
    dirs = {"prefix-interrupt", "prefix-interrupt-recover", "prefix-interrupt-park",
            "final-recover", "final-nor", "final-cold"}
    files = {"final-js-query.json", "final-js-stop.json", "js-session.jsonl", "js2-session.jsonl",
             "js3-session.jsonl", "final-offline-tests.log", "final_cold.py"}
    copies = []
    for p in sorted(source.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(source)
        keep = len(rel.parts) == 1 and (p.name in files or p.name.startswith(("final-", "prefix-interrupt")) and p.suffix == ".log")
        keep |= len(rel.parts) > 1 and rel.parts[0] in dirs and p.suffix.lower() in {".json", ".jsonl", ".log", ".bin"}
        if not keep:
            continue
        before = a.identity(p); dest = target / "inputs" / rel
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
        a.require(a.identity(p) == before == a.identity(dest), "Source changed while copying")
        copies.append(dict(source=str(p.resolve()), path=dest.relative_to(target).as_posix(), **before))
    (target / "checkpoint").mkdir()
    shutil.copyfile(checkpoint, target / "checkpoint/AGENTS.md")
    copies.append(dict(source=str(checkpoint.resolve()), path="checkpoint/AGENTS.md", **a.identity(checkpoint)))
    a.write(target / "source-copies.json", copies)
    a.write(target / "snapshot-bindings.json", {name: a.identity(out / "snapshots" / name / "SHA256SUMS.json")
                                               for name in ("initial", "qualification")})
    summary = replay_closure(target)
    summary["created_utc"] = datetime.now(timezone.utc).isoformat()
    a.write(target / "summary.json", summary)
    a.write(target / "SHA256SUMS.json", dict(schema=1, files=a.entries(target)))
    return dict(snapshot="closure", qualification_complete=True, pending=[], **a.seal(out))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=a.HERE)
    parser.add_argument("--closure", action="store_true")
    parser.add_argument("--checkpoint", type=Path, default=Path("AGENTS.md"))
    args = parser.parse_args()
    print(json.dumps(collect_closure(args.source, args.out, args.checkpoint) if args.closure
                     else collect(args.source, args.out), indent=2))
