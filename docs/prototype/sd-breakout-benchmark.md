# SD breakout wiring and comparison

## October 24 replacement: Pzsmocn PZSSD001 full-pin breakout

The user selected [Amazon B08FB3GC34](https://www.amazon.com/dp/B08FB3GC34),
identified as **Pzsmocn PZSSD001**, to replace the seven-pin carrier. This is the
requested wiring plan; physical installation and four-bit operation have **not**
been confirmed. The installed v18 RAW-slot firmware still uses **one-bit native
SDMMC2 at 3.3 V**. Current firmware and qualified measurements are tracked in
[the RAW capture README](../../firmware/capture-raw/README.md); the October 19–20
status statements below are historical.

Move the existing wires at the breakout end only. New-board pin numbers follow
[the supplier's pin diagram](https://www.cqrobot.com/image/cache/catalog/Pzsmocn/PZSSD001/PZSSD001-2-550x550.jpg)
for [PZSSD001](https://cqrobot.com/product/PZSSD001); use the printed labels to
avoid reversing the header when viewed from the solder side.

| Wire from old breakout | New breakout label | New pin | Existing Nucleo end |
|---|---|---:|---|
| SCK | CLK | 5 | CN3.3 / PC2 |
| DI | CMD | 4 | CN3.25 / PC3 |
| DO | D0 (data zero) | 3 | CN3.13 / PC4 |
| CS | D3 | 6 | CN3.21 / PE4 |
| VCC | 3.3V | 1 | CN5.4 / 3V3 |
| GND | GND | 2 | CN3.19 |
| CD (previously unused) | CD | 9 | Leave disconnected |

Add two wires for the forthcoming four-bit mode:

| New breakout label | New pin | Nucleo end | Peripheral function |
|---|---:|---|---|
| D1 | 8 | CN3.15 / PC5 | SDMMC2_D1 / AF11 |
| D2 | 7 | CN3.17 / PC0 | SDMMC2_D2 / AF11 |

The old CS wire already supplies the fourth data connection, D3. CD is the
mechanical detect switch and remains unused. Preserve the 3.3 V VDDIO5 bank
and SB23; no voltage conversion or Nucleo solder modification is needed.
Power down before moving the supply and signal wires. Keep the leads short
and retain socket decoupling.

Four-bit operation requires a separately tested firmware change: configure
PC0/PC5/PE4 as AF11 with appropriate CMD/data pull-ups, check the card's supported
width, and negotiate matching card/controller width. The installed one-bit
firmware instead leaves PE4 as an input/pull-up and does not configure the two
new data pins. Its operation on this replacement carrier remains to smoke-test.
The module listing/pin diagram does not qualify the delivered board's reset-time
pull-up/decoupling network; check that during bring-up. This interface is native
four-bit SDMMC, not QSPI.

The user confirmed the old carrier was intact and the **SanDisk Extreme 32 GB
three-cycle baseline is complete** on that carrier, unchanged v18, one-bit
25 MHz. Median current onset to confirmed Standby plateau: **882.627 ms /
450.788 mJ** on the JS-fed board branch; median payload-to-ready: **632.854 ms**.
All three slots were read back and decoded; frames were near black. See
[the measurements and comparison](../../firmware/capture-raw/evidence/2026-10-24-sandisk-extreme32/README.md).
The explicit test-card reset/erase permission was used before these runs. The
replacement carrier and four-bit firmware have not been tested yet. The target
was left powered in an idle RAM READ park after retrieval; power down before
rewiring, then recheck ownership and connections before the next experiment.

## Historical one-bit bring-up record


**Latest follow-up, October 20:** D-49 now authorizes capture → PNG16 → FAT32 on this card, with compression tuned for total time/energy and power-loss protection unqualified. The [new software](../../firmware/capture-sd/README.md) is offline-tested only. Following a normal boot, MCU debug access could not be restored through the measured VCP requests; a BOOT1 development-mode change is pending. V45b is unchanged in NOR, and no SD write/format was performed. The previous awake-park statement below is historical. See the [current checkpoint](../decisions/capture-png-sd-2026-10-20.md) before bench work.

**October 20 measured checkpoint:** the [read-only SD smoke helper v3](../../firmware/sd-smoke/README.md) passed two reads at 100 kHz and a subsequent six-read check across **100 kHz, 12.5 MHz and 25 MHz**, with byte-identical data and no data CRC errors. Three early attempts timed out at CMD8 despite the first wiring correction; a second user correction allowed card identification. V2 then exposed a software completion bug: v3 accepts DATAEND with an idle transfer, all 128 words and no errors, without requiring DBCKEND. The card reports **62,723,719,168 bytes (62.723719168 GB)**; this is reported capacity, not a full-capacity validation. No SD write or erase was attempted. Write performance, sustained throughput, complete-save latency and energy remain unmeasured.

The [v45b ST-LINK recovery guard](../../firmware/capture-timing/recovery_vcp/README.md) is installed and has selected the exact early park through PE6 after cold and warm resets, with the documented limits. The target is currently powered at the v3 helper's awake park, `0x341E05E4`. The JS110 helper closed cleanly with its starting range 128 restored; BREAK is released and COM8 closed. Only CH0/NRST and CH6/PE6 are confirmed; CH1â€“5 were not moved or reverified, and no additional probe move is needed for this smoke test. The wiring table remains canonical. The existing NAND selection is unchanged pending comparison, and normal v45b camera capture remains unqualified. Older statements that no driver has run or that VCP recovery is unimplemented are historical.

**Current choice, October 19, 2026:** the user will connect the existing seven-pin breakout without adding socket wires and asks to maximize one-bit throughput. Use **native one-bit SDMMC2**, with hardware CRC, flow control and internal DMA available. The passive breakout's SPI-labelled SCK/DI/DO connections also carry native SD CLK/CMD/DAT0. **This replaces both the proposed four-bit socket-wire modification and the earlier Arduino SPI5 partial direct-plug plan.** Four-bit SD remains a possible later comparison with an appropriate carrier; no extra socket contacts are required for this one-bit experiment.

The user confirms the configurable GPIO banks are **still at 3.3 V**; the planned NAND voltage conversion has not been applied. D2 and R23 were previously reported removed. This selects the SD comparison interface, not a final replacement of the NAND storage architecture. No SD driver has been installed and no card measurements have been made.

**Subsequent October 19 bench update:** the user reports these SD connections attached, ST-LINK USB connected, and target power through JS110. The JS110 recovery-output wire no longer reaches; the user prefers replacing it with ST-LINK-controlled recovery. Actual rails, source routing and probes still need rechecking. The [proposed VCP recovery detector](../../firmware/capture-timing/recovery_gpio/README.md#october-19-proposed-st-link-vcp-recovery) is not installed, so do not assume the current PE1 guard can be selected remotely.

## Current connection plan

Use short jumper wires to **CN3's odd-numbered row** for CLK/CMD/DAT0, the unused DAT3 bias connection and ground, plus Arduino **CN5.4 / 3V3** for power. Count CN3 from its marked pin 1 in steps of two. CLK/CMD/DAT0 use **AF11**; PE4 stays a **GPIO input with pull-up**, not an AF data output or a driven chip select. These pins belong to **VDDIO5**, which must remain at **3.3 V** with stock **SB23 fitted**. Do not apply the historical 1.8 V VDDIO5 NAND conversion. No Nucleo soldering, bank change or AREF jumper is needed.

| SD breakout connection | Native SD function | Nucleo connection | MCU |
|---|---|---|---|
| **SCK** header pad | Clock | **CN3 pin 3** | PC2 / SDMMC2_CK |
| **DI** header pad | Command/response | **CN3 pin 25** | PC3 / SDMMC2_CMD |
| **DO** header pad | Data bit 0 | **CN3 pin 13** | PC4 / SDMMC2_D0 |
| **CS** header pad | Unused DAT3; bias HIGH | **CN3 pin 21** | PE4, input with internal pull-up |
| **VCC** header pad | 3.3 V power | **CN5 pin 4 / 3V3** | Supply, not a GPIO |
| **GND** header pad | Ground | **CN3 pin 19** | Ground |
| **CD** header pad | Mechanical card detect | **Leave disconnected** | Unneeded initially |

```text
Breakout/socket                 Nucleo

SCK   (CLK) ------------------- CN3.3   PC2
DI    (CMD) ------------------- CN3.25  PC3
DO    (DAT0) ------------------ CN3.13  PC4
CS    (unused DAT3) ----------- CN3.21  PE4  [input with pull-up]
GND -------------------------- CN3.19
VCC -------------------------- CN5.4   3V3
CD    unconnected
```

**CS is not a chip select in native SD mode.** Leave PE4 as an input with pull-up; the card also has a DAT3 startup pull-up. DI/CMD and DO/DAT0 are bidirectional. Do not initialize this wiring with the earlier SPI driver or select four-bit width. **No wires go to CN3.15 or CN3.17 and no fine socket soldering is needed.** CD remains unconnected. Do not disable the card's DAT3 pull-up in this experiment.

The CN3 route avoids the camera, boot NOR, PE1 recovery, PD0/PE0 timing markers and PG0/PG8/PG10 phase LEDs. C02 ODB connectivity shows the selected signal nets connect only the MCU and their CN3 contacts. This is the cleanest reviewed routing for qualifying the highest practical one-bit clock, not evidence of a measured performance win over SPI.

A hardware **one-bit Arduino alternative exists**: SDMMC1 AF10 with CK=PC12/A4/CN4.5, CMD=PH2/A5/CN4.6 and DAT0=PE15/D13/CN14.6. Unlike the CN3 pins, these have analog-divider branches or the D13 LED transistor-gate load. They do not establish a lower working speed, but CN3 avoids those additional loads and is preferred for this throughput experiment. An all-Arduino **four-bit** route is unavailable because the required DAT1 pins are not exposed there.

## Breakout limits and later four-bit option

The photo's seven pads are `CD DO GND SCK VCC DI CS`. They provide every actively used signal for native **one-bit** SD. The header cannot carry four-bit SD because it lacks DAT1 and DAT2. The photo resembles SparkFun's passive microSD Transflash breakout, but does not establish the exact board/socket revision. Verify continuity/bidirectional direct connections if identification fails; the plan assumes a passive socket adapter, not a module with fixed-direction SPI level shifters.

In the matching published SparkFun schematic and board files:

- MicroSD socket **contact 1 = DAT2**, named `NC` in the SPI-oriented schematic.
- MicroSD socket **contact 8 = DAT1**, named `RSV` in that schematic.
- Neither contact is connected to a PCB net or tied to ground.
- Header **CS goes to socket contact 2 / DAT3**. Header **CD goes to the mechanical detect switch**; CD is not an extra data line.

**Do not add those socket wires for the current test.** If a four-bit comparison is wanted later, a breakout exposing all native signals, such as [Adafruit 4682](https://www.adafruit.com/product/4682), avoids socket rework. Then add DAT1 to **CN3.15 / PC5**, DAT2 to **CN3.17 / PC0**, and configure PE4/DAT3 as AF11 along with the other lines after proper bus-width negotiation. The current one-bit setup must not request that width.

## Supply, pull-ups and initial firmware setup

Use **3.3 V power and signaling**. Provide approximately **100 nF plus 10 microfarads** local decoupling across VCC/GND near the socket; the matching passive breakout does not include these capacitors. Check actual voltage and card-write droop; spare regulator current and the particular card's peak current are not yet measured. Keep CLK/CMD/DAT0 leads short, preferably around 5 cm where practical, with a nearby ground return rather than a large loop. This is a bench-layout recommendation, not a certified length limit. A 22-33 ohm series resistor at the MCU end of CLK is an optional provision for ringing; bus speed will be raised only after reliable reads.

For the initial bench test, retain the internal-pull-up approach on **PC3/CMD, PC4/DAT0 and PE4/unused DAT3**. STM32's specified 30-50 kilohm pull-ups fall within the cited card-interface 10-100 kilohm range. Configure them as digital inputs with pull-ups early, establish a non-floating clock, allow settling, then select AF11 for PC2/PC3/PC4 with CMD/DAT0 pulls retained. Keep PE4 in input/pull-up mode. Start native identification at **100 kHz** and retain **one-bit width** throughout data transfers. Hardware actively drives data during transfers; the weak pull-ups do not generate the high-speed data edges.

This is an experimental convenience, not a reset-time guarantee: GPIO pull-ups are disabled in reset analog mode, and the card's own startup pull-up covers **DAT3 only**. The matching breakout also leaves unused DAT1/DAT2 unconnected, so the MCU cannot pull those card contacts high. Complete interface references recommend pull-ups on CMD and all DAT lines, including unused ones; this existing SPI carrier does not implement that complete bias network. We will try it unchanged for the requested functional/performance bench test, with actual initialization, readback and current checks, rather than claiming full electrical qualification. Adding unused-line pull-ups later would require access to the hidden contacts or a different carrier. Do not silently enable four-bit mode or declare the unchanged board production-qualified. Do not copy the superseded PA3 push-pull-CS setup into this native-SD driver.

Do not request the UHS **1.8 V signaling switch**: this bench wiring stays at 3.3 V. Candidate operating points are 25 MHz default speed and, only after supported card mode selection and link/readback qualification, 50 MHz High Speed. Jumper wiring does not establish either clock as reliable. If the card was previously put into SPI mode, power-cycle the card before native-SD initialization; resetting only the MCU is insufficient.

Disconnect board power and the external recovery drive while soldering. Remove any prior Arduino SPI connections before installing these wires; the breakout must not remain plugged into the earlier four-pin arrangement. Restore the previously working power/recovery setup afterward. Keep CN10 independently powered for development with D2 removed. Recheck bench ownership, supply routing, recovery selection and probe operation before automated power control. The last confirmed CN8/CN9 target route bypassed JS110; this document does not assert that has changed. Preserve the qualified recovery guard in any subsequent firmware.

## What the comparison can establish

The selected test uses one-bit **hardware SDMMC2**, not bit-banging or SPI5. Hardware CRC, internal DMA and busy handling provide a native SD timing path. The completed smoke helper uses polling reads; DMA/cache handling, production write completion and a sustained-transfer benchmark remain to implement. Read checks have passed at 100 kHz, 12.5 MHz and 25 MHz, but these small reads do not establish throughput. At equal clock the raw payload bandwidth is still one bit per cycle, like SPI. Which implementation achieves higher total throughput must be measured.

The current captured image is **1120 x 1364**, or **1,909,600 bytes packed RAW10**. It occupies 3,730 SD sectors when padded to 512-byte boundaries (1,909,760 bytes), or 933 Alliance data pages. The existing 16-bit RAM buffer is 3,055,360 bytes; saving that buffer instead adds 60% to the payload and is not a fair comparison with packed-RAW10 NAND estimates. The specification's 1124-pixel-wide image is a separate 1,916,420-byte workload.

| Conditional model for current packed image | Time |
|---|---:|
| **Selected one-bit SD payload alone at 25 MHz** | **0.611 s** |
| **Selected one-bit SD payload alone at 50 MHz** | **0.306 s** |
| Future four-bit SD payload alone at 25 MHz | 0.153 s |
| Future four-bit SD payload alone at 50 MHz | 0.076 s |
| Selected bit-banged quad NAND, hypothetical 5 MHz, including typical array program time | 1.324 s |
| Hardware quad NAND at hypothetical 50 MHz, including typical array program time | 0.636 s |

The SD entries exclude initialization, protocol overhead, card busy/maintenance intervals, metadata, synchronization and readback. NAND entries also exclude commands, packing, metadata, erase, verification and acquisition. NAND's 933 sequential programs add 0.5598 seconds at the documented 600-microsecond typical page time. None of these rows is a measured total save time. Four-bit SD has four times the payload bandwidth of single-bit SPI at the same clock, not a guaranteed fourfold reduction in complete-save time.

The first useful test sequence is:

1. Read card identity/capacity and verify non-destructive reads. Record actual interface clock and card identity.
2. Write an image-sized pseudorandom payload to a **new test file**, or an **explicitly authorized disposable sector range**. Do not format, overwrite unknown files or treat apparently empty sectors as safe without allocation knowledge. No destructive test is authorized yet.
3. Measure initialization, payload transfer, intermediate/final busy waits, status/synchronization completion and checksum readback separately. Use native SD multi-block transfers with IDMA and chunk preparation overlapped where useful. Include file/allocation work when testing a filesystem. Native SD uses its command/response and stop procedure; do not reuse SPI data/stop tokens. DMA completion alone is not durable completion; honor the card's enabled cache and completion requirements.
4. Repeat 20-50 operations for a preliminary median/range. Measure genuine cold card starts once autonomous power cycling has been reverified, then check saved data after a fresh power cycle. Keep initialization off the capture-critical path where possible so storage does not delay exposure.
5. Measure complete-cycle energy and current peaks only after the JS110 measurement boundary is restored and checked. The prior debugger/CN8 bypass audit remains relevant. Timing results can be useful before precision energy is available.

This quick experiment cannot qualify ten-year unpowered retention, the accepted reuse requirement or preservation of older photos through interrupted SD-controller updates. Those remain part/card-specific qualification work if SD is adopted. One-bit throughput is the current test objective; four-bit results would require a separate future comparison.

## Follow-up: throughput loss and buffering with the existing SPI breakout

Historical October 19 comparison preceding the current one-bit SDMMC2 choice: what does single-bit SPI cost, and can double buffering hide it? At equal clock, SPI and one-bit SD have one quarter the four-bit SD payload bandwidth: **3.125 versus 12.5 MB/s at 25 MHz**, or **6.25 versus 25 MB/s at 50 MHz**. MB/s here uses decimal bytes. For the current packed image, padded to 3,730 sectors, transfer-only penalties are **458 ms at 25 MHz** and **229 ms at 50 MHz**. These are differences in bus occupancy, not predictions of complete-save latency. The 50 MHz SPI case requires card High Speed support/selection and independent signal-timing qualification; faster write payload clocks need not imply equally fast status/readback clocks.

There are two distinct buffering layers:

- **MCU buffers/DMA:** two sector-aligned buffers can overlap RAW10 packing/checksum work for the next chunk with transmission of the current chunk. The whole captured image is already in RAM, so there is no need for two complete images. DMA can reduce CPU energy and software gaps. It cannot transmit payload to a card that is asserting busy or exceed the serial bit-rate limit.
- **Card-controller buffers:** the SD protocol permits buffered writes, potentially accepting another block while earlier data is being programmed. This depends on the card/controller and chosen transfer mode. Use consecutive multi-block writes (**CMD25**), honor each response and busy interval, and check final stop/busy/status completion. Do not assume that CMD25 eliminates per-block waits or guarantees overlap on this unidentified card. SPI carries no SD Speed Class performance guarantee.

The optimistic sustained-rate model with effective internal overlap is `min(bus payload rate, card internal write rate)`, before protocol/software overhead. For example, at a qualified 50 MHz clock, a hypothetical 10 MB/s internal writer could reach at most 6.25 MB/s over SPI versus 10 MB/s over four-bit SD: a 37.5% throughput loss and 1.6x time, not a guaranteed 4x time. A hypothetical 2 MB/s internal writer could bottleneck either interface with little width penalty if overlap is effective. With no internal overlap, transfer and programming intervals add instead; real behavior lies in the measured command/busy trace and can change with mode, card state and workload. Startup and final drain are additional costs for a single-photo cycle.

For an efficient test, prepare large sector-aligned chunks (for example two 32 KiB packing buffers), use SPI DMA and CMD25, and avoid filesystem synchronization after every 512-byte sector. Use a properly allocated new file or an explicitly authorized scratch range. Where supported, ACMD23 with the correct forthcoming write count can assist multi-block programming; its affected extent must be within that allocation, especially if a write is interrupted. Complete the required final synchronization/status/cache contract before powering down. Measure cold initialization, time actually clocking payload, card-busy intervals, software gaps and final completion separately. This will reveal whether the existing breakout's bus width is materially limiting this card without presenting modeled values as measurements.

## Evidence

- [ST MB1940 C02 schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf) and [UM3417 Table20](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf), CN3 mapping and CN5.4 supply. C02 ODB connectivity independently confirms all six MCU/header nets and absence of other component connections.
- [STM32N657 DS14791](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), Rev10 Table20, pages126/128: selected PC/PE pins use AF11 for SDMMC2; Table67 gives pull-up resistance.
- [ST AN5967](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf), VDDIO5 includes PC0, PC2-PC5 and PE4; section14.4.1 provides SDMMC signal-layout and pull-up guidance.
- [STM32 RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), sections15.3.1/15.3.12 and GPIO reset values; [Nexperia AN10911](https://assets.nexperia.com/documents/application-note/AN10911.pdf), pages5/18, SD DAT3/CS mapping and card-internal power-up pull-up.
- [SparkFun microSD Transflash breakout](https://www.sparkfun.com/sparkfun-microsd-transflash-breakout.html), its [schematic source](https://github.com/sparkfun/microSD_Transflash_Breakout/blob/master/Hardware/SparkFun_microSD_Breakout.sch) and [board source](https://github.com/sparkfun/microSD_Transflash_Breakout/blob/master/Hardware/SparkFun_microSD_Breakout.brd), U1 socket pad connectivity. These are matching design references, not proof of the user's module's identity.
- [ATP microSD datasheet, Table4-4](https://advdownload.advantech.com/productfile/PIS/96FMSD-8G-CM-AT/file/96FMSD-8G-CM-AT_datasheet20200330122023.pdf), CMD/DAT pull-up range; [SD Association specification index](https://www.sdcard.org/downloads/pls/) for the governing protocol.
- [ST EMIF06-MSD02N16 datasheet, section2.3](https://www.st.com/resource/en/datasheet/emif06-msd02n16.pdf), page5: CMD and all DAT lines require pull-ups in four-bit, one-bit and SPI modes. This documents the unchanged carrier's unused-DAT bias limitation in either one-bit interface.
- SD Association Physical Layer Simplified Specification: [official v5.10](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver5.10.pdf), section7.2.4, multi-block SPI response/busy handling; [SDA-authored v2.00, mirrored PDF](https://chlazza.nfshost.com/docs/Simplified_Physical_Layer_Spec.pdf), sections7.2.4/7.2.13-15, CMD25, mode switching and lack of SPI Speed Class guarantee. The mirrored v2 PDF was read successfully; direct current SDA downloads returned empty files, so they are not archived as valid local references.
- [Existing Alliance timing calculations](alliance-nand-wiring.md#estimated-time-and-energy-penalty), [storage architecture comparison](../../reports/Camera%20storage%20architecture%20alternatives.md), and [debugger/power audit](../power/nucleo-debug-isolation.md).
