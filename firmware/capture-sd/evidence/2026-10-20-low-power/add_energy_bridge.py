"""Add finalized compact energy and the reviewed RAM READ bridge, never images."""
from pathlib import Path
import gzip
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
ARCHIVE=ROOT/"firmware/capture-sd/evidence/2026-10-20-low-power"
INPUT=ROOT/"tmp/bringup/capture-sleep-20261020"
plan=json.loads((ARCHIVE/"archive-plan.json").read_text())
index={e["archived_path"]:e for e in plan["source_index"]}

def add(source,dest,compress=False,description="exact finalized evidence"):
    source=Path(source); raw=source.read_bytes()
    data=gzip.compress(raw,mtime=0) if compress else raw
    target=ARCHIVE/dest
    assert target.resolve().is_relative_to(ARCHIVE.resolve())
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    entry=dict(original_path=source.relative_to(ROOT).as_posix(),
        original_bytes=len(raw),original_sha256=hashlib.sha256(raw).hexdigest(),
        archived_path=dest,archived_bytes=len(data),
        archived_sha256=hashlib.sha256(data).hexdigest(),transformation=description)
    if compress:entry["encoding"]="gzip"
    index[dest]=entry

for name in ("analysis.json","spec.json","compact-qualified-scope.json.gz"):
    add(INPUT/"baseline-energy"/name,"energy/baseline/"+name)
for name in ("analysis.json","spec.json","summary.json","README.md",
        "terminal-attestation-1.json","terminal-attestation-2.json","terminal-attestation-3.json",
        "compact-cycle-1.json.gz","compact-cycle-2.json.gz","compact-cycle-3.json.gz",
        "cold-cycle-comparison-qualified.png","cold-cycle-comparison-qualified.svg"):
    add(INPUT/"v59-energy-analysis"/name,"energy/standby/"+name)
add(INPUT/"v59-energy-analysis/replay-energy.py","energy/replay-energy.py")
for name,directory in (("baseline",INPUT/"baseline-energy/raw"),("v59",INPUT/"v59-energy-raw")):
    add(directory/"manifest.json",f"energy/raw-metadata/{name}/manifest.json")
    add(directory/"chunks.jsonl",f"energy/raw-metadata/{name}/chunks.jsonl.gz",True,
        "lossless gzip of raw sample chunk index only; sample arrays remain local")
for relative in (
        "firmware/capture-sd/cycle_plot.py",
        "firmware/capture-sd/test_cycle_plot.py",
        "firmware/capture-sd/cycle-energy.md",
        "firmware/capture-timing/test_maintenance_guards.py",
        "firmware/boot-timing/nor_bench.py",
        "firmware/boot-timing/capture_cycle.py",
        "firmware/boot-timing/tests/test_js110_power.py",
        "firmware/boot-timing/tests/test_js110_recovery.py",
        "firmware/boot-timing/tests/test_helpers_offline.py"):
    add(ROOT/relative,"support/"+relative,description="final corrected energy source snapshot")
add(INPUT/"root-test-results.json","verification/root-test-results.json")

bridge=INPUT/"recovery-read-bridge-v1"
for name in ("boot.c","entry.S","boot.ld","raw10_memory.c","boot.bin","boot.lst","boot.map","symbols.txt","manifest.json"):
    add(bridge/name,"build/readback-bridge/"+name)
for source in sorted((ROOT/"firmware/capture-sd/low_power/readback_recovery").iterdir()):
    if source.is_file() and source.suffix in (".py",".md",".c",".S",".ld"):
        add(source,"support/"+source.relative_to(ROOT).as_posix(),
            description="reviewed standalone READ-only recovery bridge source")
m=json.loads((bridge/"manifest.json").read_text())
flags=m["flags"]+[
    "-I${ARCHIVE}/dependencies/st/STM32Cube_FW_N6/Drivers/CMSIS/Include",
    "-I${ARCHIVE}/dependencies/st/STM32Cube_FW_N6/Drivers/CMSIS/Device/ST/STM32N6xx/Include"]
plan["auxiliary_recipes"]={
    "readback-bridge":dict(
        sources=["build/readback-bridge/"+s for s in ("entry.S","boot.c","raw10_memory.c")],
        compile_flags=flags,linker="build/readback-bridge/boot.ld",
        binary="build/readback-bridge/boot.bin",binary_sha256=m["binary_sha256"],
        runtime_flags=[],link_flags=["-Wl,--build-id=none"],libraries=[],
        loaded_into_nor=False)}
add(Path(__file__).resolve(),"add_energy_bridge.py",description="explicit archive ingestion inputs; no sample/image arrays")
plan["qualification"]["final_energy_summary_pending"]=False
plan["qualification"]["energy_summary"]="energy/standby/summary.json"
plan["qualification"]["baseline_full_cycle_energy_qualified"]=False
plan["qualification"]["readback_bridge_hardware_qualified"]=False
plan["status"]="v59 Standby and warm UART recovery measured; compact native-clock energy recorded; post-Standby file readback pending"
plan["source_index"]=[index[k] for k in sorted(index)]
plan["archive_bytes"]=sum(e["archived_bytes"] for e in plan["source_index"])
(ARCHIVE/"archive-plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8",newline="\n")
print(json.dumps(dict(files=len(index),bytes=plan["archive_bytes"]),indent=2))
