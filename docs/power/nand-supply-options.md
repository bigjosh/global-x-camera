# Better-supplied 1.8 V NAND candidates

> **Historical procurement snapshot:** prices, availability and recommendations below are dated September 7–8, not reserved inventory. The [current requirement](../../spec.md) is at least 200 full-resolution VD56G3 packed-RAW10 photos; the earlier VD55G0 capacity and “hundreds” wording are superseded. Exact memory selection and usable-capacity qualification remain open.

**Checked September 7, 2026. Procurement research; schematic and BOM unchanged.**

**Recommendation: qualify Alliance AS9F14G08SA-45BIN first.** It doubles the current NAND capacity to 4 Gbit (512 MiB), retains the parallel x8 interface, and has a better combination of listed stock, price and replenishment outlook than the previously proposed ISSI IS34MW02G084-TLI. It requires a new BGA footprint and firmware geometry changes.

The subsequent [image-save time and energy assessment](nand-energy-impact.md) finds that the lower-voltage NAND is not automatically a whole-board energy improvement: slower transfers and erases can keep the MCU powered longer. This remains a supply/cost recommendation pending performance qualification.

The September 8 [microSD feasibility assessment](microsd-feasibility.md) evaluates a managed-card alternative, including exact stocked candidates, SDMMC2 pin changes, cold-start latency and battery-energy scenarios. It does not yet replace the NAND recommendation with a qualified production card.

**September 8 update:** the [quad NAND comparison](quad-nand-comparison.md) identifies **MT29F4G01ABBFDWB-IT:F** as a faster 4 KiB-page, on-die-ECC candidate with 8,131 units listed at Mouser. Its factory is not accepting orders, so it is an immediate-stock/performance candidate rather than a secure production replacement. Alliance remains the lower-cost parallel fallback. The user now requires capacity for **at least hundreds of photos**.

## Supply comparison

All three candidates below operate at 1.7–1.95 V and use parallel x8 SLC NAND. Counts and prices are distributor snapshots, not reserved inventory or firm delivery commitments. Prices are USD at quantity one, excluding shipping, taxes and tariffs.

| Exact ordering code | Capacity / package | Listed stock | Price | Supply assessment |
| --- | --- | --- | --- | --- |
| **Alliance AS9F14G08SA-45BIN** | 4 Gbit; 63-ball FBGA, 9×11 mm | **Mouser 837; DigiKey 165** | **$8.40 at Mouser** | Mouser estimates **20 weeks** for additional production. DigiKey is not accepting backorders. Best overall candidate to qualify. |
| **Macronix MX30UF4G28AD-TI** | 4 Gbit; 48-pin TSOP | **DigiKey 889** | **$23.59** | Production / for new design at manufacturer; DigiKey is not accepting backorders. Best alternative if retaining TSOP matters. |
| **Micron MT29F4G08ABBFAH4-AIT:F TR** | 4 Gbit; 63-ball VFBGA, 9×11 mm | **DigiKey 1,883** | **$30.53** | Largest immediate inventory in this shortlist, but no backorders. Manufacturer catalog search lists this exact AIT:F grade as **Contact Sales**; future orders need confirmation. |

Sources: [Alliance Mouser](https://www.mouser.co.za/en/ProductDetail/Alliance-Memory/AS9F14G08SA-45BIN?qs=2SLPxufLcgCzKPiphQPyug%3D%3D), [Alliance DigiKey](https://www.digikey.com/en/products/detail/alliance-memory-inc/AS9F14G08SA-45BIN/19910584), [Macronix DigiKey](https://www.digikey.com/en/products/detail/macronix/MX30UF4G28AD-TI/18110123), [Micron DigiKey](https://www.digikey.com/en/products/detail/micron-technology-inc/MT29F4G08ABBFAH4-AIT-F-TR/11591760), [Micron catalog](https://www.micron.com/products/storage/nand-flash/slc-nand/part-catalog). Mouser's accessible regional listing displays USD; confirm destination pricing when ordering.

Alliance marks its AS9F 1–8 Gbit portfolio as mass production, with no EOL plans and a stated **7+ years of supply continuity**. This supports the recommendation but is not a contractual delivery guarantee. [Manufacturer portfolio](https://www.alliancememory.com/flash-storage-product-portfolio/). Macronix lists its [4 Gbit family as production / for new design](https://www.macronix.com/zh-tw/products/NAND-Flash/SLC-NAND-Flash/Pages/spec.aspx?m=SLC+NAND&n=PM2823&p=MX30UF4G28AD).

## Alliance integration implications

The [archived Alliance datasheet](../../datasheets/memory/Alliance_AS9F_parallel_NAND_datasheet.pdf), Rev. 1.0 March 2023, specifies:

| Parameter | AS9F14G08SA-45BIN |
| --- | --- |
| Voltage / temperature | 1.7–1.95 V; −40 to +85°C |
| Geometry | 2048 data + 128 spare bytes/page; 64 pages/block; 4096 blocks |
| Guaranteed initial valid blocks | 4016 minimum |
| ECC requirement | Four-bit correction per 528 bytes; host ECC required |
| Program time | 300 µs typical / 700 µs maximum |
| Erase time | 3.5 ms typical / 10 ms maximum |
| Bus cycle / array read | 45 ns minimum cycle; 30 µs maximum array read |
| Normal program current | 20 mA maximum; typical unspecified |
| Read / erase current | 10 mA typical / 20 mA maximum |
| Cache program / POR current | 30 mA / 50 mA maximum |
| CMOS standby | 10 µA typical / 50 µA maximum |
| Package | 63-ball FBGA, 9×11 mm, 0.8 mm pitch, 1 mm maximum height |

See datasheet pp.2,4,25,28–30,53. Current limits refer to the stated operating modes, not a complete regulator transient model. The powered standby current exceeds the board's <1 µA shelf-OFF target: place NAND on the switched rail and prevent back-powering through its signals.

Compared with the recovered **MX30LF2G18AC-TI**, it preserves 2 KiB data pages and four-bit ECC strength, but doubles the spare area from 64 to 128 bytes and doubles block count. Preserve the FMC architecture while updating identification, addressing, ECC/OOB layout, bad-block markers and timing. Four-bit ECC strength alone does not establish compatibility of protected data/spare regions. Review partial-program restrictions; do not assume the old device's policy remains valid. Keep pre-erased blocks available for capture.

The 0.8 mm BGA pitch is relatively forgiving, but the footprint, fanout and four-layer escape still need review against actual fabricator rules. The official ordering table does not show a TSOP version of this Alliance part.

## Alternatives and capacity flexibility

**Macronix MX30UF4G28AD-TI:** retains the TSOP package class, but changes to **4096+256-byte pages and eight-bit ECC per 512+32 bytes**. Update page buffering, ECC/OOB policy, address geometry and timings; verify the full pin map before substitution. Its randomizer defaults off; enabling it imposes additional programming restrictions. [Archived current family datasheet, PM2823 Rev.1.3, February 4, 2026](../../datasheets/memory/Macronix_MX30UFxG28AD_datasheet_Rev1p3.pdf).

**Smaller capacity:** Macronix **MX30UF1G28AD-XKI-T**, 1 Gbit/128 MiB, showed **609 at Mouser, $14.69 each, 52-week replenishment estimate**. It requires BGA and eight-bit ECC, so it offers little advantage over the Alliance 4 Gbit option. [Exact listing](https://www.mouser.com/en/ProductDetail/Macronix/MX30UF1G28AD-XKI-T?qs=mELouGlnn3fGF1AUPPXHHQ%3D%3D).

**Larger capacity:** Alliance **AS9F18G08SA-45BIN**, 8 Gbit/1 GiB, showed **zero stock and a 20-week estimate**. Increasing beyond 4 Gbit did not improve the useful shortlist. [Exact listing](https://www.mouser.co.za/en/ProductDetail/Alliance-Memory/AS9F18G08SA-45BIN?qs=sGAEpiMZZMutXGli8Ay4kDfp5WGyMUNJAAC9gtlnVEM%3D).

**Serial NAND:** Winbond **W25N04KWZEIR**, 4 Gbit, 1.8 V, WSON-8 8×6 mm, showed **1,137 at DigiKey**, but **$33.93 each, a 126-unit purchase limit per 30 days, and no backorders**. It reduces signal count and provides on-chip ECC, but needs an SPI/XSPI storage backend replacing FMC. Its supply is not enough better to justify that change by itself. [Exact listing](https://www.digikey.com/en/products/detail/winbond-electronics/W25N04KWZEIR/17291063).

The next hardware step is qualification of the Alliance pin map, FMC/ECC behavior and power-domain placement. This research does not establish a tested replacement or authorize a purchase.
