# Prototype parts and camera research

Updated October 18, 2026. This is the retained procurement and feasibility record with subsequent prototype decisions. The approved prototype uses **NUCLEO-N657X0-Q / STM32N6, CAM-6G3-073CLR / VD56G3 at 73° diagonal field of view, and four series CR2032 cells feeding LTC3621 at 5.0 V**. The final D-46 choice is existing Alliance NAND on Arduino headers with bit-banging allowed; D-47 retains downstream regulators while excluding unnecessary capture loads. The [consolidated assembly guide](nucleo-assembly-guide.md) governs current rework. Exact regulator hardware is still to confirm, and this record claims no performed modification or qualified leakage. The recovered KiCad design still contains older camera/power circuitry. See the [current specification](../../spec.md) and [decision register](../decisions/2026-10-13-project-baseline.md).

**The user confirmed the DigiKey order was placed** in the [review transcript, Message 014](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md). Its exact line items, quantities, substitutions and delivery dates are **unknown**. Message 004 explicitly says NUCLEO-N657X0-Q had been added to the cart; Messages 007 and 013 contain recommendations, not an exported paid order. Reconcile receipts before buying duplicates.

## Current decisions and boundaries

| Item | Status at consolidation |
| --- | --- |
| Processor | STM32N6 active; Himax abandoned. NUCLEO-N657X0-Q is the development board identified by the user. |
| First prototype assembly | **D-35, October 14:** the user will assemble it around NUCLEO-N657X0-Q. Custom-PCB manufacturer/assembler selection is deferred; prior JLCPCB/PCBWay studies remain background. |
| Exposure-time control | **D-36, October 14:** potentiometer feeding an MCU ADC, sampled and applied before acquisition. Exact part, resistance/taper, ADC pin, supply/reference and time range/mapping are TBD. Include settling/conversion/configuration in the 50 ms budget and meet the existing OFF-current target. |
| Prototype camera | **CAM-6G3-073CLR**, monochrome VD56G3, **73° diagonal**. The 84° module is not the selected substitute. |
| Power source and regulator | Four CR2032 cells in series through LTC3621; D-47 selects **5.0 V into the Nucleo's retained downstream tree**. Exact delivered regulator/evaluation board, supporting components and RUN/HOLD integration remain to confirm; follow the [assembly guide](nucleo-assembly-guide.md). |
| Finished-product thickness | Target ≤5 mm; a thicker functional prototype is acceptable. A module below 5 mm does not prove the complete PCB/enclosure stack meets that target. |
| Capture and storage | Exposure starts within 50 ms of a shutter press from fully powered off. At least 200 full-resolution uncompressed packed-RAW10 photos between downloads. Saving and shutdown are later timed phases. |
| Future camera direction | VD5943 with potentially custom compact optics remains research, not an approved replacement for the prototype camera. |
| Production availability | The earlier screening question was 500 complete, fitted modules available now. No documented supplier commitment closes that gate. Bare sensor stock and factory lead time are different evidence. |

These decisions are recorded in the [decision review](../../reports/Global%20X%20Camera%20decision%20review.md). The direct camera/battery/regulator choice is [review transcript, Message 020](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md). They do not establish measured performance, a finished driver, a revised CAD design or a released bill of materials.

## Development hardware and shopping record

**Build route:** use the Nucleo as the MCU base and reconcile the already ordered modules/adapters before finalizing their wiring and power/control connections. The user will assemble this prototype. This decision does not confirm the order's exact contents or require a new custom camera PCB or factory assembly selection.

The normal ST promodule connection is **camera 30-pin board connector → STEVAL-CAM-M0I1 P-board → 22-pin CSI cable → Nucleo camera connector**. A promodule does not plug directly into the Nucleo's 22-pin cable connector. The adapter supplies the camera rails; its included 22-pin, 10 cm FFC should be accounted for before adding duplicate cables. Verify cable contact orientation and the exact adapter revision before connecting power. [ST P-board](https://www.st.com/en/evaluation-tools/steval-cam-m0i.html)

| Part | Purpose and status | Purchase or source link |
| --- | --- | --- |
| **NUCLEO-N657X0-Q** | Main development board; user explicitly added it to the cart. Installed MCU is an STM32N657. Receipt not retained here. | [ST board](https://www.st.com/en/evaluation-tools/nucleo-n657x0-q.html) |
| **STEVAL-CAM-M0I1**, DigiKey 497-STEVAL-CAM-M0I1-ND | Recommended ST promodule adapter. Earlier shorthand STEVAL-CAM-M0I identifies the family; use the actual order code when reconciling the order. | [DigiKey](https://www.digikey.com/en/products/detail/stmicroelectronics/STEVAL-CAM-M0I1/24743059) |
| **CAM-6G3-073CLR** | Selected prototype camera. The Message 007 recommendation was one unit for comparison; Message 020 subsequently selected it. Purchased quantity is unknown. | [DigiKey](https://www.digikey.com/en/products/detail/stmicroelectronics/CAM-6G3-073CLR/24738685) |
| CAM-5G0-079CLR | Earlier recommendation was two units for the recovered VD55G0 baseline. Superseded as the prototype target; retain only as a comparison or if already ordered. | [DigiKey](https://www.digikey.com/en/products/detail/stmicroelectronics/CAM-5G0-079CLR/24737792) |
| B-CAMS-IMX | Optional IMX335 color rolling-shutter reference camera for software bring-up. Supplied lens/cable; does not meet the monochrome/global-shutter production requirement. | [DigiKey](https://www.digikey.com/en/products/detail/stmicroelectronics/B-CAMS-IMX/24737934) |
| CAM-5943-081CLR | Optional 5 MP monochrome/global-shutter bench camera for future research; far too tall for the finished-product target. | [DigiKey](https://www.digikey.com/en/products/detail/stmicroelectronics/CAM-5943-081CLR/29749370) |
| STEVAL-EVK-U0I | Separate ST PC/USB evaluation route, useful if independent sensor evaluation is needed. It is an alternative test setup, not established as necessary for Nucleo bring-up. | [ST EVK Main](https://www.st.com/en/evaluation-tools/steval-evk-u0i.html) |

The earlier search did not verify **STEVAL-CAM-G0** as an orderable board. The larger VD55G0 sensor board was **STEVAL55G0MBI1**; do not substitute an unverified name in a purchase list.

### Full bench-cart recommendation

[Review transcript, Message 007](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md) proposed one STEVAL-CAM-M0I1, two CAM-5G0-079CLR, one CAM-6G3-073CLR, one B-CAMS-IMX and one MIKROE-3780, plus the following. The approximately **$535 beyond the Nucleo** estimate was dated October 12 and preceded the extra Alliance NAND recommendation. These quantities and prices preserve the recommendation; they are not confirmed purchases or current prices.

| Recommended quantity | Exact item | Purpose / October 12 unit-price observation |
| ---: | --- | --- |
| 1 | [STEVAL-MKI179V1](https://www.digikey.com/en/products/detail/stmicroelectronics/STEVAL-MKI179V1/7561642) | LIS2DW12 orientation accelerometer breakout; $18.82. |
| 1 | [RV-3028-C7-EVALUATION-BOARD](https://www.digikey.com/en/products/detail/micro-crystal-ag/RV-3028-C7-EVALUATION-BOARD/10431075) | Timestamp/backup experiments; $17.47. This C7 evaluation board is distinct from the recovered BOM's RV-3028-C8; exact package/device integration still needs reconciliation. |
| 1 | [DC1863A](https://www.digikey.com/en/products/detail/analog-devices-inc/DC1863A/4963636) | LTC3621 evaluation; $117.13. Initial deferral in Message 005 was superseded by its inclusion in Messages 007/011. |
| 1 | [NRF-PPK2](https://www.digikey.com/en/products/detail/nordic-semiconductor-asa/NRF-PPK2/13557476) | Capture/save current and energy experiments; $113.74. |
| 2 | [Adafruit 4474 USB-A–USB-C cable](https://www.digikey.com/en/products/detail/adafruit-industries-llc/4474/11587355) | Nucleo ST-LINK and target USB; $4.95 each. |
| 2 | [Adafruit 592 micro-USB cable](https://www.digikey.com/en/products/detail/adafruit-industries-llc/592/10669955) | PPK2 data and supplementary power; $2.95 each. |
| 1 each | [Adafruit 1950 female–female](https://www.digikey.com/en/products/detail/adafruit-industries-llc/1950/6827084) and [1954 male–female](https://www.digikey.com/en/products/detail/adafruit-industries-llc/1954/6827087) jumper packs | Peripheral/control wiring; $1.95 per pack. |
| 1 | [Adafruit 64 breadboard](https://www.digikey.com/en/products/detail/adafruit-industries-llc/64/7241427) | Low-speed sensor/control wiring; $4.95. Not a CSI or high-speed quad-NAND interconnect qualification. |
| 4 | [DKS-CR2032H wired holders](https://www.digikey.com/en/products/detail/digikey-standard/DKS-CR2032H/21379579) | Four-cell experimental series fixture; $1.78 each. They are not the production enclosure's battery contacts. |
| 12 | [Panasonic CR2032](https://www.digikey.com/en/products/detail/panasonic-energy/CR2032/31939) | Three experimental battery sets; $0.40 each. Ground-shipping restriction was reported in the shopping discussion. |
| 1 each | Pomona **1166-36-0** black and **1166-36-2** red; [black lead listing](https://www.digikey.com/en/products/detail/pomona-electronics/1166-36-0/736125) | Banana-to-alligator leads for the regulator/bench supply; approximately $10 each. |
| Conditional | [B&K 1550](https://www.digikey.com/en/products/detail/b-k-precision/1550/1936375) | Approximately $215 alternative if an adjustable current-limited bench supply was not already owned. Soldering tools and multimeter were also assumed available. |

**PPK2 measurement boundary:** use its documented **0.8–5 V** range on an appropriate regulated rail, never directly on the approximately 12 V four-cell pack. The kit includes measurement leads but the shopping discussion identified USB cables separately. Regulated-rail measurements omit upstream converter losses and other pack-side loads; they are not automatically complete battery energy. A 100 nA whole-main-path leakage test needs suitable fixture resolution and leakage characterization. [Nordic getting-started requirements](https://www.nordicsemi.com/Products/Development-hardware/Power-Profiler-Kit-2/GetStarted?lang=en)

The Nucleo includes its programmer and boot NOR; these were not extra bench-cart requirements. It has **no SD socket**; STM32N6570-DK has one. The discussion records 64 MiB onboard Nucleo NOR primarily for firmware, not a qualified replacement for the image store. [Review transcript, Message 013](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md), [Nucleo manual](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf), [Discovery manual](https://www.st.com/resource/en/user_manual/um3300-discovery-kit-with-stm32n657x0-mcu-stmicroelectronics.pdf)

### Software and electrical qualification

ST's [STM32N6 image-classification example](https://github.com/STMicroelectronics/STM32N6-GettingStarted-ImageClassification/blob/main/README.md) documents Nucleo support and a USB/UVC display path. A separate LCD is not necessary for that example. Its supported-camera list must be checked against the exact example revision; support for a sensor family does not establish a ready-to-flash binary for every promodule/board combination. B-CAMS-IMX was proposed as a reference because that example documents IMX335 support, not because it replaces the selected camera.

For CAM-6G3-073CLR, confirm VD56G3 register initialization, CSI lane/polarity configuration, resolution, clocks, exposure control and repeated cold starts on the actual Nucleo/adapter. Do not copy the old VD55G0's rail timings without checking the selected sensor. [VD56G3 datasheet](https://www.st.com/resource/en/datasheet/vd56g3.pdf)

The VD55G0 comparison has two specific cautions: ST describes a rare P-board power-sequence boot failure as acceptable for evaluation but unsuitable for production; an N6/P-board CSI polarity mismatch can be corrected through sensor configuration. Neither is evidence that arbitrary CSI modules are interchangeable. [ST power-sequence discussion](https://community.st.com/imaging-sensors-49/steval-cam-m0i-compatible-with-vd55g0-149900), [ST CSI polarity discussion](https://community.st.com/imaging-sensors-49/is-p-board-steval-cam-m0i-compatible-with-stm32n6-discovery-kit-147814). [STSW-IMG505](https://www.st.com/en/embedded-software/stsw-img505.html) advertises VD55G0 embedded drivers, but the research did not verify a turnkey Nucleo binary.

For later VD5943 work, [STSW-VD5943](https://www.st.com/resource/en/data_brief/stsw-vd5943.pdf) explicitly covers STM32N6, CAM-5943 and P-board hardware. Exact Nucleo project integration remains to be validated.

## Camera and lens comparison retained from procurement research

The optical dimension gate below concerns **module height**, not all dimensions. A reasonable focus range must be defined for the intended photographs; a manufacturer's depth-of-field figure is not proof of acceptable image quality under every lighting condition or blur criterion.

| Sensor/module | Mono / shutter | Resolution | Diagonal FOV | Head and overall height | Published fixed-focus depth of field | Disposition |
| --- | --- | --- | ---: | --- | --- | --- |
| **VD56G3 / CAM-6G3-073CLR** | Mono / global | 1124 × 1364 | **73°** | Head 6.5 × 6.5 × **4.68 mm**; overall 12.4 × 8 × 4.68 mm | **43 cm–∞** | **Selected prototype**; F2, EFL 3.03 mm. |
| VD56G3 / CAM-6G3-084CLR | Mono / global | Same | 84° | 6.5 × 6.5 × **3.98 mm** head | 30 cm–6 m | Thinner comparison only; changes locked FOV. |
| VD56G3 / CAM-6G3-152CLR | Mono / global | Same | 152° | 9 × 9 × **7.15 mm** head | 14.4 cm–∞ | Wide-angle comparison; fails height gate. |
| VD55G0 / CAM-5G0-079CLR | Mono / global | 644 × 604 | 79° | 5 × 5 × **2.8 mm** head; overall 11.65 × 8 × 2.8 mm | 13.5 cm–∞ | Recovered baseline, superseded for prototype. |
| VD55G0 / CAM-5G0-158CLR | Mono / global | Same | 158° | 7 × 7 × **5.72 mm** head | 5.5 cm–∞ | Fails height gate. |
| VD5943 / CAM-5943-081CLR | Mono / global or rolling | 2560 × 1984 | 81° | Overall **23.7 × 14 × 23.1 mm** | 64.1–227.9 cm | Future sensor bench evaluation; F2.2, EFL 4.2 mm. |
| VD5943 / CAM-5943-155CLR | Mono / global or rolling | Same | 155° | Overall **25.2 × 17 × 26.3 mm** | 49 cm–∞ | Future wide-angle evaluation; F2, EFL 2.9 mm. |
| VD1943 / Leopard LI-VD1943-MIPI-062H-AF | RGB-NIR / global or rolling | 2560 × 1984 | 75° | Compact mobile module; no qualified VD5943 height established | Autofocus 10 cm–∞ | Related-family integration lead, not native mono or the selected fixed-focus module. |
| IMX335 / B-CAMS-IMX | Color / rolling | 5 MP | Not a decision criterion here | Development assembly | Not qualified here | Optional software reference; fails mono/global gates. |

Sources: [ST CAM-56G3 DB5264 Rev 3, December 2025, table 2](https://www.st.com/resource/en/data_brief/cam-56g3.pdf#page=3); [ST CAM-55G0 DB5266 Rev 2, April 2025, table 2](https://www.st.com/resource/en/data_brief/cam-55g0.pdf#page=3); [ST CAM-5943 DB5793 Rev 1, June 2026](https://www.st.com/resource/en/data_brief/cam-5943-081clr.pdf); [Leopard datasheet, draft September 2026](https://leopardimaging.com/wp-content/uploads/2026/09/LI-VD1943-MIPI-062H-AF_Datasheet.pdf). Earlier distributor-hosted VD55G0 briefs showed different height/focus figures; use the later ST revision above.

The selected module's 4.68 mm height leaves little room within a 5 mm finished assembly. PCB placement, recessing/cutouts, lens protrusion, flex routing, connector height and enclosure skins require a physical stack-up check. The available CAM-6G3 STEP must be confirmed as the exact selected module; its earlier use as a stand-in for CAM-5G0 did not validate the old camera's connector orientation.

### Resolution, storage and energy consequences

Packed RAW10 payloads, calculated as width × height × 10 / 8, are **486,220 bytes for VD55G0**, **1,916,420 bytes for VD56G3**, and **6,348,800 bytes for VD5943**, before padding and metadata. A 4 Gbit / 512 MiB device gives 280 tightly packed VD56G3 payloads before overhead; 2 MiB allocation and a 20% overall reserve give 204 planned slots. These are capacity models, not guaranteed usable-photo counts. The old approximately 800-photo estimate in September NAND notes used VD55G0 and must not be applied to the selected module.

The [earlier VD56G3/VD5943 comparison](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/6acd261d-d2f0-83ea-bac0-a86e92a61bc2.md) records 120 mW versus 308 mW typical sensor power at 60 fps under each datasheet's test conditions. Those streaming numbers do not establish energy per cold-start photograph. VD5943 adds resolution and rolling-shutter/HDR modes; the higher data volume affects buffering, save energy and latency. Measure complete capture/save cycles before selecting it on image-quality or energy grounds.

### Dated availability observations

These are retained **October 12, 2026 retrieval observations**, not reservations or an October 13 stock refresh. Distributor pages and search indexes differed in freshness. Prices were quantity-one USD, excluding delivery, taxes and possible tariffs.

| Exact part | Retained distributor observation | What it establishes |
| --- | --- | --- |
| STEVAL-CAM-M0I1 | DigiKey 50, $39.53 | Prototype adapter stock observation. |
| CAM-6G3-073CLR | Earlier DigiKey retrieval 25, $21.44; Message 017 comparison recorded 24 and Mouser 8 | Changing small prototype quantities; no 500-unit commitment. |
| CAM-6G3-084CLR | Message 017 recorded DigiKey 50 and Mouser 41 | Comparison only; not a synchronized or reserved total. |
| CAM-6G3-152CLR | Message 017 recorded DigiKey 0 | No immediate-stock case established. |
| CAM-5G0-079CLR | DigiKey 19, $17.51; Mouser opened page 32 with maximum 10, while another index showed 29 | Quantities cannot be treated as a synchronized total. |
| CAM-5G0-158CLR | DigiKey 20; maximum purchase quantity 20 per 30 days | Far below 500. Mouser index counts were not a fresh verified page. |
| CAM-5943-081CLR | DigiKey 54, $64.99 | Bench prototypes possible at the time. |
| CAM-5943-155CLR | DigiKey 58, $64.99 in the preserved project chat | Same limitation. |
| B-CAMS-IMX | DigiKey 33, $87.66 | Optional reference stock observation. |

Distributor links are in the hardware table, [review transcript, Message 017](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md), and the [preserved VD5943 chat](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/6acd261d-d2f0-83ea-bac0-a86e92a61bc2.md). VD55G0 sources: [079 Mouser](https://www.mouser.com/en/ProductDetail/STMicroelectronics/CAM-5G0-079CLR?qs=IKkN%2F947nfBQP2mn8S1VOA%3D%3D), [079 ST store](https://estore.st.com/en/cam-5g0-079clr-cpn.html), [158 ST store](https://estore.st.com/en/cam-5g0-158clr-cpn.html). The ST store said in stock without a numerical allocation and directed quantities above two to sales. That does not prove 500 units. An October 13 search index separately showed 30 CAM-6G3-073CLR units; it is not reconciled live inventory and does not change this conclusion.

## Regulator enable and power bench findings

The accepted direction is button-fed divider → LTC3621 RUN, with a diode-fed ordinary MCU GPIO providing HOLD after early boot. Detailed reasoning, component values, leakage and source-selection issues belong in [power.md](../../power.md); this record preserves the procurement implications.

- A 3.3 V-domain HOLD GPIO has useful margin in the retained BAS116 study. A 1.8 V GPIO through the same diode does **not** inherit that guaranteed margin. The digital-rail decision and HOLD interface must be reconciled.
- RUN absolute maximum follows VIN. USB-powered firmware must not assert HOLD into an absent/lower regulator input. RUN low is not a reverse-current-blocking guarantee.
- Standby can release an ordinary GPIO to high impedance; Stop retains I/O configuration. Use an appropriate HOLD pin, external pulldown, and external AUX-before-main shutdown timing. A held button continues enabling the regulator until release under the accepted prototype behavior.
- The room-temperature main-path OFF target is **100 nA**, including regulator and other pack-side leakage. LTC3621's 100 nA typical / 1 µA maximum shutdown row at 12 V and 25°C is not a whole-board guarantee. RTC cell-tap drain is accounted for separately. Screening is proposed, not qualified.
- USB supplies download mode and disables shutter operation. Hardware must inhibit the button's direct RUN path and prevent battery/USB backfeed; ignoring presses in firmware alone cannot do that.

On NUCLEO-N657X0-Q, **CN8 is the target MCU USB port and CN10 is ST-LINK**. UM3417 Rev 3 identifies CN9 pins 3–4 for the user-USB sink power selection. For the selected external 5.0 V supply, follow the [consolidated assembly guide](nucleo-assembly-guide.md) for injection, jumper positions and isolation; do not infer battery/USB priority from CN9 alone. [UM3417, pp10 and 19](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf#page=19)

The September study's LTC3621EMS8E-3.3#PBF and BAS116,235 are concrete component leads, not additional locked ordering suffixes. Their old stock observations and passive-selection gaps are in [power sourcing](../../power.md#7-sourcing-evidence). A development board with extra indicators, dividers or interface circuitry is not itself a representative 100 nA leakage test fixture.

**Regulator evaluation options, checked against ADI documentation October 13:** [DC1863A](https://www.analog.com/en/resources/evaluation-hardware-and-software/evaluation-boards-kits/dc1863a.html) uses adjustable 1 MHz LTC3621; DC1864A uses the 2.25 MHz LTC3621-2. The [DC1863A manual](https://www.analog.com/media/en/technical-documentation/user-guides/dc1863af.pdf) identifies **JP1 as RUN ON/OFF**, default ON, and selectable outputs including 1.8 V and 3.3 V. External RUN control requires removing the jumper's forced VIN/GND connection and verifying the actual node before attaching the divider/HOLD circuit. It is not permission to apply pack voltage to a GPIO. The demo board is an evaluation option; purchase, stock, final Nucleo power injection and representative OFF leakage remain unconfirmed.

## NAND and evaluation hardware

**October 18 architecture follow-up:** the [storage-architecture comparison](../../reports/Camera%20storage%20architecture%20alternatives.md) adds independent dual-NAND page interleaving, industrial native-SDMMC microSD and permanent-pSLC eMMC. It distinguishes payload transfer estimates from cold-start/durable-save energy and records the pre-exposure capacity-check, physical recovery and retention implications. Two-chip raw NAND is the recommended direct extension, with industrial microSD the simplest comparison experiment; these are proposals, not replacement decisions. D-46 remains unchanged, and no hardware, purchase or firmware action was taken.

**October 18 faster-storage review:** see the [new comparison](../../reports/Faster%20camera%20storage%20alternatives.md) for native-3.3 V serial alternatives, exact observed stock, ECC/cache distinctions and modeled native-image save times. **MX35LF4GE4AD-Z4I** is the recommended next prototype candidate; Micron offers a larger/faster BGA option, GigaDevice an unverified-supply 8 Gbit WSON option, and parallel Macronix genuine cache programming with more integration work. These remain proposals; the user's Alliance D-46 selection below is unchanged, and no candidate's combined ten-year/1,000-reuse-cycle qualification is established.

**October 18 final selection, D-46:** use the existing **AS5F14G04SND-10LIN on Arduino headers, with bit-banging allowed**. This supersedes Flash 5 Click-first, the earlier hardware-quad priority, CN3/VDDIO5 mapping and boot-NOR-bus sharing. The [selected Arduino mapping](alliance-nand-wiring.md#selected-arduino-header-bit-bang-mapping) uses VDDIO4 at 1.8 V for clock/quad data and a main-domain open-drain CS. Follow the [assembly guide](nucleo-assembly-guide.md) for the ordered modifications and diagrams. No physical rework/NAND test is recorded; actual speed, energy, capacity/retention and production suitability remain to qualify. Faster serial parts, dual NAND, parallel NAND, microSD and eMMC above remain unselected research.

The production storage part and interface remain unselected. **The October 12 evaluation recommendation became AS5F14G04SND-10LIN**, replacing the older Winbond shortlist preference after its NRND status was identified. This is an evaluation recommendation, not a user-locked production selection. [Review transcript, Message 013](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md)

The September reports are detailed source records, but their image timing/capacity models use VD55G0 and their stock counts are historical: [quad NAND comparison](../power/quad-nand-comparison.md), [parallel supply options](../power/nand-supply-options.md), [1.8 V architecture](../power/1v8-memory-assessment.md), [microSD alternative](../power/microsd-feasibility.md).

| Candidate | Retained rationale and qualification gap |
| --- | --- |
| **AS5F14G04SND-10LIN** | Alliance 4 Gbit / 512 MiB 1.8 V quad SPI SLC NAND, built-in ECC, 8 × 6 mm package. Message 013 recommended **two** at $16.28 each and a custom carrier; no ready-made exact-part evaluation board was found. September 8 report recorded 267 units and a 20-week stated lead time; those are not current stock. Purchased quantity and detailed performance remain unverified. [DigiKey](https://www.digikey.com/en/products/detail/alliance-memory-inc/AS5F14G04SND-10LIN/13282916), [manufacturer family datasheet cited in the discussion](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.1_O.pdf) |
| **MIKROE-3780 / Flash 5 Click** | Documented fitted device is **W25N01GVZEIG/IT, 1 Gbit / 128 MiB, 3.3 V supply and logic**. It can support NAND driver experiments but is neither the Alliance 4 Gbit part nor enough capacity for 200 full-resolution VD56G3 RAW10 images. WP and HOLD appear on separate mikroBUS pins; use an explicit wiring/pin-function plan for quad mode. It also has a power LED. A visited board page is not a purchase confirmation. [Board documentation, rechecked October 13](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/190/MIKROE-3780_Web.pdf) |
| MT29F4G01ABBFDWB-IT:F | September leading quad-performance candidate: 4 KiB pages, on-die ECC. Old Mouser stock 8,131, but factory-order restriction and exact current datasheet/read-clock qualification remained open. |
| W25N04KWZEIR | Historical 4 Gbit quad alternative with on-die ECC; old DigiKey stock 1,137 with 126-per-30-day limit. **October 12 correction: Winbond marked the exact part not recommended for new designs.** Do not treat its September shortlist position as current selection advice. [Manufacturer status cited in Message 013](https://www.winbond.com/hq/product/code-storage-flash/qspi-nand/w25n-kw/?__locale=en&partNo=W25N04KWZEIR) |
| MX35UF4G24AD-Z4I8 | 4 Gbit quad option; **host ECC required**, not on-die ECC. Old 704-unit listing had a 480-unit limit. Exact suffix/plane addressing matters. |
| AS9F14G08SA-45BIN | 4 Gbit 1.8 V parallel fallback; 63-ball BGA and host ECC. September sources recorded Mouser 837 and DigiKey 165, not current stock. |
| W25Q128JWPIQ TR | 1.8 V NOR proposal retained for boot storage. A NAND evaluation board does not replace the dedicated boot NOR architecture automatically. |

The linked September reports retain the manufacturer datasheets and exact distributor sources for these alternatives. No stock count here should be reused as an immediate procurement claim.

**Earlier carrier recommendation, superseded by D-46:** Flash 5 Click was proposed for initial command/allocation tests before a small Alliance carrier. The selected path now goes directly to the existing Alliance chip with its 1.8 V carrier, decoupling and Arduino wiring from the assembly guide. The Winbond board remains optional background, not the current storage-build plan.

**October 17 bring-up recommendation, superseded by D-46:** with capture demonstrated and power characterization deferred, prefer the Flash 5 Click strongly for the first image save/power-cycle/readback test because it is already assembled. This is a practical hookup preference, not a claim that the Winbond silicon is superior. If the Alliance already has a suitable carrier and voltage-compatible connection, prefer it instead to avoid a later device port. At an illustrative 2 MiB per slot, the raw capacities allow 64 versus 256 slots before bad-block and storage-control reserves; the Winbond cannot meet the 200-photo target. Keep geometry, status/ECC interpretation and command differences in the device driver, and avoid relying on repeated programming of a page in the common storage format. Exact Nucleo pins and I/O-bank voltage still require review before wiring. Neither production NAND selection nor ten-year retention qualification is settled by this recommendation. Manufacturer references rechecked: [Flash 5 Click](https://www.mikroe.com/flash-5-click), [Alliance exact-part listing](https://www.alliancememory.com/as5f14g04snd/), and [Alliance January 2026 Rev.3.2 family datasheet](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.2_Jan2026-revised.pdf). The older Rev.3.1 quotations elsewhere remain historical evidence; check the delivered device and current revision for implementation.

An [NXP M.2 NAND daughter card](https://www.nxp.com/design/design-center/development-boards-and-designs/m2-nand-flash-daughter-card:M2-NAND-FLASH) was also found with a closer 1.8 V Winbond device. Message 013 reported it was not stocked at DigiKey and needed an M.2 adapter. The recommendation was to put that adaptation effort toward the custom Alliance carrier. Exact NXP availability and fitted-device suitability remain unqualified.

Use a switched storage rail and prevent I/O back-powering. Firmware still owns completion/error checks, ECC status, bad blocks, allocation, integrity metadata, commit records and recovery. The October 13 policy enables full-image readback during bring-up, permits later disabling of payload readback, and retains final commit-record verification in both modes. Benchmark both modes against the new image size. Storage-full handling preserves existing photos and requires explicit USB erase after download.

## VD5943 compact optics and production route

The public stock ST VD5943 modules are useful for electrical/firmware work but their 23.1/26.3 mm heights are not packaging prototypes. ST explicitly offers smaller customized solutions through module integrators. No source reviewed established a finished **VD5943 + near-73° optics + <5 mm height** product with 500 units ready for shipment. [ST module brief](https://www.st.com/resource/en/data_brief/cam-5943-081clr.pdf)

### Module partners

| Partner | Concrete evidence | Remaining gap |
| --- | --- | --- |
| **Chippack** | [Manufacturer VD1943 page](https://www.chippack.com/productinfo/3682801.html) explicitly names monochrome VD5943 variant and custom-module service. [ST partner page](https://www.st.com/content/st_com/en/partner/partner-program/partnerpage/chippack.html) confirms module packaging/OEM/ODM capability. | Published family modules are 23.13/26.25 mm tall. Best specific custom-production lead; compact drawing, optical compatibility, minimum order and delivery need a proposal. |
| **APPRO** | [AP-VD5943-Mini-MIPIYUV-I](https://www.appropho.com/products_iii_en.html?cID=209&pdid=202&type=36), actual VD5943 with MIPI YUV/ISP. Lens B claims 72.5° diagonal, 6 mm F2 M12; manufacturer status Available, without numeric stock. | Large M12 assembly, Jetson support rather than proven Nucleo integration. Manufacturer FOV requires validation: simple rectilinear full-sensor geometry does not agree with the stated 6 mm/72.5° pair. Confirm distortion and active area. |
| **Leopard Imaging** | [VD1943 mobile module](https://leopardimaging.com/product/robotics-cameras/cis-2-mipi-modules/mobile-modules/li-vd1943-mipi/li-vd1943-mipi-062h-af/) provides a related-family compact design. | RGB-NIR and autofocus; page said backorder. Mono/fixed-focus adaptation and height require confirmation. |
| **Appleye** | [ST-listed custom design/manufacturing](https://www.st.com/en/partner-products-and-services/customized-camera-modules-design-development-mass-production.html); [manufacturer ST partnership](https://appleye.co.il/appleye-st-partnership/). | Generic customization and related-sensor evidence, not a verified compact VD5943 module. |
| **InnoWave** | [Camera module service](https://www.innowave.design/camera-modules); [ST partner listing](https://www.st.com/content/st_com/en/partner/partner-program/partnerpage/innowave.html). | Generic camera/software integration capability; no VD5943-specific compact part verified. |

Sunny and Vision Components were considered during the search, but no public VD5943-specific compact module was verified. This is a research gap, not proof they cannot supply one.

### Compact lens leads

**Lens TTL is not complete camera height.** A lens's image circle, back focal length, sensor cover-window stack, chief-ray angle (CRA), holder and assembly tolerance must be matched to the sensor. Thread diameter also does not specify height. VD5943's active image diagonal is approximately 7.29 mm; shorter lenses with smaller image circles require cropping and sacrifice resolution. [VD5943 datasheet, optical stack/CRA section 2.1.3](https://www.st.com/resource/en/datasheet/vd5943.pdf)

| Lens lead | Published evidence | Qualification status |
| --- | --- | --- |
| **Kantatsu F6639** | Fixed focus, EFL 3.400 mm, F1.8, image circle 6.10 mm, TTL 4.0 mm, barrel diameter 6.2 mm, maximum CRA 35°. | 2021 catalog production status is not 2026 availability. Too small an image circle for full VD5943; potential cropped integration only. |
| **Kantatsu D0501** | Fixed focus, EFL 3.695 mm, F2, image circle 6.45 mm, TTL 4.2 mm (detail 4.2356), barrel diameter 6.1 mm, maximum CRA 34.4°. | Catalog's 7.3 × 7.3 × 4.75 mm module uses Sony IMX663; it does not establish VD5943 compatibility. Sample availability was a 2021 claim. |
| TOWIN CCL125051MPF | 1/2.5-inch 5 MP lens, 5.1 mm F2.8, M7.5, 20 cm minimum object distance, 6.7 mm TTL and 5.2 mm body height. | Concrete small lens but misses the height target. [Manufacturer](https://www.towin-elec.com/product/m7-5-miniature-lens-ccl125051mpf) |
| **TOWIN M804812306618** | 4.8 mm F1.8, TTL 5.32 mm, M8.2 × 0.25 catalog lead, with 73° specified at 7.12 mm diagonal and high CRA. [Manufacturer specifications](https://www.towinlens.com/product/low-distortion-lens-m804812306618) | Message 019 projected approximately 74° at full VD5943 resolution assuming low distortion. Coverage, CRA and mechanical compatibility remain unqualified; TTL already exceeds 5 mm before structure beneath the image plane. |
| Sunex / Lensation Lensagon | [Sunex](https://sunex.com/) describes miniature board-mount lenses and active alignment; [Lensation](https://www.lensation.de/products/) lists miniature/custom optics. | Supplier capability, not a qualified VD5943 lens/module combination. |

Kantatsu source: [official June 10, 2021 catalog, F6639 p3, D0501 pp6/8/9](https://kantatsu.co.jp/product/docs/Kantatsu%20Product%20List%2020210610%20Rev.11.pdf). Its compact designs make feasibility worth investigating, but current supply, focus range, BFL and module assembly remain unconfirmed.

For an ideal rectilinear lens at 73° diagonal, required crop diagonal is `2 × EFL × tan(73°/2)`. At native 2.25 µm pixels and the VD5943 aspect ratio, approximate F6639/D0501 crops are respectively **1768 × 1370 (2.42 MP)** and **1921 × 1489 (2.86 MP)**. These are calculations, not measured usable image areas or guaranteed sensor crop modes. Maximum catalog CRA is not the CRA at the proposed crop edge; ray-angle compatibility, shading and corner sharpness remain unresolved. A supplier optical prescription or representative assembled test is necessary.

The full-sensor rectilinear estimate requires approximately **4.9 mm EFL for 73°**; this is not a physical-height lower bound. [Review transcript, Message 019](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md) also proposed a **CAM-5943-081CLR crop to roughly 73°, retaining approximately 3.8 MP**, as an optical bench test before developing custom lenses. This is an unmeasured framing estimate and retains the stock module's tall package and limited factory focus range. Message 020 subsequently selected VD56G3 for the immediate prototype and retained this work as a future direction.

## Next evidence to retain

1. Reconcile the actual order: exact part numbers, quantities, received boards/cables and any substitutions. Keep selection separate from purchase.
2. Apply and verify the [consolidated Nucleo assembly guide](nucleo-assembly-guide.md), including voltage domains and supply/debug isolation; confirm actual regulator hardware and finish RUN/HOLD/USB-source integration.
3. Measure selected-camera cold start, exposure start, full-frame readout, save/verification, shutdown and current traces. Verify the 50 ms exposure-start and 200-photo requirements.
4. Obtain current supplier confirmation for 500 **complete** camera modules, including the fitted lens/filter, focus setting, lot consistency, allocation and delivery. Evaluation-stock counts do not close this gate.
5. Check the physical 73° module and enclosure stack. Define acceptable near/far focus and sharpness before approving alternate optics.
6. For future VD5943, obtain current F6639/D0501 availability and optical/mechanical feasibility from an integrator. Confirm crop, CRA, BFL/window stack, fixed-focus range, total assembled height and production quantity before replacing the prototype baseline.

This record does not authorize additional purchases, supplier outreach, production substitutions or schematic changes.
