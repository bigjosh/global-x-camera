"""Finish the metadata-only low-power archive after bench ownership is released."""
from pathlib import Path
import gzip
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
ARCHIVE=ROOT/"firmware/capture-sd/evidence/2026-10-20-low-power"
INPUT=ROOT/"tmp/bringup/capture-sleep-20261020"
plan=json.loads((ARCHIVE/"archive-plan.json").read_text())
index={e["archived_path"]:e for e in plan["source_index"]}
def add(source,dest,compress=False):
    raw=source.read_bytes();data=gzip.compress(raw,mtime=0) if compress else raw
    target=ARCHIVE/dest;assert target.resolve().is_relative_to(ARCHIVE.resolve())
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    e=dict(original_path=source.relative_to(ROOT).as_posix(),original_bytes=len(raw),
        original_sha256=hashlib.sha256(raw).hexdigest(),archived_path=dest,
        archived_bytes=len(data),archived_sha256=hashlib.sha256(data).hexdigest(),
        transformation="lossless gzip statistics log" if compress else "exact final evidence/documentation")
    if compress:e["encoding"]="gzip"
    index[dest]=e
final=json.loads((INPUT/"final-state.json").read_text())
assert final["sector_sha256"]==plan["build_identity"]["sector"]
assert final["js110"]["ok"] and final["js110"]["range"]==128 and not final["js110"]["restore_error"]
assert final["uart_closed"] and final["break_released"] and final["no_active_storage_helper"]
assert not final["final_filename_readback_verified"]
add(INPUT/"final-state.json","results/final-state.json")
add(INPUT/"v59-final-session.jsonl","results/v59-final-session.jsonl.gz",True)
for name in ("off.json","auto.json","signal-summary.json"):
    add(INPUT/"v59-final-normal"/name,"results/v59-final-normal/"+name)
for name in ("README.md","verify.py"):
    add(Path(__file__).resolve().parent/name,name)
add(Path(__file__).resolve(),"add_final.py")
plan["qualification"]["final_target_state"]="results/final-state.json"
plan["qualification"]["final_filename_verified"]=False
plan["status"]="Complete bench archive: exact v59 firmware/rebuild, four Standby/recovery proofs, three energy cycles, six READ-only file checks, and final powered plateau"
plan["source_index"]=[index[k] for k in sorted(index)]
plan["archive_bytes"]=sum(e["archived_bytes"] for e in plan["source_index"])
(ARCHIVE/"archive-plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8",newline="\n")
print(json.dumps(dict(files=len(index),bytes=plan["archive_bytes"]),indent=2))
