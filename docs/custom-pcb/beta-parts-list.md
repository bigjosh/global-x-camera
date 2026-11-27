# Beta board parts list

**Status: first list, November 27, 2026. Not ready to order.** It gathers what the project notes record for the beta board, so that nothing decided is lost and nothing removed is bought. Many lines are still a family name or "to choose", and the passives wait for the schematic. No distributor page was opened for this list: every stock figure is a search snippet quoted from the notes, with its date where one was recorded. Check each line on the live DigiKey page before ordering.

**Quantities (user, November 27):** ten bare boards; ten sets of every part; eight MCUs. Multiply "Qty per board" by ten unless the row says otherwise. Ten sets includes ten camera modules, ten cells and twenty dials, which can be trimmed line by line.

**Status words:** DECIDED BY THE USER; CHOSEN BY THE REVIEWER (a choice the user delegated); PROPOSED (not yet confirmed by the user); TO CHOOSE (function known, part not picked).

Note files: PN = docs/prototype/NOTES.md; PW = docs/power/NOTES.md; PT = docs/power/beta-power-tree.md; DN = docs/decisions/NOTES.md; BT = firmware/boot-timing/NOTES.md; RN = NOTES.md; PIN = docs/custom-pcb/beta-pin-table.md; HB = hardware/beta/README.md; OQ = docs/review/2026-11-25-open-questions.md; PL = docs/review/2026-11-10-pcb-readiness-punch-list.md.

"Reflow" means the user's own hot-plate pass. Only the dials, cell, camera module and shutter switch are named in the notes as hand-fitted (DN 2026-11-26, HB); "reflow" for the other surface-mount parts is inferred. Order quantity on record: ten sets of everything, eight MCUs (DN 2026-11-27).

## Parts on the beta board

| Function | Part number as recorded | Qty per board | Package | Status | Fitted | Recorded in | Stock remark (date) |
|---|---|---|---|---|---|---|---|
| MCU | STM32N657X0H3Q | 1 (buy 8) | VFBGA264, 0.8 mm | DECIDED BY THE USER (project MCU; count of 8 is the reviewer's reading) | Reflow, hand-placed | DN 2026-11-26, 2026-11-27 | Snippets 2026-11-26: DigiKey US 6 at $20.62, Canada 547, Germany 686; Future about 714; LCSC C42418080 out of stock. "Buy MCUs early." Check silicon revision (PIN open point 5) |
| Boot flash | Winbond W25Q128JWPIQ | 1 | WSON-8, 6 x 5 mm | CHOSEN BY THE REVIEWER (delegated) | Reflow | BT 2026-11-25 | DigiKey snippets about 15,000 to 20,000, undated; live listing to be checked before layout |
| Main 1.8 V buck | "TI TPS6282x, 1.8 V"; exact variant not recorded | 1 | Not recorded (stored datasheet: 6-pin VSON-HR, DMQ) | Family DECIDED BY THE USER through the agreed tree; variant TO CHOOSE | Reflow | PT; PW 2026-11-25 (proposed, then agreed) | None recorded |
| Buck inductor, input and output capacitors | None | 1 set | — | TO CHOOSE (recovered design used 0.47 uH with the adjustable TPS62825DMQR) | Reflow | Not recorded for the beta | None |
| Auxiliary 1.8 V load switch, with bypass link | "TI TPS22918"; suffix not recorded | 1 | Not recorded (recovered design: TPS22918DBVT, 6-pin) | Family DECIDED BY THE USER through the agreed tree; ordering code TO CHOOSE | Reflow | PT; PW 2026-11-25 | None recorded |
| 3.3 V LDO for the SD card | "onsemi NCP115C 3.3 V"; ordering code not recorded | 1 | Not recorded (datasheet: slow-slew versions only in XDFN4 1 x 1 mm) | Family DECIDED BY THE USER through the agreed tree; ordering code TO CHOOSE | Reflow | PT; PW 2026-11-25 | None recorded |
| Sensor 2.8 V LDO | None ("2.8 V LDO from the input node") | 1 | — | TO CHOOSE | Reflow | PT | PT open point 8 (tree of 2026-11-25): the 2.8 V version "looked thinly stocked; buy it early or name an alternate" |
| Sensor 1.2 V LDO | None ("1.2 V LDO from 1V8_AUX") | 1 | — | TO CHOOSE (recovered design used NCP115AMX120TCG; sensor core is 1.10 to 1.26 V) | Reflow | PT | None |
| Latch P-FET | None | 1 | — | TO CHOOSE; must be specified for 1.8 V gate drive. Prototype part is a kit AO3401 | Reflow | PT; PW 2026-11-06 | None |
| Latch trigger capacitor and resistors | 2.2 uF X7R 10 to 16 V; 1 k, 100 k on the prototype | 1 set | — | TO CHOOSE (values from the prototype; start-up surge limit still open, PT open point 3) | Reflow | PW 2026-11-08; PT | None |
| Low-side FETs: red, green, blue, HOLD | Vishay SI2312CDS-T1-GE3 | 4 | SOT-23 | CHOSEN BY THE REVIEWER (user set four single SOT-23; no user reply on the part number recorded) | Reflow | PW 2026-11-26 | "Tens of thousands in regional snapshots", undated; LCSC C142518. Alternate onsemi NTR3C21NZT1G, about 8,000 |
| Internal SMPS coil | Murata DFE201612P-1R0M (1 uH; named in AN5967 Table 6 and fitted on the Nucleo) | 1 | 0806, 2.0 x 1.6 mm | PROPOSED; DigiKey stock not checked | Reflow | PIN, supply pins | None |
| MCU and SMPS capacitors, V08CAP 4.7 uF, VDDA18PMU ferrite | None; "AN5967 Table 6 p.12-13" | 1 set | — | TO CHOOSE | Reflow | PIN, supply pins; PN 2026-11-27 | None |
| External core regulator kit (fallback) | See the fallback table below | 0 fitted; buy 10 sets | — | Provision and purchase DECIDED BY THE USER; parts CHOSEN BY THE REVIEWER | Not fitted unless needed; by hand, hot air | DN 2026-11-27; PT | See below |
| 48 MHz crystal and load capacitors | None | 0 (footprint only) | — | TO CHOOSE; whether to fit is open (Nucleo BOM X3: NDK NX1612SA-48MHZ-EXS00A-CS13734) | Unfitted | PIN; RN 2026-11-26; OQ defaults | None |
| 32.768 kHz crystal | None; not fitted | 0 | — | No part; optional unfitted link from the RTC clock output | — | PIN | — |
| Sensor 12 MHz oscillator | None for the beta | 1 | — | TO CHOOSE (ST's adapter uses ECS-2520MVLC-120-CN) | Reflow | PIN; PL-09 | None |
| RTC | RV-3032 (ordering code not recorded) | 1 | Not recorded; datasheet not stored | DECIDED BY THE USER; backup supply open | Reflow | PN 2026-11-11; PT open point 7 | None; OQ item 27 open |
| Orientation sensor (first to cut) | LIS2DW12 (recovered BOM: LIS2DW12TR) | 1 | Not recorded in the notes read | PROPOSED: default "unless the owner objects" | Reflow | OQ, set-aside list; PN 2026-11-11 | None |
| Camera module | CAM-6G3-073CLR | 1 | Head 6.5 x 6.5 x 4.68 mm, 12.4 x 8.0 mm overall, 30-pin flex | DECIDED BY THE USER | By hand; in a cut-out, potted | PN 2026-10-13, 2026-11-11, 2026-11-26 | prototype-parts-and-camera-research.md (updated 2026-10-18): DigiKey 25 at $21.44, later 24; Mouser 8 |
| Camera connector | Hirose BM28B0.6-30DS/2-0.35V(51) | 1 | 30-position, 0.35 mm pitch | PROPOSED: carried from the recovered design; footprint to be redrawn | Reflow | PL-09; datasheets/README.md; OQ items 27, 31 | None |
| SD card socket | Molex 503398-1892 (DigiKey WM11190CT-ND) | 1 | Push-push, 13.1 x 14.05 x 1.28 mm | PROPOSED. Alternate Molex 104031-0811 | Reflow | PN 2026-11-26 (searches; "still proposed") | "Stock figures are undated"; no figure given |
| RGB LED | SunLED XZMDKCBDDG45S-9 | 1 | Reverse-mount, 3.2 x 2.8 x 1.9 mm | PROPOSED; pinout and hole diameter unread. Alternate Würth 156125M173000 | Reflow | PN 2026-11-26; OQ item 24 | "Six-figure DigiKey stock in snippets", undated |
| LED series resistors | None | 3 | — | TO CHOOSE | Reflow | Not recorded | None |
| Dials (exposure, ASA) | Alps RK10J11E0034 | 2, plus at least one sacrificial part | Through-hole thumbwheel, 14 mm, legs re-formed, face-down | DECIDED BY THE USER | By hand; one 3 s joint allowed per terminal | PN 2026-11-25; HB | 2026-11-25: listing could not be opened; snippets disagreed (none, or about 1,900); Alps status Standard |
| Shutter switch | Omron D2MQ-4L-105-1 | 1 | Snap-action, 8.2 x 6.5 x 2.7 mm, straight terminals, laid flat | DECIDED BY THE USER | By hand; terminals trimmed and joggled | PN 2026-11-26 (re-lock); HB | 2026-11-26: stock of this variant "has not been checked on a live page". SW1396-ND is the -L variant |
| Cell | Grepow GRP292434-1C-3.7V-210mAh with PCM (DigiKey 15285146) | 1 | Pouch pack, 3.8 x 24.1 x 36.5 mm maximum | DECIDED BY THE USER | By hand; protection board unfolded, leads soldered to pads | PW 2026-11-25 (three entries) | Snippets 2026-11-25: Active, 91 in stock, $7.99; Marketplace item, ships separately, flat fee as much as $130 |
| ST-LINK header | Samtec FTSH-107-01-L-DV-K, land pattern only | 0 | STDC14 pads; header is 5.97 mm tall | DECIDED BY THE USER (bare pads, pogo fixture) | Not fitted | PN 2026-11-26 (two entries); OQ item 9 | None |
| Debug probe | STLINK-V3MINIE | 1 in total | — | PROPOSED by the reviewer; listed as resolved in OQ item 9; no user sentence naming it | — | PN 2026-11-26; PT open point 6; OQ item 9 | None |
| Pogo fixture parts | None | 1 in total | — | TO CHOOSE; the user makes it | — | PN 2026-11-26 | None |
| Pull resistors and small capacitors | Values only: 200 ohm 1% (CSI_REXT); 10 k (BOOT0, BOOT1, PG10); 10 to 22 k gate pull-downs x4; 47 k or less (3.3 V enable); 100 k (PE6); 10 nF (NRST); 100 nF x2 (dial wipers) | — | — | TO CHOOSE (sizes and part numbers) | Reflow | PIN | None |
| Pads with no part | Charge + and −, BOOT0, BOOT1, latch force-on, PG10, PD0, PE0 | — | — | — | — | PW 2026-11-25; PIN | — |

## Fallback core regulator kit: buy, do not fit

For the provision described in the [power tree](../power/beta-power-tree.md). Ten kits. Stock figures are cached regional DigiKey pages returned by search on November 27, not the live US page.

| Part number | Qty per board | Purpose | Stock remark |
|---|---|---|---|
| TI TPS62825DMQR (DigiKey 296-49521-1-ND) | 1 | 2 A adjustable buck, 6-pin 1.5 x 1.5 mm no-lead. The 3 A TPS62826DMQR has the same footprint | about 10,000 to 22,000 shown; about $1.29 |
| TDK TFM201610ALM-R47MTAA | 1 | 0.47 uH coil, 2.0 x 1.6 x 1.0 mm, on TI's tested list | snapshots conflict: in stock on one page, out of stock on another. Alternate: Murata DFE201612E-R47M=P2, not on TI's list |
| Murata GRM188R61A106KE69J | 4 | 10 uF 10 V X5R 0603: two input, two output | in stock on the pages seen |
| 22 uF 6.3 V X5R 0603, part to choose | 2 | Alternate output capacitors, if a scope check shows too much droop | not looked up |
| 34.8 kilohm 1% 0603 (Yageo RC0603FR-0734K8L or equivalent) | 1 | Feedback, top | not checked |
| Panasonic ERA-3AEB104V | 1 | Feedback, bottom: 100 kilohm 0.1% 0603 | snapshots conflict |
| Murata GRM1555C1H121JA01D | 1 | 120 pF C0G 0402 feed-forward | in stock on the pages seen |
| Low-resistance metal jumper, 0603 (the Nucleo uses Rohm PMR03EZPJ000 for the same links) | 2, plus spares | The two selection links. Fitted in both builds, in one position or the other | not checked; read its resistance from the datasheet before choosing |
| 10 kilohm 0402 | 1 | Holds the unused SMPS output at ground. Fitted in both builds | any |

## Removed from this revision: do not order

| Item | Part numbers in the repository | Removed by |
|---|---|---|
| USB: receptacle, VBUS protection, PHY LDO, source-selection FET and diodes | USB4105-GF-A, USBLC6-2SC6, TLV70033DDCT, AO3401A (Q3), SS34 | RN 2026-11-26; PT "Changed November 26" |
| Raw NAND | MX30LF2G18AC-TI, AS5F14G04SND-10LIN, MT29F4G01ABBFD and other candidates | DN 2026-11-25; RN 2026-11-25 |
| FRAM | None chosen (MB85RS128TY, MB85RS256TY appear once) | DN 2026-11-25 |
| Charger | None; only + and − pads | PW 2026-11-25 |
| CR2032 holders and the coin-cell converters | LTC3621, TPS62132RGTR | PW 2026-11-25; RN 2026-11-25 |
| Nucleo boot flash | MX25UM51245GXDI00 | BT 2026-11-25 |
| Recovered design's 3.3 V flash | W25Q128JVPIQ (not the JW part) | Replaced; BT 2026-11-25 |
| Earlier RTC | RV-3028-C8 | PN 2026-11-11 |
| Tag-Connect debug | TC2030-IDC-NL, TC2070 | PN 2026-11-26 |
| Earlier shutter switches | B3U-3000P, D2MQ-4L-1 (silver), D2MQ-4L-105-1-L | PN 2026-11-26 |
| Dual N-FETs | Si1922EDH, DMN2990UDJ | PW 2026-11-26 |
| Hobby thumbwheels and dual-track dials | uxcell B503, RK10J12 parts | PN 2026-11-25 |
| 40 MHz crystal | CX3225SA40000D0PTWCC | PL (recovered design); PIN |
| Adapter level shifters and LDOs | BSS138, 74LVC1T45, LD39050 | PIN (direct 1.8 V) |
