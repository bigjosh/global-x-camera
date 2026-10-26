# Session 0 — complete SD command/response transcript

Source: `Session 0.sal`, SHA-256 `2dfa9ccb1f2e0baea4d204c01366e1e75bf3d3a5d6aab9cf506d08f6fe73b057`.
See [capture summary and validation](README.md), [individual write blocks](BLOCK-WRITES.md),
and [machine-readable command rows](commands.json).

Every genuine command and response is listed: **265 host commands + 264 card responses**.
CMD0 correctly has no response. All applicable command/response CRC7 checks pass;
R3 has no CRC7. The one malformed startup annotation is retained separately below.

**Time (s)** matches the saved Logic display: zero is its recorded trigger, not power-on,
reset release or CMD0. **Δ (µs)** is start-to-start from the previous row in this table;
it includes the previous packet's duration and intervening gaps. **Duration (µs)**
is first-to-last sampled bit, excluding the final bit's remaining clock period.
Exact sample indices and end timestamps are in `commands.json`.

CMD/response sampling uses rising CLK +16 ns at 500 MS/s. The 2 ns acquisition
resolution does not imply 2 ns absolute accuracy. DAT0 busy uses raw transitions
and can overlap command responses; it is not inserted into this sequential CMD table.
R1 state is the card state when the command arrived. READY_FOR_DATA in an early
R1 does not replace the power-up-complete bit in ACMD41's R3.

| # | Time (s) | Δ (µs) | Duration (µs) | Event | Argument / response | Meaning |
|---:|---:|---:|---:|---|---|---|
| 1 | 0.030360990 | — | 472.616 | CMD0 | `0x00000000` | reset card to IDLE/native initialization; no response is expected |
| 2 | 0.030964314 | 603.324 | 472.506 | CMD8 | `0x000001AA` | check interface compatibility: supplied voltage code 1 (1 = 2.7-3.6 V); echo test pattern 0xAA |
| 3 | 0.031557398 | 593.084 | 472.514 | R7 → CMD8 | `0x000001AA` | accepted voltage code 1 (1 = 2.7-3.6 V); echoed check pattern 0xAA |
| 4 | 0.032160614 | 603.216 | 472.430 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 5 | 0.032683344 | 522.730 | 472.590 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 6 | 0.033286768 | 603.424 | 472.536 | ACMD41 | `0x40300000` | Initialization poll 1/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 7 | 0.033819588 | 532.820 | 472.500 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 8 | 0.035398304 | 1578.716 | 472.426 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 9 | 0.035981328 | 583.024 | 472.958 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 10 | 0.036585004 | 603.676 | 472.460 | ACMD41 | `0x40300000` | Initialization poll 2/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 11 | 0.037117810 | 532.806 | 472.434 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 12 | 0.038696144 | 1578.334 | 472.564 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 13 | 0.039279316 | 583.172 | 472.780 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 14 | 0.039882890 | 603.574 | 472.910 | ACMD41 | `0x40300000` | Initialization poll 3/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 15 | 0.040416136 | 533.246 | 472.778 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 16 | 0.041995846 | 1579.710 | 472.744 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 17 | 0.042579268 | 583.422 | 472.684 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 18 | 0.043182688 | 603.420 | 472.426 | ACMD41 | `0x40300000` | Initialization poll 4/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 19 | 0.043715368 | 532.680 | 471.878 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 20 | 0.045735454 | 2020.086 | 472.592 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 21 | 0.046278402 | 542.948 | 472.404 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 22 | 0.046891358 | 612.956 | 471.922 | ACMD41 | `0x40300000` | Initialization poll 5/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 23 | 0.047423538 | 532.180 | 471.936 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 24 | 0.049069566 | 1646.028 | 471.754 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 25 | 0.049651746 | 582.180 | 471.866 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 26 | 0.050264262 | 612.516 | 472.268 | ACMD41 | `0x40300000` | Initialization poll 6/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 27 | 0.050796832 | 532.570 | 472.094 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 28 | 0.052443756 | 1646.924 | 471.928 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 29 | 0.053026206 | 582.450 | 472.094 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 30 | 0.053639020 | 612.814 | 472.100 | ACMD41 | `0x40300000` | Initialization poll 7/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 31 | 0.054171456 | 532.436 | 472.168 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 32 | 0.055818626 | 1647.170 | 472.278 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 33 | 0.056401464 | 582.838 | 472.540 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 34 | 0.057014720 | 613.256 | 472.318 | ACMD41 | `0x40300000` | Initialization poll 8/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 35 | 0.057547316 | 532.596 | 472.374 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 36 | 0.059196094 | 1648.778 | 472.644 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 37 | 0.059779346 | 583.252 | 472.622 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 38 | 0.060392696 | 613.350 | 472.484 | ACMD41 | `0x40300000` | Initialization poll 9/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 39 | 0.060925526 | 532.830 | 472.180 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 40 | 0.062572786 | 1647.260 | 472.370 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 41 | 0.063155586 | 582.800 | 472.280 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 42 | 0.063768336 | 612.750 | 472.168 | ACMD41 | `0x40300000` | Initialization poll 10/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 43 | 0.064300806 | 532.470 | 472.238 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 44 | 0.065949282 | 1648.476 | 472.852 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 45 | 0.066532786 | 583.504 | 472.966 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 46 | 0.067146624 | 613.838 | 472.644 | ACMD41 | `0x40300000` | Initialization poll 11/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 47 | 0.067679608 | 532.984 | 472.706 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 48 | 0.069329656 | 1650.048 | 472.674 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 49 | 0.069912936 | 583.280 | 472.638 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 50 | 0.070526410 | 613.474 | 472.770 | ACMD41 | `0x40300000` | Initialization poll 12/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 51 | 0.071059518 | 533.108 | 472.510 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 52 | 0.072708098 | 1648.580 | 472.704 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 53 | 0.073291404 | 583.306 | 472.150 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 54 | 0.073904214 | 612.810 | 472.080 | ACMD41 | `0x40300000` | Initialization poll 13/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 55 | 0.074436628 | 532.414 | 472.602 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 56 | 0.076085790 | 1649.162 | 472.372 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 57 | 0.076668762 | 582.972 | 472.536 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 58 | 0.077282030 | 613.268 | 472.368 | ACMD41 | `0x40300000` | Initialization poll 14/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 59 | 0.077814716 | 532.686 | 472.330 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 60 | 0.079463668 | 1648.952 | 472.500 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 61 | 0.080046794 | 583.126 | 472.292 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 62 | 0.080730210 | 683.416 | 472.712 | ACMD41 | `0x40300000` | Initialization poll 15/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 63 | 0.081263266 | 533.056 | 472.584 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 64 | 0.082841858 | 1578.592 | 472.724 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 65 | 0.083425166 | 583.308 | 472.342 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 66 | 0.084028208 | 603.042 | 472.662 | ACMD41 | `0x40300000` | Initialization poll 16/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 67 | 0.084561224 | 533.016 | 472.752 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 68 | 0.086140058 | 1578.834 | 472.278 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 69 | 0.086722968 | 582.910 | 472.646 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 70 | 0.087326280 | 603.312 | 472.350 | ACMD41 | `0x40300000` | Initialization poll 17/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 71 | 0.087858912 | 532.632 | 472.284 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 72 | 0.089436734 | 1577.822 | 472.344 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 73 | 0.090019586 | 582.852 | 472.374 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 74 | 0.090622590 | 603.004 | 472.128 | ACMD41 | `0x40300000` | Initialization poll 18/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 75 | 0.091154972 | 532.382 | 472.166 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 76 | 0.092732276 | 1577.304 | 472.410 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 77 | 0.093315144 | 582.868 | 472.366 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 78 | 0.093918130 | 602.986 | 472.334 | ACMD41 | `0x40300000` | Initialization poll 19/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 79 | 0.094450790 | 532.660 | 472.312 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 80 | 0.096028684 | 1577.894 | 472.510 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 81 | 0.096611798 | 583.114 | 472.216 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 82 | 0.097214608 | 602.810 | 472.432 | ACMD41 | `0x40300000` | Initialization poll 20/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 83 | 0.097747330 | 532.722 | 472.474 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 84 | 0.099325160 | 1577.830 | 471.994 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 85 | 0.099907550 | 582.390 | 472.238 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 86 | 0.100510438 | 602.888 | 472.228 | ACMD41 | `0x40300000` | Initialization poll 21/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 87 | 0.101042990 | 532.552 | 472.096 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 88 | 0.102620056 | 1577.066 | 472.488 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 89 | 0.103203136 | 583.080 | 472.366 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 90 | 0.103806208 | 603.072 | 472.342 | ACMD41 | `0x40300000` | Initialization poll 22/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 91 | 0.104338840 | 532.632 | 472.232 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 92 | 0.105916388 | 1577.548 | 472.834 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 93 | 0.106499762 | 583.374 | 472.418 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 94 | 0.107102988 | 603.226 | 472.662 | ACMD41 | `0x40300000` | Initialization poll 23/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 95 | 0.107636004 | 533.016 | 473.050 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 96 | 0.109215564 | 1579.560 | 472.292 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 97 | 0.109798360 | 582.796 | 472.462 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 98 | 0.110401482 | 603.122 | 472.306 | ACMD41 | `0x40300000` | Initialization poll 24/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 99 | 0.110934076 | 532.594 | 472.464 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 100 | 0.112512040 | 1577.964 | 472.280 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 101 | 0.113094820 | 582.780 | 472.558 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 102 | 0.113698082 | 603.262 | 472.354 | ACMD41 | `0x40300000` | Initialization poll 25/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 103 | 0.114230758 | 532.676 | 472.384 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 104 | 0.115808796 | 1578.038 | 472.316 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 105 | 0.116391652 | 582.856 | 472.396 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 106 | 0.116994680 | 603.028 | 472.556 | ACMD41 | `0x40300000` | Initialization poll 26/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 107 | 0.117527534 | 532.854 | 472.672 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 108 | 0.119106300 | 1578.766 | 472.568 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 109 | 0.119689548 | 583.248 | 472.566 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 110 | 0.120292746 | 603.198 | 472.220 | ACMD41 | `0x40300000` | Initialization poll 27/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 111 | 0.120825232 | 532.486 | 472.346 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 112 | 0.122403400 | 1578.168 | 472.080 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 113 | 0.122985992 | 582.592 | 472.264 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 114 | 0.123588904 | 602.912 | 472.258 | ACMD41 | `0x40300000` | Initialization poll 28/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 115 | 0.124121446 | 532.542 | 472.266 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 116 | 0.125699192 | 1577.746 | 472.390 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 117 | 0.126282128 | 582.936 | 472.400 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 118 | 0.126885138 | 603.010 | 472.362 | ACMD41 | `0x40300000` | Initialization poll 29/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 119 | 0.127417760 | 532.622 | 472.518 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 120 | 0.128996252 | 1578.492 | 472.438 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 121 | 0.129579270 | 583.018 | 472.582 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 122 | 0.130182620 | 603.350 | 472.570 | ACMD41 | `0x40300000` | Initialization poll 30/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 123 | 0.130715538 | 532.918 | 472.730 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 124 | 0.132293584 | 1578.046 | 472.574 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 125 | 0.132876778 | 583.194 | 472.794 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 126 | 0.133480280 | 603.502 | 472.828 | ACMD41 | `0x40300000` | Initialization poll 31/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 127 | 0.134013458 | 533.178 | 472.788 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 128 | 0.135591372 | 1577.914 | 472.004 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 129 | 0.136173924 | 582.552 | 472.300 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 130 | 0.136776924 | 603.000 | 472.344 | ACMD41 | `0x40300000` | Initialization poll 32/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 131 | 0.137309582 | 532.658 | 472.662 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 132 | 0.138887964 | 1578.382 | 472.252 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 133 | 0.139470750 | 582.786 | 472.706 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 134 | 0.140074142 | 603.392 | 472.248 | ACMD41 | `0x40300000` | Initialization poll 33/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 135 | 0.140606656 | 532.514 | 472.604 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 136 | 0.142185616 | 1578.960 | 472.642 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 137 | 0.142768918 | 583.302 | 472.612 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 138 | 0.143372144 | 603.226 | 472.800 | ACMD41 | `0x40300000` | Initialization poll 34/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 139 | 0.143905374 | 533.230 | 472.454 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 140 | 0.145483458 | 1578.084 | 472.288 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 141 | 0.146066330 | 582.872 | 472.416 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 142 | 0.146669394 | 603.064 | 472.534 | ACMD41 | `0x40300000` | Initialization poll 35/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 143 | 0.147202226 | 532.832 | 472.710 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 144 | 0.148781312 | 1579.086 | 472.756 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 145 | 0.149364680 | 583.368 | 472.596 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 146 | 0.149968076 | 603.396 | 472.734 | ACMD41 | `0x40300000` | Initialization poll 36/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 147 | 0.150501176 | 533.100 | 472.676 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 148 | 0.152080698 | 1579.522 | 472.660 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 149 | 0.152663876 | 583.178 | 472.766 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 150 | 0.153267350 | 603.474 | 472.330 | ACMD41 | `0x40300000` | Initialization poll 37/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 151 | 0.153799998 | 532.648 | 472.482 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 152 | 0.155378816 | 1578.818 | 472.730 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 153 | 0.155962200 | 583.384 | 472.402 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 154 | 0.156565248 | 603.048 | 472.202 | ACMD41 | `0x40300000` | Initialization poll 38/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 155 | 0.157097730 | 532.482 | 472.248 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 156 | 0.158675724 | 1577.994 | 472.640 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 157 | 0.159259044 | 583.320 | 472.544 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 158 | 0.159862268 | 603.224 | 472.412 | ACMD41 | `0x40300000` | Initialization poll 39/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 159 | 0.160395000 | 532.732 | 472.618 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 160 | 0.161973504 | 1578.504 | 472.358 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 161 | 0.162556458 | 582.954 | 472.346 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 162 | 0.163159582 | 603.124 | 472.892 | ACMD41 | `0x40300000` | Initialization poll 40/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 163 | 0.163692836 | 533.254 | 472.988 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 164 | 0.165272058 | 1579.222 | 472.566 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 165 | 0.165855290 | 583.232 | 472.890 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 166 | 0.166458970 | 603.680 | 472.660 | ACMD41 | `0x40300000` | Initialization poll 41/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 167 | 0.166992046 | 533.076 | 472.804 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 168 | 0.168571000 | 1578.954 | 472.666 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 169 | 0.169154304 | 583.304 | 472.498 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 170 | 0.169757398 | 603.094 | 472.812 | ACMD41 | `0x40300000` | Initialization poll 42/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 171 | 0.170290604 | 533.206 | 472.702 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 172 | 0.171869274 | 1578.670 | 472.570 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 173 | 0.172452514 | 583.240 | 472.602 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 174 | 0.173055862 | 603.348 | 472.546 | ACMD41 | `0x40300000` | Initialization poll 43/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 175 | 0.173588702 | 532.840 | 472.432 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 176 | 0.175167296 | 1578.594 | 472.574 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 177 | 0.175750532 | 583.236 | 472.728 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 178 | 0.176354056 | 603.524 | 472.790 | ACMD41 | `0x40300000` | Initialization poll 44/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 179 | 0.176887140 | 533.084 | 472.534 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 180 | 0.178465980 | 1578.840 | 472.730 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 181 | 0.179049328 | 583.348 | 472.846 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 182 | 0.179652962 | 603.634 | 473.102 | ACMD41 | `0x40300000` | Initialization poll 45/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 183 | 0.180186436 | 533.474 | 472.832 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 184 | 0.181765354 | 1578.918 | 472.420 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 185 | 0.182348356 | 583.002 | 472.396 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 186 | 0.182951534 | 603.178 | 472.480 | ACMD41 | `0x40300000` | Initialization poll 46/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 187 | 0.183484360 | 532.826 | 472.626 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 188 | 0.185063330 | 1578.970 | 472.580 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 189 | 0.185646476 | 583.146 | 472.332 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 190 | 0.186249444 | 602.968 | 472.506 | ACMD41 | `0x40300000` | Initialization poll 47/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 191 | 0.186782210 | 532.766 | 472.424 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 192 | 0.188360506 | 1578.296 | 472.548 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 193 | 0.188943680 | 583.174 | 472.430 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 194 | 0.189546832 | 603.152 | 472.354 | ACMD41 | `0x40300000` | Initialization poll 48/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 195 | 0.190079492 | 532.660 | 472.350 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 196 | 0.191657614 | 1578.122 | 472.510 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 197 | 0.192240690 | 583.076 | 472.426 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 198 | 0.192843894 | 603.204 | 472.846 | ACMD41 | `0x40300000` | Initialization poll 49/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 199 | 0.193377006 | 533.112 | 472.628 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 200 | 0.194956170 | 1579.164 | 472.668 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 201 | 0.195539466 | 583.296 | 472.740 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 202 | 0.196143012 | 603.546 | 473.114 | ACMD41 | `0x40300000` | Initialization poll 50/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 203 | 0.196676564 | 533.552 | 473.238 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 204 | 0.198257300 | 1580.736 | 472.634 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 205 | 0.198840490 | 583.190 | 472.636 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 206 | 0.199443870 | 603.380 | 472.864 | ACMD41 | `0x40300000` | Initialization poll 51/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 207 | 0.199977118 | 533.248 | 472.882 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 208 | 0.201556048 | 1578.930 | 472.698 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 209 | 0.202139408 | 583.360 | 472.788 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 210 | 0.202742980 | 603.572 | 472.692 | ACMD41 | `0x40300000` | Initialization poll 52/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 211 | 0.203275948 | 532.968 | 472.320 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 212 | 0.204853632 | 1577.684 | 472.454 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 213 | 0.205436554 | 582.922 | 471.994 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 214 | 0.206039126 | 602.572 | 472.034 | ACMD41 | `0x40300000` | Initialization poll 53/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 215 | 0.206571456 | 532.330 | 472.390 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 216 | 0.208149168 | 1577.712 | 471.898 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 217 | 0.208731422 | 582.254 | 471.842 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 218 | 0.209333778 | 602.356 | 471.736 | ACMD41 | `0x40300000` | Initialization poll 54/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 219 | 0.209865768 | 531.990 | 471.942 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 220 | 0.211442156 | 1576.388 | 472.520 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 221 | 0.212025280 | 583.124 | 472.432 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 222 | 0.212628294 | 603.014 | 472.068 | ACMD41 | `0x40300000` | Initialization poll 55/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 223 | 0.213160630 | 532.336 | 472.350 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 224 | 0.214738334 | 1577.704 | 472.266 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 225 | 0.215321102 | 582.768 | 472.330 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 226 | 0.215923990 | 602.888 | 472.404 | ACMD41 | `0x40300000` | Initialization poll 56/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 227 | 0.216456688 | 532.698 | 472.696 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 228 | 0.218035584 | 1578.896 | 472.498 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 229 | 0.218618680 | 583.096 | 472.486 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 230 | 0.219221946 | 603.266 | 472.800 | ACMD41 | `0x40300000` | Initialization poll 57/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 231 | 0.219755072 | 533.126 | 472.276 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 232 | 0.221333644 | 1578.572 | 472.556 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 233 | 0.221916834 | 583.190 | 472.474 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 234 | 0.222520044 | 603.210 | 472.318 | ACMD41 | `0x40300000` | Initialization poll 58/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 235 | 0.223052710 | 532.666 | 472.334 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 236 | 0.224630988 | 1578.278 | 472.758 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 237 | 0.225214346 | 583.358 | 472.516 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 238 | 0.225817620 | 603.274 | 472.842 | ACMD41 | `0x40300000` | Initialization poll 59/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 239 | 0.226350840 | 533.220 | 472.594 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 240 | 0.227929284 | 1578.444 | 472.598 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 241 | 0.228512428 | 583.144 | 472.608 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 242 | 0.229115750 | 603.322 | 472.842 | ACMD41 | `0x40300000` | Initialization poll 60/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 243 | 0.229649038 | 533.288 | 473.004 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 244 | 0.231228088 | 1579.050 | 472.412 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 245 | 0.231811024 | 582.936 | 472.556 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 246 | 0.232414272 | 603.248 | 472.360 | ACMD41 | `0x40300000` | Initialization poll 61/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 247 | 0.232946928 | 532.656 | 472.732 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 248 | 0.234526190 | 1579.262 | 472.582 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 249 | 0.235109392 | 583.202 | 472.502 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 250 | 0.235712608 | 603.216 | 472.822 | ACMD41 | `0x40300000` | Initialization poll 62/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 251 | 0.236245806 | 533.198 | 472.860 | R3 → ACMD41 | `0x00FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=0 (not valid until power-up completes); R3 has no CRC7 |
| 252 | 0.237825774 | 1579.968 | 472.996 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 253 | 0.238409456 | 583.682 | 472.798 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 254 | 0.239013140 | 603.684 | 472.888 | ACMD41 | `0x40300000` | Initialization poll 63/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 255 | 0.239546404 | 533.264 | 473.004 | R3 → ACMD41 | `0x40FF8000` | power-up still in progress; voltage window 2.7-3.6 V; CCS=1 (not valid until power-up completes); R3 has no CRC7 |
| 256 | 0.241125340 | 1578.936 | 472.290 | CMD55 | `0x00000000` | prefix next accepted command as an application command; addressed RCA 0x0000 |
| 257 | 0.241708124 | 582.784 | 472.294 | R1 → CMD55 | `0x00000120` | state when command arrived: IDLE; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 258 | 0.242311060 | 602.936 | 472.492 | ACMD41 | `0x40300000` | Initialization poll 64/64: request card power-up/operating conditions; host supports high-capacity cards: yes; host voltage window 3.2-3.4 V; 1.8 V switch requested: no |
| 259 | 0.242843870 | 532.810 | 472.056 | R3 → ACMD41 | `0xC0FF8000` | power-up complete; voltage window 2.7-3.6 V; CCS=1 (512-byte block addressing); R3 has no CRC7 |
| 260 | 0.243446548 | 602.678 | 472.536 | CMD2 | `0x00000000` | ask card for its CID identity register |
| 261 | 0.243979438 | 532.890 | 1356.850 | R2 → CMD2 | `0x035344534533324780A1CD45DB019C [bits127:8]` | card identity: manufacturer ID 0x03; OEM/application ID 'SD'; product 'SE32G'; revision 8.0; serial 0xA1CD45DB; manufacture 2025-12 |
| 262 | 0.245467000 | 1487.562 | 472.778 | CMD3 | `0x00000000` | ask card to publish a Relative Card Address (RCA); host does not assign the RCA in this command |
| 263 | 0.246050376 | 583.376 | 472.444 | R6 → CMD3 | `0xAAAA0520` | assigned RCA 0xAAAA; state when command arrived: IDENTIFICATION; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 264 | 0.246653572 | 603.196 | 472.728 | CMD9 | `0xAAAA0000` | read CSD capabilities/capacity register; RCA 0xAAAA |
| 265 | 0.247256934 | 603.362 | 1356.622 | R2 → CMD9 | `0x400E00325B590000EDC87F800A4040 [bits127:8]` | CSD structure 1 (SDHC/SDXC); capacity 62,333,952 sectors x 512 B = 31,914,983,424 B; default maximum transfer rate 25 MHz; read block length 512 B; write block length 512 B; permanent write-protect 0; temporary write-protect 0 |
| 266 | 0.248744182 | 1487.248 | 472.512 | CMD7 | `0xAAAA0000` | select card; RCA 0xAAAA |
| 267 | 0.249347336 | 603.154 | 472.488 | R1b → CMD7 | `0x00000700` | state when command arrived: STANDBY; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception; optional DAT0 busy phase is tracked separately |
| 268 | 0.249950604 | 603.268 | 472.528 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 269 | 0.250553810 | 603.206 | 472.330 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 270 | 0.251108872 | 555.062 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 271 | 0.251113696 | 4.824 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 272 | 0.251160538 | 46.842 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 273 | 0.251165208 | 4.670 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 274 | 0.251188394 | 23.186 | 3.786 | CMD55 | `0xAAAA0000` | prefix next accepted command as an application command; addressed RCA 0xAAAA |
| 275 | 0.251192906 | 4.512 | 3.788 | R1 → CMD55 | `0x00000920` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 276 | 0.251215286 | 22.380 | 3.788 | ACMD51 | `0x00000000` | read 8-byte SD Configuration Register (SCR) on data lines |
| 277 | 0.251219960 | 4.674 | 3.786 | R1 → ACMD51 | `0x00000920` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 278 | 0.253191532 | 1971.572 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 279 | 0.253196274 | 4.742 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 280 | 0.253221128 | 24.854 | 3.782 | CMD55 | `0xAAAA0000` | prefix next accepted command as an application command; addressed RCA 0xAAAA |
| 281 | 0.253225874 | 4.746 | 3.782 | R1 → CMD55 | `0x00000920` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 282 | 0.253247764 | 21.890 | 3.778 | ACMD6 | `0x00000002` | set native SD data width to 4 bits |
| 283 | 0.253252264 | 4.500 | 3.778 | R1 → ACMD6 | `0x00000920` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 284 | 0.253297566 | 45.302 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 285 | 0.253301830 | 4.264 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 286 | 0.253396176 | 94.346 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 287 | 0.253400920 | 4.744 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 288 | 0.253424322 | 23.402 | 3.782 | CMD17 | `0x00000000` | read one block at LBA 0 (byte offset 0); first sector of fixed slot 0 (project layout: 3,730 sectors/slot) |
| 289 | 0.253429228 | 4.906 | 3.780 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 290 | 0.254078190 | 648.962 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 291 | 0.254082612 | 4.422 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 292 | 0.254167178 | 84.566 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 293 | 0.254172008 | 4.830 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 294 | 0.254195198 | 23.190 | 3.784 | CMD17 | `0x00000E92` | read one block at LBA 3,730 (byte offset 1,909,760); first sector of fixed slot 1 (project layout: 3,730 sectors/slot) |
| 295 | 0.254200350 | 5.152 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 296 | 0.259948602 | 5748.252 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 297 | 0.259953104 | 4.502 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 298 | 0.260036124 | 83.020 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 299 | 0.260040548 | 4.424 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 300 | 0.260064120 | 23.572 | 3.784 | CMD17 | `0x00001D24` | read one block at LBA 7,460 (byte offset 3,819,520); first sector of fixed slot 2 (project layout: 3,730 sectors/slot) |
| 301 | 0.260068868 | 4.748 | 3.778 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 302 | 0.260448030 | 379.162 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 303 | 0.260452530 | 4.500 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 304 | 0.260535554 | 83.024 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 305 | 0.260540056 | 4.502 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 306 | 0.260563542 | 23.486 | 3.784 | CMD17 | `0x00002BB6` | read one block at LBA 11,190 (byte offset 5,729,280); first sector of fixed slot 3 (project layout: 3,730 sectors/slot) |
| 307 | 0.260568372 | 4.830 | 3.782 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 308 | 0.260945474 | 377.102 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 309 | 0.260950222 | 4.748 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 310 | 0.261033014 | 82.792 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 311 | 0.261037764 | 4.750 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 312 | 0.261061034 | 23.270 | 3.788 | CMD17 | `0x00003A48` | read one block at LBA 14,920 (byte offset 7,639,040); first sector of fixed slot 4 (project layout: 3,730 sectors/slot) |
| 313 | 0.261066108 | 5.074 | 3.782 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 314 | 0.261460372 | 394.264 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 315 | 0.261464638 | 4.266 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 316 | 0.261548016 | 83.378 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 317 | 0.261552844 | 4.828 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 318 | 0.261576034 | 23.190 | 3.784 | CMD17 | `0x000048DA` | read one block at LBA 18,650 (byte offset 9,548,800); first sector of fixed slot 5 (project layout: 3,730 sectors/slot) |
| 319 | 0.261581188 | 5.154 | 3.786 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 320 | 0.261979188 | 398.000 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 321 | 0.261983534 | 4.346 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 322 | 0.262066860 | 83.326 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 323 | 0.262071126 | 4.266 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 324 | 0.262094812 | 23.686 | 3.782 | CMD17 | `0x0000576C` | read one block at LBA 22,380 (byte offset 11,458,560); first sector of fixed slot 6 (project layout: 3,730 sectors/slot) |
| 325 | 0.262099478 | 4.666 | 3.786 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 326 | 0.262514386 | 414.908 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 327 | 0.262518648 | 4.262 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 328 | 0.262602004 | 83.356 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 329 | 0.262606830 | 4.826 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 330 | 0.262630004 | 23.174 | 3.782 | CMD17 | `0x000065FE` | read one block at LBA 26,110 (byte offset 13,368,320); first sector of fixed slot 7 (project layout: 3,730 sectors/slot) |
| 331 | 0.262635154 | 5.150 | 3.782 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 332 | 0.263035476 | 400.322 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 333 | 0.263040064 | 4.588 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 334 | 0.263123096 | 83.032 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 335 | 0.263127602 | 4.506 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 336 | 0.263151114 | 23.512 | 3.784 | CMD17 | `0x00007490` | read one block at LBA 29,840 (byte offset 15,278,080); first sector of fixed slot 8 (project layout: 3,730 sectors/slot) |
| 337 | 0.263155944 | 4.830 | 3.782 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 338 | 0.263532606 | 376.662 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 339 | 0.263537032 | 4.426 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 340 | 0.263620266 | 83.234 | 3.786 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 341 | 0.263624616 | 4.350 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 342 | 0.263648208 | 23.592 | 3.784 | CMD17 | `0x00008322` | read one block at LBA 33,570 (byte offset 17,187,840); first sector of fixed slot 9 (project layout: 3,730 sectors/slot) |
| 343 | 0.263652958 | 4.750 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 344 | 0.264153510 | 500.552 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 345 | 0.264158342 | 4.832 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 346 | 0.264242044 | 83.702 | 3.786 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 347 | 0.264246556 | 4.512 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 348 | 0.264270072 | 23.516 | 3.778 | CMD17 | `0x000091B4` | read one block at LBA 37,300 (byte offset 19,097,600); first sector of fixed slot 10 (project layout: 3,730 sectors/slot) |
| 349 | 0.264274896 | 4.824 | 3.786 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 350 | 0.264659140 | 384.244 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 351 | 0.264663888 | 4.748 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 352 | 0.264746664 | 82.776 | 3.786 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 353 | 0.264751416 | 4.752 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 354 | 0.264774656 | 23.240 | 3.780 | CMD17 | `0x0000A046` | read one block at LBA 41,030 (byte offset 21,007,360); first sector of fixed slot 11 (project layout: 3,730 sectors/slot) |
| 355 | 0.264779722 | 5.066 | 3.780 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 356 | 0.265285908 | 506.186 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 357 | 0.265290578 | 4.670 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 358 | 0.265373570 | 82.992 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 359 | 0.265378158 | 4.588 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 360 | 0.265401508 | 23.350 | 3.782 | CMD17 | `0x0000AED8` | read one block at LBA 44,760 (byte offset 22,917,120); first sector of fixed slot 12 (project layout: 3,730 sectors/slot) |
| 361 | 0.265406498 | 4.990 | 3.788 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 362 | 0.265791676 | 385.178 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 363 | 0.265796018 | 4.342 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 364 | 0.265879334 | 83.316 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 365 | 0.265883602 | 4.268 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 366 | 0.265907338 | 23.736 | 3.784 | CMD17 | `0x0000BD6A` | read one block at LBA 48,490 (byte offset 24,826,880); first sector of fixed slot 13 (project layout: 3,730 sectors/slot) |
| 367 | 0.265911928 | 4.590 | 3.788 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 368 | 0.266298198 | 386.270 | 3.786 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 369 | 0.266302710 | 4.512 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 370 | 0.266385818 | 83.108 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 371 | 0.266390238 | 4.420 | 3.774 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 372 | 0.266413710 | 23.472 | 3.782 | CMD17 | `0x0000CBFC` | read one block at LBA 52,220 (byte offset 26,736,640); first sector of fixed slot 14 (project layout: 3,730 sectors/slot) |
| 373 | 0.266418536 | 4.826 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 374 | 0.266795412 | 376.876 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 375 | 0.266800160 | 4.748 | 3.788 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 376 | 0.266883106 | 82.946 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 377 | 0.266887774 | 4.668 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 378 | 0.266911034 | 23.260 | 3.782 | CMD17 | `0x0000DA8E` | read one block at LBA 55,950 (byte offset 28,646,400); first sector of fixed slot 15 (project layout: 3,730 sectors/slot) |
| 379 | 0.266916106 | 5.072 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 380 | 0.267292652 | 376.546 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 381 | 0.267297396 | 4.744 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 382 | 0.267380172 | 82.776 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 383 | 0.267384918 | 4.746 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 384 | 0.267408162 | 23.244 | 3.778 | CMD17 | `0x0000E920` | read one block at LBA 59,680 (byte offset 30,556,160); first sector of fixed slot 16 (project layout: 3,730 sectors/slot) |
| 385 | 0.267413226 | 5.064 | 3.778 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 386 | 0.267913206 | 499.980 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 387 | 0.267917708 | 4.502 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 388 | 0.268000768 | 83.060 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 389 | 0.268005276 | 4.508 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 390 | 0.268028754 | 23.478 | 3.774 | CMD17 | `0x0000F7B2` | read one block at LBA 63,410 (byte offset 32,465,920); first sector of fixed slot 17 (project layout: 3,730 sectors/slot) |
| 391 | 0.268033572 | 4.818 | 3.780 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 392 | 0.268413478 | 379.906 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 393 | 0.268418300 | 4.822 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 394 | 0.268500976 | 82.676 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 395 | 0.268505800 | 4.824 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 396 | 0.268528952 | 23.152 | 3.776 | CMD17 | `0x00010644` | read one block at LBA 67,140 (byte offset 34,375,680); first sector of fixed slot 18 (project layout: 3,730 sectors/slot) |
| 397 | 0.268534094 | 5.142 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 398 | 0.269032742 | 498.648 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 399 | 0.269037248 | 4.506 | 3.786 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 400 | 0.269120356 | 83.108 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 401 | 0.269124776 | 4.420 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 402 | 0.269148262 | 23.486 | 3.784 | CMD17 | `0x000114D6` | read one block at LBA 70,870 (byte offset 36,285,440); first sector of fixed slot 19 (project layout: 3,730 sectors/slot) |
| 403 | 0.269153092 | 4.830 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 404 | 0.269537962 | 384.870 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 405 | 0.269542388 | 4.426 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 406 | 0.269625514 | 83.126 | 3.786 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 407 | 0.269629944 | 4.430 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 408 | 0.269653510 | 23.566 | 3.782 | CMD17 | `0x00012368` | read one block at LBA 74,600 (byte offset 38,195,200); first sector of fixed slot 20 (project layout: 3,730 sectors/slot) |
| 409 | 0.269658256 | 4.746 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 410 | 0.270042202 | 383.946 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 411 | 0.270046868 | 4.666 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 412 | 0.270129784 | 82.916 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 413 | 0.270134364 | 4.580 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 414 | 0.270157760 | 23.396 | 3.774 | CMD17 | `0x000131FA` | read one block at LBA 78,330 (byte offset 40,104,960); first sector of fixed slot 21 (project layout: 3,730 sectors/slot) |
| 415 | 0.270162660 | 4.900 | 3.778 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 416 | 0.270574522 | 411.862 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 417 | 0.270578864 | 4.342 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 418 | 0.270662036 | 83.172 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 419 | 0.270666294 | 4.258 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 420 | 0.270689998 | 23.704 | 3.776 | CMD17 | `0x0001408C` | read one block at LBA 82,060 (byte offset 42,014,720); first sector of fixed slot 22 (project layout: 3,730 sectors/slot) |
| 421 | 0.270694576 | 4.578 | 3.778 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 422 | 0.271186544 | 491.968 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 423 | 0.271191210 | 4.666 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 424 | 0.271275096 | 83.886 | 3.784 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 425 | 0.271279442 | 4.346 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 426 | 0.271303096 | 23.654 | 3.786 | CMD17 | `0x00014F1E` | read one block at LBA 85,790 (byte offset 43,924,480); first sector of fixed slot 23 (project layout: 3,730 sectors/slot) |
| 427 | 0.271307770 | 4.674 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 428 | 0.271687330 | 379.560 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 429 | 0.271692154 | 4.824 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 430 | 0.271774958 | 82.804 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 431 | 0.271779706 | 4.748 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 432 | 0.271802892 | 23.186 | 3.784 | CMD17 | `0x00015DB0` | read one block at LBA 89,520 (byte offset 45,834,240); first sector of fixed slot 24 (project layout: 3,730 sectors/slot) |
| 433 | 0.271808044 | 5.152 | 3.784 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 434 | 0.272200242 | 392.198 | 3.786 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 435 | 0.272204670 | 4.428 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 436 | 0.272288752 | 84.082 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 437 | 0.272293500 | 4.748 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 438 | 0.272316658 | 23.158 | 3.778 | CMD17 | `0x00016C42` | read one block at LBA 93,250 (byte offset 47,744,000); first sector of fixed slot 25 (project layout: 3,730 sectors/slot) |
| 439 | 0.272321804 | 5.146 | 3.786 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 440 | 0.272720720 | 398.916 | 3.774 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 441 | 0.272725136 | 4.416 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 442 | 0.272808260 | 83.124 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 443 | 0.272812602 | 4.342 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 444 | 0.272836248 | 23.646 | 3.778 | CMD17 | `0x00017AD4` | read one block at LBA 96,980 (byte offset 49,653,760); first sector of fixed slot 26 (project layout: 3,730 sectors/slot) |
| 445 | 0.272840908 | 4.660 | 3.780 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 446 | 0.273255722 | 414.814 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 447 | 0.273260384 | 4.662 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 448 | 0.273344340 | 83.956 | 3.774 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 449 | 0.273349156 | 4.816 | 3.774 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 450 | 0.273372278 | 23.122 | 3.778 | CMD17 | `0x00018966` | read one block at LBA 100,710 (byte offset 51,563,520); first sector of fixed slot 27 (project layout: 3,730 sectors/slot) |
| 451 | 0.273377420 | 5.142 | 3.776 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 452 | 0.273760630 | 383.210 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 453 | 0.273765048 | 4.418 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 454 | 0.273848126 | 83.078 | 3.772 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 455 | 0.273852460 | 4.334 | 3.774 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 456 | 0.273875984 | 23.524 | 3.774 | CMD17 | `0x000197F8` | read one block at LBA 104,440 (byte offset 53,473,280); first sector of fixed slot 28 (project layout: 3,730 sectors/slot) |
| 457 | 0.273880724 | 4.740 | 3.774 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 458 | 0.274257454 | 376.730 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 459 | 0.274262122 | 4.668 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 460 | 0.274345854 | 83.732 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 461 | 0.274350194 | 4.340 | 3.774 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 462 | 0.274373810 | 23.616 | 3.774 | CMD17 | `0x0001A68A` | read one block at LBA 108,170 (byte offset 55,383,040); first sector of fixed slot 29 (project layout: 3,730 sectors/slot) |
| 463 | 0.274378466 | 4.656 | 3.776 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 464 | 0.274870322 | 491.856 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 465 | 0.274875066 | 4.744 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 466 | 0.274957842 | 82.776 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 467 | 0.274962504 | 4.662 | 3.774 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 468 | 0.274985736 | 23.232 | 3.782 | CMD17 | `0x0001B51C` | read one block at LBA 111,900 (byte offset 57,292,800); first sector of fixed slot 30 (project layout: 3,730 sectors/slot) |
| 469 | 0.274990808 | 5.072 | 3.786 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 470 | 0.275368000 | 377.192 | 3.774 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 471 | 0.275372256 | 4.256 | 3.772 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 472 | 0.275455504 | 83.248 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 473 | 0.275460326 | 4.822 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 474 | 0.275483482 | 23.156 | 3.778 | CMD17 | `0x0001C3AE` | read one block at LBA 115,630 (byte offset 59,202,560); first sector of fixed slot 31 (project layout: 3,730 sectors/slot) |
| 475 | 0.275488626 | 5.144 | 3.778 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 476 | 0.275870964 | 382.338 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 477 | 0.275875300 | 4.336 | 3.772 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 478 | 0.275958444 | 83.144 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 479 | 0.275962704 | 4.260 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 480 | 0.275986414 | 23.710 | 3.776 | CMD17 | `0x0001D240` | read one block at LBA 119,360 (byte offset 61,112,320); first sector of fixed slot 32 (project layout: 3,730 sectors/slot) |
| 481 | 0.275990994 | 4.580 | 3.778 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 482 | 0.276385110 | 394.116 | 3.774 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 483 | 0.276389528 | 4.418 | 3.770 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 484 | 0.276472606 | 83.078 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 485 | 0.276476946 | 4.340 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 486 | 0.276500568 | 23.622 | 3.776 | CMD17 | `0x0001E0D2` | read one block at LBA 123,090 (byte offset 63,022,080); first sector of fixed slot 33 (project layout: 3,730 sectors/slot) |
| 487 | 0.276505228 | 4.660 | 3.776 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 488 | 0.276913862 | 408.634 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 489 | 0.276918682 | 4.820 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 490 | 0.277001370 | 82.688 | 3.774 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 491 | 0.277006106 | 4.736 | 3.774 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 492 | 0.277029332 | 23.226 | 3.780 | CMD17 | `0x0001EF64` | read one block at LBA 126,820 (byte offset 64,931,840); first sector of fixed slot 34 (project layout: 3,730 sectors/slot) |
| 493 | 0.277034398 | 5.066 | 3.774 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 494 | 0.277441212 | 406.814 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 495 | 0.277445952 | 4.740 | 3.780 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 496 | 0.277528690 | 82.738 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 497 | 0.277533352 | 4.662 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 498 | 0.277556652 | 23.300 | 3.776 | CMD17 | `0x0001FDF6` | read one block at LBA 130,550 (byte offset 66,841,600); first sector of fixed slot 35 (project layout: 3,730 sectors/slot) |
| 499 | 0.277561632 | 4.980 | 3.774 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 500 | 0.277953314 | 391.682 | 3.774 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 501 | 0.277957650 | 4.336 | 3.774 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 502 | 0.278040774 | 83.124 | 3.772 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 503 | 0.278045028 | 4.254 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 504 | 0.278068724 | 23.696 | 3.778 | CMD17 | `0x00020C88` | read one block at LBA 134,280 (byte offset 68,751,360); first sector of fixed slot 36 (project layout: 3,730 sectors/slot) |
| 505 | 0.278073304 | 4.580 | 3.776 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 506 | 0.278482934 | 409.630 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 507 | 0.278487352 | 4.418 | 3.778 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 508 | 0.278570384 | 83.032 | 3.776 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 509 | 0.278574802 | 4.418 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 510 | 0.278598328 | 23.526 | 3.774 | CMD17 | `0x00021B1A` | read one block at LBA 138,010 (byte offset 70,661,120); first sector of fixed slot 37 (project layout: 3,730 sectors/slot) |
| 511 | 0.278603064 | 4.736 | 3.776 | R1 → CMD17 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 512 | 0.278978680 | 375.616 | 3.774 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 513 | 0.278983256 | 4.576 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 514 | 0.279099262 | 116.006 | 3.786 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 515 | 0.279103610 | 4.348 | 3.782 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 516 | 0.279127750 | 24.140 | 3.780 | CMD55 | `0xAAAA0000` | prefix next accepted command as an application command; addressed RCA 0xAAAA |
| 517 | 0.279131932 | 4.182 | 3.784 | R1 → CMD55 | `0x00000920` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 518 | 0.279154222 | 22.290 | 3.782 | ACMD23 | `0x00000E92` | pre-erase hint for 3,730 blocks before next multiblock write; does not set its transfer length |
| 519 | 0.279158970 | 4.748 | 3.782 | R1 → ACMD23 | `0x00000920` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); APP_CMD set; no reported error/status exception |
| 520 | 0.279181646 | 22.676 | 3.780 | CMD25 | `0x00021B1A` | start multiblock write at LBA 138,010 (byte offset 70,661,120); continues until stop/count completion; project slot 37, 3,730 sectors are observed in this recording |
| 521 | 0.279186630 | 4.984 | 3.778 | R1 → CMD25 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 522 | 0.606964112 | 327777.482 | 3.784 | CMD12 | `0x00000000` | stop current multiblock transfer; check R1b and DAT0 busy release before considering card ready |
| 523 | 0.606968542 | 4.430 | 3.786 | R1b → CMD12 | `0x00000C00` | state when command arrived: RECEIVING DATA; READY_FOR_DATA=0 (card buffer not ready); no reported error/status exception; optional DAT0 busy phase is tracked separately |
| 524 | 0.607012956 | 44.414 | 3.778 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 525 | 0.607017458 | 4.502 | 3.778 | R1 → CMD13 | `0x00000E00` | state when command arrived: PROGRAMMING; READY_FOR_DATA=0 (card buffer not ready); no reported error/status exception |
| 526 | 0.608077484 | 1060.026 | 3.780 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 527 | 0.608082230 | 4.746 | 3.784 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |
| 528 | 0.608177650 | 95.420 | 3.782 | CMD13 | `0xAAAA0000` | query card status and readiness; RCA 0xAAAA |
| 529 | 0.608181996 | 4.346 | 3.776 | R1 → CMD13 | `0x00000900` | state when command arrived: TRANSFER; READY_FOR_DATA=1 (card buffer ready); no reported error/status exception |

## SCR data reply

The ACMD51 R1 response is followed by this separate data packet on DAT0:

- At **0.253146840 s**, 6.512 µs: SCR: structure 0; SD_SPEC 2; supports 1-bit and 4-bit; DATA_STAT_AFTER_ERASE=0x00; D0:OK 0x82B7/0x82B7.

The 38 CMD17 responses are likewise followed by 512-byte data packets.
All 38 read packets passed CRC16. Their timing and fields (without image previews)
are retained in `commands.json` under `read_data`.

## Invalid startup annotation

The decoder emits an invalid `CMD63 0xFFFFFFFF` from **-0.000029132 s** to **0.029737320 s**,
with received CRC7 `0x7F` versus calculated `0x0C`.
It spans an initial clock gap and is a known decoder framing artifact. It is
excluded from the genuine-command count and timing deltas, but preserved here
and in `commands.json`; it is not evidence that the firmware sent CMD63.
