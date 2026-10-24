# Ordered-edge timing: v61b cold cycle 01

**Labels are inferred from source call order. Pulse-width qualification failed and remains false.**

The exact v61b sector was independently read back before the cycle. Ten complete PD12 pulses were observed with LOW capture boundaries. A later warm recovery observed SBF=1. These facts support this separately labelled ordering analysis; they do not repair the strict decoder or verify a saved PNG.

| Inferred event | Inferred checkpoint | Width (µs) | After NRST release (ms) | After observed 5 V crossing (ms) | Since previous marker (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Receiver main entry | 0.740 | 21.511070 | 23.142740 | — |
| 2 | First STROBE rising interrupt observed | 1.240 | 22.817290 | 24.448960 | 1.306220 |
| 3 | First complete-frame interrupt observed | 1.740 | 44.678560 | 46.310230 | 21.861270 |
| 4 | SAVE module entry | 2.560 | 501.783840 | 503.415510 | 457.105280 |
| 5 | SD initialization complete | 2.730 | 618.874570 | 620.506240 | 117.090730 |
| 6 | FAT32 mount complete | 3.070 | 620.555840 | 622.187510 | 1.681270 |
| 7 | PNG encode complete | 3.580 | 2249.726970 | 2251.358640 | 1629.171130 |
| 8 | File close/rename/card-ready complete | 4.070 | 2271.760620 | 2273.392290 | 22.033650 |
| 9 | Cache cleanup, uncached frame validation and snapshots complete | 4.870 | 2718.908350 | 2720.540020 | 447.147730 |
| 10 | Pre-Standby WFI checkpoint | 5.340 | 2732.168190 | 2733.799860 | 13.259840 |

All timings use observed GPIO rising edges in the same Logic capture. Event 2 is the STROBE interrupt observation, not the exact exposure edge. Event 7 still precedes flushing any buffered tail. Event 9 follows uncached validation but precedes terminal publication. Event 10 is before WFI, not a measured electrical shutdown boundary.

The pulse-width vector is preserved as measured; no tolerance was expanded and no missing pulse was invented. See `ordered-analysis.json` for every edge, input hash, nominal-width error, and limitation. Full PNG integrity remains unverified by this analysis.
