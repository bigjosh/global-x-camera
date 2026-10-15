# Camera and memory design review

> **Historical sensor workload:** this September review analyzes CAM-5G0-079CLR/VD55G0 and the recovered memory circuit. The prototype now selects CAM-6G3-073CLR/VD56G3, at least 200 packed-RAW10 photos and a 50 ms deadline to exposure start; see the [current specification](../../spec.md). VD55G0 patch timings, 486,220-byte frames, rail assumptions and capacity estimates below must not be reused as qualification of VD56G3. Physical findings remain open unless a corrected implementation or documented supersession closes them.

Date: 2026-09-05. Based on the reconstructed connectivity and raw Flux per-property units. The source connectivity SHA-256 is `51e7cc050d23652d4eaf891e7384f519d6f3fd94c0c72f2dd945cbf626a62e98`. No schematic changes were made.

**The selected camera, NOR and NAND architecture is usable, but J3 lands must be rebuilt before PCB release.** The 50 ms target requires a qualified sensor revision/patch and a measured exposure/startup budget. NAND hardware BCH capability is sufficient; metadata and interrupted-write behavior still need a defined integrity format. MCU boot-CS and NAND-RNB pin faults are owned by the separate MCU review.

The machine-readable evidence and findings are in [camera-memory-findings.json](camera-memory-findings.json). Confirmed means established by current artifacts/documents; conditional means it depends on a stated firmware, tolerance or procurement condition; measurement identifies a bench closure requirement.

## Priorities

| ID | Severity | Confidence | Finding |
| --- | --- | --- | --- |
| CAM-001 | blocker | confirmed | Rebuild J3 signal lands before PCB release |
| CAM-002 | high | conditional | Sensor revision can make a 50 ms cold capture impossible |
| CAM-003 | high | measurement | Define exposure completion and first valid frame for the 50 ms requirement |
| CAM-004 | high | conditional | Power-down must remove analog power before camera core and I/O |
| CAM-005 | medium | conditional | The 1.2 V camera core choice has limited tolerance margin |
| CAM-006 | medium | conditional | XSHUTDOWN pulldown is not proven against maximum input leakage |
| CAM-007 | medium | measurement | 1 MHz camera I2C needs a capacitance and pull-up budget |
| CAM-008 | medium | conditional | Use the exact 079CLR module envelope for mechanical release |
| CAM-009 | low | conditional | Qualify the clear-filter optics for intended lighting |
| MEM-001 | high | conditional | Use BCH4 or stronger and protect metadata outside the FMC BCH data path |
| MEM-002 | high | conditional | Power-fail recovery must respect partial-program and erase rules |
| MEM-003 | medium | conditional | Keep NAND scanning and erase work outside acquisition latency |
| MEM-004 | medium | conditional | NOR warm-reset state needs a recovery contract |
| MEM-005 | low | confirmed | AC remains supported; AD substitution changes the storage format |

## Checks that passed or have a clear boundary

- Exact module supports one CSI-2 data lane; DATA1P/N positions 10/12 mate to MCU lane0. Positions 15/17/19/21/22/24 are module NC; added connector power contacts 31-34 are GND in both symbols.
- Camera PC9=MCO2 and PC10/PC11=I2C4 on 1.8 V VDDIO4 pass MCU AF/domain review. A legal MCLK rate such as 20 MHz can be generated from 40 MHz HSE divided by 2, subject configuration and duty/jitter validation.
- C63/C65/C70 provide nominal 1 uF host capacitors on analog/core/IO respectively; module embedded capacitors do not replace these. Production MLCC effective value/placement remains a layout/BOM check.
- NOR IQ fixed QE does not block ROM legacy SPI; its CS pullup and EP ground are valid. Actual ROM CS pin error is MCU-001, not a Winbond protocol fault.
- NAND 2.7-3.6 V x8, TSOP48 map, supply pins and protection defaults are structurally suitable. FMC BCH exists; actual RNB connection to PF2/NWAIT is a separate MCU-003 issue: relocate to PA7/R12 AF12 on 3.3 V for dedicated NAND RNB; do not substitute PE4 on 1.8 V.
- NAND PT has a specified internal pulldown: the exact datasheet (PDF p12) explicitly permits low or floating to disable protection. R27=100 kohm reinforces this valid default. Maintain WP# low during ramp and wait for POR readiness (R/B# or 1 ms, p71).
- No schematic or footprint edits were made. Electrical correctness is not inferred from zero ERC.

## Data, capacity and save budget

Full native output is **644x604 at 10-bit in RAW10**, or 486,220 packed image bytes. A 16-bit SRAM/container representation is 777,952 bytes. Neither padding nor a 12-bit container increases sensor information. Four border pixels are included in the native dimensions; preserve the requested full crop.

| Stored representation | Image bytes | 2KiB NAND pages | Program busy typ/max | NAND-only busy energy at 3.3 V typ/max | Image slots, 2008/2048 good blocks |
| --- | ---: | ---: | --- | --- | --- |
| 10-bit storage | 486,220 | 238 | 71.4/142.8 ms | 3.5343/14.1372 mJ | 539/550 |
| 16-bit storage | 777,952 | 380 | 114.0/228.0 ms | 5.643/22.572 mJ | 338/344 |

Busy time and energy use datasheet program timing/current only, at 3.3 V; exclude bus transfer, ECC CPU, readback, erase, metadata and other system loads. Capacity excludes metadata/redundancy/reserve and assumes page-granular allocation across blocks; whole-block allocation yields less. These are estimates, not measurements.

NAND page-program current is 15 mA typical/30 mA maximum; page busy time 300/600 us. Block erase is 1/3.5 ms typical/maximum, and power-on current can reach 50 mA. Keep pre-erased blocks available. Program is outside the 50 ms acquisition target, but its complete system energy matters to the coin-cell design. A 1.2 Gb/s CSI lane transports packed active payload in 3.24 ms in isolation; line/frame overhead and exposure make this an optimistic transport bound, not a frame-acquisition specification.

Evidence: [NAND datasheet](../../datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf), PDF pp64-66,73; [sensor datasheet](../../datasheets/camera/VD55G0_DS13170_datasheet.pdf), PDF pp8,16; [UM2829](../../datasheets/camera/VD55G0_UM2829_integration_registers.pdf), PDF pp18-21,39-40.

## CAM-001 - Rebuild J3 signal lands before PCB release

**blocker / confirmed.** The current GX.pretty/J3_Recovered.kicad_mod retains 30 signal lands of 0.127 by 1.1176 mm centered at Y=+/-0.7468 mm. Hirose recommends 0.18+/-0.02 mm width, with 1.80/1.18 mm outer/inner row extents, implying 0.31 mm pad length. The recovered lands extend into the central area marked no conductive trace.

This is a manufacturing geometry defect, not an ERC error. Fine-pitch soldering and connector fit cannot be released with these lands.

**Recommendation:** Rebuild copper, mask, and paste from the exact Hirose drawing; independently verify pin-1/mating orientation. Keep the four end power contacts 31-34 on GND. Obtain a controlled drawing or vendor acceptance for production because the archived sheet is marked reference.

**Closure:** Compare every land and mask aperture numerically, then inspect a 1:1 plot and actual mating part before routing/fabrication.

Evidence:
- [datasheets/connectors/BM28B0.6-30DS_51_drawing.pdf](../../datasheets/connectors/BM28B0.6-30DS_51_drawing.pdf) PDF page(s) 1; Recommended PCB layout and metal mask.
- [hardware/kicad/GX.pretty/J3_Recovered.kicad_mod](../../hardware/kicad/GX.pretty/J3_Recovered.kicad_mod).
- [datasheets/camera/CAM-5G0-079CLR_schematic.pdf](../../datasheets/camera/CAM-5G0-079CLR_schematic.pdf) PDF page(s) 1.

## CAM-002 - Sensor revision can make a 50 ms cold capture impossible

**Current-scope note, October 15:** the numbers below concern the historical VD55G0. The selected VD56G3 module has a different revision/patch dependency; see the [current cold-start review](../decisions/50ms-cold-start-review.md). D-04 now measures the start of exposure, not completion/readout.

**high / conditional.** The module BOM does not identify the sensor silicon cut. Official ST driver revision 0x1111 uses cut1_patch=6868 bytes; revision 0x1120 uses cut2_patch=260 bytes, loaded at each power-on. UM2829 describes the patch load/activation before BOOT and STREAMING.

At the sensor maximum 1 MHz I2C rate, patch data plus ACK alone takes at least 61.812 ms for cut1 or 2.340 ms for cut2. At 400 kHz those bounds are 154.530 and 5.850 ms. The cut1 path already exceeds 50 ms before power ramp, MCU boot, configuration, exposure, or readout. These are transfer lower bounds, not measured startup times.

**Recommendation:** Read and record the module revision on samples and qualify the production supply to a supported cut/patch combination. Use the approved patch for that cut and measure it; do not omit a required patch merely to meet latency. If only cut1 is available, revise latency or power-retention architecture.

**Closure:** A procurement-controlled sensor revision and measured cold boot-to-valid-frame trace within the allocated budget.

Evidence:
- [datasheets/camera/VD55G0_UM2829_integration_registers.pdf](../../datasheets/camera/VD55G0_UM2829_integration_registers.pdf) PDF page(s) 7, 12; READY_TO_BOOT and firmware patch.
- [datasheets/camera/VD55G0_DS13170_datasheet.pdf](../../datasheets/camera/VD55G0_DS13170_datasheet.pdf) PDF page(s) 21; I2C maximum clock.
- [docs/review/evidence/vd55g0.c](../../docs/review/evidence/vd55g0.c).
- [docs/review/evidence/vd55g0_patches.h](../../docs/review/evidence/vd55g0_patches.h).

## CAM-003 - Define exposure completion and first valid frame for the 50 ms requirement

**Requirement settled since this historical review:** D-04 defines button press from fully off to start of exposure; D-38/D-39 select fixed 1×/1× gain and manual exponential exposure control. VD55G0-specific data below is historical. Qualify the selected VD56G3 first exposure using the [current review](../decisions/50ms-cold-start-review.md).

**high / measurement.** The specification requires full native resolution and bit depth within 50 ms. VD55G0 full depth is 10-bit, with RAW10 output, not 9-bit fast mode or RAW8. Autoexposure updates from preceding frame statistics; a cold first frame is not guaranteed to have converged exposure. The host must provide CLKIN before XSHUTDOWN release and wait for READY_TO_BOOT before I2C access.

A steady-state 185 fps rating (~5.41 ms frame period) does not establish cold-shutter latency or image exposure quality. Long exposures and several AEC convergence frames can consume the deadline even with cut2.

**Recommendation:** Define whether the deadline means end of exposure or a complete valid frame in SRAM. Use full 644x604, normal 10-bit ADC and RAW10. Budget rail/ROM/FSBL/patch/configuration/exposure/readout separately; choose a bounded manual or seeded AEC cold-start exposure policy and record actual applied gain/exposure with the image. GPIO0 is currently unconnected, so use supported I2C follower trigger or streaming control unless precise external-trigger wiring is added.

**Closure:** Instrument power, XSHUTDOWN, MCLK, first CSI frame start/end and exposure status across light levels and supply/temperature corners.

Evidence:
- [datasheets/camera/VD55G0_DS13170_datasheet.pdf](../../datasheets/camera/VD55G0_DS13170_datasheet.pdf) PDF page(s) 8, 16, 20.
- [datasheets/camera/VD55G0_UM2829_integration_registers.pdf](../../datasheets/camera/VD55G0_UM2829_integration_registers.pdf) PDF page(s) 7, 20, 21, 35, 36, 37, 39, 40.
- [spec.md](../../spec.md); 1.2 and 6.
- [docs/review/mcu-review.md](../../docs/review/mcu-review.md); MCU-006 boot-load budget.

## CAM-004 - Power-down must remove analog power before camera core and I/O

**high / conditional.** U9 analog enable is controllable, but U10 core enable follows 1V8 and camera I/O is directly on 1V8. The recorded flow ends by releasing the main latch. DS13170 requires XSHUTDOWN low before analog power-down, analog below 20% of its minimum (0.54 V), then at least 1000 us before core/I/O fall. TLV700 has no specified active output-discharge function or guaranteed discharge interval.

Simultaneously dropping the main latch does not guarantee the required sequence. Disabling U9 and waiting a nominal 1 ms also does not establish that its output capacitor has already discharged below 0.54 V.

**Recommendation:** Stop streaming, enter standby, assert shutdown, disable U9, and keep the upstream/core/I/O rails alive until measured or guaranteed analog decay plus 1 ms has elapsed. Add a defined discharge path or choose a regulator with specified output discharge if software timing cannot bound it. Preserve the existing startup delay of >=1 ms after both lower rails are actually valid before enabling analog.

**Closure:** Scope simultaneous VANA/VCORE/VDDIO/XSHUTDOWN at cold start, normal shutdown, rapid re-press and USB transitions; determine behavior on uncontrolled brownout separately.

Evidence:
- [datasheets/camera/VD55G0_DS13170_datasheet.pdf](../../datasheets/camera/VD55G0_DS13170_datasheet.pdf) PDF page(s) 17, 18.
- [datasheets/camera/VD55G0_UM2829_integration_registers.pdf](../../datasheets/camera/VD55G0_UM2829_integration_registers.pdf) PDF page(s) 7, 8.
- [datasheets/power/TI_TLV700_datasheet.pdf](../../datasheets/power/TI_TLV700_datasheet.pdf) PDF page(s) 6, 11, 12.
- [hardware/reconstruction/schematic-connectivity.json](../../hardware/reconstruction/schematic-connectivity.json).

## CAM-005 - The 1.2 V camera core choice has limited tolerance margin

**medium / conditional.** U10 NCP115AMX120TCG nominal 1.200 V supplies a sensor specified at 1.10-1.26 V, nominal 1.15 V. NCP115 specifies +/-40 mV output accuracy at its stated 1 mA test point and separately up to 30 mV load regulation for XDFN. Static 1.16-1.24 V fits, leaving only 20 mV to the sensor upper limit before accounting for other effects.

The nominal value is not itself an overvoltage fault, but typical graphs or the +/-1% room-temperature headline do not establish a guaranteed rail budget across input, load, temperature and transients. Sensor core ripple allowance is 20 mV up to 10 MHz.

**Recommendation:** Close the signed worst-case regulation and transient budget using exact test conditions and actual loading. Retain U10 only if the full 1.10-1.26 V window is met at the module; otherwise select a tighter regulator nearer 1.15 V. Do not simply add all maxima as a claim of actual overvoltage.

**Closure:** Worst-case design calculation plus VCORE measurements at sensor startup/streaming, including the specified 38 mA streaming-start transient.

Evidence:
- [datasheets/power/onsemi_NCP115_datasheet.pdf](../../datasheets/power/onsemi_NCP115_datasheet.pdf) PDF page(s) 3, 4.
- [datasheets/camera/VD55G0_DS13170_datasheet.pdf](../../datasheets/camera/VD55G0_DS13170_datasheet.pdf) PDF page(s) 16, 19, 20.
- [hardware/reconstruction/schematic-connectivity.json](../../hardware/reconstruction/schematic-connectivity.json).

## CAM-006 - XSHUTDOWN pulldown is not proven against maximum input leakage

**medium / conditional.** R20 is 100 kohm. Sensor digital-input leakage permits 10 uA, while VIL max is 0.3*VDDIO. An adverse 10 uA leakage through 100 kohm permits 1 V, above the ~0.54 V low threshold at nominal I/O power. Actual leakage direction and MCU reset-state contributions are not characterized here.

The stated default-low shutdown guarantee has no demonstrated worst-case margin during reset and rail sequencing.

**Recommendation:** Use a stronger pulldown such as 10 kohm, or document a guaranteed combined leakage bound including the MCU pin. A lower resistance adds small current only while shutdown is released. R21 U9 enable does not have this same issue: its 100 kohm with TLV700 0.5 uA maximum enable leakage yields 50 mV.

**Closure:** Guaranteed leakage calculation over corners, plus a captured reset/startup waveform below VIL until the intended release.

Evidence:
- [datasheets/camera/VD55G0_DS13170_datasheet.pdf](../../datasheets/camera/VD55G0_DS13170_datasheet.pdf) PDF page(s) 20; Digital inputs.
- [datasheets/power/TI_TLV700_datasheet.pdf](../../datasheets/power/TI_TLV700_datasheet.pdf) PDF page(s) 6; Enable current.
- [hardware/reconstruction/schematic-connectivity.json](../../hardware/reconstruction/schematic-connectivity.json).

## CAM-007 - 1 MHz camera I2C needs a capacitance and pull-up budget

**medium / measurement.** R22/R23 are 4.7 kohm to 1V8. Sensor Fm+ allows 120 ns rise time, while Fast mode allows 300 ns. A lumped RC estimate tr(30-70%)=0.8473*R*C gives maximum bus capacitance about 30 pF at 1 MHz or 75 pF at 400 kHz with these pulls.

The speed used to reduce patch/configuration time is not guaranteed by choosing a 1 MHz peripheral setting; module flex, connector, MCU/sensor pads and probe capacitance all count.

**Recommendation:** Keep the bus short and measure rise/fall times at the module. Select pull-ups from actual capacitance and both devices' sink limits if Fm+ is needed. Use MCO2 on PC9 at a legal 6-27 MHz clock with the documented duty/jitter limits; MCU AF/domain checks passed separately.

**Closure:** Scope I2C timing and MCLK at final loading; no transfer errors across supply/temperature corners.

Evidence:
- [datasheets/camera/VD55G0_DS13170_datasheet.pdf](../../datasheets/camera/VD55G0_DS13170_datasheet.pdf) PDF page(s) 20, 21.
- [docs/review/mcu-review.md](../../docs/review/mcu-review.md); PC9 MCO2 and PC10/PC11 I2C4 at VDDIO4=1V8.

## CAM-008 - Use the exact 079CLR module envelope for mechanical release

**medium / conditional.** The existing spec used a related CAM-6G3 STEP. Exact DB5266 Rev2 specifies 079CLR head 5x5x2.8 mm, total 11.65x8x2.8 mm, and connector-to-optical-center distance 7.45 mm. ST now lists an exact CAM-5G0-079CLR STEP ZIP; direct TLS retrieval failed in this review, so no replacement model was claimed imported.

Related-module geometry cannot certify flex sweep, connector orientation, optical aperture, or the complete <=5 mm product stack.

**Recommendation:** Retrieve/import the exact STEP via the listed official link or use a physical module. Combine it with the corrected J3 footprint, actual mating height, PCB/enclosure datums, clearances and optical field of view before locking placement. Evaluation-module procurement and production-unit supply should also be confirmed with the module supplier.

**Closure:** Exact CAD/physical fit with the intended flex orientation and a complete thickness/clearance drawing.

Evidence:
- [datasheets/camera/CAM-55G0_DB5266_module_brief.pdf](../../datasheets/camera/CAM-55G0_DB5266_module_brief.pdf) PDF page(s) 3.
- [https://www.st.com/en/evaluation-tools/cam-55g0.html](https://www.st.com/en/evaluation-tools/cam-55g0.html); CAD Design Files: exact 079CLR STEP.
- [https://www.st.com/resource/en/cad_design_files/cam-5g0-079clr-step.zip](https://www.st.com/resource/en/cad_design_files/cam-5g0-079clr-step.zip).

## CAM-009 - Qualify the clear-filter optics for intended lighting

**low / conditional.** The selected 079CLR has a clear filter and 13.5 cm-to-infinity depth of field. ST AN5836 documents persistent visible-domain artifacts after intense focused illumination, including when the sensor is unpowered.

A powered-off outdoor camera can still acquire image artifacts; close-up behavior and spectral appearance are also properties of the selected optical module, not MCU processing.

**Recommendation:** Include intended outdoor/indoor lighting and near-distance scenes in optical qualification. If necessary, add an optical cover/shutter or revise the filter/module specification with the supplier; avoid treating power gating as optical protection.

**Closure:** Acceptable images after intended storage/illumination exposure and at required scene distances.

Evidence:
- [datasheets/camera/CAM-55G0_DB5266_module_brief.pdf](../../datasheets/camera/CAM-55G0_DB5266_module_brief.pdf) PDF page(s) 3.
- [datasheets/camera/VD55G0_AN5836_visible_domain_limitations.pdf](../../datasheets/camera/VD55G0_AN5836_visible_domain_limitations.pdf) PDF page(s) 1, 5.

## MEM-001 - Use BCH4 or stronger and protect metadata outside the FMC BCH data path

**high / conditional.** MX30LF2G18AC requires 4-bit correction per (512+16) bytes. STM32N6 FMC supports BCH4/BCH8 per 512-byte data sector; BCH4 produces 7 parity bytes, or 28 bytes per 2 KiB page. Hamming is the reset/default algorithm and is insufficient. RM0486 explicitly says its BCH encoder does not process spare-area metadata.

There is no inherent controller ECC-strength incompatibility, but selecting Hamming or putting unprotected commit/allocation data into OOB would leave the required integrity contract incomplete. CRC detects errors but does not replace correction.

**Recommendation:** Configure BCH explicitly, specify an OOB layout retaining factory bad-block markers, and place critical metadata in BCH-protected data sectors or provide its own adequate error protection/redundancy. Flip corrected bits using FMC error locations and handle uncorrectable sectors, erased pages and ECC-field errors.

**Closure:** Documented format plus injected 1-4 bit errors in each data sector, parity and metadata; correctable recovery and deterministic rejection of uncorrectable records.

Evidence:
- [datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf](../../datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf) PDF page(s) 6, 7, 73, 74.
- [datasheets/processor/STM32N6_RM0486_reference_manual.pdf](../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf) PDF page(s) 1231, 1232, 1233, 1234; NAND ECC controller and sequencer.

## MEM-002 - Power-fail recovery must respect partial-program and erase rules

**high / conditional.** The spec calls for a verified commit and redundant metadata but implementation is not present here. AC permits at most four partial programs per page and requires ascending page order within a block. Macronix warns an interrupted program/erase can appear readable yet have inadequate retention margin. Pulling WP# low or issuing reset during program/erase aborts it.

A last-minute WP# assertion, a same-page commit-bit rewrite, or an immediate successful readback cannot by itself prove a durable transaction. Reusing an uncertain erased page/block can damage later recovery.

**Recommendation:** Use append-only, BCH-protected commit records and an interrupted-operation ledger; keep old committed records until new ones pass status/ECC/CRC checks. Quarantine/re-erase uncertain blocks. Preserve factory bad-block marks before erase and budget partial-program count including ECC/OOB writes. Keep WP# high until the final operation completes; only then protect and remove power.

**Closure:** Randomly interrupt power throughout data, ECC, commit and erase stages; every reboot must recover prior valid images and reject uncertain new records without erasing valid factory markers.

Evidence:
- [datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf](../../datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf) PDF page(s) 27, 40, 65, 71, 72, 73, 74.
- [datasheets/memory/Macronix_AN0340_NAND_interrupted_program_erase.pdf](../../datasheets/memory/Macronix_AN0340_NAND_interrupted_program_erase.pdf) PDF page(s) 3, 4.
- [datasheets/memory/Macronix_AN0363_NAND_unexpected_power_loss.pdf](../../datasheets/memory/Macronix_AN0363_NAND_unexpected_power_loss.pdf) PDF page(s) 5, 6.

## MEM-003 - Keep NAND scanning and erase work outside acquisition latency

**medium / conditional.** The device has 2048 blocks; factory markers occupy the first spare byte of pages 0 and 1 in each block. At the specified 25 us maximum array-to-buffer time, a two-marker full scan can budget 4096*25 us=102.4 ms before command/transfer overhead. This is a worst-case timing budget, not a minimum or a measured scan time.

An unconditional startup scan before camera capture is incompatible with a guaranteed 50 ms acquisition budget at the device timing corner, even though save completion is allowed later.

**Recommendation:** Persist redundant protected allocation/BBT checkpoints, perform first-use formatting and full recovery scans in a separate mode or after capture into SRAM, and maintain a reserve of erased good blocks. Plan recovery paths without making NAND ready a prerequisite for exposure when SRAM can hold the frame.

**Closure:** Measured normal and damaged-metadata startup paths with explicit acquisition behavior; documented minimum erased reserve.

Evidence:
- [datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf](../../datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf) PDF page(s) 66, 73, 74.
- [datasheets/memory/Macronix_AN0545_NAND_design_in_notice.pdf](../../datasheets/memory/Macronix_AN0545_NAND_design_in_notice.pdf) PDF page(s) 1, 2, 3.

## MEM-004 - NOR warm-reset state needs a recovery contract

**medium / conditional.** IQ fixes QE=1 but still accepts standard single-line SPI. WSON8 has no dedicated reset input. Guaranteed power initialization requires VCC below 0.8 V for at least 100 us; a processor reset or quick power re-press does not necessarily do that. UM3234 documents a fixed legacy 0Bh boot read, not a documented universal flash reset/release sequence.

If firmware leaves NOR in deep power-down, continuous-read/wrap state, or an unfinished write, watchdog/BOR/debug reset can re-enter ROM with an unsuitable flash state. This is conditional on firmware behavior, not a proven failure of the current absent firmware.

**Recommendation:** Keep boot NOR in a ROM-compatible state before reset and avoid deep power-down/volatile read modes unless reset recovery is demonstrated. Use the 66h/99h sequence only when safe; it takes about 30 us and may corrupt an active write. Respect 20 us read-ready and 5 ms write-inhibit after power-up. Restrict 133 MHz reads to VCC>=3.0 V; at 2.7 V the datasheet fast-clock limit is 104 MHz.

**Closure:** Test cold, warm, watchdog, BOR, USB-powered reset and rapid re-press from every NOR state allowed by firmware.

Evidence:
- [datasheets/memory/W25Q128JV_datasheet_RevM.pdf](../../datasheets/memory/W25Q128JV_datasheet_RevM.pdf) PDF page(s) 10, 17, 60, 61, 62.
- [docs/review/mcu-review.md](../../docs/review/mcu-review.md); MCU-001 actual boot CS error; MCU-006 ROM protocol/timing.

## MEM-005 - AC remains supported; AD substitution changes the storage format

**low / confirmed.** Macronix March 2026 MPLP lists MX30LF2G18AC-TI as recommended for new design with longevity support through December 2029; AD-TI is listed through July 2030. This is not an EOL notice. The migration note changes AC 4-bit/528 B and 64-byte spare to AD 8-bit/544 B and 128-byte spare, with different endurance and program/erase performance.

There is no evidence here requiring an immediate AC replacement. A purchasing substitution to AD without firmware/format qualification would be unsafe, and longevity horizon should be checked against the intended production period.

**Recommendation:** Keep exact MPN control, confirm supply/support horizon directly with Macronix, and qualify AD as a separate device/format if desired. Do not label AC obsolete from distributor stock or the existence of a migration note.

**Closure:** Supplier lifecycle confirmation and a controlled alternate-device qualification before substitutions.

Evidence:
- [datasheets/memory/Macronix_MPLP_part_list_March_2026.pdf](../../datasheets/memory/Macronix_MPLP_part_list_March_2026.pdf) PDF page(s) 20.
- [datasheets/memory/Macronix_AN0719_MX30LF2G18AC_to_MX30LF2G28AD_migration.pdf](../../datasheets/memory/Macronix_AN0719_MX30LF2G18AC_to_MX30LF2G28AD_migration.pdf) PDF page(s) 1, 2.

## Evidence acquisition and scope

Official ST reference driver and patch tables are archived under `docs/review/evidence/`, pinned to commit `a05627b0f6d8775aa54b6fa306e91f425f2cbf9e`; they were inspected to calculate patch-transfer bounds, not integrated as project firmware. The manufacturer March 2026 longevity list was added to `datasheets/memory/`.

Exact-module STEP link was discovered on the ST product page, but HTTPS retrieval reset; no browser workaround or global browser-setting change was used. Existing exact electrical documents and the module dimensional brief were sufficient to complete this review.

Remaining bring-up work includes actual unit/patch identification, capture/exposure timing, I2C/MCLK waveforms, camera rail sequencing/ripple, corrected connector fit and NAND error/power-interruption tests. Firmware integration can proceed separately; it is not a reason to delay correcting the known PCB land and MCU pin issues.
