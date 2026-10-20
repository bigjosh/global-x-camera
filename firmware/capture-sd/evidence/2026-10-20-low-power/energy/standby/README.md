# Native-clock cold-cycle energy

Three v59 cold cycles reached the low-current state and subsequently passed
UART recovery and a fresh SBF check. The bench owner reports no SWD traffic
during capture or the measured plateau, and no power interruption between
Standby and that cycle's SBF check. The exact installed sector is
`7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63`.

| Cycle | Current onset to plateau | Energy to plateau | Separate 1 s plateau confirmation | Plateau current |
|---|---:|---:|---:|---:|
| 1 | 2.962862 s | 1.411008 J | 40.174 mJ | 8.209 mA |
| 2 | 2.982532 s | 1.423819 J | 39.649 mJ | 8.103 mA |
| 3 | 2.967123 s | 1.409841 J | 40.182 mJ | 8.212 mA |

Mean onset-to-plateau energy is **1.414889 J** and mean duration is
**2.970838 s**. Pretrigger energy was zero in the selected 100 ms intervals.
The first waveform samples, including inrush, are retained in the integration.
Measured peak current was 7.716–7.733 A; minimum JS110 source voltage was
1.966–1.971 V. These transient values may be affected by the recorded automatic
range/suppression configuration; no unsuppressed transient accuracy is claimed.
The final plateau draws approximately 39.64–40.18 mW in the measured branch.

These are **JS110 branch measurements**, with known CN8/debugger bypass paths
outside that boundary. The plateau boundary is selected from 1 ms current
bins; it may include analog settling and is not the precise WFI/Standby-entry
timestamp. No host UTC timestamps align integration boundaries. Only three
cycles were measured, so the numbers are not PVT or battery-life guarantees.

The v50 comparison shows an approximately **80.03 mA** awake level, versus
8.10–8.21 mA after v59 Standby. Its detected 2.524 s/1.239 J boundary is **not a
complete-cycle baseline**: the same awake current level can begin during final
uncached frame validation. The v50 proof reports 381.195 ms between module
TOTAL and COMPLETE. A later successful terminal proof establishes eventual
completion, not when that level first began. Do not subtract 1.239 J from v59
energy or attribute the difference to shutdown. Scene/PNG workload can also
differ; no matched-workload energy comparison is claimed. The 381 ms uncached
validation tail is a possible future optimization; these experiments preserve
the checksum and cache-cleanup checks.

The terminal attestations bind exact per-cycle SBF/recovery evidence and the
firmware SAVE-success guard. At the time of this analysis, independent
per-file content readback was pending and must be recorded separately.
No camera pixels or SD-sector contents are present here.

## Evidence and replay

`analysis.json` contains the strict raw integrity/finite checks, native sample
windows, thresholds, all energy terms and instrument-setting provenance.
`summary.json` is the concise numeric result and limitations.
`compact-cycle-{1,2,3}.json.gz` contains native-ID binned signed sums/min/max
and exact integration splits. The baseline uses
`compact-qualified-scope.json.gz`; earlier unqualified comparison files are
superseded and should not be archived.

`cold-cycle-comparison-qualified.png` and `.svg` show whole cycles plus the
inrush detail. Dotted lines identify selected current-level boundaries, with
the baseline ambiguity explicitly labeled.

The archive's `energy/replay-energy.py` verifies compact provenance, raw
manifest/chunk-index hashes and all aggregate energy sums. For example:

```powershell
python energy/replay-energy.py --archive . --out replay-output --figures
```

Rendering additionally needs Matplotlib; aggregate replay needs NumPy.
The compact export preserves sample counts, signed integrals and extrema,
but not within-bin ordering. **The raw onset/plateau detector is not replayed
from the archive**. Its original multi-GB float32 samples remain local and are
bound by the archived file hashes and chunk CRC index.
