# STM32N657 MCU hardware review

> **Scope as of October 13, 2026:** these findings describe the recovered schematic, not a revised prototype circuit. The [current specification](../../spec.md) and [power study](../../power.md) record later camera, shutter, USB and Standby decisions. They do not close boot-pin, voltage-domain or sequencing findings; verify those against the eventual implemented netlist. Older complete-frame timing discussions do not redefine the accepted 50 ms exposure-start deadline.

Review date: 2026-09-05. Device: U1 STM32N657X0H3Q, VFBGA264,14×14 mm,0.8 mm pitch. This review uses the current generated schematic's physical balls and native per-instance values. It does not assume that EDIF aliases, net names, or a zero-error ERC prove peripheral compatibility. No schematic was changed.

The present MCU circuit is not ready to route unchanged. There are five confirmed hardware issues: fixed ROM flash chip select, supply sequencing, NAND ready/busy, RTC interrupt voltage, and the NRST capacitor. The separate power review owns the battery-derived PC13 overvoltage and latch defects. Firmware integration can proceed later; the physical corrections and interface contracts below can be resolved now.

## Evidence and coverage

Baseline: `hardware/reconstruction/schematic-connectivity.json`, SHA256 `51e7cc050d23652d4eaf891e7384f519d6f3fd94c0c72f2dd945cbf626a62e98`. The recovered native source hash is recorded in the JSON companion. U1's 264-ball source map was previously compared against DS14791 Figure 13/p87 in `hardware/reconstruction/pin-map-review.md`. This review covers every connected functional GPIO, plus the dedicated power-control, reset, oscillator, USB and CSI interfaces. All source balls and net names below are read from the current connectivity JSON. Native spellings such as `VDDA18A_ON` were normalized only in explanatory prose.

Sources are the archived DS14791 Rev 10, AN5967 Rev 5, UM3234 Rev 5, RM0486 Rev 4 and ES0620 Rev 5 PDFs. URLs below point to the manufacturer document with a page anchor; the JSON also records local paths and SHA256. Confidence `confirmed` means the source conflicts with an explicit document requirement, `conditional` means the missing firmware/revision/operating choice determines the outcome, and `measurement` means a bound requires hardware characterization. A timing risk is not proof that all implementations fail.

## Findings

### MCU-001 — Boot NOR chip select is on the wrong ROM pin

**blocker / confirmed**. BOOT_XSPI_NCS connects U1 P14/PN12 to NOR /CS. PN12 AF9 is XSPIM_P2_NCS2. U1 R17/PN1 is unused. Other boot pins are PN6 CLK and PN2/PN3 IO0/IO1.

STM32N6 ROM uses a fixed PN1 AF9 chip select for serial NOR; the selected flash is not addressed by the ROM. Firmware in that flash cannot repair the pin selection before it has booted.

**Action:** Move BOOT_XSPI_NCS and its pull-up to U1 R17/PN1, AF9 XSPIM_P2_NCS1. Keep PN6/PN2/PN3; PN4/PN5 may serve quad data after the FSBL. Recheck pin-map and cold boot with a minimal signed/headered FSBL.

Evidence: [Sections 3.4.5-3.4.6, Table 27: fixed legacy SPI boot on PN6/PN1/PN2/PN3.](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf#page=13) (PDF pp.13,14,28); [VFBGA264 ball map and Table 20: PN1=NCS1; PN12=NCS2 at AF9.](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=87) (PDF pp.87,106,132).

### MCU-002 — Main and auxiliary MCU supplies cannot perform the mandatory sequence

**blocker / confirmed**. The single 1V8 net joins F6/VDDA18AON to VDDSMPS, VDDA18PMU, VDDA18ADC, VDDA18CSI, VDDA18USB and other domains. U7 EN is tied directly to 3V3. USB-derived 3V3_USB is generated independently from VBUS. PWR_ON only drives the battery latch.

AN5967 requires main VDD and VDDA18AON first, then auxiliary domains after PWR_ON rises. On shutdown auxiliary rails must discharge below 0.6 V while main supplies remain in their operating ranges. Tying AON to the auxiliary 1.8 V consumers prevents that independent sequence. USB-derived auxiliary power can also precede the main group. A successful bench startup would not establish compliance across corners.

**Action:** Separate the main 1.8 V AON domain from auxiliary domains and implement PWR_ON-controlled auxiliary enables with defined discharge and ordering on both battery and USB. Observe permitted exceptions for IO supplies tied to VDD and PLL tied to AON. Capture every rail and PWR_ON during cold start, shutdown, hot plug, brownout and rapid retry before release. Coordinate the latch fixes in power-review.md.

Evidence: [Section 3.5 and Figures2/3: mandatory main/AUX startup and shutdown sequence; AUX below 0.6 V before main shutdown.](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=8) (PDF pp.8,9,10); [Power-on control and PWR_CR1 POPL/MODE_PDN/SDEN behavior.](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=353) (PDF pp.353,356,357,385,386).

### MCU-003 — NAND ready/busy is routed to FMC_NWAIT instead of FMC_RNB

**high / confirmed**. NAND_RNB is on PF2/N4, whose AF12 is FMC_NWAIT. The actual dedicated FMC_RNB is available on unused PA7/R12 AF12 (also PE4/D10, but that pin uses the 1.8 V bank).

The N6 NAND controller uses its dedicated RNB input for automatic busy waits, sequencer tWB handling and ready/busy interrupts. FMC_NWAIT is not the same input. Software GPIO/status polling can be a separately validated fallback, but the intended hardware wait/sequencer path is unavailable as wired.

**Action:** Move NAND_RNB to PA7/R12 AF12 FMC_RNB on the 3.3 V VDD bank. Retain a suitable 3.3 V pull-up and configure NAND wait timing. Do not substitute PE4 without revisiting voltage compatibility.

Evidence: [PA7 supports FMC_RNB AF12; PF2 supports FMC_NWAIT AF12.](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=91) (PDF pp.91,124,128); [Table 185 and NAND control description distinguish RNB and its wait/interrupt uses.](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=1227) (PDF pp.1227,1230,1241).

### MCU-004 — RTC interrupt pull-up exceeds the receiving bank operating limit

**high / confirmed**. RTC_INT_N at U1 E7/PH2 is pulled to 3V3 by R24. PH2 belongs to VDDIO4, which is supplied by1V8.

DS14791 Table 24 recommends input voltage at most the receiving supply+0.3 V in the 1.8 V range (about 2.1 V here).3.3 V violates that operating limit. In default VRSEL=0 the TT absolute maximum is 3.6 V, so immediate damage is not proven; after selecting 1.8 V VRSEL=1 its absolute maximum is 1.98 V, making this also an overstress path.

**Action:** Pull RTC_INT_N up to 1V8, using the RTC open-drain output, or relocate it to a 3.3 V bank. Verify backup-only isolation and the revised supply order. Do not enable IO4 high-speed 1.8 V mode while this 3.3 V pull-up remains.

Evidence: [PH2 bank note 6; Table 21 TT absolute limits; Table 24 VIN operating limit.](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=105) (PDF pp.105,112,138,140); [PWR_SVMCR1 VDDIO4VRSEL and supply-valid controls.](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=393) (PDF pp.393).

### MCU-005 — NRST capacitor is ten times the specified maximum

**high / confirmed**. C38 is recorded as 100 nF in the native per-instance Capacitance field and connected from NRST to GND.

DS14791 Table 71 specifies CEXT maximum 10 nF. The existing load is outside the reset-pin characterization and can compromise internally generated or external reset pulses.

**Action:** Use C38 no greater than 10 nF, including its positive tolerance, and verify NRST low level and pulse timing with the selected debugger and switch. Apply the silicon-revision reset workaround where needed.

Evidence: [Section 5.3.18, Table 71 and Figure 25: CEXT maximum 10 nF; VIL maximum 0.65 V.](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=177) (PDF pp.177); [Section2.2.18: incorrect NRST reset behavior on affected revisions.](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf#page=10) (PDF pp.10).

### MCU-006 — The 50 ms capture target needs a bounded cold-boot payload and measured startup budget

**high / measurement**. The design physically cold-starts and loads firmware from serial NOR before capture; the spec targets image acquisition within 50 ms. ROM uses 32 MHz single-bit data transfer, not a quad data boot.

The ideal ROM data ceiling is4MB/s:100 KiB already needs 25.6 ms and 200 KiB needs 51.2 ms, before command/software/authentication overhead, rail startup, clock settling or sensor initialization. Large FSBL payloads alone can consume the complete budget. This is a quantitative risk, not a claim that every possible small FSBL fails.

**Action:** Create a small capture-first FSBL, keep noncritical code and NAND commit after acquisition, and measure shutter-to-rails, ROM completion, first MCLK, first I2C operation and first complete frame. Coordinate sensor-revision/patch bounds in the memory/sensor review. Define whether the deadline is exposure completion or frame arrival and reserve real margin; do not infer cold-boot latency from Standby wake figures.

Evidence: [Table14 single-line0Bh read with prescaler2; Table26 XSPI kernel from 64 MHz per_ck; no DMA for ROM SPI transfer.](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf#page=13) (PDF pp.13,14,26,28); [Low-power wake times are not cold boot; HSE crystal startup is 2 ms typical with no guaranteed maximum.](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=159) (PDF pp.159,161,162).

### MCU-007 — The 0.81 V core label must not be treated as an 800 MHz operating point

**medium / conditional**. The core/CSI rail is named VCORE_0V81 and the spec describes an 800 MHz MCU. The core rail is produced by the programmable internal SMPS, not a fixed external 0.81 V regulator.

VOS low uses nominal 0.81 V and permits at most 600 MHz CPU;800 MHz requires VOS high, nominal 0.89 V. There is no supplied firmware proving which operating point will actually be used. A fixed 0.81 V/800 MHz configuration would be out of specification.

**Action:** Choose the lowest operating point that meets capture timing; if using 800 MHz, program VOS high and wait for readiness before raising CPU frequency. Validate0.858-0.921 V at the core at high VOS and account for its increased transient load. Rename the rail to VDDCORE during an approved schematic revision if it will change voltage.

Evidence: [Table 24: CPU600MHz low VOS/800 MHz high VOS; VDDCORE ranges0.782-0.842 V and0.858-0.921 V.](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=139) (PDF pp.139,140).

### MCU-008 — Shutdown and bank setup need an N6-specific early firmware contract

**high / conditional**. PWR_HOLD uses dedicated PWR_ON, while the camera/control interfaces use independent 1.8 V banks and the boot flash uses VDDIO3. Firmware is not yet in the repository.

PWR_ON is a hardware-controlled VDD output, not a writable GPIO: it asserts after main POR and drops in Standby. Firmware that attempts to clear an ordinary GPIO will not release this latch. IO supply-valid controls, voltage-range settings and current errata also affect whether MCLK/control pins work and whether output duty cycles meet specification.

**Action:** Implement shutdown by saving/isolating external devices then entering the appropriate Standby sequence; program a sufficient POPL minimum low interval and required discharge, retaining BSECEN. Validate VDDIO3/4/5 supplies before enabling them; select correct voltage modes and OTP HSLV settings only for the corresponding physical voltage. Apply ES0620 fixed I/O-compensation workaround and coupled supply-valid access requirements. Do not fuse OTP until the final supply plan is reconciled.

Evidence: [PWR_ON powered by VDD; independent-bank voltage selection follows actual bank supplies.](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=89) (PDF pp.89,112); [PWR_ON in Standby; POPL default no guaranteed low time; MODE_PDN defaults off; supply-valid and VRSEL controls.](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=356) (PDF pp.356,357,385,386,393,394,396); [Sections2.2.2,2.2.19,2.2.20: BSECEN requirement and fixed compensation0x287 workaround.](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf#page=7) (PDF pp.7,11).

### MCU-009 — The 40 MHz crystal network needs startup and load qualification

**medium / measurement**. Y1 is CX3225SA40000D0PTWCC,40 MHz,CL 8 pF,ESR 50 ohm maximum; C36/C37 are 8.2 pF each. ST allows16-48 MHz crystals.

The first-order load estimate8.2/2+4=8.1 pF matches the requested 8 pF using ST's rough 4 pF stray estimate, so the capacitor values are not demonstrably wrong. Actual parasitics, crystal shunt capacitance, drive and startup margin remain unverified. HSERDY detects initial cycles and does not guarantee stable frequency.

**Action:** Use C0G load capacitors and a short oscillator layout. Obtain the crystal shunt-capacitance/startup data, check critical-gm margin against the MCU 1.95 mA/V capability, and measure drive level, frequency and worst-case stable-start time across voltage/temperature. Budget that measured time before enabling USB/camera timing-critical paths.

Evidence: [Table 49:16-48 MHz, maximum critical crystal gm 1.95 mA/V;4 pF rough combined parasitics;2 ms typical startup.](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=161) (PDF pp.161,162); [Section7.2: crystal selection and C0G load capacitors with PCB/pin capacitance.](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=21) (PDF pp.21); [Section2.2.24: HSERDY is not frequency-stability assurance.](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf#page=12) (PDF pp.12); [Kyocera exact-MPN specification, historical TI-hosted copy:40 MHz, CL 8 pF, ESR maximum 50 ohm, drive maximum 200uW. Confirm current procurement specification.](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/CX3225SA40000D0PTWCC_5F00_DS.pdf#page=3) (PDF pp.3).

### MCU-010 — Silicon revision and cold-reset recovery must be recorded before bring-up

**medium / conditional**. The part number specifies STM32N657X0H3Q but no purchased silicon revision or ROM version is recorded. SWD pins are connected; BOOT0 and NRST pads exist, while PA6/BOOT1 only has a pull-down.

ES0620 describes revision-dependent reset/boot fallbacks and all-revision clock/SMPS limitations. A stuck reset path or invalid flash state may require a real power cycle. REV_ID alone does not distinguish Z/B/X in this errata; assuming generic STM32 reset behavior would weaken recovery.

**Action:** Record package revision marking and ROM version, apply applicable NRST and software-reset clock-mux workarounds, and avoid the internal-SMPS backup-domain reset limitation. Keep accessible SWD/NRST, BOOT0, a way to force PA6/BOOT1 development boot, and a true power-cycle path during prototype bring-up. Keep flash in a ROM-readable state before warm reset and verify production boot/recovery before locking debug or fusing boot options.

Evidence: [Revision matrix;2.2.1 APB prescaling;2.2.5 REV_ID;2.2.12/13 FSBL fallback;2.2.15 VSWRST/SMPS;2.2.18 NRST;2.2.22 reset clocks.](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf#page=1) (PDF pp.1,2,7,9,10,12); [Boot1 priority/development flow, no special serial-NOR setup, ROM version and diagnostics.](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf#page=8) (PDF pp.8,9,14,20,22); [Boot configuration and debug management.](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=24) (PDF pp.24,25).

## Complete connected GPIO/alternate-function matrix

“Pass” is a physical function/nominal-voltage check, not a timing, sequencing or firmware implementation sign-off. GPIO functions need the stated GPIO mode rather than an AF number. Hardware I2C uses AF with open-drain outputs. All banks still require the power-sequence correction. Supply memberships follow DS14791 Table 18 notes on p112; source VDDIO2/3 are 3.3 V and VDDIO4/5 are 1.8 V. PH0/PH1 are VDDA18AON-powered oscillator pads (DS p105 note2), not ordinary 3.3 V GPIOs.

| MCU ball | GPIO | Source net | Required function | Bank/nominal supply | Validation | DS page |
|---|---|---|---|---|---|---|
| U10 | PA0 | NAND_D7 | AF12 FMC_D7 | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| P9 | PA1 | NAND_D6 | AF12 FMC_D6 | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| T8 | PA2 | NAND_D5 | AF12 FMC_D5 | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| R14 | PA3 | NAND_ALE | AF12 FMC_A17/ALE | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| U14 | PA4 | NAND_NWP | GPIO output (NAND /WP) | VDD /3.3 V | Pass; keep /WP asserted until NAND setup is complete. | 113 |
| R8 | PA5 | NAND_NOE | AF12 FMC_NOE | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| P8 | PA6 | BOOT1 | BOOT1 input sampled by ROM | VDD /3.3 V | Pass pull-down; add practical development-boot access. | 91 |
| U8 | PA8 | NAND_D4 | AF12 FMC_D4 | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| P7 | PA9 | NAND_D3 | AF12 FMC_D3 | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| R7 | PA10 | NAND_D2 | AF12 FMC_D2 | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| T7 | PA11 | NAND_D1 | AF12 FMC_D1 | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| U7 | PA12 | NAND_D0 | AF12 FMC_D0 | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 124 |
| U6 | PA13 | SWDIO | AF0 JTMS/SWDIO | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 113 |
| T6 | PA14 | SWCLK | AF0 JTCK/SWCLK | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 113 |
| U12 | PB5 | SWO | AF0 JTDO/TRACESWO | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 114 |
| C10 | PC0 | STATUS_LED_K | GPIO output LED sink | VDDIO5 /1.8 V | Conditional: LED fed from 3.3 V; qualify off leakage/ghosting and powered-off state. Physical LED polarity is correct. | 115 |
| A9 | PC1 | ACCEL_PWR_EN | GPIO output load-switch enable | VDDIO4 /1.8 V | Pass 1.8 V control of TPS22918; sensor bus pull-ups follow switched rail. | 115 |
| D9 | PC2 | ACCEL_I2C_SCL | GPIO open-drain software I2C | VDDIO5 /1.8 V | Pass 1.8 V switched pull-ups; remain high impedance until ACCEL_VDD is present. | 115 |
| E10 | PC3 | ACCEL_I2C_SDA | GPIO open-drain software I2C | VDDIO5 /1.8 V | Pass 1.8 V switched pull-ups; remain high impedance until ACCEL_VDD is present. | 115 |
| A10 | PC4 | ACCEL_INT1 | GPIO input/EXTI | VDDIO5 /1.8 V | Pass 1.8 V accelerometer interrupt; keep safe when sensor unpowered. | 115 |
| D7 | PC8 | CAM_XSHUTDOWN | GPIO output sensor shutdown | VDDIO4 /1.8 V | Pass 1.8 V camera control; firmware sequence pending sensor review. | 115 |
| C7 | PC9 | CAM_MCLK | AF0 MCO2 | VDDIO4 /1.8 V | Pass clock-capable 1.8 V pin; HSE/2 gives 20 MHz; verify required sensor mode and duty cycle. | 115 |
| A8 | PC10 | I2C4_SCL | AF4 I2C4_SCL | VDDIO4 /1.8 V | Pass 1.8 V pull-ups; configure open-drain and external-bus timing. | 115 |
| B8 | PC11 | I2C4_SDA | AF4 I2C4_SDA | VDDIO4 /1.8 V | Pass 1.8 V pull-ups; configure open-drain and external-bus timing. | 115 |
| C8 | PC12 | CAM_AVDD_EN | GPIO output camera LDO enable | VDDIO4 /1.8 V | Pass 1.8 V enable capability; camera sequencing pending sensor review. | 115 |
| F3 | PC13 | SHUTTER_SENSE | GPIO input shutter | VDD_VSW /3.3 V | Fail external battery-derived input topology; see PWR-001. | 115 |
| C11 | PE5 | RTC_I2C1_SCL | AF4 I2C1_SCL | VDD /3.3 V | Pass 3.3 V RTC pull-up; verify RTC backup isolation. | 117 |
| D11 | PE6 | RTC_I2C1_SDA | AF4 I2C1_SDA | VDD /3.3 V | Pass 3.3 V RTC pull-up; verify RTC backup isolation. | 117 |
| N4 | PF2 | NAND_RNB | AF12 FMC_NWAIT (wrong for RNB) | VDD /3.3 V | Fail MCU-003; move to PA7/R12 AF12 FMC_RNB. | 128 |
| N3 | PF8 | NAND_NWE | AF12 FMC_NWE | VDD /3.3 V | Pass at nominal connected voltage; configure timing and supply state. | 129 |
| T10 | PG10 | NAND_CLE | AF12 FMC_A16/CLE | VDD /3.3 V | Pass; ROM can use PG10 for boot-failure UART5_TX diagnostics, so retain NAND deselect/write-protect defaults. | 130 |
| P6 | PG14 | NAND_NCE | AF10 FMC_NCE | VDD /3.3 V | Pass at AF10; AF12 is FMC_NE2 and must not be selected for NAND CE. | 130 |
| A7 | PH0 | HSE_IN | Dedicated HSE OSC_IN | VDDA18AON /1.8 V (oscillator) | Pass 40 MHz crystal range; oscillator runs from VDDA18AON, see MCU-009. | 161 |
| B7 | PH1 | HSE_OUT | Dedicated HSE OSC_OUT | VDDA18AON /1.8 V (oscillator) | Pass 40 MHz crystal range; oscillator runs from VDDA18AON, see MCU-009. | 161 |
| E7 | PH2 | RTC_INT_N | GPIO input/EXTI | VDDIO4 /1.8 V | Fail MCU-004:3.3 V pull-up on 1.8 V bank. | 120 |
| T17 | PN2 | BOOT_XSPI_IO0 | AF9 XSPIM_P2_IO0 | VDDIO3 /3.3 V | Pass 3.3 V flash; ROM uses IO0/1 only, quad IO2/3 are application use. | 132 |
| R15 | PN3 | BOOT_XSPI_IO1 | AF9 XSPIM_P2_IO1 | VDDIO3 /3.3 V | Pass 3.3 V flash; ROM uses IO0/1 only, quad IO2/3 are application use. | 132 |
| N17 | PN4 | BOOT_XSPI_IO2 | AF9 XSPIM_P2_IO2 | VDDIO3 /3.3 V | Pass 3.3 V flash; ROM uses IO0/1 only, quad IO2/3 are application use. | 132 |
| R16 | PN5 | BOOT_XSPI_IO3 | AF9 XSPIM_P2_IO3 | VDDIO3 /3.3 V | Pass 3.3 V flash; ROM uses IO0/1 only, quad IO2/3 are application use. | 132 |
| P15 | PN6 | BOOT_XSPI_CLK | AF9 XSPIM_P2_CLK | VDDIO3 /3.3 V | Pass 3.3 V flash clock, including fixed ROM boot assignment. | 132 |
| P14 | PN12 | BOOT_XSPI_NCS | AF9 XSPIM_P2_NCS2 | VDDIO3 /3.3 V | Fail MCU-001: ROM requires PN1/R17 AF9 NCS1. | 132 |

Coverage check: **41 connected GPIO/oscillator pads**, with no uncovered or duplicate assignments. Source physical balls match the exact VFBGA264 device; references are DS Tables 18–20, with AF0–7 in Table 19 and AF8–15 in Table 20. [Pin and AF tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=89).

## Dedicated interfaces and boot/recovery

| MCU balls | Source function | Assessment |
|---|---|---|
| E2 | PWR_ON → PWR_HOLD |3.3 V VDD-powered hardware output; automatically high after main POR, high in Run/Sleep/Stop, low in Standby. It is not a software GPIO. |
| G4 | BOOT0 | R8 pull-down selects normal boot with BOOT1 low. TP6 and optional SW2 provide access. SW2 connects to 1V8, requiring a threshold-margin check below. |
| G3 | NRST | Correct dedicated reset pad and debug connection; C38 is excessive (MCU-005). |
| A1 | PDR_ON →1V8 | Correct tie to VDDA18AON in the current topology; preserve that tie when splitting rails. |
| E1 | VBAT →3V3 | Allowed VDD tie; MCU backup domain does not retain power when the main latch turns off. The external RTC provides retention. |
| T3/U3 | CSI_CKP/CKN | Correct dedicated CSI clock polarity. |
| T5/U5 | CSI_D0P/D0N | Correct dedicated CSI lane 0 polarity; second lane unused. One-lane mode/rate and CSI/DCMIPP setup still require the sensor-mode review. |
| P5 | CSI_REXT | R17 is 200 Ω, 1%, to GND. This matches AN5967 §13.5 p35 and DS14791 Table125 p234 (198–202 Ω). Place it close to the pin with a short, quiet ground return. |
| R4 | VDDCSI →VCORE_0V81 | Correct shared core-voltage class; must follow actual VOS operating point and sequencing. |
| A5/B5 | OTG1_HS_DM/DP | Correct dedicated USB1 pair polarity; root review owns external USB network and VBUS sensing. |
| C6 | OTG1_TX_RTUNE | R18 is 200 Ω, 1%, to GND. This matches RM0486 Table723 p3748, AN5967 §13.3.1 p29 and DS14791 Table126 p235 (198–202 Ω). Place it close to the pin with a short, quiet ground return. |

The R17/R18 values above come from the native per-instance `Resistance` and `Tolerance` fields, not from the shared descriptive alias. Their respective nets are `CSI_REXT` and `USB_TX_RTUNE`; both return to GND. Value/tolerance checks pass. [CSI guidance](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=35), [USB PHY electrical requirements](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=235).

Unused USB2 pads are A3/HSDM, B3/HSDP, D6/TXRTUNE and E6/ID, all explicitly NC in this snapshot. AN5967 Rev5 Table5 footnote2 on p8 specifies grounded DP/DM and open TXRTUNE when USB/UCPD features are unused. This supports leaving unused TXRTUNE open and recommends reviewing a ground connection for the unused data pair, with PHY2 kept disabled. The footnote is written for unused USB/UCPD features as a group, not explicitly for one unused port while the other is active; therefore the present USB2 data-pair NC is recorded as a **conditional unused-port treatment item**, not a confirmed functional fault. Do not ground the shared USB supplies because USB1 is used. The newer controlled application note takes precedence over older, inconsistent forum recommendations. [AN5967 unused-feature note](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=8).

ROM normal serial-NOR boot uses PN6/PN1/PN2/PN3, AF9; BOOT0=0 and BOOT1=0 select flash boot, with unfused default selecting serial NOR. BOOT1=1 requests development boot where allowed by lifecycle state and takes priority over BOOT0. BOOT0=1/BOOT1=0 selects serial recovery. Final OTP/lifecycle settings must be recorded, not inferred from the pin straps. The default SPI read is 0Bh with 24-bit addressing and 8 dummy cycles. PN4/PN5 are application quad-data pins rather than ROM boot data pins. Keep IO2/WP and IO3/HOLD safe during reset; the memory review owns exact flash-state and pull-up details.

The6-pin debug net assignment is electrically consistent with SWD: J2.1=3V3 reference, .2=PA13 SWDIO, .3=GND, .4=PA14 SWCLK, .5=NRST, .6=PB5 SWO. Do not rely on the debugger to power an unpowered bank. A reachable PA6 development-boot pad/jumper and true main-rail power-cycle path are advisable on the prototype, especially before debug locking. PG10 is shared with ROM boot-failure diagnostics; its NAND CLE connection is acceptable only while NAND remains deselected and write-protected during boot failures.

SW2's 1.8 V drive is **not a confirmed logic fault**. BOOT0 is a VDD-powered TT input. DS Table 65 gives VIH=0.52×VDD−0.11, or 1.606 V at 3.3 V, so nominal 1.8 V is high. Across the full independent MCU ranges VDD=3.6 V needs 1.762 V, which 1.71 V cannot guarantee. Actual regulator tolerances may provide margin; using the 3.3 V domain for a recovery strap removes this cross-rail margin dependency and should be considered alongside the power-sequencer revision.

Sources: [DS pin supplies and logic limits](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=89); [ROM boot, flash and diagnostics](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf#page=8); [Boot and debug guidance](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=24).

## MCU supplies and operating envelope

| Domain | Current rail | Required operating range/qualification |
|---|---|---|
| VDD; main GPIO bank |3V3 |3.0–3.6 V in 3.3 V mode. |
| VDDA18AON |1V8 |1.71–1.935 V; main supply, separate sequencing role from auxiliary rails. |
| VDDIO2/3 |3V3 |2.7–3.6 V; VDDIO3 drives boot NOR. |
| VDDIO4/5 |1V8 |1.71–1.935 V; camera and accelerometer domains, plus RTCINT conflict. |
| VDDSMPS, VDDA18PMU |1V8 |1.62–1.89 V, auxiliary; the 1.89 V ceiling is tighter than several other 1.8 V domains. |
| VDDA18USB |1V8 |1.746–1.935 V, auxiliary. |
| VDDA18PLL, VDDA18CSI |1V8 |1.62–1.98 V normally;1.746 V minimum when using the specified NPU overdrive condition. |
| VDDA18ADC / VREF+ |1V8 | ADC supply1.62–1.98 V; ADC/VREF use and errata need checking if subsequently enabled. |
| VDDCORE and VDDCSI | Internal SMPS | VOS low0.782–0.842 V; VOS high0.858–0.921 V. VDDCSI must follow the selected core voltage. |
| VDD33USB |3V3_USB from VBUS |3.0–3.6 V when USB is used; absent supply is allowed when USB is unused and isolated. |
| VBAT |3V3 | Tie to VDD is allowed; external RTC is separate. |
| V08CAP | Dedicated capacitor | Internal output, not an external power input; power review checks the specified bypass. |

Steady nominal rail values mostly fit the operating windows, but they do not prove transient compliance. DS Table 25 additionally specifies supply ramp rates; main VDD/VDDIO/AON/core entries are20–1500 µs/V and the listed analog/CSI/USB/VBAT entries10–1500 µs/V. Use scope measurements at the MCU balls or nearest local bypass for overshoot, undershoot, slew and sequencing. Existing power-good outputs are not connected to an MCU reset supervisor; power-review.md discusses source droop and cutoffs.

Battery-only operation with VDD33USB=0 is **not by itself a defect**. The reference manual explicitly supports logical/electrical isolation with USB33SV=0 when that supply is absent; USB33RDY/monitoring is available. Keep USB PHY functions inactive until their supplies and clocks are valid, enable USB33SV only after the required supply is present, and handle unplug while running. The simultaneous main/AUX sequencing fault remains MCU-002, including VBUS-driven startup. Root's USB review separately addresses connection detection and the unused second PHY.

Power-review.md owns local decoupling counts, effective ceramic capacitance, MCU SMPS L3 saturation/DCR and placement. Its PWR-006 should be closed together with MCU-002; nominal rail labels or regulator output capacitors are not substitutes for the specified local bypass placement. No duplicate decoupling finding is added here.

Sources: [Supply limits and ramp rates](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=138); [Independent supply isolation](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=393); [Sequencing and local SMPS network](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=8).

## Clock and early-firmware contract

PC9/C7 is a valid MCO2 output on the 1.8 V VDDIO4 bank. RCC can select HSE40MHz and divide by 2 to generate 20 MHz; the even divider also gives a nominal50% duty cycle. This is a viable clock path, not proof that 20 MHz matches the selected camera mode. Validate that mode and CSI link rate with the sensor review, then choose MCO drive speed and termination from the routed load. With VRSEL=0 at 1.8 V the MCU provides documented degraded-mode timings; do not burn HSLV OTP merely because a 1.8 V rail exists. Use either validated degraded-mode timing or the correct 1.8 V high-speed configuration, never 1.8 V mode on 3.3 V banks.

Before bringing up camera/NAND/USB, firmware must reconcile:

1. Main/AUX enable and shutdown discharge; PWR_ON automatic assertion and Standby deassertion; POPL minimum-off interval.
2. Actual I/O bank voltages, supply-valid bits, VRSEL/HSLV settings and ES0620 compensation workaround0x00000287. Compensation-register access couples IO2+IO4 and IO3+IO5 supply-valid bits.
3. Core VOS/readiness before CPU clock increases. ES0620 APB prescaling and clock-mux reset rules, including both clocks being present during a mux change.
4. Stable HSE timing before USB or sensor use; correct MCO2 and I2C4 configuration; one-lane CSI mode and DCMIPP/DMA buffer setup.
5. Small ROM-loaded image and a measured shutter-to-image budget. Complete-frame transfer time is additional to exposure and initialization, even with a global shutter. NAND commit may occur later per the product requirement.
6. NAND hardware RNB relocation, BCH/ECC and bad-block format from memory review; flash read-state recovery before warm reset.
7. Silicon marking/ROM version and the applicable reset/SMPS errata. Preserve BSECEN before Standby and avoid VSWRST with the internal-SMPS configuration on affected silicon.

These are specific integration contracts, not reasons to stop the hardware work. Schematic correction, regulator/sequencer selection, BGA escape planning, clock placement, supply zoning and test-point planning can proceed while firmware is imported.

Sources: [MCO2 clock selection and prescaler](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=435); [GPIO output timing by voltage mode](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=172); [Relevant reset, power and clock errata](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf#page=7).
