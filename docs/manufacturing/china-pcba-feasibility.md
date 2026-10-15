# Chinese PCBA feasibility and sourcing

> **Historical feasibility snapshot:** this is September 28 research, not a current quote or supplier selection. The [current prototype](../../spec.md) now selects CAM-6G3-073CLR/VD56G3 and LTC3621; update exact-part sourcing and assembly assumptions accordingly. The later user-reported DigiKey prototype order has not been reconciled with this study and does not establish an assembled-board order. JLCPCB/PCBWay remain candidates.

**Current decision, October 14 — D-35:** the user will assemble the first prototype around **NUCLEO-N657X0-Q** and decide on a custom-PCB manufacturer/assembler later. This study is retained for future board work. Its JLCPCB Standard/PCBWay recommendation is not adopted as the current prototype build route; no vendor selection or factory order follows from the research.

**October 14 candidate check — selection deferred by D-35:** the earlier recommendation was JLCPCB Standard as the first custom-board fabrication/assembly design and quote target, with PCBWay as fallback. Retain that comparison for later. The current [exact STM32N657X0H3Q entry](https://jlcpcb.com/partdetail/STMicroelectronics-STM32N657X0H3Q/C42418080) remains Standard Only and requires X-ray inspection. [JLC's published assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities) list 0.3 mm minimum BGA pitch and a 70 × 70 mm Standard board/panel minimum with rails; the 85.60 × 53.98 mm camera outline needs suitable panel accommodation. [PCBWay sourcing](https://www.pcbway.com/pcb_prototype/Electronic_Components.html) supports supplier-purchased, consigned or mixed components. These capability checks do not establish current exact-part inventory, a successful board escape, layer count, mechanical fit, price or delivery. Select those from the completed design and quotes; the September stock counts below remain historical. No supplier commitment or order is selected here. Photographic flash is deferred under D-34/FD-06; status LED indications remain required.

**Checked September 28, 2026, America/New_York. Feasibility assessment; no order, vendor message or design upload.**

**Historical September recommendation, deferred by D-35: target JLCPCB Standard PCBA, with PCBWay turnkey as the fallback.** JLC has the exact STM32N657X0H3Q and a suitable 1.8 V, 4 Gbit Micron quad NAND in its assembly library. It also lists the exact proposed 1.8 V NOR, accelerometer and fine-pitch camera connector. Procurement, rather than BGA assembly capability, is the immediate limitation: the MCU source listing has only one unit, so a multi-board build needs replenishment, Global Sourcing or consignment.

This evaluates both the recovered schematic and the later 1.8 V / quad-NAND proposals. Those proposals have not yet been applied to the recovered schematic. The result supports a manufacturing route, not release of the existing incomplete PCB or unresolved schematic.

## Critical parts and actual inventory meaning

JLC library inclusion means a part-specific assembly entry exists. It does **not** establish inventory ready at their assembly warehouse. The counts below are explicitly identified as LCSC distributor/source inventory or JLC public-page source/presale data; none is reserved. A dated, sanitized extraction of the four key JLC pages is saved in [jlc-library-snapshot-2026-09-28.json](jlc-library-snapshot-2026-09-28.json).

| Function | Exact part and JLC code | Evidence and proposed route |
| --- | --- | --- |
| MCU | **STM32N657X0H3Q — C42418080** | [JLC entry](https://jlcpcb.com/partdetail/STMicroelectronics-STM32N657X0H3Q/C42418080): Extended, **Standard Only**, X-ray required. [LCSC](https://www.lcsc.com/product-detail/C42418080.html) shows **1**. JLC public-page source count is also 1, but presale count is 0. Do not plan a batch from this listing alone. |
| Preferred 1.8 V quad NAND candidate | **MT29F4G01ABBFDWB-IT:F — C20511638** | [JLC entry](https://jlcpcb.com/partdetail/C20511638): Extended, SMT, UPDFN-8 8×6 mm; source/presale counts **46/46**. [LCSC](https://www.lcsc.com/product-detail/C20511638.html) independently shows **46**, about $11.81 at quantity one. Exact non-TR listing; the separate TR listing is out of stock. |
| Proposed 1.8 V NOR | **W25Q128JWPIQ — C2689660** | [JLC entry](https://jlcpcb.com/partdetail/W25Q128JWPIQ/C2689660); [LCSC](https://www.lcsc.com/product-detail/C2689660.html) showed **6,044**. JLC's later source/presale snapshot is **6,109/6,077**. Exact desired WSON package; no SOIC substitution needed. |
| Original 3.3 V parallel NAND | **MX30LF2G18AC-TI — C136616** | [JLC entry](https://jlcpcb.com/partdetail/MXIC_Macronix-MX30LF2G18ACTI/C136616): source/presale counts **156/156**. Preserves the recovered parallel interface and TSOP48 footprint, but requires 3.3 V NAND and correctly supplied MCU I/O. |

The exact MCU is also listed at [DigiKey](https://www.digikey.com/en/products/detail/stmicroelectronics/STM32N657X0H3Q/25675974): **434 units**, $25.24 at one / $20.202 at ten in the refreshed US page. This is a concrete external source to request through JLC or PCBWay, not proof that JLC has approved a particular procurement order. Older regional search snippets showed conflicting quantities and were not used.

JLC supports [public-library parts, pre-orders, Global Sourcing and consignment](https://jlcpcb.com/help/article/pcba-parts-sourcing-instruction), with private parts usable after arrival. Its overview says 9–15 days for Global Sourcing; the [detailed ordering guide](https://jlcpcb.com/help/article/how-to-use-jlcpcb-global-sourcing-parts-service) says normally **9–20 business days**, plus review. Use the quoted order lead time and allow several weeks, rather than promising immediate assembly. No parts were purchased in this review.

## NAND choice and substitution scope

The Micron C20511638 is the same **1.7–1.95 V, 4 Gbit quad-SPI, on-die-ECC** candidate already examined in the [September 8 quad comparison](../power/quad-nand-comparison.md). At the prior 512 KiB/image allocation and 20% reserve assumption, it holds approximately **819 packed RAW10 photos**. [Manufacturer-authored 1.8 V datasheet](https://www.farnell.com/datasheets/3151594.pdf).

It is an appropriate *candidate*, not a drop-in replacement for the recovered parallel NAND. Implementing it requires the UPDFN footprint, a selected SPI/XSPI pin mapping and a compatible driver/storage format. The existing comparison records conflicting read-clock documentation and the need for an exact current specification. It also records a replenishment concern; 46 available units support prototype planning, not long-term production assurance.

If retaining parallel NAND is preferred, the original Macronix is library-covered. The preferred 1.8 V parallel **Alliance AS9F14G08SA-45BIN** has an [LCSC listing C20348774](https://www.lcsc.com/product-detail/C20348774.html) but was out of stock; use distributor sourcing rather than assuming local inventory. A 3.3 V NAND is not an electrically simple substitution into the all-1.8 V architecture.

## Coverage of the rest of the BOM

The recovered Flux BOM contains 47 grouped lines, including unselected passive values and non-placement items. This is a screen of critical components, not a completed, procurement-ready mapping of all 47 lines. Counts below are **LCSC** snapshots; each cited JLC page establishes library inclusion.

| Function | Exact candidate / code | LCSC count | Change needed |
| --- | --- | ---: | --- |
| Accelerometer | **LIS2DW12TR / C189624** | 18,634 | Exact ST part; Standard Only, X-ray required. [JLC](https://jlcpcb.com/partdetail/STMicroelectronics-LIS2DW12TR/C189624), [stock](https://www.lcsc.com/product-detail/C189624.html) |
| Camera receptacle | **BM28B0.6-30DS/2-0.35V(51) / C424571** | 1,265 | Exact Hirose part; Standard Only. Existing footprint still needs the correction already identified by design review. [JLC](https://jlcpcb.com/partdetail/HRS_Hirose-BM28B0_6_30DS_2_0_35V_51/C424571), [stock](https://www.lcsc.com/product-detail/C424571.html) |
| USB 3.3 V LDO | **TLV70033DDCR / C11337** | 98,700 | Replaces DDCT with a reel-quantity suffix change. [JLC](https://jlcpcb.com/partdetail/TLV70033DDCR/C11337), [stock](https://www.lcsc.com/product-detail/C11337.html), [TI ordering variants](https://www.ti.com/product/TLV700/part-details/TLV70033DDCR) |
| Accelerometer switch | **TPS22918DBVR / C131941** | 13,055 | Replaces DBVT with a packaging-quantity variant. [JLC](https://jlcpcb.com/partdetail/TexasInstruments-TPS22918DBVR/C131941), [stock](https://www.lcsc.com/product-detail/C131941.html) |
| Existing camera analog LDO | **TLV70028DDCR / C507266** | 545 | Exact recovered part; only retain if its input rail remains suitable. [JLC](https://jlcpcb.com/partdetail/TLV70028DDCR/C507266), [stock](https://www.lcsc.com/product-detail/C507266.html) |
| USB-C receptacle | **USB4105-GF-A-060 / C3025063** | 687 | Check suffix-specific dimensions, board thickness and mounting against current footprint. [JLC](https://jlcpcb.com/partdetail/GCT-USB4105_GF_A060/C3025063), [stock](https://www.lcsc.com/product-detail/C3025063.html) |
| Shutter button | **B3U-3000P / C963349** | 22,200 | Exact existing part; suitability for a 13.2 V battery-connected button circuit remains a circuit-rating review. [JLC](https://jlcpcb.com/partdetail/OmronElectronics-B3U3000P/C963349), [stock](https://www.lcsc.com/product-detail/C963349.html) |

Use genuine ST LIS2DW12TR, not similarly named HXY/MS devices returned by substitution searches. Retain exact connector mating compatibility. The R/T packaging substitutions above are the most straightforward changes; the USB suffix needs drawing verification.

The original **RV-3028-C8** RTC remains a sourcing gap in the verified local library. A [C7 variant](https://jlcpcb.com/partdetail/C3019759) is listed but changes footprint and was out of stock at LCSC; another C7 grade showed only 15. Source/consign the original or qualify a deliberate alternate instead of redesigning around that small stock snapshot.

Power conversion remains open: the recovered TPS62132/TPS62825 chain and the later direct 1.8 V plus 2.8 V proposal are different circuits. The [TPS62132RGTR listing C81563](https://www.lcsc.com/product-detail/C81563.html) was out of stock, while a linked RGTT packing variant showed 81. This is useful only if that regulator is retained. Do not choose a regulator merely because it is stocked: the input range, <1 µA OFF objective, transient current and shutdown sequencing remain requirements.

Passives can generally be selected from library parts once voltage rating, effective capacitance, tolerance, ESR, inductor saturation and physical dimensions are fixed. General availability is not a completed passive BOM. The debug Tag-Connect footprint is a board contact pattern, not a header requiring assembly; test points likewise need classification before a production BOM export.

The **CAM-5G0-079CLR** sensor/lens/flex module should be separately procured and plugged into the assembled Hirose receptacle after reflow. [ST module description](https://estore.st.com/en/cam-5g0-079clr-cpn.html). No library camera-module stock was established. Check the current ST module documentation before release; the product listing now references a September 2026 schematic revision newer than the recovered design.

## Manufacturing fit

| Requirement | Finding |
| --- | --- |
| MCU package | VFBGA264, 14×14 mm, **0.8 mm pitch**, as verified in the [MCU review](../review/mcu-review.md). Within published assembly capability; no MCU package change required. |
| Assembly service | **JLC Standard**, because the exact MCU, accelerometer and 0.35 mm camera connector are Standard-only entries. JLC publishes 0.3 mm minimum BGA pitch and 0.35 mm lead pitch for Standard; Economic's 0.4 mm lead-pitch limit is unsuitable for the camera connector. |
| Product size | 85.6×53.98 mm. Standard PCBA publishes a 70×70 mm minimum board/panel size: add breakaway rails or panelization while retaining the product outline. Simple 5 mm rails alone on the short dimension would not reach 70 mm. |
| Four layers | Plausible with 0.8 mm BGA and the limited used interfaces, but a complete escape and return-path layout is not yet proved. HDI is not automatically necessary. |
| Trace/via rules | JLC publishes 0.09/0.09 mm multilayer track/space, with 3 mil locally for BGA fanout. The proposed 0.10/0.10 mm routing and 0.20 mm via drill / 0.50 mm via pad are within the headline capability. Apply inner hole-to-copper clearance and solder-mask rules too. |
| CSI impedance | Controlled impedance is supported, with ±10% stated capability. Calculate the required differential geometry using the selected factory stackup; the old dielectric values were placeholders. Keep continuous return planes. |
| Via-in-pad | If needed, specify filled and copper-capped vias. Tenting does not replace this process. JLC offers filled/capped vias as standard on 6+ layers, making a six-layer comparison worthwhile if four-layer escape becomes awkward. |
| Inspection | Require the indicated BGA/leadless X-ray checks. Assembly inspection does not replace a programmed functional test. Provide SWD access and power/camera/memory test instructions. |

Sources: [JLC assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities), [PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities), [via covering](https://jlcpcb.com/help/article/pcb-via-covering). These are feasibility limits, not approval of an unrouted design. Prefer margin above minimum geometry where practical.

## Other houses and next implementation step

**PCBWay** is the strongest fallback: its [assembly service](https://www.pcbway.com/pcb-assembly.html) and [component sourcing policy](https://www.pcbway.com/pcb_prototype/Electronic_Components.html) explicitly support turnkey procurement from distributors such as DigiKey/Mouser, customer-specified suppliers and consigned/hybrid parts. Its [BGA capabilities](https://www.pcbway.com/pcb_prototype/BGA_Assembly_Capabilities.html) cover these packages. This is a way to have the MCU and NAND factory-soldered while retaining preferred parts; it is not evidence of a pre-stocked public library.

**Seeed Fusion** also supports [turnkey assembly](https://www.seeedstudio.com/pcb-assembly.html), but its [published guide](https://wiki.seeedstudio.com/Service_for_Fusion_PCB/) gives 0.4 mm lead pitch, so the 0.35 mm connector needs explicit manufacturing review. No ready-stock exact MCU/NAND combination was established there. It is a secondary quote option.

The historical custom-board recommendation, deferred by D-35, was a JLC Standard procurement/placement plan using the exact MCU, Micron quad NAND candidate and exact 1.8 V NOR. Secure a quoted path for MCU quantity before freezing the BOM. Finish the existing schematic/connector corrections, the storage-interface choice and power-tree selection, then map all passives and obtain the factory stackup. Have the house assemble the full SMT set, including the camera connector, rather than leaving its tiny pads for hand soldering. Compare ordinary four- and six-layer fabrication if routing warrants it.

Actual cost and delivery remain unquoted because the final BOM, board layout, panel, assembly quantity and test scope are not fixed. This assessment did not modify the schematic, original BOM or source connectivity.
