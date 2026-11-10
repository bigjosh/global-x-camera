# SD DMA sleep implementation — hardware qualification pending

The user requested CPU sleep during DMA writes on the current SD hardware.
The opt-in implementation is complete and tested offline. **It has not been
run on the target or installed in NOR. No new image, timing or energy result
is claimed.**

## Implemented behavior

- Preserve the current single-frame, Ethernet-down, four-bit 25 MHz capture
  profile, front-metadata RAW slots, one preannounced CMD25 and final-ready checks.
- When a complete validated frame and stopped sensor are already available,
  keep SDMMC/DMA and its memory/security/interconnect clocks running while the
  CPU uses shallow WFI. Existing 1 ms SysTick supplies wake-up and wall timing.
- Preserve awake streaming when capture is incomplete. Do not delay the first
  write to force a DMA path. The original polling build remains reproducible.
- Retain wait/clock telemetry, bounded timeout/error handling and the exact
  early UART recovery guard. BSEC run/sleep-clock checks are new; this is not
  proof that missing BSEC was the cause of the old failed sleep experiment.
- Provide a RAM-only no-write probe using the actual capture runtime's timer
  and vectors: three awake ticks, 20 ms WFI, then intentional failed-photo
  terminal before CMD25. The dedicated host reader never labels this a saved
  image or an idle authorization.

## Offline validation

The final source-bound capture suite passed **281 tests**, with no source
changes during the run; see [report](offline-tests.json) and [log](offline-tests.log).
The storage agent separately ran **38 storage tests** successfully, covering
the actual driver register model, complete 3,730-sector payload, one-CMD25
sequencing, PIO fallback, errors, timeouts, wrap, and completion-before-WFI.
Real CMSIS ARM compilation and omitted/disabled feature-section equality also
passed; see [record](storage-tests.json).

The first full capture run caught two host/build compatibility regressions:
an admission predicate threw instead of returning false, and a new guard
changed the existing diagnostic's error-message precedence. Both were fixed;
the failed report/log are retained alongside the successful rerun.

The independent [packaged-image audit](standby-audit.json) verifies the original
15,804-byte early load, early interrupt vectors, all twenty recovery literals,
and the unchanged relocated 1,536-byte error engine. Direct review against the
installed single-frame prefix found only the two approved CRC words changed.
New state records are outside the frame, read buffer, stack and error engine.
The final [RAM admission checks](ram-admission.json) and no-execution probe plan
also passed.

| Build | Receiver SHA-256 | Status |
|---|---|---|
| Existing polling baseline | `560a8734306436fe95bc1407031e70f1bc5b448949366e1bd007779c1736f646` | Reproduced exactly, including prefix and 64 KiB sector |
| Sleep Standby candidate | `05835210616c3453a2703472b2db81e7ed291f4dda831db85e39afa6e8c9319d` | Compiled/audited; not programmed |
| Sleep RAM candidate | `bf1aef90a861f133809ef169c7d64d229a35da32acd41318a1f26c8664294247` | Compiled/admitted; not executed |
| Idle-card WFI probe | `98774723e4a027073fe3c4e4531919a9b8cfb6c2c60f23c7b542e68843caee75` | Compiled/admitted; not executed |

Candidate Standby prefix is
`296ebf716138c08be27c76ccc2831835e3f65273339cac1b84c4d9f49e3e6d4f`;
sector is `3c26603fc7405d3d57ad30075d3d8bb45ac8621291efeb5f2275db14c3defa41`.
The candidate adds 460 receiver bytes in the late load. Earlier compile
failures were resolved by putting the address-taken millisecond callback in
late storage code, preserving the fixed early boundary. Generated build
folders remain in `tmp/bringup/sd-dma-sleep-20261030/`; manifests and hashes are
retained here, rather than claiming these are hardware-qualified releases.

## Hardware boundary and next work

Stats-only JS110 reads at 17:40 and 17:59 UTC on October 30 measured approximately
0 V input and zero load current. Windows detected JS110/LP8 but not ST-LINK/COM8.
Measurement settings were restored unchanged; there were **no target memory
writes, NOR/SD operations, resets or power toggles**. See
[preflight](preflight-final.json) and [handoff](final-state.json).

The pending user action is to restore direct bench 5 V through JS110 to CN5.5,
return CN5.6, and connect CN10 ST-LINK USB, retaining the camera/SD and CN15
markers. The last verified installed image remains the October 28 single-frame
build; it was not reread on October 30, and its current PC is unknown.

After the connection is restored: establish fresh exact recovery, qualify the
finite no-write WFI probe, then complete RAM image writes/full original-frame
readback, UART recovery and matched external cycle measurements before NOR
promotion. The [root-only workflow](WORKFLOW.md) and offline JS analysis helper
are prepared. Both control/candidate use eleven single-frame markers. DWT
spans can exclude sleep, so use SysTick/JS for elapsed time; WFI call counts
alone do not establish actual clock gating or energy savings.
