# Normal-firmware Ethernet power-down integration review

2026-10-28. Offline review only. This review did not access instruments, program
NOR, or modify any frozen candidate inputs. Root owns installation and hardware
qualification. **No source-level deployment blocker found for the reviewed
25 MHz normal camera profile.**

## Behavior and failure semantics

`board_eth_powerdown_once()` is called at the start of `raw_magic_execute()`,
after receiver arm, sensor-start acknowledgement and the checked late load,
before SD initialization. It touches only the unused LAN8742 management pins
and BMCR: PF4/MDIO, PG11/MDC, PHY address 0. It does not use the Ethernet MAC,
change a rail, assert PHY reset, or alter the camera/SD settings.

The helper checks the qualified 400 MHz RCC tuple, DWT availability/progress,
privileged thread context and D-cache-off requirement. I-cache and the live
camera path's CONTROL FPCA/SFPA bits are permitted. GPIO access follows clock
and reset checks. Short pin-configuration RMW sections preserve PRIMASK;
interrupts remain available during all MDIO transactions.

The helper requires IDs `0007/C13x` and two equal stable BMCR reads. AN must
remain enabled; only speed/duplex strap bits and optional existing power-down
are accepted. For BMCR `3000`, it writes `3800` once and verifies two reads.
For a stable already-powered-down BMCR, it performs no write. It never clears
power-down, retries a write, or restores the PHY at the end of capture.

Missing pull-up/PHY acknowledgement, unexpected identity/configuration,
unsupported clocks/context, stalled DWT, failed readback, or cleanup mismatch
produce retained `ETH1` warning telemetry. The API is void and has no path to
camera/storage terminal handling, error LEDs, reset or storage abort. A first
failed attempt is not retried on a later call in the same runtime. A write
attempt whose verification fails retains `OUTCOME_UNKNOWN`; it does not claim
an energy saving or attempt a potentially disruptive rollback.

The original owned GPIO mode, output type, speed, pull, alternate function and
output latch are restored and checked. Only GPIO clock bits enabled by this
helper are removed; unrelated bits are preserved. If clocks/reset unexpectedly
change during operation, the helper refuses unsafe GPIO cleanup and records
the failure. Continuing the camera on that warning does not falsely certify
the GPIO restore or the power saving.

RAM READ operations bypass this helper and require a zero proof. A readback
does not prove the PHY's retained power state. The host observer accepts a
well-formed warning without invalidating a successful image, but qualifies
power-down only with complete identity/BMCR/GPIO/clock/timing evidence.

## Placement, measured example and limits

The candidate offline audit puts all 16 helper functions in the checked late
interval `0x34303DBC..0x34308330`. The ROM/early receiver remains 15,804 bytes;
the recovery prefix remains 6,720 bytes and only its two receiver-CRC words
change. Recovery instructions/literals and the relocated error engine remain
identical. The feature-disabled rebuild is byte-identical to the previous
normal build.

The enabled receiver grows from 31,348 to 33,584 bytes, entirely in late code
for the new functions. BSS grows from 2,336 to 2,612 bytes (276 net bytes,
including proof/latch/alignment effects). Therefore fixed early code length
does not establish identical cold-start timing: BSS clearing and the larger
late transfer still require measurement. The helper does not deliberately
delay exposure, but it delays SD initialization by its own work and may affect
total cycle duration; compare complete cold cycles rather than subtracting a
steady-state current alone.

The already-recorded RAM capture in `candidate-reobserved/verified.json`
qualifies new power-down with IDs `0007/C131`, BMCR `3000 -> 3800`, one write,
six reads, exact GPIO/RCC restoration and CONTROL `0xC`. It started 0.343590 ms
after arm, took 5.319825 ms, and ended 1.6375 us before SD initialization.
This is a saved RAM result, not evidence of NOR installation or a new cold
energy measurement. Complete image readback was still being handled by root
when this note was written.

The absent-PHY/fail-open paths and already-down/no-write behavior are covered
by the offline model; an absent physical PHY was not tested here. Power-down
does not remove all PHY supply current, and cold power restoration may reset
the PHY to its normal state. A custom PCB would ordinarily omit this unrelated
load. Clock/profile changes deliberately produce a warning until the helper
and its proof validator are requalified.

## Verification and source identities

- `test_board_eth_powerdown.py` retains the actual C clock, framing, guard,
  write and cleanup routines. The PHY advances its output immediately after
  rising MDC; deliberately restoring the old late sample fails the same test.
- New/retained PD, missing PHY, wrong ID, unstable/unsupported BMCR, GPIO clock
  enable/restore failures, stalled DWT, ambiguous writes, exact pin restoration,
  enabled/disabled initial IRQ state and one-shot behavior are exercised.
- `test_board_eth_bench.py` covers complete success, nonfatal warnings, proof
  placement/profile admission, READ bypass, malformed claims and FP context.
- This review reran 15 focused tests successfully; see `integration-tests.txt`.
  The earlier helper/prior-probe combined run passed 17 tests. The independent
  integration agent reported 222 capture-raw tests passed before the later
  host-only CONTROL correction; its focused correction tests also passed.

Frozen helper SHA256:
`4353eeb1f447fb6da3a5981ba0692ef87d0c5aa91d46e892292d82873bf9ee8c`.
RAM receiver SHA256:
`ef85e7106b3cb0cb253fe4a174e926a1bd227c006b7bfa46ab0433a1496ae000`.
Flash receiver SHA256:
`69c5a5c0cc434eb7496371d9e5b9c007db346b8bb7b9a1a650c90f0eade79d28`.
Candidate flash sector SHA256:
`a10e4894d79cd3fe182b95b48eb56a308280f3201736d295860ecfe725a62645`.

## Production build selection

From the repository root, the following is an **offline build**, not a
programming command. Use a fresh output directory and inspect its manifest
and recovery/layout audit before a separate hardware installation:

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/ethernet-normal-20261028/flash-production-review --base tmp/bringup/sd-normal-20261024/v66c-normal-standby --pattern scene --transport idma --sd-bus-width 4 --sd-clock-hz 25000000 --sd-gpio-speed 3 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt --magic-format --line-stream --async-stop --flash --standby --error-blinks --ethernet-powerdown
```

`--ethernet-powerdown` is explicit; omitting it keeps the legacy behavior.
Do not substitute the RAM-only `--power-probe ethernet-powerdown` option:
that experiment adds a hold and restores BMCR, and is excluded by the normal
feature's guards. The current normal feature is scoped to the reviewed
25 MHz four-bit/default-exposure profile; other experimental combinations are
not qualified by this review.
