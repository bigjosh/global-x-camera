"""Offline replay of the isolated probe's deterministic integer/SRAM workload.

Reads saved successful proof only. Never imports a hardware runner.
"""
import argparse
import json
from pathlib import Path


def expected(iterations):
    if iterations <= 0 or iterations % 256:
        raise ValueError("Expected a positive count of complete 256-iteration batches")
    mask = 0xFFFFFFFF
    words = [(0x9E3779B9 * (i + 1)) & mask for i in range(256)]
    value = 0xA5F13579
    for _ in range(iterations // 256):
        for i in range(256):
            value ^= (value << 13) & mask
            value ^= value >> 17
            value ^= (value << 5) & mask
            words[i] ^= value
            value = (value + words[i]) & mask
    return value


def check(path):
    saved = json.loads(path.read_text())
    if saved.get("passed") is not True:
        raise ValueError(f"Not a successful run: {path}")
    proof = saved["proof"]
    got = proof["CHECKSUM"]
    want = expected(proof["BUSY_ITERATIONS"])
    return dict(path=str(path), iterations=proof["BUSY_ITERATIONS"],
                checksum=got, expected=want, passed=got == want)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    results = [check(p) for p in args.paths]
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)
