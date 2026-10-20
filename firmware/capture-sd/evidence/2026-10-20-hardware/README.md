# Capture-to-SD hardware evidence — October 20, 2026

This archive preserves the installed v50 awake firmware, its exact v8b save
module and build inputs, hardware qualification records, and reproducible
energy analysis. It contains **no camera images, RAW frames or SD sector
contents**. PNG verification records contain hashes and comparison results.
The finalized JS110 power recording is included as gzip for energy replay.

## Exact firmware

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Raw recovery prefix | 5,140 | `8a65df7b36a0c9a0c80e25c4a1000d4bae914ce9d3a46e5ff83e5454cdf109f7` |
| Receiver | 14,996 | `303f3989db133c818e8890c098b843ebc96d712a313e64e733e225706172acca` |
| PNG/FAT32 save module | 27,420 | `91e1edfa43f95a9608b94457cfbf900c6f51d5ecd10d2b3b7667c84d40cd3844` |
| Complete first NOR sector | 65,536 | `9ffc2c1cbaacf9f60258343ac6a061b35fb62f8b62b42c1a5b50ccc5f432f5cd` |

The ROM-wrapped prefix is 6,176 bytes; 5,140 is the raw size used by the recovery
allowlist. The first 2,816 prefix bytes and all 62 reviewed early literal loads
match v45b/v46. The early recovery park remains `0x3418078c`, instruction `fee7`.
The save module starts at `0x34320000`, defaults to fast-none mode 1 with D-cache
enabled, and is loaded only after capture and sensor STOP. Completion stays
awake. Original build-time `hardware_status: untested` fields are preserved:
the separate result records establish later hardware qualification.

## Hardware records

`results/` includes the earlier v4 FIFO failure, independent card-ready proof,
successful v5 format/save, cache and encoder comparisons, and exact PNG
readback metadata. The v50 records include full NOR write/readback verification,
independent readback and following-sector checks, automatic cold-save reports,
full host PNG equality metadata, and the exact PE6 recovery-park proof.

The full `IMG00024.PNG` readback was 869,254 bytes, SHA-256
`58666a754ae3e646efb75dbb5179e31f85921cb0b10629a25875dc194f60b9dd`.
Every PNG chunk CRC passed; all 1,527,680 grayscale16 samples exactly matched
the corresponding RAW10 samples shifted left six bits, with `sBIT=10`.
This is evidence for that complete file. Other successful save reports are
not automatically full host readback claims.

The recovery proof checks exact live prefix bytes, CPU context, both caches
disabled, and idle XSPI. It observed nine good PE6 pulses and zero bad pulses
in the unchanged nominal 100 µs guard window. UART/cold-cycle signal statistics
are compacted; their original file hashes are retained. Only the exact park
proof establishes selected firmware recovery.

Four normal cold saves completed as `IMG00024.PNG` through `IMG00027.PNG`,
with a verified early VCP recovery between normal runs. The first saved
`IMG00001.PNG` was also reread after v50 integration and remained byte-identical
to its original SHA-256
`466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330`.
That is a preservation check during these ordinary operations, not a power-loss
test.

The [final bench state](results/final-state.json) records the target left
powered, awake at the completion loop `0x343022d8`, with LEDs off, SD idle
and deinitialized. The debugger inspection explicitly resumed the CPU.
At 06:55:51.077813 UTC the JS110 helper stopped cleanly and restored starting
range 128; its final input reading was 4.88184 V and 80.1278 mA. COM8 was closed
and BREAK released. This awake idle is not low-power shutdown, and JS IN+
does not prove a separately isolated DUT rail.

## Verify and rebuild

Run from this directory using Python 3:

```powershell
python verify.py
python rebuild.py --toolchain <matching-STM32-toolchain-tools-root> `
  --out <new-local-output-directory> --execute
python energy-analysis/replay_energy.py
```

`verify.py` checks the complete inventory, original/archived hashes, firmware
layout, memory bounds and decompressed power-stream identity. `rebuild.py`
checks the pinned compiler/runtime/header hashes and compiles the three payloads
from archived sources and headers in a new directory. It uses no original
ignored build or vendor checkout. The matching Windows GCC 12.3.1 toolchain is
an external prerequisite and is not redistributed. Exact sector padding is
retained as immutable source data.

A relocated archive build reproduced the raw prefix, receiver, module, wrapped
prefix and complete sector byte-for-byte. The verification record is archived
under `verification/`. The ordered compile/link recipes and source map are in
`archive-plan.json`; original absolute paths in frozen manifests are historical
provenance, not dependencies of the archive rebuild.

## Energy evidence and limits

See [the energy analysis](energy-analysis/README.md). Replay validates all
21 strict comparison runs and 18 COMPLETE-duration windows against the finalized
power recording. Its uncompressed SHA-256 is
`a78b316350d47d6d0cf6666317db02bd1369651909edc126deab5392b20f82e9`.
The primary recording is 108,442,748 bytes, compressed to about 8.3 MB.
Exact operation JSONs retain their original hashes for replay.

No private frame bytes are needed for energy-only replay. It checks the target
frame FNV recorded in the reports; the private RAW SHA remains provenance and
cannot be recomputed without the private file. Full PNG/pixel verification
metadata is retained separately.

COMPLETE includes cache teardown and a deliberately uncached frame check;
TOTAL ends earlier. Neither is a complete cold power-to-save measurement.
Energy is bounded using host timing and stated UTC uncertainty, without
electrical phase markers. The JS boundary includes board overhead and does
not establish isolated production-camera consumption. Arbitrary power loss,
regulator-off shutdown, long retention and recovery from every warm/reset
state remain unqualified.
The current RX-abort cleanup drains at most 64 words of the 256-word FIFO;
uncertain cleanup fails closed and is not qualified for automatic retry.
