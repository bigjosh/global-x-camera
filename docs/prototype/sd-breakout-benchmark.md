# SD breakout comparison experiment

October 19, 2026. The user proposed trying the pictured seven-pad SD breakout before deciding whether to switch storage. The user confirms that the configurable GPIO banks are **still at 3.3 V**; the planned NAND VDDIO4 conversion has not been applied. D2 and R23 were previously reported removed. This is an experiment proposal, not a replacement of the selected NAND architecture. No SD firmware has been installed and no card measurement has been made.

## Connection with four direct pins and two wires

The photo's pad order is `CD DO GND SCK VCC DI CS`. It resembles SparkFun's passive microSD Transflash breakout; its exact manufacturer/revision and the card model/capacity are not established. The matching SparkFun schematic has direct socket connections without a regulator, level translator, pull-ups or decoupling. Use a **3.3 V supply and 3.3 V signals**, subject to confirming the actual board's connections. Do not power a card from a GPIO or from the proposed 1.8 V NAND supply.

There is **no correct fully populated seven-pin direct-plug alignment** on the Arduino headers. However, reversing the row over CN14 pins 3 through 9 aligns four contacts exactly for hardware SPI5:

```text
CN14 pin, ascending:   3      4      5      6      7      8      9
Arduino label:        D10    D11    D12    D13    GND    AREF   SDA
SD pad above it:      CS     DI     VCC    SCK    GND    DO     CD
Fit a header pin?    YES    YES     NO    YES    YES     NO     NO
```

Fit **two separate two-pin male header sections**, one at CS/DI and the other at SCK/GND. Leave VCC, DO and CD without mating pins. Align by the actual silkscreen labels; the diagram is a signal-order diagram, not a promise of which way the module body faces. Dry-fit the module for clearance from the camera, other connectors and its own card-removal path before soldering. No Nucleo trace cuts, bank conversion or AREF jumper are needed.

| SD board pad | Connection | MCU function |
|---|---|---|
| CS | Direct to **D10 / CN14.3** | PA3, software chip select |
| DI | Direct to **D11 / CN14.4** | PG2, AF5 SPI5_MOSI |
| SCK | Direct to **D13 / CN14.6** | PE15, AF5 SPI5_SCK |
| GND | Direct to **CN14.7** | Board ground through fitted SB25 |
| VCC | Short wire to **CN5.4 / Arduino 3V3** | Target 3.3 V supply |
| DO | Short wire to **CN15.13** | PG1, AF5 SPI5_MISO; identical net to D12/CN14.5 |
| CD | Leave disconnected | Card-detect contact is unnecessary initially |

CN15.13 avoids trying to access CN14.5 underneath the breakout. **Do not fit a pin beneath VCC:** it would connect card power to MCU MISO/PG1. Likewise leave DO clear of AREF and leave CD unconnected. A normal seven-pin strip is not safe in this alignment. If physical clearance is unsuitable, use six short jumper wires with the same electrical mapping; DO can instead use CN14.5 when accessible.

For this passive breakout, fit approximately **100 nF plus 10 microfarads** across VCC/GND near the socket. **October 19 follow-up: the external 10 kilohm CS pull-up can be omitted for this bench test; use PA3's internal pull-up and actively drive CS during SPI operations.** The planned driver must enable GPIOA access, configure PA3 as a digital input with pull-up (not analog mode), preload its output latch HIGH through BSRR, then select push-pull output before generating any SPI clocks. The pull-up biases an undriven input; it is not used to generate the normal high-speed CS edges. This sequencing is a firmware requirement, not an implemented/tested result yet.

STM32's pull-up is 30-50 kilohms (DS14791 Table67). It is not available as a reset-time guarantee: PA3 resets to analog mode, which disables the pull-up (RM0486 sections15.3.1/15.3.12). SD cards provide their own DAT3/CS pull-up at power-up; retain that default and do not disable it through ACMD42 in this experiment. A card that remains powered after software disables its own pull-up is a different reset case. An external resistor remains an optional fallback if reset/startup measurements show a problem. Keep leads short, establish mode-0 clock/CS levels before initialization, and check supply droop as clock/write load increases. The capacitors are initial prototype provisions, not a qualified current-transient design. D13 also drives the Arduino LED through Q4/SB18, adding load and measurement overhead; it does not prevent using SPI5. Actual link speed remains to be tested.

Disconnect board power and the external recovery drive while soldering. Restore the previously working power/recovery setup afterward. Keep the separate ST-LINK supply connected for development with D2 removed. Recheck bench ownership, actual supply routing, recovery selection and probe operation before using automated power control. The last confirmed CN8/CN9 target route bypassed JS110; this document does not assert that has changed.

## What the comparison can establish

Hardware SPI5 is available on these pins; bit-banging is unnecessary. Start identification at no more than 400 kHz, then test faster clocks with complete readback. Treat 25 MHz as a candidate, not a demonstrated clock. Use 50 MHz only after supported card-mode selection and timing/link qualification. An advertised UHS card speed does not establish SPI performance.

The current captured image is **1120 x 1364**, or **1,909,600 bytes packed RAW10**. It occupies 3,730 SD sectors when padded to 512-byte boundaries (1,909,760 bytes), or 933 Alliance data pages. The existing 16-bit RAM buffer is 3,055,360 bytes; saving that buffer instead adds 60% to the payload and is not a fair comparison with packed-RAW10 NAND estimates. The specification's 1124-pixel-wide image is a separate 1,916,420-byte workload.

| Conditional model for current packed image | Time |
|---|---:|
| SD SPI payload alone at 25 MHz | 0.611 s |
| SD SPI payload alone at 50 MHz | 0.306 s |
| Selected bit-banged quad NAND, hypothetical 5 MHz, including typical array program time | 1.324 s |
| Hardware quad NAND at hypothetical 50 MHz, including typical array program time | 0.636 s |

The SD entries exclude initialization, protocol overhead, card busy/maintenance intervals, metadata, synchronization and readback. NAND entries also exclude commands, packing, metadata, erase, verification and acquisition. NAND's 933 sequential programs add 0.5598 seconds at the documented 600-microsecond typical page time. None of these rows is a measured total save time. SD could beat the selected software-driven NAND path; a narrower bus alone does not establish a loss.

The first useful test sequence is:

1. Read card identity/capacity and verify non-destructive reads. Record actual interface clock and card identity.
2. Write an image-sized pseudorandom payload to a **new test file**, or an **explicitly authorized disposable sector range**. Do not format, overwrite unknown files or treat apparently empty sectors as safe without allocation knowledge. No destructive test is authorized yet.
3. Measure initialization, payload transfer, intermediate/final busy waits, status/synchronization completion and checksum readback separately. Use multi-block transfers and include the file/allocation work when testing a filesystem. DMA completion alone is not durable completion; honor the card's enabled cache and completion requirements.
4. Repeat 20-50 operations for a preliminary median/range. Measure genuine cold card starts once autonomous power cycling has been reverified, then check saved data after a fresh power cycle. Keep initialization off the capture-critical path where possible so storage does not delay exposure.
5. Measure complete-cycle energy and current peaks only after the JS110 measurement boundary is restored and checked. The prior debugger/CN8 bypass audit remains relevant. Timing results can be useful before precision energy is available.

This quick experiment cannot qualify ten-year unpowered retention, the accepted reuse requirement or preservation of older photos through interrupted SD-controller updates. Those remain part/card-specific qualification work if SD is adopted. The seven-pin breakout also does not expose the two extra data signals needed for four-bit SDMMC; a later four-bit carrier is a different performance comparison. One-bit native SDMMC is possible in principle with verified passive wiring but provides no four-bit payload advantage and is not needed for this Arduino SPI test.

## Evidence

- [ST MB1940 C02 schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), Arduino sheet 10; CN14 pin roles, CN5.4 supply, and LED loading. C02 ODB connectivity independently confirms PG1 at both CN14.5 and CN15.13.
- [STM32N657 DS14791](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), Rev10 Table19: PE15 SPI5_SCK AF5 (page117), PG1 SPI5_MISO and PG2 SPI5_MOSI AF5 (page119).
- [STM32 RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), sections15.3.1/15.3.12 and GPIOA reset values; [Nexperia AN10911](https://assets.nexperia.com/documents/application-note/AN10911.pdf), pages5/18, SD DAT3/CS mapping and card-internal power-up pull-up.
- [SparkFun microSD Transflash breakout](https://www.sparkfun.com/sparkfun-microsd-transflash-breakout.html) and its [published schematic source](https://github.com/sparkfun/microSD_Transflash_Breakout/blob/master/Hardware/SparkFun_microSD_Breakout.sch). This is a matching design reference, not proof of the user's module's identity.
- [ADI AN-1443](https://www.analog.com/en/resources/app-notes/an-1443.html), SPI signal roles and initialization-clock guidance; [SD Association specifications](https://www.sdcard.org/downloads/pls/) for card initialization, bus modes and completion rules.
- [Existing Alliance timing calculations](alliance-nand-wiring.md#estimated-time-and-energy-penalty), [storage architecture comparison](../../reports/Camera%20storage%20architecture%20alternatives.md), and [debugger/power audit](../power/nucleo-debug-isolation.md).
