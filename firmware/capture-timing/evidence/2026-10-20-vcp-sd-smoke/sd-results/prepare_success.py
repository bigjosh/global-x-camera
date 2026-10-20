"""Archive selected SD smoke results, never card sector bytes; no hardware."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    index = json.loads((HERE / "source-index.json").read_text())

    def save(source, name, raw, transformation):
        source = REPO / source
        destination = HERE / name
        destination.write_bytes(raw)
        index[:] = [e for e in index if e["archive"] != name]
        index.append({
            "source": source.relative_to(REPO).as_posix(),
            "source_sha256": sha(source.read_bytes()),
            "archive": name, "archive_sha256": sha(raw),
            "transformation": transformation,
        })

    def encoded(data):
        return (json.dumps(data, indent=2) + "\n").encode()

    for name in ("sd-read-100k-05", "sd-read-25m-01"):
        source = Path("tmp/bringup/vcp-install-20261019") / name / "report.json"
        report = json.loads((REPO / source).read_text())
        assert all(report[k] is True for k in
                   ("read_smoke_pass", "host_data_verified", "device_reported_pass"))
        status = report["status"]
        selected = {
            "run": name,
            "helper_sha256": "790b240b4246d61daf6361da67cb2bca6084d666897902e0bfd1dc9555c03db6",
            "reported_capacity_bytes": report["capacity_bytes"],
            "reported_product_name": report["cid"]["product_name"],
            "read_smoke_pass": True, "host_data_verified": True,
            "device_reported_pass": True,
            "status": {k: status[k] for k in (
                "result", "stage", "request_max_hz", "kernel_hz", "current_sd_hz",
                "clkcr", "read_count", "read_words", "read_sta", "read_match_mask",
                "card_status", "fail_stage", "fail_command", "fail_sta", "cleanup")},
            "buffers": [{k: b[k] for k in ("name", "crc32", "same_as_slow_read")}
                        for b in report["buffers"]],
            "park_verification": report["park_verification"],
            "sd_writes_or_erases": False,
            "limitations": [
                "Two sectors only; no capacity verification or sustained test.",
                "No write throughput or energy result.",
                "No raw card bytes, CID serial, or raw SD records archived.",
            ],
        }
        save(source, name + ".json", encoded(selected),
             "Selected result/configuration/checksum/park fields; no sector contents or card serial")

    base = Path("tmp/bringup/sd-smoke-readonly-v3-20261020")
    for source_name, archive_name in (
        ("manifest.json", "helper-v3-manifest.json"),
        ("sd-smoke.bin", "helper-v3-sd-smoke.bin"),
    ):
        source = base / source_name
        raw = (REPO / source).read_bytes()
        if source_name.endswith(".json"):
            raw = encoded(json.loads(raw))
        save(source, archive_name, raw,
             "UTF-8 LF manifest" if source_name.endswith(".json") else
             "Exact compiled helper bytes, not card data")

    source = Path("tmp/bringup/vcp-install-20261019/js/response.json")
    cleanup = json.loads((REPO / source).read_text())
    assert cleanup["event"] == "stopped" and cleanup["ok"]
    assert cleanup["starting_range"] == cleanup["range"] == 128
    save(source, "js-cleanup.json", encoded(cleanup),
         "Final API ownership release and measured supply statistics; UTF-8 LF")
    (HERE / "source-index.json").write_bytes(encoded(index))
    print(json.dumps({"indexed_files": len(index), "card_bytes_archived": False}))


if __name__ == "__main__":
    main()
