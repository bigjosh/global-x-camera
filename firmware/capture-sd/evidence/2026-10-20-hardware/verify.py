"""Verify a staged archive offline; no hardware, filesystem writes or imports."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import zlib


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify(root):
    root = root.resolve()
    plan = json.loads((root / "archive-plan.json").read_text(encoding="utf-8"))
    expected={e["archived_path"] for e in plan["source_index"]}
    found={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    # Python may create a local bytecode cache when rebuild.py imports verify.
    found={p for p in found if "__pycache__" not in Path(p).parts}
    if found-{"archive-plan.json"} != expected:
        raise ValueError("Archive contains missing or unlisted files")
    for entry in plan["source_index"]:
        path = (root / entry["archived_path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Archive path escapes root")
        raw = path.read_bytes()
        if len(raw) != entry["archived_bytes"] or digest(raw) != entry["archived_sha256"]:
            raise ValueError(f"Archive hash mismatch: {path}")
        if entry.get("encoding") == "gzip":
            unpacked=gzip.decompress(raw)
            if (len(unpacked)!=entry["original_bytes"] or
                    digest(unpacked)!=entry["original_sha256"]):
                raise ValueError("Decompressed primary input differs")
    b = root / "build"
    mm = json.loads((b / "module/manifest.json").read_text())
    rm = json.loads((b / "receiver/manifest.json").read_text())
    pm = json.loads((b / "prefix/manifest.json").read_text())
    payloads = {name:(root / recipe["binary"]).read_bytes()
                for name,recipe in plan["recipe"].items()}
    for name,raw in payloads.items():
        if digest(raw) != plan["build_identity"][name]:
            raise ValueError(f"Binary identity mismatch: {name}")
    boot = (b / "prefix/stage1_boot.bin").read_bytes()
    sector = (b / "prefix/capture_sector_0.bin").read_bytes()
    if len(sector) != 65536 or digest(sector) != pm["program_sha256"]:
        raise ValueError("Sector identity mismatch")
    assert sector[:len(boot)] == boot
    assert boot[0x400:0x400+len(payloads["prefix"])] == payloads["prefix"]
    assert sector[0x2000:0x2000+len(payloads["receiver"])] == payloads["receiver"]
    assert sector[0x6000:0x6000+len(payloads["module"])] == payloads["module"]
    assert digest(payloads["module"]) == mm["binary_sha256"]
    assert digest(payloads["receiver"]) == rm["raw_sha256"] == pm["stage2_sha256"]
    assert zlib.crc32(payloads["receiver"]) == int(pm["stage2_crc32"], 0)
    assert mm["binary_bytes"] == len(payloads["module"]) <= 40960
    assert int(mm["load_address"],0) == 0x34320000
    assert 0x34320000+len(payloads["module"]) <= int(mm["bss_start"],0)
    assert int(mm["bss_start"],0) <= int(mm["bss_end"],0) <= 0x343A0000
    assert len(payloads["prefix"]) == pm["stage1_raw_bytes"]
    assert plan["privacy"]["camera_images"] is False
    assert plan["privacy"]["sd_contents"] is False
    assert plan["privacy"]["other_raw_instrument_streams"] is False
    return dict(files=len(plan["source_index"]), bytes=plan["archive_bytes"],
                identity=plan["build_identity"], hardware_accessed=False)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path,nargs="?",default=Path(__file__).parent)
    print(json.dumps(verify(parser.parse_args().archive),indent=2))
