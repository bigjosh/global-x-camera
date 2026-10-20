# ST-LINK VCP recovery and SD smoke-test evidence — October 20

**v45b is programmed and PE6-only recovery has worked after a cold cycle and a
subsequent warm reset.** The exact early park, live prefix, CPU/cache context,
and idle XSPI state passed the host checks. Read-only NOR INFO then succeeded
with zero WREN commands. Normal camera capture remains unqualified for this
exact firmware.

**The SD connection also passed:** the card reports 62.7 GB and both tested
sectors matched at 100 kHz, 12.5 MHz and 25 MHz. No SD writes were performed.
See [the SD results](sd-results/README.md) for the wiring retries, corrected
receive-completion check, exact helper identity and remaining benchmark limits.

This archive's `build/`, `programming/`, `parks/`, `nor-info/`, `signals/`, and
`failures/` directories cover VCP recovery and boot NOR only. SD outcomes are
maintained separately under `sd-results/` by the bench controller. **No SD card
sector contents or raw SD record/status dumps are included.** The archived
`capture_sector_0.bin` is compiled boot firmware, not data read from the SD card.

## Observations and limits

| Operation | Result |
| --- | --- |
| v45b programming | Complete 65,536-byte readback matched the compiled sector; following 4,096 bytes unchanged |
| Normal cold boot | AP1 access unavailable afterward; no qualified camera-capture result |
| First two warm requests with zero bytes | AP1 access unavailable after both |
| First warm request with `0xC0` | AP1 access unavailable afterward |
| Cold request with `0xC0` | Exact park passed; PE1 HIGH and request-source bits 2 establish PE6-only selection |
| NOR INFO from recovery | Result 0, zero WREN, no erase or page programming |
| Subsequent warm request with `0xC0` | Exact park passed again, with PE1 HIGH and source bits 2 |

Use **1 Mbaud, 8N1, repeated `0xC0`** for the currently successful stimulus.
It provides about 7 microseconds LOW and 3 microseconds HIGH, both within the
installed detector thresholds. The longer HIGH interval provides more sampling
margin than the original zero-byte proposal. The detector is a pulse-signature
test, not a full UART decoder or authentication mechanism.

Both successful records contain 153 polls and nine valid pulses within the
existing nominal 100 microsecond observation deadline. The cold run averaged
about **0.641 microseconds per poll** from its first to last sample; this does
not bound the maximum interval. It selected recovery about 38.41 microseconds
after guard start. The subsequent warm run selected after about 31.63
microseconds. Neither result establishes a guaranteed retry rate or timing
bound. The three earlier failed requests are preserved, and their cause is
unestablished.

The explicit observation deadline remains 40,000 nominal 400 MHz cycles.
Total boot cost is not unchanged: the wrapped prefix grew **480 bytes**, from
5,696 to 6,176 bytes, and diagnostic stores/copies add execution work.
BREAK controls NRST on this measured ST-LINK firmware, not PE6. All maintenance
requires exact park verification; do not reset during an active or uncertain
storage write.

## Contents and identities

| Item | SHA-256 |
| --- | --- |
| Installed 64 KiB sector | `2323caa6b0ef142a6f46adbfdb078f9070877f7665f97337145de75eec60b3d2` |
| Raw 5,140-byte prefix | `a8aebf4ed32d735d6352e9d5267759ed7b2c6733ac1a87bd4a0926a51c17e08a` |
| Byte-identical v44 receiver | `478680d7ca87b19a0bcbab208535b36ab1fd985e141ce69a86b3602963a621ac` |

- `build/` preserves the manifests, frozen prefix sources, generator sources,
  disassembly, symbols and exact binaries. Receiver source/header dependencies
  remain in the previous [v44 archive](../2026-10-18-phase-leds/README.md); this
  compact archive is not a new standalone toolchain/vendor bundle.
- `programming/verified.json` and selected CLI logs preserve programming
  evidence. The preparation script independently compared the full local
  readback with the archived firmware and verified the following 4 KiB.
- `parks/` retains both complete successful park records, raw status/proof
  buffers, live prefix, register evidence and CLI logs.
- `signals/` contains compact analog and pulse statistics, request configuration
  and host events where available. Full CSV, `.sal`, and multi-megabyte interval
  JSON remain local; their paths, sizes and hashes are indexed.
- `failures/` preserves the failed AP1 attempts and a concise failure summary.

`source-index.json` records original and archived sizes/hashes separately.
Text is normalized to UTF-8 with LF newlines. Windows CLI logs requiring
CP1252 decoding record that conversion explicitly. Binary artifacts are
byte-identical. The raw signal helper emitted a stale generic limitation
claiming no detector/cold test; each compact summary explicitly corrects it
and refers to the separate park records for qualification.

The original working directory is `tmp/bringup/vcp-install-20261019/`; its name
identifies the session, not the local date of every operation. Large raw
waveforms and local readback buffers are intentionally not republished.

Verify both archived evidence indices without hardware:

```powershell
python firmware/capture-timing/evidence/2026-10-20-vcp-sd-smoke/verify_archive.py
```

`prepare_archive.py` uses an explicit VCP/NOR allowlist and does not inspect
or overwrite `sd-results/`. Its output index covers only that subset.
The verifier separately checks the selected SD result index and compiled helper.
