# Timing context for the 2.2-ohm comparison

The median-total-energy runs are baseline02 and resistor02. Their post-5-ms cycle energy differs by **62.212 mJ**, with **126.860 ms** more total time. This is not a measured resistor-only penalty.

| Nonoverlapping phase | Duration, baseline -> resistor (ms) | Mean power, baseline -> resistor (mW) | Energy increase (mJ) | Duration term at baseline power (mJ) | Power term at new duration (mJ) |
|---|---:|---:|---:|---:|---:|
| SD_init | 102.995 -> 109.456 | 409.25 -> 425.49 | 4.423 | 2.645 | 1.778 |
| scan_preparation | 111.639 -> 116.528 | 320.45 -> 327.95 | 2.440 | 1.567 | 0.874 |
| slot_transport | 164.859 -> 280.441 | 400.39 -> 430.46 | 54.709 | 46.278 | 8.431 |

The three disjoint SD phases account for 61.572 mJ of the 62.212 mJ difference. Holding their baseline mean powers fixed attributes 50.489 mJ (about 81.2%) arithmetically to extra time; the remaining mean-power term is 11.083 mJ. Everything outside these phases differs by 0.640 mJ.

Slot transport is dominant: 164.860 -> 280.441 ms, 66.009 -> 120.718 mJ. Its 54.709 mJ increase is about 88% of the total difference.

The first resistor run has nearly the same transport duration as baseline02 (164.745 versus 164.860 ms): transport energy is 68.386 versus 66.009 mJ, a 2.377 mJ / 3.60% difference. Its full post-5-ms cycle is 168.425 mJ rather than 159.974 mJ (+5.28%), with a 7.784 ms longer cycle. This is a close-duration comparison, not a randomized paired experiment.

All three strobe-to-frame windows stay about 21.864 ms. Their mean power is about 615 mW with the resistor versus 587 mW without it. That matched phase suggests a modest operating-power change; it does not isolate resistor dissipation from regulator/card differences.

The accounting identity uses baseline power as its reference; reversing the reference changes the split. Card service time and the proportion of transfer versus busy time affect mean power, and new slots require a longer linear header scan. Do not attribute the +62 mJ median difference to the resistor. Source voltage is upstream and no downstream rail-stability conclusion follows.
