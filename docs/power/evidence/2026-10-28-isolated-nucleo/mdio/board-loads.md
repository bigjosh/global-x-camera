# What firmware can reduce on the isolated Nucleo

2026-10-28, offline board audit. No power delta is assigned to an individual
component by this table. Camera and SD are currently physically disconnected;
the remaining prototype still contains development-board loads. D2 and R23
were already removed. Target power is direct regulated 5 V through JS110.

| Load | Firmware action possible | What remains / physical alternative |
|---|---|---|
| MCU CPU/buses/unused peripherals | Clock scaling, bounded WFI and clock gating; compare the same work and validate wake/recovery. | Difference between busy and WFI is a dynamic workload delta, not the entire MCU's draw. Keep needed SRAM, fabric, BSEC/debug and recovery clocks. Other agent owns these experiments. |
| Ethernet PHY U24 (LAN8742; not a regulator) | General power-down via MDIO BMCR bit11 is now measured in two isolated-board A/B/A runs: about36.76 mA /182.85 mW saving on the measured5 V branch. | Exact BMCR restoration passed; the short restored window returned DC current but not the original bursts. This is a scoped PHY-mode difference, not a complete-cycle saving. Removal of U24 eliminates its active die load; L5 alone removes only analog supply, leaving VDDIO connected. Keep reset/straps untouched in software tests. |
| Boot NOR | Stop accesses, deselect CS and gate XSPI after all required code is in RAM and operation is idle. Deep power-down is a separate part-specific qualification. | Standby current remains unless qualified deep power-down is used. Boot/recovery still requires NOR at the next power/reset cycle. Do not remove its supply during an active boot/read. |
| Red/green/blue user LEDs | PG10/PG0/PG8 HIGH turns active-low LD5/LD6/LD7 off. | Intentional indications are real energy. Modify only these GPIO bits; never reset GPIOG wholesale. |
| Arduino LD3 | Keep PE15/Q4 inactive. | Avoid attaching a test function that drives this indicator inadvertently. |
| USB-C U22 / associated paths | Keep PA7/EN low and PN7 OCP indicator inactive. CN8 is disconnected. | U22 still has auxiliary 3.3 V supply; software disable is not zero supply current. SB1 affects the provider path only. |
| Six ADC buffer amplifiers, U7/U8/U9 | No shutdown/enable input. Analog mode on the MCU does not switch these off. | Their VDDA1V8 supply is direct. Complete removal would lose Arduino analog conditioning and can affect slider inputs; lifting supply alone while inputs remain driven is not suitable. This is a small load, not the first rework target. |
| Debugger voltage-sense dividers | None: passive target-powered branches. | R65+R70 draw about165 µA from3.3 V; R73+R74 about331 µA from5 V. Opening source resistors removes those loads but changes debug voltage sensing. D2 removal alone does not remove signal/sense coupling. |
| Debugger interface pins | Peripheral/GPIO configuration can avoid active MCU outputs except those needed for recovery. | SWD/VCP/reset/sensing are still physical connections. Full isolation conflicts with convenient UART recovery/debug and requires a separate measurement setup. |
| Target power LED LD1 | Already disconnected by removal of R23. | Do not count this again as available saving. |
| Unused converter U14 ST1S31 | Already disabled: EN has no fitted pullup and has an internal pulldown. | Do not budget its enabled no-load specification as present overhead. Its fitted input/coupling capacitance still participates in startup. |
| VIN regulator U25 | No action needed with VIN disconnected and CN9 shunts absent. | It is not powered from the target5 V net in this hookup. |
| Core/main/AON/AUX regulators U17/U33/U23/U34/U26 | MCU shutdown can sequence auxiliary rails through the board's intended power control. | Required supplies and converter/LDO losses are not removed by CPU clock gating. Arbitrary GPIO rail disabling while the core runs is not a valid experiment. |
| Input/output capacitors and supply startup | Later firmware cannot undo inrush that happened before it executed. | Qualify startup separately. Soft start, precharge, regulator/capacitor changes or a different source/reservoir are hardware choices. Do not equate a raw unqualified startup sample maximum with true peak current. |

The remaining physical board load should be measured with matched controls.
Do not subtract catalog maxima from a trace and call the residual “intrinsic
STM32 power”; conversion efficiency, rail state, peripherals and firmware
activity change together. With the camera and SD removed, the result is an
isolated board baseline, not a capture/save energy measurement.

Primary board source is [MB1940 C02 schematic, sheets7–10/12/13](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf),
cross-checked against the local C02 BOM/ODB and the earlier
`tmp/hardware-review/nucleo-modifications/power-audit.md`.
Device behavior references: [LAN8742 power modes](https://www.microchip.com/content/dam/mchp/documents/OTH/ProductDocuments/DataSheets/DS_LAN8742_00001989A.pdf),
[TSZ122 pinout](https://www.st.com/resource/en/datasheet/tsz122.pdf),
[TCPP03-M20 EN behavior](https://www.st.com/resource/en/datasheet/tcpp03-m20.pdf),
[ST1S31 §4.5 enable](https://www.st.com/resource/en/datasheet/st1s31.pdf).
GPIO LED polarities are also established by
`firmware/capture-timing/status_leds/status_leds.h`.

Measured PHY evidence: `phy01/02` and `analysis/phy*-phy-analysis.json` in the
[isolated-Nucleo archive](../../../../../docs/power/evidence/2026-10-28-isolated-nucleo/README.md).
The saving uses the mean of the surrounding baseline windows; the pre/post
baseline difference and absent post-restore bursts limit waveform equivalence.
