# NUCLEO-N657X0-Q reference documents

Permanent vendor references for the **MB1940 N657X0Q C02** board used by this
project. Archived November 10, 2026. Files retain their original bytes and
vendor attribution. The schematic, BOM and manufacturing archive are the
October 18 copies used for the existing wiring and power reviews; the user
manual and external power-board manual were downloaded for this archive.

## Board documents

| Document | Revision / contents | Use |
| --- | --- | --- |
| [Full schematic pack](MB1940-N657X0Q-C02-schematic.pdf) | C02; 20 PDF pages, including assembly drawings | Circuit connectivity, regulators, solder bridges and connector pinouts |
| [User manual UM3417](UM3417-Nucleo-user-manual-Rev4.pdf) | Rev 4, September 2026; 46 pages | Power selection, jumpers, board operation and header tables |
| [BOM archive](MB1940-C02-bom.zip) | C02 spreadsheet and original ST notice | Exact component values and fitted/unfitted population |
| [Manufacturing archive](MB1940-C-manufacturing.zip) | MB1940C assembly, pick/place, Gerber, ODB++ and mechanical files | Component locations, PCB connectivity and layout checks |

The manufacturing files cover board revision C. **Use the C02 BOM to establish
which components are fitted**; pick/place and layout records can include
unfitted parts. These are stock-board references, not an as-built record of
our modified prototype. Current modifications and wiring belong in the
[assembly guide](../../../docs/prototype/nucleo-assembly-guide.md),
[power review](../../../docs/power/2026-10-14-power-tree-review.md) and
[hardware/firmware interface](../../../docs/hardware-firmware-interface.md).

## Schematic page finder

| Sheet / PDF page | Topic |
| --- | --- |
| 3 / 4 | MCU I/O / MCU power connections |
| 5 / 6 | Boot NOR / extension connectors |
| 7 / 8 | Ethernet / target USB |
| 9 | Power supplies and source selection |
| 10 | Arduino headers and analog-input conditioning |
| 11 / 12 | Camera / LEDs and other peripherals |
| 13 / 14 | ST-LINK / external debug interface |
| PDF pages 16-17 | Top/bottom assembly drawings |

The existing [assembly-only PDF and annotated location diagrams](../../../docs/prototype/nucleo-assembly/README.md)
remain available; the full original is now preserved here as well.

## Related references already in the repository

- [STM32N6 processor reference library](../../processor/README.md): datasheet,
  RM0486 reference manual, ES0620 errata, boot ROM and hardware/power guides.
- [DC1863A demonstration-board manual](../../power/ADI_DC1863A_demo_manual.pdf)
  and [LTC3621 datasheet](../../candidates/power-latch/ADI_LTC3621.pdf): the
  external buck converter used for the historical four-CR2032 option. It is
  **not an onboard Nucleo regulator** and is not the current LiPo latch path.
- [Prototype power decisions](../../../docs/power/NOTES.md) and
  [measurement boundaries](../../../docs/power/nucleo-debug-isolation.md).

## Sources and integrity

Each vendor file has an adjacent `.source.json` containing its official URL,
revision, byte count, SHA-256 and provenance. [manifest.json](manifest.json)
indexes this supplemental collection; the older root datasheet manifest
remains the historical September collection. Cached-file metadata does not
invent a precise download timestamp or redirect URL. PDF page counts/content
and ZIP integrity were checked before publication; copied files match their
source hashes.

Official sources: [ST board resources](https://www.st.com/en/evaluation-tools/nucleo-n657x0-q.html#cad-resources),
[schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf),
[user manual](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf),
[BOM](https://www.st.com/resource/en/bill_of_materials/mb1940-bom.zip),
[manufacturing files](https://www.st.com/resource/en/board_manufacturing_specification/mb1940-manufacturing.zip),
[DC1863A manual](https://www.analog.com/media/en/technical-documentation/user-guides/dc1863af.pdf).

ST's schematic and source archives retain their Open Platform License
Agreement notices and link to [ST OPLA](https://www.st.com/opla). The manuals
retain their publishers' copyright and terms; no project license replaces
the vendors' notices. This archive does not update firmware or qualify a
hardware modification.
