# CLK and CMD probe control, October 27, 2026

**Attaching both probes changed six reproducible read failures into six
successful reads.** The same PIO and IDMA executables read the same 512-byte
sector at four-bit 25 MHz. Every probe-connected result matched the historical
pattern and the preceding fresh 12.5 MHz reference byte for byte.

| Wiring condition | PIO attempts | IDMA attempts | Data comparison |
|---|---:|---:|---|
| No LP8 signal probes | 3/3 CRC failures | 3/3 CRC failures | Same corrupted buffer in all six |
| CH0 to CMD, CH1 to CLK, analyzer ground connected | 3/3 successes | 3/3 successes | All six exactly match the correct sector |

The first row is the [sealed original comparison](../2026-10-27-pio-idma-read/README.md).
This archive records only the second row. The user confirmed the probe
connections and reported all other wiring unchanged. The CLK series resistor
remained present near the card; wire geometry was not independently inspected.

## Results and interpretation

Order was PIO1, IDMA1, IDMA2, PIO2, PIO3, IDMA3. Every attempt used LBA 0,
one sector, falling-edge host launch during identification and transfer,
GPIO speed3, inherited compensation and unchanged hardware flow control.
The sensor remained held in reset. No waveform was recorded.

All six completed with STA=256 (DATAEND), DCOUNT=0, result0, SD error0 and
cleanup_error0. The card reported one sector read, zero written, successful
cleanup and released ownership. Camera-reset, immutable-code, nonce and
CPU-fault checks passed, followed by a fresh exact idle proof for each read.
Each retained snapshot also matched the subsequent independent sector
download. There were no automatic retries or clock fallbacks.

Correct SHA256 for every probe-connected 512-byte result:

`fa6a9fc6d2fdd48e921c7a3b2d794e78477934056895190cc78449c4fcb05598`

Every preceding probe-free result instead had SHA256
`99acb3960c29159b74c99b3b4c1a6700e09c5c85f7cacb63eb508e6a70eb0429`,
with the exact ten-symbol deletion/CRC-prefix pattern documented in the
original archive. The [complete paired analysis](addenda/clk-cmd-probes/evidence/analysis-complete.json)
retains both conditions and every per-attempt proof.

This comparison implicates the physical hookup rather than CPU versus IDMA
FIFO servicing. **It does not isolate CLK loading, CMD loading, ground/return
paths or incidental mechanical movement.** Both probes and their ground
connection are part of the successful condition. It does not establish
reflections, analog timing margins or formal SD compliance. These are six
single-sector reads, not full-image write/read qualification.

## Evidence and replay

- `addenda/clk-cmd-probes/attempts/`: all six complete operation records,
  raw status snapshots, 512-byte buffers and final idle checks.
- `builds/`: exact original PIO25 and IDMA25 binaries/manifests. Their
  source-map paths resolve in the [original archive](original-archive.json),
  which retains the shared frozen sources and SDK dependency inventory.
- `reference/`: the historical sensor-pattern sector and its provenance.
- [Final closure](closure.json): powered early recovery park `0x3418078C`,
  nine good UART pulses/zero bad, COM8 closed and no active helpers.
- `archive-index.json` and `SHA256SUMS`: exact archived bytes.

From the repository root, Python 3 can replay without hardware access or
writing Python caches. Use a new output filename:

```powershell
python -B firmware/capture-raw/evidence/2026-10-27-pio-idma-probe-control/replay/analyze_probe_control.py --campaign firmware/capture-raw/evidence/2026-10-27-pio-idma-probe-control/addenda/clk-cmd-probes/attempts --out tmp/probe-control-replay.json
python -B firmware/capture-raw/evidence/2026-10-27-pio-idma-probe-control/replay/archive_results.py verify --out firmware/capture-raw/evidence/2026-10-27-pio-idma-probe-control
```

The replay binds the original sealed checksum manifest and verifies that
each trial used its exact mode-specific executable. The original archive
was not modified.

No image capture, card write/erase, NOR programming, power cycle, new
Joulescope session or Logic capture occurred in this control. The installed
normal firmware is unchanged. Removing only the CMD probe while retaining
CLK and ground is the next, separately recorded condition; it is pending
user confirmation at this archive's closure. Consult the [live checkpoint](../../../../AGENTS.md)
before touching the bench rather than treating this evidence as an ownership
lease.
