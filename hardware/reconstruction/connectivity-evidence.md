# Physical connectivity reconciliation

The unchanged native Flux export, fresh EDIF, original EDIF, and IPC-2581C export reconcile **726 of 729 terminals** without assigning undocumented optional-switch connections. Their paths and SHA-256 hashes are recorded in [connectivity.json](connectivity.json). Run [reconcile_flux_connectivity.py](../../tools/reconcile_flux_connectivity.py) to reproduce the file; the script exits unsuccessfully if reconciliation conflicts remain.

| Result | Count |
| --- | ---: |
| Components / physical terminals | 148 / 729 |
| Accepted connected terminals | 539 |
| Explicit native no-connects | 187 |
| Unresolved optional-switch terminals | 3 |
| Accepted named nets | 81 |
| Compiled EDIF connected terminals | 538 |
| IPC unique net-assigned host pad locations | 518 |
| Reconciliation conflicts | 0 |

The 539 accepted connections are the EDIF's 538 plus SW2 pin 1, which has a native UUID-specific canonical BOOT0 anchor. CAM1's 20 connected terminals are external to the host PCB, so the compiled host has 518 connected endpoints. All 518 host pad locations in IPC match the reconciled logical-name/net membership, and per-component/per-net counts agree exactly. U8's IPC names `pad1` through `pad8` map through native board-node `terminalId` fields rather than by assuming that their suffixes are pin numbers.

## Method and bounds

Native terminal UUIDs supply physical pin/ball numbers. Explicit native no-connect records are preserved. Fresh EDIF supplies logical-name groups and net memberships. Duplicate-name suffixes only identify members of the logical group; the script never treats an EDIF suffix as a physical pin number. Groups whose duplicate terminals all share a net can be mapped without an ordering assumption. Explicit native canonical anchors disambiguate additional pins, including LED1 pin 1 = STATUS_LED_K; the remaining EDIF group membership resolves LED1 pin 2 = STATUS_LED_A.

Every reconciled logical-name group has exactly the fresh EDIF's net membership. The original and fresh EDIF memberships agree outside J3. J3's unstable aliases are resolved independently by IPC copper coordinates, as described below. This verifies consistency of the exported circuit; it does not verify the manufacturer's pinout or the circuit's electrical suitability.

The native schematic route graph was examined by joining every `connectedVertices` edge and each terminal reference. It produces 544 terminal-bearing graph components and **none contains multiple terminals**. The native top-level nets are likewise single-pin fragments; generic `Net N` records are not accepted as electrical net names. Two such fragments also carry explicit no-connect markers: U1 PH9 / ball D8 and U8 CLKOUT / pin 1. They remain no-connects, consistent with their absence from compiled connections.

## J3 numbered connector map

IPC places unrotated, unmirrored J3 at (36.8, -36.990002) mm. The numbered embedded footprint maps to IPC by `x_ipc = x_component + x_pad` and `y_ipc = y_component - y_pad`. Each of the 20 net-assigned connector pad locations matches exactly one numbered logical pad within 0.00002 mm, far below the 0.35 mm pitch. Native canonical anchors agree. The JSON includes each coordinate match as evidence.

| Physical pins | Recovered net / state |
| --- | --- |
| 1 | CAM_VANA_2V8 |
| 2, 3, 8, 14, 20, 23, 26, 29, 30 | GND |
| 4 | CAM_VCORE_1V2 |
| 5 | 1V8 |
| 6 | CAM_XSHUTDOWN |
| 10 / 12 | CAM_CSI_D0_P / CAM_CSI_D0_N |
| 16 / 18 | CAM_CSI_CLK_P / CAM_CSI_CLK_N |
| 25 / 27 | I2C4_SCL / I2C4_SDA |
| 28 | CAM_MCLK |
| 7, 9, 11, 13, 15, 17, 19, 21, 22, 24 | Explicit no-connect |

Pads 31–34 in the footprint are mounting copper, not additional logical connector terminals, and are outside the 729-terminal electrical map.

## Optional switches

SW2/SW3 are native DNP components excluded from the BOM and absent from both compiled EDIF and IPC component exports. Only SW2 pin 1 has direct recovered net evidence, BOOT0. The following are stored as candidates with `net=null`, `status=unresolved`; they are deliberately excluded from the accepted net list:

| Endpoint | Candidate | Evidence and qualification |
| --- | --- | --- |
| SW2.2 | 1V8 | Stored role says optional BOOT0-to-1V8 SPST; the other pin has canonical BOOT0 evidence. |
| SW3.1 | NRST | Stored role says optional NRST-to-GND SPST; assigning NRST to pin 1 is a reconstruction choice for a symmetric switch. |
| SW3.2 | GND | Same stored role; assigning GND to pin 2 is a reconstruction choice for a symmetric switch. |

A schematic generator may use these candidates only as explicit documented reconstruction assumptions. They must not be represented as source-verified recovered connectivity.
