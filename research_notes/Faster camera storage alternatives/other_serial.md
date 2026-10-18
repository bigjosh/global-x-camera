# Other serial NAND replacements: GigaDevice, Winbond, Kioxia and Alliance

Research date: 2026-10-18. Read-only research; no hardware access or vendor contact. Manufacturer datasheets determine technical properties; distributor stock is a point-in-time indication, not a reservation.

## Which current serial parts improve capacity and programming speed?

### Takeaway

GigaDevice GD5F8GM8UEYIG is the most promising current 8 Gbit, native 3.3 V candidate in this subset: 4 KiB pages and 340 us typical ECC-enabled programming. Its practical procurement remains unverified. The similarly fast 4 Gbit GD5F4GM7UEYIG also lacks verified distributor stock.

### Cited Findings

- GD5F8GM8UEYIG: manufacturer status MP, 2.7–3.6 V, 8 Gbit, industrial -40 to +85 C, x1/x2/x4, 133 MHz, WSON8 8x6 mm. The product webpage lists 2 KB, conflicting with the linked current datasheet. — [Product page](https://www.gigadevice.com/product/flash/spi-nand-flash/gd5f8gm8ueyig)
- The September 2025 GD5F8GM8 Rev1.0 datasheet pp4/72 instead specifies **4096-byte data pages**, plus 128 user spare bytes with internal ECC enabled / 256 physical spare with ECC disabled; ECC is 8 bits per 528 bytes. ECC-enabled tPROG is **340 us typical, 600 us maximum**; without ECC 300/600 us. ECC-enabled read is 70 us typical / 180 us maximum. It advertises 10-year retention and typical 80k P/E cycles with ECC, reduced to60k at105 C. The 3.3 V variant is 2.7–3.6 V; 1.8 V is a different ordering variant, not one flexible-voltage device. — [GD5F8GM8 datasheet](https://download.gigadevice.com/Datasheet/DS-01328-GD5F8GM8UE-Rev1.0.pdf)
- GD5F4GM7UEYIG is also manufacturer MP, 4 Gbit, 2.7–3.6 V, 133 MHz quad, WSON8 8x6 mm. Its product webpage also conflicts with the datasheet on page size. — [Product page](https://www.gigadevice.com/product/flash/spi-nand-flash/gd5f4gm7ueyig)
- GD5F4GM7 Rev1.0 September 2025 pp4/74: 4096-byte pages, internal8-bit ECC, ECC-enabled340/600 us program, 70/180 us read, 10-year retention and typical80k ECC P/E cycles. — [GD5F4GM7 datasheet](https://download.gigadevice.com/Datasheet/DS-01326-GD5F4GM7UE-Rev1.0.pdf)
- Current Alliance AS5F38G04SNDC-08LIN is 8 Gbit, native3.3 V (3.0–3.6 V), quad120 MHz, 4 KiB+256-byte pages, 8-bit ECC, LGA8 8x6x0.8 mm, and tPROG750 us typical/850 us maximum. It advertises60k+ P/E cycles and10-year retention. The4 Gbit RevC has the same4 KiB page/timing. — [RevC datasheet pp7/46](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_3V3_AS5F_QSPI_NAND_Flash_1Gb-2Gb-4Gb-8Gb_C-die_Ver1.0_Feb2026.pdf)

### Inferences

- For current1,909,600-byte packed frame, 4674-KiB pages: GigaDevice internal programming totals158.78 ms. At assumed50 MHz, transfer+program is approximately **235 ms quad** or **464 ms single-bit**, before commands/metadata/erase/readback. This is arithmetic, not measured hardware performance.
- Alliance RevC sameframe internal programming350.25 ms; estimated427 ms quad50 MHz /656 ms single50 MHz. Its largerpages improve over existingAlliance2 KiB600 us despite slowerperpage figure.
- 8 Gbit nominal1 GiB comfortably exceeds200×1,916,420 bytes before reasonable overhead; exactcapacity depends block-slot layout, factorybadblocks/reserves.4 Gbit512 MiB also nominallyfits.

### Gaps

- No verified DigiKey/Mouser listing or small-quantity stock found for either new GigaDevice exactpart. Thus neither prototypeavailability nor500unitsnow can be claimed. The manufacturer's Buy Now may require direct distributor inquiry; no contact was made.
- GigaDevice product-page/datasheet page-size conflict needs explicit confirmation before finalpartselection; calculations use linked datasheet.
- Advertised10-yearretention and80k/60k endurance do not themselves fully qualify the requested10years after1000 complete reusecycles atroomtemperature; exactretentionconditions need confirmation.

## Do these parts actually support loading the next page while programming?

### Takeaway

No verified write pipeline in the inspected serial candidates. GigaDevice explicitly rules it out in its documented sequence; “cache” in read descriptions or a pagebuffer is not evidence of cache programming.

### Cited Findings

- GigaDevice8 Gbit §9.4 p45 says next Program Load follows successful completion of current Program Execute. Parameterbyte114 p30 is00h, clearing the bit defined as program-cache support. — [GD5F8GM8 datasheet](https://download.gigadevice.com/Datasheet/DS-01328-GD5F8GM8UE-Rev1.0.pdf)
- The4 Gbit variant has the same sequence and parameterbyte114=00h. — [GD5F4GM7 datasheet pp30/45](https://download.gigadevice.com/Datasheet/DS-01326-GD5F4GM7UE-Rev1.0.pdf)
- AllianceRevC parameterpage programs-cache timing support bytes131–132=0000h. The reset chapter has generic “cache program” wording but no supported corresponding command/sequence was found; do not count that wording as capability. — [AllianceRevC datasheet pp35/37](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_3V3_AS5F_QSPI_NAND_Flash_1Gb-2Gb-4Gb-8Gb_C-die_Ver1.0_Feb2026.pdf)
- Kioxia8 Gbit sequence is Write Enable→Program Load→Program Execute→Get Feature tocheckbusy; this is not a documentedcachepipeline. — [TH58CVG3S0HRAIJ datasheet §4.4](https://www.kioxia.com/content/dam/kioxia/newidr/productinfo/datasheet/201910/DST_TH58CVG3S0HRAIJ-TDE_EN_36004.pdf)

### Inferences

- Largerpages plus fasterinternalprogramming may be the more useful/simple serial upgrade, even without cacheprogramming.

### Gaps

- No supported test was run for undocumented commands and none should be relied on for design.

## Which attractive parts have sourcing or lifecycle problems?

### Takeaway

Several superficially appealing choices fail current lifecycle/availability checks. Do not recommend a stockedpart solely from distributor “Active” if the manufacturer says NRND/EOL.

### Cited Findings

- Winbond W25N04KVZEIR is3.3 V4 Gbit quad104 MHz with250 us listedprogram time. DigiKey showed **4,002 in stock**, constrainedsupply/no backorders on today's page. — [DigiKey](https://www.digikey.com/en/products/detail/winbond-electronics/W25N04KVZEIR/15182086)
- Current manufacturer W25N04KVZEIRG page states IndustrialStatus **N = Not Recommended for New Design**. Gsuffix changes renewablemanufacturingenergy, not electricalspecs. Therefore do notpromoteKVasnewproductionchoice absent replacement/lifecycleclarification. — [Winbond](https://winbond.com/hq/product/code-storage-flash/qspi-nand/w25n-kv/?__locale=en&partNo=W25N04KVZEIRG)
- Kioxia TH58CVG3S0HRAIJ:8 Gbit3.3 V, quad133 MHz,4 KiBpages, on-chip8-bitECC, WSON8. — [Kioxia productbrief](https://www.kioxia.com/content/dam/kioxia/shared/business/memory/slc-nand/asset/productbrief/KIOXIA_Serial_Interface_NAND_Product_Brief.pdf)
- Mouser lists TH58CVG3S0HRAIJ **End of Life**, manufacturerdiscontinuationnotice2025-10-24, unavailableinregion; not a goodnewdesigncandidate. Its listed300 usspeedis not used as a fullyverifiedprogramtiming in thisnote. — [Mouser](https://www.mouser.com/ProductDetail/Kioxia-America/TH58CVG3S0HRAIJ?qs=OlC7AqGiEDmkinos%252BEmSPw%3D%3D)
- Alliance AS5F38G04SNDC-08LIN DigiKey Active but **not stocked**,20weekleadtime,MOQ352; Mouseralso nonstock20weeks,min/multiple352. Neither500now norprototypeimmediateavailability demonstrated. — [DigiKey](https://www.digikey.ca/en/products/detail/alliance-memory-inc/AS5F38G04SNDC-08LIN/29926107), [Mouser](https://eu.mouser.com/en/ProductDetail/Alliance-Memory/AS5F38G04SNDC-08LIN?qs=Omd18uQ5iJHK1lOPVeshjw%3D%3D)
- Earlier Alliance8 Gbit AS5F38G04SNDA-08LIN has2 KiBpages,610 us typicalprogram, notspeedimprovement; DigiKey shows0stock andDiscontinuedatDigiKey. — [Manufacturerdatasheet](https://www.alliancememory.com/wp-content/uploads/ALLIANCE-SPI-NAND-Flash-AS5F38G04SNDA-08LIN_Rev-1.0_20250728.pdf), [DigiKey](https://www.digikey.com/en/products/detail/alliance-memory-inc/AS5F38G04SNDA-08LIN/28167225)

### Inferences

- A separatelyverified in-stockMicron8 Gbit orMacronix4 Gbit candidate from theotherresearch is strongerforimmediateprototype than these newGigaDevice orAllianceRevCparts.

### Gaps

- Winbondfull250 usmax/PVTqualificationnotcompleted becausecurrentNRNDmakesitlowerpriority. Do nottreat250 us as maximum.
- Kioxiapackageheight andretentionqualificationnotpursuedafterEOLfinding.
