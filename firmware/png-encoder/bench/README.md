# Compute-only PNG experiments in RAM

This separate harness benchmarks the same fixed RAW fixture without linking a sensor, filesystem, SD driver or NOR-command implementation. It leaves the installed v66c sector alone. Exact scalar and separately reviewed MVE builds were qualified on the MCU on October 24; see the [frozen results and replay](../evidence/2026-10-24-mcu-tuning/README.md). A new build remains unqualified until its own controller and hardware run are checked. This harness does not broaden ordinary capture/SD maintenance permissions.

The existing frozen `low_power/readback_recovery` bootstrap can first establish expanded SRAM and the reviewed 400 MHz ROM clock profile from an exact early UART recovery park. Its low-SRAM code and stack lie **inside** the eventual RAW upload. The next mandatory step is to load this harness, run its PREPARE entry, and verify its exact high-SRAM READY park, fresh nonce, caches-off context and live code. Only then may the host upload the fixture to `0x34000000` and its eight `0x504E4700+i` guard words immediately afterward. The fixture upload intentionally replaces the no-longer-executing low recovery/bridge memory; it must never occur while the bridge is still running or parked there.

| Region | Bounds |
|---|---|
| RAW10 fixture | `0x34000000..0x342E9F00`, 3,055,360 bytes; then 32 guard bytes |
| Code/data/workspace | `0x34320000..0x343A0000`; executable at most 128 KiB |
| Stack, MSPLIM and bottom canary | `0x343A0000..0x343B0000` |
| Independent PNB1 report | `0x343E0000`, 512 bytes |
| Request | `0x343E0800`, 64 bytes |
| Cumulative output intervals | `0x343E1000`, up to 100 × 32 bytes |
| Existing LPL/LPM/SAVE ownership | `0x343F9xxx`; untouched |

`entry.S` provides separate prepare and encode entry points and branch-to-self parks. Every RUN starts with fresh report/nonce state and uncached prerequisite checks. It checks the exact fixture FNV, enables D/I cache only after adopting neither from the caller, encodes, cleans/disables owned caches, checks the fixture and canaries again, and publishes DONE last. A bad initial context is refused without cleaning/disabling a caller-owned cache. The scalar compiler flags prevent FP/MVE context changes; CONTROL must stay zero and is never silently normalized. A future MVE version requires separate context-return review.

The sink counts every output byte and computes FNV-1a. Its expected output length and digest must come from an independently decoded host result for the same encoder source, mode and RAW fixture. This is a benchmark integrity check, not a cryptographic proof or a substitute for eventual MCU PNG readback. Sink time is measured separately: `cpu_cycles = encode_cycles - png_callback`, with the encoder's disjoint conversion/DEFLATE/framing/other counters also retained. Each 32 KiB output boundary records cumulative elapsed cycles and measured sink-body cycles. Those interval CPU estimates omit the measured sink body; unlike the final parent-timed total, they retain callback entry/exit overhead. Final partial intervals are recorded too. Hashing/cache effects and timing instrumentation still perturb the computation, so compare variants under the same harness before estimating production performance.

The cooperative 4,000,000,000-cycle deadline is checked in callbacks; it is **not an interrupt watchdog**. The host must enforce its own bounded polling and stop on a missing/failed proof. No retry, reset, power operation, arbitrary PC or SD operation is supplied by this directory. A new host controller must verify exact READY/DONE park and code, nonce/request/report, disabled caches, inactive lazy FP, guarded SRAM extents and output intervals before another write. Do not forge camera/SAVE proofs or remove the existing LPL/LPM records to reuse `capture-sd/bench.py`.

Build offline using the bundled Python runtime:

```powershell
python firmware/png-encoder/bench/build.py --out tmp/png-bench-20261024/candidate-os --optimization Os
python firmware/png-encoder/bench/build.py --out tmp/png-bench-20261024/candidate-o2 --optimization O2
python firmware/png-encoder/bench/test_sink.py
python firmware/png-encoder/bench/test_target.py
```

`--source-dir` accepts a separate source tree with `png16.c/.h`, `png16_miniz.c`, `miniz_config.h` and `vendor/miniz/`. Every build copies and hashes the exact inputs into a new directory; existing builds are never overwritten. The manifest exports both entries/parks and all memory bounds. `protocol.py` is a pure codec/validator for a future reviewed host controller, not an instrument runner.

The intended current fixture is `tmp/bringup/sd-normal-20261024/awake02-frame/raw.bin`, SHA-256 `ba0e69552271a93a743ebe0778c30fcdfc168532955129eae8312e3cbf7936d3`. It contains 1,527,680 right-aligned little-endian RAW10 samples at 1120 × 1364. Its corresponding v64 PNG had exact pixel verification. The production comparison must separate CPU encoding, card payload throughput, initialization/metadata/card-busy time and energy; a compute-only test has no direct SD-throughput or full-cycle energy claim.
