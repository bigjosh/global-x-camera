C17 removed: three new cold cycles versus the latest three low-current controls

Direct regulated 5 V through JS110; no LiPo/LTC/battery losses are included.
All startup values below are raw, unqualified instrument observations, not guaranteed physical inrush.

| Run | Peak, first 250 µs (A) | Peak time (µs) | Net Q 250 µs (mC) | Net Q 1 ms (mC) | Net Q 5 ms (mC) |
|---|---:|---:|---:|---:|---:|
| C17 fitted 01 | 6.4971 | 14.0 | 0.186039 | 0.198541 | 0.478819 |
| C17 fitted 02 | 6.4956 | 14.0 | 0.185403 | 0.197651 | 0.476862 |
| C17 fitted 03 | 6.5002 | 14.0 | 0.185230 | 0.197467 | 0.476315 |
| C17 removed 01 | 6.1676 | 11.0 | 0.145884 | 0.158953 | 0.437799 |
| C17 removed 02 | 6.0825 | 12.5 | 0.145896 | 0.158954 | 0.438246 |
| C17 removed 03 | 6.1397 | 11.0 | 0.145484 | 0.158935 | 0.439070 |

Time above thresholds within the first 5 ms (sum of all native sample intervals):

| Run | >1 A (µs) | >3 A (µs) | >5 A (µs) | >7 A (µs) |
|---|---:|---:|---:|---:|
| C17 fitted 01 | 70.0 | 30.5 | 18.5 | 0.0 |
| C17 fitted 02 | 69.5 | 30.0 | 18.0 | 0.0 |
| C17 fitted 03 | 70.0 | 30.0 | 18.0 | 0.0 |
| C17 removed 01 | 58.0 | 23.0 | 13.5 | 0.0 |
| C17 removed 02 | 59.5 | 23.0 | 13.5 | 0.0 |
| C17 removed 03 | 58.5 | 23.5 | 13.5 | 0.0 |

Active metrics exclude the first 5 ms and end at the detected low plateau:

| Run | 5–10 ms (mA) | Active mean (mA) | Energy (mJ) | Low plateau begins (ms) | First strobe (ms) |
|---|---:|---:|---:|---:|---:|
| C17 fitted 01 | 43.93 | 80.03 | 256.56 | 647.82 | 24.757 |
| C17 fitted 02 | 43.39 | 79.65 | 256.77 | 651.43 | 25.116 |
| C17 fitted 03 | 43.40 | 79.69 | 260.89 | 661.44 | 25.163 |
| C17 removed 01 | 43.38 | 73.72 | 158.78 | 436.89 | 24.775 |
| C17 removed 02 | 43.61 | 74.13 | 159.97 | 437.72 | 24.903 |
| C17 removed 03 | 43.65 | 74.58 | 169.45 | 460.60 | 24.997 |

All six source records passed raw hashes, sample continuity, eleven markers and one exposure mirror.
Current onset is a threshold, not proven target power-good. JS voltage is upstream of the DUT.
Net charge retains negative samples; positive/negative charge, window peaks and all thresholds are in summary.json.
Fixed 10 A low-current averages do not supersede a separate auto-range sleep measurement.
SD history and elapsed time vary. These measurements do not establish target-rail stability or C17-only causality.
The power-trace analysis does not itself verify saved images or independently prove MCU Standby.
