# Beta board power tree

**Status: agreed with the user on November 25, 2026, subject to the open points below; ST's answer on the SD bank decides between this tree and the fallback.** It answers the user's idea for the beta board: one buck for 1.8 V, and a 3.3 V rail the MCU switches on for the SD card. The idea holds, with four changes. A researcher built this from the stored ST, sensor and regulator documents and a second reader re-opened the citations and re-derived the numbers. Nothing here has been measured, and distributor figures are search snippets, not live pages.

Inputs settled with the user: a single LiPo, the Grepow GRP292434 (210 mAh, 2.9 mm cell, protection board unfolded flat beside it), and no charger; no USB on this revision, so the cell is the only source and the card is taken out to read the photos; an SD card on SDMMC2; unordered power-down accepted; the SPDT-and-capacitor start stays; ST-LINK is the only programming path.

**Changed November 26:** the user removed USB from this revision. The source-selection stage, the USB PHY supply and the VBUS protection are gone from the tree below. The MCU's USB supply pins are tied off as ST's hardware guide directs for an unused PHY.

**Changed November 27:** the RTC is powered from `3V3_SW` with the cell on its backup pin, as the user proposed, in place of the always-on 1.8 V regulator first suggested for it. Its bus runs at 3.3 V on MCU bank VDDIO4, which moves to `3V3_SW`. This uses the LiPo for this revision only: the user requires the eventual clock battery to be field-replaceable.

**Changed November 27:** the user asked for a fallback in case the internal SMPS gives trouble. The board carries unpopulated footprints for an external core regulator and two links that select it; see "Fallback: external core regulator" below. The default build is unchanged.

## The tree

| Block | Part class | Makes | Notes |
|---|---|---|---|
| Latch | the existing P-FET latch, SPDT switch and 2.2 µF trigger, held by an MCU pin | switched input | At a 3.0 V cell the trigger holds the gate for only about 40 ms, so the FET must be specified for 1.8 V gate drive. |
| Main buck | TI TPS6282x, 1.8 V (stored datasheet; used in the recovered design) | `1V8_MAIN` | Soft start 1.25 ms, inside ST's ramp limits. Feeds VDD, VDDA18AON, VDDA18PLL, VBAT, the unused banks and the boot flash. |
| Auxiliary switch | load switch enabled by `PWR_ON` (TI TPS22918, stored datasheet), with a bypass link | `1V8_AUX` | ST requires the main supplies up before the auxiliary ones. Feeds the internal SMPS, the ADC, CSI analog supplies, the sensor's I/O and the 1.2 V regulator. |
| Core | the MCU's internal SMPS; an external regulator is provisioned as a fallback and not fitted | 0.81 V | No extra converter and no firmware needed to start. Never run in this project: the Nucleo ships on its external buck. |
| SD rail | LDO with slow slew and active discharge (onsemi NCP115C 3.3 V, stored datasheet), enabled by an MCU pin with a pull-down | `3V3_SW` | Feeds the card and the MCU's SD pin bank (VDDIO5). From November 27 it also feeds the RTC's supply pin, the RTC bus pull-ups and the MCU bank that bus is on (VDDIO4). |
| RTC | Micro Crystal RV-3032-C7: supply pin on `3V3_SW`, backup pin on the cell through 1 kΩ with 1 µF at the pin | — | Level switchover mode: it runs from `3V3_SW` while the camera is on and from the cell while it is off. No regulator of its own. |
| Sensor analog | 2.8 V LDO from the input node | 2.8 V | Holds until the cell is near 2.75 V. |
| Sensor core | 1.2 V LDO from `1V8_AUX` | 1.2 V | Burns up to about 52 mW while streaming, which a LiPo can afford. |
| LED | low-side FETs from the input node | — | Fault blinks then work with the 3.3 V rail off. |

## Fallback: external core regulator (provisioned, not fitted)

**Status: designed on paper and checked once by a second reader, November 27. Nothing built, simulated or measured.** The same bare board can be built with the internal SMPS (default) or with an external regulator feeding the core, converted on the bench. ST supports both: with an external supply it calls the mode bypass, and the only setting is one firmware bit.

| Item | What it is | Default build | Fallback build |
|---|---|---|---|
| Link LK1 | selects what feeds VDDSMPS and, through the ferrite, VDDA18PMU. It sits before all their capacitors | to `1V8_AUX` | to ground, as ST requires when the SMPS is unused |
| Link LK2 | selects what feeds VDDCORE | the SMPS output | the regulator output |
| SMPS output parts | 1 µH coil, 4 x 15 µF, snubber, and VFBSMPS wired to these capacitors by a plain track | working | left in place, held at ground by the 10 kΩ |
| 10 kΩ | from the SMPS output to ground | fitted (costs 81 µA) | fitted |
| Regulator | TI TPS62825DMQR from the latched cell node, enabled by `PWR_ON`; 0.47 µH; two 10 µF in, two 10 µF out; feedback 34.8 kΩ over 100 kΩ with 120 pF | footprints empty | fitted |
| Test pads | VDDCORE with a ground pad beside it; the regulator's power-good | pads | pads |

- **Output voltage:** 0.809 V nominal, 0.795 to 0.828 V with 1% resistors, against ST's 0.790 to 0.830 V at the regulator and 0.782 to 0.842 V at the balls. The fallback is fixed at 0.81 V: no overdrive leg. Ball R10 (PB12), which the Nucleo uses to switch its regulator to 0.89 V, stays unassigned in case one is wanted later.
- **Input from the cell, not from 1.8 V:** the regulator needs at least 2.4 V, and this keeps the core current off the 1.8 V buck.
- **Power-up order:** the MCU raises `PWR_ON` by hardware only after the 1.8 V pins pass power-on reset, so the regulator cannot start early. The `PWR_ON` pull-down is 47 to 68 kΩ: at ST's drawn 470 kΩ, worst-case pin leakage could hold the regulator on.
- **Separate output capacitors:** the regulator has its own, and does not share the SMPS's 60 µF. That keeps VFBSMPS permanently on the SMPS's own capacitors, stays inside the capacitance TI tested, and lets the regulator be powered and measured before it is connected to the MCU.
- **The links:** each is two jumper sites sharing a centre pad and angled so that only one jumper can be fitted. They are low-resistance metal jumpers, as on the Nucleo, because LK2 carries the whole core current outside the regulation loop: an ordinary thick-film zero-ohm part can be tens of milliohms, and the whole budget for voltage drop is about 8 to 13 mV.
- **The path from the regulator to the core** is a pour 3 to 4 mm wide with several vias, 10 mm at most. The feedback divider senses at the regulator's own capacitors and is never moved past LK2.

### Converting a board to the fallback

Cell disconnected throughout, except where power is called for.

1. Move LK1 to ground. Meter: LK1 centre to ground reads 0 Ω; centre to `1V8_AUX` is not a short.
2. Remove LK2 and leave it off. Meter: SMPS output to VDDCORE reads about 10 kΩ or more, not near 0 Ω.
3. Fit the regulator, coil, four capacitors, two feedback resistors and the 120 pF. Meter before power: feedback pin to ground about 100 kΩ, feedback pin to the regulator output about 34.8 kΩ.
4. Power the board with the force-on pad held (with no core the MCU never asserts HOLD). Measure the regulator output at LK2: 0.795 to 0.830 V. Scope the turn-on for overshoot; from 0.61 V to 0.782 V should take under 180 µs. Load the output with 2.2 to 3.3 Ω and confirm it holds. Keep this state short.
5. Power off. Fit LK2 in the regulator position. Meter: SMPS output to VDDCORE still about 10 kΩ; regulator output to VDDCORE about 0 Ω.
6. Power on, check the VDDCORE test pad, and load firmware that clears the SMPS-enable bit.

To go back, reverse the two links; the regulator may stay fitted and runs unloaded.

### What can go wrong

- **A wrong feedback divider destroys the MCU.** Swapped resistors give 2.3 V and an open top resistor gives the cell voltage; VDDCORE's absolute maximum is 0.99 V. This is why the regulator is measured in step 4 before LK2 connects it.
- **Both supplies on VDDCORE at once.** ST documents this nowhere, and the internal SMPS starts by itself at every power-on whenever its input is powered. The shared-centre-pad links make it physically hard; the meter checks in steps 2 and 5 confirm it.
- **VDDSMPS left floating in a fallback build.** ST's Nucleo manual warns of a damaging inrush current. Step 1 ends with a 0 Ω reading to ground.
- **Start-up ramp.** The regulator's fixed soft start gives about 0.77 V/ms, inside the datasheet's limit on typical figures only and below the 0.86 V/ms ST's discrete-supply note asks for. The Nucleo's own regulator is reported to behave the same. Step 4's scope check is the acceptance test; a board that fails needs a different regulator.
- **Hot air near the cell or the MCU** when fitting the regulator later: place the regulator block clear of both.

### Firmware in the fallback build

- Clear SDEN (PWR_CR1 bit 2) as the first power action; it can be written once after power-on reset. If it is not cleared, ST says only that low-power modes will not work.
- Never select the high voltage range or run the CPU above 600 MHz: the regulator is fixed at 0.81 V and no flag reports the error.
- One image for both builds looks possible, since SDEN is said to read 0 in bypass. Untested.

## Why an LDO for 3.3 V

On a 3.0 to 4.2 V cell the drop is small: an LDO is 79 to 92% efficient between 4.2 and 3.6 V, and below about 3.4 V it simply follows the cell, which the card accepts down to 2.7 V. A buck would save under 10 mW for under a second per photo and add an inductor and ripple on the card and PHY supplies. The slow-slew version matters: ST limits these rails to between 20 and 1500 µs per volt, rising and falling, and the fast versions of the same LDO ramp at 5 µs per volt.

## The 1.8 V window

The MCU pins need 1.746 to 1.89 V: the floor is the CSI analog supply, the ceiling the internal SMPS input. A fixed 1.8 V buck leaves about 18 mV above the floor after the load switch. If that proves short, ST's own arrangement is the fallback: a small always-on 1.8 V regulator for the main group and the buck enabled by `PWR_ON`.

## Firmware rules this tree forces

- Switch `3V3_SW` on early in boot, not only for the save, so the card is ready when readout ends. Whether that adds image noise during the exposure has to be measured.
- Rail on: enable the LDO, wait a fixed time (the supply-ready flag does not work, erratum ES0620), set the bank's supply-valid bit, then start the card. Rail off: idle the card, stop SDMMC2, drive its pins low or high-impedance, clear the supply-valid bit, disable the LDO. Do this before releasing the latch.
- Never set the bank's 1.8 V range bit while it is at 3.3 V: ST says that damages the device.
- Never issue a backup-domain reset: a stored erratum says the internal SMPS output then drops and does not recover.
- The SD start-up profile assumes an already valid rail and must change.
- RTC: on first power-up write its EEPROM register C0h = 60h (clock output off, level switchover, trickle charger off). Until that is done the part ignores its backup pin and loses the time at every power-off. Read the RTC only after `3V3_SW` is up and bank VDDIO4's supply-valid bit is set; treat a set power-on flag as time lost.

## Open points

1. **Ask ST.** The datasheet's Table 24 limits inputs in the 3.3 V range to "Min(VDD, VDDIOx) + 0.3", which read literally forbids a 3.3 V SD bank beside a 1.8 V VDD. The hardware guide says the banks are independent and may be tied to the card supply, and the reference manual says they "can be independent from VDD", but no stored ST board shows the combination. Also ask whether one 1.8 V rail may feed both supply groups at once; if yes, the load switch is bridged.
2. **Try the internal SMPS on the Nucleo** before committing copper. UM3417 Table 7 gives the solder bridges. This is a function trial, not one of the power measurements the user declined. If it gives trouble on the beta board, the fallback above replaces it. Add to the question for ST: whether VLXSMPS and VFBSMPS may be held at ground through 10 kΩ in bypass (ST's figures disagree on VLXSMPS), and how long 1.8 V may be present with no core supply.
3. **The start trigger at a low cell.** Bench or simulate the SPDT-and-capacitor trigger at a 3.0 V cell, and limit the start-up surge well below the cell's 3 A protection trip.
4. **Low-battery lock-out** at about 3.3 to 3.4 V under load keeps both the 3.3 V rail and the 2.8 V regulator in regulation. It needs the chosen cell's resistance.
5. *(Removed with USB.)*
6. **Probe.** The board is 1.8 V: an STLINK-V3MINIE works from 1.65 V; a plain STLINK-V3SET needs its voltage adapter.
7. **RTC supply:** settled on November 27 (above), from third-party copies of the RV-3032 manual; re-check against Micro Crystal's own documents. It rests on the same answer from ST as the SD bank (point 1). The `3V3_SW` ramp sits at the lower edge of the RTC's stated power-on window; it matters only until the switchover mode is programmed.
8. The 2.8 V version of the LDO looked thinly stocked; buy it early or name an alternate.

## What would change this

ST says no to a 3.3 V bank beside a 1.8 V VDD: run VDD at 3.3 V as the prototype does, or put a level translator on the SD lines. The internal SMPS gives trouble: convert to the provisioned external core regulator. The card is ready within about 20 ms, or noise shows during exposure: switch 3.3 V on after readout. Operation is wanted below a 3.3 V cell: a buck-boost for 3.3 V.

Sources: DS14791 Rev 10, AN5967 Rev 5, AN6000 Rev 1, RM0486 Rev 4, ES0620 Rev 5, UM3417 Rev 4, the MB1940 C02 schematic and BOM, the VD56G3 and Swissbit S-56u datasheets, and the TI and onsemi regulator datasheets, all stored under `datasheets/`.
