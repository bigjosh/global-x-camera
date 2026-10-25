# Four-bit SD bring-up: initial CMD8 blocker

This is the **provisional October 24 local / October 25 UTC initial finding** after the user installed the new full-pin PZSSD001 breakout. Neither four-bit operation nor new image saves or capture-cycle time/energy measurements succeeded in this pass. A later successful experiment should supersede this checkpoint while retaining these failure records.

The user requested four-bit operation, image verification and the same three-cycle comparison. Existing authorization includes exclusive experimental-board use, permission to overwrite memory/flash/SD as needed, and the explicit reply **“Yes—reset and erase this test card.”** The recorded [recovery authorization](recovery-authorization.json) preserves the root bench owner's scope. No additional approval was inferred from a failed storage record.

## Observed failure

A RAM helper requesting four-bit operation and the previously qualified frozen one-bit RAM helper both failed during **CMD8 identification at 100 kHz**. Each attempted a READ of one sector at LBA 0, but initialization stopped before any data read.

| Observation | New four-bit RAM build | Frozen one-bit control |
|---|---:|---:|
| Commands reached | CMD0, CMD8 | CMD0, CMD8 |
| CMD8 argument | `0x1AA` | `0x1AA` |
| SD error | 8: command CRC error | 8: command CRC error |
| Error/last status | `0x00000001` | `0x00000001` |
| Received response register | `0x000007C5` | `0x000007C5` |
| Read sectors / written sectors | 0 / 0 | 0 / 0 |
| Data transfer words | 0 | 0 |

The response field is named `last_r1` in the generic driver record; for CMD8 it contains the sampled R7 response register. Because its CRC failed, `0x7C5` is not treated as a valid response. The expected CMD8 echo is `0x1AA`.

This failure precedes SCR inspection, ACMD6 bus-width negotiation and any four-bit data transfer. Identical failure with the frozen one-bit helper argues against a problem limited to the new four-bit data path. Wiring, connector orientation/contact, power or signal integrity remain hypotheses; this evidence does not identify a specific bad wire or prove a particular electrical cause. The four-bit helper's extra pin configuration and the changed carrier are still experimental differences.

Both terminal records retain `media_idle=0` and `controller_owned=1`. They are **failed initialization records, not successful idle/maintenance permission**. Root used the existing explicit reset/clobber authorization for controlled recovery and final power-off; no failed status was relabeled as success.

## Exact identities and scope

| Artifact | SHA-256 |
|---|---|
| Requested four-bit scene RAM v19b | `9a541fbe00de3a2c3d92b5fbe48aafe7f3ed4b770aedc3da1275a0c2ca662a52` |
| Frozen one-bit RAM v18 control | `1b96bf02555a33035a6ca4b4fd641409d9e2129274f9dfbf326ae1aa26d51b2f` |
| Installed v18 flash sector, unchanged by this task | `174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e` |
| Installed v18 recovery prefix | `9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba` |

The one-bit build carries its historical pattern-selection flag, but these were READ requests and no camera capture ran. The new v19b flash image was built offline and **was not programmed**. No NOR program/erase or SD data-write/erase command was issued in these tests. No fresh full NOR-sector verification or successful card identity/preservation readback is claimed.

The [cold recovery result](v18-cold-recovery.json) verifies the existing v18 prefix, exact early park and nine good PE6 pulses with zero bad pulses. It establishes recovery access for this attempt, not general all-state reliability or successful SD access. Its generic `next_step` text is a tool suggestion, not a record of NOR programming.

## Powered-off handoff

At **2026-10-25 03:24:06.677635 UTC**, the JS110 input measured approximately **4.894 V**, with output range deliberately set to **0/OFF** and measured load current **0 A**. A separate passive observation of Saleae CH4 on target 5 V / CN3 pin 18 measured mean **3.306 mV**, maximum **9.006 mV**. This establishes that observed target 5 V point was near zero; it does not prove every board rail or signal was zero.

The root bench owner left the target off for the user's physical wiring check. Restore power only after that check; do not use older powered/Standby checkpoints as the present state. See [power-off record](power-off-for-wiring.json) and [target-5V observation](target-5v-off-observation.json).

## Compact evidence

- [Four-bit attempted READ plan](four-bit-read-plan.json) and [failed diagnostics](four-bit-diagnostic.json).
- [Frozen one-bit control plan](one-bit-control-read-plan.json) and [failed diagnostics](one-bit-control-diagnostic.json).
- [Machine-readable summary](summary.json) and [source/copy hashes](manifest.json).

Only parsed control/error records and compact power observations are included. Absolute local build paths were converted to repository-relative paths; original source hashes remain in the manifest. No private images, sector payloads, raw SRAM dumps, native power arrays or Saleae capture files are published.

The [previous one-bit SanDisk baseline](../2026-10-24-sandisk-extreme32/README.md) remains the comparison reference: **882.627 ms / 450.788 mJ median** across three qualified cycles. There is no new four-bit result to compare yet.
