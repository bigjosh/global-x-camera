"""Copy explicit, non-image low-power evidence into the still-open archive."""
from pathlib import Path
import hashlib
import json
import statistics
import gzip

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT / "firmware/capture-sd/evidence/2026-10-20-low-power"
INPUT = ROOT / "tmp/bringup/capture-sleep-20261020"
PLAN = ARCHIVE / "archive-plan.json"
plan = json.loads(PLAN.read_text(encoding="utf-8"))
index = {e["archived_path"]: e for e in plan["source_index"]}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def add(original, destination, data=None, transformation="exact evidence"):
    original = Path(original)
    before = original.read_bytes()
    after = before if data is None else data
    target = ARCHIVE / destination
    assert target.resolve().is_relative_to(ARCHIVE.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(after)
    index[destination] = dict(
        original_path=original.relative_to(ROOT).as_posix(),
        original_bytes=len(before), original_sha256=sha(before),
        archived_path=destination,
        archived_bytes=len(after), archived_sha256=sha(after),
        transformation=transformation,
    )


def encode(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def compact_signal(directory):
    path = directory / "signal-summary.json"
    source = json.loads(path.read_text())
    channels = {}
    for channel, intervals in source["digital_intervals"].items():
        assert all(i["end_s"] >= i["start_s"] for i in intervals)
        levels = {}
        for level in sorted({i["level"] for i in intervals}):
            widths = [i["end_s"] - i["start_s"] for i in intervals if i["level"] == level]
            levels[str(level)] = dict(
                count=len(widths), min_s=min(widths), max_s=max(widths),
                median_s=statistics.median(widths), total_s=sum(widths))
        channels[channel] = dict(
            interval_count=len(intervals), levels=levels,
            first_intervals=intervals[:4], last_intervals=intervals[-4:],
        )
    refs = []
    for local in sorted(directory.iterdir()):
        if local.is_file() and local.name in (
                "analog.csv", "digital.csv", "signal.sal", "power-cycle.sal",
                "signal-summary.json"):
            raw = local.read_bytes()
            refs.append(dict(path=local.relative_to(ROOT).as_posix(),
                             bytes=len(raw), sha256=sha(raw), archived=False))
    compact = dict(
        schema=1, source_summary_path=path.relative_to(ROOT).as_posix(),
        source_summary_sha256=sha(path.read_bytes()),
        analog=source.get("analog"),
        digital=channels,
        source_limitations=source.get("limitations"),
        interpretation=[
            "Interval statistics summarize the exported logic threshold states; they do not prove every transition is a physical reset.",
            "Power-cycle traces include threshold chatter near low rails; physical causation is not established.",
            "The exact firmware recovery park and fresh SBF result establish recovery and Standby history; this waveform summary alone does not.",
            "Raw waveforms remain local. This compact summary cannot recreate the waveform or replay the edge detector.",
        ],
        local_primary_files=refs,
    )
    add(path, f"results/{directory.name}/signal-compact.json", encode(compact),
        "compact per-level interval counts/durations and analog statistics; raw files hash referenced only")


def metadata_folder(name, recursive=False):
    directory = INPUT / name
    assert directory.is_dir(), name
    files = directory.rglob("*") if recursive else directory.iterdir()
    for path in sorted(files):
        if not path.is_file():
            continue
        if path.name == "signal-summary.json":
            compact_signal(directory)
        elif path.suffix in (".json", ".jsonl", ".log"):
            # These explicitly selected folders contain only program/proof and
            # instrument-control metadata, never SD sectors or photo records.
            add(path, f"results/{name}/{path.relative_to(directory).as_posix()}")


metadata_folder("v59-nor-info")
metadata_folder("v59-nor-write")
for suffix in ["cold-1", "uart-recovery-1", "recovery-park-1", "sbf-1"]:
    metadata_folder("v59-" + suffix, recursive=suffix == "sbf-1")
for number in (1, 2, 3):
    for kind in ("cycle", "uart", "park", "sbf"):
        metadata_folder(f"v59-energy-{kind}-{number}", recursive=kind == "sbf")
for name in (
        "v57-save-proof", "v57-lowpower-proof", "v57-recovery-park",
        "v58-nor-write", "v58-lowpower-proof", "v58-ap0-proof",
        "v58-ap2-proof", "v58-recovery-park", "v58-post-reset-flags"):
    metadata_folder(name, recursive=name == "v58-post-reset-flags")
add(ROOT/"firmware/capture-sd/low_power/hardware-notes-2026-10-20.md",
    "qualification/v57-v58-hardware-notes.md")
session = INPUT/"v57-session.jsonl"
destination = "qualification/v57-v58-statistics.jsonl.gz"
add(session, destination, gzip.compress(session.read_bytes(), mtime=0),
    "lossless gzip of JS110 half-second statistics/control log; no raw sample stream")
index[destination]["encoding"] = "gzip"

# Independent exact-build validation and an actual byte-identical rebuild.
for name in (
        "v57-peripherals-off-independent-review.json",
        "v58-stop-independent-review.json",
        "v59-standby-independent-review.json",
        "v57-v59-offline-review.json"):
    add(INPUT / name, f"verification/{name}")
add(ROOT / "tmp/bringup/low-power-archive-rebuild-v59-20261020/rebuild-verification.json",
    "verification/rebuild-verification.json")
add(Path(__file__).resolve(), "add_hardware.py", transformation="archive ingestion helper; explicit non-image inputs only")

evidence = []
for park, sbf in [("v59-recovery-park-1", "v59-sbf-1")] + [
        (f"v59-energy-park-{i}", f"v59-energy-sbf-{i}") for i in (1, 2, 3)]:
    p = json.loads((INPUT / park / "result.json").read_text())
    s = json.loads((INPUT / sbf / "result.json").read_text())
    assert p["passed"] and s["passed"] and s["sbf"]
    assert p["prefix_sha256"] == plan["build_identity"]["prefix"]
    assert p["vcp_status"]["request"] == 1 and p["vcp_status"]["source_bits"] == 2
    assert not s["cpucr_written"] and not s["reset_or_power_changed"]
    assert s["cpucr"] == 0x10201
    evidence.append(dict(
        recovery=f"results/{park}/result.json",
        standby_flag=f"results/{sbf}/result.json",
        sbf=True, cpucr=s["cpucr"], good_pulses=p["vcp_status"]["good_pulses"],
        bad_pulses=p["vcp_status"]["bad_pulses"],
        request_cycle=p["vcp_status"]["request_cycle"],
    ))
plan["status"] = "v59 exact firmware rebuilt; four observed Standby histories and warm UART recoveries; final energy/file qualification pending"
plan["qualification"] = dict(
    standby_entry=True, recovery_from_standby=True,
    observed_trials=4, hardware_status="initial and three repeated Standby/recovery trials passed",
    evidence=evidence,
    attribution="Each tested cold boot used this exact candidate, which clears SBF before Standby. The operator recorded no power cycle between each low-current state and its warm UART reset/SBF read. The SBF helper itself intentionally reports historical Standby only.",
    final_energy_summary_pending=True,
    post_standby_image_readback_pending=True,
)
plan["source_index"] = [index[key] for key in sorted(index)]
plan["archive_bytes"] = sum(e["archived_bytes"] for e in plan["source_index"])
PLAN.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(dict(files=len(index), bytes=plan["archive_bytes"], observations=evidence), indent=2))
