# Quad SPI NAND versus parallel x8 NAND

> **Historical comparison, September 8:** the numerical results below use VD55G0's 486,220-byte frame and the earlier unspecified “hundreds” requirement. The [current prototype](../../spec.md) selects VD56G3 with a 1,916,420-byte packed-RAW10 payload, at least 200 usable photos and configurable full-image readback. Recalculate complete save time, energy, reserves and capacity; the old approximately 800-photo scenarios and stock snapshots are not current qualification or a selected memory BOM.

**September 8, 2026. Design screening; no schematic, PCB or BOM substitution.**

**Recommendation:** investigate **Micron MT29F4G01ABBFDWB-IT:F** as the leading quad alternative for immediate availability and image-save performance. It provides on-die ECC and 4 KiB pages. Retain **Alliance AS9F14G08SA-45BIN** as the lower-cost parallel candidate with a better stated replenishment outlook. Quad NAND is attractive for routing and can improve cycle energy, but there is no general supply advantage across all quad parts.

Micron's 8,131-unit listed stock is substantial for prototypes or a limited run, but the distributor says the factory is currently not accepting orders. It is therefore not yet a secure production selection. Obtain a current exact-part datasheet and replenishment confirmation before freezing the design.

## Capacity for hundreds of photos

The user has clarified that storage must retain at least hundreds of photos. A native 644 × 604 RAW10 image contains **486,220 bytes** when packed without loss. No compression benefit is assumed.

| NAND density | Main-array capacity | Images with tight page allocation, before reserves | Images allowing 512 KiB each and reserving 20% of capacity |
| --- | ---: | ---: | ---: |
| 1 Gbit | 128 MiB | 275 | 204 |
| 2 Gbit | 256 MiB | 550 | 409 |
| 4 Gbit | 512 MiB | 1,101 | 819 |

The 512 KiB allocation can hold one image in four 128 KiB blocks or two 256 KiB blocks. The 20% allowance covers metadata, bad blocks, replacement blocks and free space as a planning assumption; actual guaranteed capacity depends on the device's good-block specification and final format. **Target 4 Gbit for roughly 800 photos with comfortable margin; 2 Gbit can still meet hundreds.** Retaining 16-bit containers instead of packed RAW10 would increase each image to 777,952 bytes and reduce these counts. Small FRAM/MRAM parts discussed earlier do not meet bulk capacity by themselves.

## Supply snapshot

Checked September 8, 2026. USD quantity-one prices; stock is listed inventory, not reserved, and pages can lag actual availability. All parts below operate from a nominal 1.8 V supply. The quad parts use eight-terminal packages approximately 8 × 6 mm; the parallel Alliance part uses 63-ball BGA, 9 × 11 mm.

| Exact ordering code | Interface / capacity | Listed stock | Unit price | Supply limitation |
| --- | --- | ---: | ---: | --- |
| **MT29F4G01ABBFDWB-IT:F** | Quad SPI / 4 Gbit | **Mouser 8,131** | **$33.18** | Factory not accepting orders; page also shows 53-week estimate |
| **W25N04KWZEIR** | Quad SPI / 4 Gbit | DigiKey 1,137 | $33.93 | Limit 126 units per 30 days; no backorders |
| **MX35UF4G24AD-Z4I8** | Quad SPI / 4 Gbit | DigiKey 704 | $20.33 | Limit 480 units per 30 days; no backorders |
| AS5F14G04SND-10LIN | Quad SPI / 4 Gbit | DigiKey 267 | $16.28 | Listed 20-week lead time |
| AS5F12G04SND-10LIN | Quad SPI / 2 Gbit | DigiKey 371 | $12.97 | Listed 20-week lead time |
| **AS9F14G08SA-45BIN** | Parallel x8 / 4 Gbit | **Mouser 837; DigiKey 165** | **$8.40** | Mouser 20-week estimate; DigiKey no backorders |

Sources: [Micron Mouser](https://www.mouser.com/en/ProductDetail/Micron/MT29F4G01ABBFDWB-ITF?qs=0lSvoLzn4L%2FCPhmn3pDt0Q%3D%3D), [Winbond DigiKey](https://www.digikey.com/en/products/detail/winbond-electronics/W25N04KWZEIR/17291063), [Macronix DigiKey](https://www.digikey.com/en/products/detail/macronix/MX35UF4G24AD-Z4I8/24773874), [Alliance 4 Gbit quad](https://www.digikey.com/en/products/detail/alliance-memory-inc/AS5F14G04SND-10LIN/13282916), [Alliance 2 Gbit quad](https://www.digikey.com/en/products/detail/alliance-memory-inc/AS5F12G04SND-10LIN/13282910), [Alliance parallel Mouser](https://www.mouser.co.za/en/ProductDetail/Alliance-Memory/AS9F14G08SA-45BIN?qs=2SLPxufLcgCzKPiphQPyug%3D%3D), [Alliance parallel DigiKey](https://www.digikey.com/en/products/detail/alliance-memory-inc/AS9F14G08SA-45BIN/19910584).

The lower-cost Alliance quad parts do not presently improve stock over its parallel part. Their detailed performance is not qualified by this report. Other checked 2 Gbit quad candidates were weakly supplied: W25N02JWZEIF showed four at DigiKey and MX35UF2G24AD-Z4I8 showed zero. These observations favor 4 Gbit in this search, not a general rule about density.

## Why quad can be faster than x8

The number of data wires alone does not set throughput. The Alliance x8 part's 45 ns cycle permits approximately **22.2 MB/s** ideal input. Quad at 50 MHz transfers **25 MB/s**; quad at 100 MHz transfers **50 MB/s**. These are interface ceilings, before host and command overhead.

More importantly, NAND programming takes hundreds of microseconds per page after the data arrives. The 4 KiB Micron and Macronix devices require **119 page programs per image**, versus **238** for 2 KiB Alliance and Winbond devices. Page size and internal programming time can outweigh bus width.

| Device | Main + spare page | Typical / maximum page program | Program current, typical / maximum | Error correction |
| --- | ---: | ---: | ---: | --- |
| Alliance AS9F14G08SA | 2048 + 128 B | 300 / 700 µs | Unspecified / 20 mA | Host, four bits per 528 B |
| Winbond W25N04KW | 2048 + 128 B | 250 / 700 µs | 25 / 35 mA | Internal eight-bit ECC |
| Micron MT29F4G01ABBFD | 4096 + 256 B | 240 / 600 µs, ECC enabled | 20 / 25 mA | Internal eight-bit ECC |
| Macronix MX35UF4G24AD-Z4I8 | 4096 + 256 B | 320 / 700 µs randomizer off; 360 / 740 µs on | 23 / 30 mA | **Host**, eight bits per 544 B |

**The Macronix device does not include on-die ECC.** Its datasheet p.6 explicitly requires host correction. The exact `-Z4I8` ordering suffix also changes column/plane-addressing requirements relative to `-Z4I`; verify the exact variant in the driver.

Primary evidence: [Alliance datasheet](../../datasheets/memory/Alliance_AS9F_parallel_NAND_datasheet.pdf), pp.2,4,25,28–30; [Winbond Rev.C](../../datasheets/memory/W25N04KW_datasheet_RevC.pdf), pp.17,38,59–63; [Micron Rev.F](../../datasheets/memory/Micron_MT29F4G01ABBFD_1v8_SPI_NAND_RevF.pdf), pp.1,8,34,46–48,55–56; [Macronix Rev.1.4](../../datasheets/memory/Macronix_MX35UFxG24AD_datasheet_Rev1p4.pdf), pp.5–7,46,60,63–64.

## Image-save and camera-cycle time

The following model uses pre-erased blocks, ordinary sequential programming and a conservative transfer allowance of the full data-plus-spare page. This is a bandwidth allowance, **not** an instruction to write reserved internal-ECC bytes. Actual firmware must send only legal user data/OOB. Serial results include 64 command clocks per page; parallel command overhead is omitted consistently with the earlier baseline.

| Device / bus setting | Transfer + serial commands | Internal programming, typical | Modeled write, typical programming | Modeled write using maximum programming |
| --- | ---: | ---: | ---: | ---: |
| Alliance x8, 45 ns cycle | 23.30 ms | 71.40 ms | **94.70 ms** | 189.90 ms |
| Winbond quad, 50 MHz | 21.02 ms | 59.50 ms | **80.52 ms** | 187.62 ms |
| Winbond quad, 100 MHz | 10.51 ms | 59.50 ms | **70.01 ms** | 177.11 ms |
| Micron quad, 50 MHz | 20.87 ms | 28.56 ms | **49.43 ms** | 92.27 ms |
| Micron quad, 83 MHz | 12.57 ms | 28.56 ms | **41.13 ms** | 83.97 ms |
| Macronix quad, 100 MHz, randomizer off | 10.43 ms | 38.08 ms | **48.51 ms** | 93.73 ms |
| Macronix quad, 100 MHz, randomizer on | 10.43 ms | 42.84 ms | **53.27 ms** | 98.49 ms |

These are **not measured save times or whole-operation worst-case bounds**. They exclude status polling, chip-select gaps, DMA/software costs, host ECC, metadata/commit records, readback verification, retries, erase and shutdown. No program-cache or two-plane overlap is assumed. The alternate data-only calculation is included in the generated JSON; it slightly reduces each time.

With acquisition completed at the 50 ms target and saving then performed serially, the modeled acquisition-plus-write totals are approximately **145 ms Alliance**, **120 ms Winbond at 100 MHz**, and **99 ms Micron at 50 MHz**, before the omitted work. These are not button-to-OFF predictions. Storage selection principally improves save/shutdown latency; it does not itself reduce exposure latency. Startup may overlap the capture preparation if firmware schedules it that way.

Verification matters. Winbond ECC reads add 45 µs typical / 65 µs maximum per page before transfer. Micron has a distinct, lower quad-read clock limit and approximately 90/170 µs ECC read timing in its electrical table; do not use its quad-write speed to predict USB download or verification. For ordinary page-at-a-time reads, the same full-spare allowance gives:

| Device and read bus | Extra full-image read time, typical / maximum array timing | Typical-program write plus full read, typical / maximum array-read timing |
| --- | ---: | ---: |
| Alliance, 45 ns x8 | Typical unavailable / 30.44 ms | Typical unavailable / 125.15 ms |
| Winbond, 100 MHz quad | 21.07 / 25.83 ms | 91.08 / 95.84 ms |
| Micron, conservative 30 MHz quad | 45.24 / 54.76 ms | 94.66 / 104.18 ms |

The two numbers in each row vary only array-read latency; they are not full-operation bounds. These calculations still omit read commands, CRC processing, host ECC and metadata. **Micron's write-only advantage largely disappears against Winbond if every photo is fully read back.** A durable commit needs a defined verification policy, so retain this distinction in the final camera cycle/energy budget. Keep pre-erased blocks ready; erase costs can otherwise erode the improvement.

**Micron documentation qualification:** the publicly accessible Rev.F manufacturer-authored PDF, hosted by authorized distributor Farnell, supports quad program-load `32h` and a general 83 MHz clock. Its electrical table limits quad reads to 37 MHz while revision history says 30 MHz; its front-page ECC-read limit conflicts with the later table. The distributor's manufacturer link currently resolves to a generic page and names a 3 V family. This report uses the explicit **1.8 V** PDF and a conservative **50 MHz write** planning point. Obtain an exact current revision and validate write/read clocks before hardware release.

## Energy and OFF current

At nominal 1.8 V, internal-program energy is `V × Iprogram × total_program_busy_time`:

| Device | NAND internal-program energy per image |
| --- | ---: |
| Alliance | **2.57 mJ using maximum current with typical time**; typical current unknown |
| Winbond | **2.68 mJ typical** |
| Micron, ECC enabled | **1.03 mJ typical** |
| Macronix | **1.58 mJ typical** randomizer off; **1.77 mJ** on, excluding host ECC |

The Alliance and quad values are not matched typical-to-typical measurements. In particular, Winbond is not established as a lower-energy NAND chip than Alliance. These numbers exclude loading, I/O switching, verification and erase; current during quad loading is not fully characterized by the program-current row.

The larger opportunity is earlier shutdown of the processor and other powered circuits. If that other load averages **200 mW** throughout saving, the modeled time reduction saves approximately:

- Winbond at 100 MHz: `(94.70 - 70.01) ms × 0.2 W = 4.94 mJ`.
- Micron at 50 MHz: `(94.70 - 49.43) ms × 0.2 W ≈ 9.1 mJ`.
- Macronix at 100 MHz: **8.29–9.24 mJ**, before host-ECC processing.

These are **conditional other-board energy savings for the write interval**, not total battery-energy savings. Full-image readback reduces the Micron advantage: comparing typical-program plus maximum-array-read models above, its other-board saving versus Alliance is about **4.2 mJ** at 200 mW, rather than 9.1 mJ. That is still a partial model, not a total or guaranteed saving. Firmware can sleep the MCU while NAND is busy and shut down the camera rails after capture, reducing the assumed 200 mW; verification, BCH processing and regulator efficiency also change the result. The storage-interface change needs measurement of current versus time through the full commit and shutdown sequence. Converter input demand must include the MCU plus memory pulses, not only memory average power.

All candidates should remain on a **switched 1.8 V rail**, avoiding continuous regulator quiescent current and making the OFF budget depend on shutdown leakage. Deep power-down alone does not establish compliance with the <1 µA battery target: Winbond specifies 2 µA maximum and Macronix 1 µA typical / 15 µA maximum at the NAND rail. Micron ordinary standby is 15 µA typical / 50 µA maximum. These rail currents are not directly battery currents; input power depends on conversion efficiency and regulator quiescent current. Ensure MCU signals cannot back-power the unpowered NAND. Power removal is allowed only after program completion, status checks and the chosen durable commit procedure.

## Integration and next decision

Quad reduces the storage interface to clock, chip select and four data signals, easing four-layer routing and removing the separate parallel latch/control wiring. It requires an STM32 XSPI storage driver instead of the current planned FMC backend. An eight-terminal package does not establish drop-in electrical, footprint or firmware compatibility across vendors.

Keep the dedicated NOR boot device. Review available XSPI instances, pin alternate functions, I/O supply banks and boot-flash conflicts before assigning a storage bus; no new pin map is established here. These candidates permit 1.8 V storage and do not themselves require the extra 3.3 V supply of ordinary microSD.

Micron and Winbond on-die ECC reduce host work, but firmware still owns bad-block management, ECC status handling, wear policy, allocation, CRCs, commit metadata and recovery from interrupted power. Poll readiness and explicitly configure protection/ECC after cold power-up. Never infer completed programming from DMA completion alone.

The immediate candidate to qualify is **Micron at a conservative 50 MHz quad-write clock**, with Winbond as another on-die-ECC option and Alliance parallel as the cost/replenishment fallback. Macronix remains a timing/price alternative if host BCH is acceptable. Bench qualification should measure one full-image save and verification at operating-voltage extremes, including cold startup, an aged/nearly-full device and interrupted writes. A current manufacturer specification and supply confirmation remain prerequisites to production selection.

Reproduce the arithmetic with [calculate_quad_nand_tradeoff.py](../../tools/calculate_quad_nand_tradeoff.py); generated results are in [quad-nand-calculations.json](quad-nand-calculations.json). Earlier baselines: [parallel NAND energy](nand-energy-impact.md), [supply comparison](nand-supply-options.md), [microSD feasibility](microsd-feasibility.md).
