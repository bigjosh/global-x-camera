# v60c ordered-edge timing

**All checkpoint labels are inferred from source call order. Width qualification remains false.**

Successful SAVE evidence: `IMG00062.PNG`, 1,458,185 bytes. PNG byte/pixel readback is separate from this timing analysis.

| Inferred event | Inferred checkpoint | Width (µs) | After inferred SAVE entry (ms) | Since previous marker (ms) |
| --- | --- | ---: | ---: | ---: |
| 4 | SAVE module entry | 2.530 | 0.000000 | — |
| 5 | SD initialization complete | 2.730 | 26.846570 | 26.846570 |
| 6 | FAT32 mount complete | 3.070 | 27.992500 | 1.145930 |
| 7 | PNG encode complete | 3.570 | 1637.205480 | 1609.212980 |
| 8 | File close/rename/card-ready complete | 4.060 | 1668.367920 | 31.162440 |
| 9 | Cache cleanup, uncached frame validation and snapshots complete | 4.810 | 2113.329920 | 444.962000 |

These endpoint intervals are not isolated compression or card-programming costs. Event 9 is before terminal publication. Every original edge, width, and input hash remains in the JSON. No event or energy alignment to the independent Joulescope clock is asserted.
