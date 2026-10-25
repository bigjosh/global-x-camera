# Recorded native-SD edge fixtures

These are bounded clips of the October 25, 2026 **phase01** Saleae recording:
four-bit native SD at 25 MHz, NEGEDGE, before the 27-ohm clock resistor was
added. The source acquisition was 250 MS/s, with 4 ns time quantization.
This is a deterministic pattern-write experiment, not an exported scene.
Only one complete 512-byte payload is included; the final-stop clip contains
no data-block payload.

| Fixture | Source time range | Important observations |
|---|---|---|
| `first-write.csv.gz` | 0.422550000–0.423062900 s | CMD55 → ACMD23(3730) → CMD25(LBA 14920), one block with four valid CRC16s, accepted token, 244.104 µs DAT0 busy |
| `final-stop.csv.gz` | 0.639660000–0.640800000 s | CMD12/R1b, 854.604 µs DAT0 busy, CMD13 reports PRG followed by READY/TRAN |

The final busy starts at 0.639673576 s and ends at 0.640528180 s. It begins
**before** the CMD12 response starts at 0.639673828 s. A decoder which starts
observing DAT0 only after decoding that response will miss the real start.
The first-write busy edges are 0.422818496–0.423062600 s. Busy durations here
use actual DAT0 edge samples; clock-sampled decoders may place both edges
a few samples later while obtaining the same duration.

## Format and source binding

Each gzip contains ASCII CSV with columns
`sample,clk,cmd,d0,d1,d2,d3`. `sample` is an **absolute** 250 MHz source-capture
sample index, so time in seconds is `sample / 250000000`; it is not a
clip-relative index. The first row establishes all six initial levels, then
each event row gives their levels after all transitions at that sample. The
final snapshot preserves the clip end. No interpolation, clock deglitching,
resampling, or CRC-dependent selection of edges was applied.

The channel map is CLK=2, CMD=3, DAT0=7, DAT1=4, DAT2=5, DAT3=1. Default data
width must be set to four bits when decoding these clips because earlier bus
width negotiation is outside their selected ranges. Use zero sample offset
for the recorded first-block CRC comparison. `manifest.json` binds the source
binary exports and both compressed/uncompressed fixtures by SHA-256, and
records exact expected sample counts, commands, payload hash and busy edges.
Instrument identifiers and local machine paths are intentionally omitted.

The original capture contains some narrow clock pulses. They remain in these
clips; an analyzer must not silently discard them to manufacture valid CRCs.
These fixtures exercise the observed logic-threshold waveform, not analog
signal margins or what another receiver necessarily sampled. They are
separate from the later resistor-qualified and probe-free measurements.

## Regeneration

`../extract_real_fixtures.py` reads the existing native Saleae binary exports
offline and uses NumPy for bounded edge selection. It never connects to the
analyzer, serial port, debugger or DUT. Run:

```text
python tools/saleae-sd-native/tests/extract_real_fixtures.py <phase01/signals/binary>
```

The original private capture is needed only for regeneration; regression
tests use the committed clips. The gzip header is deterministic (`mtime=0`,
empty filename). The first-sector payload hash is independently matched to
the known slot representation `GXR2 + 152 zero bytes + pattern frame + GXRE`.

Run the real-recording regression tests after building the offline replay:

```text
python tools/saleae-sd-native/tests/test_recordings.py --replay <sd_native_replay.exe> -v
```

These tests need only the Python standard library. They verify fixture hashes
and edge counts, command/response CRCs, all four data CRCs and payload preview,
exact raw busy boundaries, CMD12 busy overlapping its response, and PRG to
READY/TRAN status. The first clip ends during the 3730-block transaction;
the test explicitly requires an incomplete-transfer result rather than
mistaking one accepted block for completion of the whole save.
