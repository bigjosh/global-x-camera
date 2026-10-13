# Additional-vendor PMOS screen

2026-09-05. Bounded manufacturer-document screen for an 8-13.2 V high-side battery switch, illustrative 0.55 A peak. No hardware or BOM edits. Required drain-leakage limit is IDSS, not IGSS. Toshiba/Nexperia and AOS are covered separately.

**One conditional candidate found: Diodes DMP2077UCA3-7.** No second part was verified to meet both <=100 nA IDSS and <=0.2 ohm RDS(on) from the assigned vendors.

| Exact candidate | Guaranteed table conditions at 25 C | Integration boundary |
| --- | --- | --- |
| DMP2077UCA3-7 or -7A | VDS rating -20 V; IDSS max 100 nA at VDS=-16 V, VGS=0; RDS(on) max 100 mOhm at VGS=-4.5 V, ID=-0.5 A, or 78 mOhm at -8 V, -0.5 A; gate +/-12 V | Gate divider/clamp required for a 13.2 V pack. RDS test current is 0.5 A: validate illustrative 0.55 A and actual inrush/SOA. No 100 nA maximum specified at elevated temperature. |

[Manufacturer datasheet](https://www.diodes.com/datasheet/download/DMP2077UCA3.pdf), DS41537 Rev3-2, March 2020, pp1-2 and 6-7. The archived PDF p2 was rendered and visually checked. Separate IGSS limit is 50 nA. X4-DSN1006-3 is 1.0 x 0.6 x 0.2 mm nominal with 0.35 mm pitch; assembly/inspection and exact pad geometry need qualification. -7A rotates tape orientation 180 degrees relative to -7. Text extraction retains an Advanced Information label; seek a released controlled specification before production.

The current [Diodes Master CofC](https://www.diodes.com/assets/Quality-Reliability-Docs/Master_CofC.pdf), GL-106 Rev249, PDF p175, explicitly lists both suffixes **Active**. The [manufacturer product page](https://www.diodes.com/part/view/DMP2077UCA3) lists the same gate limit and 4.5 V on-resistance. Active status does not establish stock, lead time, or a hot-temperature leakage bound.

## Important exclusions

| Part | Exact reason it does not meet the requested combination | Primary evidence |
| --- | --- | --- |
| Diodes DMP3160L-7 | IDSS max 800 nA at -30 V, VGS=0, 25 C. RDS max 190 mOhm at -4.5 V, -2 A is otherwise near the target. | [DS31268 Rev11-2 p2](https://www.diodes.com/datasheet/download/DMP3160L.pdf) |
| Vishay Si2343CDS-T1-GE3 / -BE3 | IDSS max 1 uA at -30 V, VGS=0, 25 C; 5 uA at 55 C. RDS max 75 mOhm at -4.5 V, -3.2 A and +/-20 V gate are suitable for conduction/drive, but do not qualify leakage. | [Document 65474 pp1-2](https://www.vishay.com/docs/65474/si2343cds.pdf) |
| onsemi BSS84LT1G | Real 100 nA IDSS maximum at -25 V, VGS=0, 25 C; however RDS max is 10 ohm at -5 V, -100 mA. Excluded as the 0.55 A power switch. | [BSS84L family datasheet p2](https://www.onsemi.com/pdf/datasheet/bss84lt1-d.pdf) |
| onsemi NTR1P02T1G | IDSS max 1 uA at -20 V, VGS=0, 25 C; also RDS max 280 mOhm at -4.5 V, -0.75 A. | [NTR1P02 family datasheet p2](https://www.onsemi.com/pdf/datasheet/ntr1p02t1-d.pdf) |
| Infineon BSL308PE | IDSS max 1 uA at -30 V, VGS=0, 25 C. 130 mOhm at -4.5 V, -1.7 A meets conduction target. Official status active/preferred does not improve leakage guarantee. | [Datasheet Rev2.03 p2](https://www.infineon.com/assets/row/public/documents/24/49/infineon-bsl308pe-datasheet-en.pdf), [status](https://www.infineon.com/part/BSL308PE) |
| ROHM RQ3E120ATTB | IDSS max 1 uA at -30 V, VGS=0, 25 C; its low on-resistance does not make it a <=100 nA guaranteed switch. | [Manufacturer datasheet p2](https://rohmfs-rohm-com-cn.oss-cn-shanghai.aliyuncs.com/en/products/databook/datasheet/discrete/transistor/mosfet/rq3e120attb-e.pdf) |

At 0.55 A and 0.1 ohm, calculated conduction drop is 55 mV and dissipation 30.25 mW per FET, before temperature and inrush. These calculations do not establish switching SOA or hot leakage. A resistor divider must be sized from both battery extremes and gate-leakage tolerances, with every gate pull-down path included; clamp leakage must be counted in the sleep-current budget. Root owns that circuit integration.

The candidate PDF and adjacent provenance are under `docs/review/evidence/pmos-candidates/`; it is an unselected reference and was not added to the BOM datasheet catalog.
