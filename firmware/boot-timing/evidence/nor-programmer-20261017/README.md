# First ROM-configured NOR programmer evidence

These October 17, 2026 trials established a RAM-only path for updating the first
64 KiB of NOR without CubeProgrammer's failing external-loader initialization.
The helper reuses the ROM's single-line SPI controller setup. Later image-size
experiments are collected separately; this directory stops after the first
baseline write and the following cold-boot INFO check.

| Trial | Observed result |
| --- | --- |
| `nor-info-01` | JEDEC ID `C2 80 3A`, status/security zero, result 0, no WREN. |
| `nor-noop-01` | Requested image equals current image; full 64 KiB readback matches, no changed/erased/programmed sectors or WREN. |
| `nor-crc-refusal-01` | Deliberately incorrect current-image CRC refused with result 18 (`CURRENT_CHANGED`) before any WREN, erase, or program. |
| `nor-program-baseline-01` | Changed/erased/completed masks all `0x0001`; one 4 KiB erase, six 256-byte pages programmed, seven WREN operations. Full 64 KiB readback exactly matches the requested baseline. |
| `nor-guard-after-baseline` | Immediately following 4 KiB at flash `0x10000..0x10FFF` exactly matches the pre-program read. |
| `nor-info-after-baseline-01` | HOTPLUG AP1 access and INFO succeeded after the baseline's autonomous cold boot; result 0, no WREN. Cold-boot waveform evidence is in the separate timing capture. |

The programmer binary is 2,936 bytes, SHA-256
`2dd98e8facd32426b622cb4dc023f4efac5315a7f5d336379066bda43db06909`.
The complete baseline 64 KiB result has SHA-256
`4f22cc11e9819dd499489abb1f3c6a884098c70fcf0e16960b30705c098fa758`.
The prior diagnostic image had SHA-256
`b7fea08c0a192c97964d6c58fc84e49a26df4d4dc1d99e421c402a70fc2d57e5`.

The [trial summary](trial-summary.json) is derived from the preserved status
records. [Guard comparison](guard-comparison.json) independently compares all
4,096 bytes before and after. [Pre-program reader comparisons](pre-program-reader-comparisons.json)
confirm both earlier 64 KiB reads matched the diagnostic reference byte for
byte. The guard covers the immediately following sector only; this is not a
comparison of the entire NOR device.

Raw programmer logs, command/status binaries and request/result JSON are copied
without edits. Build manifests, our small helper binaries, disassembly,
stack reports and matching source snapshots make the reviewed code identifiable.
The host runner is a collection-time snapshot; individual calls are recorded in
each trial's `calls.jsonl`. The `usb-recovery` logs preserve the earlier successful
pipe recovery and subsequent target-register read, described in the
[recovery note](../../stlink-recovery.md).

[Provenance](provenance.json) records source paths, byte counts, SHA-256 hashes,
original modification times and Windows attributes. Copies preserve those
times/attributes. All raw NOR content buffers remain local; their hashes and
sizes are recorded without publishing their contents. Collection performed no
hardware access.

These are controlled bench results with the documented hardware and clocks.
They establish the tested success and CRC-refusal paths, not recovery from
power loss during an erase/program or exhaustive fault testing. No target
reset or power cycle is an automatic response to a programmer failure.
