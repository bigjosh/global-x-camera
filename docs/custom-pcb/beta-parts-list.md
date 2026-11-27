# Beta board parts list

**Status: second list, November 27, 2026. Not ready to order.** The first list gathered what the project notes record. On November 27 a part-selection study picked the open lines from the stored datasheets, and each pick was checked once by a second reader. Where no datasheet is stored, the row says what the pick rests on. Where the checker disagreed, the checker's figure is used and the row says "corrected by the checker". Nothing was built or measured. Stock figures are search snippets from regional or cached pages, never live; unless a row gives a date they were seen on November 27 and carry no page date. Clear the items under [Before ordering](#before-ordering) first.

**Quantities (user, November 27):** ten bare boards; ten sets of every part; eight MCUs. Multiply "Qty per board" by ten unless the row says otherwise. Ten sets includes ten camera modules, ten cells and twenty dials, which can be trimmed line by line.

**Status words:** DECIDED BY THE USER; CHOSEN BY THE REVIEWER (a choice the user delegated); CHOSEN BY THE REVIEWER, CHECKED (picked in this study and confirmed by the checker; "with caveat" where the checker attached one, given in the last column); PROPOSED (not yet confirmed by the user); TO CHOOSE (function known, part not picked).

Note files: PN = docs/prototype/NOTES.md; PW = docs/power/NOTES.md; PT = docs/power/beta-power-tree.md; DN = docs/decisions/NOTES.md; BT = firmware/boot-timing/NOTES.md; RN = NOTES.md; PIN = docs/custom-pcb/beta-pin-table.md; HB = hardware/beta/README.md; OQ = docs/review/2026-11-25-open-questions.md; PL = docs/review/2026-11-10-pcb-readiness-punch-list.md.

"Reflow" means the user's own hot-plate pass. Only the dials, cell, camera module and shutter switch are named in the notes as hand-fitted (DN 2026-11-26, HB); "reflow" for the other surface-mount parts is inferred. Order quantity on record: ten sets of everything, eight MCUs (DN 2026-11-27).

## Parts on the beta board

Shared capacitor and resistor lines are listed once, with the count per board and where each piece goes. The last figure in each package cell is the height as the study gave it.

| Function | Part number | Qty per board | Package | Status | Fitted | Recorded in | Stock remark (snippets) and caveats |
|---|---|---|---|---|---|---|---|
| MCU | STM32N657X0H3Q | 1 (buy 8) | VFBGA264, 0.8 mm | DECIDED BY THE USER (project MCU; count of 8 is the reviewer's reading) | Reflow, hand-placed | DN 2026-11-26, 2026-11-27 | Snippets 2026-11-26: DigiKey US 6 at $20.62, Canada 547, Germany 686; Future about 714; LCSC C42418080 out of stock. "Buy MCUs early." Check silicon revision (PIN open point 5) |
| Boot flash | Winbond W25Q128JWPIQ | 1 | WSON-8, 6 x 5 mm | CHOSEN BY THE REVIEWER (delegated) | Reflow | BT 2026-11-25 | DigiKey snippets about 15,000 to 20,000, undated; live listing to be checked before layout |
| Main 1.8 V buck | TI TPS6282518DMQR, fixed 1.8 V, 2 A (DigiKey 296-49520-1-ND) | 1 | DMQ 6-pin VSON-HR, 1.5 x 1.5 mm, 0.5 mm pitch, 1.0 mm | Family DECIDED BY THE USER; fixed variant CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PT; PW 2026-11-25, 2026-11-27 | Snippets: US page 7,619 at $1.25; regional pages about 6,740 to 7,140; 12-week lead time on one page. Caveats: floor margin at the pins is thin; soft start is inside ST's limit on typical figures only. The same pads take TPS6282618DMQR (3 A) or the fallback kit's TPS62825DMQR |
| Main buck coil, 0.47 uH | Murata DFE201610E-R47M=P2 (DigiKey 490-18109-1-ND; the -1 suffix is inferred) | 1, plus 1 in the fallback kit | 2.0 x 1.6 mm, 1.0 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PW 2026-11-27 | Snippet: about 96,390 on one regional page, 21-week lead time; not rechecked by the checker. Caveat: Murata datasheet not stored; the 4.8 A saturation figure rests on TI's table and snippets disagree (4.8 and 4.2 A). Alternate TDK TFM201610ALM-R47MTAA, thin stock |
| 10 uF 10 V X5R capacitors | Murata GRM188R61A106KE69J (DigiKey 490-14372-1-ND, not confirmed by the checker) | 13: buck input 1, buck output 2, VDDSMPS 2, 3.3 V LDO input 1 and output 1, sensor 2.8 V 2, sensor 1.2 V 2, latch trigger 1, orientation sensor 1. Plus 4 in the fallback kit | 0603, 0.8 mm nominal (0.9 mm maximum not confirmed) | CHOSEN BY THE REVIEWER, CHECKED with caveat for the buck, VDDSMPS and trigger uses; cannot be verified for the LDO uses (no Murata datasheet stored) | Reflow | PW 2026-11-27 | Stock doubtful. Snippets conflict: 125,916 on one listing and 0 on another, "not normally stocked" on a third, "quote required" on a fourth. Capacitance under bias is an estimate. Sensor rails: keep both footprints and decide the fitted count after the first board is scoped. Alternates were named from memory and not looked up |
| Auxiliary 1.8 V load switch, with bypass link | TI TPS22918DBVR (DigiKey 296-46278-1-ND) | 1 | SOT-23-6, 2.9 x 1.6 mm body, 1.45 mm | Family DECIDED BY THE USER; ordering code CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PT; PW 2026-11-25, 2026-11-27 | Snippets conflict: US page 26,027, Canada about 25,898, Brazil 199, Italy 0, Mexico and Finland out of stock. Caveat: the internal SMPS start current through the switch is unchecked. TPS22918DBVT is the same device on a 250-piece reel |
| Load switch rise-time capacitor (CT), 470 pF 50 V C0G | Murata GRM1555C1H471JA01D (DigiKey 490-1297-1-ND) | 1 | 0402, 0.5 mm | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PW 2026-11-27 | Snippets: about 372,621 (Canada), about 404,534 (Austria). The same pad takes 220 pF or 1000 pF if the scope disagrees |
| 1 uF 25 V X5R capacitors | Murata GRM155R61E105KA12D (DigiKey 490-10017-1-ND; the -1 suffix is inferred) | 14: VDDCORE 9, VDDCSI 1, VDDSMPS 2, VREF+ 1, load switch input 1 | 0402, 0.5 mm | CHOSEN BY THE REVIEWER, CHECKED (the MCU uses with caveat: no stock seen) | Reflow | PW 2026-11-27 | Snippets disagree between the two study groups: about 2.4 and 5.9 million on two Canada listings in one, no stock snippet seen in the other. On the Nucleo BOM. Alternate Yageo CC0402KRX5R6BB105 |
| 1 uF capacitors with no part number yet | None given by the study | 3: 2.8 V LDO input, 1.2 V LDO input, RTC backup pin | 0402 | TO CHOOSE. The study asked for 10 V X5R at the LDO inputs and named no part; the 1 uF line above meets that rating | Reflow | PW 2026-11-27 | No snippet |
| QOD link: load switch QOD to VOUT, 0 ohm | Yageo RC0402JR-070RL (DigiKey 311-0.0JRCT-ND) | 1 | 0402, about 0.35 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow; removed if the bypass link is fitted | PW 2026-11-27 | Snippets: 10 to 17 million on regional pages; a Hong Kong page out of stock. Part number and DigiKey number not rechecked by the checker |
| Bypass link site across the load switch | Rohm PMR03EZPJ000 (the fallback kit's jumper) | 0 fitted; 0603 site | 0603, 0.35 mm (corrected by the checker; the picker guessed 0.5 mm) | CHOSEN BY THE REVIEWER, CHECKED with caveat | Not fitted unless ST allows one rail for both supply groups | PT open point 1; PW 2026-11-27 | See the fallback table |
| 3.3 V LDO for the SD card | onsemi NCP115CMX330TCG (DigiKey NCP115CMX330TCGOSCT-ND) | 1 (buy 15 to 20 across both NCP115 lines: small and easy to lose) | XDFN4, 1.0 x 1.0 mm, 0.65 mm pitch, 0.43 mm | Family DECIDED BY THE USER; ordering code CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow only: stencil and hot plate, joints hidden | PT; PW 2026-11-25, 2026-11-27 | Snippets: Canada 16,064; Finland 9,829; 12-week lead time on one page. Caveat: the SD supply ramp is 110 us typical against a 0.1 ms minimum. Do not substitute NCP115AMX330TCG: its ramp is outside ST's limit |
| Sensor 2.8 V LDO | TI TLV70028DDCR (DigiKey 296-39280-1-ND) | 1 | SOT-23-THIN 5-pin (DDC), 2.9 x 1.6 mm, 1.1 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PT; PW 2026-11-27 | Snippets: Canada 3,922; Brazil about 3,897; Australia 9,810; Italy about 9,753. Caveat: no soft start, so up to 0.86 A from the cell at PWR_ON. Alternates: NCP115CMX280TCG (XDFN4 footprint, slow start; 2,169 in a snippet); TPS7A2028PDBVR cannot be verified and is not a drop-in until its datasheet is read |
| Sensor 1.2 V LDO | onsemi NCP115CMX120TCG (DigiKey NCP115CMX120TCGOSCT-ND) | 1 (buy with the 3.3 V part) | XDFN4, 1.0 x 1.0 mm, 0.43 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow only | PT; PW 2026-11-27 | Snippets: Canada 10,515; UK about 10,517; lead time 12 weeks on one page, 35 on another. The sensor core is 1.08 to 1.26 V (DS12968 Table 12; the 1.10 V in the first list was wrong). Caveats: start pulse of 0.36 to 0.40 A from 1V8_AUX; 20 mV below the sensor's maximum. Alternate NCP115AMX120TCG only if the C version cannot be bought, and then with one 10 uF |
| Latch P-FET | Vishay SI2333DDS-T1-GE3 (DigiKey number not seen; product page 3679996) | 1 | SOT-23, 0.89 to 1.12 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PT; PW 2026-11-06, 2026-11-27 | Snippets conflict: 10,530 on one page; Austria 23,931; Brazil 24,311; Ireland 4; a punch-out page out of stock; lead time 13 to 38 weeks. Buy early. Not SI2333DS (obsolete), and not -T1-BE3 unchecked. Alternate onsemi FDN306P (DigiKey FDN306PCT-ND; about 47,376 in a snippet), guaranteed at 1.8 V gate drive only |
| Latch trigger network | Values: 47 k gate to source; 10 k switch NO to gate; 10 k HOLD drain to gate; 10 uF switch common to ground; 1 k switch NC to ground; 220 nF gate to source; 22 nF gate to drain | 1 set | See the capacitor and resistor rows | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PW 2026-11-08, 2026-11-27; PT | From hand arithmetic and a square-law simulation; nothing measured. HOLD takeover time on the beta is unknown |
| Latch soft-start capacitor, gate to drain, 22 nF 50 V X7R | Murata GRM155R71H223KA12D (DigiKey 490-3884-1-ND, from the checker's snippet) | 1 | 0402, 0.55 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PW 2026-11-27 | Snippets: Mexico about 634,000; Germany 969,245; Italy 998,495. Datasheet not stored. 47 nF on the same pad halves the surge |
| Latch gate-source capacitor, 220 nF 16 V X7R | Murata GRM155R71C224KA12D (DigiKey 490-5418-1-ND) | 1 | 0402, 0.55 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PW 2026-11-27 | Snippets: Canada 926,040; Brazil 361,756; a punch-out page zero. Caveat: the margin that keeps the FET off at cell connection is nominal only; 470 nF fits the same pad |
| Low-side FETs: red, green, blue, HOLD | Vishay SI2312CDS-T1-GE3 | 4 | SOT-23, 0.89 to 1.12 mm | CHOSEN BY THE REVIEWER, CHECKED (datasheet now read: threshold 0.45 to 1.0 V, 41.4 mohm maximum at 1.8 V) | Reflow | PW 2026-11-26, 2026-11-27 | "Tens of thousands in regional snapshots", an undated snippet from November 26, not rechecked; LCSC C142518. Alternate onsemi NTR3C21NZT1G, about 8,000 |
| Internal SMPS coil, 1 uH | Murata DFE201612P-1R0M=P2 (named in AN5967 Table 6; fitted on the Nucleo as L3) | 1 | 2.0 x 1.6 mm, 1.2 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PIN, supply pins; PW 2026-11-27 | Snippets: 7,648 on one regional DigiKey page; Future about 3,000; the checker saw no DigiKey figure. Caveat: one distributor snippet marks it no longer manufactured and gives 3.1 A saturation (Nucleo BOM 3.3 A; ST's floor 3.0 A). Check Murata's status. Alternate DFE201612E-1R0M=P2, not verified. Not DFE201612PD |
| MCU and SMPS decoupling set | AN5967 Table 6: 24 x 100 nF, 13 x 1 uF, 2 x 10 uF, 4 x 15 uF, 1 x 4.7 uF, 1 x 2.2 nF, with the coil, 2 ohm and ferrite: 48 parts | 1 set | 0402 and 0603; no 0201 | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PIN, supply pins; PN 2026-11-27; PW 2026-11-27 | Part numbers are in the capacitor rows above and below. Caveat: all on the parts side, where ST recommends the opposite side for BGA packages |
| 100 nF 16 V X7R capacitors | Murata GRM155R71C104KA88D (DigiKey 490-3261-1-ND, not seen by the checker) | 27: MCU 24, dial wipers 2, oscillator bypass 1. Three more 100 nF positions (RTC 1, orientation sensor 2) have no part number from the study and can share the line | 0402, 0.55 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PW 2026-11-27 | Snippets: large stock on several regional pages, backorder on one; the checker saw no figure. Datasheet not stored. Alternate Yageo CC0402KRX7R7BB104 |
| SMPS output capacitors, 15 uF 6.3 V X5R | TDK C1608X5R0J156M080AC (DigiKey 445-8027-1-ND, not seen by the checker) | 4 | 0603, 0.8 mm nominal; allow 1.0 mm (corrected by the checker) | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PW 2026-11-27 | Stock uncertain. Snippets conflict: 24-week lead time on one page; aggregators quote about 120,000 and about 379,000. ST's table says 15 uF; ST's Nucleo fits 22 uF (Murata GRM188R60J226MEA0J), the named substitute |
| V08CAP capacitor, 4.7 uF 6.3 V X5R | Murata GRM155R60J475ME47D | 1 | 0402, 0.5 mm nominal | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PW 2026-11-27 | Snippet: 970,727 on one regional page; not rechecked. The Nucleo's own part |
| SMPS snubber capacitor, 2.2 nF 50 V X7R | Yageo CC0402KRX7R9BB222 | 1 | 0402, 0.5 mm | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PW 2026-11-27 | Stock not looked up; no snippet. The Nucleo's part. Alternate Murata GRM155R71H222KA01D |
| 10 nF 50 V X7R capacitors: NRST, cell-sense filter at PA8 | Yageo CC0402KRX7R9BB103 | 2 | 0402, 0.5 mm | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PW 2026-11-27 | Stock not looked up; no snippet. 10 nF is the datasheet maximum on NRST: add nothing in parallel. Alternate Murata GRM155R71H103KA88D |
| VDDA18PMU ferrite, 18 ohm at 100 MHz | Taiyo Yuden LSMCA160808T180NGR (the Nucleo's L2) | 1 | 0603, 1.0 mm (corrected by the checker; 0.8 mm reported) | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PIN, supply pins; PW 2026-11-27 | Snippets: 29,230 on one regional page; 13-week lead time on another. Datasheet not stored. Alternate FBMJ1608HM180NTR, not verified |
| 10 k 1% resistors | Yageo RC0402FR-0710KL (DigiKey 311-10.0KLRCT-ND) | 12: two latch gate-path series, four gate pull-downs, 3.3 V enable pull-down, BOOT0, BOOT1, PG10, XSHUTDOWN pull-down, RTC EVI. Plus 1 in the fallback kit | 0402, 0.35 mm | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PIN; PW 2026-11-27; PN 2026-11-27 | Snippets conflict: a Hong Kong page out of stock with an 18-week lead time; no other figure seen. The RTC and XSHUTDOWN positions take the value from the study; the part number was picked for the other ten |
| 47 k 1% resistors | Yageo RC0402FR-0747KL (DigiKey 311-47.0KLRCT-ND, from the checker's snippet) | 2: latch gate pull-up, PWR_ON pull-down | 0402, 0.35 mm | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PIN; PW 2026-11-27 | Snippet: 1,164,117 in a substitute table; 18-week lead time on another page |
| 1.0 k 1% resistors | Yageo RC0402FR-071KL | 2: trigger reset, red LED | 0402, 0.35 mm | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PW 2026-11-27; PN 2026-11-27 | Not found in snippets. Check the live page |
| 510 ohm 1% resistors | Yageo RC0402FR-07510RL (DigiKey 311-510LRCT-ND) | 2: green LED, blue LED | 0402, 0.35 mm | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PN 2026-11-27 | Aggregator snippets disagree: 20,868 on one, 279,892 on another |
| 2.2 k 1% I2C pull-ups | Yageo RC0402FR-072K2L | 2 on the camera bus; 2 on the orientation-sensor bus (I2C4, 1.8 V) | 0402, about 0.35 mm | CHOSEN BY THE REVIEWER, CHECKED; the RTC bus has its own 4.7 k line | Reflow | PN 2026-11-27 | Stock not looked up; no snippet. The number is formed from Yageo's code and was not seen in any document |
| 4.7 k 1% pull-ups for the RTC bus | Yageo RC0402FR-074K7L | 2, to 3V3_SW | 0402, about 0.35 mm | CHOSEN BY THE REVIEWER; not checked by a second reader | Reflow | PIN; PN 2026-11-27 | Stock not looked up |
| RTC backup-pin series resistor, 1 k 1% | Yageo RC0402FR-071KL (a line already on this list) | 1 more | 0402 | CHOSEN BY THE REVIEWER from Micro Crystal's 100 to 1000 ohm range; not checked by a second reader | Reflow | PT; PN 2026-11-27 | Stock not looked up |
| 200 ohm 1% (CSI_REXT) and 2 ohm 1% (SMPS snubber) | Yageo RC0402FR-07200RL; Yageo RC0402FR-072RL | 1 each | 0402, about 0.35 mm | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PIN; PW 2026-11-27 | Stock not looked up; no snippet. Both are the Nucleo's parts |
| Cell-voltage divider at PA8: 1 M over 560 k, 1% | Yageo RC0402FR-071ML; Yageo RC0402FR-07560KL | 1 each | 0402, about 0.35 mm | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PIN; PW 2026-11-27 | Stock not looked up; no snippet. Caveat: no guaranteed accuracy against the MCU's 5 uA pin-leakage limit; 100 k over 56 k fits the same pads |
| External core regulator kit (fallback) | See the fallback table below | 0 fitted; buy 10 sets | - | Provision and purchase DECIDED BY THE USER; parts CHOSEN BY THE REVIEWER | Not fitted unless needed; by hand, hot air | DN 2026-11-27; PT | See below |
| 48 MHz crystal and load capacitors | NDK CS13734-48M, the current number for NX1612SA-48MHZ-EXS00A-CS13734 (DigiKey 644-CS13734-48MCT-ND; neither number verified by the checker); capacitors Yageo CC0402CRNPO9BN8R2, 8.2 pF C0G | 0 fitted: one crystal footprint, two capacitor footprints. Buy a few of each as spares | Crystal 1.6 x 1.2 mm, 0.30 mm typical; capacitors 0402 | PROPOSED: do not fit (the study's pick, CHECKED with caveat) | Unfitted | PIN; RN 2026-11-26; OQ defaults; PN 2026-11-27 | Snippet: 5,894 on one DigiKey page; 16-week lead time on another. Caveat: the boot ROM's serial boot without the crystal is untested |
| 32.768 kHz crystal | None; not fitted | 0 | - | No part; optional unfitted link from the RTC clock output | - | PIN | - |
| Sensor 12 MHz oscillator | ECS ECS-2520MVLC-120-CN-TR (DigiKey 50-ECS-2520MVLC-120-CN-TRCT-ND) | 1 | 4-pad, 2.5 x 2.0 mm, 0.90 mm (corrected by the checker; 0.8 mm reported) | CHOSEN BY THE REVIEWER, CHECKED with caveat | Reflow | PIN; PL-09; PN 2026-11-27 | Stock thin. Snippets conflict: 4,856 on one regional page, 0 on another; 9-week lead time; the checker saw no figure. Buy early. ECS datasheet not stored: start-up time, jitter and output levels unread. Alternate ECS-2520MVLC-120-BN-TR (+/-50 ppm) |
| RTC | Micro Crystal RV-3032-C7-32.768KHZ-2.5PPM-TA-QC (DigiKey 2195-RV-3032-C7-32.768KHZ-2.5PPM-TA-QCCT-ND) or -TA-QA (DigiKey 2195-RV-3032-C7-32.768KHZ-2.5PPM-TA-QACT-ND), whichever the live page has in stock | 1 | C7 ceramic, 3.2 x 1.5 mm, 0.8 mm | Part DECIDED BY THE USER; ordering code corrected by the checker (the picker preferred QA on a stock reading that did not hold; the two differ only in qualification) | Reflow; hot-air rework at 270 C at most | PN 2026-11-11, 2026-11-27; PT open point 7 | Snippets: QC 19,348 on a regional page, about $3.18; QA about 10,000 to 12,700, about $3.33. Every RTC figure is from a third-party mirror of the application manual. It cannot run from the cell with a 1.8 V bus: see the next row |
| Orientation sensor (first to cut) | ST LIS2DW12TR (DigiKey 497-17718-1-ND) | 1 | LGA-12, 2.0 x 2.0 mm, 0.7 mm | PROPOSED: default "unless the owner objects"; the part is CHECKED | Reflow only: pads under the body | OQ, set-aside list; PN 2026-11-11, 2026-11-27 | Snippets conflict: US page 0 with a 20-week lead time; regional pages about 176,000 to 213,000. Strap CS and SA0 high: address 0x19 |
| Camera module | CAM-6G3-073CLR | 1 | Head 6.5 x 6.5 x 4.68 mm, 12.4 x 8.0 mm overall, 30-pin flex | DECIDED BY THE USER | By hand; in a cut-out, potted | PN 2026-10-13, 2026-11-11, 2026-11-26 | prototype-parts-and-camera-research.md (updated 2026-10-18): DigiKey 25 at $21.44, later 24; Mouser 8 |
| Camera connector | Hirose BM28B0.6-30DS/2-0.35V(51) (DigiKey 26-BM28B0.6-30DS/2-0.35V(51)CT-ND) | 1 (order about 15 for ten boards) | Receptacle, 30 positions, 0.35 mm pitch; body 7.85 x 1.7 mm, 0.6 mm high | PROPOSED; the mate is CHECKED with caveat (plug on the module, receptacle on the board) | Reflow: 0.08 mm stencil, 250 C peak, two cycles at most; no flux if touched up by hand | PL-09; datasheets/README.md; OQ items 27, 31; PN 2026-11-27 | Snippet: about 91,858 on a regional page. Power pads are 0.53 x 0.33 mm (corrected by the checker). Rated for 10 mating cycles |
| SD card socket | Molex 503398-1892 (DigiKey WM11190CT-ND) | 1 | Push-push, 1.28 mm high; the 13.1 x 14.05 mm footprint is not confirmed | PROPOSED; cannot be verified, because no drawing was read. Alternate Molex 104031-0811 (DigiKey WM6357CT-ND): push-pull, 1.42 mm | Reflow | PN 2026-11-26, 2026-11-27 | Snippets conflict: about 39,500 to 48,000 (Canada, Mexico); 65,510 (UK); a punch-out page out of stock; US page 14-week lead time with no count. Do not draw the detect symbol or fix the setback until Molex drawing SD-503398-003 is read |
| RGB LED | SunLED XZMDKCBDDG45S-9 (DigiKey number not seen; product page 4902045) | 1 | Gull-wing, mounted lens-down over a 3.2 +/-0.1 mm hole; body 3.2 x 2.8 mm, 5.2 mm over the leads, 1.9 +/-0.2 mm high | PROPOSED; datasheet read, CHECKED with caveat. Common anode on pin 2; red 1, blue 3, green 4. Alternate Würth 156125M173000: different footprint, datasheet unread | Reflow; keep hot air and tweezers off the lens | PN 2026-11-26, 2026-11-27; OQ item 24 | Snippet: 265,948 on an Austria page; 9-week lead time. Caveats: it can reach 2.1 mm, over the 2.0 mm target; the footprint may need mirroring, so check with a part in hand |
| LED series resistors | Values: 1.0 k red; 510 ohm green; 510 ohm blue | 3 | See the resistor rows | CHOSEN BY THE REVIEWER, CHECKED | Reflow | PN 2026-11-27 | About 2 mA each at a 3.7 V cell; green and blue fade below about 3.3 V |
| Dials (exposure, ASA) | Alps RK10J11E0034 | 2, plus at least one sacrificial part | Through-hole thumbwheel, 14 mm, legs re-formed, face-down | DECIDED BY THE USER | By hand; one 3 s joint allowed per terminal | PN 2026-11-25; HB | 2026-11-25: listing could not be opened; snippets disagreed (none, or about 1,900); Alps status Standard |
| Shutter switch | Omron D2MQ-4L-105-1 | 1 | Snap-action, 8.2 x 6.5 x 2.7 mm, straight terminals, laid flat | DECIDED BY THE USER | By hand; terminals trimmed and joggled | PN 2026-11-26 (re-lock); HB | 2026-11-26: stock of this variant "has not been checked on a live page". SW1396-ND is the -L variant. The beta circuit switches at most 4.2 V and 4.2 mA, below Omron's stated minimum for the gold model (5 V, 5 mA): tolerated by the circuit, not guaranteed by Omron |
| Cell | Grepow GRP292434-1C-3.7V-210mAh with PCM (DigiKey 15285146) | 1 | Pouch pack, 3.8 x 24.1 x 36.5 mm maximum | DECIDED BY THE USER | By hand; protection board unfolded, leads soldered to pads | PW 2026-11-25 (three entries) | Snippets 2026-11-25: Active, 91 in stock, $7.99; Marketplace item, ships separately, flat fee as much as $130 |
| ST-LINK header | Samtec FTSH-107-01-L-DV-K, land pattern only | 0 | STDC14 pads; header is 5.97 mm tall | DECIDED BY THE USER (bare pads, pogo fixture) | Not fitted | PN 2026-11-26 (two entries); OQ item 9 | Stock not looked up. Pad numbering is in the design values (CHECKED against UM2448 Table 6) |
| Debug probe | STLINK-V3MINIE | 1 in total | - | PROPOSED by the reviewer; listed as resolved in OQ item 9; no user sentence naming it | - | PN 2026-11-26; PT open point 6; OQ item 9 | None |
| Pogo fixture parts | None | 1 in total | - | TO CHOOSE; the user makes it | - | PN 2026-11-26 | None |
| Remaining pull and series resistors | Values only: 100 k (PE6; Yageo RC0402FR-07100KL would follow the series, not picked). Not yet set: pull-ups on the flash chip select, IO2 and IO3; series resistors on the SD clock and the strobe; SD card-detect pull-up and its rail | - | - | TO CHOOSE | Reflow | PIN | None |
| Pads with no part | Charge + and −, BOOT0, BOOT1, latch force-on, PG10, PD0, PE0 | - | - | - | - | PW 2026-11-25; PIN | - |

## Fallback core regulator kit: buy, do not fit

For the provision described in the [power tree](../power/beta-power-tree.md). Ten kits. Stock figures are cached regional DigiKey pages returned by search on November 27, not the live US page. The study of November 27 moved the coil to the main buck's line, named a part for the 22 uF line and checked the jumper.

| Part number | Qty per board | Purpose | Stock remark |
|---|---|---|---|
| TI TPS62825DMQR (DigiKey 296-49521-1-ND) | 1 | 2 A adjustable buck, 6-pin 1.5 x 1.5 mm no-lead. The 3 A TPS62826DMQR has the same footprint. Also the conversion part for the main buck if its floor proves short: 1.83 V with 205 kilohm over 100 kilohm, both 0.1%, and the 120 pF below | about 10,000 to 22,000 shown; about $1.29 |
| Murata DFE201610E-R47M=P2 (the main buck's coil line) | 1 | 0.47 uH coil, 2.0 x 1.6 x 1.0 mm, on TI's tested list and on TI's evaluation board. Changed by the study from TDK TFM201610ALM-R47MTAA, which stays the alternate; the checker did not rule on the change | Murata: snippet about 96,390 on one regional page. TDK: thin in snippets (2,431 on an Irish page; 903 on an aggregator dated 06-12-2026) and called being discontinued at RS |
| Murata GRM188R61A106KE69J | 4 | 10 uF 10 V X5R 0603: two input, two output | Doubtful: snippets conflict, see the main table |
| Murata GRM188R60J226MEA0J, 22 uF 6.3 V X5R 0603 (proposed by the study: the part the Nucleo fits on its SMPS output) | 2 | Alternate output capacitors, if a scope check shows too much droop | not looked up |
| 34.8 kilohm 1% 0603 (Yageo RC0603FR-0734K8L or equivalent) | 1 | Feedback, top | not checked |
| Panasonic ERA-3AEB104V | 1 | Feedback, bottom: 100 kilohm 0.1% 0603 | snapshots conflict |
| Murata GRM1555C1H121JA01D | 1 | 120 pF C0G 0402 feed-forward | in stock on the pages seen |
| Rohm PMR03EZPJ000, low-resistance metal jumper, 0603 (DigiKey 846-PMR03EZPJ000CT-ND, not seen by the checker). The Nucleo uses it for the same links | 2, plus spares; one spare serves the bypass link site | The two selection links. Fitted in both builds, in one position or the other. CHECKED: 0.5 milliohm maximum and 22.4 A per Rohm's product page (search summary; datasheet not stored); 0.35 mm high | snippets: about 127,000 on several regional pages, 76,394 on another; $1.16 |
| 10 kilohm 0402 (the main table's Yageo RC0402FR-0710KL line) | 1 | Holds the unused SMPS output at ground. Fitted in both builds | see the main table |

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
| RTC regulator | TPS7A0218PDBVR | DN 2026-11-27: the RTC runs from 3V3_SW with the cell on its backup pin |
| Tag-Connect debug | TC2030-IDC-NL, TC2070 | PN 2026-11-26 |
| Earlier shutter switches | B3U-3000P, D2MQ-4L-1 (silver), D2MQ-4L-105-1-L | PN 2026-11-26 |
| Dual N-FETs | Si1922EDH, DMN2990UDJ | PW 2026-11-26 |
| Hobby thumbwheels and dual-track dials | uxcell B503, RK10J12 parts | PN 2026-11-25 |
| 40 MHz crystal | CX3225SA40000D0PTWCC | PL (recovered design); PIN |
| Adapter level shifters and LDOs | BSS138, 74LVC1T45, LD39050 | PIN (direct 1.8 V) |


## Design values

From the study of November 27, after the checker's corrections. These are paper figures from datasheets, typical curves and hand arithmetic; nothing was measured. Document names: DS14791 = MCU datasheet; AN5967 and AN6000 = ST hardware and power notes; DS12968 = sensor datasheet.

| Item | Value | Basis |
|---|---|---|
| **1.8 V rail** | | |
| Supply window | 1.746 to 1.89 V at the 1V8_AUX pins; 1.71 to 1.935 V on 1V8_MAIN; sensor I/O 1.7 to 1.9 V | DS14791 Table 24 p.140; DS12968 Table 12 p.31 |
| Absolute maximum on the 1.8 V pins | 1.98 V on the analog pins, 2.0 V on VDD and VDDIOx; the fixed buck's 1.83 V ceiling leaves 150 mV | DS14791 Table 21 p.138; added by the checker |
| 1V8_AUX load, typical | about 150 mA | SMPS input 78.5 mA, sensor core 57 mA, sensor I/O 8.5 mA, CSI, ADC and dials about 3.4 mA, oscillator 3 mA (assumed) |
| 1V8_AUX load, design-max | about 213 mA at 25 C; about 337 mA at 85 C junction (corrected by the checker; the picker's 249 and 414 mA used the wrong ratio) | Core current maximum x 0.612, the ratio of DS14791 Table 39 to Table 34; ST gives no maximum for the SMPS input at these temperatures, so both sets are estimates |
| Load switch drop | 8.3 mV typical; 16.8 mV design-max; 26.6 mV at 85 C (corrected by the checker) | TPS22918 at 1.8 V in: 55 mohm typical, 79 mohm maximum to 85 C (p.5) |
| Fixed buck, margin at the 1V8_AUX pins | floor: +20.7 mV typical, +12 mV design-max, +2.4 mV at 85 C (corrected by the checker); ceiling 1.830 V, 60 mV below 1.89 V | 1.780 V minimum less regulation, half ripple, 3 mV copper (assumed) and the switch drop; 1.820 V maximum plus 7 mV power-save rise and 3 mV |
| Adjustable buck at 1.80 V, 1% resistors | 1.7585 to 1.8425 V at the buck; below the floor at the pins even at typical load (-0.8 mV) | Why the fixed part was chosen |
| Adjustable buck at 1.80 V, 0.1% resistors | 1.7796 to 1.8204 V: the fixed part's floor with three more parts | VFB 0.594 to 0.606 V (p.5) |
| Adjustable buck trimmed to 1.83 V | 205 k over 100 k, both 0.1%, and 120 pF: 1.8093 to 1.8508 V at the buck; +50 mV at the pins at typical load; top 1.871 V, 19 mV below 1.89 V | The conversion option on the same pads; 1% resistors would exceed the ceiling |
| 1V8_MAIN soft start | about 585 us/V (450 to 730); limit 20 to 1500 us/V | TI typical figures only; no maximum given (DS14791 Table 25 p.141) |
| CT capacitor for the 1V8_AUX rise | 470 pF: 289 us/V by formula, 333 us/V by table; limit 20 to 1500 us/V | TPS22918 Eq 3 and Table 2 p.14 |
| 1V8_AUX capacitance and inrush | about 26 uF nominal; about 78 mA inrush with 470 pF | AN5967 Table 6 plus about 2.5 uF assumed |
| Bulk on 1.8 V | about 50 uF nominal with the switch closed; TI tested this buck to 47 uF with 0.47 uH. Add no more bulk | TPS6282x Table 8-3 p.13 |
| QOD discharge of 1V8_AUX | 670 to 890 us/V from TI's table; 1580 to 2380 us/V from an RC estimate; limit 1500 us/V. Measure it | TPS22918 Table 1 p.13 and pull-down 45 to 60 ohm (p.5) |
| Ripple | 8 to 11 mV p-p at the buck by arithmetic, 8 to 15 mV by the checker's reading of TI's scope shot; about 5 mV at the 1V8_AUX pins; ST allows 20 mV p-p | Power-save mode over the whole camera load; AN6000 Tables 7 to 9 |
| Main buck coil currents | normal peak about 1.0 A; fault peak 4.44 A (4.67 A with the coil 30% low, checker); coil 4.8 A in TI's table | TPS6282x p.6, p.9, Table 8-5 |
| Cell current into the 1.8 V buck | typical 73 / 83 / 102 mA at 4.2 / 3.7 / 3.0 V; design-max 113 / 129 / 159 mA; about 241 mA at 3.0 V and 85 C (design-max and 85 C corrected by the checker) | 92% and 90% efficiency read from a typical graph |
| Average cell current over a photo cycle, 1.8 V buck only | about 48 mA at 3.7 V for a short exposure; about 57 mA for a 1 s exposure | Assumed cycle times, not measured |
| Latch closing to both 1.8 V rails valid | about 2.2 to 2.4 ms (corrected by the checker; 2.5 to 3 ms reported) | Sum of typical delays |
| **Regulators** | | |
| 3V3_SW rise | 50 us/V typical; 70 to 150 us/V by the checker's reading of the datasheet's scope figures; ST allows 20 to 1500 us/V | NCP115 slow slew 20 mV/us, typical only (p.3) |
| SD supply ramp | 110 us typical from 0.5 V to 2.7 V against a 0.1 ms minimum (corrected by the checker; the 165 us reported was for 0 to 3.3 V) | SD rule from search snippets of secondary sources, not the specification text |
| 3V3_SW inrush at enable | about 120 mA for 165 us with one 10 uF at the output | 6 uF effective assumed |
| 3V3_SW fall rate | 1 uF to about 19 uF effective on the rail; with one 10 uF: 120 to 180 us/V at the steepest, 310 to 470 us/V averaged | Discharge 66 to 100 ohm. The 19 uF bound is an interpretation: ST does not say between which voltages the rate is measured (checker) |
| 3.3 V LDO capacitors | 10 uF at the input; 10 uF at the output near the socket; 100 nF at each of the two VDDIO5 balls | NCP115 p.12; AN5967 Table 6 |
| 3.3 V dropout at the card's 120 mA | 86 mV typical, 104 mV maximum; the rail sits at about 3.30 V from a 3.4 V input | 215 and 260 mV at 300 mA, scaled (p.3) |
| Lowest LDO input that keeps 2.7 V at the card | about 2.80 V at 120 mA; 2.84 V at 160 mA | Card figures are the Swissbit S-56u's, not the card that will be used |
| 3.3 V LDO heat | 108 mW worst case, about 22 C rise | 0.9 V x 0.12 A; 208 C/W |
| 3.3 V enable pull-down (PD7) | 10 k fitted; the rule is 47 k or less | 5 uA x 10 k = 50 mV against the 0.4 V off level. One group assumed 47 k; both pass. Typical thresholds 0.57 to 0.74 V (corrected by the checker) |
| Firmware timing for 3V3_SW | wait at least 1 ms after enabling, then the card's own 1 ms and 74 clocks; stay off at least 5 ms, 10 ms to be safe, before re-enabling | Off time added by the checker from snippets of secondary sources |
| 2.8 V rail window | 2.744 to 2.856 V against the sensor's 2.65 to 2.95 V | TLV700 +/-2% (p.6); DS12968 Table 12 |
| 2.8 V dropout and lowest cell node | about 22 mV typical, 31 mV scaled worst, at 25 mA; regulates down to about a 2.83 V node; sensor in range to about 2.68 V. At the 106 mA start pulse the node must be above 2.74 V to stay in range, 2.83 V to stay in regulation (corrected by the checker) | Typical figures only for the 2.8 V version |
| 2.8 V LDO capacitors | input 1 uF; output two 10 uF footprints at the camera connector | Sensor asks for at least 10 uF; ST's adapter fits 4.7 uF + 100 nF |
| 2.8 V start surge | 0.22 to 0.86 A from the cell node for about 40 to 165 us; about 0.2 V dip on the cell node (checker) | TLV700 has no stated soft start; current limit p.6; pack impedance up to 230 mohm |
| 2.8 V LDO heat | 35 mW worst case, about 8 C rise | 1.4 V x 0.025 A |
| 1.2 V rail window | 1.15 to 1.24 V against the sensor's 1.08 to 1.26 V (typical 1.15 V) | NCP115 +/-40 mV and load regulation (p.3) |
| 1.2 V dropout from 1.75 V in | 0.51 V available; about 0.13 to 0.2 V needed at 86 mA | Read from the 1.8 V version's typical curve; no figure exists for this condition |
| 1.2 V LDO power | 52 mW maximum, 34 mW typical while streaming; about 11 C rise | 0.6 V x 86 mA |
| 1.2 V start-up with EN tied to IN | 0.36 to 0.40 A from 1V8_AUX for about 60 us with two 10 uF; about 0.18 A with one (corrected by the checker: the output does not follow the 1V8_AUX ramp) | NCP115 Fig. 42 and 43 p.11 |
| 1.2 V LDO capacitors | input 1 uF on 1V8_AUX; output two 10 uF footprints at the camera connector | DS12968 Table 9 p.24 |
| XSHUTDOWN pull-down (PF1) | 10 k; 34 k is the limit | 0.51 V low level / 15 uA leakage |
| Sensor rail order | PWR_ON, 2.8 V within about 0.2 ms, then 1V8_AUX with 1.2 V, XSHUTDOWN last | Allowed by DS12968 section 7.3; ST's adapter brings up 1.15 V, then 2.8 V, then 1.8 V (checker) |
| **Latch and LED** | | |
| Peak current through the latch FET | about 0.2 A; design for 0.25 A | 0.55 W / 3.0 V = 0.183 A plus LEDs |
| The tree's "40 ms" | 40 ms above 2.5 V gate drive at a 3.0 V cell with the prototype's 100 k and 2.2 uF; 112 ms above 1.8 V | 220 ms x ln(3.0/2.5); the AO3401 is not specified below 2.5 V |
| Off-state leakage | 2 uA guaranteed maximum at 25 C: 17.5 mAh a year, 8.3% of the cell | Latch FET and HOLD FET, 1 uA each; the pack's protection board draws up to 5.5 uA |
| Trigger network | 47 k gate to source; 10 k switch NO to gate; 10 k HOLD drain to gate, force-on pad on the drain; 10 uF switch common to ground; 1 k switch NC to ground; 220 nF gate to source; 22 nF gate to drain | Gate divider 0.825; time constant 570 ms |
| Start window, gate drive above 1.8 V | about 170 ms at a 3.0 V cell, 365 ms at 4.2 V. Capacitor 20% low: 133 and 286 ms by formula (137 and 294 ms simulated). With 4.7 uF: 73 and 163 ms (78 and 172 ms simulated) | 570 ms x ln(initial / 1.8); formula figures from the checker |
| Start window, gate drive above 1.5 V | about 275 ms at 3.0 V, 470 ms at 4.2 V; SI2333DDS only, not the FDN306P alternate | SI2333DDS has a 1.5 V row |
| Prototype's 2.2 uF with the 47 k pull-up | 28 ms at 3.0 V (corrected by the checker; 33 ms reported): too small | Why the trigger capacitor is 10 uF |
| Gate drive once HOLD has taken over | 3.46 V at 4.2 V, 2.47 V at 3.0 V, 2.31 V at the 2.8 V cut-off | Vcell x 47 / 57 |
| Start-up surge into the input capacitors | at 4.2 V: 0.19 A into 12 uF, 0.34 A into 22 uF, 0.69 A into 47 uF nominal; about 1.0 A with tolerances stacked (checker). The pack trips at 3 A minimum | 15 V/ms from the 22 nF capacitor; square-law simulation, not SPICE or a bench |
| Turn-off after HOLD is released | the board stays up 10 to 23 ms, then the input falls at about 0.7 V/ms, about 3 ms to the buck's lock-out | 47 k x 242 nF; fall rate added by the checker |
| Shutter held after HOLD is released | power stays on about 0.64 s at 3.0 V and 0.84 s at 4.2 V (0.61 and 0.80 s by the checker's arithmetic) | Simulated; 2.6 times the prototype's tail |
| Trigger capacitor reset | 10 ms time constant; reset in about 50 ms | 1 k x 10 uF |
| Cell connection, no press | the gate sees 0.38 V of a 4.2 V step nominal, 0.46 V with tolerances: the FET conducts weakly for a few milliseconds, harmlessly (corrected by the checker; "stays off" reported) | Threshold 0.4 V minimum; 470 nF would give 0.19 V nominal |
| Self-turn-on margin, camera off | 8.5 uA of gate-node leakage needed at 25 C against 1 uA maximum; at 70 C the HOLD FET's limit is 10 uA, over the threshold on paper | 0.4 V / 47 k |
| Switch contact load | NO: at most 4.2 V, 0.42 mA peak. NC: at most 4.2 mA, about 0.7 mA after a normal shot | Omron's minimum for the gold model is 5 V 5 mA |
| LED resistors and currents | red 1.0 k: 1.9 mA at 3.7 V, 1.3 mA at 3.0 V. Green and blue 510 ohm: 2.0 mA at 3.7 V, 0.8 mA at 3.0 V. A part 0.7 V above typical: 1.5 mA at 4.2 V, 0.6 mA at 3.7 V, dark at 3.3 V (checker's straight arithmetic) | Forward voltages read by eye from typical curves |
| Relative brightness | green about 6.5 times red and blue at equal current | 695 against 108 and 98 mcd at 20 mA |
| Gate pull-downs: HOLD, red, green, blue | 10 k each | 5 uA x 10 k = 50 mV against a 0.45 V threshold |
| **MCU support** | | |
| Decoupling count | 24 x 100 nF, 13 x 1 uF, 2 x 10 uF, 4 x 15 uF, 1 x 4.7 uF, 1 x 2.2 nF: 45 capacitors; 48 parts with the coil, 2 ohm and ferrite | AN5967 Rev 5 Table 6 p.12-13, which gives no case size; count confirmed by the checker |
| 100 nF by pin group | VDD 6; VDDA18AON 1; VDDA18PLL 1; VDDIO3 2; VDDIO2 4; VDDIO4 2; VDDIO5 2; VDDA18ADC 1; VDDA18CSI 1; VREF+ 1; VDDA18PMU 1 (after the ferrite); VDDSMPS 2 | One per pin. If the package edge is crowded, two of VDDIO2's four and one of VDDIO4's two are the first to leave unfitted: those banks carry no switching pins |
| 1 uF by pin group | VDDCORE 9; VDDCSI 1; VDDSMPS 2; VREF+ 1 | One per VDDCORE pin |
| Pins with no capacitor | VBAT (tied to VDD); VDD33USB and VDDA18USB (tied to VSS, USB unused) | AN5967 Tables 5 and 6 |
| SMPS output network | 1 uH coil, 2 ohm with 2.2 nF, 4 x 15 uF | ST's table; the Nucleo fits 4 x 22 uF. DS14791 p.26 says 0.9 uH typical, Table 27 and AN5967 say 1.0 uH; a 1.0 uH +/-20% part covers both |
| SMPS coil ripple and peak | 0.19 A p-p; peak 2.29 A at nominal inductance, 2.32 A with the coil 20% low (corrected by the checker) | Saturation 3.3 A per the Nucleo BOM, 3.1 A in one distributor snippet; ST's floor is 3.0 A |
| Coil resistance loss | 54 mV and 54 mW at 1 A; 108 mV and 216 mW at 2 A | 0.054 ohm maximum; inside the regulation loop |
| Snubber dissipation | 17 mW (19 mW at 1.89 V) | 2.2 nF x V^2 x 2.4 MHz; an 0402 is rated 62.5 mW |
| Core link drop | 1.0 mV and 2 mW at 2 A | 0.5 mohm jumper |
| Cell divider at PA8 | 1 M over 560 k with 10 nF: 1.508 V at 4.2 V, 2.7 uA | Pin reaches the 1.746 V reference floor only at a 4.80 V cell |
| Cell-sense settling | wait 30 ms after power-up before the first reading; space burst samples | 3.6 ms time constant; spacing added by the checker |
| Cell-sense leakage error | about 50 mV at the cell per 50 nA of pin leakage; no guaranteed accuracy at the 5 uA limit | 100 k over 56 k fits the same pads with a tenth of the error |
| PWR_ON pull-down | 47 k | 5 uA x 47 k = 0.235 V against the load switch's 0.5 V |
| I2C pull-ups | camera bus: 2.2 k, 37 to 93 ns rise on 20 to 50 pF, limit 64 pF at 1 MHz. RTC bus: 4.7 k to 3V3_SW (about 200 ns on 50 pF); orientation-sensor bus 2.2 k | At 3.3 V the RTC allows 400 kHz |
| Crystal load capacitors, unfitted | 2 x 8.2 pF C0G | 7 pF load, about 3 pF stray |
| Crystal drive margin, if ever fitted | 1.64 to 2.10 mA/V needed against 1.95 mA/V available | Thin on paper; the crystal's shunt capacitance was not read |
| Sensor clock levels and start wait | high at least 1.26 V, low at most 0.54 V; wait 20 ms or more before releasing XSHUTDOWN until the ECS datasheet is read (corrected by the checker; the 10 ms reported was unsourced) | DS12968 Table 15 p.33 |
| **RTC, sensor, connectors** | | |
| RTC drain on the cell, camera off | 170 nA typical, 270 nA maximum at 25 C: about 1.5 to 2.4 mAh a year, about 1% of the cell | RV-3032 manual p.128, backup current in level mode (third-party copy) |
| RTC first-boot programming | write EEPROM C0h = 60h once: clock output off, level switchover, trickle charger off | RV-3032 manual p.45, p.58 to 60, p.141 (third-party copy) |
| RTC on the cell with a 1.8 V bus | not possible: a logic high needs 2.4 to 3.36 V | VIH = 0.8 x VDD |
| RTC backup pin | works in level switchover mode only, and only with the supply pin above about 2.4 V: supply pin on 3V3_SW, cell on the backup pin. It does not work with a 1.8 V supply pin | Level mode runs from the supply pin above its threshold whatever the backup voltage; direct mode would stay in backup |
| Capacitor-only backup | not workable: 100 uF holds about 2.5 minutes, 11 mF about 4.6 hours; a month needs about 1.7 F | 0.25 V usable at 165 nA |
| RTC support parts | 100 nF at the supply pin; 1 k in series with the backup pin and 1 uF at the pin; 10 k from EVI to ground; INT and CLKOUT unconnected; two 4.7 k bus pull-ups to 3V3_SW | Backup-pin network from the maker's primary-cell circuit, p.141; the 1 uF rides through a brief loss of contact |
| Orientation sensor strapping | CS and SA0 to VDD_IO: address 0x19; 100 nF at pin 10; 100 nF and 10 uF at pin 9 | Grounding SA0 would waste 37 uA |
| Camera receptacle land pattern | signal pads 0.18 x 0.31 mm with 0.17 mm gaps; power pads 0.53 +/-0.02 x 0.33 mm, centres 6.31 mm apart (corrected by the checker; 0.35 mm reported); whole pattern 6.84 x 1.90 mm; keep-out 8.05 x 1.9 mm | Stored Hirose drawing and catalog p.7 |
| Stencil at the camera receptacle | 0.08 mm | Area ratio 0.71; 0.52 at 0.10 mm |
| Hirose soldering limits | by hand: 340 +/-10 C within 3 s recommended, 350 C for 3 s maximum, no flux; reflow 250 C peak, two cycles | Catalog p.4 and p.10; corrected and added by the checker |
| Card socket position | socket front 2.8 mm behind the outer face for a flush card, 3.3 mm for a card 0.5 mm below it; finger relief 1.4 mm; 6.2 mm clear outside | From the project note of 2026-11-26, not from a document read in the study; do not fix it until the Molex drawing is read |
| STDC14 pad numbering | 1 NC, 2 NC, 3 1V8_MAIN, 4 SWDIO (PA13), 5 GND, 6 SWCLK (PA14), 7 GND, 8 SWO (PB5, optional), 9 NC, 10 NC, 11 NC or a test point, 12 NRST, 13 to PE6 (USART1_RX), 14 from PE5 (USART1_TX) | UM2448 Rev 5 Table 6 p.23; confirmed by the checker |

## Before ordering

1. **Check stock on the live DigiKey page where snippets were doubtful or disagreed:** GRM188R61A106KE69J; TPS22918DBVR; SI2333DDS-T1-GE3; C1608X5R0J156M080AC; ECS-2520MVLC-120-CN-TR; DFE201612P-1R0M=P2; LIS2DW12TR; 503398-1892; RV-3032-C7 (QC against QA); RC0402FR-0710KL; RC0402FR-07510RL; RC0402JR-070RL; GRM155R71C224KA12D; GRM155R61E105KA12D; TFM201610ALM-R47MTAA (alternate); ERA-3AEB104V (first list).
2. **Check lines for which no stock figure was seen:** RC0402FR-071KL, RC0402FR-072K2L, RC0402FR-07200RL, RC0402FR-072RL, RC0402FR-071ML, RC0402FR-07560KL, CC0402KRX7R9BB222, CC0402KRX7R9BB103, CC0402CRNPO9BN8R2, GRM188R60J226MEA0J, FTSH-107-01-L-DV-K, and the first list's Alps dials and Omron switch. The checkers saw no figure for GRM155R71C104KA88D or the SMPS coil.
3. **Confirm DigiKey numbers that were inferred or not seen by the checker:** 490-18109-1-ND (buck coil), 490-14372-1-ND (10 uF), 490-10017-1-ND (1 uF), 311-0.0JRCT-ND (0 ohm), 490-3261-1-ND (100 nF), 445-8027-1-ND (15 uF), 644-CS13734-48MCT-ND (crystal), 846-PMR03EZPJ000CT-ND (jumper). No DigiKey number was seen for SI2333DDS-T1-GE3 or XZMDKCBDDG45S-9.
4. **Picks the checker could not verify** (no pick was marked low confidence): Molex 503398-1892, until drawing SD-503398-003 is read; GRM188R61A106KE69J at the three LDOs (bias loss, height, fitted count); TPS7A2028PDBVR as the 2.8 V alternate.
5. **Check part status:** DFE201612P-1R0M=P2 is marked no longer manufactured in one distributor snippet; TFM201610ALM-R47MTAA is called being discontinued at RS; order SI2333DDS-T1-GE3, not SI2333DS or the -T1-BE3 listing.
6. **Decisions for the owner** (the study marked only the first for the user; the others are choices its picks leave open):
   - 48 MHz crystal: leave it unfitted (the study's recommendation) and buy a few with their 8.2 pF pairs in case UART serial boot stalls?
   - Thin 1.8 V floor: add margin now, by a second TPS22918DBVR feeding only VDDA18CSI (the checker's suggestion), the bypass link if ST allows it, or the 1.83 V adjustable conversion, or wait for the bench?
   - SMPS output capacitors: 15 uF as ST's table says, or the 22 uF the Nucleo fits?
   - Orientation sensor: still the default "unless the owner objects".
7. **Smaller choices left to the reviewer:** 1 uF part for the four unassigned positions; the 100 k for PE6 and the pull and series resistors not yet valued; cell divider 1 M over 560 k or 100 k over 56 k, when the low-battery level is set; whether to fit one or two 10 uF on each sensor rail, after the first scope.
8. **Datasheets to read or upload before the footprints are frozen:** Micro Crystal's own RV-3032-C7 application manual and datasheet (only third-party mirror copies are stored); Molex drawing SD-503398-003 (and SD-104031-001 if the alternate is used); the ECS-2520MVLC datasheet; Murata's sheets for DFE201610E-R47M, DFE201612P-1R0M and GRM188R61A106KE69J; TDK C1608X5R0J156M080AC; ST TN0018 (LIS2DW12 land pattern); UM2910 (STLINK-V3MINIE); the CAM-6G3-073CLR schematic; the TPS7A2028 and Würth 156125M173000 datasheets if either alternate is to be used. Vishay documents 63861 and 65900 are Rev A and may not be the latest.
9. **Buy early or buy extra:** the MCU (first list); ECS-2520MVLC-120-CN-TR and SI2333DDS-T1-GE3 early; 15 to 20 NCP115 parts across the two lines; about 15 camera receptacles.

## Open points from the study

Carried from the pickers' open points and from every requirement the checkers found missing (marked "checker"). They are not ordering items; they belong to the schematic, the firmware and the first board.

**Schematic and layout**

- Margin options for the 1.8 V floor: the bypass link (+20 mV, only if ST allows one rail for both supply groups); the sensor's 1.2 V regulator fed from 1V8_MAIN (+7 mV, changes the agreed tree); the adjustable TPS62825DMQR at 1.83 V (+29 mV); or a second TPS22918DBVR, also enabled by PWR_ON, feeding only VDDA18CSI, for about 29 mV at any core current (checker).
- For the 1.83 V conversion: three 0402 footprints at the buck's FB pin, with the top resistor's pads joined by a copper neck so the fixed part needs nothing fitted. The 205 k 0.1% resistor is not a list line (Panasonic ERA-3AEB2053V was named from memory and not looked up). An open top resistor puts the cell voltage on pins limited to 1.98 V, so meter FB to VOUT before first power (checker).
- State in the schematic notes that ST's reference draws a 3 A supply for the PWR_ON rail and a separate 500 mA regulator for VDD and VDDA18AON; the 2 A part covers ST's worst listed SMPS input of 757.5 mA (checker).
- The load side of the switch (about 26 uF) is slightly larger than the 1V8_MAIN side (about 24 uF), against TI's advice; at power-down 1V8_AUX feeds back through the switch's body diode (checker).
- When the bypass link is fitted, remove the QOD link or the TPS22918, or its pull-down loads the rail with 30 to 40 mA whenever PWR_ON is low. Put a test pad on the buck's PG pin.
- The 2.8 V regulator's footprint must be fixed before layout; the study chose SOT-23-5. Give its enable a link or 0 ohm option instead of hard-wiring it to PWR_ON, so ST's own order (1.15 V, 2.8 V, 1.8 V) can be tried (checker). PWR_ON gains this enable as a third load.
- XDFN4 footprint: onsemi's pattern leaves 0.11 mm to the centre pad. Confirm the fabricator's solder-mask web or reduce the centre paste aperture before the stencil is ordered.
- The sensor rails cannot be switched off separately from PWR_ON; gating them later needs one spare MCU pin. The XSHUTDOWN release question (OQ item 18, PL-09) stays open; the picks work with either answer.
- The oscillator must sit on 1V8_AUX with the sensor's I/O supply, never on 1V8_MAIN: the clock input may not exceed VDDIO + 0.3 V (checker).
- Raw cell node: only the latch FET's source, its pull-up, the gate-source capacitor and the charge pads, plus the RTC's backup pin through its 1 k resistor. LED anodes, the cell divider and all bulk capacitors go on the switched side.
- The surge figures assume at most 47 uF on the switched node; above that, raise the 22 nF capacitor. The fallback regulator adds two 10 uF when fitted, so total the node once the picks are final (checker).
- Hot storage: at the 70 C leakage limit the 47 k pull-up does not hold the latch off on paper. A scaled network (22 k, 4.7 k, 47 nF, 470 nF, 22 uF) is the answer if a guarantee is wanted.
- With the FDN306P alternate the start window must be judged at 1.8 V only: 169 ms at a 3.0 V cell, 133 ms with the capacitor 20% low (checker).
- One-sided decoupling departs from ST's guidance (AN5967 section 14.3) more than 0402 against 0201 does: give VDDCORE a solid plane next to ground, one via per VDDCORE and VSS ball, and group the 1 uF and 15 uF parts on the SMPS side.
- The Nucleo's 2.2 nH inductor ahead of the VDDSMPS capacitors is left out; link LK1 sits there. ST's other named SMPS coil, TDK TFM322512ALVA1R0MTAA, needs a larger 3.2 x 2.5 mm footprint (checker).
- PA8 sits at about 1.5 V whenever 1V8_AUX is off, while ADC inputs must stay within the ADC supply (pin table open point 11; checker).
- No link from the RTC's CLKOUT to PC14: with the RTC on 3V3_SW its clock output swings 3.3 V, and PC14 is a 1.8 V pin.
- Camera connector: it has no polarity mark and the plug mates face down, so rows as well as ends can be swapped. Copy the pad numbering from ST's adapter (J2) and confirm with the module in hand. Whether the plug's power contacts are ground rests on the CAM-5G0-079CLR schematic alone: check continuity on a CAM-6G3-073CLR before grounding the tabs (checker).
- Keep Hirose's recommended pad and stencil dimensions. The picker's suggestion to lengthen the pads and clear bridges with a fluxed tip goes against Hirose's instructions and is dropped (checker).
- SD socket: confirm the detect switch's polarity and pad on the Molex drawing, and decide which rail its pull-up uses. The LIS2DW12 land pattern is in ST TN0018, not stored.
- LED: 3.2 +/-0.1 mm non-plated hole through all layers; pin numbers are drawn from the lens side.
- A 0.08 mm stencil for the whole board, or a step-down at the camera receptacle, affects the paste for the BGA and the 0402 parts.

**Firmware**

- Before releasing HOLD: put the sensor in reset and idle the card, because every power-off is a slow brown-out of about 3 ms (checker). Pull PF1 low before any path that drops PWR_ON (checker). Disable the 3.3 V regulator before releasing the latch.
- Enter Standby straight after releasing HOLD. With the shutter still held the board stays powered up to about 0.85 s and a restart that reaches firmware would take another photo (checker).
- ST's power-off order wants the auxiliary group discharged first, with the main group falling only once it is below 0.6 V. Unordered power-down is accepted; entering Standby before releasing HOLD would give ST's order through the QOD pull-down. Not verified (checker).
- SD card: off time before re-enabling 3V3_SW of at least 5 ms, 10 ms to be safe; the card resets itself if its supply dips below 2.6 V (checker).
- The sensor clock must be running before XSHUTDOWN is raised (checker).
- RTC: write EEPROM C0h = 60h at first boot (see Design values); the RTC is on I2C1 (PH9, PC1) at 3.3 V; send a STOP or bus-clear before the first access and check the PORF and VLF flags; clear or ignore the EVF flag, which is set at every power-on with EVI held low (checker).
- Cell readings: wait 30 ms after power-up, and space the samples of a burst, because each takes about one step of charge from the 10 nF (checker).
- Without the crystal the timebase is the internal oscillator: +/-0.5% at 30 C and up to +/-5% over temperature, which affects the probe UART and the SD clock.
- LED: green looks about 6.5 times brighter than red and blue at equal current, so dim it by PWM or fit a larger resistor after seeing it. Use red for the low-battery warning.
- Low-battery level (tree open point 4): the 3.3 V rail leaves regulation below about a 3.40 to 3.44 V input but stays usable to about 2.8 V; the 2.8 V rail regulates to about 2.83 V and keeps the sensor in range to about 2.68 V, where the tree says 2.75 V.

**First-board bench checks**

- 1V8_MAIN and 1V8_AUX rise and fall against 20 to 1500 us/V, including the fall at power-down and the QOD discharge; decide then whether a bleed resistor is wanted.
- Voltage at the VDDA18CSI capacitor with the sensor streaming, against 1.746 V, and the dip when the sensor starts or the core load steps, against the +/-30 mV ST allows (checker). Ripple at the 1.8 V analog pins against 20 mV p-p.
- Current into VDDSMPS at start, against the switch's 2 A continuous and 2.5 A pulsed limits, and whether the 1V8_AUX ramp stays monotonic through the 1.2 V regulator's start pulse (checker).
- 3V3_SW rise against the SD card's 0.1 ms minimum, and its fall (checker).
- Cell-node dip at PWR_ON, when the 2.8 V regulator, the load switch and the internal SMPS start together (checker; add to tree open point 3). Overshoot on the 1.2 V rail when the sensor drops from streaming to standby.
- HOLD takeover time against the switched input at a 3.0 V cell; the window is about 170 ms. The switched node and the cell current at start; the held-shutter case (checker).
- UART serial boot without the crystal (checker).

**Assembly**

- Before power: meter OUT, IN and EN to ground on both XDFN4 regulators, and IN to OUT on the 1.2 V part before the camera module is plugged in; a bridge there puts 1.8 V on a sensor core limited to 1.4 V (checker).
- RTC: hot-air rework at 270 C only; the lid seal melts above 280 C. No ultrasonic cleaning. Thermal relief on pads joined to planes (checker).
- Camera receptacle: paste and hot plate; 250 C peak, two reflow cycles at most, board warpage 0.02 mm at the connector; no flux by hand. Rated for 10 mating cycles, and Hirose asks for something pressing on the mated pair (checker for the limits).
- LED on the hot plate: the lens faces the plate through the hole, so keep the plate clean under it. Moisture level 3 floor life applies to a batch built over several sessions. Blue is rated 250 V and green 450 V ESD (checker for the plate and floor life).
- The shutter switch is rated for 30,000 mechanical operations.

**Context**

- The pack's own protection circuit draws up to 5.5 uA, about 48 mAh a year or 23% of the cell. The RTC branch is about a thirtieth of that and does not set the shelf life (checker).
- Datasheets stored from the study on November 27: SI2333DDS, SI2312CDS, FDN306P, the SunLED LED, TPS7A02, the Samtec FTSH page, UM2448, the two Molex part pages and the two RV-3032 mirror copies. Four of the study's downloads were HTML error pages and were not stored (checker).
