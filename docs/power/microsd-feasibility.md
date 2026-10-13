# microSD feasibility, card candidates and capture-cycle energy

> **Historical screening:** this September 8 study uses the earlier VD55G0 workload and dated supply observations. microSD remains an alternative, not an approved substitution. Reevaluate its rail/socket, cold start, durable commit and complete energy against the [selected VD56G3 prototype](../../spec.md), the 200-photo minimum and current readback policy before adopting a card.

**September 8, 2026. Research and analytical screening; no schematic or firmware changes.**

**microSD is feasible. Qualify Kingston SDCIT2/8GB first, with ATP AF4GUDI-WACXM as an SLC comparison.** No public data located establishes either as the lowest-energy card for our cold-start, single-photo workload. The decisive measurement is battery energy and time from power-on through durable commit, not maximum sequential MB/s. Industrial microSD supply is better for some exact parts, but the checked distributor prices are much higher than the $8.40 Alliance NAND candidate.

## Card shortlist

Stock checked September 8; USD at quantity one before shipping/tax/tariffs. These are snapshots, not reserved inventory or firm replenishment commitments.

| Candidate | Exact distributor listing | Supply / price | Reason to evaluate |
| --- | --- | --- | --- |
| **Kingston SDCIT2/8GB** | DigiKey **6318-SDCIT2/8GB-ND**, bulk | **915; $74.79; six-week standard lead time; Active** | First practical benchmark: industrial pSLC, ample capacity, available replenishment estimate |
| **ATP AF4GUDI-WACXM** | DigiKey **1282-AF4GUDI-WACXM-ND** | **3,847; $167.81; Active; no backorders; 1,200-unit limit per 30 days** | True SLC comparison with stronger immediate stock, but high cost |
| Kingston SDCE/32GB | DigiKey current listing | **325; $70.30; Active; no backorders** | Optional consumer-endurance control; little price advantage at this distributor |

Sources: [Kingston industrial listing](https://www.digikey.com/en/products/detail/kingston-technology/SDCIT2-8GB/28521680), [ATP listing](https://www.digikey.com/en/products/detail/atp-electronics-inc/AF4GUDI-WACXM/3770355), [Kingston endurance listing](https://www.digikey.com/en/products/detail/kingston-technology/SDCE-32GB/26598480). The separate older Kingston packaging listing has different inventory; use the exact linked SKU. These prices do not establish the best possible direct-OEM or retail quote.

Kingston's [SDCIT2 manufacturer datasheet](https://www.kingston.com/datasheets/sdcit2_en.pdf) lists up to 100/80 MB/s read/write, U3/V30/A1 and −40 to +85°C, with TLC used in pSLC mode. It does **not** publish operating current, cold initialization time or maximum first-image write latency. [Local archive](../../datasheets/memory/Kingston_SDCIT2_industrial_microSD.pdf).

ATP's [2026 guide](https://www.atpinc.com/upload/download/2026/01-21/604c08d4.pdf) lists S800Pi family write performance up to 39 MB/s, while the exact distributor-linked [legacy brief](../../datasheets/memory/ATP_microSD_S800Pi_legacy_brief.pdf) says 18 MB/s. Confirm the supplied controller/firmware revision before assigning either performance figure to AF4GUDI-WACXM. No exact-part current or cold-start/first-write bound was found. SLC technology alone does not prove lower whole-card energy.

The older low-power Swissbit S-200u/S-300u and Delkin U331C families do not offer a convincing current supply solution; checked variants are NRND, obsolete or scarce. Transcend TS8GUSDC10I provides maximum power limits but no typical cold-photo energy and no useful DigiKey/Mouser stock was found. Avoid choosing an obsolete card solely because its electrical table looks attractive.

## Hardware path

Use **native four-bit SDMMC2 at 50 MHz High Speed** for the initial design study. Its raw data ceiling is 25 MB/s; STM32N657 supports IDMA and SD/UHS-I. SPI would surrender much of the throughput advantage. UHS-II is unsupported. [STM32 datasheet, SDMMC sections and timing tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=202).

Conservative power arrangement:

```text
Battery / USB source selection
  +-- 1.8 V digital supply --> MCU main/core-SMPS input, NOR, other 1.8 V I/O
  +-- controlled 2.8 V supply --> camera analog branch
  +-- switched 3.3 V supply --> microSD VDD and MCU VDDIO5
```

This removes the raw NAND device and its parallel bus, adds a socket, and replaces host BCH/bad-block management with the card's managed block interface. Socket retention, card detect, exposed-contact ESD, extra height and removable-card behavior need mechanical/electrical review. Provide local decoupling and a switch with controlled ramp, sufficient pulse-current capability and low off leakage. Gate or isolate all pull-ups/signals to prevent back-powering an off card. Main/AUX sequencing still applies to the MCU banks.

The six preferred SDMMC2 signals share VDDIO5:

| Signal | GPIO / ball | Recovered use to relocate |
| --- | --- | --- |
| CK | PC2 / D9 | Accelerometer software-I2C SCL |
| CMD | PC3 / E10 | Accelerometer software-I2C SDA |
| D0 | PC4 / A10 | Accelerometer interrupt |
| D1 | PC5 / B10 | Unconnected |
| D2 | PC0 / C10 | Status LED |
| D3 | PE4 / D10 | Unconnected |

Move the accelerometer and LED signals onto spare 1.8 V GPIOs, potentially those released by deleting NAND. SDMMC1's default pins instead conflict with camera controls, MCLK and I2C, making it less convenient. This is a bounded feasibility check, not a completed alternate pin assignment. [STM32 pin/AF tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=126).

**1.8 V UHS signaling does not mean a 1.8 V card supply.** Ordinary microSD VDD is 2.7–3.6 V; UHS negotiation changes signal voltage while card VDD remains powered. Faster UHS needs either a switchable I/O-bank supply or appropriate SD translator and adds tuning/sequence work. [ST AN5967](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=28).

Sharing an upsized **2.8 V** camera source is a possible later optimization, not ruled out by card VDD or VDDIO5's 2.7–3.6 V operating range. However, ST's SDMMC timing tables characterize the upper signaling range at **3.0–3.6 V**, and 2.8 V leaves only 100 mV nominal above the card minimum. A −2% regulator tolerance leaves 44 mV for switch/trace loss and droop. Such a shared source needs independent card/camera switches, camera filtering and timing/power qualification. Use 3.3 V as the conservative prototype baseline.

## Cycle-time model

The native packed image is **486,220 bytes**, padded to **950 sectors / 486,400 bytes** before metadata. The STM32 can buffer the image in SRAM. Start SD initialization alongside camera setup without blocking acquisition; stop the camera safely after the frame arrives, then complete storage and shutdown. This can hide initialization latency but not the card's initialization energy, and it increases concurrent load.

```text
Cycle = max(camera-ready image time, SD-ready time)
      + image write + additional commit/ready delay + shutdown
```

For payload alone, 10/20/25 MB/s imply **48.64 / 24.32 / 19.46 ms**. The 25 MB/s number is a bus ceiling, not achievable complete-transaction throughput. An advertised 80 MB/s UHS rating cannot be used on the initial 25 MB/s High Speed interface.

Protocol behavior prevents a universal small-file latency guarantee:

- ACMD41 initialization may take up to one second from the first command. This is an allowance, not a typical delay or an instruction to sleep for a full second; identification, mode setup and filesystem preparation also take time.
- Write-busy intervals can reach 250 ms, with some SDXC final/stop busy periods reaching 500 ms. These apply to individual operations and do not bound an entire image containing multiple operations.
- If optional card caching is enabled, ready may precede durable storage; the host must honor flush/power-off notification. Flush can itself take up to one second. Leave optional cache disabled until the driver implements its shutdown contract.

Primary sources: [SD Association Physical Layer v6.00, sections 4.2.3 and 4.6.2](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver6.00.pdf), [SDA cache explanation](https://www.sdcard.org/wp-content/uploads/2020/11/Mobile_Device_Innovations_20170227.pdf). The physical specification was readable through web retrieval, but a direct local download returned HTTP 403; no local PDF was saved.

## Power and numerical scenarios

As a documented reference, the [Swissbit S-56u Rev.1.14 datasheet](../../datasheets/memory/Swissbit_S56u_datasheet_Rev114.pdf) gives **50 mA typical HS write**, **90 mA typical UHS write**, and **120 mA maximum** at 25°C. Standby is 2 mA; autonomous read/refresh draws more. It describes background read/refresh after power-on, which needs measurement in a repeatedly switched camera. Its 250 ms power-up parameter describes **rail ramp**, not initialization latency. [Manufacturer-authored source](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6750/S-56u_data_sheet.pdf).

These Swissbit figures are **not Kingston or ATP specifications**. They support useful sensitivity inputs, while the exact selected card still requires measurement.

The following model assumes: camera acquisition completes at 50 ms; SD power starts at time zero; card ready includes startup/host setup; 20 MB/s effective image write; 50 mA average card current during initialization and write/commit, 2 mA while ready but waiting for capture; 3.3 V card supply; 200 mW for other loads after capture; common 85% conversion efficiency. The 50 ms capture is a target used for comparison, not established performance. Shutdown, verification and metadata costs beyond the stated commit allowance remain unmodeled.

| Illustrative SD behavior | Ready after power-on | Additional commit delay | Cycle through commit | Incremental storage energy at loads / battery |
| --- | ---: | ---: | ---: | ---: |
| Short startup/commit | 20 ms | 10 ms | **84.32 ms** | **16.02 / 18.85 mJ** |
| Longer startup/commit | 100 ms | 25 ms | **149.32 ms** | **44.50 / 52.36 mJ** |
| Long-delay example | 1,000 ms | 250 ms | **1,274.32 ms** | **455.13 / 535.44 mJ** |

These are **constructed scenarios, not typical or worst-case ratings for any card**. Incremental energy includes all modeled SD energy, including initialization during capture, plus other-board energy after capture; common camera/MCU boot-and-capture energy is excluded once, avoiding double counting overlap. Extra commit delay means work not already included in the assumed write throughput. Card initialization current is an assumption, not inferred from its write-current rating.

The previous Alliance NAND partial reference is **94.70 ms storage / 144.70 ms including the same 50 ms acquisition**, and **21.51 mJ at loads / 25.31 mJ battery** under this model. It includes 200 mW of other-board power during storage and 2.57 mJ of NAND program-busy energy, but excludes NAND loading, verification, erase and metadata. Its NAND figure uses maximum normal-program current with typical program time. Thus it is a useful benchmark target, not a measured total or perfectly complete comparison. [NAND analysis](nand-energy-impact.md).

microSD can therefore beat this reference if it starts and commits quickly; a longer startup can roughly double storage-related energy, and long delays cost much more. Changing throughput from 20 to 80 MB/s saves only 18.24 ms of payload time before accounting for mode-switching overhead or higher current. For this small image, cold readiness and commit behavior deserve priority over headline bandwidth.

At **100 mA card current**, 3.3 V card plus 200 mW elsewhere is **530 mW**. At 85% conversion efficiency it draws about **52 mA at 12 V** or **78 mA at 8 V**, through every series CR2032. Camera startup or card inrush can add more. These are load examples, not card peak limits; qualify cell droop and regulator transients separately from nominal battery capacity. SD needs complete power gating between shots to preserve the shelf-OFF objective.

## Firmware and qualification

Use multi-sector IDMA writes with aligned, cache-coherent buffers and packed RAW10. Preallocate contiguous storage while USB-powered. A FAT file preserves removable-card usability; an append-only raw log can reduce filesystem metadata but requires export software and still has the card's internal flash translation/garbage collection. [FatFs allocation](https://elm-chan.org/fsw/ff/doc/expand.html), [multi-sector performance guidance](https://elm-chan.org/fsw/ff/doc/appnote.html).

Successful DMA completion is not sufficient for power-off. Close/synchronize the file, check lower-level errors and card status/ready, complete any enabled cache contract, then sequence card and MCU supplies off. Use busy-release interrupts to let the CPU idle. This does not make accidental brownouts safe; recoverable records and interrupted-write testing remain necessary. [FatFs synchronization](https://elm-chan.org/fsw/ff/doc/sync.html), [STM32 RM0486 SDMMC](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=1422).

For each exact card revision, measure at least 1,000 cold photo cycles for an initial distribution, followed by representative aging/fullness and voltage/temperature tests. Record rail enable, card-ready, image transfer, final busy/commit and shutdown markers; integrate battery voltage × current, and record peak current and minimum card voltage. Separate median, 99th percentile and largest observed time/energy; none is a guaranteed field maximum. Verify saved images after a fresh power cycle, and test recovery from interrupted writes without damaging earlier photos. Start with 50 MHz HS; test UHS only if the measured time/energy reduction justifies its hardware work.

**Decision:** microSD merits a prototype comparison, but current documentation does not justify replacing NAND on power grounds. Kingston is the first supply/practicality candidate to test; ATP is the higher-cost SLC control. Keep the NAND option until actual cold-cycle measurements establish an improvement or the removable-card/supply benefits justify the measured cost.

Reproducible scenario model: [script](../../tools/calculate_microsd_tradeoff.py), [results and assumptions](microsd-calculations.json).
