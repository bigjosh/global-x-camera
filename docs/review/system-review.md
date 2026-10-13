# USB, timing, mechanics and system review

> **Review scope:** the findings below concern the September recovered circuit. Later [prototype decisions](../../spec.md) settle USB-powered photo-drive mode with the shutter inactive, explicit erase, the exposure-start deadline and permission for a thicker functional prototype. Hardware USB detection/isolation, rail sequencing, firmware and mechanical qualification remain unimplemented; the later policies do not close those engineering findings.

Reviewed 2026-09-05 against the reconstructed schematic and the native Flux snapshot. No circuit or footprint changes were made. This is a pre-layout review: source placement, loaded footprints and an ERC pass do not establish electrical performance or manufacturability. The main review index integrates this report with the MCU, power and camera/storage reviews.

## USB

### USB-001 — Attach/detach detection and USB power policy are incomplete

**High / conditional.** J1 VBUS feeds U4 and D2, but no explicit VBUS divider/comparator or CC advertisement detector reaches the MCU. The STM32N6 OTGPHY1 has no connection to VBUS; its legacy VBUS/SESSION signals cannot be used as though it had one. The present VBUS-only 3V3_USB supply may permit a qualified supply-status proxy using USB33RDY, but that is not a demonstrated attach/detach implementation. In particular, unplugging USB while batteries keep the MCU powered must remove USB signaling and isolate the PHY correctly.

**Recommendation:** Add explicit, safely scaled VBUS detection, or demonstrate the supply-status approach over threshold, timing, power-order and firmware failure cases. An ADC divider must suit a 1.8 V input and remain safe with its receiving supply off. Coordinate with MCU-002 supply sequencing. USB33VMEN/USB33RDY monitoring supports EXTI edge interrupts, so a validated supply proxy is a real option rather than an assumed unavailable capability. [RM0486 Rev4, §72.2.6 p3751, §72.4.2/Figure978 p3756, supply monitoring pp365,396](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=3756). ST explicitly requires VBUS sensing for self-powered operation; its GPIO detector examples must be adapted to the N6 input voltage and off-state limits. [AN4879 Rev12, §2.6 pp11–12](https://www.st.com/resource/en/application_note/an4879-introduction-to-usb-hardware-and-pcb-guidelines-using-stm32-mcus-stmicroelectronics.pdf#page=11).

R10/R11 are correctly separate 5.1 kΩ sink resistors. They advertise a sink; they do not entitle the board to draw 1.5 A or 3 A. Establish a startup, configured and suspend load budget. Remain within default USB power rules unless the advertised current is detected and used correctly. If download mode needs more power, use a suitable CC detector/controller and a source-selection circuit. A selected USB-C source can advertise higher current without USB PD, but the sink has to determine that advertisement. [USB Type-C specification §2.3.4](https://www.usb.org/sites/default/files/USB%20Type-C%20Spec%20R2.0%20-%20August%202019.pdf).

USB descriptors and reported bus/self-powered state must follow the actual source and load. USB-IF's suspend-current update specifies 2.5 mA. Qualify both full-speed fallback and high-speed operation. The separate PWR-003 finding explains why this design currently reconnects its batteries during a USB session. [USB-IF electrical compliance updates](https://compliance.usb.org/index.asp?UpdateFile=Electrical).

### USB-002 — Directly connected capacitance and startup load need inrush control

**High / measurement.** C13+C43 contribute 5.7 µF directly on VBUS. D2 also exposes approximately C1+C2=10.1 µF at SYS_IN to plug-in charging, giving roughly 15.8 µF nominal before downstream converter startup. This is more than the usual simple 10 µF input-load model. Diode drop, MLCC bias, cable resistance and soft-start affect the actual waveform, so this calculation alone is not a compliance failure measurement. U2 soft-start does not limit the initial charging of its input capacitors through D2.

**Recommendation:** Provide controlled USB input charging/current limiting and an appropriate initial operating mode. Record at least the first 100 ms at sufficient sample rate and evaluate the inrush regions using the USB-IF method. Test with empty input capacitors, weak ports, both plug orientations and battery presence/absence. Include hot-plug overshoot at U4, whose maximum operating input is 5.5 V. [USB-IF inrush test update](https://compliance.usb.org/index.asp?UpdateFile=Electrical), [TLV700 electrical limits](https://www.ti.com/lit/ds/symlink/tlv700.pdf#page=5).

### USB-003 — Protection selection needs exact-vendor qualification and short return paths

**Medium / measurement.** D1 is UMW USBLC6-2SC6, not the ST part with the same base name. Its connections are correct: pins1/6 DP,3/4 DM,2 ground,5 VBUS. The archived UMW sheet lists up to 1 pF I/O-to-ground capacitance and 10 V/15 V clamping at its stated 1 A/6 A tests. Those numbers alone do not prove protection of the MCU under an assembled-product ESD event.

**Recommendation:** Route connector → protection → PHY without protection stubs; give the clamp and shield a short, low-inductance ground return. Select an exact traceable device with adequate characterization, then validate USB signal quality and the intended ESD test level. Consider VBUS transient/overvoltage protection as part of the input switch selection. CC pins presently terminate only through Rd, so an MCU CC-pin overvoltage fault is not claimed here. SBU pins being unused and shield tabs being grounded are reasonable for this USB2 sink. [Archived exact-vendor UMW datasheet](../../datasheets/discretes/UMW_USBLC6-2SC6_datasheet.pdf), [GCT connector drawing](../../datasheets/connectors/USB4105_drawing.pdf).

## RTC and orientation sensor

### RTC-001 — Backup mode must be provisioned persistently; default is disabled

**High / conditional.** U8 has a suitable single-cell backup connection and local bypass, but the RV-3028 is delivered with backup switching disabled. The specification's intended LSM setting is sensible when the 3.3 V main rail and fresh backup cell are close in voltage; it must actually be programmed into EEPROM and verified. A RAM-only setting can be replaced by an EEPROM refresh. In backup-only insertion standby, the clock is not established merely by connecting the cell before the first valid main-power initialization.

**Recommendation:** Define a factory provisioning operation on stable power: set the correct time, persist BSM=11, keep FEDE=1, verify the EEPROM and retention after main power removal, and record a validity flag. Test primary-cell replacement and cold/weak-cell switchover. LSM requires the backup input to exceed its approximately 2 V threshold, so the lowest series cell and sag matter separately from total pack voltage. Changing from disabled to LSM can take 15.625 ms; do not repeat that initialization on every capture. The approximately 66 ms POR refresh applies after true RTC power loss, not each ordinary main-rail cycle with valid backup. [RV-3028 application manual, pp39,43–48,54–57,87](../../datasheets/sensors_timing/RV-3028-C8_application_manual.pdf).

### RTC-002 — The primary backup cell must never have trickle charging enabled

**High / conditional.** U8 VBACKUP is directly connected to a non-rechargeable CR2032 tap. EEPROM register37h contains the charger-enable bit alongside backup-mode configuration. TCE defaults off, so an existing enabled charger is not alleged; a careless whole-register write could enable a real charging path from VDD.

**Recommendation:** Keep TCE=0 explicitly, preserve it during all configuration updates, and read back the persistent setting in production. Preserve the factory calibration bit7 in register37h and disable unused CLKOUT in register35h. Include this in the hardware/firmware contract. The manufacturer primary-battery application example uses charging disabled. [RV-3028 application manual, pp39,48,104](../../datasheets/sensors_timing/RV-3028-C8_application_manual.pdf).

### RTC-003 — Resolve the optional pull-down and interrupt voltage before release

**Low / confirmed, with the high-severity voltage issue tracked as MCU-004.** R26=1 MΩ is fitted on RTC SDA although source prose calls it optional/DNP. It draws about 3.3 µA while the main-powered bus is high; it is not a ten-year backup drain because the pull-up rail is off and the RTC bus is high impedance during backup. Choose fitted/DNP intentionally. R25=10 kΩ correctly defines EVI low; CLKOUT is explicitly unused. R28/R29=4.7 kΩ are plausible local bus pull-ups, subject to measured rise time. U8's interrupt is open drain, so changing R24's pull-up to the receiving 1.8 V domain is preferable to adding a translator. [RV-3028 manual pp45,94–97](../../datasheets/sensors_timing/RV-3028-C8_application_manual.pdf); physical nets in [schematic-connectivity.json](../../hardware/reconstruction/schematic-connectivity.json).

### ACC-001 — Accelerometer cold startup consumes up to 20 ms before sampling

**Medium / conditional.** U12 powers U11 from a GPIO-enabled switched rail. LIS2DW12 needs a 20 ms cold boot to load trims, followed by mode-dependent sampling/filter startup. Its much shorter single-conversion figures are not cold-power-on timing. Sequentially initializing the accelerometer and then the camera would consume avoidable latency.

**Recommendation:** Enable the accelerometer early and overlap its boot with other startup work; choose an ODR/filter mode that delivers a valid orientation sample before the image needs it. Timestamp the sample and mark invalid/transient orientation instead of silently using stale data. Provide at least 10 ms below 100 mV when a true sensor power cycle is required. Consider connecting the sensor to the main switched 1.8 V supply and using its power-down mode: the whole main supply already turns off between photographs. This removes U12/control parts but sacrifices independent isolation during long USB sessions. A gravity sensor resolves orientation relative to gravity, not absolute yaw, and motion during the shutter press can disturb that estimate. [AN5038 Rev6, pp5,10,34](https://www.st.com/resource/en/application_note/an5038-lis2dw12-alwayson-3d-accelerometer-stmicroelectronics.pdf#page=5), [LIS2DW12 datasheet](../../datasheets/sensors_timing/LIS2DW12_datasheet.pdf).

### ACC-002 — Keep MCU bus pins passive while the sensor rail is off

**Medium / conditional.** U11 VDD/VDDIO/CS share ACCEL_1V8_SW; SA0 is grounded, selecting I2C address0x18. R30/R31=10 kΩ pull up to the switched rail, and interrupt routing uses the appropriate 1.8 V bank. These connections are consistent. U12 QOD tied to VOUT and CT left open are allowed; QOD helps discharge the sensor rail.

**Recommendation:** Disable MCU internal pull-ups and avoid driving SDA/SCL/INT high into the unpowered sensor; configure open-drain/high-impedance states before removing power. At 100 kHz, 10 kΩ pull-ups allow about 118 pF for a 1 µs RC rise limit; a short local bus is plausible, but faster operation needs its own timing check. Verify that external leakage does not defeat QOD or the required power-off interval. [LIS2DW12 electrical/I2C limits](../../datasheets/sensors_timing/LIS2DW12_datasheet.pdf), [TPS22918 QOD and CT behavior](https://www.ti.com/lit/ds/symlink/tps22918.pdf).

## Placement, routing, mechanical and production readiness

### PCB-001 — The four-layer target needs a real stackup and an escape trial

**High / conditional.** The provisional dielectric values 0.18+1.17+0.18 mm and four 35 µm copper layers sum to 1.67 mm before other finish allowances, rather than the stated 1.6 mm. A nominal Dk and trace width do not specify controlled impedance. The 0.8 mm BGA pitch is compatible with investigating ordinary through-via escape; it does not by itself prove the complete pinout can escape on this board.

For the inherited U1 pad diameter0.394 mm and proposed 0.50 mm via land, a via centered between four balls has nominal copper gap `0.8/sqrt(2) - (0.394+0.50)/2 = 0.1187 mm`. That is only 18.7 µm above the proposed 0.10 mm clearance. A 0.10 mm trace between two 0.50 mm vias on 0.8 mm pitch leaves exactly 0.10 mm on each side. These are ideal geometry calculations, not toleranced manufacturing acceptance. Hole registration, finished hole, annular ring, mask webs and the actual fanout must be checked with the fabricator.

**Recommendation:** Retain four layers as a working cost target. Select a representative fabricator stackup and complete the MCU power/ground, boot bus, NAND and CSI escape before committing placement. If that consumes all routing access or forces poor return paths, compare a conventional six-layer option before adding HDI complexity. Record actual laminate thicknesses, copper weight, mask, impedance tolerance, finished drill and annular-ring rules. [Recovered board rules](../../imports/flux/2026-09-05/recovered-context.md), [U1 package/PCB recommendations](../../datasheets/processor/STM32N657X0_DS14791_datasheet.pdf).

### PCB-002 — High-speed and power routing rules are not yet implemented or verified

**High / conditional.** USB and CSI need their intended 90 Ω and 100 Ω differential impedances using the selected stack. FMC and XSPI single-ended edges, camera MCLK, oscillator loops and the internal/external switchers also matter. The Flux failure is not evidence that a general autorouter can solve the power loops, return paths and component dependencies automatically.

**Recommendation:** Place camera connector and MCU CSI side first, with grounded reference continuity; then place each SMPS's input loop, inductor, output bank and Kelvin feedback before ordinary signal routing. Keep L2 continuous under L1 high-speed signals. On other signal layers, explicitly identify the adjacent return plane and avoid crossing power splits. Add nearby ground stitching at layer transitions. Keep CSI pair polarity and lane mapping intact; set pair skew and clock/data constraints from the selected operating mode, including package and flex contribution. Avoid unnecessary vias and long test stubs. Do not add arbitrary series resistors or discrete termination to CSI; its receiver termination is part of the PHY. Route NAND/XSPI with deliberately chosen drive strength and setup/hold margins. [AN5967](../../datasheets/processor/STM32N6_AN5967_hardware_design.pdf), [AN5050](../../datasheets/processor/STM32_AN5050_XSPI_memory_interface.pdf), [module integration manual](../../datasheets/camera/VD55G0_UM2829_integration_registers.pdf).

### PCB-003 — The five-millimetre envelope and camera alignment are not closed

**High / conditional.** A 3.2 mm CR2032 above a 1.6 mm PCB already consumes 4.8 mm before contacts, insulation, covers or parts on the opposite face. Four 20 mm cells occupy approximately 1,257 mm² in circular area, around 27% of the 85.6×53.98 mm board; a simple two-by-two bounding rectangle occupies 1,600 mm². The native camera model reference was for a related module, so it is not evidence of the exact lens height or image orientation.

**Recommendation:** Close a sectioned mechanical model with the exact camera STEP, battery contacts, USB overhang, shutter actuator, screw bosses and covers before placing the dense electronics. Compare recessed contacts/cutouts against a modest increase in thickness. Verify flex bend radius, connector mating height, optical aperture, lens protrusion and assembly access. Keep battery cans/contacts insulated by durable mechanical features, and support the thin board to control flex at the BGA and camera connector. The battery and camera envelope can dominate layout more than the nominal PCB outline. [CR2032 reference dimensions](https://data.energizer.com/pdfs/cr2032_eu.pdf), [camera document/STEP record](../../datasheets/camera/README.md), [project requirements](../../spec.md).

### PCB-004 — Library load validation is not footprint manufacturing validation

**High / confirmed gap.** All147 host footprints load and cover all703 expected physical host pins. That checks identity/connectivity, not pad geometry, solder mask, paste, courtyard, height or assembly orientation. The camera review identifies a specific J3 geometry problem. Generic L1–L3 and high-value MLCC packages cannot be released until exact MPNs are selected.

**Recommendation:** Rebuild/correct J3 from the manufacturer drawing, select the power passives, and perform a drawing-to-footprint review of every distinct production land pattern. Include exposed pads, paste segmentation, mask web capability, pin1 marks and rotations in assembly outputs. Validate the selected 0.2 mm finished through-hole process and assembly stencil with the vendors. First-article inspection should include BGA X-ray and microscope inspection of J3/USB solder joints. A separate [spot-check report](footprint-spot-check.md) records the critical dimensions actually checked; it is not an all-footprint release certificate. [Existing validation scope](../../hardware/reconstruction/footprint-load-validation.md).

### PCB-005 — Debug keepout and assembly clearances need enforced rules

**Medium / confirmed.** The Tag-Connect no-track/via area is drawn on Dwgs.User but has no KiCad rule-area enforcement. The switch has no courtyard. These do not alter the netlist, but a routed board can pass ordinary clearance rules while obstructing the debug probe or component assembly. U1's0.394 mm lands/paste differ slightly from the recommended0.400 mm, and the recommended0.470 mm NSMD mask opening is not explicitly encoded.

**Recommendation:** Encode the required debug exclusion area as enforceable board rules, add verified courtyards, and explicitly set the BGA copper/mask/paste geometry accepted by the assembler. Preserve the manufacturer-matched pitch, pad numbering and connector holes. The6 µm BGA land difference is a normalization/qualification item, not evidence that the current BGA cannot solder. [Critical footprint measurements and drawings](footprint-spot-check.md).

### SYS-001 — Add observability and a production recovery path before layout

**Medium / confirmed gap.** TP1–TP13 expose battery, ground, main/core/camera supplies, BOOT0, NRST, RTC bus and MCLK. They do not explicitly expose PWR_ON, both PG signals, USB input current or sensor frame timing. Both PG nets presently end at a regulator and pull-up. Many startup faults can otherwise look like an identical dead board.

**Recommendation:** Add compact accessible ground-adjacent pads for PWR_ON, power-good/sequencer states, camera shutdown and a firmware timing marker. Provide a removable current-measurement link or fixture contact for the main pack; avoid CSI branch stubs. Confirm the selected Tag-Connect cable/adaptor's pinout, mechanical access, VTref and SWO behavior, and retain recoverable boot/reset access. SW2/SW3 are inferred optional DNP additions, so their footprint and assembly variant need explicit review before fitting. Include firmware provisioning, RTC setup, device identity, known-image capture, bad-block initialization and USB download in the factory test. [Current connectivity](../../hardware/reconstruction/schematic-connectivity.json), [reconstruction decisions](../../hardware/reconstruction/reconstruction-decisions.json).

### SYS-002 — Narrow the first prototype's performance and operating contract

**Medium / conditional.** STM32N657 provides useful native CSI and enough nominal SRAM for this image size, so replacing it is not automatically an improvement. Its cold boot, multiple power domains and large BGA add complexity that must earn their energy and latency cost. Raw NAND offers substantial capacity but adds controller/ECC and power-fail firmware work. Unspecified temperature range, cell end-of-life condition and interpretation of “capture within50 ms” prevent a single meaningful pass/fail result.

**Recommendation:** Keep the current architecture for the first measured feasibility experiment after correcting the explicit faults. Define the deadline as either exposure completion or full frame in RAM, bound exposure time, firmware load size, sensor revision and CPU operating point, and measure acquisition and commit energy separately. Run capture first with USB/NAND/background tasks deferred. Keep at least one full image plus DMA/cache/stack/firmware margin in a linker-checked SRAM plan; two unpacked 16-bit images already need about1.56 MB. Do not promise ten-year shelf life from IC typical currents or fifty-millisecond capture from isolated peripheral timings. If the corrected prototype misses the energy budget, revisit the battery and always-on/cold-start strategy before spending time on a dense final PCB. [MCU timing/operating-point findings](mcu-review.md), [camera/storage analysis](camera-memory-review.md), [power bounds](power-review.md).

## Connections found consistent in this review

USB receptacle D+/D− duplication, separate Rd resistors, D2 orientation, D1 functional pin assignment, unused SBU and grounded shields are consistent at netlist level. RTC VDD/VBACKUP bypass, EVI pull-down and backup I2C isolation are appropriate, subject to configuration and the separate interrupt voltage correction. LIS2DW12 rail ties, I2C mode/address and switched pull-ups are consistent.

LED1 physical pin1 is cathode and pin2 anode; its existing polarity is correct. R12=1.5 kΩ gives approximately0.93 mA using the LED's1.9 V typical forward voltage and neglecting GPIO low voltage, consistent with its1 mA-class indication. The older EDIF alias-based LED reversal suspicion was disproved and is not a finding. The exact LED is a top-view package: any reverse-facing indicator arrangement needs a real aperture/mounting drawing, rather than assuming that the suffix makes it a reverse-mount component. Evaluate visibility through the final cover and avoid illuminating the sensor cavity during exposure. [ROHM LED datasheet pp1–3](../../datasheets/controls/SML-P11MTT86R_datasheet.pdf).

These checks do not replace routing and assembled-product validation.
