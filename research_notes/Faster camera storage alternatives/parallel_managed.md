# Parallel NAND with genuine cache programming

## Which parts genuinely overlap loading and programming?

### Takeaway

Macronix MX30LF4G28AD-TI (4 Gbit) and MX60LF8G28AD-TI (8 Gbit) are concrete native-3.3 V alternatives with documented cache programming. They require an x8 parallel interface and host ECC, so they are a substantially larger integration change than choosing a faster quad-SPI NAND.

### Cited Findings

- **MX30LF4G28AD-TI:** 4 Gbit/512 MiB; 4096+256-byte pages, 64 pages/block; 2.7–3.6 V single supply; TSOP48. Requires host correction of eight bits per 512+32 bytes. Typical program time is 320 µs, maximum 700 µs; enabling its optional randomizer changes these to 360/740 µs. The 20 ns minimum write cycle corresponds to a 50 MB/s ideal x8 interface ceiling. The datasheet expressly documents loading the next cache buffer while the prior data programs, using 15h instead of 10h and separate cache-ready/array-ready bits. — [Macronix PM2579 Rev. 1.3, §§1–2, 6-6, Tables 15–16](https://www.macronix.com/Lists/Datasheet/Attachments/8864/MX30LF4G28AD%2C%203V%2C%204Gb%2C%20v1.3.pdf)
- **MX60LF8G28AD-TI:** 8 Gbit/1 GiB; 4096+256-byte pages, 64 pages/block; 2.7–3.6 V single supply; TSOP48. Requires host eight-bit ECC/544 bytes. Programming is 320/700 µs typical/maximum, or 360/740 µs with randomizer. Genuine 15h cache programming is documented, including current/previous-page error status. Typical cache-busy time is 5 µs without randomizer, 30 µs with it; the maximum can be as long as page programming. It additionally supports two-plane and interleaved-die operations. — [Macronix PM2783 Rev. 1.1, §§2, 6-6, 6-15–18, Table 12](https://www.macronix.com/Lists/Datasheet/Attachments/8865/MX60LF8G28AD%2C%203V%2C%208Gb%2C%20v1.1.pdf)
- The traditional parallel interface needs eight bidirectional data lines plus CLE, ALE, CE#, RE#, WE#, WP# and R/B#; WP# can potentially be fixed rather than GPIO-controlled. Cache programming hides data loading behind array programming, but its status and termination sequence differ from ordinary page programming. — [Macronix AN0268 Rev. 2](https://www.mxic.com.tw/Lists/ApplicationNote/Attachments/2117/AN0268V2-Improving%20NAND%20Throughput%20with%20Two-Plane%20and%20Cache%20Operations.pdf)
- Both datasheets advertise ten-year retention and 60,000 typical P/E cycles, but expressly direct customers to request the reliability report for retention-test conditions. Neither read establishes our combined ten-year unpowered retention after 1,000 full reuse cycles. — [4 Gbit datasheet, p.6](https://www.macronix.com/Lists/Datasheet/Attachments/8864/MX30LF4G28AD%2C%203V%2C%204Gb%2C%20v1.3.pdf); [8 Gbit datasheet, p.6](https://www.macronix.com/Lists/Datasheet/Attachments/8865/MX60LF8G28AD%2C%203V%2C%208Gb%2C%20v1.1.pdf)

### Inferences

- These parts solve native 3.3 V operation and true write overlap together, but do not provide a separately flexible VCCQ domain: these exact variants are single-supply 3 V parts.
- Conditional timing model for the required **1,916,420-byte native RAW10 photo**: 468 4 KiB pages; at an assumed achieved 50 MB/s parallel transfer, main-data loading is approximately 38.3 ms and internal programming is 149.76 ms typical. Without overlap the ideal total is roughly 188 ms; with well-filled cache programming it can approach the programming floor, approximately **150–155 ms**, before ECC/metadata/software/commands, pipeline boundaries, readback and retries. This is a model, not a tested throughput or maximum bound. Sending OOB ECC adds bytes; host ECC generation must keep up. Derivation uses the documented page sizes, 320 µs typical programming and cache mechanism above.
- At an achievable 25 MB/s instead of 50 MB/s, a 4 KiB load is about 164 µs, still shorter than the typical 320 µs program interval. Thus the cache pipeline could largely hide the slower bus, conditional on controller support and software overhead.
- The larger part supports further plane/die overlap, but this review does not model that advantage. Using it would require allocation, address, error-status and power-failure review; do not claim a fourfold multiplier automatically.
- Fixed 2 MiB photo slots would give 256 gross slots on 4 Gbit and 512 on 8 Gbit. A purely illustrative 20% reserve leaves approximately 204 or 409 slots, respectively. Guaranteed bad-block limits and allocation metadata still determine the actual usable capacity.

### Gaps

- Nucleo FMC/NAND pin availability, voltage-domain compatibility, package pin map, bank conflicts and header convenience have **not been verified**. Do not present this as a ready-to-wire header solution.
- STM32N6 host-ECC capability and cost for this exact eight-bit/544-byte requirement have not been qualified. Hardware FMC presence alone is insufficient evidence.
- No dedicated, verified evaluation board/carrier for either exact part was established. TSOP48 is more accessible for a custom breakout than BGA, but generic TSOP/TSSOP adapters must match body width and footprint; a QFN48/TQFP48 breakout is not equivalent.
- The ten-year/1,000-cycle requirement needs manufacturer confirmation or applicable qualification data, including ECC assumptions. Powered refresh is not an acceptable substitute for our requirement.

## Can we buy them in useful quantities now?

### Takeaway

Both exact TSOP order codes have more than 500 pieces listed at DigiKey when checked October 18, 2026. The listings prohibit backorders, so current stock does not establish ongoing production supply.

### Cited Findings

| Exact ordering code | Listed inventory | USD quantity-one price | Qualification of availability |
| --- | ---: | ---: | --- |
| MX30LF4G28AD-TI | 1,889 | $37.52 | Purchase limit 768 per 30 days; no backorders. [DigiKey](https://www.digikey.com/en/products/detail/macronix/MX30LF4G28AD-TI/13420748) |
| MX60LF8G28AD-TI | 997 | $60.66 | No backorders; no purchase limit displayed in the latest retrieved page. [DigiKey](https://www.digikey.com/en/products/detail/macronix/MX60LF8G28AD-TI/13420752) |

- The older MX30LF4G18AC-XKI listing shows zero stock and recommends MX30LF4G28AD-XKI as its replacement. This favors researching current AD-generation parts over relying on older AC-family recommendations. — [DigiKey older part](https://www.digikey.com.mx/es/products/detail/macronix/MX30LF4G18AC-XKI/4968350)

### Inferences

- The 8 Gbit part is the most relevant demonstration that bigger, 3.3 V, genuine cache-programming NAND exists and is presently listed in production-sized quantities. At current one-off prices it is not a cheap prototype improvement.
- Prices and inventory changed from indexed search snippets during this review. The table uses the final retrieved United States/USD product pages, not older search snippets; reconfirm before purchase.

### Gaps

- Inventory is not reserved, and distributor pages may lag. No order, allocation, supplier contact, evaluation-kit purchase or hardware change was performed.
- Managed eMMC/SD was intentionally not expanded after the coordinator narrowed the task to a confirmed cache-programming parallel alternative. No managed part is proposed as satisfying the ten-year offline retention requirement.
