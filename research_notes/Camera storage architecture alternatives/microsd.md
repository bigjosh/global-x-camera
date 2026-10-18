# Industrial microSD and native SDMMC as camera storage

Research date: October 18, 2026. Read-only research; no hardware, firmware, vendor contact or purchase. This extends the historical screening in `docs/power/microsd-feasibility.md`; it does not select a replacement. Full native RAW10 payload used for calculations: 1,916,420 bytes, supplied by the current project review. Current acceptance target is at least 200 images, ten years unpowered at room temperature without refresh after 1,000 complete reuse cycles.

## Which practical SD alternatives deserve a benchmark?

### Takeaway

Industrial microSD using the STM32's native four-bit SDMMC interface is the easiest large-capacity alternative to prototype. Start with Kingston SDCIT2/8GB as a pSLC benchmark and ATP AF4GUDI-WACXM as a more expensive true-SLC comparison; neither is established as the lowest-energy or retention-qualified choice.

### Cited Findings

- Kingston SDCIT2 is TLC operated in pSLC mode, capacities 8–128 GB, 3.3 V, with family-level performance up to 100/80 MB/s read/write and 30,000 P/E cycles. It includes ECC, wear leveling, power-failure protection and refresh functions. The public sheet gives no exact current, cold-start timing, or decade-retention-after-use limit. — [Kingston SDCIT2 datasheet](https://www.kingston.com/datasheets/sdcit2_en.pdf)
- ATP's current July 2026 family table lists S800Pi true SLC at 512 MB–8 GB, family maximum 39 MB/s write, and firmware-based protection of data already at rest. Other ATP families use permanent pSLC rather than merely a small transient SLC cache. — [ATP microSD products](https://www.atpinc.com/products/industrial-microsd-usd-cards)
- The distributor-linked legacy ATP sheet only says up to 18 MB/s write for SLC, and omits exact operating current. Do not assign the current family 39 MB/s to the supplied AF4GUDI-WACXM revision without confirmation. — [ATP legacy brief linked by DigiKey](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/2385/ATP%20microSD_SDHC.pdf)
- Freshly opened DigiKey pages showed **Kingston SDCIT2/8GB: 414 available, $79.28 quantity one**; **ATP AF4GUDI-WACXM: 3,093 available, $177.88 quantity one**. Search snippets had older, higher inventory and lower prices; use the opened-page observations. These are research snapshots, not reservations. — [Kingston listing](https://www.digikey.com/en/products/detail/kingston-technology/SDCIT2-8GB/28521680), [ATP listing](https://www.digikey.com/en/products/detail/atp-electronics-inc/AF4GUDI-WACXM/3770355)
- Swissbit's current S-600u true-SLC microSD family is 512 MB–2 GB, up to 21 MB/s write. S-56u pSLC is 4–128 GB, up to 90 MB/s family maximum. Both list 2.7–3.6 V supply. The larger S-600 full-size SD family must not be mistaken for S-600u microSD. — [Swissbit microSD comparison](https://www.swissbit.com/en/products/flash-storage/industrial-microsd-card)
- **Adafruit 4682**, listed in stock at $3.50, exposes native four-bit SD signals and supports SPI too. It has no regulator or level translators and requires 3 V-class power/signals. It is a suitable small socket carrier; the SPI-only product 254 is not the intended board. — [Adafruit 4682](https://www.adafruit.com/product/4682), [manufacturer PCB files](https://github.com/adafruit/Adafruit-MicroSD-SPI-or-SDIO-card-breakout-PCB)
- STM32N657 SDMMC supports native SD, IDMA, and UHS-I subject to I/O speed; it does not support UHS-II/SD Express. Ordinary SPI mode would use a different SPI peripheral. — [STM32 datasheet §3.18](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf)

### Inferences

- At the supplied 1,916,420-byte image size, 4 GB is roughly 2,087 images and 8 GB roughly 4,174 before reserve space and metadata. Both comfortably exceed 200 images. These are arithmetic capacity ceilings, not exact formatted counts.
- Prototype native SDMMC2 can use the six stock-3.3 V VDDIO5 pins already documented on populated CN3: PC2/CK = CN3.3; PC3/CMD = CN3.25; PC4/D0 = CN3.13; PC5/D1 = CN3.15; PC0/D2 = CN3.17; PE4/D3 = CN3.21. This is crosschecked against the MCU AF table and existing header guide, not continuity tested. It avoids the 1.8 V NAND bank modifications and the boot-NOR bus taps. Keep SB23 fitted if the board remains stock; first inspect any actual modifications before wiring. — [ST pin tables](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), [Nucleo manual CN3 table](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf)
- Recommend a benchmark rather than immediate selection: the removable medium and 3.3 V native bus reduce prototype work, but cost and cold-cycle behavior may favor raw NAND.

### Gaps

- No exact ATP AF4GUDI-WACXM or Kingston SDCIT2/8GB electrical-current table or first-write timing bound found. Do not substitute Swissbit's electrical values for them.
- Exact minimum-capacity family write speeds, controller/firmware revisions, and long-term supply commitments need identification before production selection.
- No actual card or socket on this bench was inspected. A detailed final wiring/passives/rail-switch plan remains to make after choosing this experiment.

## How fast and low-energy could a cold photo save be?

### Takeaway

Native four-bit High Speed SD at 50 MHz offers a 25 MB/s raw bus ceiling and roughly 77 ms payload-only lower bound for this photo. Startup and durable completion, not the card's headline sequential rate, can determine the real advantage over raw NAND.

### Cited Findings

- At High Speed, the four-bit interface operates up to 50 MHz; UHS-I uses negotiated 1.8 V signaling while the card supply remains 2.7–3.6 V. — [Swissbit S-56u manufacturer datasheet, §7–8](https://www.mouser.com/datasheet/2/615/swissbit_02162021_S_56u_data_sheet-2013721.pdf)
- SD allows substantial write-busy intervals: up to 250 ms in the common block-gap case, and up to 500 ms for certain SDXC final/stop cases. These are operation limits, not a bound on a whole photo. — [SD Association physical specification v6.00, §4.6.2](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver6.00.pdf)
- Optional SD caching can release the busy line before writing slower nonvolatile media. Cache-supporting cards require power-off notification; flushing is bounded at one second under the documented feature contract. — [SD Association cache explanation](https://www.sdcard.org/press/thoughtleadership/applications-in-action-introducing-the-newest-application-performance-class/)
- A documented **Swissbit S-56u Rev1.02**, as an electrical example only, lists 50 mA typical HS write, 90 mA typical UHS write and 120 mA maximum write at 25°C; standby is 2 mA and background auto-read can consume 40 mA typical in HS mode. Its 250 ms power-up field describes supply ramp, not initialization. — [Swissbit electrical table §7.3](https://www.mouser.com/datasheet/2/615/swissbit_02162021_S_56u_data_sheet-2013721.pdf)

### Inferences

- Payload arithmetic: native 50 MHz ×4 /8 =25 MB/s, so 1,916,420 bytes /25 MB/s = **76.66 ms**; at 20 MB/s effective throughput = **95.82 ms**, at 10 MB/s = **191.64 ms**. These exclude initialization, command gaps, card busy, record commit and shutdown. At 50 MHz single-bit SPI, the raw transfer floor is **306.63 ms**, before these costs.
- Illustrative energy only: 3.3 V ×50 mA ×95.82 ms =15.81 mJ card energy during payload time. Every additional 100 ms at an assumed 50 mA adds16.5 mJ; at an assumed 200 mW MCU/board waiting load it adds another20 mJ. Actual current and busy overlap must be measured rather than double-counted. This is not a prediction for ATP or Kingston.
- A fast high-current card can consume less energy than a slow low-current part by allowing earlier whole-system shutdown, but the CR2032 rail must still survive its inrush and peaks. Current draw and latency tails need both oscilloscope/logic timing and Joulescope integration after the bench power boundary is fixed.
- SD initialization can overlap sensor work and image capture in RAM. However, the project's existing availability-before-exposure policy makes delayed capacity/catalog availability a **potential 50 ms startup conflict**, requiring either qualification or an explicit architecture/policy change. It is not proof that SD cannot meet the exposure requirement.
- Completely switch SD power off between shots; standby currents alone are incompatible with the 0.1 µA main-path target. Switch pull-ups/signals too or otherwise prevent back-powering.
- Completion means lower-layer transfer success, final card busy/status completion, durable record commit, and any enabled cache flush/power-off notification. DMA completion alone is insufficient. A private raw-sector object store remains possible; PTP export does not require FAT or exposing a host filesystem.

### Gaps

- Exact cold initialization duration is unmeasured. The historical project study cites the SD one-second ACMD41 initialization allowance; direct retrieval of the complete official document intermittently failed in this run, so do not present one second as typical or automatically additive to the photo path.
- No peak/inrush current or whole-cycle energy measured for any shortlisted card. No card is proven lower energy than the faster raw-NAND shortlist.
- No promise that a 25 MB/s bus yields 25 MB/s durable short writes; advertised 80–90 MB/s requires a faster negotiated interface and is a sustained benchmark, not a cold-photo result.

## Will retention and brownout behavior satisfy the project?

### Takeaway

True SLC and industrial pSLC are credible reliability candidates, but none of the reviewed currently purchasable cards has established the project's exact ten-year retention after 1,000 reuse cycles. Managed storage trades host ECC/bad-block implementation for less visibility into internal movement and errors.

### Cited Findings

- Swissbit explicitly specifies **ten years at beginning of life and one year at end of life** for its listed microSD families. This is not ten years at all wear levels. — [Swissbit product comparison](https://www.swissbit.com/en/products/flash-storage/industrial-microsd-card)
- The Swissbit S-600 profile claims true-SLC 100,000 P/E cycles and includes the same beginning/end-of-life retention distinction. — [Swissbit S-600/S-600u profile](https://www.swissbit.com/files/public/Documents/Flyer/Product_Profile_Swissbit_S-600.pdf)
- ATP's current wording is explicitly **data-at-rest** power-loss protection; it is firmware-based, not a claim of onboard energy storage that saves every in-flight write. — [ATP product specification](https://www.atpinc.com/products/industrial-microsd-usd-cards)
- A historical ATP 2012 Rev3.3 sheet lists 10 years at25°C after6,000 block P/E cycles for its old512MB/4GB variants, but those are **AF4GUDI-5ABXX**, not today's selected **WACXM**. It is only evidence that vendors can specify retention versus wear, not proof for the current part. — [Manufacturer-authored historical ATP specification §2.3](https://logicio.com/files/ATP%20Industrial%20grade%20microSD_spec_detail%20v3.3_20120920.pdf)

### Inferences

- The 200-photo/1,000-reuse workload is roughly383 GB host data before metadata and write amplification. A 4GB card offers substantial capacity headroom and much less than1,000 whole-card writes if each reuse still means200 photos; clarify whether the product's1,000-cycle requirement expands to filling a newly larger card. Do not translate host bytes to NAND P/E without controller/write-amplification knowledge.
- Factory-configured permanent pSLC is materially different from TLC with a temporary SLC write cache. The former is the appropriate high-endurance candidate; either still needs the card-specific retention curve and sudden-power-loss behavior.
- Host preallocation/raw-sector logging can reduce external metadata churn but cannot remove controller garbage collection, internal refresh, remapping or hidden write amplification. Protecting earlier photos must be tested with interrupted writes and cold restart; a marketing PLP label is insufficient proof.
- A controller may expose sector failure without offering the raw NAND/ECC evidence necessary to recover every readable bit or retire a particular physical slot. This differs from the project's raw-NAND recovery/retirement policy and needs an explicit mapping if managed media is adopted.
- Suggested qualification: frozen card revision; cold-cycle timing and energy distribution; nearly full and worn-card tests; immediate power removal after claimed durable success followed by independent readback; interruption during data/metadata writes to ensure old photos survive; written retention-versus-wear specification. These tests would follow approval of the prototype experiment, not part of this read-only research.

### Gaps

- Ten years unpowered at room temperature after the precise intended reuse workload is not proven for current ATP/Kingston/Swissbit exact SKUs.
- Data-at-rest protection scope, maximum persistent-sector corruption boundary, and whether corrupted data can be returned instead of discarded are card/controller-specific and undocumented in the available briefs.
- No refresh is possible during the specified unpowered shelf interval; powered background-refresh marketing cannot establish that requirement.
