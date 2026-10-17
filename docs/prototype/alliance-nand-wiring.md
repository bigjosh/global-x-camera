# Alliance NAND wiring for the Nucleo prototype

October 17, 2026. **D-46 selects AS5F14G04SND-10LIN for prototype storage bring-up.** The user strongly prefers Arduino headers, then connections nearer ST-LINK. This is a reviewed wiring proposal, not completed assembly or successful NAND communication. Power characterization is deferred; camera firmware and existing instrument/recovery wiring were not changed.

## Recommended candidate: bit-banged quad SPI on VDDIO5

**October 17 follow-up:** software-generated quad SPI removes the hardware peripheral's pin restrictions. The recommended candidate now uses the six VDDIO5 GPIOs on populated **CN3**, with **SB23 opened** and the isolated bank supplied at 1.8 V through **CN3.31**. It sacrifices the Arduino-header preference but avoids the translator, the VDDIO4 pull-up changes and an unpopulated signal header. This remains a reviewed proposal, not an approved/performed modification or a measured bus-speed result.

| NAND pin | Function | MCU GPIO | Connection |
|---:|---|---|---|
| 1 | CS# | PE4 | **CN3.21**, with 10 kΩ pull-up to 1.8 V |
| 2 | IO1 / SO | PC3 | **CN3.25** |
| 3 | IO2 / WP# | PC4 | **CN3.13**, with 10 kΩ pull-up to 1.8 V |
| 4 | GND | — | **CN3.19** |
| 5 | IO0 / SI | PC2 | **CN3.3** |
| 6 | CLK | PC0 | **CN3.17** |
| 7 | IO3 / HOLD# | PC5 | **CN3.15**, with 10 kΩ pull-up to 1.8 V |
| 8 | VCC | — | **CN12.14**, verified nominal 1.8 V |

Feed **CN3.31 (VDDIO5)** from that same 1.8 V source **only after opening SB23 and verifying isolation from the stock 3.3 V supply with power removed**. Verify the physical bridge identity and delivered-board connections before rework. The reviewed schematic exposes these six signals as header GPIOs without additional onboard pull-ups or peripheral drivers; physical continuity has not been tested. All six belong to VDDIO5. They avoid the current camera, boot NOR, PE1 recovery and PD0/PE0 timing markers. The supply-headroom and decoupling requirements below still apply.

PC2–PC5 are consecutive bits on GPIOC: one masked input-register read obtains all four data bits, and one BSRR write can set/reset the four outputs. PC0 clock is on that same port; PE4 CS is outside the tight transfer loop. Start with conservative single-bit identification/configuration, then use quad payload transfers. Keep other GPIO bits intact.

- Alliance supports single-bit command/address phases followed by quad data: **32h Program Load x4** and **6Bh Read from Cache x4** (eight dummy clocks for the latter). This is not an assumption of all-command QPI operation.
- Set **B0.QE (bit 0)** using read-modify-write, preserving **ECC_EN (bit 4)**. IO2/IO3 are connected data lines, not hard-wired high. Keep IO3/HOLD# high during the single-bit erase, program-execute, page-read, ID and feature commands as required by the command-table note, even with QE enabled.
- Switch MCU data pins to inputs before NAND drives quad read data; after CS deassertion, allow output-disable time before driving them again. Respect setup/hold and clock timing at each transition.
- Initial slow operation can retain **VDDIO5VRSEL=0**: DS14791 specifies 1.71–1.89 V operation in its reduced-performance mode. Do not change HSLV OTP for initial bring-up. Confirm supply-valid handling and actual rail voltage; faster low-voltage pad configuration remains a separate qualification.

**Performance is unmeasured.** Software occupies the CPU during transfers and may cost more time/energy than hardware SPI/DMA. As a calculation only, a 5 MHz quad payload clock carries 2.5 MB/s, so the current 1120 × 1364 image packed to RAW10 (1,909,600 bytes) takes approximately **0.76 s** of payload transfer, plus NAND program waits, commands and metadata. Readback adds another transfer. Saving the current unpacked 16-bit buffer would take approximately 1.22 s at that hypothetical clock. Neither 5 MHz nor these total save times has been demonstrated. Begin slowly, then measure correctness, throughput and energy; keep storage work after the capture-critical startup sequence where possible. Hardware quad SPI remains a production option.

Sources: [UM3417 Rev4, Table 20, CN3 mapping](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf#page=34), [ST's SB23/VDDIO5 guidance](https://community.st.com/stm32-mcus-boards-and-hardware-tools-26/stm32n6-nucleo-board-not-as-1v8-possible-144776), [MB1940 C02 sheets 3/4/6](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), [DS14791 supply-bank and low-voltage electrical tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), and Alliance §§3, 5, 6.5, 7.2 linked under Evidence.

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
- SPI5 is proposed for header convenience, not final save-speed/energy qualification. The NAND choice is approved; the interface remains a proposal.

## Alternative: a native 1.8 V GPIO bank

**October 17 follow-up:** the MCU supports 1.8 V GPIOs, but their physical supply determines the voltage; changing a voltage-range register does not change the supply. The Arduino SPI5 pins above all use main VDD (board net VDDIO). Reducing that rail would affect many camera/debug signals and their existing 3.3 V pull-ups/drivers, so it is not a contained NAND modification.

**A contained candidate is SPI3 on VDDIO4:** PC10 clock and PC12 MOSI are also Arduino A1/CN4.2 and A4/CN4.5; PC11 MISO is CN2.27 on an unpopulated header. All three have AF6. Use PC8/CN3.37 as a separate-bank GPIO CS candidate. VDDIO4 can be isolated from board VDDIO by opening SB24 and supplied at 1.8 V through CN3.10. This is a feasibility direction, not approved rework: audit the whole bank first. In particular, R88 and R89 pull PH9/PC1 to main 3.3 V and must be removed or moved to the new bank supply for 1.8 V operation. Changing only SB24 is insufficient. Main-domain camera I2C2 and debug supply would remain unchanged.

This route could eliminate the SPI translator at the cost of board rework and one unpopulated signal connection. The analog-header divider branches on PC10/PC12 are additional loads to consider during signal-integrity qualification. It still provides single-bit SPI, not hardware quad. Correct low-voltage pad configuration and startup behavior must be checked; DS14791 also specifies reduced-performance operation at 1.8 V with VRSEL=0, so initial exploration does not inherently require irreversible OTP programming. No OTP, wiring, regulator or bridge changes have been made. The original Arduino SPI5/translator proposal remains the unmodified-board option.

Sources: [ST response on Nucleo 1.8 V domains and SB24/SB23](https://community.st.com/stm32-mcus-boards-and-hardware-tools-26/stm32n6-nucleo-board-not-as-1v8-possible-144776), [DS14791 supply/alternate-function/electrical tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), [MB1940 C02 indexed sheets 3/4/10](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf). Physical pad locations and complete delivered-board continuity remain to verify before issuing a rework recipe.

## Evidence

- [Alliance Rev.3.2, January 2026](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.2_Jan2026-revised.pdf): exact non-C device, LGA-8 top-view pinout, supply/current specifications.
- [UM3417 Rev4, Tables 16/18/21 and Figure 9](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf): header mapping, domains and measurement pair.
- [DS14791 alternate-function tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf): SPI5 AF5, XSPIM AF9 and supply banks.
- [MB1940 C02 schematic, indexed sheets 4/9](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf): CN12.14 net, R104 and U26. Physical header orientation is not inferred from text extraction.
- [TI TXU0304, Table 6-1 and functional modes](https://www.ti.com/lit/ds/symlink/txu0304.pdf), [ST LD56100](https://www.st.com/resource/en/datasheet/ld56100.pdf).
