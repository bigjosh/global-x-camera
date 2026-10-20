"""Archive completed READ-only qualification metadata, never file/RAM bytes."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
ARCHIVE=ROOT/"firmware/capture-sd/evidence/2026-10-20-low-power"
INPUT=ROOT/"tmp/bringup/capture-sleep-20261020"
READ=INPUT/"standby-png-readback"
plan=json.loads((ARCHIVE/"archive-plan.json").read_text())
index={e["archived_path"]:e for e in plan["source_index"]}

def add(source,dest,description="exact READ-only qualification metadata"):
    raw=source.read_bytes()
    target=ARCHIVE/dest
    assert target.resolve().is_relative_to(ARCHIVE.resolve())
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    index[dest]=dict(original_path=source.relative_to(ROOT).as_posix(),
        original_bytes=len(raw),original_sha256=hashlib.sha256(raw).hexdigest(),
        archived_path=dest,archived_bytes=len(raw),archived_sha256=hashlib.sha256(raw).hexdigest(),
        transformation=description)

finished=json.loads((READ/"verified.json").read_text())
assert finished["read_only"] and not finished["nor_image_changed"] and not finished["raw_frame_comparison"]
expected={"IMG00001.PNG","IMG00038.PNG","IMG00039.PNG","IMG00040.PNG","IMG00041.PNG","IMG00042.PNG"}
assert {f["name"] for f in finished["files"]}==expected
for name in ("plan.json","verified.json","bootstrap/verified.json","bootstrap/early-guard/result.json"):
    add(READ/name,"results/standby-png-readback/"+name)
chunk_count=0
for file in finished["files"]:
    name=file["name"];folder=READ/Path(name).stem
    verified=json.loads((folder/"verified.json").read_text())
    assert verified==file
    assert (file["all_png_chunk_crcs_valid"] and file["complete_independent_decode"]
            and file["all_samples_10bit_left_aligned"] and not file["exact_capture_pixel_comparison"]
            and file["pixels"]==1527680 and file["readonly_card_writes"]==0)
    add(folder/"verified.json",f"results/standby-png-readback/{folder.name}/verified.json")
    offset=0
    for number in range(file["read_chunks"]):
        path=folder/f"chunk-{number:02d}"/"verified.json"
        record=json.loads(path.read_text());r=record["report"];q=record["request"];c=record["card"];fs=record["filesystem"]
        assert r["operation"]==q["operation"]==3 and r["nonce"]==q["nonce"] and r["nonce"]
        assert q["name"]==name and q["offset"]==offset and r["read_bytes"]<=262144
        assert r["terminal"]==0x444F4E45 and r["result"]==0 and r["media_idle"]==1
        assert not any(c[k] for k in ("written_sectors","write_cycles","error","initialized","controller_owned"))
        assert c["media_idle"]==1 and not fs["bytes_written"] and not fs["fat_result"]
        assert record["context"]["registers"]["PC"]==0x3432006E and record["module_sha256"]==plan["build_identity"]["module"]
        assert not record["reset_sent"] and not record["power_changed"] and not record["nor_commands_sent"]
        add(path,f"results/standby-png-readback/{folder.name}/chunk-{number:02d}/verified.json")
        offset+=r["read_bytes"];chunk_count+=1
    assert offset==file["bytes"]
old=next(f for f in finished["files"] if f["name"]=="IMG00001.PNG")
assert old["known_file_hash_matched"] and old["sha256"]=="466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330"
summary=dict(
    schema=1,status="Post-Standby READ-only file qualification completed",
    evidence="results/standby-png-readback/verified.json",
    files=finished["files"],chunks=chunk_count,
    scope=[
        "IMG00001 matches the previously downloaded original file SHA-256 exactly.",
        "IMG00038 is from the Stop trial; IMG00039 is the initial Standby trial; IMG00040..42 are the three measured Standby energy trials.",
        "Every file passed independent PNG CRC/decoding and left-aligned 10-bit sample checks; the original raw frames were lost, so no exact capture pixel comparison is claimed.",
        "All READ chunks reported zero card writes, completed cleanup, caches off and the exact v8b terminal park. NOR was unchanged.",
        "This addendum supersedes the pending file-readback notes in the frozen energy analysis/attestations without changing their bytes.",
        "Photographs, uploaded buffers and SD sectors remain local; only verification metadata is archived.",
    ])
summary_path=INPUT/"post-standby-readback-addendum.json"
summary_path.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8",newline="\n")
add(summary_path,"qualification/post-standby-readback.json")
add(Path(__file__).resolve(),"add_readback.py",description="explicit metadata-only archive ingestion helper")
plan["qualification"]["post_standby_image_readback_pending"]=False
plan["qualification"]["readback_bridge_hardware_qualified"]=True
plan["qualification"]["post_standby_file_readback"]="qualification/post-standby-readback.json"
plan["status"]="v59 Standby/warm UART recovery, compact energy and subsequent READ-only PNG validation qualified on this bench"
plan["source_index"]=[index[k] for k in sorted(index)]
plan["archive_bytes"]=sum(e["archived_bytes"] for e in plan["source_index"])
(ARCHIVE/"archive-plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8",newline="\n")
print(json.dumps(dict(files=len(index),bytes=plan["archive_bytes"],read_chunks=chunk_count),indent=2))
