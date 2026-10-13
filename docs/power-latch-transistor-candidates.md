# Discrete power-latch transistor candidates

For the selected LTC3621 prototype direction and its unimplemented circuit study, see [power.md](../power.md). The [September 5 discrete PMOS proposal](power/pmos-latch-2026-09-05.md) records the subsequently sourced onsemi control NMOS and side-actuated switch. This file preserves the earlier transistor candidate comparison; it is not the current baseline. Its stock and electrical assumptions retain their original dates.

Research date: 2026-09-05. Candidate selection for the existing 8–13.2 V battery-stack assumption and 3.3 V control. This is a component recommendation, pending circuit and prototype qualification.

**Recommended low-leakage prototype combination: Diodes DMP2077UCA3-7 power PMOS and Toshiba SSM3K79FU,LF control NMOS.** Use two of the PMOS devices with their sources connected together when retaining bidirectional blocking while off. The controller NMOS carries only the gate-network current.

| Function / exact part | Voltage ratings | Drain leakage, IDSS maximum | RDS(on) maximum at 25°C |
| --- | --- | --- | --- |
| Power PMOS: Diodes DMP2077UCA3-7 | VDS −20 V; VGS ±12 V | 100 nA at VDS −16 V, VGS 0, TJ 25°C | 100 mΩ at VGS −4.5 V, ID −0.5 A; 78 mΩ at −8 V, −0.5 A |
| Control NMOS: Toshiba SSM3K79FU,LF | VDS 30 V; VGS ±20 V | 60 nA at VDS 30 V, VGS 0, TA 25°C | 6 Ω at VGS 2.5 V, ID 10 mA |
| Larger-package power fallback: AOS AO3407A | VDS −30 V; VGS ±20 V | 1 µA at VDS −30 V, VGS 0, 25°C; 5 µA at 55°C | 78 mΩ at VGS −4.5 V, ID −3 A; 48 mΩ at −10 V, −4.3 A |

Sources: [Diodes datasheet p2](https://www.diodes.com/datasheet/download/DMP2077UCA3.pdf#page=2), [Toshiba datasheet p3](https://toshiba.semicon-storage.com/info/docget.jsp?did=158872&prodName=SSM3K79FU), [AOS datasheet pp1–2](https://www.aosmd.com/sites/default/files/res/datasheets/AO3407A.pdf). These are drain-leakage limits, not the separate gate-leakage numbers. IGSS maxima are respectively 50 nA at ±12 V, 50 nA at ±5 V, and 100 nA at ±20 V, under each table's 25°C conditions. Those gate tests are not complete-circuit OFF-current specifications.

The Diodes device uses a very small X4-DSN1006-3 package. Its datasheet retains an Advanced Information label; obtain the controlled production specification before a production release. The manufacturer lists both -7 and -7A as Active in its [Master CofC, GL-106 Rev249, PDF p175](https://www.diodes.com/assets/Quality-Reliability-Docs/Master_CofC.pdf#page=175). The suffixes differ in tape orientation. Toshiba's [product page](https://toshiba.semicon-storage.com/ap-en/semiconductor/product/mosfets/detail.SSM3K79FU.html) identifies the SOT-323/SC-70 package and orderable ,LF suffix. AOS uses SOT-23. Stock and lead time must be checked when ordering.

## Gate network for the recommended pair

The PMOS gate must not be pulled directly to ground from a 13.2 V source: that exceeds its ±12 V gate rating. A suitable starting point is:

- 100 kΩ, 1%, from the PMOS common-source node to the joined PMOS gates.
- 47 kΩ, 1%, from the joined gates to a control node.
- Button and NMOS drain each connect to that control node; each pulls it toward ground when active. The button must use the same 47 kΩ path.
- NMOS source goes to ground. Its gate uses a 3.3 V HOLD signal and a ground pull-down; 47 kΩ is a starting value for the latter, subject to the controlling pin's powered/unpowered leakage.

Ignoring the sub-millivolt NMOS drop, the gate-drive magnitude is Vsource × 100/(100+47), approximately 5.44–8.98 V over 8–13.2 V. With 1% resistor tolerances the ratio is 0.67591–0.68461, giving approximately 5.41–9.04 V before load drop. The common-source voltage falls slightly under load; the low-end gate drive remains above 4.5 V at the illustrative current. This divider is not a transient clamp, so check the actual source and gate waveforms during insertion and switching.

When ON, the divider draws about 54–90 µA. At 90 µA, a 6 Ω NMOS drops only 0.54 mV. Milliohm control-NMOS resistance offers no useful benefit here. When OFF, the lower end floats and the gate follows the source; the resistor pair is not a permanent divider to ground. A larger pull-up therefore does not automatically save OFF current, and can make the circuit more sensitive to leakage.

## Loss and OFF-current limits

Using the review's illustrative 0.55 A battery current and 0.1 Ω per PMOS gives approximately 55 mV drop / 30 mW per device, or **110 mV / 61 mW for a back-to-back pair**. This is a sizing estimate using the 25°C resistance specification at 0.5 A, not a guarantee at every temperature or at startup. The actual battery current, inrush and switching safe operating area remain prototype checks.

Neither recommended datasheet gives an elevated-temperature IDSS maximum. The 100 nA and 60 nA values do **not** establish a ≤100 nA whole-latch limit, even at room temperature. Gate bias, GPIO interfaces, button/PCB surface leakage and other connected paths also matter. Measure complete OFF current at 8 V and 13.2 V across the intended storage-temperature range and humidity conditions.

Back-to-back PMOS devices block the body-diode path while off; their conducting channels do not provide reverse-current protection or USB source priority while on. Preserve a common ground and resolve that source-control behavior in the full latch circuit. The recovered battery-level shutter-to-PC13 path must not be carried into the corrected circuit; see the existing power review.

## Archived evidence

- [Diodes DMP2077UCA3 PDF](../datasheets/candidates/power-latch/Diodes_DMP2077UCA3.pdf), with verified source metadata and SHA-256.
- [AOS AO3407A PDF](../datasheets/candidates/power-latch/AOS_AO3407A.pdf), with verified source metadata and SHA-256.
- Toshiba's linked manufacturer PDF was readable through the research tool, but direct HTTPS archive requests returned HTTP 403; no local PDF is claimed.
- [Additional vendor screen](review/pmos-candidates-additional-vendors.md) records alternatives and exclusions.
