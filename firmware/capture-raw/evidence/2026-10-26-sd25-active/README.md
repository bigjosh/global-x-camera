# Active four-bit 25 MHz cold-flash firmware

**Passed and installed.** The reviewed startup/no-tail profile now runs four-bit SD at 25 MHz, with falling-edge launch during identification and transfer, GPIO speed3 and unchanged compensation. The final installed image captures to GXR2 packed RAW slots and then enters Standby. Earlier-clock-transition, tail-wait, receive-IDMA, DMA-WFI, tracing and electrical experiments remain disabled.

This promotion follows the [twenty-image RAM campaign](../2026-10-26-sd25-twenty/README.md) and [illuminated-scene addendum](../2026-10-26-sd25-lit-scene/README.md). Those frozen records remain unchanged.

| Qualification | Observed result |
| --- | --- |
| Awake NOR installation | All 65,536 bytes match; following 4,096 bytes unchanged |
| Awake cold capture, slot 47 | All 1,909,600 SD pixel bytes equal original camera RAM; independent PNG decoding passed |
| Final Standby NOR installation | All 65,536 bytes match; following 4,096 bytes unchanged |
| Standby cold capture, slot 48 | Complete 3,730-sector readback at 25 MHz; GXR2/GXRE and PNG samples passed |
| New-slot attribution | The Standby slot header was read and confirmed FREE before the cold capture |
| Post-save current signature | 8.177 mA at 4.892 V on the JS-fed board branch |
| Warm UART recovery | Exact final prefix/early park; retained pulse proof passed |
| Guarded power flag read | SBF=1, PDDS=1, STOPF=0; trial_entry_proven:false retained |

Both readbacks have eight guarded operations with zero retained card/command/data/cleanup errors. The awake cold write and source-RAM comparison qualify the installed transport path before the separately tested Standby build. Standby loses original camera RAM; its pixel source equality is therefore not claimed.

One host-only readback preflight was rejected because its SCR source pointed to a READ record rather than the required CAPTURE record. The output folder had not been created and no hardware operation occurred. The corrected invocation used the original awake capture/SCR proof; no guard, reset or SD retry was involved. Both logs and the correction record are preserved.

## Exact final identities

- Receiver SHA-256: `4dbe72895705a30b3c699500d90517e2424676d732c18eb944971560901e6512`
- 64 KiB NOR sector SHA-256: `c68593cebeddf5b9c24f85249505ae719dd1ea73d11f309e3a8553e9c1a9fa47`
- Recovery-prefix SHA-256: `0592a543cb1e75b176e97f715f139a0a13d8a4d791ba44efd0ec94dc4f5b6754`

The early load remains 15,804 bytes. Independent prefix review found only the two expected CRC data words changed, with all recovery instructions/literals retained. Build manifests retain their original `hardware_status: untested` creation-time field; this evidence supplies the later measured qualification.

## Final bench state

After the complete slot48 qualification, a separate final normal cold boot left the target powered on the installed 25 MHz Standby image's low-current plateau: 8.178 mA. Expected next slot49 and SBF were not reread after this final boot. This final observation is a power signature only; it is not counted as another verified image.

The exact final state and preserved instrument settings are in [final-state.json](inputs/final-state.json). Do not infer live bench state from this historical report; use the latest repository checkpoint before hardware work.

## Limits

- The 25 MHz link was qualified on the reported card/wiring with the LP8 probes removed and the 27-ohm CLK resistor retained. No analog eye/timing margins or formal SD certification are established.
- The awake cold capture is compared against its original camera RAM. Standby discards that RAM; its image is checked for complete markers, same-speed read integrity and independent PNG decoding only.
- SBF/PDDS are observed after warm UART recovery without an intervening power-off. The guarded reader retains trial_entry_proven:false; it does not independently attribute the flag to this specific entry.
- Cold-start evidence is a measured JS110-off interval of at least 15 seconds and near-zero current; target rails were not probed. Completion current is a signature, not by itself an idle or Standby proof.
- No new cycle-energy or power-on timing comparison is made. Current statistics are not an integrated energy measurement.
- GXR2/GXRE markers do not checksum pixels or establish arbitrary power-loss atomicity. Existing CRC, ownership, recovery and cleanup gates remain enabled.

## Offline replay

The public bundle contains exact firmware, source/manifest hashes, cold-power events, both NOR installation proofs, operation records, recovery and final-state records. Photos, SD-sector payloads and original camera RAM remain private; hashes bind those locally compared bytes. The pinned prior verifier supplies the reviewed same-speed RAM READ checks. The archive verifier has no hardware access; copied bench scripts are historical sources and are not part of offline verification.

```text
python -B archive.py inspect --source <private promotion folder> --out <report.json>
python -B archive.py freeze --source <private promotion folder> --out <new evidence folder>
python -B archive.py verify --out <frozen evidence folder>
```

Full pixel replay requires private source data and the frozen `ram25-scene` helper from the prior campaign. `verify` checks every public file hash and refuses missing, changed or extra files. `freeze` requires all expected independent checks and the final-state record.

Build both candidates from the repository with the same existing capture receiver/prefix bases used in the manifests:

```text
python -B firmware/capture-raw/build.py --out tmp/bringup/rebuild-active25-awake --base tmp/bringup/sd-normal-20261024/v66c-normal-standby --flash --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt --magic-format --line-stream --async-stop --transport idma
python -B firmware/capture-raw/build.py --out tmp/bringup/rebuild-active25-standby --base tmp/bringup/sd-normal-20261024/v66c-normal-standby --flash --standby --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt --magic-format --line-stream --async-stop --transport idma
```

These commands require the existing frozen base and STM32 toolchain/vendor sources. Their identities, every generated source hash and exact compiler flags are retained in the manifests; a build alone does not authorize hardware installation.
