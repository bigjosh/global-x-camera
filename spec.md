# Global X Camera Design Specification

**Project:** Global X Camera  
**Project URL:** https://www.flux.ai/bigjosh/global-x-camera  
**Updated:** 2026-10-14; recovered-design descriptions originated 2026-09-05.
**Design state:** Prototype selections below are locked. The recovered KiCad schematic still contains the earlier VD55G0 camera and TPS62132/AO3401A power circuit, including known review findings; it has not yet been revised or qualified for this prototype. D-35 selects a self-assembled Nucleo-based first prototype; a custom camera PCB and its manufacturer remain later work.

Current decisions and their remaining implementation boundaries are indexed in the [project decision register](docs/decisions/2026-10-13-project-baseline.md). This specification defines the current requirements; explicitly historical circuit descriptions preserve the unchanged CAD evidence.

**Prototype-work status, October 15:** board modifications and debugger-isolation rework are paused until the board is in hand. Gain and exposure range/curve are selected under D-38/D-39; D-40 selects losslessly compressed 16-bit grayscale PNG export on USB power, while hardware tuning remains pending; the existing requirements remain in force.

**Power review findings, October 14:** [rail requirements, phase timing and conversion proposals](docs/power/2026-10-14-power-tree-review.md) now precede wiring. The selected camera requires 2.8 V / 1.8 V / 1.15 V. A 5.0 V LTC3621 output is recommended for the Nucleo bench, with existing downstream regulators; custom-board voltage/topology remains open. These are engineering findings/proposals, not additional locked choices or applied CAD changes.

**Direct 3.3 V follow-up:** evaluate the [Nucleo modification](docs/power/2026-10-14-power-tree-review.md#direct-33-v-nucleo-operation--feasibility-study) before fixing the LTC3621 output. Separate main and switched auxiliary 3.3 V feeds appear feasible; simple header injection or tying these domains together is insufficient. This is a feasibility study, not an approved voltage or assembly instruction.

**Power-cost follow-up:** the [comparative energy model](docs/power/power-cost-comparison.md) suggests removing debugger/power-indicator overhead before undertaking direct 3.3 V rework. After those removals in both cases, the model predicts about 7% lower cycle energy from 3.3 V; a custom board offers further savings through lower-voltage conversion and removal/gating of unused loads. All values are estimates and no output voltage is newly selected.

## Locked prototype decisions — October 12–15, 2026

| Item | User decision |
| --- | --- |
| Processor direction | STM32N6 remains active; Himax is abandoned. |
| Prototype build route | **Approved October 14 (D-35): the user will assemble the first prototype around NUCLEO-N657X0-Q.** Defer the custom-PCB manufacturer/assembler decision; no JLCPCB or PCBWay direction is adopted. |
| Firmware starting point | **Approved October 14 (D-37): C with STM32CubeN6/HAL for bring-up, with readiness to use streamlined bare-metal startup/runtime and LL/direct-register code to improve power or timing.** HAL does not require an RTOS; runtime and USB middleware remain open. Measure gains while preserving accepted behavior. |
| Camera module | **ST CAM-6G3-073CLR**, using **VD56G3**, with **73° diagonal field of view**. This replaces CAM-5G0-079CLR/VD55G0 as the prototype selection. |
| Exposure-time control | **Approved October 14 (D-36): potentiometer into an MCU ADC input, sampled and applied before capture.** D-38/D-39 set fixed 1×/1× gain and an exponential fastest-supported-to-1 s exposure curve, to be tuned on hardware. Exact part, ADC wiring and numeric sensor timing limits are TBD. Startup, settling, conversion and programming must fit the ≤50 ms exposure-start budget; the existing OFF-current target still applies. |
| Photo capacity | **At least 200 full-native-resolution, uncompressed packed RAW10 photos between downloads** from CAM-6G3-073CLR / VD56G3. This is a capacity requirement; the exact NAND part and implemented storage format remain to be qualified. |
| Photo retention | **Approved October 14: ten years at room temperature, fully unpowered, with no refresh needed.** Approximately 25°C is the reference. Include successfully committed images and metadata needed to recover them. No periodic wake, battery, USB connection or maintenance write may be required. Qualify retention through the accepted 1,000 complete reuse cycles; see §6.7. |
| Storage reuse lifetime | **Approved October 14: 1,000 complete fill/download/explicit-erase cycles**, representing at least 200,000 photo saves at 200 photos per fill. The ten-year retention requirement still applies to photos saved after rated usage. Account for actual physical block and metadata wear; hardware compliance remains unqualified. |
| Full image readback | **Approved October 13:** full payload readback plus checksum comparison is configurable, enabled by default during bring-up/initial testing, and may be disabled later. Required save checks and final commit-record readback verification remain mandatory; see §6.1. Firmware implementation remains pending. |
| Capture indication | **D-41, approved October 15:** flashing yellow from power-up through capture and saving; steady green for 0.25 s only after required checks and verified durable commit, then shutdown. Existing red codes override normal indication on capture faults. Yellow cadence and indicator hardware remain to qualify. |
| Storage full | **Approved October 13:** preserve existing committed photos, reject new captures when no usable slot remains, and indicate storage full with the status LED. Reclaim saved-photo space through an explicit USB erase action after download; connection or download alone must not erase photos. Firmware implementation remains pending. |
| Presses while busy | **Approved October 13:** ignore additional shutter presses during capture/save, finish the current operation unless a fault requires abort, and do not queue another exposure. A new capture requires a fresh press after ready and an actual power cycle of the main capture electronics after shutdown. |
| USB mode | **Updated October 14: USB-powered PTP camera interface with explicit per-photo deletion.** This replaces drive/filesystem emulation. The shutter remains inactive. Connection or download alone never deletes photos. D-40 selects losslessly compressed 16-bit grayscale PNG, generated on USB power. Encoding, safe deletion/reclamation, host interoperability and USB power isolation remain implementation work. |
| Read integrity and recovery | **Approved October 14:** each USB host image-data request freshly reads the entire original NAND image into RAM, checks ECC/CRC-32C, then exports that buffer with current-read warnings via filename/EXIF. No background payload scans, stale-buffer reuse, relocation or refresh. Predictive media errors permanently retire the slot from future writes without deleting its image. Only explicit host deletion removes photos; see §6.8. |
| Post-save shutdown | **Clarified October 13:** prepare peripherals and the required shutdown sequence, then enter genuine STM32N6 Standby so an ordinary HOLD GPIO becomes high impedance and releases the diode hold path. A held shutter keeps the buck enabled until release. External rail sequencing and any RUN-delay capacitor remain unimplemented. |
| Shutdown state | **Approved October 13:** the lowest attainable power state; the main capture electronics must undergo an actual power cycle before another image. RTC backup may remain powered. A held button waits for release; no automatic wake or retake. A fresh press alone does not substitute for the power cycle. |
| F-01: low battery at any phase | **Approved October 13:** one red LED flash, then abort the cycle to the shutdown state. Indication requires sufficient remaining power; successful commit is not a prerequisite to this abnormal abort. Preserve existing committed photos; detection, thresholds and interrupted-write recovery remain implementation work. |
| F-02: abrupt power loss | **Approved October 13:** previously saved photos must survive; the current uncommitted photo may be incomplete. Keep bytes already written to NAND. Mark blocks **USED** at save start and **DONE** at successful completion; USED without DONE means possibly corrupt/incomplete. Recover valid committed photos without silently erasing/discarding incomplete bytes or automatically taking a replacement exposure. Marker layout and recovery remain unimplemented and unqualified. |
| Failure response map | **Approved October 13:** red flashes: low battery **1**, camera initialization **2**, frame capture **3**, storage unresponsive **4**, new-photo write/readback/commit **5**, allocation/index damage **6**; then shutdown as defined above. Missing time/orientation uses explicit **BAD** metadata while the image is saved. Existing-photo read and explicit-erase errors are reported through USB. See §6.6. |
| Photographic flash | **Approved October 14 (D-34): ambient-light prototype; flash illumination deferred to FD-06.** Required status/error LED indications remain part of the prototype. |
| Battery and main converter | **Four CR2032 cells in series through LTC3621.** These are the prototype power choices. |
| Room-temperature OFF current | **0.1 µA (100 nA) target for the main power path**, including regulator, input-capacitor, switch, PCB and other pack-connected leakage. The retained RTC cell-tap drain is additional and excluded from this target; it must be measured and budgeted separately. Compliance is not yet demonstrated. |
| Cold-start shutter timing | **≤50 ms from shutter-button press to start of exposure, starting fully powered off.** Exposure duration, frame readout, save and shutdown may follow and are measured separately. This is the acceptance requirement, not demonstrated hardware performance. |
| Thickness | **≤5 mm is the finished-product design target.** The functional prototype may be thicker; this target is not a hard prototype acceptance gate. Final mechanical stackup and fit remain to be verified. |

These selections do not establish a completed circuit or measured performance. The [power implementation study](power.md) still needs rail sequencing, USB source control, exact component qualification and integration. Its earlier regulator suffix, 3.3 V/250 mA operating point and passive values are not additional locked decisions. Recalculate frame size, RAM, storage capacity, timing and energy for the selected VD56G3 module; the existing 644 × 604 VD55G0 calculations do not qualify it.

**Future directions remain open:** VD5943, potentially with custom optics; and a mechanical frame-advance action winding/driving a spring. Neither is part of the locked prototype. The [earlier shutter-motion study](docs/power/shutter-energy-harvesting.md) provides energy-envelope context, not a selected mechanism or generation topology.

**FD-03 — Series-capacitor start pulse, deferred October 13:** investigate a capacitor in the shutter-start path so the camera can eventually shut down even while the button remains held. Qualify capacitor reset/rearming, pulse duration through reliable boot-to-HOLD takeover, leakage, transients, bounce and rapid repeat presses. An SPST switch with a reset bleed versus an SPDT reset arrangement remains unselected. This differs from the optional RUN-to-ground shutdown-delay capacitor. The existing divider/HOLD prototype baseline remains unchanged; no component values, hardware or firmware changes are selected by this future direction.

**FD-06 — Photographic flash, deferred October 14:** retain illumination as a future direction after evaluating prototype low-light images. Establish working distance, brightness/coverage, pulse and recharge timing, energy source, physical fit and capture timing before choosing components. No flash hardware or alternate battery system is selected for this prototype.

## 1. WHAT: Product definition

Global X Camera is an ultra-thin, credit-card-size monochrome digital camera optimized for instantaneous single-frame capture and extremely low battery drain between captures. A shutter press physically starts the main power system. The STM32N657 initializes the camera, captures one full-resolution, full-bit-depth global-shutter image, timestamps and orientation-tags it, stores it in raw NAND, and then deliberately removes main-system power. USB-C provides independent processor power for image download without relying on the coin-cell stack.

The PCB is intended to be both the electronic assembly and a structural rear surface of a milled enclosure. The target outline remains the ISO ID-1 credit-card size, 85.60 mm x 53.98 mm; the recovered board assumption is rigid, 1.6 mm and four-layer. **The finished-product thickness design target is ≤5 mm, while the functional prototype may be thicker.** The camera, lens, batteries, contacts, PCB and enclosure stackup still require a complete fit check.

### 1.1 Required user-visible behavior

1. With no USB cable attached, the shutter released and shutdown complete, the main electronic system is physically power-gated. A held shutter can keep the buck enabled in the lowest attainable state until release.
2. With USB disconnected, pressing the right-angle shutter switch starts the battery power latch.
3. The processor asserts its power-hold signal before the user releases the switch.
4. The processor boots from external Quad-SPI NOR, establishes clocks and rails, and checks for a usable storage slot. If none remains, it preserves existing committed photos, rejects the capture and indicates storage full with the status LED. Otherwise, it initializes the camera, reads orientation and time, and captures one image.
5. The image is written to raw SLC NAND with firmware-managed bad blocks/pages.
6. Flash yellow from power-up throughout capture/save; after required checks and verified durable commit, show steady green for 0.25 s before shutdown. Red-coded faults override normal indication (D-41). Ignore additional shutter presses while capture/save is busy, finish the current operation unless a fault requires abort, and queue no exposure. Another image requires a power cycle of the main capture electronics after shutdown and a fresh press after ready.
7. After all required save checks and verification of the durable NAND commit record, firmware prepares peripherals and the required shutdown sequence, then enters Standby. The ordinary HOLD GPIO becomes high impedance, releasing the diode hold path. With the shutter released, the main supply turns off after any qualified shutdown delay; a held shutter keeps the buck enabled while the MCU remains in Standby until release. Full image readback follows the configurable policy in §6.1.
8. When USB-C is attached, USB powers the camera's download/explicit-erase mode independently of the batteries. Firmware presents photos through PTP and accepts explicit per-photo delete requests; the shutter has no operation. Attaching USB or downloading images does not itself delete them. Persist deletion safely and reclaim only the corresponding storage without harming other photos.
9. At any phase of a cycle, detected low battery causes one red LED flash while sufficient power remains, followed by abort to the shutdown state. Abort is not proof of a successful save; retain an already valid, committed current image and never claim an incomplete or unverified image was saved. See §6.4 for the power-cycle and data-preservation requirements.

### 1.2 Performance priorities

The priorities, in descending order, are:

1. Minimize shutter-button-to-exposure-start latency. From fully powered off, exposure must start within **≤50 ms** of the shutter-button press.
2. Minimize total energy from shutter press through completed nonvolatile save and shutdown.
3. Minimize assembled thickness toward the finished-product ≤5 mm design target; allow a thicker functional prototype.
4. Minimize area, with credit-card size as the present outline.
5. Use well-documented components that are readily procurable from major distributors or PCBA catalogs.

Every prototype capture uses the selected CAM-6G3-073CLR module's full native resolution and full sensor bit depth. The former 644 x 604 requirement described the superseded VD55G0 module; dependent budgets must be updated for VD56G3. The **≤50 ms deadline ends at start of exposure**, measured from shutter-button press with the camera initially fully powered off. Exposure duration, frame readout, nonvolatile save and shutdown may occur afterward; measure each separately. Earlier references to a 50 ms "acquisition" or complete-frame budget do not define the current acceptance criterion.

**Capacity requirement, locked October 12, 2026:** retain **at least 200 full-native-resolution, uncompressed packed RAW10 photos between downloads** from CAM-6G3-073CLR / VD56G3. This replaces the earlier unspecified "hundreds" requirement. Capacity planning must include metadata, bad blocks and reserve space; the exact NAND part and implemented storage format are not frozen by this decision.

The selected sensor's packed RAW10 image payload is **1,916,420 bytes per frame**, before storage metadata and allocation overhead. A **4 Gbit / 512 MiB raw** device holds **280 payloads gross**; an illustrative allocation of **2 MiB per photo with 20% reserved capacity** yields **204 photo slots**. These calculations support capacity planning, not a qualified usable-capacity guarantee. Verify the actual format, metadata, ECC/bad-block handling and reserve policy against the 200-photo minimum. The [quad NAND comparison](docs/power/quad-nand-comparison.md) uses the superseded VD55G0 format; its older photo counts, including estimates near 800, remain historical and do not apply to VD56G3.

## 2. WHY: Architecture rationale

The following records the inherited architecture rationale. The camera and main-converter selections above supersede the earlier parts; other component descriptions remain the recovered baseline pending integration and qualification.

### 2.1 STM32N657 processor

The STM32N657X0H3Q was selected because it combines an 800 MHz Cortex-M55, approximately 4.2 MB SRAM, MIPI CSI-2 receiver, USB 2.0 High-Speed capability, FMC-style parallel NAND support, external XSPI boot support, image-processing accelerators, and enough memory/peripheral bandwidth to acquire a full frame without adding external working RAM. Consolidating these interfaces in one processor reduces component count, startup sequencing, board area, and cycle energy.

### 2.2 Global-shutter camera module

The prototype now selects **ST CAM-6G3-073CLR / VD56G3, 73° diagonal field of view**. The integrated module approach avoids the optical and sensor-assembly work of mounting a bare sensor. The recovered design instead represents CAM-5G0-079CLR / VD55G0 and uses a Hirose BM28B0.6-30DS/2-0.35V receptacle. Verify the selected module's exact electrical interface, operating mode, supplies and mechanics before revising the camera circuit; shared family naming does not establish a qualified substitution.

### 2.3 Raw SLC NAND image storage

In the recovered baseline, MX30LF2G18AC-TI 2 Gbit raw SLC NAND was chosen over managed flash because it offers low program energy, short page-program time, simple high-throughput parallel access, and deterministic firmware control. The firmware architecture is explicitly responsible for bad-block management, page allocation, metadata integrity, recovery after interrupted writes, and wear management. The prototype's exact NAND part remains to be qualified against the locked 200-photo requirement for VD56G3; the recovered 2 Gbit device is not established as meeting it. Once that minimum is met, additional capacity is secondary to write latency and energy; the largest suitable device within the selected performance class is preferred.

### 2.4 Separate boot NOR

The W25Q128JVPIQ 128 Mbit Quad-SPI NOR provides fast and deterministic boot storage. Firmware is intended to load into internal SRAM early so that the slower nonvolatile interfaces are not repeatedly accessed during the time-critical capture sequence. The design reserves a primary FSBL at address 0 and a redundant FSBL at 0x40000.

### 2.5 Four series CR2032 cells

**Four CR2032 primary cells in series through LTC3621 are locked for the prototype.** The earlier 8–13.2 V pack range remains a calculation assumption, not a qualified end-of-life limit. The higher voltage allows the main buck converter to draw less current from the high-impedance cells for a given system power level. The main converter's current passes through all four cells; the separate RTC tap adds drain to one cell. Exact cells, contacts, pulse capability, polarity keying and cutoff behavior still require engineering qualification.

### 2.6 Physical power gating

The prototype will use the selected LTC3621 with the startup, hold and shutdown implementation developed in [power.md](power.md). The user-confirmed room-temperature OFF target is **0.1 µA (100 nA) for the complete main power path**, superseding the earlier <1 µA wording. It includes regulator shutdown current plus input-capacitor, open-button, PCB, protection and other pack-connected leakage. Main loads are switched. The existing RTC backup bypasses the main regulator and is retained; its cell-tap drain is additional and excluded from the 100 nA target; it must be measured and budgeted separately. Compliance is not yet demonstrated. Screening regulators and rejecting high-leakage parts is a user-proposed candidate approach, subject to measured leakage, an agreed acceptance cutoff and acceptable yield; it does not by itself qualify assembled-camera OFF current.

**Recovered circuit, retained for reference:** two back-to-back AO3401A P-channel MOSFETs isolate the battery stack from the system input. The shutter switch mechanically pulls down the latch gate to start the system. A BSS138 controlled by the STM32 maintains the latch until the save operation is complete. Back-to-back MOSFETs block the body-diode reverse path when off, but do not establish USB priority while enabled; the known latch faults are recorded in the [power review](docs/review/power-review.md).

Literal zero leakage is physically impossible. AO3401A drain leakage is specified up to approximately 1 uA per device at 25 C and 5 uA at 55 C under the datasheet test voltage. The design goal should therefore be interpreted as physically power-gated with leakage limited by devices and PCB cleanliness, not mathematical zero current.

### 2.7 Ceramic reservoir instead of a supercapacitor

The recovered 3.3 V rail uses a bank of four 47 uF ceramic capacitors rather than a supercapacitor. This reduces leakage and startup charge time, both of which directly affect shelf life and shutter latency. The prototype reservoir remains to be sized for CAM-6G3-073CLR/LTC3621; the recovered bank is not a newly frozen value. Effective capacitance under DC bias must be checked against the selected production MLCCs and measured rail droop.

### 2.8 Independently powered RTC

In the recovered circuit, the RV-3028-C8 is continuously backed up from the positive terminal of the lowest CR2032 cell relative to system ground, bypassing the main regulator. Its normal VDD and I2C pull-ups are switched with the main 3.3 V rail. Firmware must configure the RTC's Level Switching Mode, BSM=11, so the digital bus is high impedance while only backup power is present. CLKOUT is intentionally unused to eliminate a backup-powered backfeed path. Use the C8's specified backup-mode current, not its lower VDD-only timekeeping figure, when budgeting this cell tap; see [power.md §4](power.md#4-off-current-budget). The user has retained this backup path and approved measuring and budgeting its additional drain separately from the 100 nA main-path target. This accounting decision makes no hardware change and establishes no measured shelf-life result.

### 2.9 Switched accelerometer

The LIS2DW12TR provides image orientation. It is powered from the 1.8 V rail through a TPS22918 load switch rather than directly from a GPIO. The load switch guarantees adequate voltage and current while allowing firmware to remove power after the reading. A 100 kOhm enable pulldown guarantees the sensor remains off during reset. Its dedicated I2C bus is limited to 100 kHz with 10 kOhm pull-ups to the switched sensor rail.

### 2.10 USB-C and signal integrity

USB-C is used as a USB 2.0 device connection. The PCB is designed for possible 480 Mbit/s High-Speed operation even though firmware may choose 12 Mbit/s Full-Speed. D+ and D- pass through a USBLC6-2SC6 low-capacitance ESD array. Each CC pin has an independent 5.1 kOhm Rd. Designing the physical channel for High-Speed preserves both firmware choices with no PCB change.

## 3. HOW: Recovered electrical implementation

**Historical implementation, not the newly selected prototype circuit.** The component identities, rail values, pin assignments and camera timing below describe the unchanged VD55G0/TPS62132 reconstruction. They preserve the source design and must be revised against the locked CAM-6G3-073CLR/LTC3621 choices and the [design-review findings](docs/DESIGN-REVIEW.md) before release.

## 3.1 Processing and clocks

U1 is STM32N657X0H3Q in a 14 mm x 14 mm, 0.8 mm-pitch VFBGA264 package. The main external reference is Y1, a 40 MHz CX3225SA40000D0PTWCC crystal with 8.2 pF load capacitors. The crystal feeds the STM32 HSE input. The sensor master clock is not driven directly by the crystal: firmware configures the STM32 clock tree and emits CAM_MCLK from an MCU peripheral-capable pin. This permits programmable frequency and clock gating. The selected pin's alternate-function mapping and the final CAM_MCLK frequency, nominally within the module's 6-27 MHz accepted range, must be confirmed in firmware configuration.

The STM32's internal SMPS uses L3, 1 uH, to produce the approximately 0.81 V VDDCORE rail. The design includes the recommended bulk and per-domain capacitors, V08CAP bypass, VREF filtering, VLXSMPS damping network, 200 Ohm CSI_REXT, and 200 Ohm USB TX tuning resistor.

The MCU supply domains are:

- Main VDD and relevant VDDIO banks: 3.3 V.
- VDDIO4/VDDIO5 and 1.8 V analog/CSI-related domains: 1.8 V.
- VDDCORE and VDDCSI: approximately 0.81 V.
- VDD33USB: isolated 3.3 V USB domain from VBUS.

## 3.2 Main input and latch

Battery input BAT_PLUS enters Q1 and Q3, two AO3401A P-MOSFETs wired as a common-source back-to-back pair. Their shared gate is normally returned high by R1, 1 MOhm. R2, 100 kOhm, limits gate pull-down current and constrains worst-case gate-source voltage. Pressing SW1 grounds SHUTTER_SENSE. D3 couples this event into the latch pull-down path while preventing the MCU hold transistor from masking switch release. Q2, BSS138, is driven by the net named PWR_HOLD, which is actually connected to the MCU's dedicated PWR_ON output, not an ordinary GPIO. R3, 1 MOhm, pulls Q2's gate low when that output is unpowered. The known battery-level PC13 exposure, PFET gate-margin and USB-startup faults remain recorded in the [power review](docs/review/power-review.md); this paragraph does not qualify the recovered latch.

USB VBUS feeds SYS_IN through D2, an SS34 Schottky diode. This prevents SYS_IN or the battery path from backfeeding VBUS. The diode is simple and robust but dissipates power and drops voltage; an ideal-diode replacement remains a possible optimization if USB efficiency or thermal measurements justify it.

## 3.3 Voltage rails

- **SYS_IN:** Selected battery or USB source. Battery range is approximately 8-13.2 V; USB source is nominally 5 V minus D2 drop.
- **3V3:** U2 TPS62132RGTR fixed 3.3 V synchronous buck, rated 3 A, with L1=2.2 uH, 10 uF input, 22 uF standard output, and four 47 uF reservoir MLCCs. This powers the processor's 3.3 V domains, NAND, boot flash, downstream regulators, and control circuitry.
- **1V8:** U7 TPS62825DMQR adjustable buck, configured with 200 kOhm/100 kOhm feedback for 1.8 V, L2=0.47 uH, 4.7 uF input, and two 10 uF output capacitors. It powers STM32 1.8 V domains, camera VDDIO, and the accelerometer switch input.
- **VCORE_0V81:** STM32 internal SMPS with L3=1 uH and approximately 88 uF core bulk capacitance plus local decoupling.
- **CAM_VANA_2V8:** U9 TLV70028DDCR, 2.8 V/200 mA LDO from 3.3 V. The MCU controls CAM_AVDD_EN so analog power can be sequenced after the lower rails.
- **CAM_VCORE_1V2:** U10 NCP115AMX120TCG, 1.2 V/300 mA LDO from 1.8 V. This supplies the camera module's nominal 1.15 V core input within the selected implementation tolerance.
- **3V3_USB:** U4 TLV70033DDCT, 3.3 V/200 mA LDO directly from USB VBUS for STM32 VDD33USB.
- **ACCEL_1V8_SW:** U12 TPS22918DBVT load-switched 1.8 V rail for U11.
- **BAT_CELL1_TAP:** Always-on single-cell backup source for the RTC VBACKUP pin.

## 3.4 Camera interface

CAM1 represents the external CAM-5G0-079CLR module; it is excluded from the host PCB and pick-and-place. J3 is the on-board Hirose BM28B0.6-30DS/2-0.35V receptacle. The active data channel is one CSI-2 lane plus differential clock:

- CAM_CSI_D0_P/N: camera data lane to STM32 CSI receiver.
- CAM_CSI_CLK_P/N: camera differential clock to STM32 CSI receiver.
- I2C4_SCL/SDA: 1.8 V sensor configuration bus with 4.7 kOhm pull-ups.
- CAM_MCLK: MCU-generated module input clock.
- CAM_XSHUTDOWN: defaults low through 100 kOhm and is released only after rails and clock are valid.
- CAM_VANA_2V8, 1V8, and CAM_VCORE_1V2 provide the three module rails.

Firmware should keep XSHUTDOWN low while rails start. VDDIO and core may come up first; CAM_AVDD_EN should be asserted after the 1.8 V and 1.2 V rails have been valid for at least approximately 1 ms. MCLK must be stable before releasing XSHUTDOWN. These inherited VD55G0 sequencing values must be revalidated for the selected module. The current prototype deadline is **≤50 ms from shutter-button press to start of exposure from fully powered off**; completing exposure or receiving the full frame is outside that deadline.

## 3.5 Raw NAND interface

U6 is MX30LF2G18AC-TI, powered at 3.3 V. It connects directly to 3.3 V-powered STM32 GPIO/FMC resources through an 8-bit bus:

- NAND_D0 through NAND_D7.
- CLE and ALE command/address latches.
- CE#, RE#, and WE# control.
- R/B# status with a 10 kOhm pull-up.
- CE# with a 10 kOhm reset-state pull-up.
- WP# with a 10 kOhm pulldown so program/erase is inhibited until firmware deliberately drives the MCU output high.
- PT with a 100 kOhm pulldown.

The NAND is 2 Gbit SLC, approximately 256 MiB raw before bad-block and metadata overhead. Firmware must never assume all blocks are usable. A robust format should protect storage-control metadata using implementation-appropriate redundancy, monotonic sequence numbers, CRCs, committed/uncommitted states, and recovery scanning after an interrupted save. This historical storage description does not require duplicating photo-object attributes; §6.10 defines the accepted object/control boundary.

## 3.6 Boot flash

U5 is W25Q128JVPIQ, a 3.3 V 128 Mbit Quad-SPI NOR in WSON-8. It connects to the STM32 XSPI boot interface using CLK, NCS, and IO0-IO3. NCS has a 10 kOhm pull-up so the device remains deselected during power ramp. The exposed center pad is not internally connected and may be grounded or left floating according to the footprint strategy; avoid untreated open vias beneath it.

## 3.7 RTC and timestamping

U8 RV-3028-C8 uses switched 3.3 V for VDD and BAT_CELL1_TAP for VBACKUP. PE5/PE6 provide I2C access through 4.7 kOhm pull-ups to switched 3.3 V. Its open-drain interrupt is pulled up to switched 3.3 V and connected to an MCU input. EVI has the datasheet-recommended pulldown. Optional 1 MOhm bus pulldown footprints may be left DNP unless bench testing shows a benefit. CLKOUT is intentionally disconnected.

Firmware requirements include configuring BSM=11, setting and validating the timestamp format, checking oscillator/status flags, and reading time early enough that the saved record can be associated unambiguously with the exposure.

## 3.8 Orientation sensor

U11 LIS2DW12TR is powered through U12. The MCU first enables ACCEL_PWR_EN, waits for the switched rail and sensor startup, reads acceleration over a dedicated 100 kHz software-I2C bus, determines orientation, and then removes power. INT1 is routed to the MCU for optional data-ready or wake diagnostics. The I2C assignment may move to any voltage-compatible GPIO pair if routing requires it.

## 3.9 USB and download mode

J1 USB4105-GF-A is a USB 2.0 Type-C receptacle. R10 and R11 are independent 5.1 kOhm CC pull-downs. D1 protects D+ and D-. USB_DP and USB_DM route to the STM32 USB PHY. U4 produces 3V3_USB from VBUS so the USB PHY can operate with the batteries absent or disconnected. D2 also feeds the main 3.3 V buck input for complete processor operation in download mode.

The USB channel is intended for 90 Ohm differential impedance. It should be routed on L1 directly over the L2 ground plane, short and tightly coupled, with minimal discontinuity through J1 and D1. Firmware may enumerate at High-Speed or Full-Speed without PCB changes.

## 3.10 User interface and debug

SW1 is an Omron B3U-3000P side-actuated SPST-NO shutter switch located at the top edge near the right side. It serves both as the physical latch start and an MCU-readable shutter signal. LED1 is a low-current SML-P11MTT86R yellow-green 0402 LED driven at approximately 1 mA through R12=1.5 kOhm. It is intended to face the rear through a PCB/enclosure optical opening. This is the recovered hardware, not a compliant three-color implementation of D-41; select distinct yellow, green and red indication hardware during the deferred board work.

J2 is a TC2030-IDC-NL six-pad Tag-Connect pattern carrying SWDIO, SWCLK, SWO, NRST, VTref, and GND. The final product has no populated debug connector. BOOT0, reset, rails, camera I2C, RTC I2C, camera clock, camera rails, and battery tap have compact test pads. Optional BOOT and RESET switch footprints are excluded from the production BOM.

## 4. PCB implementation

These are recovered, provisional board constraints. Recheck camera reserves, connector mapping and power placement for CAM-6G3-073CLR and LTC3621 before carrying them into the prototype layout.

### 4.1 Board geometry

- Outline: 85.60 mm x 53.98 mm.
- Corner radius: 3.18 mm.
- Recorded PCB finished thickness: 1.60 mm, provisional; distinct from total product thickness.
- Board-edge copper/component inset: 0.25 mm provisional.
- PCB serves as the visible rear structural surface.
- Bottom face is intended to have soldermask-covered ground copper, with a logo added later without affecting electrical design.

### 4.2 Four-layer stackup

- L1: Components and signals; USB and MIPI pairs.
- L2: Ground reference plane, kept as continuous as practical.
- L3: Power distribution and slower signals.
- L4: Near-solid ground plane on the visible rear face, covered by soldermask.

The provisional dielectric construction uses approximately 0.18 mm between L1-L2, 1.17 mm core between L2-L3, and 0.18 mm between L3-L4. These values and Dk=4.2 are placeholders. The selected fabricator must provide its actual 1.6 mm four-layer construction and impedance calculation.

### 4.3 Fabrication assumptions

The four-layer STM32 BGA escape is conditionally feasible with:

- 0.10 mm minimum trace and spacing.
- 0.50 mm via pad.
- 0.20 mm finished mechanical drill.
- 0.40 mm BGA pads at 0.80 mm pitch.
- Through-via dogbones for inner used signals.
- Direct L1 escape for perimeter MIPI and USB balls.

No microvias, blind vias, or via-in-pad are presently required. If the selected vendor cannot guarantee these rules, the design must change to an HDI process or more layers. Through vias will create visible drilled features on the rear unless tented or filled.

### 4.4 High-speed constraints

- USB_DP/USB_DM: 90 Ohm differential, +/-10 percent target.
- CAM_CSI_CLK_P/N: 100 Ohm differential, +/-10 percent target.
- CAM_CSI_D0_P/N: 100 Ohm differential, +/-10 percent target.
- Route all principal high-speed pairs on L1 over L2.
- Use local 0.10 mm neckdowns only where pad access requires them.
- Determine production width/gap with the fabricator field solver; current 0.15 mm preferred width is provisional.
- Avoid testpoint stubs on USB and MIPI.
- Preserve ground return continuity and add stitching near unavoidable transitions.

### 4.5 Placement constraints

- Keep critical STM32 decoupling at the assigned supply balls.
- Keep regulator input capacitor, switch node, inductor, and output capacitor loops compact.
- Keep NAND close enough for a short, orderly 8-bit bus with escape channels along both TSOP sides.
- Place boot flash close to the STM32 XSPI balls.
- Maintain top-side access to the Tag-Connect probe footprint.
- Align USB-C and the shutter actuator to enclosure edge openings.
- Keep the bottom predominantly free of components; LED1 is the deliberate exception.
- Preserve the camera connector and flex/module body reserve.

In the recovered VD55G0 design, two conservative 10 mm x 15 mm component-only keepouts extend from both sides of J3 because the available CAM-6G3-073CLR STEP did not establish CAM-5G0 electrical pin-1 orientation. That historical reserve spans approximately X=-21 to -11 mm and Y=-14 to +14 mm in the source board coordinates, with routing allowed through it. Revalidate the reserve and orientation for the now-selected CAM-6G3-073CLR module.

## 5. Mechanical design assumptions

The ≤5 mm finished-product target is not a hard gate for the functional prototype. Verify the final sectioned mechanical stackup and actual component fit before claiming the finished-product target is met.

The enclosure is expected to be milled and secured with four corner screws. The PCB forms the rear face. The lens protrudes through a front opening, and edge openings expose USB-C and the side-actuated shutter. Battery sockets/contacts may be custom enclosure features. A later revision may recess the camera module into a PCB cutout if thickness measurements justify it.

The recovered design used a CAM-6G3 reference STEP while electrically specifying CAM-5G0. CAM-6G3-073CLR is now the selected prototype module; confirm that the available model is the exact selected version and validate it against a physical module before releasing the lens aperture, orientation, flex sweep, image roll and enclosure. The earlier dimensional assumptions are not a completed fit check.

## 6. Firmware architecture requirements

The staged workflow remains the starting point, but the inherited rail actions and sensor initialization below must be reconciled with CAM-6G3-073CLR and the LTC3621 implementation. No existing firmware or timing model is thereby qualified for the new module. The sequence below describes successful capture/save; faults follow §§6.4–6.6 instead of requiring a successful-save sequence.

For battery-powered capture with USB disconnected, the firmware implementation should use a staged, latency-measured startup:

1. Establish PWR_HOLD immediately after reset.
2. Initialize clocks from HSE and configure the core/IO domains.
3. Validate boot cause and minimum required state, including availability of a usable storage slot. If full, reject the capture and indicate storage full under §6.2.
4. Start 1.8 V and camera core rails; hold camera in XSHUTDOWN.
5. Enable and read the accelerometer; then disable its rail. If orientation is unavailable, record an explicit BAD sentinel and continue saving the image.
6. Read RTC and status flags. If valid time is unavailable, record an explicit BAD sentinel and continue saving the image.
7. Configure CAM_MCLK and camera I2C. Initialize the exposure-control ADC/reference, allow the input to settle and sample the potentiometer; translate the sample to the intended exposure time (D-36). Exact scheduling can overlap independent initialization, but this must complete before exposure starts.
8. Enable camera analog rail, satisfy the selected module's delays, release XSHUTDOWN, and apply the potentiometer-selected exposure setting before beginning the saved exposure within ≤50 ms of shutter-button press from fully powered off. Then complete exposure and read out the full-resolution frame.
9. Mark the save's storage blocks USED at the beginning of saving, then record timestamp/orientation or their BAD sentinels, exposure/configuration actually used, sequence number, image payload, and generated checksum/integrity metadata to raw NAND.
10. Complete the required save checks, optional full payload readback, redundant allocation metadata update and successful-end DONE marking under §§6.1 and 6.5. Read back and verify the final durable commit record before treating the photo as successfully saved.
11. Keep flashing yellow until all required operations and checks, including verified durable commit, complete successfully. Then show steady green for 0.25 s, prepare peripherals and the required rail-shutdown sequence, and enter genuine Standby so the ordinary HOLD GPIO automatically becomes high impedance. Leave HOLD driven until Standby entry; Stop mode does not perform this release.

All phases should be instrumented during bring-up. Budget the **≤50 ms shutter-button-to-exposure-start interval** across power ramp, boot-ROM/FSBL, firmware load, clock configuration, camera rails, initialization, ADC/reference startup, input settling, potentiometer sampling and exposure programming, and any other prerequisite to starting exposure. Record the actual exposure-start event. Measure exposure duration, frame readout/transfer, nonvolatile save including NAND programming and metadata commit, and shutdown as separate later intervals. The deadline is a deterministic design/timing qualification requirement, not a selected runtime error code. No current measurements establish compliance with this cold-start requirement.

**USB mode, updated October 14:** use a USB-powered **PTP camera interface with explicit per-photo deletion**, superseding the October 13 drive-emulation requirement. Scan/recover the NAND catalog and expose committed FULL photos and interrupted PARTIAL objects for retrieval and explicit deletion, clearly marking PARTIAL as incomplete. Return whatever safely attributable image data can be read, with read errors/incompleteness reported in EXIF and/or PTP under D-32. Generate a host-readable representation where possible; missing optional metadata or EXIF must not suppress recoverable bytes. D-40 selects 16-bit grayscale PNG with lossless compression on USB power, retaining all ten sensor bits from the stored RAW10 object; exact reversible sample mapping and encoding remain to implement. An explicit host delete request authorizes deletion of that photo; durably record deletion before success acknowledgment and reclaim storage safely without damaging other photos or incomplete allocations. Connection/download alone does not delete photos. The shutter remains inactive in USB mode. Implementation, error mapping and interoperability are unqualified; see the [accepted USB interface](docs/decisions/usb-photo-access-review.md). Full-Speed is permitted during early bring-up; High-Speed remains an option after signal-integrity validation.

USB insertion and removal during operation are allowed. This does not establish seamless power continuity or a selected concurrent host-write/capture policy; qualify source transitions and retain the applicable failure/recovery behavior. USB detection, source selection and isolation—including preventing unintended LTC3621 battery-path enable and backfeed—remain hardware integration work. The proposed HOLD diode alone does not establish these behaviors; qualify them with the actual USB-powered prototype/Nucleo wiring before claiming they are resolved.

**Standby handoff, clarified October 13:** select an ordinary HOLD GPIO outside the RESET/PWR_ON, configured RTC and enabled WKUP exceptions, and retain the external pulldown. Standby makes ordinary I/O high impedance; Stop leaves its configuration unchanged. Configure wake sources so a held shutter does not retrigger the MCU. The external PWR_ON/AUX sequencing remains to be implemented and qualified. An optional, unselected RUN-to-ground capacitor could delay buck disable through the RUN pulldown after the diode ceases sourcing; it does not independently power the MCU. Any delay must keep main power valid until AUX falls below 0.6 V, while meeting the 50 ms exposure-start requirement and accounting for tolerances, leakage and rapid represses. See [power.md §6](power.md#6-camera-integration-requirements) and [RM0486 §§13.7.6–13.7.7, pp381–383](datasheets/processor/STM32N6_RM0486_reference_manual.pdf#page=381). No capacitor value or completed shutdown circuit is selected here.

### 6.1 Save verification policy — approved October 13, 2026

**Full image verification is configurable:** read back the full stored image payload and compare its checksum with the generated image checksum when enabled. Enable this by default during bring-up and initial testing. It may be disabled later; the measured behavior that would justify disabling it and any quantitative criteria have not yet been settled.

**Required for a successful save in both modes:** generate and store image checksums and integrity metadata; wait for NAND program/busy completion; check completion status and program-failure indicators; perform the required ECC, bad-block and recovery handling; and establish a valid durable commit. ECC status applies to data actually read and cannot verify an unread image payload.

Read back and verify the **final commit record** in both modes, separately from the optional full image readback. Complete all required data and metadata operations, status/failure checks and commit-record verification before reporting a successful save or performing the normal post-save shutdown. Disabling full image readback does not make these steps optional. The USED/DONE concept in §6.5 does not replace these checks. A new-photo write, enabled-readback or commit failure follows the five-red-flash response in §6.6. An abnormal low-battery abort under §6.4 must not wait for a successful commit or report an incomplete photo as saved. This is an approved firmware requirement; its implementation and measured behavior remain unverified.

### 6.2 Storage-full policy — approved October 13, 2026

When no usable photo slot remains, preserve all existing committed photos, reject the new capture and indicate storage full with the status LED. Do not overwrite older photos to make room. Reclaim storage occupied by saved photos through an **explicit USB erase action after download**; merely connecting USB or downloading images must not erase them. The minimum usable capacity remains 200 photos as specified in §1.2.

The exact LED pattern and erase-interface details remain implementation work. This policy is an approved requirement; firmware implementation and behavior have not yet been verified.

### 6.3 Presses while busy — approved October 13, 2026

Ignore additional shutter presses during capture and save. Finish the current operation unless a fault requires abort, without queuing another exposure. A new capture requires an actual power cycle of the main capture electronics after shutdown and a fresh press after ready; a press made while busy, even if still held at completion, must not become a deferred shot. The existing held-button Standby behavior still applies. D-41 selects flashing yellow while busy and steady green for 0.25 s after successful save; yellow cadence, startup latency, hardware and input handling remain implementation work. USB mode keeps the shutter inactive.

### 6.4 F-01: low-battery abort and shutdown state — approved October 13, 2026

**Low battery at any point in the cycle:** indicate it with **one red LED flash**, then abort the cycle to the shutdown state. This applies before exposure, during capture/save and through post-save shutdown. A flash can only occur while enough power remains; the requirement does not establish detection or indication after rail collapse. Do not continue or retry the exposure automatically, and do not require successful image commit before this abnormal abort. Preserve existing committed photos, including the current image if already valid and durably committed; never present an incomplete or unverified write as successfully saved. Exact interruption, cleanup and recovery implementation remain open; §6.5 defines the approved abrupt-loss recovery behavior.

**Shutdown means the lowest attainable power state, with an actual power cycle of the main capture electronics required before another image.** RTC backup may remain powered. Prepare peripherals and the shutdown sequence as remaining power permits, then use the Standby/HOLD handoff. With the prototype divider and a held button, remain in the lowest attainable state until release permits main power-off; prevent automatic wake or retake. A fresh press or software wake without the intervening main-power cycle is insufficient.

Battery measurement circuitry, thresholds, load qualification and available warning/shutdown energy are unimplemented or unqualified; no hold-up guarantee is implied. The recovered [BOM](bom.txt) identifies LED1 as **ROHM SML-P11MTT86R, green/yellow-green**. It does not meet the new red indication requirement; select and qualify a red-capable indication implementation without treating the unchanged BOM/CAD as compliant. Flash duration and drive details remain implementation work.

### 6.5 F-02: abrupt power loss — approved October 13, 2026

If power disappears too quickly for firmware to respond, loss of a complete **current uncommitted photo** is acceptable; **previously saved photos must be preserved**. Retain the current image too if it was already valid, complete and durably committed. **Keep any bytes already written to NAND.** Mark storage blocks **USED at the beginning of a save** and **DONE at successful completion**. USED without DONE identifies possibly corrupt/incomplete data. On next startup recover valid, complete, durably committed records; do not present incomplete data as a successfully saved photo, silently erase/discard its physical bytes, or automatically take a replacement exposure. The earlier instruction to ignore incomplete writes means exclude them from successful-photo recovery, not delete them.

USED/DONE selects the state concept, not NAND geometry, marker placement/encoding, atomic updates, reclamation or host presentation of incomplete data. D-32 now defines PARTIAL recovery access in §6.11. Required status/integrity checks and final commit-record readback verification still apply; a marker alone is not proof of valid image data. The format and recovery implementation remain unimplemented. Qualify interrupted data, metadata and marker/commit writes, torn markers, device programming limits and shared-block effects against the selected NAND and actual power behavior, preserving both old photos and interrupted raw bytes. Accepting an incomplete current image does not permit damage to older photos. This is a requirement, not a demonstrated hardware guarantee; no last-moment LED indication or successful final write is assumed.

### 6.6 Remaining failure responses — approved October 13, 2026

For the red-coded faults below, emit the stated number of red flashes while power permits, then enter the shutdown state in §6.4. An actual power cycle of the main capture electronics is required before another image; do not automatically retake it. Preserve committed photos and apply the USED/DONE and raw-byte preservation policy. No retry count, flash duration or repeating pattern is selected here.

| Condition | Accepted response |
| --- | --- |
| Low battery | **1 red flash**, at any phase as previously approved, then shutdown. The later before-exposure example does not narrow §6.4. |
| Camera initialization failure | **2 red flashes**, then shutdown. |
| Frame-capture failure | **3 red flashes**, then shutdown. |
| Storage unresponsive | **4 red flashes**, then shutdown. |
| New-photo write, enabled-readback or commit failure | **5 red flashes**, then shutdown. Do not report incomplete/unverified data as a saved photo. |
| Damaged allocation metadata or photo index | **6 red flashes**, then shutdown. |
| Time or orientation unavailable/invalid | Record an explicit **BAD sentinel** for each unavailable field during capture and still save the image. When presenting the photo through USB, omit the corresponding unavailable EXIF field rather than invent a value. Sentinel encoding and photo-file representation remain implementation work. |
| Existing saved photo unreadable | On a host request, read/check the whole original image into RAM and return recoverable content with current-read warnings. Preserve the source and retire its slot only for predictive media errors. No relocation or automatic deletion. True transfer failure or inability to establish any safely attributable data ranges still reports a USB error; malformed image/EXIF alone does not block recovery. See §§6.8 and 6.11. |
| Explicit erase fails or is interrupted | Report the failure/interruption through USB; erase is USB-only and explicitly requested. A photo read must not initiate erasure. Durable error reporting after a power interruption remains implementation work. |
| Boot failure or firmware hang | No recovery requirement or automatic strategy is selected. This is a scope decision, not a claim that technical recovery is impossible. |
| USB inserted or removed during operation | Allowed; qualify power/source transitions. No seamless-continuity guarantee or concurrent host-write behavior is selected. Shutter inactivity in USB mode remains required. |
| Exposure-start timing | Meet the deterministic **≤50 ms** design budget through qualification. No runtime timing-failure code is selected. |

### 6.7 Photo retention — approved October 14, 2026

Successfully committed photos and the metadata needed to locate, decode and verify them must remain recoverable for **ten years at room temperature (approximately 25°C reference), fully unpowered, with no refresh required**. Use the selected NAND's required ECC on retrieval; batteries, RTC backup, periodic waking and USB maintenance must not be prerequisites for retention. This is not a requirement that the RTC continue keeping time without its backup supply.

Qualify the exact part, ECC and storage layout against this requirement through **1,000 complete fill/download/explicit-erase reuse cycles**, approved October 14. At the minimum 200-photo capacity that is 200,000 photo saves. Retention must still hold for photos saved after rated usage; do not limit qualification to uncycled memory. Complete device reuse is distinct from each physical block's erase count, including metadata wear, retries and recovery. Higher-temperature storage requires separate qualification. USB image relocation/refresh is excluded by §6.8; predictive-error retirement and on-demand reads remain to implement. No measured ten-year retention result is established by this approval. See the [retention review and evidence](docs/decisions/storage-retention-review.md).

### 6.8 Host-requested reads, warnings and slot retirement — approved October 14, 2026

For each USB host image-data request, freshly read the entire image from its original NAND slot into RAM, apply device-appropriate ECC, inspect all page status results, and compare against the original stored CRC-32C before sending image bytes. Serve the prepared RAM snapshot during that transfer; a later host request performs a new NAND read. A previously successful read does not guarantee later success. Whole-image RAM staging is required; budget payload, metadata and export/USB buffers.

Read stored image payload only on a host image-data request. No background integrity scans, automatic refresh, relocation or replacement NAND copies are permitted. Catalog/commit/allocation metadata reads needed for enumeration/recovery and metadata writes needed for retirement/deletion are separate. Capture-time configurable payload readback and mandatory save/commit verification remain unchanged.

Return as much safely attributable data as the current read obtains. Preserve image geometry and original CRC; do not claim suspect bytes or missing-range placeholders are verified captured pixels. Report detected read errors/corrections via the agreed filename and EXIF UserComment warning scheme, distinguishing corrected/CRC-valid, media-marginal and damaged/unverified outcomes. A whole-image CRC mismatch alone cannot locate damaged pixels or prove a NAND defect. Missing optional timestamp/orientation still uses BAD/omit-EXIF.

If the read indicates future media unreliability, permanently exclude the whole image slot and its blocks from new image writes. Persist this safely without modifying/erasing the current image or blocking future host reads. The slot stays retired after explicit host deletion and after any later successful read. Routine corrections are classified using the selected device's predictive-error rules; unrelated USB/firmware failures alone do not condemn NAND.

Only an explicit host delete removes a photo. No read success, error or retirement triggers automatic deletion or relocation. A complete recovered object may transfer successfully while carrying integrity warnings; actual truncation/link failure still fails. PTP object names may be fetched before the current payload read, so current-read filename updates require host qualification; EXIF must describe the actual RAM buffer. Do not add background scans to work around name timing. See the [accepted read policy](docs/decisions/ecc-read-error-review.md).

### 6.9 Slot-state persistence — provisional October 14, 2026

Use a RAM lookup table backed by redundant append-only NAND journals and protected checkpoints as the prototype working direction (D-30). The fixed-slot model distinguishes FREE/PARTIAL/FULL occupancy from GOOD/BAD health. Allocate only slots established as FREE and GOOD; make allocation durable before payload writes, and complete the required save checks and verified commit before FULL. Host-authorized deletion must recover safely and establish successful erase before reusable FREE; BAD remains permanent through deletion and later good reads.

D-33 provisionally selects circular allocation: start just after the last durably allocated slot, wrap, and choose only FREE and GOOD. Advance on durable PARTIAL allocation even if saving is interrupted; host deletion does not reset the search. Keep the next-search position in RAM, include it in ordinary checkpoints, and replay subsequent valid allocation records on startup. Cursor recovery uses the same validated history as the slot table; it does not add a standalone per-capture pointer write or authorize reuse independently of slot state.

The user explicitly leaves the page/block storage layout and off-NAND allocation-table alternatives open for a later design review. Exact record encoding, physical reserve, checkpoint rotation, copy/commit protocol and startup bounds remain to design and qualify. The illustrative 16-block metadata reserve is not a frozen layout. No repeated in-place programming of state bits is assumed.

Retain off-NAND table storage and in-slot allocation/commit/health records as future directions (FD-04/FD-05). A first page reading FF alone is not sufficient evidence that the entire slot is safely erased. Vendor factory-bad markers must be preserved; runtime retirement must not modify retained photos, hide them from reads or change their physical mapping. See the [slot-state analysis](docs/decisions/slot-state-storage-review.md).

### 6.10 Photo object and storage-control boundary — approved October 14, 2026

An image and its photo metadata, including name, time, orientation and other capture attributes, are one stored object. Store that object once; do not separately duplicate its pixels or photo attributes. A single object can span multiple pages/blocks and does not imply an atomic hardware write.

Redundancy used by allocation maps, occupancy/health state, commit/deletion/retirement transactions, journals and checkpoints depends on the storage implementation. D-30's redundant journal remains a provisional approach; this object policy does not impose a universal storage-record copy count. Structural references, transaction identities/generations and integrity information may repeat, but must not become a second backup of photo attributes in a catalog/journal.

Device-required ECC, the original image-payload CRC-32C and required final commit verification remain unchanged. Exact object serialization, protection of other object fields and storage-control recovery remain to implement; do not silently change the approved CRC domain. The prior recommendation for duplicated photo metadata is superseded. See the [accepted policy](docs/decisions/storage-redundancy-review.md).

### 6.11 FULL and PARTIAL object recovery over USB — approved October 14, 2026

For every host image-data request, return whatever safely attributable image data can be read from either a FULL or a PARTIAL object. Attempt all known object ranges and stage the current result in RAM before transfer; a failed page must not suppress attempts to recover other ranges or discard bytes already obtained. Preserve positions and distinguish captured/suspect bytes from unwritten, unreadable or unknown gaps.

Report read errors and known incompleteness through EXIF and/or PTP. Retain the _RECOVERED naming convention. PARTIAL remains incomplete even if readable pages pass ECC; unavailable expected CRC means unverified, not verified or a newly invented checksum. Missing optional photo attributes, missing EXIF support or an unviewable partial image is not by itself a reason to withhold readable data. Exact gap representation, export format, object lengths and PTP warning behavior remain to implement and qualify.

Both FULL and PARTIAL objects support explicit host deletion. Retrieval never marks PARTIAL as successfully saved, causes deletion, creates a replacement NAND copy or clears retirement. Report genuine transport failures separately; if no image data can be obtained, report that result. Never guess corrupt allocation addresses or expose unrelated stored bytes. See the [accepted read policy](docs/decisions/ecc-read-error-review.md).

### 6.12 Potentiometer exposure-time control — approved October 14, 2026

**D-36 — prototype exposure time:** use a potentiometer connected to an MCU ADC input. Sample it before acquiring the image, map the reading to exposure time and apply that setting before the saved exposure begins. D-38/D-39 select fixed 1× analog and 1× digital gain, and an exponential exposure curve from the fastest supported exposure to 1 s, to be tuned on the real camera. Exact potentiometer part, resistance/taper, ADC pin/reference, wiring, filtering, invalid-input handling, numeric minimum and sensor timing configuration remain to qualify. Include input/reference startup, settling, sampling and sensor setting application in the existing ≤50 ms exposure-start budget. The control circuit must meet the existing main-path OFF-current requirement; no permanently battery-powered divider is selected. Record the exposure/configuration actually used in the existing single photo object.

The separate narrow-field photopic light-sensor proposal remains unselected background.

An initial firmware mapping candidate for normalized knob position `x` from 0 to 1 is `t(x) = t_min * (1 s / t_min)^x`. This gives equal exposure ratios for equal knob movements and smaller absolute time changes at the fast end. Clamp/quantize to supported sensor timings and record the actual applied exposure. The user selected the exponential behavior and endpoints, not a frozen formula, numeric minimum or physical logarithmic potentiometer. Verify that the selected clock/mode and frame-length settings permit one-second integration. The ≤50 ms deadline concerns exposure start; the exposure itself may last one second. Gain remains fixed during normal prototype capture, with firmware changes available for testing; there is no automatic gain/exposure loop.

### 6.13 Firmware starting point and optimization path — approved October 14, 2026

**D-37 implementation boundary:** use C and STM32CubeN6/HAL as the initial bring-up base. Keep camera, storage, power/control and USB hardware access behind simple replaceable interfaces so timing/energy-critical paths can move to LL/direct-register code or streamlined bare-metal startup/runtime without changing the accepted behavior. HAL use and RTOS use are separate choices: bare-metal firmware can use HAL, and this decision does not select an RTOS or USB middleware. ST documents HAL/LL and optional middleware separately in [STM32CubeN6](https://github.com/STMicroelectronics/STM32CubeN6); its [driver component](https://github.com/STMicroelectronics/stm32n6xx-hal-driver) supports selecting needed functions.

Measure shutter-button press from fully powered off to the saved exposure's start, later readout/save/shutdown intervals, and energy per complete capture under equivalent exposure/configuration and verification settings. Use those results to prioritize startup, driver or runtime changes; no savings follow merely from the label “bare metal.” Retain required hardware delays, integrity/commit checks, fault behavior and shutdown sequencing. D-40 selects 16-bit grayscale PNG export. Hardware integration, measured compliance, encoder integration and exact runtime/USB choices remain open.


### 6.14 Capture status indication — approved October 15, 2026

**D-41 — capture indication, approved October 15:** flash yellow from power-up throughout startup, exposure, readout and saving. After the save completes successfully, show steady green for **0.25 s (250 ms)**, then perform the accepted shutdown sequence. Successful save includes all required checks, any enabled full-image readback, and verified durable commit. Red-coded capture faults replace yellow/green with the existing red code and abort to shutdown; never show success for a failed save.

The user specified: “flashing yellow starting at power up and until write completes - then it turns to green for 0.25s. any error in the process show the Red LED codes.” This replaces the proposal to leave the LED off while busy.

Implement yellow indication from startup, with the earliest controllable point and actual power-up-to-indication latency qualified on hardware; firmware-driven blinking cannot be assumed before firmware executes. Yellow cadence/duty cycle, red flash timing, LED currents, drivers and pins are not selected. Keep indication nonblocking so it does not delay the ≤50 ms exposure-start target. Qualify placement/shielding against light entering the image while yellow flashes during exposure. The existing single yellow-green LED does not establish distinct yellow/green/red capability.

Include flashing load and the 250 ms green interval in complete-cycle energy and latency measurements. Required rails/MCU state during green remain to design; do not assume this costs only LED energy. The prior power-cost model excludes these new contributions. Power/debug modifications remain paused until the board arrives.

Preserve the accepted response map: unavailable time/orientation is recorded BAD and does not by itself fail a photo; USB faults retain host reporting; boot/hang or abrupt power loss cannot guarantee a firmware indication. A detected low-battery fault during yellow or green takes precedence and uses its existing one-red-flash shutdown response, preserving any already committed photo. No new code is assigned to these exceptions or to storage full by this decision.

## 7. Validation and bring-up

Adapt the recovered circuit checklist below to the implemented CAM-6G3-073CLR/LTC3621 revision; references to Q1/Q3 and old rail names are not instructions to retain the superseded power path.

### 7.1 Unpowered checks

- Verify no short between each rail and ground.
- Verify battery polarity/contact geometry before installing cells.
- Confirm Q1/Q3 orientation and opposed body-diode behavior.
- Confirm USB VBUS cannot feed the battery terminal.
- Inspect U1 BGA, U7 VSON-HR, U10 XDFN, J3 fine-pitch connector, and WSON/TSOP soldering.

### 7.2 Power checks

- Start from a current-limited bench source at representative battery voltages.
- Exercise the mechanical latch and verify the MCU can hold and release power.
- Measure SYS_IN, 3V3, 1V8, VCORE_0V81, CAM_VCORE_1V2, CAM_VANA_2V8, 3V3_USB, and ACCEL_1V8_SW.
- Capture startup rise time, overshoot, droop, and shutdown discharge on an oscilloscope.
- Repeat with USB-only power and with both USB and batteries connected.
- Measure true off-state leakage across temperature and humidity conditions relevant to storage.

### 7.3 Functional checks

- Qualify D-41 startup/yellow cadence, flashing during capture/save without optical contamination, no green before required checks and durable commit, steady green duration of 250 ms, red-code priority and subsequent shutdown. Measure the added indication energy and complete-cycle duration.

- Establish SWD access and boot recovery.
- Validate QSPI boot and redundant FSBL selection.
- Run destructive NAND bad-block, program, readback, interrupted-write, and recovery tests.
- Confirm full image readback/checksum comparison is enabled by default for bring-up. Validate that disabling it retains required completion/status checks, integrity metadata, ECC/recovery handling and final commit-record readback verification before normal shutdown.
- Qualify ten-year room-temperature photo and recovery-metadata retention without power or refresh through 1,000 complete reuse cycles. Use exact-part vendor retention/ECC evidence and an appropriate accelerated-retention qualification; ordinary prototype read/write tests alone do not demonstrate ten years.
- Verify busy presses do not interrupt the current capture/save or queue a shot, and another image requires an actual main-power cycle after shutdown plus a fresh press after ready. Verify the shutter is inactive in USB mode and downloads do not erase photos.
- Exercise F-01 before exposure, during capture/save and through post-save shutdown: one red flash where power permits, abnormal abort without falsely reporting incomplete/unverified data as saved, preservation of committed photos, and no automatic wake/retake before a main-power cycle. Qualify battery detection and interrupted-write recovery separately.
- Exercise F-02 through capture, USED marking, data/metadata programming and DONE/commit, including torn-marker and shared-block cases. Verify previously saved photos and valid committed current images survive, written incomplete bytes remain retained and distinguishable from successful photos, and recovery does not trigger a replacement exposure.
- Inject the §6.6 failures and verify the six red codes/shutdown behavior, BAD sentinels and omission of unavailable EXIF fields, USB reporting of photo-read/explicit-erase errors, and allowed USB transitions. These checks do not imply implemented fault detection or qualified recovery.
- Validate RTC backup operation with main power absent and confirm no digital-pin backfeed.
- Validate accelerometer switched-power behavior and orientation mapping.
- Verify camera rail sequence, MCLK, I2C identity, CSI lock and repeated cold starts; measure shutter-button press to exposure start separately from exposure duration, first complete frame, save and shutdown.
- Verify potentiometer endpoint/intermediate readings, ADC settling and the exposure actually applied to the saved frame. Check repeated cold starts and input conditioning against the ≤50 ms deadline; account for the control circuit in OFF-current measurements.
- Validate USB Full-Speed first, then High-Speed eye/channel behavior if used.
- Verify LED visibility and shutter mechanics in the enclosure.

## 8. Current verification status

The recovered schematic passed connectivity reconstruction and ERC checks. Those checks do not establish electrical correctness: the [September 5 design review](docs/DESIGN-REVIEW.md) records 47 findings, including confirmed wiring and footprint faults. An October 12 export still matched that reviewed connectivity baseline. The prototype camera and LTC3621 selections have not been applied to the CAD, and there is no measured prototype qualification.

The recovered design has 148 schematic components and 81 nets; its earlier inventory records 27 unique BOM part types and 146 BOM instances, with CAM1 externally mounted and optional SW2/SW3 excluded. These are historical counts, not a released prototype BOM. All recovered PCB-included components have footprints, but footprint loading and earlier U7/U10 corrections do not replace manufacturing-geometry review.

## 9. Open items and release blockers

First integrate CAM-6G3-073CLR and the selected four-cell/LTC3621 power path, update the dependent image/memory/power budgets, and close the existing electrical review findings. This document is not a manufacturing-release declaration. The following also remain open:

1. Complete and independently review final component placement.
2. Route all nets and clear DRC/airwires.
3. Obtain the selected fabricator's actual stackup and field-solved USB/MIPI geometry.
4. Confirm the selected fabricator can reliably build 0.10/0.10 mm and 0.50/0.20 mm vias.
5. Rebuild and independently verify J3 production lands against the exact drawing and selected module interface; the recovered footprint has a confirmed geometry defect.
6. Verify the exact CAM-6G3-073CLR mechanical model and physical module fit/orientation.
7. Finalize battery contacts, polarity keying, screw locations, lens aperture, USB opening, shutter interface, and rear LED aperture.
8. Choose actual manufacturer part numbers for generic resistors, capacitors, and inductors, including MLCC DC-bias and inductor saturation/DCR validation.
9. Bench-validate ≤50 ms from shutter-button press to start of exposure, starting fully powered off; measure exposure duration, frame readout, save and shutdown separately.
10. Measure capture/save energy, peak current, rail droop, cell voltage sag, off leakage, and repeated-shot recovery.
11. Validate raw NAND record/recovery behavior and PTP enumeration, download, explicit per-photo deletion, failure reporting and disconnect recovery.
12. Recheck sourcing and lifecycle status immediately before procurement.

## 10. Production notes

- Treat bom.txt as the recovered historical BOM; revise and review it for the locked prototype before procurement or assembly. The selected CAM-6G3-073CLR remains a separately procured external module.
- SW2 and SW3 are optional DNP debug footprints and are excluded from the production BOM.
- The battery contact system is not represented by production-ready holder components in this revision.
- Generic passives require final procurement MPN assignment before assembly release.
- Do not release Gerbers until placement, routing, DRC, impedance, camera mechanics, and enclosure fit are signed off.
- Preserve project test pads unless their removal is explicitly justified by routing or enclosure constraints.
- Any component substitution must preserve voltage rating, temperature range, package/land pattern, startup behavior, leakage, transient response, and interface timing, not merely nominal function.
