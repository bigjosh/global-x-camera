# Alliance NAND wiring for the Nucleo prototype

October 18, 2026, final user selection. **D-46 retains the existing AS5F14G04SND-10LIN and selects Arduino-header connections with bit-banging allowed.** Use the VDDIO4 1.8 V mapping below; this supersedes the earlier hardware-quad priority and CN3/VDDIO5 route. **D-47 selects 5.0 V from LTC3621 with the existing downstream regulator tree and unnecessary capture loads excluded.** The [consolidated assembly guide](nucleo-assembly-guide.md) is the authoritative rework order, component-location reference and verification checklist. This file retains the electrical reasoning and unselected alternatives. No physical rework, NAND communication or firmware change has been reported in these documentation turns.

## Current direction: Arduino bit-banged quad SPI

All six NAND signals and ground use Arduino headers; the 1.8 V supply and bank feed use CN12.14 and CN3.10. Remove SB24 and the two 3.3 V pull-ups R88/R89 before powering VDDIO4 at 1.8 V. Keep SB8/SB5/SB3 fitted and SB2/SB4 open. PA3/D10 remains a main-domain GPIO used only as open-drain CS with a pull-up to NAND 1.8 V. See [the selected pin table](#selected-arduino-header-bit-bang-mapping) and the [assembly guide](nucleo-assembly-guide.md); do not combine this with the historical SB23 bank conversion.

The Arduino mapping spans GPIOC/GPIOH and its actual clock, energy and signal integrity remain unmeasured. Software bit-banging is accepted for this prototype; no hardware SPI/DMA performance is promised. The alternative storage parts and hardware-quad schemes below remain research rather than an instruction to replace the existing NAND or modify the boot bus.

## Unselected alternative: hardware quad SPI

The following assessment records the earlier hardware-quad preference, superseded by the final Arduino decision above.

**October 18 alternative-part research:** the [faster-storage comparison](../../reports/Faster%20camera%20storage%20alternatives.md) recommends evaluating native-3.3 V **MX35LF4GE4AD-Z4I** for simpler CN16 hardware-quad wiring and faster programming; larger Micron/GigaDevice serial parts and genuine-cache parallel Macronix parts are also compared. None is yet qualified against the combined retention/reuse requirement. This is a recommendation, not a replacement decision: **D-46's Alliance selection remains in force**, and no hardware change or purchase was made.

The STM32 XSPI peripheral supports four-bit payload transfers and DMA. Moving from Arduino back to the earlier CN3 pins alone would **not** provide that hardware interface. The separate XSPIM port 1 interface is available at the normally unpopulated **CN16** header:

| Function | MCU / AF | CN16 pin |
|---|---|---:|
| NCS1 | PO0 / AF9 | 5 |
| CLK | PO4 / AF9 | 13 |
| IO0 | PP0 / AF9 | 3 |
| IO1 | PP1 / AF9 | 2 |
| IO2 | PP2 / AF9 | 4 |
| IO3 | PP3 / AF9 | 6 |
| GND | — | 1 or 16 |

**These pins are stock 3.3 V VDDIO2, not direct connections to the 1.8 V Alliance NAND.** The MCU supports operating VDDIO2 at 1.8 V, but the Nucleo does not provide a simple bank-isolation link. Neither SB23 nor SB24 changes this bank. MB1940 sheet 4 ties all four VDDIO2 supply balls (L13/L14/M14/M15) directly to main VDDIO; a native-1.8 V conversion would need layout-specific PCB rework, and no safe cut points have been verified. This is not a claim that conversion is impossible. PO5/camera NRST also belongs to VDDIO2, so its changed output level and camera startup would need checking after such a conversion. Do not lower the entire main VDDIO supply or make the earlier SB23/SB24/R88/R89 changes for this interface. If any earlier rework has already been performed, first record and reconcile the actual board state; never close a 3.3 V bridge while an external 1.8 V feed remains attached.

The preferred separate-bus direction is CN16 plus suitable high-speed bidirectional translation, keeping NAND wiring off the boot NOR bus. Translator selection is **not yet qualified**. TI **TXB0606** is a concrete six-channel auto-direction candidate explicitly intended for QSPI/OSPI and offered in TSSOP-16. It is not a drop-in approval: verify NAND output-drive compatibility, VOH/VIH margins, translator delay plus NAND clock-to-data delay, load and sample timing. Its external pull-up constraints differ from the earlier 10 kΩ wiring. A generic I2C shifter, the earlier TXU0304 single-SPI translator, or the translator's headline data rate does not establish a working fast quad link. No 50 MHz assembled link is claimed.

An alternative avoiding translation is to share the already-1.8 V **XSPIM port 2 / VDDIO3** boot-NOR bus. The clock/data nets are PN6/PN2/PN3/PN4/PN5 at existing 0 Ω links **R116/R108/R101/R120/R109**, with separate **PN12/NCS2 at CN16.31**. All are AF9. This would need five fine solder taps with the original NOR links retained, plus NAND CS pulled high to 1.8 V during boot. It requires very short stubs, cold-boot requalification, and software running entirely from SRAM while selecting/configuring NAND; restore NOR settings before later NOR access. Use single-memory indirect transactions with software-selected CS2, not simultaneous dual-memory or automatic contiguous-memory extension. Added loading or a wiring fault could prevent ROM boot before the PE1 recovery guard executes. This is an alternative requiring deliberate physical selection, not an issued solder recipe.

October 18 voltage-bank follow-up: if native 1.8 V hardware quad operation without translators is the priority, investigate shared port 2 before invasive VDDIO2 isolation. It preserves hardware quad transfers and DMA, although achievable clock rate still needs measurement. Ordinary hardware SPI3 is another native-1.8 V possibility after the VDDIO4 conversion described below, but it is single-bit and does not satisfy the user's latest quad-performance requirement. No shared-bus assembly decision or physical modification has been made.

Sources: [UM3417 CN16 pin table](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf), [DS14791 XSPI features, supply banks and AF9 tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), [MB1940 sheets 2/3/4/6](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), [TI TXB0606 product](https://www.ti.com/product/TXB0606) and [datasheet electrical/application limits](https://www.ti.com/lit/gpn/TXB0606).

## Selected Arduino-header bit-bang mapping

The final October 18 decision selects this mapping. **None of the six earlier VDDIO5 signals appears on the Arduino headers.** Use **VDDIO4 at 1.8 V for four data signals and clock**, plus a main-VDD GPIO configured as **open-drain CS# with an external pull-up only to 1.8 V**. No physical rework or communication has been reported. The earlier VDDIO5 plan is retained below as historical evidence; do not combine its bank-feed/bridge instructions with this mapping.

| NAND pin | Function | Arduino marking | Header / MCU |
|---:|---|---|---|
| 1 | CS# | D10 | CN14.3 / PA3, open-drain only, 10 kΩ to 1.8 V |
| 2 | IO1 | A4 | CN4.5 / PC12 |
| 3 | IO2 / WP# | D14 / SDA | CN14.9 / PC1, 10 kΩ to 1.8 V |
| 4 | GND | GND | CN14.7 |
| 5 | IO0 | A1 | CN4.2 / PC10 |
| 6 | CLK | D15 / SCL | CN14.10 / PH9 |
| 7 | IO3 / HOLD# | A5 | CN4.6 / PH2, 10 kΩ to 1.8 V |
| 8 | VCC | — | CN12.14, nominal 1.8 V; verify before attaching NAND |

Arduino routing conditions: keep **SB2/SB4 open and SB3/SB5 closed**, the manual's default analog-header digital routing, so A4/A5 expose PC12/PH2 independently of D14/D15. Preserve **SB8**, the stock A1 digital link. Check continuity to the named MCU nets/header equivalents if the delivered board differs; A4 and D14 must not be shorted, nor A5 and D15. Analog amplifier/divider branches on A1/A4/A5 are passive loads, not 3.3 V drivers onto the NAND bus: each uses 470 kΩ/560 kΩ into a separate VDDA1V8-powered buffer, approximately 1.75 µA per high line. Their amplifier output pins are not extra independently available Arduino GPIOs. Any optional analog-buffer removal belongs in the assembly guide, not a reason to open the required digital links.

Board rework for this alternative is **remove SB24's 0 Ω link, remove R88 and R89 (the PH9/PC1 pull-ups to 3.3 V), and feed CN3.10/VDDIO4 from CN12.14**. The R88/R89 removal is essential before applying 1.8 V or attaching NAND. Leave SB23 in its stock state if the earlier modification has not been made. If VDDIO5 was already modified, record that state first; never restore a 3.3 V bridge while its external 1.8 V feed remains connected. Apply the same all-sources-off procedure, isolation checks and initial 1.71–1.89 V bank measurement as the earlier checklist, using **CN3.10** as the bank test point. The supply is still obtained from CN12, even though all six bus signals and ground are Arduino-accessible. NAND decoupling remains 100 nF plus approximately 1 µF locally.

CS firmware must preload the released state, configure PA3 open-drain with internal pull-up/pull-down disabled before enabling output, and never drive it push-pull high. The external 1.8 V pull-up provides the high level; PA3 only sinks current for selection. Allow the pull-up's measured rise time before starting another transaction. A 1.8 V high need not meet the 3.3 V GPIO input-high specification because CS is output-only: do not use its input readback as a readiness test. Its enabled input buffer can still draw additional current at this intermediate voltage; characterize that rather than assuming zero leakage. Initial VDDIO4VRSEL=0 conservative-speed operation needs no HSLV OTP change. Validate the independent supply through its monitor/ready status and VDDIO4SV before using the pins. All PC1/PC6–PC12/PH2/PH9 bank pins become 1.8 V; do not attach a 3.3 V shield to them. PE1 recovery and PD0/PE0 timing markers remain in the main domain; camera I2C2 and reset are unaffected.

Tradeoff: this achieves the user's selected physical header preference with two additional resistor removals compared with the VDDIO5 plan. Quad data spans GPIOC and GPIOH and is not contiguous, so each nibble requires more register accesses/packing than the PC2–PC5 route; the earlier timing scenarios are not measured predictions for this mapping. Throughput, rail headroom and complete-cycle energy remain to test.

Sources: [UM3417 Arduino pin assignments and SB2–SB5 routing footnote](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf), [MB1940 sheets 3/4/10](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), [ST bank-isolation guidance](https://community.st.com/stm32-mcus-boards-and-hardware-tools-26/stm32n6-nucleo-board-not-as-1v8-possible-144776), and [ST AN4899 §4.3.2, open-drain outputs and different supply voltages](https://www.st.com/resource/en/application_note/an4899-stm32-microcontroller-gpio-hardware-settings-and-lowpower-consumption-stmicroelectronics.pdf).

## Superseded: bit-banged quad SPI on VDDIO5

**Proposed October 17, selected by the user October 18:** software-generated quad SPI removes the hardware peripheral's pin restrictions. Use the six VDDIO5 GPIOs on populated **CN3**, with **SB23 opened** and the isolated bank supplied at 1.8 V through **CN3.31**. This sacrifices the Arduino-header preference but avoids the translator, the VDDIO4 pull-up changes and an unpopulated signal header. Physical modification, communication and bus-speed qualification are still pending.

### Assembly checklist

1. **Remove all board power before soldering.** Disconnect USB at CN8 and CN10, and temporarily disconnect the JS110 OUT0 recovery lead at the board so it cannot feed the unpowered MCU. Wait for the target rails to discharge. Keep the known-good CN9/BOOT jumper arrangement for reassembly.
2. **Open SB23 by removing its fitted 0 Ω link.** UM3417 defines closed SB links as 0 Ω resistors; do not cut an arbitrary PCB trace. Identify the SB23 marking on the actual board. With power removed, its bank-side pad must trace to CN3.31 and its former supply side to CN3.5 (main VDDIO). Verify no solder bridge remains and that these rails are no longer directly shorted; in-circuit semiconductor/capacitor paths need not read infinite resistance. SB24 stays fitted. The physical SB23 location has not been independently identified in a placement drawing, so no board-side/direction landmark is claimed.
3. **Add the bank supply wire: CN12.14 → CN3.31.** CN12.14 is the existing nominal 1.8 V supply measurement node. Leave R104 fitted. CN12.13/14 are both sides of a current-measurement pair, not power and ground. The new wire must be installed only after SB23 is open.
4. **Check the rails before attaching NAND.** Restore the normal power connections and measure CN3.31 relative to CN3.19: nominal 1.8 V, within **1.71–1.89 V** for the initial MCU low-speed configuration. CN3.5 should remain approximately 3.3 V. If the bank reads 3.3 V, disconnect power and resolve the bridge/wiring before connecting NAND. Power down again before the remaining assembly.
5. **Mount the LGA-8 NAND on a suitable carrier and connect the eight pins in the table below.** Use the package pin-1 marking and manufacturer's top-view drawing; underside pad order is mirrored. All listed CN3 connections are on its odd-numbered row; count from the marked pin 1, with numbers increasing by two along that row.
6. **Fit local passives at the NAND:** 100 nF ceramic plus approximately 1 µF between VCC pin 8 and GND pin 4, and three 10 kΩ pull-ups from CS# pin 1, IO2 pin 3 and IO3 pin 7 to the same 1.8 V rail. IO2/IO3 remain connected to their MCU pins; the resistors do not replace those wires. Keep clock/data wires and ground return short. A 22–47 Ω clock series resistor near CN3.17 is an optional signal-integrity provision.
7. **Restore the recovery connection and bench wiring, then report assembly complete for the API smoke test.** The installed camera image has no NAND driver yet. First test is identity/configuration and rail checks, followed by bounded scratch-block program/readback with factory bad-block markers preserved. No OTP programming is needed for initial conservative-speed operation.

Nucleo PCB rework is limited to SB23 plus the 1.8 V feed; the pull-ups and capacitors belong on the NAND carrier. Existing camera, BOOT, CN9 supply route, and other probes retain their functions. Additional NAND load and shared 1.8 V rail stability remain to be measured during operation.

| NAND pin | Function | MCU GPIO | Connection |
|---:|---|---|---|
| 1 | CS# | PE4 | **CN3.21**, with 10 kΩ pull-up to 1.8 V |
| 2 | IO1 / SO | PC3 | **CN3.25** |
| 3 | IO2 / WP# | PC4 | **CN3.13**, with 10 kΩ pull-up to 1.8 V |
| 4 | GND | — | **CN3.19** |
| 5 | IO0 / SI | PC2 | **CN3.3** |
| 6 | CLK | PC0 | **CN3.17** |
| 7 | IO3 / HOLD# | PC5 | **CN3.15**, with 10 kΩ pull-up to 1.8 V |
| 8 | VCC | — | **CN12.14**, nominal 1.8 V; verify before attaching NAND |

Feed **CN3.31 (VDDIO5)** from that same 1.8 V source **only after opening SB23 and verifying isolation from the stock 3.3 V supply with power removed**. Verify the physical bridge identity and delivered-board connections before rework. The reviewed schematic exposes these six signals as header GPIOs without additional onboard pull-ups or peripheral drivers; physical continuity has not been tested. All six belong to VDDIO5. They avoid the current camera, boot NOR, PE1 recovery and PD0/PE0 timing markers. The supply-headroom and decoupling requirements below still apply.

PC2–PC5 are consecutive bits on GPIOC: one masked input-register read obtains all four data bits, and one BSRR write can set/reset the four outputs. PC0 clock is on that same port; PE4 CS is outside the tight transfer loop. Start with conservative single-bit identification/configuration, then use quad payload transfers. Keep other GPIO bits intact.

- Alliance supports single-bit command/address phases followed by quad data: **32h Program Load x4** and **6Bh Read from Cache x4** (eight dummy clocks for the latter). This is not an assumption of all-command QPI operation.
- Set **B0.QE (bit 0)** using read-modify-write, preserving **ECC_EN (bit 4)**. IO2/IO3 are connected data lines, not hard-wired high. Keep IO3/HOLD# high during the single-bit erase, program-execute, page-read, ID and feature commands as required by the command-table note, even with QE enabled.
- Switch MCU data pins to inputs before NAND drives quad read data; after CS deassertion, allow output-disable time before driving them again. Respect setup/hold and clock timing at each transition.
- Initial slow operation can retain **VDDIO5VRSEL=0**: DS14791 specifies 1.71–1.89 V operation in its reduced-performance mode. Do not change HSLV OTP for initial bring-up. Confirm supply-valid handling and actual rail voltage; faster low-voltage pad configuration remains a separate qualification.

**Performance is unmeasured.** Software occupies the CPU during transfers and may cost more time/energy than hardware SPI/DMA. As a calculation only, a 5 MHz quad payload clock carries 2.5 MB/s, so the current 1120 × 1364 image packed to RAW10 (1,909,600 bytes) takes approximately **0.76 s** of payload transfer, plus NAND program waits, commands and metadata. Readback adds another transfer. Saving the current unpacked 16-bit buffer would take approximately 1.22 s at that hypothetical clock. Neither 5 MHz nor these total save times has been demonstrated. Begin slowly, then measure correctness, throughput and energy; keep storage work after the capture-critical startup sequence where possible. Hardware quad SPI remains a production option.

Sources: [UM3417 Rev4, Table 20, CN3 mapping](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf#page=34), [ST's SB23/VDDIO5 guidance](https://community.st.com/stm32-mcus-boards-and-hardware-tools-26/stm32n6-nucleo-board-not-as-1v8-possible-144776), [MB1940 C02 sheets 3/4/6](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), [DS14791 supply-bank and low-voltage electrical tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), and Alliance §§3, 5, 6.5, 7.2 linked under Evidence.

## Estimated time and energy penalty

October 17 follow-up: these are conditional calculations, not measured interface clocks or measured storage energy. The exact 4 Gbit part has **2048 data bytes per page**, not 4096. The current 1,909,600-byte packed frame occupies 933 data pages. Alliance Table 16-5 specifies 600 µs typical / 700 µs maximum page programming and 70 µs typical page reads (no maximum stated). Consequently, serial page programming adds **0.5598 s typical**, or 0.6531 s using the stated maximum, regardless of bus width. Full readback adds 0.06531 s of typical internal reads as well as another payload transfer.

| Assumed interface | Payload transfer | Transfer + typical programming | Including full readback, typical array times |
|---|---:|---:|---:|
| Bit-banged quad, 2 MHz | 1.910 s | 2.469 s | 4.444 s |
| Bit-banged quad, 5 MHz | 0.764 s | 1.324 s | 2.153 s |
| Bit-banged quad, 10 MHz | 0.382 s | 0.942 s | 1.389 s |
| Hardware SPI, 25 MHz | 0.611 s | 1.171 s | 1.847 s |
| Hardware SPI, 50 MHz | 0.306 s | 0.865 s | 1.236 s |
| Hardware quad SPI, 50 MHz | 0.076 s | 0.636 s | 0.778 s |

Model: `transfer = payload_bytes * 8 / (clock_hz * data_width)`; `write = transfer + pages * tPROG`; `write_and_readback = 2 * transfer + pages * (tPROG + tRD)`. Assume pre-erased slots, no cache-program/plane overlap, and equal sustained input/output clocks. Excludes command/status transactions, inter-page software/DMA gaps, packing/checksums, spare transfers, metadata/journal commits, retries, erase and acquisition. Partial final-page padding is negligible at this precision. These are not whole-operation upper bounds. Retaining the 16-bit buffer increases payload transfer by 60%, with 1492 data-page programs instead of 933.

### Hardware single-bit versus quad: October 18 follow-up

For a full 2048-byte page at a candidate 50 MHz write clock, single-bit loading takes 327.68 µs and quad loading takes 81.92 µs. Both then require the same 600 µs typical internal programming interval: 927.68 µs versus 681.92 µs total. The single-bit write is therefore about **36% longer**, or about 26.5% lower sustained write throughput, rather than four times as long. Loading accounts for about **35%** of the single-bit total and **12%** of the quad total. Single-bit transfer and typical programming time become equal at approximately **27.3 MHz**; below that, transfer dominates, and above it internal programming dominates.

For the packed 1,909,600-byte frame, the modeled save is **0.865 s single-bit at 50 MHz versus 0.636 s quad at 50 MHz**, a 0.229 s penalty. At a more conservative 25 MHz single-bit write clock it is **1.171 s**, a 0.535 s penalty relative to 50 MHz quad. Using 700 µs per-page programming instead adds 0.0933 s to each figure, leaving the absolute transfer penalty unchanged. These are storage estimates, not shutter latency or total button-to-shutdown times. Actual clocks remain unqualified. Hardware SPI can use DMA, and the CPU can sleep during the NAND busy interval in either implementation.

**Read clocks need separate qualification.** The equal-50-MHz readback row above is arithmetic, not a demonstrated or worst-case timing-compliant ordinary-SPI link. Alliance Table 16-5 gives 9.5 ns maximum clock-to-output delay; STM32 DS14791 Table 114 requires 4.5 ns controller input setup. With NAND output changing after falling SCLK and ordinary SPI sampling on rising SCLK, this consumes at least 14 ns of the half-cycle before board propagation, edge and duty-cycle margins: an ideal ceiling of about 35.7 MHz. Thus a practical candidate is 50 MHz Program Load with slower 25 MHz status/cache reads, subject pad/loading qualification. With those asymmetric clocks, modeled save plus full readback is **1.542 s**, compared with **0.778 s** for the conditional 50 MHz quad case. Read-only NAND-to-RAM time is 0.676 s at 25 MHz single-bit versus 0.142 s at 50 MHz quad, before PNG/PTP work. XSPI's sampling configuration needs its own validation; none of these figures establishes a tested bus speed.

The documented Alliance program sequence is load → execute → wait for OIP to clear. No usable cache-program overlap command or flow is established for this exact device, so do not replace the serialized sum with `max(transfer, program)` on the basis of generic cache-program wording elsewhere in the datasheet. Sources: [Alliance Rev.3.2 §§2.1, 7 and Table 16-5](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.2_Jan2026-revised.pdf), [STM32 DS14791 Table 114](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf). This comparison records the tradeoff; final D-46 selects Arduino bit-banged quad wiring, not a single-bit hardware interface.

Specific next-page-preload audit, October 18: there is **no documented supported way to load page N+1 into this AS5F14G04SND-10LIN while page N is programming**. Table 3-1 lists Program Load (02h/32h) and Program Execute (10h), but no pipelined cache-program command. The random-data load commands are restricted to Internal Data Move (§8), not a second independently loadable page. Sections 7/7.3 direct the controller to poll OIP through the program interval; the status register has no separate cache-ready indicator. Table 11-3 also lists program-cache timing-mode support as 00h/00h, supporting the conclusion but not alone proving it because several generic ONFI-style fields are zero. Section 10's isolated reference to pending cache-program operations is ambiguous and supplies no usable command sequence or timing guarantee. Treat overlap as unsupported unless Alliance provides exact-part confirmation; do not infer how an undocumented load-during-busy would behave. A successful bench attempt alone would not establish production support. MCU-side packing/checksumming of the next RAM page can overlap the current page's program wait, but its SPI transfer must still follow the supported serialized sequence. No load-during-busy experiment has been performed.

### Earlier bit-bang comparison

At the hypothetical 5 MHz bit-banged rate, the write penalty is **0.687 s versus 50 MHz hardware quad**, **0.458 s versus 50 MHz hardware SPI**, or **0.153 s versus 25 MHz hardware SPI**. Full readback approximately doubles those interface-time penalties. The flash's common programming delay explains why 10× slower payload loading produces about 2.1× total modeled save time, not 10×.

For an equal-power illustration, `extra_energy = powered_system_watts * extra_seconds`. Against hardware quad at 50 MHz, 5 MHz bit-banging adds **69 mJ at 100 mW**, **137 mJ at 200 mW**, or **344 mJ at 500 mW**. Readback approximately doubles these numbers under the same assumptions. The 100/200/500 mW values are scenarios, not qualified product-power figures. Historical bench snapshots were around 0.5 W through the JS110 path, but those are different workloads and include unresolved debugger/bypass paths; they do not establish actual NAND-cycle or battery energy.

Actual interface energy is better modeled as `P_bitbang * t_bitbang - P_hardware * t_hardware`, plus any differences in other phases and regulator losses. Bit-banging occupies the CPU during payload transfer; hardware with DMA can permit CPU sleep or useful work. **Both approaches can sleep between NAND busy-status checks**, so the common 0.56 s programming interval must not automatically be charged as extra CPU work for bit-banging. Turn off unneeded camera/receiver activity after capture in either design. Additional NAND program energy is common to both routes; NAND I/O current versus clock and real GPIO-loop CPU power still need measurement.

The user selected Arduino bit-banging in the final October 18 decision; none of these scenarios establishes its actual throughput or battery efficiency. A guarded GPIO throughput experiment can establish software clock rates without NAND attached; actual read performance and complete energy require the connected device and a qualified power boundary. Preserve the camera/recovery prefix and shared-bench ownership rules. No hardware experiment was performed for these estimates.

## Unmodified-board alternative: Arduino SPI5 with translation

Use **SPI5 on Arduino CN14**, with a **TXU0304PWR** level translator in TSSOP-14. The NAND requires 1.8 V; these Arduino signals are 3.3 V. Do not connect the four SPI signals directly. The translator provides three channels toward NAND and one returning to the MCU. Mount the NAND's 8 x 6 mm LGA-8 package on a suitable carrier. Pin numbering is shown from above; when viewing the chip's underside, the arrangement is mirrored. Identify pin 1 using the manufacturer's package drawing and marking.

| NAND pin | Function | Connection |
|---:|---|---|
| 1 | CS# | From **D10 / CN14.3 / PA3**, through translator; 10 kΩ pull-up to NAND 1.8 V |
| 2 | SO / IO1 | To **D12 / CN14.5 / PG1**, through translator |
| 3 | WP# / IO2 | 10 kΩ pull-up to NAND 1.8 V for single-bit SPI |
| 4 | GND | **CN14.7 / Arduino GND** |
| 5 | SI / IO0 | From **D11 / CN14.4 / PG2**, through translator |
| 6 | SCLK | From **D13 / CN14.6 / PE15**, through translator |
| 7 | HOLD# / IO3 | 10 kΩ pull-up to NAND 1.8 V for single-bit SPI |
| 8 | VCC | **CN12.14**, `I_SENS_VDDA1V8_N`, nominal 1.8 V with stock R104 fitted |

CN12 pins 13/14 are the 1.8 V measurement pair, not a supply/ground pair. Leave R104 and the board measurement components unchanged. Measure CN12.14 against ground before attaching NAND: it must be within the part's **1.70–1.98 V** operating range. Validate this shared rail during program/erase. U26/LD56100 is configured for 0.5 A mode; that is not 0.5 A spare capacity. NAND specifies up to 30 mA active current; existing load/headroom is unmeasured.

Fit 100 nF ceramic plus approximately 1 µF across NAND pins 8/4 close to the chip. Keep SPI wires and ground return short; initially run mode 0 at about 1 MHz, increasing only after reliable readback. A 22–47 Ω series clock resistor at the translator output is a useful provision if edges ring.

## Exact translator connections

This pin numbering is specifically **TXU0304PWR, PW/TSSOP-14**. Other packages have different numbers.

| TXU0304 pin | Name | Connection |
|---:|---|---|
| 1 | VCCA | **CN5.4**, Arduino 3.3 V |
| 14 | VCCB | Same 1.8 V supply as NAND pin 8 |
| 7 | GND | Common ground / CN14.7 |
| 2 | A1 | CN14.6 / D13 clock |
| 13 | B1Y | NAND pin 6 clock |
| 3 | A2 | CN14.4 / D11 MOSI |
| 12 | B2Y | NAND pin 5 SI |
| 4 | A3 | CN14.3 / D10 CS# |
| 11 | B3Y | NAND pin 1 CS# |
| 10 | B4 | NAND pin 2 SO |
| 5 | A4Y | CN14.5 / D12 MISO |
| 8 | OE | **CN14.1 / D8 / PD12**, with 100 kΩ pull-down to ground |
| 6, 9 | NC | Leave unconnected |

Add 100 nF at each translator supply pin to ground. OE is active high. Firmware establishes CS high and clock low, configures SPI5 and allows the rails/NAND power-up interval to settle before asserting OE. Default-low OE and the NAND-side CS pull-up keep NAND deselected during boot. Disable OE for shutdown. Supply isolation/partial-power-down behavior in the translator does not qualify the entire prototype's OFF leakage.

## Firmware and routing limits

- PE15/PG2/PG1 use **AF5** for SPI5 clock/MOSI/MISO. PA3 is software-controlled GPIO CS; PD12 controls OE. These do not overlap the current camera, boot NOR, PE1 recovery, PD0/PE0 markers or rail probes.
- Preserve the qualified boot/recovery prefix. The first storage experiment can write the already captured frame; subsequent allocation timing must honor the existing capture-integrity policy.
- Read JEDEC identity/configuration before erasing. Use an explicit scratch block, preserving factory bad-block markers. Validate program status, ECC and full readback before storing camera objects.
- **This is single-bit SPI, not hardware quad-SPI.** Arduino pins do not expose XSPIM. A later quad path is available through unpopulated CN16: CS PO0/.5, CLK PO4/.13, IO0 PP0/.3, IO1 PP1/.2, IO2 PP2/.4, IO3 PP3/.6, AF9. These are also 3.3 V on the stock board (VDDIO2). Changing headers does not remove translation. TXU0304 does not implement bidirectional quad data; that interface needs a separate design. The PN/1.8 V bank is already used by boot NOR.
- SPI5 is retained as an unmodified-board alternative for header convenience, not the selected interface or final save-speed/energy qualification. The final October 18 selection is the Arduino/VDDIO4 bit-banged quad route above.

## Alternative: a native 1.8 V GPIO bank

**October 17 follow-up:** the MCU supports 1.8 V GPIOs, but their physical supply determines the voltage; changing a voltage-range register does not change the supply. The Arduino SPI5 pins above all use main VDD (board net VDDIO). Reducing that rail would affect many camera/debug signals and their existing 3.3 V pull-ups/drivers, so it is not a contained NAND modification.

**A contained candidate is SPI3 on VDDIO4:** PC10 clock and PC12 MOSI are also Arduino A1/CN4.2 and A4/CN4.5; PC11 MISO is CN2.27 on an unpopulated header. All three have AF6. Use PC8/CN3.37 as a separate-bank GPIO CS candidate. VDDIO4 can be isolated from board VDDIO by opening SB24 and supplied at 1.8 V through CN3.10. This is a feasibility direction, not approved rework: audit the whole bank first. In particular, R88 and R89 pull PH9/PC1 to main 3.3 V and must be removed or moved to the new bank supply for 1.8 V operation. Changing only SB24 is insufficient. Main-domain camera I2C2 and debug supply would remain unchanged.

This route could eliminate the SPI translator at the cost of board rework and one unpopulated signal connection. The analog-header divider branches on PC10/PC12 are additional loads to consider during signal-integrity qualification. It still provides single-bit SPI, not hardware quad. Correct low-voltage pad configuration and startup behavior must be checked; DS14791 also specifies reduced-performance operation at 1.8 V with VRSEL=0, so initial exploration does not inherently require irreversible OTP programming. No OTP, wiring, regulator or bridge changes have been made. The original Arduino SPI5/translator proposal remains an unselected unmodified-board option; the final prototype choice is the Arduino/VDDIO4 bit-bang mapping.

Sources: [ST response on Nucleo 1.8 V domains and SB24/SB23](https://community.st.com/stm32-mcus-boards-and-hardware-tools-26/stm32n6-nucleo-board-not-as-1v8-possible-144776), [DS14791 supply/alternate-function/electrical tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), [MB1940 C02 indexed sheets 3/4/10](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf). Physical pad locations and complete delivered-board continuity remain to verify before issuing a rework recipe.

## Evidence

- [Alliance Rev.3.2, January 2026](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.2_Jan2026-revised.pdf): exact non-C device, LGA-8 top-view pinout, supply/current specifications.
- [UM3417 Rev4, Tables 16/18/21 and Figure 9](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf): header mapping, domains and measurement pair.
- [DS14791 alternate-function tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf): SPI5 AF5, XSPIM AF9 and supply banks.
- [MB1940 C02 schematic, indexed sheets 4/9](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf): CN12.14 net, R104 and U26. Physical header orientation is not inferred from text extraction.
- [TI TXU0304, Table 6-1 and functional modes](https://www.ti.com/lit/ds/symlink/txu0304.pdf), [ST LD56100](https://www.st.com/resource/en/datasheet/ld56100.pdf).
