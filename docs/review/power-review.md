# Power architecture review

> **Historical circuit, outstanding findings:** this review concerns the recovered TPS62132/TPS62825/AO3401A design. Four series CR2032 cells and LTC3621 are now selected for the prototype, but no replacement circuit is implemented. Use the [current power study](../../power.md) for accepted control behavior and the 100 nA main-path OFF target with separate RTC drain. The older load estimates below remain unmeasured historical assumptions.

The power system is not ready for layout release. Two confirmed latch faults need circuit changes: the shutter-sense connection exposes PC13 to the battery-level gate network, and automatic PWR_ON assertion reconnects the batteries during USB operation. The PFET divider has no gate-voltage margin at the specified fresh-cell voltage. Battery pulse capability and production power passives are also unqualified.

This review uses `hardware/reconstruction/schematic-connectivity.json` and the per-instance values **and unit fields** in the native Flux snapshot. It does not use old EDIF duplicate-name ordering. No schematic edits were made. Machine-readable findings, source hashes and PDF page/URL evidence are in `power-findings.json`. All page numbers below are PDF page numbers.

## Findings

| ID | Severity | Confidence | Finding |
|---|---|---|---|
| PWR-001 | Blocker | Confirmed | The battery gate pull-down drives PC13 through D3 when the latch is released. |
| PWR-002 | High | Confirmed | The nominal 13.2 V stack already produces the PFET's 12 V absolute maximum gate voltage. |
| PWR-003 | High | Confirmed | USB startup asserts PWR_ON and reconnects the higher-voltage batteries. |
| PWR-004 | Blocker | Measurement | Four CR2032 cells have no qualified pulse-power/capture-energy budget. |
| PWR-005 | High | Confirmed | Magnetics and high-value MLCCs have generic footprints and no production MPN/derating evidence. |
| PWR-006 | High | Confirmed | L3's target is below ST's current requirement; the local SMPS input bank is not allocated. |
| PWR-007 | Medium | Confirmed | The stated 8 V battery endpoint has no enforcing monitor or cutoff. |
| PWR-008 | Medium | Measurement | Existing leakage specifications do not establish a ten-year shelf-life guarantee. |

“Confirmed” describes the observed circuit or missing selection requirement. It does not mean every unselected inductor, capacitor or battery has been proved to fail. Measurement findings require a selected component and a representative workload.

### Latch, start, hold and shutdown

The actual battery current path is BAT_PLUS → Q1 drain/source → common source → Q3 source/drain → SYS_IN. Q1/Q3 are common-source back-to-back P-channel MOSFETs. R1 connects their common source to the shared gate. R2 connects that gate to LATCH_PULLDOWN. Q2 pulls LATCH_PULLDOWN to ground when PWR_ON is high. D3's **anode** is LATCH_PULLDOWN and **cathode** is SHUTTER_SENSE, which directly connects to U1 F3/PC13 and SW1.

That D3 orientation allows SW1 to start the latch and prevents an asserted Q2 from pulling the shutter input low. It also leaves a forward path from the battery to PC13 when both switch and Q2 are open. For the PFETs to turn fully off, their gate must approach the common-source voltage; D3 then drives PC13 toward that same battery voltage. PC13 is TT with a 3.6 V absolute input limit. If PC13 clamps instead, the clamp current drops voltage across R1 and keeps the PFETs on. Even an illustrative 3.6 V clamp plus 0.6 V diode drop leaves 3.45–8.18 V across R1 for an 8–13.2 V source. The exact input-clamp waveform is not needed to identify the incompatibility, but must be measured during correction. Separate low-voltage shutter sensing from the battery-level actuator. [DS14791, pp96 and 138](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=138)

With Q2 conducting, the DC divider gives:

`|VGS| = Vsource × R1/(R1+R2) = 13.2 × 1 MΩ/1.1 MΩ = 12.0 V`.

HUASHUO AO3401A permits only ±12 V. Opposed ±1% resistor variation gives 12.022 V; ±5% gives 12.105 V. There is no transient allowance. R1=1 MΩ/R2=330 kΩ with 1% tolerance is one possible DC-margin correction: below 10 V at 13.2 V and approximately 6 V drive at 8 V. A different PFET or characterized clamp is another option. A clamp must work at this circuit's microampere current without defeating shelf life. No proposed change has been applied. [Exact-vendor AO3401A manufacturer copy, pp1–2](https://datasheet.lcsc.com/datasheet/pdf/3df398cd119b96ff4752ae1fb5622b7c.pdf?productCode=C700954)

**PWR_ON is not a normal GPIO.** U1 E2 is powered from VDD, hence nominally 3.3 V here, and asserts automatically before firmware starts. It is low in Standby. This corrects the native Q2 role text claiming 1.8 V drive. Q2 only sinks approximately 13.2/1.1 MΩ = 12 µA in steady hold. The MCU 3.3 V-range output guarantee is VOH≥VDD−0.4 V at a load vastly greater than Q2/R3 impose. BSS138's threshold maximum is 1.5 V at 1 mA and 25°C; RDS(on) specifications at 4.5/10 V should not be mistaken for a requirement to drive this microampere load at those voltages. There is no demonstrated Q2 drive defect at the actual 3.3 V supply. Verify low-temperature release/hold after redesign, using guaranteed output levels and leakage. [DS14791, pp89,112 and171](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=171), [BSS138, p2](https://www.onsemi.cn/pdf/datasheet/bss138-d.pdf#page=2)

The MCU/boot review owns mandatory main-versus-auxiliary rail sequencing and the exact Standby/reset software procedure. The latch redesign must permit auxiliary rails to fall in the required order before removing the main supplies. Replacing PWR_ON with an arbitrary firmware GPIO would also discard its useful early automatic assertion and needs a startup-hold plan.

### USB coexistence

D2 is correctly oriented to block BAT/SYS_IN backfeed into VBUS. With Q1/Q3 **off**, their opposed body diodes block current between the battery and SYS_IN. These facts do not establish USB priority.

USB starts U2 and the MCU; automatic PWR_ON then turns Q2 on and enables both PFETs. An 8–13.2 V stack raises SYS_IN above the USB diode output, so D2 becomes reverse biased and the batteries power the session. When both PFET channels conduct, current can also travel from SYS_IN into a stack whose voltage is lower than SYS_IN. Add source selection and reverse-current control that keeps the battery disabled during USB-only downloading. Root's USB review covers VBUS inrush, port power entitlement, PHY power and connector protection. [AN5967, pp13 and 15–16](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=15)

### Battery and reservoir bounds

The provisional U2 output peak is 1.2 A at 3.3 V, or 3.96 W. Assuming 90% buck efficiency only for sizing, the series current is 333 mA at 13.2 V and 550 mA at 8 V, before sag. **Every cell carries this current.** Four series cells multiply voltage and resistance, not the mAh rating.

The archived Energizer candidate specifies 235 mAh under a 15 kΩ load and shows roughly 6.8 mA two-second pulses. These are typical reference tests, not a universal maximum-current rating. They do not qualify a several-hundred-milliampere startup/capture pulse. At a nominal 12 V open circuit, even an ideal resistive source needs total pack resistance ≤8.18 Ω, or ≤2.05 Ω per identical cell, to deliver 3.96 W through a 90%-efficient converter at its maximum-power point. Real contact resistance and converter operating constraints tighten that condition. Actual captured-image workload may be much smaller than the provisional peak and must be measured. [Energizer CR2032 reference, p1](https://data.energizer.com/pdfs/cr2032_eu.pdf)

| Nominal reservoir bound, C3+C4–C7=210 µF | Value |
|---|---:|
| Energy from 3.3 V all the way to 0 V | 1.143 mJ |
| Usable energy from 3.3 V to 3.0 V | 0.198 mJ |
| Time at 3.96 W from 3.3 V to 3.0 V | 50.1 µs |
| Energy if 3.96 W persisted for 50 ms | 198 mJ |
| Ideal capacitance for that 50 ms interval between 3.3 and 3.0 V | 0.210 F |

The capacitor example is a bound, not a proposed supercapacitor substitution: a larger store must first be charged and changes latency, leakage and energy. Other rail bypasses add some energy but do not change this order-of-magnitude result. DC-bias reduction makes the nominal reservoir estimate optimistic.

C8=3.3 nF gives approximately 1.65 ms U2 soft-start using its typical 2.5 µA charge current and 1.25 V ramp. Charging the 210 µF output bank alone takes roughly 0.42 A of output-capacitor current during a linear 3.3 V ramp, before downstream loads. Neither the IC's 3 A label nor the small output bank proves the cells can start the system. [TPS62132, pp5 and 16](https://www.ti.com/lit/gpn/TPS62132)

The U2 falling UVLO is 2.6–2.8 V, far below the stated 8 V four-cell endpoint, and EN is simply tied to SYS_IN. There is no stack ADC divider or cutoff in the recovered circuit. PG_3V3 and PG_1V8 each connect only to their own regulator and pull-up. Define an end-of-life/imbalance policy and provide detection before an unreliable capture/write, rather than treating 8 V as an enforced lower bound. [TPS62132, p5](https://www.ti.com/lit/gpn/TPS62132)

After correcting D3, off-state current still requires qualification. One sustained microampere consumes 87.6 mAh in ten years; five consume 438 mAh. The AO3401A maximum tests are at a higher VDS than this application, so these are budget bounds rather than predicted leakage. Do not add two full series-PFET leakage limits as though they were independent parallel paths. The RTC tap adds a small one-cell imbalance that the selected-cell lifetime model must include.

## Regulator and SMPS checks

| Part | Actual configuration | Assessment |
|---|---|---|
| U2 TPS62132RGTR | SYS_IN→3V3; EN=SYS_IN; fixed-version FB=GND; VOS=3V3; FSW=DEF=GND; SS=C8; all ground pins/EP grounded | Fixed-output connections are correct. Input range 3–17 V covers nominal battery and USB. FSW low selects about 2.5 MHz; 2.2 µH is allowed. 3 A rating does not establish battery capability. PG is unused by control logic. |
| U7 TPS62825DMQR | 3V3→1V8; EN=3V3; R5/R6=200 kΩ/100 kΩ; C12=120 pF; L2=0.47 µH | Divider gives 1.8 V; R6 and feed-forward capacitor match TI's example. ±1% feedback/reference and resistors give about 1.758–1.842 V before leakage/load/ripple. Maximum 50 nA FB leakage contributes up to about 10 mV through R5. 2 A IC rating is plausible; actual load/current budget unmeasured. PG unused. |
| U4 TLV70033DDCT | USB_VBUS→3V3_USB; EN=VBUS; C13/C14=1 µF | 2–5.5 V input, 200 mA rating, ±2% nominal output. At an illustrative full 200 mA and 5 V input, dissipation is 0.34 W; DDC reference θJA≈236°C/W implies ~80°C rise. This is not the actual expected PHY load; calculate using the selected USB mode. |
| U9 TLV70028DDCR | 3V3→CAM_VANA_2V8; MCU CAM_AVDD_EN with R21=100 kΩ low; C62/C63=1 µF | 200 mA rating versus module 21 mA maximum gives current margin; nominal loss at 21 mA is ~10.5 mW. 0.5 µA maximum enable leakage across 100 kΩ is 50 mV, below 0.4 V disable threshold. Camera review owns rail tolerance and required analog-first shutdown. |
| U10 NCP115AMX120TCG | 1V8→CAM_VCORE_1V2; EN=IN; C64/C65=1 µF; EP/GND grounded | 1.7–5.5 V input and 300 mA rating versus module 61 mA maximum. Nominal loss ~36.6 mW. Initial output 1.16–1.24 V fits the sensor's 1.10–1.26 V window, but full line/load/transient margin is narrow and belongs to camera review. 0.47 µF minimum effective output; no claim that exactly 1.2 V is guaranteed. |
| U12 TPS22918DBVT | 1V8→ACCEL_1V8_SW; R32=100 kΩ low; QOD directly to output; CT NC | Valid basic switching topology. At 1.8 V, on-resistance ≤88 mΩ over stated -40…105°C range; sensor current produces negligible DC drop. QOD≈45 Ω typical, 60 Ω maximum at 1.8 V. CT open selects the default fast ramp; root owns inrush/bus isolation. |
| U1 internal SMPS | Six VLX balls together→L3→VDDCORE; VFBSMPS senses output; VDDCSI on core; R19/C59 series snubber; V08CAP separate | Topological connections match the intended internal-SMPS architecture. L3, local input bypass, output impedance and main/aux sequencing are not signed off. |

Evidence: [TPS62132 pp3–5,14–16](https://www.ti.com/lit/gpn/TPS62132), [TPS62825 pp5–6,12–14](https://www.ti.com/lit/gpn/TPS62825), [TLV700 pp4–6,13](https://www.ti.com/lit/ds/symlink/tlv700.pdf), [NCP115 pp3,12](https://www.onsemi.cn/download/data-sheet/pdf/ncp115-d.pdf), [TPS22918 pp5–6](https://www.ti.com/lit/ds/symlink/tps22918.pdf).

U7's provisional 0.7 A peak is a workload assumption, not a full-temperature processor maximum. DS14791 p154 lists a characterized 757.5 mA VDDSMPS maximum at 125°C for one 800 MHz internal-SMPS condition, before camera core/IO and other loads on 1V8. This does not overload the 2 A regulator by itself; it means the 0.7 A system budget is not a worst-case bound. Clock/temperature/workload limits must be explicit. [DS14791, p154](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=154)

Current ST Table 6 requires L3=1 µH ±20%, Isat>3 A and DCR<60 mΩ. It lists local VDDSMPS 2×10 µF +2×1 µF +2×100 nF. The source allocates C10/C11 to the U7 output, while every other 1 µF on 1V8 is allocated to VREF, camera or U12; no two local SMPS 1 µF capacitors are identified. Nor are two local SMPS 100 nF parts identified in addition to the four VDDIO and six analog decouplers. Shared U7 output capacitors can only be justified by final loop geometry; even then the smaller local bank remains to be allocated. [AN5967 Rev5, pp12–13](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=13)

The 88 µF C15–C18 bank differs from ST's current 60 µF typical recommendation. DS14791 Table 27 also specifies 16–33 mΩ output impedance. More capacitance is not automatically a fault; select actual MLCCs and validate impedance, ramp and load transient behavior. R19=2 Ω/C59=2.2 nF and the separate C19 V08CAP net are correct. A simple switched-capacitor loss estimate for the snubber, C×V²×f at 1.8 V/2.4 MHz, is about 17 mW; choose an actual resistor with appropriate pulse/temperature capability. [DS14791, pp142–143](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=142)

## Power component coverage

Every capacitor/inductor below lacks a production MPN. Voltage/package entries are source values, not proof of effective capacitance or a purchasable footprint. Numeric values with separate units are resolved correctly: C72=100 nF, C73/C74=1 µF, R32=100 kΩ. Grouped rows have identical listed values for every reference.

| References | Actual value / rating / package | Connection or purpose | Review result |
|---|---|---|---|
| Q1,Q3 | HUASHUO AO3401A, SOT-23, -30 V, ±12 V VGS | Common-source battery isolation | Physical S/D/G mapping correct; PWR-001/002/003/008. |
| Q2 | onsemi BSS138, SOT-23, 50 V, ±20 V VGS | PWR_ON-controlled gate pull-down | Actual 3.3 V microampere hold is reasonable; source role text says 1.8 V incorrectly. |
| D2 | UMW SS34, SMB stock C2758511 / SS34B family | VBUS anode, SYS_IN cathode | Correct diode orientation; source-priority fault PWR-003 is elsewhere. Exact stock/suffix caveat retained in datasheets coverage. |
| D3 | Diodes Inc. 1N4148W-13-F | LATCH anode, SHUTTER cathode | Critical PWR-001. |
| SW1 | Omron B3U-3000P | SHUTTER_SENSE to GND | Starts latch; sensing requires redesign. |
| R1 | 1 MΩ, 0603, tolerance/voltage unspecified | Common source→PMOS_GATE | Gate return and divider; PWR-002. |
| R2 | 100 kΩ, 0603, tolerance/voltage unspecified | PMOS_GATE→LATCH_PULLDOWN | PWR-002. |
| R3 | 1 MΩ, 0603 | PWR_HOLD→GND | Defined Q2 gate discharge; ~3.3 µA load when high. |
| R4 | 100 kΩ, 0603 | 3V3→PG_3V3 | Valid pull-up, ~33 µA when PG low; no downstream monitor. |
| R5 | 200 kΩ, 1%, 0603 | 1V8→FB | Correct divider top. |
| R6 | 100 kΩ, 1%, 0603 | FB→GND | TI recommended maximum divider bottom. |
| R7 | 100 kΩ, 0603 | 1V8→PG_1V8 | Valid pull-up, ~18 µA when low; no downstream monitor. |
| R19 | 2 Ω, 0402, tolerance/power unspecified | SMPS snubber series resistor | Value/topology match ST; select pulse-rated part. |
| R20 | 100 kΩ, 1%, 0402 | CAM_XSHUTDOWN→GND | Camera review owns default-low leakage margin. |
| R21 | 100 kΩ, 1%, 0402 | CAM_AVDD_EN→GND | 50 mV worst specified EN-leak drop, adequate default-low margin. |
| R32 | 100 kΩ, 1%, 0402 | ACCEL_PWR_EN→GND | 0.1 µA ON-leak limit gives 10 mV; valid default low. |
| L1 | 2.2 µH, Isat target4 A, generic0603 | U2 SW→3V3 | Nominal inductance valid; DCR/RMS/MPN/footprint absent. At 13.2 V/2.5 MHz ripple≈0.45 A nominal. |
| L2 | 0.47 µH, Isat target3 A, generic0603 | U7 SW→1V8 | Nominal valid; at3.3 V/2.2 MHz ripple≈0.79 A. Qualify full current/bias margin and footprint. |
| L3 | 1 µH, Isat target2 A, generic0603 | MCU VLX→core | Below current ST >3 A target; no <60 mΩ DCR evidence. |
| C1 | 10 µF,25 V,0603 | SYS_IN input | Correct nominal input class; ≥10 µF effective target not established by nominal10 µF. |
| C2 | 100 nF,25 V,0603 | U2 AVIN bypass | Correct nominal value; place separately at AVIN/AGND. |
| C3 | 22 µF,6.3 V,0603 | U2 output | TI standard nominal output; qualify bias/ESR. |
| C4–C7 | Each47 µF,6.3 V,0603 | 3V3 reservoir | 188 µF nominal total; PWR-004/005. U2's checked LC table reaches nominal200 µF at2.2 µH; evaluate this210 µF bank plus downstream loads rather than assuming instability. |
| C8 | 3.3 nF, rating unspecified,0603 | U2 SS/TR | About1.65 ms typical soft-start; specify dielectric/tolerance. |
| C9 | 4.7 µF,6.3 V,0603 | U7 input | Must retain ≥3 µF effective. |
| C10,C11 | Each10 µF,6.3 V,0603 | U7 output | Total20 µF nominal, ≥10 µF effective required; local MCU sharing needs layout evidence. |
| C12 | 120 pF, rating unspecified,0603 | Across R5 | Correct feed-forward value; select stable dielectric. |
| C13,C14 | Each1 µF,10 V,0603 | U4 input/output respectively | Nominal TI values; U4 output must retain minimum effective capacitance. |
| C15–C18 | Each22 µF,4 V,0603 | Core output bulk | Total88 µF; validate versus ST60 µF typical/16–33 mΩ impedance. |
| C19 | 4.7 µF,4 V,0603 | V08CAP→GND only | Topology/value correct. ST reference uses6.3 V; lower voltage rating is not itself overvoltage, but effective-C equivalence is unproved. |
| C20–C25 | Each100 nF,6.3 V,0603 | 3V3 I/O-domain groups | Six available for four VDDIO2 and two VDDIO3 balls; confirm per-ball placement. |
| C26–C29 | Each100 nF,6.3 V,0603 | 1V8 I/O-domain groups | Four for two VDDIO4 and two VDDIO5 balls; confirm placement. |
| C30–C35 | Each100 nF,6.3 V,0603 | 1V8 analog domains | Six for AON/PLL/PMU/CSI/USB/ADC; C35 role says10 V but actual field6.3 V. Equivalent effective bypass must be demonstrated. |
| C39 | 100 nF,6.3 V,0603 | Boot NOR3V3 | Present; storage reviewer owns high-frequency/load requirements. |
| C40–C42 | Each100 nF,6.3 V,0603 | NAND3V3 | Present with C71 for four supply contacts. |
| C43 | 4.7 µF,10 V,0603 | USB_VBUS bulk | Present; root owns total port-visible capacitance/inrush. |
| C44–C49 | Each100 nF,10 V,0402 | Six MCU VDD balls | Count matches six balls; placement/MLCC quality still open. |
| C50–C58 | Each1 µF,6.3 V,0402 | Nine core balls | Count matches nine VDDCORE balls; placement still open. |
| C59 | 2.2 nF,50 V,0402 | VLX→snubber resistor | Correct ST nominal value; X7R/tolerance must be selected. |
| C60,C61 | 1 µF6.3 V and100 nF10 V,0402 | VREF+ on1V8 | Correct nominal local pair. |
| C62,C63 | Each1 µF,6.3 V,0603 | U9 input/output | Output≥0.1 µF effective; camera sequence/decay review separate. |
| C64,C65 | Each1 µF,6.3 V,0603 | U10 input/output | Output≥0.47 µF effective, ESR<1.8 Ω; nominal values suitable. |
| C66 | 100 nF,6.3 V,0402 | Camera VDDIO | Present with C70; camera review owns module-specific placement. |
| C67,C68 | Each100 nF,6.3 V,0402 | RTC VDD and single-cell backup | Present; root owns RTC backup configuration/leak paths. |
| C69 | 1 µF,6.3 V,0402 | MCU VDDCSI/core | Correct dedicated nominal bypass. |
| C70 | 1 µF,6.3 V,0402 | Camera1V8 | Host-side local bulk present. |
| C71 | 100 nF,6.3 V,0402 | Fourth NAND supply bypass | Present. |
| C72,C73 | 100 nF and1 µF,6.3 V,0402 | Switched accelerometer rail | Correct units; nominal bank1.1 µF, root owns switched-bus behavior. |
| C74 | 1 µF,6.3 V,0402 | U12 input1V8 | Present input bypass. |

U2/U4/U7/U9/U10/U12 are individually covered in the regulator table; U1 SMPS is covered above. C36/C37 are HSE load capacitors, C38 is NRST filtering, and boot/debug/I/O pull resistors are covered by the MCU/interface reviews. Test pads do not provide battery protection or energy storage.

## Required evidence before power routing

1. Correct the shutter/latch and USB-priority circuitry, coordinated with MCU main/aux sequencing; then verify all source/button/Standby combinations on a bench.
2. Select the battery and measure a realistic capture/save pulse profile over temperature, aging and contact resistance. Record both rail minima and total energy; establish an end-of-life policy.
3. Select L1–L3 and all high-value MLCCs; document bias, tolerance, RMS/saturation, DCR, loss and land patterns. Allocate local MCU SMPS bypass.
4. Verify startup, supply removal, regulator stability, load steps and off-state leakage on the corrected board. This includes interrupted NAND writes and cold/weak-cell starts; it does not assume firmware alone can fix invalid voltage domains.
