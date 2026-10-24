# October 24, 2026 — magic slots and progressive SD writing

**Selected firmware: v17d, capture → packed RAW10 magic slot → Standby.** The new fixed-slot format, whole-image preannouncement and write, image retrieval, recovery and shutdown passed the checks below. The fresh comparison establishes essentially unchanged cycle time; the measured energy difference is small and cannot be attributed solely to firmware.

This archive contains 96 selected records, seven exact builds, source files, binaries, disassembly/listings, manifests, protocol tests, instrument exports, readback proofs and compact energy replay data. [Offline qualification](qualification.json) passes 121 terminal proofs, ten image reports and 24 energy intervals. [The index](index.json) binds every retained byte and identifies omitted files. Earlier archives are unchanged.

## Fresh comparison

The same board, card and scene were used for three fresh v16 baseline cold cycles and three v17d candidate cold cycles. Each cycle passed first-attempt warm PE6 UART recovery, exact early park and SBF=1 with no intervening power-off. Complete slot readback and independent PNG decoding passed for all six images.

| Build | Median onset → plateau | Range | Median energy | Range |
|---|---:|---:|---:|---:|
| v16 baseline, before erase | 0.997516 s | 0.796301–1.041987 s | 0.549897 J | 0.444034–0.582389 J |
| v17d magic slots, after erase | 0.998118 s | 0.983274–1.016510 s | 0.536883 J | 0.528532–0.546401 J |

The median time increased by **0.602 ms (0.060%)**; median energy decreased by **13.014 mJ (2.367%)**. There is no demonstrated speed gain. Three samples per group, chronological ordering, scan position and the explicit card erase between groups limit causal or statistical conclusions.

Energy uses the unchanged native-Joulescope onset/plateau method from the earlier baseline. The one-second plateau confirmation energy is reported separately, outside the headline interval. These are measurements of the JS-fed Nucleo branch, including board overhead; they are not isolated MCU or production battery energy. The independent Saleae and JS clocks do not support per-phase energy attribution.

Baseline slots 19/20/21 and candidate slots 3/4/5 were fully retrieved. **Their original camera RAM was lost in Standby, so these six readbacks do not claim comparison to the original frames.** PNG decoding checks the retrieved RAW data. Root separately viewed all three candidate PNGs and observed a discernible illuminated panel and bench without obvious missing rows or gross corruption; the observation and file hashes are retained, separately from automated checks.

## Stored format and actual streaming behavior

Each slot is 3,730 logical sectors, or 1,909,760 bytes:

| Offset | Content |
|---:|---|
| 0 | Four bytes `GXRS` |
| 4 | 1,909,600 bytes of packed RAW10, 1120 × 1364 pixels |
| 1,909,604 | Four bytes `GXRE` |
| 1,909,608 | 152 zero padding bytes |

There is no superblock, per-image metadata or payload checksum in this prototype format. The markers indicate completion, not integrity or atomicity under power loss. The card's SCR reports erased byte **0x00**. Its reported capacity permits 32,843 slots; this is geometry, not a capacity/retention qualification.

The driver preannounces 3,730 sectors with CMD55 + ACMD23, then uses one CMD25 stream for the whole slot. It uses IDMA when the complete buffer is already available and progressive PIO when the producer is still supplying data. Commit/deinitialization gates remain required before shutdown.

**The current first published prefix is 89,600 bytes, not the ideal first 512-byte sector.** Conservative LINE-based publication and holdback remain. In the normal short-exposure cold runs, the frame is already complete by the time SD initialization finishes; those runs do not establish capture/write overlap. Earlier SD readiness and finer publication are future optimization opportunities, not measured improvements here.

## Separate long-exposure RAM experiment

The long test used the exact `ram-long-v17d` diagnostic build with sensor coarse exposure 30,000, reported exposure **230,597 µs**, frame length 32,000 and margin 68. This is a RAM-driven test, not a normal cold-boot benchmark or a separate energy result.

| Event | Time since RAW operation begin |
|---|---:|
| SD initialization begins | 191.115088 ms |
| SD ready | 217.863135 ms |
| First write submitted | 421.858735 ms |
| Frame complete | 431.309950 ms |
| Payload complete | 1262.330675 ms |
| Commit complete | 1262.335368 ms |
| SD deinitialized | 1262.394558 ms |

SD was ready **213.446815 ms before frame completion**, and the first write started **9.451215 ms before frame completion**. Progressive mode began with 89,600 available bytes and completed all 3,730 sectors with no producer errors. The complete SD image matched the retained camera RAM byte for byte.

Twenty immediate 512-byte snapshots of published tails matched the final retained frame: 10,240 checked bytes. There were 21 LINE events; the first published zero bytes, followed by 89,600-byte steps up to 1,792,000 bytes before FRAME. LINE spacing was 0.489320–0.490610 ms. This is empirical sampled visibility evidence, **not an architectural AXI-drain guarantee**. DWT timestamps include software/interrupt latency and are not wire-level SD timestamps.

Both short and long deterministic frames independently decode to the previously acquired native16 sensor-pattern reference. Their RAW SHA-256 is `5edaa1705f76b8434993271c86e71d5d83bce1c0ec7272caeec9564594279c1e`. A separate awake flash scene capture also matched all SD bytes to its retained original RAM. After the later captures, the entire original slot 0 was reread byte-identical, including both markers and padding; the preservation report retains its original `preservation` comparison classification.

## Erase failure and bounded recovery

The first FORMAT attempt remains recorded as **failed**. CMD38 inherited the SCR transaction's two-second hardware timer. After timeout the card reported READY/TRANSFER and DAT0 HIGH, while the host DPSM stayed active. A debugger ICR-write attempt did not establish recovery and is retained as failed evidence.

A separately reviewed, exact RAM helper issued three CMD13 operations, including a host CMDSTOP abort, then verified card and host idle. It did not reset the card, switch power, change DTIMER, send a card-data write or alter the original failed FORMAT proof. The production erase path was then corrected to select a hardware timer covering the requested timeout at a slow SD clock, restoring settings only after verified idle.

A second explicit ERASE with `ram-magic-v17d` passed. Twenty SCR-bound probes, including early slots, middle and end sectors, were entirely zero. These samples do not verify every card sector and do not retroactively qualify the first FORMAT attempt. The v17d flash binaries are byte-identical to the reviewed v17c flash binaries; only the RAM builds include the reachable FORMAT change.

## Qualification limits and final bench state

All measured baseline/candidate events 1–9 decode directly by pulse width. The final pre-WFI pulse remains unknown and strict decoding remains failed. The awake test also had an unclassified 8.44 µs initialization pulse; no tolerance was widened and no unknown pulse was relabeled. Intervals requiring an unknown endpoint remain unavailable. SBF and image evidence provide independent completion qualification.

Final source suites passed **95 tests**: capture 65, slot system 17, SD driver 2, recovery 11. Scratch support/privacy suites passed another 16, for **111 recorded tests**. Negative checks cover malformed slot data, geometry/guards, unsupported recovery identities and accidental retention of renamed image payloads. No additional on-hardware fault injection or arbitrary power-loss qualification is claimed.

Installed v17d Standby sector SHA-256:

`2ad7168302fe05b928b2b1aa62ef9732dfeab0d61e6092de2c086412d4485880`

Early recovery prefix SHA-256:

`44c3425ea8e22c06168d8a8d0b65ae7813a0cad147a6d06ad18278f71bd4b9c2`

The full programmed 64 KiB matched, and the following 4 KiB remained unchanged. The recovery code/literals are preserved; only the expected early-image CRC words differ from v16.

At **2026-10-24 17:56:22.939300 UTC**, the final normal cold boot reached the low-current plateau at **4.892311 V / 8.075647 mA**. JS110 stopped cleanly and restored range 128 with power left on. Root confirmed COM8 closed, BREAK released, Logic 2 running and no active bench helpers. The first sector of slot 6 had been verified erased before this final boot; **the final expected slot 6 and its SBF were not reread**, and this handoff cycle is excluded from the A/B groups.

## Offline replay and inspection

From the repository root:

```powershell
python firmware/capture-raw/evidence/2026-10-24-magic-slots/replay.py
python firmware/capture-raw/evidence/2026-10-24-magic-slots/materialize.py --record candidate-analysis-final --out tmp/magic-analysis-review
python firmware/capture-raw/evidence/2026-10-24-magic-slots/materialize.py --build flash-magic-standby-v17d --out tmp/magic-build-review
```

These commands do not access hardware. Materialization requires a new output directory. Exact source, code, protocol/guard snapshots and deterministic pattern bytes are preserved. Scene pixels and their previews are omitted; scene comparison results remain hash-bound historical evidence. The pre-pack privacy audit classified 2,048 retained non-pattern binaries; replay rejects unknown binary filenames, unreviewed code bytes and image-bearing scan buffers.

Compact native-sample sums replay interval energy integration, not the omitted raw-sample boundary classification. Pure archived validators avoid importing instrument/bench runners. The initial replay's tool-relative codec import was corrected to load the archived pure marker parser; the preservation comparison retains its recorded classification. These were offline archive repairs, with no firmware or measurement change.

Index SHA-256: `1b6bbab5c4821deb86b2dba0ac6e6cbeff1f6bb0c53531df228c26d270a4028e`.

Replay SHA-256: `3d43969b3f547e97df0992ee47a1a13c70df823f80241bdbbffcf709ccffad4d`.

Qualification SHA-256: `5151173427f20a9044d9a36bcd6d69c1e93cae0bb12d1e8b2ff19ce9d6c7acc9`.
