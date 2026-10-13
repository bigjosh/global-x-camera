# Power and discrete documentation coverage

Downloaded 2026-09-05. The unchanged PDFs and adjacent `.source.json` records preserve source URLs, retrieval time, page count, and SHA-256 hash.

All 11 distinct requested power/discrete BOM MPNs have documentation. The two TLV700 voltage options share one family datasheet. Power datasheets include package drawings; the two buck converters also have TI evaluation-module guides with reference circuits and PCB layout examples.

| BOM part / references | Manufacturer and document selection |
| --- | --- |
| TPS62132RGTR / U2 | Texas Instruments TPS6213x datasheet; RGT package. EVM guide is for the related adjustable TPS62130 family, so its circuit is a layout reference rather than an exact BOM implementation. |
| TPS62825DMQR / U7 | Texas Instruments TPS6282x datasheet; DMQ package. TPS6282xEVM-794 includes the adjustable TPS62825 configured for 1.8 V. |
| TLV70033DDCT / U4; TLV70028DDCR / U9 | Shared Texas Instruments TLV700 family datasheet; both DDC orderable variants. |
| NCP115AMX120TCG / U10 | onsemi NCP115 datasheet. The BOM manufacturer field is blank; the MPN and XDFN4 package identify onsemi. Downloaded from the official onsemi China host because the global host returned HTTP 403. |
| TPS22918DBVT / U12 | Texas Instruments TPS22918 datasheet; DBV package. |
| AO3401A / Q1, Q3 | HUASHUO, as specified by the BOM. The HUASHUO-branded version 2.0 datasheet is hosted by LCSC; this is a distributor-hosted manufacturer copy. Do not substitute Alpha and Omega Semiconductor documentation solely because the base MPN is the same. |
| BSS138 / Q2 | onsemi, as specified by the BOM. Official onsemi China-hosted English datasheet, April 2024 revision 7; the global host returned HTTP 403. |
| USBLC6-2SC6 / D1 | UMW, as specified by the BOM. Official UMW November 2024 document. Do not treat STMicroelectronics' similarly named device as the selected manufacturer. |
| SS34 / D2 | UMW, LCSC stock code C2758511. See the order-code caveat below. |
| 1N4148W-13-F / D3 | Diodes Incorporated datasheet, including the exact -13-F ordering option and SOD123 drawing. |

## SS34 order-code caveat

The BOM names D2 `SS34`, manufacturer UMW, stock code `C2758511`, and an SMB footprint. The [exact LCSC stock-code document](UMW_SS34_C2758511_datasheet_LCSC_copy.pdf) is UMW's `SS32B THRU SS320B` family. Its ordering table on PDF page 5 specifies **SS34B as the SMB order code**, with **SS34 as the top marking**. The [official UMW family PDF](UMW_SS32B_SS320B_SS34B_datasheet.pdf) gives the same package and ordering information. Both copies are retained to preserve the distributor-to-manufacturer mapping.

Resolve the SS34/SS34B purchase-code suffix before ordering. This is a naming ambiguity, not evidence that the BOM's SMB footprint is wrong. The separate plain-SS34 UMW family document describes SMA and must not be used to define this SMB footprint.

## Scope

These files establish documentation coverage and package references. They do not constitute an electrical design review or certification that netlist pin mapping and footprint geometry are correct.

## EDIF reconstruction inputs

The power/discrete cells have logical port names, but the EDIF has no physical pin-number properties or `portImplementation` records. Most names can be mapped using the archived package pin tables. Repeated SW/PVIN/PGND ports of U2, paired I/O ports of D1, and GND/GND_2 of U10 each share their respective net, so permutations within those duplicate groups do not alter the existing electrical connectivity.

D3 is different: its EDIF ports are only `1` and `2` (raw identifiers `&1` and `&2`), with no anode/cathode labels. `&1` connects to `SHUTTER_SENSE` and `&2` to `LATCH_PULLDOWN`. The EDIF alone does not establish which logical port is the cathode. Reconstruct this mapping explicitly and check it against the source library convention or documented circuit intent before assigning a physical diode footprint.

Conversion code must also preserve EDIF identifier/display-name pairs: for example, the cell displays `SS/TR` and `I/O1`, while net references use `SS_TR` and `I_O1`. Joining only by display label would lose valid connections.
