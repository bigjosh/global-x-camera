# eMMC and managed soldered storage for the camera

## Is industrial pSLC eMMC a credible alternative?

### Takeaway
Yes: permanent-pSLC eMMC is a credible high-capacity, fast-write architecture to benchmark against raw SLC NAND. Its hidden controller and cold-start/shutdown behavior mean advertised throughput alone does not establish lower energy per safely saved photo.

### Cited Findings
- ISSI's IS21/22EF04GP/08GP family offers 4/8 GB pSLC eMMC. The manufacturer lists typical cache-OFF 8-bit SDR52 writes of 35/40 MB/s, DDR52 65 MB/s, and HS200 95/115 MB/s. Table 1.3 is labeled sequential burst/PSA status: these are benchmarks, not worst-case cold-save guarantees. VCC is 2.7–3.6 V; VCCQ supports 1.8/3.3 V. — [ISSI datasheet, §§1.1 and 1.3](https://www.issi.com/WW/pdf/21-22EF04GP-08GP.pdf)
- Swissbit EM-36 is preconfigured entirely as pSLC, in capacities 5–80 GB. EM-30 instead supports mixed TLC/pSLC configurations. — [Swissbit manufacturer profile](https://www.swissbit.com/files/public/Documents/Flyer/Product_Profile_Swissbit_EM-30.pdf)
- Kingston offers enhanced/pSLC firmware configurations, distinguishing them from ordinary native MLC/TLC operation. pSLC sacrifices capacity for faster programming and greater endurance. — [Kingston firmware configurations](https://media.kingston.com/pdfs/emmc/firmware-config_us.pdf)
- STM32N657 SDMMC supports eMMC 5.1 with 1-, 4-, and 8-bit buses; HS200 is subject to I/O speed limits, and HS400 is explicitly unsupported. Integrated DMA is available. — [ST DS14791 Rev 11, §3.18](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf)

### Inferences
- For the supplied native RAW10 size of 1,916,420 bytes, dividing by 35–40 MB/s gives **48–55 ms of benchmark-scaled write time**, not total save latency. A 4-bit 52 MHz SDR bus itself has a 26 MB/s ceiling before overhead, so an easy six-signal implementation cannot deliver the 8-bit benchmark unchanged.
- Six active bus signals suffice for 4-bit operation (CLK, CMD, DAT0–3); eight-bit adds DAT4–7. Power, grounds, decoupling, pullups and preferably reset remain additional wiring. This is SDMMC hardware, not SPI.
- Logical fixed photo slots and our own checksum/commit records can remain. Their addresses would be logical sectors: the device's FTL still relocates physical NAND and owns ECC, wear leveling and bad-block handling. The existing plan to salvage physical bad pages or retire physical image slots would need revision.

### Gaps
- Exact Nucleo header routing and board modifications have not been audited for SDMMC. No firmware or hardware was changed.
- No candidate's maximum per-photo write latency, garbage-collection stall, or cold-save energy has been measured.

## What limits cold-start latency, power efficiency, and durability?

### Takeaway
The useful comparison is cold power-on to verified nonvolatile commit and safe power-off, with total joules and peak current measured. Initialization may be comparable to, or longer than, the actual image transfer.

### Cited Findings
- NXP reports typical eMMC/SD initialization around 100–200 ms, with the specification allowing 1 s. This is broad platform guidance, **not a measurement or bound for a shortlisted part**; recovery after abrupt loss can lengthen startup. — [NXP i.MX8X erratum ERR050108](https://www.nxp.com.cn/docs/en/errata/IMX8X_1N95W.pdf)
- ISSI's cache defaults OFF; enabling it permits temporary cached data. For intentional shutdown, its documented power-off notification sequence requires waiting until busy deasserts before removing supplies. Sleep retaining VCCQ is different from removing both rails. — [ISSI datasheet, §§6.3 and 6.5](https://www.issi.com/WW/pdf/21-22EF04GP-08GP.pdf)
- Swissbit EM-30 lists typical 4/8/16 GB write currents of 42 mA at 3.3 V VCC plus 92 mA at 1.8 V VCCQ, measured with an 8-bit 200 MHz DDR interface. This totals about **0.304 W for storage alone** in that test; STM32N657 cannot use that HS400 operating point. Typical sleep currents are 20 µA VCC plus 60 µA VCCQ. — [Manufacturer datasheet hosted by Mouser, Table 8 and conditions](https://www.mouser.com/catalog/specsheets/Swissbit_01-12-2026_EM-30-series.pdf)
- Swissbit describes FTL remapping, static wear leveling moving cold data, and garbage collection consolidating pages. Consequently a logical sector allocation scheme does not expose or control all physical writes. — [Swissbit storage technology](https://www.swissbit.com/en/technology/storage-technology)
- Swissbit EM-30 specifies retention at 40°C of 10 years at beginning of life and 1 year at life end, defined as 3,000 P/E cycles. It does not establish ten unpowered years after our 1,000 full reuse cycles. — [Manufacturer datasheet, Table 14](https://www.mouser.com/catalog/specsheets/Swissbit_01-12-2026_EM-30-series.pdf)

### Inferences
- Faster writes can overcome higher active current, but startup, controller maintenance and shutdown energy can reverse the ranking. Neither idle current nor advertised MB/s identifies the winning part.
- Whole-device power gating removes retention-power demand; eMMC sleep current is irrelevant to our desired approximately 0.1 µA main-path off budget if isolation is correct.
- Begin storage initialization in parallel with sensor work where possible. However, if the camera must know that a FREE slot exists **before exposure**, an initialization longer than 50 ms creates a dependency requiring an early persistent capacity hint or policy change. Do not claim concurrency automatically solves the deadline.
- A conservative first firmware experiment uses write cache OFF, waits for data programming completion, commits/checks object metadata, sends power-off notification and waits for completion. Cache-enabled experiments must include flush latency and energy before declaring success.
- Ordinary consumer TLC eMMC is not excluded, but a permanent-pSLC industrial configuration with explicit power-failure guarantees is a better starting candidate for long retention and frequent cold cycling. Temporary SLC acceleration is not equivalent to persistent pSLC storage.

### Gaps
- No reviewed public source establishes the exact required retention **after 1,000 full-device reuse cycles**, with no power/refresh, for a specific candidate. Obtain vendor qualification evidence before selecting production storage.
- No verified peak-current specification, low-speed power measurement or exact cold initialization distribution for the shortlisted pSLC parts. The Swissbit example is not a prediction for ISSI or our operating mode.
- Need explicit vendor guarantee and destructive power-cut testing that previously committed photos survive interruptions during writes, erase, FTL maintenance and shutdown. Generic “power-fail protection” marketing cannot be assumed to provide capacitor-backed preservation of all in-flight user data.

## What concrete parts and prototype hardware are available?

### Takeaway
There are real industrial parts to pursue, but this review did not establish an in-stock, production-matched pSLC carrier ready to wire into the Nucleo. A BGA carrier or a socketed module with audited wiring is likely needed.

### Cited Findings
- **IS21EF04GP-JQLI**, industrial 4 GB pSLC, 100-ball 14×18 mm package, is listed as active by DigiKey; the checked listing showed zero stock and no backorders. Treat it as a candidate, not an immediate buying recommendation. — [DigiKey listing](https://www.digikey.com/en/products/detail/issi-integrated-silicon-solution-inc/IS21EF04GP-JQLI/24617480)
- Kingston lists industrial **EMMC04G-WT32** 4 GB MLC and 16 GB and larger TLC families, with enhanced/pSLC configuration availability. The nominal capacity of a native-mode part is not its resulting pSLC capacity. — [Kingston product selector](https://www.kingston.com/en/embedded/emmc-embedded-flash), [industrial flyer](https://media.kingston.com/pdfs/emmc/itemp-emmc_flyer_en.pdf?_=v1)
- Hardkernel offers assembled removable eMMC modules, including an 8 GB H-series module described as eMMC 5.0-or-later, 8-bit DDR/HS400. This confirms that module-based prototyping exists, but not industrial pSLC, fixed BOM, retention qualification or plug-in Nucleo compatibility. — [Hardkernel module](https://www.hardkernel.com/shop/8gb-emmc-module-h2/)

### Inferences
- Recommended architecture experiment: compare the chosen raw NAND with one industrial permanent-pSLC eMMC on SDMMC, using identical cold acquisition/save workloads. Measure rail energy, power peaks, startup distribution, durable commit and shutdown, then repeat near full capacity and after reuse.
- Keep the current Alliance selection until that comparison justifies a change. eMMC is the stronger large-capacity/simpler-firmware challenger, but raw SLC NAND retains better physical failure visibility and more predictable startup behavior.

### Gaps
- 500-unit availability was not established for any recommended pSLC eMMC. Stock references are transient, checked October 18, 2026.
- No verified industrial pSLC evaluation board/carrier with convenient headers was found in this focused review; module pinout and signal integrity need a separate audit.
