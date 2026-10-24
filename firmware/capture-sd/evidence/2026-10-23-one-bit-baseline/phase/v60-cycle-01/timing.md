# v60c ordered-edge timing

**All checkpoint labels are inferred from source call order. Width qualification remains false.**

Successful SAVE evidence: `IMG00061.PNG`, 1,458,185 bytes. PNG byte/pixel readback is separate from this timing analysis.

| Inferred event | Inferred checkpoint | Width (µs) | After NRST release (ms) | Since previous marker (ms) |
| --- | --- | ---: | ---: | ---: |
| 1 | Receiver main entry | 0.730 | 21.190690 | — |
| 2 | First STROBE rising interrupt observed | 1.250 | 22.543020 | 1.352330 |
| 3 | First complete-frame interrupt observed | 1.740 | 44.404790 | 21.861770 |
| 4 | SAVE module entry | 2.530 | 498.354940 | 453.950150 |
| 5 | SD initialization complete | 2.730 | 621.932760 | 123.577820 |
| 6 | FAT32 mount complete | 3.070 | 623.641720 | 1.708960 |
| 7 | PNG encode complete | 3.570 | 2257.615280 | 1633.973560 |
| 8 | File close/rename/card-ready complete | 4.080 | 2282.412470 | 24.797190 |
| 9 | Cache cleanup, uncached frame validation and snapshots complete | 4.820 | 2727.524960 | 445.112490 |
| 10 | Awake diagnostic completion checkpoint | 5.730 | 2727.542620 | 0.017660 |

These endpoint intervals are not isolated compression or card-programming costs. Event 9 is before terminal publication. Every original edge, width, and input hash remains in the JSON. No event or energy alignment to the independent Joulescope clock is asserted.
