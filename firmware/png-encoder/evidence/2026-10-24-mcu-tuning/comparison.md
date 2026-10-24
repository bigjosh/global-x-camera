# Fixed-frame MCU comparison

Measured times are medians of the repetitions listed. CPU excludes the complete output callback. The frame, 400 MHz clock, sink behavior and every executable are bound by the archived records.

| Executable | Mode | Runs | PNG bytes | CPU ms | Conversion ms | DEFLATE ms | Framing ms |
|---|---|---:|---:|---:|---:|---:|---:|
| batch8-o2 | Literal Huffman / Sub | 3 | 1,026,718 | 617.354 | 85.301 | 510.467 | 20.372 |
| emitter-os | Fast / None | 3 | 1,452,183 | 945.884 | 143.200 | 767.663 | 33.793 |
| emitter-os | Fast / Sub | 3 | 1,305,199 | 919.247 | 143.157 | 744.340 | 30.530 |
| emitter-os | Literal Huffman / Sub | 3 | 1,026,718 | 806.540 | 143.341 | 638.299 | 23.655 |
| local-o2 | Literal Huffman / Sub | 3 | 1,026,718 | 662.589 | 85.255 | 555.698 | 20.413 |
| local-os | Literal Huffman / Sub | 3 | 1,026,718 | 799.019 | 143.509 | 630.748 | 23.617 |
| mve-batch8-o2 | Literal Huffman / Sub | 3 | 1,026,718 | 545.696 | 13.969 | 510.461 | 20.366 |
| mve-local-o2 | Fast / None | 3 | 1,452,183 | 925.752 | 8.912 | 886.690 | 29.187 |
| mve-local-o2 | Fast / Sub | 3 | 1,305,199 | 921.069 | 14.009 | 879.726 | 26.395 |
| mve-local-o2 | Literal Huffman / Sub | 3 | 1,026,718 | 590.743 | 13.988 | 555.450 | 20.381 |
| mve-pair-o2 | Literal Huffman / Sub | 3 | 1,026,718 | 435.078 | 13.931 | 399.854 | 20.374 |
| pair-o2 | Fast / None | 3 | 1,452,183 | 1087.910 | 85.326 | 972.285 | 29.187 |
| pair-o2 | Literal Huffman / Sub | 3 | 1,026,718 | 506.791 | 85.308 | 399.946 | 20.375 |
| scalar-o2 | Fast / None | 3 | 1,452,183 | 837.061 | 85.248 | 721.332 | 29.266 |
| scalar-o2 | Fast / Sub | 3 | 1,305,199 | 817.013 | 85.237 | 704.084 | 26.446 |
| scalar-o2 | Literal Huffman / Sub | 3 | 1,026,718 | 851.878 | 85.256 | 744.967 | 20.402 |
| scalar-os | Fast / None | 3 | 1,452,183 | 953.512 | 143.129 | 775.386 | 33.761 |
| scalar-os | Fast / Sub | 3 | 1,305,199 | 925.255 | 143.133 | 750.323 | 30.555 |
| scalar-os | Literal Huffman / Sub | 3 | 1,026,718 | 999.100 | 143.289 | 830.951 | 23.649 |

The following values are hypothetical payload-transfer models using 2,649,960 bytes/s from the prior one-bit SD test. They exclude storage initialization, metadata, altered busy time and contention; no concurrent write or DMA occurred in these compute trials.

| Executable | Mode | Serial CPU + write ms | Ideal max(CPU, write) ms | Two-buffer proxy ms | 32 KiB producer mean / p95 ms |
|---|---|---:|---:|---:|---:|
| batch8-o2 | Literal Huffman / Sub | 1004.800 | 617.354 | 629.803 | 19.785 / 22.398 |
| emitter-os | Fast / None | 1493.886 | 945.884 | 960.141 | 21.451 / 26.402 |
| emitter-os | Fast / Sub | 1411.782 | 919.247 | 929.706 | 23.090 / 25.446 |
| emitter-os | Literal Huffman / Sub | 1193.987 | 806.540 | 817.701 | 25.846 / 29.116 |
| local-o2 | Literal Huffman / Sub | 1050.035 | 662.589 | 674.709 | 21.233 / 24.017 |
| local-os | Literal Huffman / Sub | 1186.466 | 799.019 | 810.448 | 25.612 / 28.854 |
| mve-batch8-o2 | Literal Huffman / Sub | 933.142 | 545.696 | 558.627 | 17.489 / 19.819 |
| mve-local-o2 | Fast / None | 1473.754 | 925.752 | 939.869 | 20.991 / 25.625 |
| mve-local-o2 | Fast / Sub | 1413.604 | 921.069 | 931.504 | 23.116 / 25.727 |
| mve-local-o2 | Literal Huffman / Sub | 978.190 | 590.743 | 603.366 | 18.932 / 21.441 |
| mve-pair-o2 | Literal Huffman / Sub | 822.525 | 435.078 | 448.927 | 13.944 / 15.844 |
| pair-o2 | Fast / None | 1635.912 | 1087.910 | 1101.443 | 24.663 / 30.698 |
| pair-o2 | Literal Huffman / Sub | 894.238 | 506.791 | 519.983 | 16.242 / 18.434 |
| scalar-o2 | Fast / None | 1385.063 | 837.061 | 851.468 | 18.981 / 23.281 |
| scalar-o2 | Fast / Sub | 1309.548 | 817.013 | 827.445 | 20.519 / 22.594 |
| scalar-o2 | Literal Huffman / Sub | 1239.325 | 851.878 | 862.695 | 27.297 / 30.753 |
| scalar-os | Fast / None | 1501.514 | 953.512 | 967.736 | 21.624 / 26.618 |
| scalar-os | Fast / Sub | 1417.791 | 925.255 | 935.710 | 23.241 / 25.619 |
| scalar-os | Literal Huffman / Sub | 1386.547 | 999.100 | 1008.940 | 32.015 / 36.022 |

Producer means/p95s are medians of each run’s full 32 KiB interval statistics; the final partial interval is excluded from that column but included in the two-buffer model. The producer clock excludes sink-body time only, so callback/timer-edge overhead remains. It is not interchangeable with total CPU time.

No speed result is assigned to failed PREPARE attempts. See [README.md](README.md) for context, the preserved failures and qualification limits.

## Instrumented diagnostic: profile-os

These coarse probes perturb execution and are excluded from the speed tables. The following disjoint intervals include probe/layout overhead.

| Run | Region | ms |
|---|---|---:|
| mode 3 / 1 | accumulation_including_histogram_updates | 270.407 |
| mode 3 / 1 | huffman_tree_construction | 29.172 |
| mode 3 / 1 | huffman_header_other | 4.385 |
| mode 3 / 1 | lz_code_emission | 286.169 |
| mode 3 / 1 | adler | 29.372 |
| mode 3 / 1 | raw_fallback_emission | 0.000 |
| mode 3 / 1 | histogram_clear | 1.359 |
| mode 3 / 1 | block_flush_other | 0.220 |
| mode 3 / 1 | flush_output_buffer | 0.158 |
| mode 3 / 1 | compress_other | 1.306 |
| mode 3 / 1 | init | 0.630 |
| mode 3 / 1 | compressed_output_callback | 50.115 |
