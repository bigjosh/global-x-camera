"""Offline validation of an intentionally rejected recording; no energy repair."""
import gzip
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Archive identity mismatch: " + name)
    raw = (root / "raw-manifest.json").read_bytes()
    m = json.loads(raw)
    d = json.loads((root / "raw-failure-diagnostic.json").read_bytes())
    chunks = gzip.decompress((root / "raw-chunks.jsonl.gz").read_bytes())
    if (m["finalized"] is not False or m["status"]["coverage"]["passed"] is not False or
            m["status"]["dropped_chunks"] != 513 or
            hashlib.sha256(raw).hexdigest() != d["manifest_sha256"] or
            hashlib.sha256(chunks).hexdigest() != m["chunks_sha256"]):
        raise ValueError("Original failure metadata differs")
    last, gaps = {}, []
    for record in map(json.loads, chunks.decode("utf-8").splitlines()):
        if record.get("event") != "stream_chunk":
            continue
        signal = record["signal"]
        start, end = record["sample_id"], record["sample_id_end_exclusive"]
        if signal in last and start != last[signal]:
            gaps.append(dict(signal=signal, start_sample_id=last[signal],
                end_sample_id=start, missing_native_samples=start-last[signal]))
        last[signal] = end
    expected = [{k: row[k] for k in
        ("signal", "start_sample_id", "end_sample_id", "missing_native_samples")}
        for row in d["gaps"]]
    if sorted(gaps, key=lambda x: x["signal"]) != sorted(expected, key=lambda x: x["signal"]):
        raise ValueError("Gap replay differs")
    print(json.dumps(dict(passed=True, original_recording_valid=False,
        dropped_chunks=513, gap_count=len(gaps), energy_estimated=False,
        data_repaired=False), indent=2))


if __name__ == "__main__":
    main()
