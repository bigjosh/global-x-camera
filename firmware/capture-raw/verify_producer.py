"""Offline qualification of LINE snapshots and pre-call DMA bounds."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

FRAME_BYTES = 1909600
GROUP_BYTES = 89600
NAMES = ("magic schema enabled line_events frame_seen validated error available_bytes "
         "first_line_cycle first_prefix_cycle last_line_cycle frame_cycle validation_cycle "
         "max_prefinal_bytes ignored_after_frame snapshot_count").split()


def decode(data):
    if len(data) != 416:
        raise ValueError("producer telemetry must contain exactly416bytes")
    words = struct.unpack("<104I", data)
    result = dict(zip(NAMES, words[:16]))
    result["events"] = [list(words[i:i + 2]) for i in range(16, 64, 2)]
    result["snapshots"] = [list(words[i:i + 2]) for i in range(64, 104, 2)]
    return result


def verify(producer, snapshots, frame, chunks, proof, *, require_overlap=True):
    p = decode(producer)
    expected = dict(magic=0x50524431, schema=1, enabled=1, frame_seen=1,
                    validated=1, error=0, available_bytes=FRAME_BYTES)
    if any(p[k] != v for k, v in expected.items()) or len(frame) != FRAME_BYTES:
        raise ValueError("producer or retained frame is incomplete")
    if not 2 <= p["line_events"] <= 22:
        raise ValueError("insufficient/invalid LINE events")
    expected_snapshots = min(p["line_events"], 21) - 1
    if p["snapshot_count"] != expected_snapshots or len(snapshots) < expected_snapshots * 512:
        raise ValueError("missing immediate prefix snapshots")
    if p["max_prefinal_bytes"] != expected_snapshots * GROUP_BYTES:
        raise ValueError("unexpected pre-FRAME watermark")
    for i in range(p["line_events"]):
        if p["events"][i][1] != (min(i + 1, 21) - 1) * GROUP_BYTES:
            raise ValueError("LINE watermark overpublished or regressed")
    snapshot_results = []
    for i in range(expected_snapshots):
        offset, size = p["snapshots"][i]
        if (offset, size) != ((i + 1) * GROUP_BYTES - 512, 512):
            raise ValueError("snapshot range is not the immediate published tail")
        data = snapshots[i * 512:(i + 1) * 512]
        if data != frame[offset:offset + 512]:
            raise ValueError(f"snapshot{i} differs from finalframe atoffset{offset}")
        snapshot_results.append(dict(index=i, offset=offset, bytes=512,
                                     sha256=hashlib.sha256(data).hexdigest()))
    count = proof["chunk_count"]
    if proof["chunk_overflow"] or not 1 <= count <= 128 or len(chunks) < count * 32:
        raise ValueError("incomplete chunk trace")
    sent, overlap, rows = 0, False, []
    delta = lambda cycle: (cycle - proof["begin"]) & 0xFFFFFFFF
    frame_time = delta(proof["frame_done"])
    for i in range(count):
        start, end, offset, sectors, available, ready, error, cycles = struct.unpack_from("<8I", chunks, i * 32)
        if offset != sent or not sectors or error or ready & 0x1F00 != 0x900:
            raise ValueError("chunk sequence/error/ready mismatch")
        if available > FRAME_BYTES or (offset + sectors) * 512 > available:
            raise ValueError("SD read beyond its pre-call producer watermark")
        if offset + sectors > 3729:
            raise ValueError("whole-sector stream consumed finalpartialsector")
        if delta(start) < frame_time:
            overlap = True
            if available > 20 * GROUP_BYTES:
                raise ValueError("unvalidated fullframe published beforeFRAME")
        if delta(end) < delta(start):
            raise ValueError("chunk end precedesstart")
        rows.append(dict(index=i, offset_sectors=offset, sectors=sectors,
                         available_before=available, start_cycle=start, end_cycle=end,
                         starts_before_frame=delta(start) < frame_time))
        sent += sectors
    if sent != 3729:
        raise ValueError("whole-sector prefix is incomplete")
    if require_overlap and not overlap:
        raise ValueError("no payloadwrite started beforeFRAME")
    return dict(passed=True, snapshot_count=expected_snapshots, exact_snapshot_bytes=expected_snapshots * 512,
                overlap_observed=overlap, payload_sectors=sent,
                producer=p, snapshots=snapshot_results, chunks=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("producer", "snapshots", "frame", "chunks", "proof", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--allow-no-overlap", action="store_true")
    args = parser.parse_args()
    proof = json.loads(args.proof.read_text())
    if "proof" in proof:
        proof = proof["proof"]
    result = verify(args.producer.read_bytes(), args.snapshots.read_bytes(), args.frame.read_bytes(),
                    args.chunks.read_bytes(), proof, require_overlap=not args.allow_no_overlap)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("passed", "snapshot_count", "exact_snapshot_bytes", "overlap_observed")}))


if __name__ == "__main__":
    main()
