# Micron and Macronix serial NAND alternatives

## Which parts improve speed and voltage compatibility?

### Takeaway

The strongest Macronix candidate is MX35LF4GE4AD-Z4I: native 3.3 V and much faster per stored byte than the current Alliance, without cache programming. Micron MT29F8G01ADAFD12-AAT:F doubles capacity and is faster again, but costs more and its manufacturer lifecycle entry needs clarification. Research checked October 18, 2026.

### Cited Findings

- MX35LF4GE4AD: 4 Gb, 2.7–3.6 V, 4096-byte data pages, 64 pages/block, 2048 blocks; 8-WSON 8×6×0.8 mm. Program 400 µs typical/800 µs maximum; read 110 µs maximum; 133 MHz supported for WSON non-continuous transfers. Internal 8-bit ECC is enabled by default. No program pipeline: parameter-page program-cache timing is N/A, and the write sequence loads data then executes and waits. See pp. 33–40, 67–72. [Macronix PM2794 rev. 1.6](https://www.macronix.com/Lists/Datasheet/Attachments/9047/MX35LF4GE4AD,%203V,%204Gb,%20v1.6.pdf)
- Macronix lists MX35LF4GE4AD as production/recommended for new design. The currently listed 8 Gb serial part, MX35UF8GE4AD, is 1.8 V and under development; no production 3.3 V 8 Gb Macronix serial part was established. [Manufacturer serial-NAND portfolio](https://www.macronix.com/en-us/products/NAND-Flash/Serial-NAND-Flash/Pages/default.aspx)
- MT29F8G01ADAFD12-AAT:F: 8 Gb, native 3.3 V, 6×8×1.2 mm BGA. Manufacturer currently says **Contact Sales**, whereas DigiKey says Active; do not treat that discrepancy as established long-term production availability. [Micron part record](https://in.micron.com/products/storage/nand-flash/slc-nand/part-catalog/part-detail/mt29f8g01adafd12-aat-f), [DigiKey](https://www.digikey.com/en/products/detail/micron-technology-inc/MT29F8G01ADAFD12-AAT-F/10280730)
- Micron M70A: 4096+256-byte pages, two dies for 8 Gb. ECC-enabled programming is 240 µs typical/600 µs maximum (3.3 V Table 29, p.62); ECC-disabled 200/600 µs is not the appropriate comparison. No supported program cache. Die selection uses SET FEATURE, expressly prohibited while **any LUN is busy** (p.41), so the stacked dies do not provide usable interleaved programming. [Micron-authored automotive datasheet rev. I, distributor mirror](https://datasheet.lcsc.com/datasheet/pdf/dd5a5d073373a605b97087884de5e38b.pdf?productCode=C22029726)

### Inferences

- At the supplied native image size 1,916,420 bytes, both use 468 pages. Assuming pre-erased storage and 50 MHz quad transfers, Macronix takes approximately **187.2 ms programming + 76.66 ms transfer = 263.9 ms**; Micron **112.32 + 76.66 = 189.0 ms**. These are calculations, not bench results; exclude commands, metadata, status polling, checksums, extra ECC/OOB transfer and packing. Inputs come from the cited datasheets above.
- Both can exceed 200 photos before storage overhead. Fixed eight-block slots consume 2 MiB/photo, giving 256 gross slots on 4 Gb or 512 on 8 Gb; factory bad blocks, reserved journal blocks and retirement reduce this. Layout-specific capacity still needs verification.

### Gaps

- No qualified off-the-shelf evaluation/breakout board was found in this targeted search; this does not establish none exists.
- No genuinely pipelined program operation was established for either family. Larger pages and faster programming, rather than transfer/program overlap, provide their speed benefit.
- No single part with separately flexible logic voltage was established; these candidates are fixed 3.3 V versions.

## What reliability and ECC qualifications matter?

### Takeaway

The ECC-equipped E4 Macronix variant is materially different from the previously considered 24 variant. Neither family should be declared qualified for the project's combined 10-year retention after 1000 reuse cycles solely from headline specifications.

### Cited Findings

- Macronix lists 10-year retention and **typical** 60k-cycle endurance separately. Its 7Ch status command reports exact worst-segment errors (0–8; >8 uncorrectable), and warning threshold is configurable 1–8. Internal ECC detects nine/corrects eight errors. [PM2794, pp.5 and 35–38](https://www.macronix.com/Lists/Datasheet/Attachments/9047/MX35LF4GE4AD,%203V,%204Gb,%20v1.6.pdf)
- MX35UF4G24AD requires external 8-bit ECC; its parameter page says eight required ECC bits, whereas the E4 variant includes internal ECC. [MX35UF4G24AD PM2887 rev.1.4](https://www.macronix.com/Lists/Datasheet/Attachments/9033/MX35UF4G24AD,%201.8V,%204Gb,%20v1.4.pdf), [Macronix developer's Linux driver submission explaining suffixes](https://lists.infradead.org/pipermail/linux-mtd/2021-May/086601.html)
- Micron lists 100k P/E endurance and JESD47H retention qualification; its explicit ten-year/85°C claim is **uncycled**. Internal ECC corrects eight bits per 512-byte segment; seven/eight corrected bits signal a required refresh for retention. [Micron datasheet, pp.1 and 49](https://datasheet.lcsc.com/datasheet/pdf/dd5a5d073373a605b97087884de5e38b.pdf?productCode=C22029726)

### Inferences

- Macronix's detailed ECC counts fit the project's predictive slot-retirement policy particularly well. That does not by itself establish a retirement threshold or the retention guarantee.

### Gaps

- Need manufacturer qualification conditions connecting room-temperature retention to the intended cycle count. No such complete guarantee was verified in this review.
- Micron public catalog advertises serial SLC up to 32 Gb, but no additional exact orderable higher-capacity part with public command/timing evidence was located. [Micron industrial memory offering](https://assets.micron.com/adobe/assets/urn%3Aaaid%3Aaem%3Ae82ae163-0e9e-414d-b58f-42f39f0d053a/original/as/imm-memory-offering-flyer.pdf)

## Can we purchase prototypes or 500 units?

### Takeaway

Both exact candidates have observed distributor stock exceeding 500, but stock is a changing page observation, not a purchase commitment. Macronix is less expensive and easier to prototype physically.

### Cited Findings

- **MX35LF4GE4AD-Z4I**, DigiKey 1092-series listing: **1825 in stock**, $39.65 quantity one, $33.74890 quantity 100; active, tray. Backorders currently unavailable. [DigiKey exact part](https://www.digikey.com/en/products/detail/macronix/MX35LF4GE4AD-Z4I/18110032)
- **MT29F8G01ADAFD12-AAT:F**, DigiKey 557 listing: latest opened page **794 in stock**; search snapshots also showed 986/1122, so use 794 as observed and recheck at order time. $79.13 quantity one/$67.1545 quantity 100; backorders unavailable. [DigiKey exact part](https://www.digikey.com/en/products/detail/micron-technology-inc/MT29F8G01ADAFD12-AAT-F/10280730)
- **MX35LF4G24AD-Z4I8**, the host-ECC version, showed zero stock; not a substitute for the internal-ECC E4 candidate. [DigiKey](https://www.digikey.com/en/products/detail/macronix/MX35LF4G24AD-Z4I8/24773875)

### Inferences

- Macronix is the practical prototype candidate among these two vendors. Micron merits consideration if capacity and save time outweigh BGA assembly, cost and lifecycle uncertainty.

### Gaps

- Mouser candidate pages were found but reliable current stock could not be read. No 500-unit firm quote, delivery promise or long-term allocation was obtained.
