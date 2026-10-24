# v60c ordered-edge timing

**All checkpoint labels are inferred from source call order. Width qualification remains false.**

Successful SAVE evidence: `IMG00064.PNG`, 1,458,185 bytes. PNG byte/pixel readback is separate from this timing analysis.

| Inferred event | Inferred checkpoint | Width (µs) | After inferred SAVE entry (ms) | Since previous marker (ms) |
| --- | --- | ---: | ---: | ---: |
| 4 | SAVE module entry | 2.510 | 0.000000 | — |
| 5 | SD initialization complete | 2.720 | 26.810000 | 26.810000 |
| 6 | FAT32 mount complete | 3.070 | 28.331920 | 1.521920 |
| 7 | PNG encode complete | 3.570 | 1640.186660 | 1611.854740 |
| 8 | File close/rename/card-ready complete | 4.080 | 1665.102760 | 24.916100 |
| 9 | Cache cleanup, uncached frame validation and snapshots complete | 4.810 | 2109.927460 | 444.824700 |

These endpoint intervals are not isolated compression or card-programming costs. Event 9 is before terminal publication. Every original edge, width, and input hash remains in the JSON. No event or energy alignment to the independent Joulescope clock is asserted.
