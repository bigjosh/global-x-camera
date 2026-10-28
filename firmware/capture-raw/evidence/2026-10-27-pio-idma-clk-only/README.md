# CLK-only probe control, October 27, 2026

**Removing the CMD probe while keeping CLK and analyzer ground connected
preserved six successful reads.** All six matched the correct 512-byte sector
using the same PIO25/IDMA25 executables as the preceding conditions.

**CLK was a direct jumper with no series resistor throughout all compared
conditions.** The user's clarification supersedes the resistor assumptions
in the earlier sealed reports; see the [wiring correction](../2026-10-27-sd-wiring-correction/README.md).
Those reports' original bytes remain unchanged.

| Condition | PIO at25MHz | IDMA at25MHz | Sector data |
|---|---:|---:|---|
| No LP8 signal probes | 3/3 CRC failures | 3/3 CRC failures | Identical corrupted buffer |
| CLK and CMD probes plus analyzer ground | 3/3 passes | 3/3 passes | Exact reference match |
| CLK probe plus analyzer ground; CMD probe removed | 3/3 passes | 3/3 passes | Exact reference match |

The first two rows are the [probe-free](../2026-10-27-pio-idma-read/README.md)
and [joint-probe](../2026-10-27-pio-idma-probe-control/README.md) archives.
This archive freezes only the third condition. The user reported removing
only CMD and leaving other wiring unchanged; geometry was not independently
inspected.

## Results and limits

Order was PIO1, IDMA1, IDMA2, PIO2, PIO3, IDMA3. All reads addressed LBA0,
one512-byte sector, native four-bit25MHz. Falling-edge host launch,
GPIO speed3, inherited compensation, receive feedback and hardware flow
control remained unchanged. The sensor was held in reset.

All attempts returned STA256(DATAEND), DCOUNT0, result0, SD error0 and
cleanup_error0. Each reported one sector read, zero sectors written and
released controller ownership. Camera-reset, exact code, nonce and CPU-fault
checks passed. Retained snapshots equaled independent sector downloads,
and every trial ended with a fresh exact successful-idle proof. No retries
or clock fallback were used.

All six512-byte SHA256 values were:

`fa6a9fc6d2fdd48e921c7a3b2d794e78477934056895190cc78449c4fcb05598`

The [three-condition analysis](addenda/clk-only/evidence/analysis-complete.json)
binds both earlier sealed reports and all six current operation records.

These isolated reads did not require the CMD probe. **That does not rule
out a CMD-probe effect during a full capture/write cycle.** CLK-probe loading
is still combined with the analyzer ground/return connection. This is not
full-image write/read qualification, an analog timing-margin measurement,
or proof of reflections or another electrical mechanism.

## Evidence and replay

`addenda/clk-only/attempts/` contains complete status, bytes and terminal
proofs. `builds/` contains the exact original binaries/manifests; source-map
paths resolve in the original read archive. [Preceding-evidence bindings](preceding-evidence.json)
identify both sealed histories and the wiring correction.

From the repository root, replay using Python3 and a new output filename:

```powershell
python -B firmware/capture-raw/evidence/2026-10-27-pio-idma-clk-only/replay/analyze_clk_only.py --campaign firmware/capture-raw/evidence/2026-10-27-pio-idma-clk-only/addenda/clk-only/attempts --out tmp/clk-only-replay.json
python -B firmware/capture-raw/evidence/2026-10-27-pio-idma-clk-only/replay/archive_results.py verify --out firmware/capture-raw/evidence/2026-10-27-pio-idma-clk-only
```

[Closure](closure.json) records the final UART early park at06:03:33.708UTC,
PC0x3418078C, exact installed prefix, nine good pulses/zero bad, COM8 closed
and no active helpers. Target power was left on. No new Joulescope/Logic
session, power cycle, camera capture, card write/erase or NOR programming
occurred. The next ground-only condition is separately recorded and is not
part of these six trials. Consult the [live checkpoint](../../../../AGENTS.md)
before operating the bench. `archive-index.json` and `SHA256SUMS` bind the
final archive bytes.
