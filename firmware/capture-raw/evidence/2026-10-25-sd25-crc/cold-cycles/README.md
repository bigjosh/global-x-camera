# Three cold cycles at four-bit 25 MHz

All three measured cycles reached independently attributed Standby and produced complete GXR2 image objects. Each saved slot's first sector was blank before its cycle; after saving, the full slot was read and independently reconstructed as PNG. Original capture RAM was lost in Standby.

| Cycle | Slot | Current onset → plateau (ms) | Energy (mJ) | Plateau (mA) |
|---|---:|---:|---:|---:|
| cold01 | 9 | 419.916 | 230.023 | 8.190 |
| cold02 | 10 | 410.282 | 225.653 | 8.089 |
| cold03 | 11 | 419.518 | 229.913 | 8.192 |

Median: **419.518 ms / 229.913 mJ**.

The 27 Ω clock resistor remains approximately midway along the wire. All six SD signal probes were removed; only reset and recovery UART probes remained. Firmware uses four-bit 25 MHz, NEGEDGE, GPIO speed three, unchanged compensation and configured hardware IDMA with progressive PIO fallback. Per-cycle runtime transport telemetry is lost in Standby; a separate awake cold test directly established IDMA use.

| Earlier configuration | Median time (ms) | Median energy (mJ) | Observed time reduction | Observed energy reduction |
|---|---:|---:|---:|---:|
| four-bit 12.5 MHz, pre-resistor, SD CLK/CMD probes attached | 578.942 | 309.532 | 27.54% | 25.72% |
| one-bit 25 MHz, old carrier | 882.627 | 450.788 | 52.47% | 49.00% |

Thresholds and native-sample integration match the earlier baseline. The one-second plateau confirmation is recorded separately and excluded from headline energy. No phase timing is inferred.

- Three trials per configuration are observations, not a long-run reliability qualification.
- Clock, clock edge, series resistor, probe loading, scene, card state and allocation position differ; earlier slots0–2 versus current slots9–11 do not isolate one cause.
- No PD12 phase or rail probes were present; per-phase durations, per-phase energy and physical rail-good/WFI timestamps are not inferred.
- Standby loses original frame RAM. These readbacks verify full object markers and PNG reconstruction, not SD-versus-original-camera-RAM equality.
- SBF attribution uses exact recovery prefix, reviewed CSSF source and explicit root chronology; current alone does not establish Standby.
- JS-fed Nucleo-branch energy includes board overhead and omits unmeasured bypass paths; it is not isolated MCU or production battery energy.
- Original sample validity thresholds, startup spikes and autorange behavior are unchanged; no calibration or saturation correction is inferred.
- Each current stream contains 71 nonfinite samples at native IDs0–70, before the shared valid timeline and integration. All three signals are finite throughout every integrated window and logged coverage has no gaps or overlaps.
- GXR2/GXRE markers are not pixel checksums or arbitrary SD power-loss protection.

`energy-summary.json` preserves sample boundaries, individual energy intervals, source hashes, qualification results and comparison arithmetic. It contains no raw images, card identifiers, instrument identifiers or local user paths.


Compact arithmetic replay: run `python compact/replay_energy.py`. The standard-library verifier checks all artifact hashes, 12 exact interval sums, durations and medians using the exported native-sample sums. It needs no instruments or bulk raw arrays. Compact bins preserve sums/extrema, not sample order; they cannot rerun onset/plateau classification or qualify calibration. All exported and integrated current/voltage/power samples were finite; the original 71 initial nonfinite current samples per stream remain explicitly recorded outside those windows.
