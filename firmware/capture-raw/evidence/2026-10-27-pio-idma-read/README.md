# Repeated sector reads: PIO versus IDMA, October 27, 2026

**PIO and IDMA produced exactly the same corruption at 25 MHz.** Three
attempts per mode all failed data CRC. A fresh 12.5 MHz PIO read of the same
sector passed and matched the historical verified pattern. With the camera
held in reset throughout, this strongly disfavors CPU FIFO servicing or
camera activity as the explanation.

The next control is to repeat the same binaries with **both CLK and CMD
probes attached**. The user reports that combination worked reliably before;
neither probe has been independently isolated. This control is pending user
confirmation of the connections. It is not included in the results below.

## Measured results

All reads used LBA 0, one 512-byte sector, four-bit native SDMMC2, falling-edge
host launch during identification and transfer, unchanged local-pad receive
feedback, GPIO speed3, inherited compensation and hardware flow control.
The card remained powered. The reported hookup had no LP8 signal probes and
a 27-ohm series CLK resistor nearer the card following a wire extension;
physical geometry was not independently inspected.

| Profile | Attempts | Result | Retained data |
|---|---:|---|---|
| 12.5 MHz PIO reference | 1 | Complete success | All 512 bytes match historical same-card pattern |
| 25 MHz PIO | 3 | DCRCFAIL on CMD17 data | Identical corrupted 512 bytes in every attempt |
| 25 MHz IDMA | 3 | DCRCFAIL on CMD17 data | Identical to all three PIO buffers |

Order: reference, PIO1, IDMA1, IDMA2, PIO2, PIO3, IDMA3. Warm UART recovery
separated the 25 MHz attempts, with the exact installed early park checked
before loading each helper. There was no automatic retry or clock fallback.

All six failures retained STA=2 (DCRCFAIL), DCOUNT=0, SD error14/stage5/CMD17,
RAW result1038 and cleanup_error10. There was no reported RXOVERR, timeout,
IDMA error or CPU fault. PIO recorded128 serviced words; IDMA's zero successful
word count on failure is bookkeeping, **not** evidence that its destination
was untouched. Each destination was prefilled with0xA5, and all512 retained
bytes were retrieved. Camera-reset, GPIO speed, immutable-code, final-proof
nonce and CFSR/HFSR checks passed.

Correct reference SHA256:
`fa6a9fc6d2fdd48e921c7a3b2d794e78477934056895190cc78449c4fcb05598`

Every failed buffer SHA256:
`99acb3960c29159b74c99b3b4c1a6700e09c5c85f7cacb63eb508e6a70eb0429`

## What the retained bytes tell us

Relative to the correct sector,323 of512 bytes differ. The complete failed
payload exactly fits deleting ten four-bit symbols from the expected data,
then appending the first ten symbols of the correctly calculated four-lane
SD CRC16. Those final five received bytes are `55 4A 5C AB C7`.

The zero-based omitted symbol positions in that model are
`143, 145, 149, 151, 303, 309, 623, 629, 954, 960`. The alignment is unique
within the tested deletion-only model; that does not make the physical
explanation unique. See [the complete analysis](reports/analysis-complete01.json).

The shared result points toward a failure before, or common to, the choice
of CPU versus IDMA draining the receiver. It does **not** establish whether
the card sees extra clock transitions, the MCU misses transitions, or some
other shared controller/timing mechanism causes the shift. It does not prove
reflections, analog voltage margins or CMD sensitivity. The user-observed
successful arrangement includes both probes and their ground connection;
reconnecting that arrangement does not isolate capacitance from return paths.

## Diagnostic implementation and limits

`--sd-read-diagnostics` is opt-in and RAM-only, restricted to a one-sector
READ at12.5 or25 MHz. CAPTURE and FORMAT are rejected. The camera is held in
reset without starting I2C or acquisition. It snapshots status before the
existing abort path, retains the destination on failure, and leaves CRC,
completion, ownership and cleanup checks intact. Default installed firmware
does not include this option and was not changed.

The N6 has no FIFOCNT register. Recorded FIFO fields are STA flags, not an
occupancy count; no reserved register or extra FIFO data read was added.
The snapshot is sequential rather than atomic: STA is the loop observation,
while DCOUNT/control reads occur after the existing command-transfer clear
and before abort. It is not an analog waveform or per-clock trace.

Failed records remain failed even though later card fields report
media_idle1/initialized0/controller_owned0. Their cleanup_error10 is retained;
these are not ordinary successful-idle proofs. Recovery after these failures
used the user's existing explicit experimental-board reset authorization.

Offline validation passed195 capture tests,31 driver tests and11 runner
tests. Disabled diagnostics preserved every allocatable ARM section across
eight driver profiles and all seven checked normal firmware artifacts.
The analyzer tests include1530 exhaustive small alignment cases.

## Evidence and reproduction

- [Scope](scope.json), [file index](archive-index.json) and
  [exact build commands/hashes](reports/build-results.json).
- `builds/`: three exact binaries and manifests; `build-inputs/` and
  `host-source/`: frozen project sources needed to understand/reproduce them.
- `attempts/`: all seven operation records, target snapshots and512-byte
  data; `reference/`: historical pattern bytes and provenance.
- `recovery/` and `status/`: recovery/park records and instrument context.
- `replay/analyze_reads.py`: offline analysis; `replay/run_read.py`: the
  explicitly gated hardware runner. Offline replay requires no instruments.

From the repository root, using Python 3, replay the archived sector analysis
without creating Python cache files:

```powershell
python -B firmware/capture-raw/evidence/2026-10-27-pio-idma-read/replay/analyze_reads.py --campaign firmware/capture-raw/evidence/2026-10-27-pio-idma-read/attempts --out tmp/pio-idma-replay.json
python -B firmware/capture-raw/evidence/2026-10-27-pio-idma-read/replay/archive_results.py verify
```

The output report must be a new filename. [Offline replay and runner tests](addenda/offline-verification/selection.json)
passed. The [driver-source provenance](addenda/driver-qualification/normalization-provenance.json)
confirms the driver identity record and all final frozen inputs differ only
by CRLF-to-LF conversion, with no intervening code change.

[Final closure](addenda/final-status/evidence/closure.json) records the clean
Joulescope exit at 05:15:56.096 UTC, range128 restored, target power left on
at the exact early park, and the pending probe connection. The original
`scope.json` retains the initial unsealed/partial-log snapshot; final
`archive-index.json` and `SHA256SUMS` identify the complete sealed archive.

Compiler ELF/object files, the full vendor SDK and the full historical image
chunk are omitted. Build manifests retain pinned dependencies and paths.
The synthetic first-sector pattern is sufficient for the byte/CRC analysis.

No image capture, SD write/erase, NOR programming or power cycle occurred in
this comparison. The installed normal25 MHz firmware remains unchanged.
The target was returned to the exact UART early park `0x3418078C`, nine good
pulses/zero bad, before requesting probe reconnection. No tests may run during
that physical change. See [the live checkpoint](../../../../AGENTS.md) before
resuming; this report is evidence, not a current instrument-ownership lease.
