# One-wire phase timing diagnostic

This is an isolated instrumented overlay. Frozen v50/v59 inputs retain their
historical behavior; newer inputs carry an explicit normal or diagnostic
profile and require reviewed input hashes. It uses **PD12, CN15 pin 21**, also Arduino D8/CN14 pin 1. The pin is
idle LOW and produces one HIGH pulse per event. Nominal pulse width is the event
number multiplied by 0.5 µs at the existing 400 MHz CPU clock. No prefix marker is
added: first-stage startup and UART recovery remain untouched.

| Event | Observation |
| --- | --- |
| 1 | Receiver main entry, after first-stage sensor START |
| 2 | First sensor STROBE rising interrupt observed |
| 3 | First complete-frame interrupt observed |
| 4 | SAVE module entered |
| 5 | SD initialization succeeded |
| 6 | FAT32 mount succeeded |
| 7 | PNG encoding completed; final output buffer may still need flushing |
| 8 | File finish completed, including close/rename and card-ready checks |
| 9 | SD deinit, cache cleanup, final cheap frame checks and snapshots completed; diagnostic profiles also completed their RAW hashes/stack scan; terminal publication follows |
| 10 | Immediately before Standby WFI, or awake diagnostic completion park |

Event 2 includes interrupt latency and is not an electrical measurement of the
sensor's exposure edge. Event 10 proves software intent only; power and SBF
evidence still qualify physical Standby. The full cold cycle emits 1–10; a
guarded repeated SAVE on a retained frame emits 4–9. READ operations emit no
storage markers.

For the historical v60/v61 schema-1 overlays, event 9 includes the final
uncached full-RAW checksum. New schema-2 normal builds skip that checksum and
the other expensive diagnostics; event 9 still follows the retained metadata,
canary, storage and cache checks. A pulse is not evidence that an optional
check ran: use the report schema, profile and performed-check flags.

The combined nominal HIGH time for events 1–10 is 27.5 µs. Calls, GPIO accesses, cache
state and interrupts add overhead; **less than 100 µs total overhead is a design
aim, not a measured result**. The additional receiver bytes also increase its
NOR load time. Requalify the first-frame deadline and received image on hardware.
The existing 1,800,000-cycle receiver guards are unchanged.

The pulse loop uses the already-running DWT counter and has a 4,096-iteration
limit. It never changes CYCCNT or clock configuration. It preserves PRIMASK and
only changes PD12's mode, speed, pull, output type and output state. Initialization
refuses a disabled timer/debug trace or reset/gated GPIO bank. A later disabled
or stalled timer results in a missing or malformed pulse, which the decoder
must reject; it cannot create an infinite firmware wait. GPIO HIGH is committed
before the sampled start time, so measured widths include a small extra bus and
barrier interval that needs qualification.

## Offline builds

Use the bundled Python runtime. Neither command below accesses hardware:

```powershell
python firmware/capture-sd/phase_markers/build.py --mode awake --base tmp/bringup/capture-sd-v50-build-20261020 --module tmp/bringup/save-module-v8b-fast-loop-cache-20261020 --out NEW_AWAKE_DIRECTORY
python firmware/capture-sd/phase_markers/build.py --mode standby --base tmp/bringup/capture-sleep-20261020/v59-standby --module tmp/bringup/save-module-v8b-fast-loop-cache-20261020 --out NEW_STANDBY_DIRECTORY
```

The awake build uses the v50 architecture with no LPL/LPM ownership claim, so
existing strict maintenance and repeated-frame SAVE guards remain applicable.
The Standby build retains v59's late completion module and ownership guards.
The builder copies exact frozen sources and adds markers only to its outputs;
the original v50/v59 artifacts remain intact. For schema-2 inputs, first build
the receiver and SAVE module with matching `--diagnostics-profile normal`
(default) or `diagnostic`. Supply their reviewed sector and module hashes to
the overlay using `--expected-base-sha256` and `--expected-module-sha256`.
Those hashes identify inputs; they do not authorize programming or qualify
the new image on hardware.

Both outputs keep all early recovery bytes through the complete first variable
instruction and all referenced recovery literals identical to the baseline.
The receiver length/CRC constants change normally. The compiler can otherwise
change later prefix layout when a receiver length becomes an immediate special
case, so explicit diagnostic padding preserves that identity check. In the
October 23 candidates, awake is 15,560 bytes (the original v59 receiver length)
and Standby 15,796 bytes; newer exact sizes belong to their own manifests. The only
initialized data remains the final SystemCoreClock word. No identity guard is
relaxed. Newly compiled prefix hashes still need explicit reviewed recovery
allowlist registration before use.

Historical candidates from October 23:

| Build | Sector SHA-256 |
| --- | --- |
| `tmp/bringup/sd-phase-20261023/v60c-awake` | `20444827100b1a33826c5b7e3362a396a0ce31f27f0c3db7fea12fb755320f7e` |
| `tmp/bringup/sd-phase-20261023/v61b-standby` | `cc49159990ecd7aab9b0ab9c9055b3c230cc2ef639b1c295c511bea4a8be943f` |

Both contain the 27,576-byte instrumented storage module
`51c067de2859588fc87cf1249fdff4186b17a4e0ab85585c72fc9b5dc94379f5`.
The original restore image remains v59 sector
`7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63`.
Build manifests describe software candidates as untested; later hardware
qualification must be recorded separately.

## Capture and verification

[capture.py](capture.py) uses the existing Logic 2 API and saves/exports the
phase and power observations. [decode.py](decode.py) preserves unknown pulses,
rejects malformed/incomplete sequences and does not infer Standby from a pulse.
Use `decode.py --sequence cold` for a complete automatic cycle and
`decode.py --sequence storage` for a repeated RAM SAVE (events 4–9).
Their `--help` output describes the explicit channel/sequence options. Only the
bench owner may run capture after confirming physical probes and ownership.

```powershell
python firmware/capture-sd/phase_markers/test_marker.py
python -m unittest discover -s firmware/capture-sd/phase_markers -p "test_*.py"
```

The actual-C marker model exercises 18 cases: all ten event widths, invalid IDs,
disabled/stalled counters, CYCCNT wrap, PRIMASK preservation, and preservation of
other GPIO bits. Existing storage completion, image-integrity and recovery gates
remain the authority for success; decoded pulses supplement those proofs.

## October 23 hardware result

The PD12 wiring passed a reversible three-pulse smoke test after the probe was
reseated. The instrumented firmware produced complete phase sequences, but the
strict pulse-width decoder rejected them: GPIO/bus/cache overhead was variable
enough to exceed the original tolerance. That decoder and its failed results
are retained unchanged. Do not use pulse width alone to identify these events.

The [baseline archive](../evidence/2026-10-23-one-bit-baseline/README.md) contains
a separate analysis that requires the exact number of complete pulses, stable
capture boundaries, the reviewed source call order, and independent successful
operation evidence. Its event labels are explicitly inferred from source
order; `width_qualification` remains false. A future reusable marker protocol
needs wider spacing or a different encoding and renewed hardware qualification.
These October 23 results describe the frozen v60/v61 overlays. New profile-aware
overlays need their own exact-build, completion and image evidence; they do not
inherit qualification merely because the pulse order is unchanged.
