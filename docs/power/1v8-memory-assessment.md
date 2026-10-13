# 1.8 V flash and battery power architecture

> **Historical architecture study:** the camera assumptions and supply observations below originate September 7. The [current prototype](../../spec.md) now selects CAM-6G3-073CLR/VD56G3 and four series CR2032 cells through LTC3621. Digital voltage, exact memories and downstream rails remain implementation choices; the 1.8 V recommendation is not a selected or implemented replacement. Recheck camera supplies, RTC backup and HOLD margin before adopting it.

**September 7, 2026. Proposal only; schematic and BOM unchanged.**

**NAND procurement update:** the later [supply comparison](nand-supply-options.md) recommends qualifying **Alliance AS9F14G08SA-45BIN**, a 4 Gbit, 1.8 V parallel NAND in BGA, ahead of the ISSI candidate below. The ISSI discussion is retained as the earlier TSOP option.

Moving the digital system to 1.8 V is feasible and worth pursuing. It can eliminate the battery-derived 3.3 V rail, while retaining a 2.8 V supply for camera analog power. USB still needs its own VBUS-derived 3.3 V PHY supply when connected. This is an alternative to the recovered wiring and the LTC3621-3.3 proposal, not an implemented revision.

## Flash candidates

| Function | Current part | Proposed candidate | Supply and interface | Procurement snapshot |
| --- | --- | --- | --- | --- |
| Boot NOR | W25Q128JVPIQ | **W25Q128JWPIQ TR** | 128 Mbit / 16 MiB; 1.7–1.95 V; SPI/quad SPI; 8-pad WSON 6×5 mm | DigiKey showed 23,850, approximately $4.18 at quantity 1 |
| Image NAND | MX30LF2G18AC-TI | **IS34MW02G084-TLI** | 2 Gbit / 256 MiB; 1.7–1.95 V; parallel x8 SLC; 48-pin TSOP-I | DigiKey showed 288, approximately $17.38 at quantity 1, purchase limit 96 and no backorders; Mouser showed 45 and 52-week factory lead time |

Stock is a dated distributor snapshot, not reserved inventory. The NOR is readily stocked; the NAND is obtainable for prototypes but replenishment needs qualification before production. Sources: [NOR DigiKey](https://www.digikey.com/en/products/detail/winbond-electronics/W25Q128JWPIQ-TR/12090691), [NAND DigiKey](https://www.digikey.com/en/products/detail/issi-integrated-silicon-solution-inc/IS34MW02G084-TLI/7690476), [NAND Mouser](https://www.mouser.com/ProductDetail/ISSI/IS34MW02G084-TLI?qs=YCa%2FAAYMW03redGr8SaKkQ%3D%3D).

The Winbond JW candidate retains the package class and conventional SPI boot commands. Its IQ option has QE fixed at 1, like the selected JV IQ option. Identification changes to **EF 60 18**; loader identification, dummy cycles, reset recovery and timing still require review. Its maximum advertised 133 MHz applies to the specified EBh quad-I/O read mode, not every command. The manufacturer datasheet is archived as [W25Q128JW Rev. H](../../datasheets/memory/W25Q128JW_datasheet_RevH.pdf).

The ISSI candidate retains **2048+64-byte pages, 64 pages per block, 2048 blocks and a four-bit-per-512-byte ECC requirement**. Its basic read, program, erase, status and reset commands match the existing NAND interface. That preserves the storage architecture, but does not establish a drop-in substitution. Review the full pin map, including the existing Macronix-specific PT pin 38 and extra supply/ground contacts; update device identification, FMC timing and bad-block/partial-program handling. Its 45 ns bus timing cannot inherit the faster Macronix timing configuration without review. [ISSI manufacturer-authored datasheet, pp2–3,15–20](https://www.mouser.com/datasheet/3/3722/1/34-35MW02G084-164.pdf).

The ISSI PDF was readable through web retrieval, but both the manufacturer and Mouser direct-download attempts returned HTML rather than a completed PDF. No false PDF was saved. The source link above remains usable for review.

Alternatives examined but not preferred:

- Macronix MX30UF2G18AC is a close electrical/geometry family, but the examined catalog listings had unavailable or poor stock and lifecycle concerns. MX30UF2G28AD changes to a 128-byte spare area and eight-bit ECC.
- SkyHigh S34MS02G200TFI000 has a current-looking family page, but the **exact TSOP ordering code is marked End of Life by Mouser**, with a January 2026 discontinuation notice. Do not select it based on the family page alone. Its [datasheet](../../datasheets/memory/SkyHigh_S34MS02G2_datasheet_RevH.pdf) is preserved as evaluated evidence. [Exact-part lifecycle listing](https://www.mouser.com/en/ProductDetail/SkyHigh-Memory/S34MS02G200TFI000?qs=vdiGlTBG6Jvzh%252BxyT3q0rw%3D%3D).

## Proposed voltage arrangement

```text
Battery or USB -> source selection -> 1.8 V buck
                                  |    +-> main/AON supplies
                                  |    +-> controlled AUX supplies
                                  |          +-> MCU internal SMPS -> VCORE
                                  |          +-> NOR + NAND + digital interfaces
                                  |          +-> accelerometer + camera I/O
                                  |          +-> camera core regulator -> 1.15/1.2 V
                                  |
                                  +-> controlled 2.8 V converter -> camera analog

USB VBUS only -> 3.3 V LDO -> USB PHY 3.3 V supply
Cell tap -> proposed low-Iq 1.5 V regulator -> RTC backup
Main 1.8 V -> RTC VDD and RTC bus pull-ups
```

This is a functional tree, not a complete sequenced circuit. It groups memory and interface loads for clarity; final main/AUX assignments must respect each MCU I/O bank's supply and avoid powering signals into an unpowered domain.

STM32N657 supports 1.8 V VDD and I/O-bank supplies. VBAT can also be tied to 1.8 V VDD under the datasheet's explicit tied-supply exception. ADC supplies do not require 3.3 V. Configure the relevant supply-valid, voltage-range and HSLV settings for the actual voltages. The separate 1.8 V main/AON versus AUX ordering remains necessary even though both have the same nominal voltage. [STM32 datasheet Table24](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=140), [RM0486 p395](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=395).

The camera needs **2.7–2.9 V analog**, nominal 2.8 V. A small input-to-2.8 V buck is the energy-efficient option to evaluate, with ripple/filtering and discharge designed for the sensor. A raw-pack LDO uses fewer parts but loses approximately 0.11–0.22 W at the 21 mA reference maximum across an 8–13.2 V pack; the existing TLV700 cannot accept that pack voltage. A 1.8-to-2.8 V boost is possible, but requires true output isolation/discharge so analog power can fall before core/I/O. [Camera datasheet pp16–20](https://www.st.com/resource/en/datasheet/vd55g0.pdf#page=16).

If a dual buck is selected, the new useful pair is **1.8 V and 2.8 V**. Eliminating 3.3 V does not eliminate the camera's analog conversion or the internal/core regulators.

## Changes beyond the flash chips

**RTC backup:** RV-3028 can communicate at 1.8 V using 100 kHz I2C, but directly retaining its approximately 3 V backup cell would keep backup selected and disable I2C. One coherent proposal is cell tap -> very-low-Iq 1.5 V regulator -> VBACKUP, main 1.8 V -> VDD, and direct switching mode (DSM). Check regulator tolerance, shutdown/reverse leakage and guaranteed ground current at the RTC's tiny load; the backup regulator has not been selected. Keep charging disabled for the primary cell. This avoids adding an I2C level translator. [RTC manual pp45–47,97–98](../../datasheets/sensors_timing/RV-3028-C8_application_manual.pdf).

**Power hold:** the previous 3.3 V GPIO -> BAS116 -> RUN design does not retain its guaranteed voltage margin when the GPIO becomes 1.8 V. The earlier conservative assumptions give only `1.8 − 0.4 − 0.9 = 0.5 V`, below the LTC3621 RUN-high requirement. Select an enable/hold interface that explicitly supports 1.8 V logic; retaining a bulk 3.3 V rail is not necessary just for this signal.

**Indicator and pull-ups:** the current LED has about 1.9 V typical forward drop, so useful brightness at 1.8 V is not established. It can use a separately driven 2.8 V branch or be replaced. If sharing the 2.8 V converter, isolate/filter the camera branch from LED transitions. Move bus pull-ups and debug voltage reference to their actual 1.8 V domains.

Lower signal voltage reduces capacitive I/O switching energy: at unchanged capacitance and activity, `(1.8/3.3)^2 ≈ 0.30`, approximately a 70% reduction in that contribution. This is not a claim of 70% lower total system energy. Flash array programming, CPU core power, camera power and regulator losses must be budgeted separately. The flash and former 3.3 V digital loads also move onto the 1.8 V converter, so the [previous current budget](current-budget.md) must be revised before choosing its current rating. The <1 µA whole-board OFF target remains unqualified.

**Recommendation:** pursue the 1.8 V digital architecture with the Winbond NOR and the later [Alliance NAND candidate](nand-supply-options.md). Complete the NAND footprint/ECC/timing review, qualify procurement, and integrate the RTC and hold-interface changes before replacing the schematic's power tree.
