"""Decode saved SD smoke RAM dumps offline; never controls the target."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--records", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.build / "manifest.json").read_text())
    raw = args.status.read_bytes()
    if len(raw) != 4 * manifest["status_words"]:
        raise ValueError("Incomplete status dump")
    s = dict(zip(manifest["status_fields"], struct.unpack("<" + "I" * (len(raw)//4), raw)))
    if s["magic"] != 0x53445231 or s["schema"] != 1 or s["words"] != manifest["status_words"]:
        raise ValueError("Status layout mismatch")
    result = {"status": s}
    if args.records:
        raw = args.records.read_bytes()
        count = min(s["records_used"], manifest["record_count"])
        if len(raw) < count * 48:
            raise ValueError("Incomplete command records")
        result["records"] = [
            dict(zip(manifest["record_fields"], struct.unpack_from("<12I", raw, i*48)))
            for i in range(count)
        ]
    sectors = (s["sector_count_high"] << 32) | s["sector_count_low"]
    result["capacity_bytes"] = sectors * 512
    result["capacity_decimal_gb"] = sectors * 512 / 1e9
    cid = b"".join(s[f"cid{i}"].to_bytes(4, "big") for i in range(4))
    result["cid"] = {
        "hex": cid.hex(), "manufacturer_id": cid[0],
        "oem_id": cid[1:3].decode("ascii", errors="replace"),
        "product_name": cid[3:8].decode("ascii", errors="replace"),
        "product_revision": f"{cid[8]>>4}.{cid[8]&15}",
        "serial": int.from_bytes(cid[9:13], "big"),
        "year": 2000 + (((cid[13]&15)<<4) | (cid[14]>>4)),
        "month": cid[14]&15,
    }
    if args.data:
        raw = args.data.read_bytes()
        if len(raw) < s["read_count"] * 512:
            raise ValueError("Incomplete sector buffers")
        result["buffers"] = []
        for i in range(s["read_count"]):
            data = raw[i*512:(i+1)*512]
            actual = zlib.crc32(data)
            if actual != s[f"read_crc{i}"]:
                raise ValueError(f"Buffer {i} CRC32 differs from target")
            result["buffers"].append({
                "name": manifest["buffer_order"][i], "crc32": f"{actual:08x}",
                "sha256": hashlib.sha256(data).hexdigest(),
                "last_two_bytes": data[-2:].hex(),
                "same_as_slow_read": None if i < 2 else data == raw[(i%2)*512:((i%2)+1)*512],
            })
    expected = {100000: 2, 12500000: 4, 25000000: 6}.get(s["request_max_hz"])
    expected_matches = ((1 << expected) - 1) & ~3 if expected else None
    result["device_reported_pass"] = bool(
        expected and s["result"] == 0 and s["stage"] == 9 and
        s["read_count"] == expected and s["cleanup"] == 3 and
        s["read_match_mask"] == expected_matches
    )
    result["host_data_verified"] = bool(
        args.data and s["read_count"] > 0 and
        all(buffer["same_as_slow_read"] is not False for buffer in result["buffers"])
    )
    result["read_smoke_pass"] = result["device_reported_pass"] and result["host_data_verified"]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
