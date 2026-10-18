# Faster camera storage alternatives

Research checked October 18, 2026. **Yes: better-fitting parts exist, and native 3.3 V would remove the prototype's current voltage-interface problem.** My first prototype recommendation is **Macronix MX35LF4GE4AD-Z4I**, a 4 Gbit quad-SPI part with internal ECC and an 8 × 6 mm WSON package. It does not support cache programming, but larger pages and faster programming reduce the modeled native-image save from about **638 ms to 264 ms**. Micron's **MT29F8G01ADAFD12-AAT:F** doubles capacity and models at **189 ms**, with BGA assembly, higher price and lifecycle questions. Genuine load-while-programming operation is documented in **Macronix parallel NAND**, including the 8 Gbit **MX60LF8G28AD-TI**, at the cost of substantially more wiring and host ECC. These are recommendations for investigation; **D-46's Alliance prototype selection remains unchanged pending the user's decision**.

## Faster pages deliver the simplest serial upgrade

The useful distinction is **programming throughput per byte**, not merely the advertised serial clock or the presence of a page “cache.” The current Alliance programs 2 KiB in 600 µs typical. Macronix programs 4 KiB in 400 µs; Micron programs 4 KiB in 240 µs with ECC enabled. None of those serial devices documents the desired next-page write pipeline. The following timings are datasheet values, not measurements of assembled hardware.

| Exact part and package | Capacity; supply | Data page; program time, typical / maximum | Cache programming; ECC |
|---|---|---|---|
| [Alliance AS5F14G04SND-10LIN](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.2_Jan2026-revised.pdf), 8 × 6 mm | 4 Gbit / 512 MiB; 1.8 V | 2 KiB; 600 / 700 µs | No documented overlap; internal ECC |
| [Macronix MX35LF4GE4AD-Z4I](https://www.macronix.com/Lists/Datasheet/Attachments/9047/MX35LF4GE4AD,%203V,%204Gb,%20v1.6.pdf), WSON8, 8 × 6 × 0.8 mm | 4 Gbit / 512 MiB; 2.7–3.6 V | 4 KiB; 400 / 800 µs | No; internal 8-bit ECC |
| [Micron MT29F8G01ADAFD12-AAT:F](https://datasheet.lcsc.com/datasheet/pdf/dd5a5d073373a605b97087884de5e38b.pdf?productCode=C22029726), BGA, 6 × 8 × 1.2 mm | 8 Gbit / 1 GiB; 3.3 V variant | 4 KiB; 240 / 600 µs, ECC enabled | No; internal 8-bit ECC |
| [GigaDevice GD5F8GM8UEYIG](https://download.gigadevice.com/Datasheet/DS-01328-GD5F8GM8UE-Rev1.0.pdf), WSON8, 8 × 6 mm | 8 Gbit / 1 GiB; 2.7–3.6 V | 4 KiB; 340 / 600 µs, ECC enabled | No; internal 8-bit ECC |
| [Macronix MX30LF4G28AD-TI](https://www.macronix.com/Lists/Datasheet/Attachments/8864/MX30LF4G28AD%2C%203V%2C%204Gb%2C%20v1.3.pdf), TSOP48 | 4 Gbit / 512 MiB; 2.7–3.6 V | 4 KiB; 320 / 700 µs without randomizer | **Yes, parallel x8**; host 8-bit ECC |
| [Macronix MX60LF8G28AD-TI](https://www.macronix.com/Lists/Datasheet/Attachments/8865/MX60LF8G28AD%2C%203V%2C%208Gb%2C%20v1.1.pdf), TSOP48 | 8 Gbit / 1 GiB; 2.7–3.6 V | 4 KiB; 320 / 700 µs without randomizer | **Yes, parallel x8**; host 8-bit ECC |

The E4 in the recommended Macronix serial part matters: the previously researched **MX35UF4G24AD** requires host ECC and is not an equivalent internal-ECC substitute. GigaDevice is an attractive larger WSON alternative, but its product page says 2 KiB while its current datasheet says 4 KiB; this report uses the datasheet and leaves that discrepancy for confirmation. No reviewed candidate provides separately adjustable VCCQ or a single supply range covering both 1.8 V and 3.3 V. Different voltage suffixes identify different devices. ([Macronix ECC distinction](https://www.macronix.com/Lists/Datasheet/Attachments/9033/MX35UF4G24AD,%201.8V,%204Gb,%20v1.4.pdf), [GigaDevice product record](https://www.gigadevice.com/product/flash/spi-nand-flash/gd5f8gm8ueyig))

## A full native photo models at 264 ms or less

Use the locked **1,916,420-byte native packed RAW10** payload, rather than the slightly smaller current capture-test frame. It occupies **936 × 2 KiB pages** or **468 × 4 KiB pages**. At an assumed achieved 50 MHz quad payload clock, loading the image takes 76.7 ms. For the serial devices, `save = payload transfer + page count × typical program time`.

| Device / modeled interface | Internal programming | Modeled save | Improvement over current Alliance quad |
|---|---:|---:|---:|
| Current Alliance, 50 MHz quad | 561.6 ms | **638 ms** | Baseline |
| Macronix 4 Gbit serial, 50 MHz quad | 187.2 ms | **264 ms** | 59% less time |
| Micron 8 Gbit serial, 50 MHz quad | 112.3 ms | **189 ms** | 70% less time |
| GigaDevice 8 Gbit serial, 50 MHz quad | 159.1 ms | **236 ms** | 63% less time |
| Macronix parallel, cache pipeline at assumed 50 MB/s | 149.8 ms programming floor | **About 150–155 ms** | Conditional, different interface |

These calculations assume pre-erased slots and omit command/status overhead, packing, ECC/OOB transfers, metadata, erase, readback, retries and software gaps. They are neither measured throughput nor worst-case bounds. Parallel randomizer use changes typical programming to 360 µs; pipeline boundaries and ECC computation also affect its result. **Faster 3.3 V storage is not automatically lower-energy storage**: measure complete-cycle energy, including MCU operation and regulator losses.

At 50 MHz single-bit SPI, transfer alone is 306.6 ms: modeled Macronix and Micron saves become approximately **494 ms and 419 ms**. Faster silicon therefore makes preserving quad transfers more valuable. With 2 MiB fixed slots, 4 Gbit gives 256 gross slots and 8 Gbit gives 512; an illustrative 20% reserve leaves **204 or 409**. Actual guaranteed capacity still depends on bad-block limits, metadata and retirement reserves.

## True cache programming changes the hardware architecture

The parallel Macronix parts explicitly use **15h cache programming**, separate cache-ready/array-ready status, and previous/current-page failure reporting. That lets the host load a following page while the array programs its predecessor. An achieved 25 MB/s bus loads 4 KiB in about 164 µs, already below the typical 320 µs programming interval. Micron's two-die serial device does not offer the same workaround: its die-selection operation is prohibited while any LUN is busy. ([Macronix cache-operation application note](https://www.mxic.com.tw/Lists/ApplicationNote/Attachments/2117/AN0268V2-Improving%20NAND%20Throughput%20with%20Two-Plane%20and%20Cache%20Operations.pdf), [Micron datasheet, die selection](https://datasheet.lcsc.com/datasheet/pdf/dd5a5d073373a605b97087884de5e38b.pdf?productCode=C22029726))

Parallel NAND needs eight data lines plus address/command/control signals, and firmware must provide the specified eight-bit ECC. **Nucleo FMC pin access, voltage compatibility and suitable ECC support have not been qualified.** This is a future architecture option, not a ready-to-wire alternative. By contrast, a native-3.3 V serial part matches the stock voltage of the already identified CN16 hardware-quad interface, avoiding both translation and changes to the boot-NOR bus. Pinout, carrier layout and actual clock speed still require verification. ([Current Nucleo interface assessment](../docs/prototype/alliance-nand-wiring.md))

## Procurement favors Macronix for the next prototype

Observed DigiKey inventory on October 18 exceeded 500 for the following exact parts. Prices are USD quantity one; inventory is not reserved, and these listings did not allow backorders.

| Exact order code | Observed stock | Unit price | Practical qualification |
|---|---:|---:|---|
| [MX35LF4GE4AD-Z4I](https://www.digikey.com/en/products/detail/macronix/MX35LF4GE4AD-Z4I/18110032) | 1,825 | $39.65 | WSON; strongest immediate prototype candidate |
| [MT29F8G01ADAFD12-AAT:F](https://www.digikey.com/en/products/detail/micron-technology-inc/MT29F8G01ADAFD12-AAT-F/10280730) | 794 | $79.13 | BGA; manufacturer lifecycle needs clarification |
| [MX30LF4G28AD-TI](https://www.digikey.com/en/products/detail/macronix/MX30LF4G28AD-TI/13420748) | 1,889 | $37.52 | Parallel; listed 768-piece purchase limit per 30 days |
| [MX60LF8G28AD-TI](https://www.digikey.com/en/products/detail/macronix/MX60LF8G28AD-TI/13420752) | 997 | $60.66 | Parallel; host ECC and pin plan required |

Macronix lists the serial E4 part as production/recommended. Micron's manufacturer record says **Contact Sales**, despite DigiKey's Active status. GigaDevice's 8 Gbit part is manufacturer-listed MP, but no verified DigiKey/Mouser stock was established; keep it on the watchlist. No exact-part evaluation board was qualified. ([Macronix portfolio](https://www.macronix.com/en-us/products/NAND-Flash/Serial-NAND-Flash/Pages/default.aspx), [Micron part record](https://in.micron.com/products/storage/nand-flash/slc-nand/part-catalog/part-detail/mt29f8g01adafd12-aat-f))

Other apparent bargains have specific drawbacks: **W25N04KVZEIRG** is manufacturer NRND; **TH58CVG3S0HRAIJ** has a distributor EOL/discontinuation notice; and Alliance's new **AS5F38G04SNDC-08LIN** is unstocked with a listed 20-week lead time and slower 750 µs typical programming. Those findings concern those exact parts, not every product from those vendors. ([Winbond status](https://winbond.com/hq/product/code-storage-flash/qspi-nand/w25n-kv/?__locale=en&partNo=W25N04KVZEIRG), [Kioxia listing](https://www.mouser.com/ProductDetail/Kioxia-America/TH58CVG3S0HRAIJ?qs=OlC7AqGiEDmkinos%252BEmSPw%3D%3D), [Alliance listing](https://www.digikey.ca/en/products/detail/alliance-memory-inc/AS5F38G04SNDC-08LIN/29926107), [Alliance Rev C timing](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_3V3_AS5F_QSPI_NAND_Flash_1Gb-2Gb-4Gb-8Gb_C-die_Ver1.0_Feb2026.pdf))

## Lifetime qualification remains separate from prototype selection

**None is yet qualified for our ten years unpowered at room temperature after 1,000 complete reuse cycles.** Macronix and GigaDevice advertise retention and endurance, but the combined conditions need evidence. Micron's explicit ten-year/85°C claim is for uncycled memory. Manufacturer reliability data must connect cycling, temperature and ECC assumptions before production selection. Macronix's detailed corrected-error reporting is useful for our slot-retirement policy, but it does not replace that qualification. ([Macronix reliability and ECC specifications](https://www.macronix.com/Lists/Datasheet/Attachments/9047/MX35LF4GE4AD,%203V,%204Gb,%20v1.6.pdf), [GigaDevice reliability specifications](https://download.gigadevice.com/Datasheet/DS-01328-GD5F8GM8UE-Rev1.0.pdf), [Micron retention conditions](https://datasheet.lcsc.com/datasheet/pdf/dd5a5d073373a605b97087884de5e38b.pdf?productCode=C22029726))

The next useful decision is whether to retain the already purchased Alliance for initial driver work or buy the Macronix serial E4 part to simplify wiring and improve save speed together. **My recommendation is the Macronix serial part for the next prototype**, with the GigaDevice 8 Gbit WSON as a sourcing follow-up. No purchase, hardware change or replacement selection was made by this review.
