# Ground-only reversal, October 27, 2026

**Removing the CLK signal probe while retaining analyzer ground restored
the same six deterministic CRC failures.** The preceding CLK-only condition
passed all six reads. Both used the exact same PIO25/IDMA25 binaries and
one known512-byte sector, with the sensor held in reset.

| Condition | PIO at25MHz | IDMA at25MHz | Retained sector |
|---|---:|---:|---|
| Initial, no LP8 signal probes | 3/3 CRC failures | 3/3 CRC failures | Same corrupted buffer |
| CLK and CMD probes plus analyzer ground | 3/3 passes | 3/3 passes | Exact reference |
| CLK probe plus analyzer ground; CMD removed | 3/3 passes | 3/3 passes | Exact reference |
| Ground only; CLK and CMD signal probes removed | 3/3 CRC failures | 3/3 CRC failures | Same original corrupted buffer |

**CLK was a direct jumper with no series resistor throughout these tests.**
See the [wiring correction](../2026-10-27-sd-wiring-correction/README.md) for
the user's clarification and the superseded resistor assumptions in earlier
sealed reports. Ground was explicitly retained across the final two rows;
the original condition's ground state was not independently established.

The [complete four-condition analysis](addenda/ground-only/evidence/analysis-complete.json)
binds the [initial](../2026-10-27-pio-idma-read/README.md),
[joint-probe](../2026-10-27-pio-idma-probe-control/README.md), and
[CLK-only](../2026-10-27-pio-idma-clk-only/README.md) archives. Their sealed
contents remain unchanged. This archive freezes only the final condition.

## Results and meaning

Trial order remained PIO1, IDMA1, IDMA2, PIO2, PIO3, IDMA3. All addressed
LBA0 at native four-bit25MHz, with falling-edge host launch, GPIO speed3,
inherited compensation, receive feedback and hardware flow control unchanged.

Every failure retained STA2(DCRCFAIL), DCOUNT0, SD error14/stage5/CMD17,
RAW result1038 and cleanup_error10. Camera-reset, immutable-code, nonce and
CPU-fault checks passed. Every complete512-byte failed buffer had SHA256:

`99acb3960c29159b74c99b3b4c1a6700e09c5c85f7cacb63eb508e6a70eb0429`

That exactly matches all six initial failures. Every buffer also reproduces
the previously documented deletion-only model: ten data symbols omitted,
then the first ten correctly calculated CRC symbols appended. This model
describes retained bytes; it does not prove physical missing clock edges.
The fresh12.5MHz reference and successful probe-connected reads have SHA256:

`fa6a9fc6d2fdd48e921c7a3b2d794e78477934056895190cc78449c4fcb05598`

The reversal ties this isolated read failure to the CLK probe connection:
**analyzer ground alone was insufficient, while CLK plus that same ground
passed.** CPU versus IDMA servicing did not change the outcome. It does not
identify capacitance, damping, reflections, thresholds or another analog
mechanism, and physical geometry was not independently inspected.

These are single-sector reads with no camera activity. They do not qualify
full-image writes/readback, establish production timing margin or formal SD
compliance, or rule out a CMD-probe effect during full capture/write cycles.

Failed cleanup remains failed even when later card fields indicate released
ownership. No failed result was used as ordinary successful-idle permission.
The bench owner used the user's existing explicit experimental-board reset
authority for intervening UART recovery. No automatic retry or clock
fallback was performed inside an attempt.

## Evidence and replay

`addenda/ground-only/attempts/` contains complete operation proofs, failed
buffers and target snapshots. `builds/` contains exact original binaries and
manifests; source-map paths resolve in the original read archive.
[Preceding-evidence bindings](preceding-evidence.json) identify all histories
and the wiring correction. `supplemental-recovery-context/` preserves small
inter-trial UART-helper logs for these and the preceding controls; it changes
none of their results.

From the repository root, Python3 can replay without hardware or cache files;
the output filename must be new:

```powershell
python -B firmware/capture-raw/evidence/2026-10-27-pio-idma-ground-only/replay/analyze_ground_only.py --campaign firmware/capture-raw/evidence/2026-10-27-pio-idma-ground-only/addenda/ground-only/attempts --out tmp/ground-only-replay.json
python -B firmware/capture-raw/evidence/2026-10-27-pio-idma-ground-only/replay/archive_results.py verify --out firmware/capture-raw/evidence/2026-10-27-pio-idma-ground-only
```

[Final closure](closure.json) records the exact UART early park at
06:11:43.776UTC, PC0x3418078C, verified installed prefix and nine good pulses
with zero bad. Target power remains on, COM8 is closed/BREAK released, and
no helpers or physical-action question remain active. No new Joulescope or
Logic session, power cycle, camera capture, SD write/erase or NOR programming
occurred. The normal installed firmware is unchanged. `archive-index.json`
and `SHA256SUMS` bind the final bytes; consult the [live checkpoint](../../../../AGENTS.md)
before any later bench operation.
