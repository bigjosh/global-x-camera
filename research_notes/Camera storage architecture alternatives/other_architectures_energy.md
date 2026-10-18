# Other storage architectures and whole-cycle energy

Research checked October 18, 2026. Read-only research; no hardware or project decision changed. SD and eMMC are covered by other researchers. The payload here is the project's 1,916,420-byte native packed RAW10 image, not the slightly smaller current capture-test frame.

## Which alternatives are actually useful beyond one raw NAND chip?

### Takeaway

The most useful overlooked architecture is **two independent serial SLC NAND chips, alternating pages of the same photo**. It gives genuine transfer/program overlap without requiring cache-program support inside either chip, doubles capacity, and preserves a simple MCU interface. Parallel cache-program NAND is another serious option, but needs more pins and an ECC implementation. Neither is automatically the lowest-energy option until measured.

### Cited Findings

- Macronix MX35LF4GE4AD provides 4 Gbit, 4 KiB pages, 400/800 microseconds typical/maximum page program time, 2.7–3.6 V operation, and internal ECC. Page programming continues after CS rises; the device's outputs deselect independently. These properties permit an architectural proposal using two **separate packages with separate CS signals**. [Macronix datasheet, program sequence and Tables 31/34](https://www.macronix.com/Lists/Datasheet/Attachments/9047/MX35LF4GE4AD,%203V,%204Gb,%20v1.6.pdf)
- STM32N657 has hardware XSPI supporting serial NAND and quad transactions, plus an FMC NAND controller. FMC's headline ECC support does **not** by itself establish compatibility with a particular NAND's required multi-bit ECC strength. [STM32N657 datasheet, sections 3.16–3.17](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf)
- Macronix's parallel cache-program architecture explicitly provides overlap between loading and array programming, with distinct cache/array status and failure handling. [Macronix cache-operation application note](https://www.mxic.com.tw/Lists/ApplicationNote/Attachments/2117/AN0268V2-Improving%20NAND%20Throughput%20with%20Two-Plane%20and%20Cache%20Operations.pdf)
- Some Winbond serial NAND offers a bad-block lookup table. This is useful hardware remapping, but the cited product information describes block replacement, not a complete eMMC-style FTL with transparent wear leveling and arbitrary sector updates. Do not equate internal ECC or BBM with fully managed storage. [Winbond QSPI NAND portfolio](https://www.winbond.com/hq/product/code-storage-flash/qspi-nand/?__locale=de)

### Inferences

**Two-chip schedule, calculated and untested:** at an assumed achieved 50 MHz quad payload rate, a full 4 KiB page loads in 163.84 microseconds. Chip A loads during 0–163.84 us and programs until 563.84 us. Chip B loads during 163.84–327.68 us and programs until 727.68 us. Then A receives its next page, followed by B, repeating. Thus one pair is issued every 563.84 us, plus the final chip's 163.84 us offset.

For 468 full padded pages, `234 × (163.84 + 400) + 163.84 = 132,102.4 us`, or **about 132 ms**, compared with **about 264 ms** for a single chip. At the 800 us maximum program-time input, the same idealized schedule gives **about 226 ms** versus **451 ms** for a single chip; these remain incomplete timing models, not worst-case camera-save guarantees. Commands, status, metadata, packing, CRC, readback, retries, start-up and erase are omitted.

- This requires **striping pages of each photo across both chips**. Merely alternating whole photos between chips increases capacity but does not reduce one-photo latency. A durable FULL commit must wait for both sides and all status checks.
- Two 4 Gbit chips provide 1 GiB gross: 512 gross 2 MiB slots, about 409 after an illustrative 20% reserve. Actual guaranteed capacity requires bad-block and metadata accounting. Slot allocation, per-chip block mapping, retirement, partial-write recovery, and atomic commit need an explicit design.
- This is distinct from two dies inside one serial package: die-selection rules may forbid switching while busy. Separate independent chips avoid that specific restriction; do not assume a multi-die part behaves equivalently.
- Two program operations can overlap, increasing peak storage current and bus capacitance. Overall programming work is essentially unchanged; wall time falls, potentially saving MCU/board energy. It does not imply doubling energy or halving energy.
- We have not selected or verified a second chip-select pin on this Nucleo. Separate CS wiring, bus loading, clock rate, and simultaneous programming remain to be qualified. This proposal need not share the boot-NOR bus.

### Gaps

- No assembled dual-NAND timing or energy measurement; no verified pin plan; no combined ten-year-retention-after-1,000-reuse-cycle qualification.
- No credible ready-to-buy SPI-native fully managed NAND replacement with complete FTL was established in this focused search. This is a search limit, not proof none exists.

## Why not NOR, MRAM/FRAM, USB flash, UFS or an SSD?

### Takeaway

NOR is compatible but generally a poor fast-photo-write choice; MRAM/FRAM are excellent for a small allocation table but costly or physically excessive for hundreds of megabytes. USB flash is technically usable but adds initialization and power-management overhead. UFS and native SATA/NVMe SSDs do not have a directly supported host interface on this MCU.

### Cited Findings

- A concrete high-density NOR, Macronix MX66UM2G45G, stores 2 Gbit/256 MiB and programs 256-byte pages in 0.15 ms typical, 0.75 ms maximum. Its impressive octal interface speed is not its sustained programming throughput. [Macronix NOR datasheet, page 92](https://www.macronix.com/Lists/Datasheet/Attachments/8709/MX66UM2G45G,%201.8V,%202Gb,%20v1.0.pdf)
- Infineon's SEMPER portfolio includes densities through 4 Gbit and emphasizes high read bandwidth and retention features. NOR therefore must not be dismissed as universally too small; write throughput and cost remain the relevant objections. [Infineon SEMPER product brief](https://www.infineon.com/dgdl/Infineon-SEMPER_NOR_Flash_Memory-ProductBrief-v01_00-EN.pdf?fileId=8ac78c8c7ddc01d7017e671f419a57aa)
- Everspin's serial PERSYST portfolio now extends through **256 Mbit/32 MiB**, operates at 1.8 V, and includes quad/octal interfaces. Larger densities appear in roadmaps; do not treat future products as stocked production parts. [Everspin September 24, 2026 technology comparison](https://www.everspin.com/toggle-mram-vs-stt-mram-blog), [current product portfolio](https://www.everspin.com/products)
- The earlier EMxxLX datasheet describes byte writes with no erase, 10-year industrial retention and very high endurance; exact 256 Mbit suffix qualification and stock still need verification. [Everspin EMxxLX datasheet](https://www.everspin.com/sites/default/files/EMxxLX%20Datasheet%20v3.2.pdf)
- Everspin also sells **1 Gbit MRAM**, but it uses a DDR4-like interface with MRAM-specific changes. It is not an SPI part and STM32N6's SDRAM support is not a DDR4 controller. [Everspin ST-DDR products](https://www.everspin.com/spin-transfer-torque-ddr-products), [STM32 interface list](https://www.st.com/en/microcontrollers-microprocessors/stm32n657x0.html)
- A concrete price warning, not a recommendation: the older NRND 128 Mbit EM128LXQAB313IS1R listing showed about $196 each at a 4,000-piece quantity. This does not establish pricing for a current 256 Mbit part, but cheap bulk-photo MRAM was not found. [DigiKey listing](https://www.digikey.com/en/products/detail/everspin-technologies-inc/EM128LXQAB313IS1R/23623483)
- Infineon EXCELON F-RAM is offered through **16 Mbit/2 MiB** with SPI/QSPI and instant nonvolatility. [Infineon portfolio](https://www.infineon.com/products/memories/f-ram-ferroelectric-ram/excelon-f-ram)
- The reviewed discrete ReRAM example, Fujitsu MB85AS8MT, is **8 Mbit/1 MiB**. No suitable hundreds-of-megabytes discrete ReRAM part was established. [Fujitsu datasheet](https://www.fujitsu.com/jp/group/fsl/imagesgig5/MB85AS8MT-DS501-00060-1v0-J.pdf)
- Industrial USB flash exists with SLC and multi-GB capacity. Swissbit explicitly distinguishes **10-year retention at beginning of life** from **one year at end of life**, illustrating why a headline ten-year claim is insufficient for our combined retention/endurance requirement. [Swissbit USB portfolio](https://www.swissbit.com/en/products/flash-storage/usb-drives/)
- STM32N657 provides USB 2.0 HS host support at 480 Mbit/s. This can host USB mass-storage devices, but cannot obtain USB 3.x headline throughput. The MCU peripheral set does not include native SATA, PCIe/NVMe, or UFS host controllers. UFS uses M-PHY/UniPro, different from the camera's CSI D-PHY. [STM32 datasheet, section 3.51](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), [Kioxia UFS interface description](https://www.kioxia.com/en-jp/business/topics/topics-01.html)

### Inferences

| Architecture | Assessment for this camera |
|---|---|
| Serial/parallel NOR | 1,916,420 bytes require 7,486 of the cited 256-byte pages: **1.123 seconds of typical internal programming alone**. Poor save-time alternative to the faster SLC NAND candidates, even though capacity can be sufficient. |
| Serial MRAM | At the currently identified 32 MiB density, **16 chips** would be needed for 512 MiB before reserves. Excellent fast persistent small-state memory; unattractive bulk-photo capacity/area/cost. |
| F-RAM / reviewed ReRAM | 256 F-RAM or 512 reviewed ReRAM chips would be needed for 512 MiB. A **small F-RAM for the slot table plus NAND for payload** is much more sensible and directly addresses the user's earlier allocation-table concern. It does not speed NAND payload programming. |
| USB flash | Possible, particularly for a bench prototype, but enumeration/initialization, 5 V host supply where required, flush semantics and controller power add work; little advantage over native SDMMC for a compact fully power-cycled camera. |
| UFS / SATA / NVMe SSD | Needs a bridge or different MCU/SoC, adding hardware/software/energy overhead. Exclude from the immediate prototype shortlist; USB-connected SSD is constrained by USB 2.0 and still carries its controller/bridge overhead. |
| NAND plus tiny persistent metadata chip | Useful reliability/implementation option independent of bulk-media choice. Needs redundant/checksummed records and power-fail-safe state transitions; FRAM alone does not make multi-byte transactions atomic. |

### Gaps

- Current 256 Mbit MRAM price, 500-unit stock, exact lifecycle/retention qualification and a practical assembled module remain unverified. Do not claim all MRAM is tiny or all 1 Gbit parts directly work here.
- No measured USB boot-to-durable-write latency or exact USB-device peak current was obtained; neither superiority nor inferiority in total energy has been proven.

## How should low power be evaluated fairly?

### Takeaway

The deciding number is **battery joules from power-on through durable save and shutdown**, plus peak-current compatibility. Since the design completely removes power between captures, a memory's powered standby current is not the main comparison. Faster managed flash could win total energy despite higher active current by allowing the MCU and board to shut down sooner.

### Cited Findings

- Macronix specifies **30 mA typical / 40 mA maximum program current**, separate from transfer/read current; its 4 Gbit program interval is 400/800 us typical/maximum. This permits a bounded *model component* rather than multiplying an arbitrary maximum current by total camera time. [Macronix Tables 31 and 34](https://www.macronix.com/Lists/Datasheet/Attachments/9047/MX35LF4GE4AD,%203V,%204Gb,%20v1.6.pdf)
- Swissbit's product guide includes USB devices with high-speed typical current around 80 mA and distinguishes SLC/pSLC/MLC variants. Such family-level typical figures are **not exact-part peak-current guarantees**, so they cannot alone size the coin-cell supply or prove an energy winner. [Swissbit product guide, USB table](https://www.swissbit.com/files/public/Documents/Swissbit_Product_Guide.pdf)

### Inferences

Use `E_battery = integral(P_total_load / efficiency) dt`, separating initialization, data transfer, array program/busy, metadata commit or managed-media flush, MCU/SRAM/peripheral power and regulator loss. Include the sensor shutdown point, which can materially change the post-capture power baseline. Compare the same image, error checking and retention obligations.

At a chosen nominal 3.3 V, 468 pages × 400 us × 30 mA gives **18.5 mJ of typical modeled NAND programming energy**. This excludes data loading, initialization, metadata, MCU, regulator loss and readback, and is not a measurement or guarantee. Two-chip interleaving does approximately the same number of page programs and hence similar array-program energy, while finishing sooner. Two simultaneously programming chips can draw up to **80 mA from the storage rail using the two 40 mA DC maxima**, in addition to everything else; transient and supply-design margin still need testing.

For illustration only, eliminating 132 ms of a **hypothetical** 100 mW residual MCU/board load saves 13.2 mJ; at 500 mW it saves 66 mJ. This shows why component active-current rankings can disagree with whole-camera energy rankings. These power levels are scenarios, not qualified measurements of our prototype.

Required benchmark: cold power-on to ready, sustained write of the native photo, wait for durable completion/flush, optional readback under the agreed setting, final shutdown; record rail peak, battery energy and latency distribution after repeated reuse/full-device conditions. Prepare erase/free-space during USB mode where the architecture permits, but do not assume a managed FTL will never perform housekeeping during capture. Check the four-CR2032 source and reservoir against **peak power and droop**, not only average energy.

### Gaps

- The current board has known debugger/USB bypass paths, so a precision energy ranking must await a qualified power boundary. Standby specifications cannot settle this comparison, and fast burst transfer does not prove durable completion.
- Every flash candidate still needs evidence for ten years unpowered at room temperature after 1,000 complete reuse cycles; retention-at-beginning-of-life and endurance separately do not establish that combined condition.
