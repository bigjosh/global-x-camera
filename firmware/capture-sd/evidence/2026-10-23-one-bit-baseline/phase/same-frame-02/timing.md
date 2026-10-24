# v60c ordered-edge timing

**All checkpoint labels are inferred from source call order. Width qualification remains false.**

Successful SAVE evidence: `IMG00063.PNG`, 1,458,185 bytes. PNG byte/pixel readback is separate from this timing analysis.

| Inferred event | Inferred checkpoint | Width (µs) | After inferred SAVE entry (ms) | Since previous marker (ms) |
| --- | --- | ---: | ---: | ---: |
| 4 | SAVE module entry | 2.530 | 0.000000 | — |
| 5 | SD initialization complete | 2.720 | 26.828810 | 26.828810 |
| 6 | FAT32 mount complete | 3.080 | 28.348480 | 1.519670 |
| 7 | PNG encode complete | 3.560 | 1645.833450 | 1617.484970 |
| 8 | File close/rename/card-ready complete | 4.060 | 1670.251710 | 24.418260 |
| 9 | Cache cleanup, uncached frame validation and snapshots complete | 4.810 | 2115.049380 | 444.797670 |

These endpoint intervals are not isolated compression or card-programming costs. Event 9 is before terminal publication. Every original edge, width, and input hash remains in the JSON. No event or energy alignment to the independent Joulescope clock is asserted.
