# SD breakout comparison: four-bit hardware SDMMC2

**Selected October 19, 2026:** use the STM32's **SDMMC2 peripheral in native four-bit SD mode**, with hardware CRC and internal DMA available. This is the SD-card interface corresponding to the user's request for hardware "QSPI"; SD cards do not implement the quad-SPI NAND command protocol. **This replaces the earlier Arduino SPI5/four-direct-pin/two-wire plan.** Do not combine those connections with this plan.

The user confirms the configurable GPIO banks are **still at 3.3 V**; the planned NAND voltage conversion has not been applied. D2 and R23 were previously reported removed. This selects the SD comparison interface, not a final replacement of the NAND storage architecture. No SD driver has been installed and no card measurements have been made.

## Current connection plan

Use short jumper wires to **CN3's odd-numbered row** for all six signals and ground, plus Arduino **CN5.4 / 3V3** for power. Count CN3 from its marked pin 1 in steps of two. All six signals use **AF11** and belong to **VDDIO5**, which must remain at **3.3 V** with stock **SB23 fitted**. Do not apply the historical 1.8 V VDDIO5 NAND conversion. No Nucleo soldering, bank change or AREF jumper is needed.

| SD breakout connection | Native SD function | Nucleo connection | MCU |
|---|---|---|---|
| **SCK** header pad | Clock | **CN3 pin 3** | PC2 / SDMMC2_CK |
| **DI** header pad | Command/response | **CN3 pin 25** | PC3 / SDMMC2_CMD |
| **DO** header pad | Data bit 0 | **CN3 pin 13** | PC4 / SDMMC2_D0 |
| **Added wire: microSD socket contact 8** | Data bit 1 | **CN3 pin 15** | PC5 / SDMMC2_D1 |
| **Added wire: microSD socket contact 1** | Data bit 2 | **CN3 pin 17** | PC0 / SDMMC2_D2 |
| **CS** header pad | Data bit 3 | **CN3 pin 21** | PE4 / SDMMC2_D3 |
| **VCC** header pad | 3.3 V power | **CN5 pin 4 / 3V3** | Supply, not a GPIO |
| **GND** header pad | Ground | **CN3 pin 19** | Ground |
| **CD** header pad | Mechanical card detect | **Leave disconnected** | Unneeded initially |

```text
Breakout/socket                 Nucleo

SCK   (CLK) ------------------- CN3.3   PC2
DI    (CMD) ------------------- CN3.25  PC3
DO    (DAT0) ------------------ CN3.13  PC4
socket contact 8 (DAT1) ------- CN3.15  PC5  [additional solder wire]
socket contact 1 (DAT2) ------- CN3.17  PC0  [additional solder wire]
CS    (DAT3) ------------------ CN3.21  PE4
GND -------------------------- CN3.19
VCC -------------------------- CN5.4   3V3
CD    unconnected
```

**CS is now a bidirectional data line, not a GPIO chip select.** DI/CMD and all four DAT lines must support both directions. Do not hold CS/DAT3 HIGH with a push-pull GPIO or initialize this wiring with the earlier SPI driver. CLK is the only host-only signal.

There is no complete Arduino-only four-bit SD mapping: SDMMC2 DAT1 is available on PC5 or PG8, neither on Arduino; PG8 also drives the blue phase LED. SDMMC1 DAT1 is PC9, also absent from Arduino, and the natural SDMMC1 group overlaps the camera controls. The selected CN3 route avoids the camera, boot NOR, PE1 recovery, PD0/PE0 timing markers and PG0/PG8/PG10 phase LEDs. C02 ODB connectivity shows each of the six selected nets connects only the MCU and its CN3 contact.

## Two additional contacts on the breakout

The photo's seven pads are `CD DO GND SCK VCC DI CS`. **That header alone cannot carry four-bit SD**, because it lacks DAT1 and DAT2. The photo resembles SparkFun's passive microSD Transflash breakout, but does not establish the exact board/socket revision or expose enough of the solder-contact row to mark the two physical pads safely.

In the matching published SparkFun schematic and board files:

- MicroSD socket **contact 1 = DAT2**, named `NC` in the SPI-oriented schematic.
- MicroSD socket **contact 8 = DAT1**, named `RSV` in that schematic.
- Neither contact is connected to a PCB net or tied to ground.
- Header **CS goes to socket contact 2 / DAT3**. Header **CD goes to the mechanical detect switch**; CD is not an extra data line.

Thus two fine wires from the actual DAT1/DAT2 solder pads can make that design usable. **Contact numbers here are the standard microSD electrical numbering, not an instruction to count visible solder joints from the left or right.** Socket mounting orientation, shield tabs and detect contacts must be checked on the user's board. Confirm the pads from its actual connector layout/continuity with power and card removed before soldering. No trace cut is indicated by the reference SparkFun design. Physical DAT1/DAT2 solder locations on the user's module remain to be identified from a clear socket-tail/backside view or continuity evidence.

If those contacts are inaccessible, use a passive breakout exposing **CLK, CMD and DAT0-DAT3**, such as [Adafruit 4682](https://www.adafruit.com/product/4682). The same Nucleo table applies by native signal name. This is a fallback, not a purchase or a claim that the existing module is unusable.

## Supply, pull-ups and initial firmware setup

Use **3.3 V power and signaling**. Keep the socket's approximately **100 nF plus 10 microfarads** local decoupling. Check actual voltage and card-write droop; spare regulator current and the particular card's peak current are not yet measured. Keep the six signal wires short, with a nearby ground return. A 22-33 ohm series resistor at the MCU end of CLK is an optional provision for ringing; bus speed will be raised only after reliable reads.

For the initial bench test, retain the internal-pull-up approach, now on **CMD and all four DAT lines**. STM32's specified 30-50 kilohm pull-ups fall within the cited card-interface 10-100 kilohm range. Configure them as digital inputs with pull-ups early, establish a non-floating clock, allow settling, then select AF11 with pulls retained. Start native identification at **100 kHz** and initially one-bit width, then negotiate four-bit operation with the card before changing host width. Hardware actively drives data during transfers; the weak pull-ups do not generate the high-speed data edges.

This is an experimental convenience, not a reset-time guarantee: GPIO pull-ups are disabled in reset analog mode, and the card's own startup pull-up covers **DAT3 only**, not CMD/DAT0/DAT1/DAT2. **Five external 10 kilohm pull-ups**, one from each CMD/DAT0-DAT3 line to card 3.3 V, are the more robust option for defined levels before firmware and during reset. No external resistor is mandated for this initial experiment, but startup/readback qualification must include that limitation. Do not copy the superseded PA3 push-pull-CS setup into this native-SD driver. Avoid disabling the card's own DAT3 pull-up in the initial experiment.

Do not request the UHS **1.8 V signaling switch**: this bench wiring stays at 3.3 V. Candidate operating points are 25 MHz default speed and, only after supported card mode selection and link/readback qualification, 50 MHz High Speed. Jumper wiring does not establish either clock as reliable. If the card was previously put into SPI mode, power-cycle the card before native-SD initialization; resetting only the MCU is insufficient.

Disconnect board power and the external recovery drive while soldering. Remove any prior Arduino SPI connections before installing these wires; the breakout must not remain plugged into the earlier four-pin arrangement. Restore the previously working power/recovery setup afterward. Keep CN10 independently powered for development with D2 removed. Recheck bench ownership, supply routing, recovery selection and probe operation before automated power control. The last confirmed CN8/CN9 target route bypassed JS110; this document does not assert that has changed. Preserve the qualified recovery guard in any subsequent firmware.

## What the comparison can establish

The selected test now uses four-bit **hardware SDMMC2**, not bit-banging or SPI5. Firmware, DMA/cache handling, card status/completion checks and verified clock rates remain to implement.

The current captured image is **1120 x 1364**, or **1,909,600 bytes packed RAW10**. It occupies 3,730 SD sectors when padded to 512-byte boundaries (1,909,760 bytes), or 933 Alliance data pages. The existing 16-bit RAM buffer is 3,055,360 bytes; saving that buffer instead adds 60% to the payload and is not a fair comparison with packed-RAW10 NAND estimates. The specification's 1124-pixel-wide image is a separate 1,916,420-byte workload.

| Conditional model for current packed image | Time |
|---|---:|
| **Selected four-bit SD payload alone at 25 MHz** | **0.153 s** |
| **Selected four-bit SD payload alone at 50 MHz** | **0.076 s** |
| Superseded single-bit SPI payload alone at 25 MHz | 0.611 s |
| Superseded single-bit SPI payload alone at 50 MHz | 0.306 s |
| Selected bit-banged quad NAND, hypothetical 5 MHz, including typical array program time | 1.324 s |
| Hardware quad NAND at hypothetical 50 MHz, including typical array program time | 0.636 s |

The SD entries exclude initialization, protocol overhead, card busy/maintenance intervals, metadata, synchronization and readback. NAND entries also exclude commands, packing, metadata, erase, verification and acquisition. NAND's 933 sequential programs add 0.5598 seconds at the documented 600-microsecond typical page time. None of these rows is a measured total save time. Four-bit SD has four times the payload bandwidth of single-bit SPI at the same clock, not a guaranteed fourfold reduction in complete-save time.

The first useful test sequence is:

1. Read card identity/capacity and verify non-destructive reads. Record actual interface clock and card identity.
2. Write an image-sized pseudorandom payload to a **new test file**, or an **explicitly authorized disposable sector range**. Do not format, overwrite unknown files or treat apparently empty sectors as safe without allocation knowledge. No destructive test is authorized yet.
3. Measure initialization, payload transfer, intermediate/final busy waits, status/synchronization completion and checksum readback separately. Use multi-block transfers and include the file/allocation work when testing a filesystem. DMA completion alone is not durable completion; honor the card's enabled cache and completion requirements.
4. Repeat 20-50 operations for a preliminary median/range. Measure genuine cold card starts once autonomous power cycling has been reverified, then check saved data after a fresh power cycle. Keep initialization off the capture-critical path where possible so storage does not delay exposure.
5. Measure complete-cycle energy and current peaks only after the JS110 measurement boundary is restored and checked. The prior debugger/CN8 bypass audit remains relevant. Timing results can be useful before precision energy is available.

This quick experiment cannot qualify ten-year unpowered retention, the accepted reuse requirement or preservation of older photos through interrupted SD-controller updates. Those remain part/card-specific qualification work if SD is adopted. A one-bit native identification/read check is a useful bring-up stage; it is not the final four-bit performance comparison.

## Evidence

- [ST MB1940 C02 schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf) and [UM3417 Table20](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf), CN3 mapping and CN5.4 supply. C02 ODB connectivity independently confirms all six MCU/header nets and absence of other component connections.
- [STM32N657 DS14791](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), Rev10 Table20, pages126/128: selected PC/PE pins use AF11 for SDMMC2; Table67 gives pull-up resistance.
- [ST AN5967](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf), VDDIO5 includes PC0, PC2-PC5 and PE4; section14.4.1 provides SDMMC signal-layout and pull-up guidance.
- [STM32 RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), sections15.3.1/15.3.12 and GPIO reset values; [Nexperia AN10911](https://assets.nexperia.com/documents/application-note/AN10911.pdf), pages5/18, SD DAT3/CS mapping and card-internal power-up pull-up.
- [SparkFun microSD Transflash breakout](https://www.sparkfun.com/sparkfun-microsd-transflash-breakout.html), its [schematic source](https://github.com/sparkfun/microSD_Transflash_Breakout/blob/master/Hardware/SparkFun_microSD_Breakout.sch) and [board source](https://github.com/sparkfun/microSD_Transflash_Breakout/blob/master/Hardware/SparkFun_microSD_Breakout.brd), U1 socket pad connectivity. These are matching design references, not proof of the user's module's identity.
- [ATP microSD datasheet, Table4-4](https://advdownload.advantech.com/productfile/PIS/96FMSD-8G-CM-AT/file/96FMSD-8G-CM-AT_datasheet20200330122023.pdf), CMD/DAT pull-up range; [SD Association specification index](https://www.sdcard.org/downloads/pls/) for the governing protocol.
- [Existing Alliance timing calculations](alliance-nand-wiring.md#estimated-time-and-energy-penalty), [storage architecture comparison](../../reports/Camera%20storage%20architecture%20alternatives.md), and [debugger/power audit](../power/nucleo-debug-isolation.md).
