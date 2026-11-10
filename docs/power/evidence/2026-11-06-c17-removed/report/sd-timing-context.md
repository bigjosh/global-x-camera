SD timing confounds the apparent cycle-energy saving

| Run | SD init (ms) | Scan/preparation (ms) | Slot transport (ms) | Transport energy (mJ) |
|---|---:|---:|---:|---:|
| C17 fitted 01 | 99.763 | 106.382 | 383.680 | 165.538 |
| C17 fitted 02 | 102.944 | 106.688 | 383.197 | 164.404 |
| C17 fitted 03 | 109.464 | 108.260 | 385.810 | 165.447 |
| C17 removed 01 | 102.885 | 111.026 | 164.609 | 65.657 |
| C17 removed 02 | 102.995 | 111.639 | 164.859 | 66.009 |
| C17 removed 03 | 109.384 | 113.423 | 179.373 | 72.055 |

Median SD initialization: 102.944 → 102.995 ms.
Median scan/preparation: 106.688 → 111.639 ms.
Median slot transport: 383.680 → 164.859 ms.
Median transport energy: 165.447 → 66.009 mJ.

The shorter SD transport interval dominates the lower total cycle energy. Do not attribute that energy reduction to C17 removal.
These are whole-board phase intervals; transport combines bus transfers, card waits and host scheduling.
The power trace does not determine why card service time changed. Startup charge and peak comparisons remain separately limited by instrument response.
No hardware was operated and no root documentation was edited.
