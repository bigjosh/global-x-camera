# Fixed post-frame error handling, shutdown and UART recovery

October 26, 2026. The runtime engine now executes from the verified persistent
copy at `0x343C8000`, outside camera DMA. The production four-bit 25 MHz
Standby image is installed and fully read back. An explicit post-frame test
and a real production SD read failure both produced five sets of four red
blinks, followed by the low-current plateau and successful UART recovery.

**The resistor-free SD connection still fails CRC.** This work fixes its
error response, not the signal-integrity problem. The normal test saved no
new photo. The user's removed CLK resistor and analyzer probes stayed removed;
no clock reduction, SD erase or wiring change was used to make this test pass.

## Installed identities and placement

| Item | Verified identity or placement |
| --- | --- |
| Production build | `flash-normal-v2`, four bits, 25 MHz, reviewed startup/no-tail, Standby |
| Installed 64 KiB NOR sector | `232af9173262473021453f40ea944dfa4cafc2657443cd0b83ea9c8c8bb3b02c` |
| Production receiver | `fd37dde1ac7e26918346eafd0d5ecc20f0551553fff82bd0126b716cf6d7303a` |
| Production 6,720-byte prefix | `99dbb0f9ecdd56a9313e4e62bbbfec22ec8e5e5901c852d956315844cd066eba` |
| ROM-loaded engine source | `[0x34181840, 0x34181E40)`, includes zero padding |
| Persistent executable copy | `[0x343C8000, 0x343C8600)` |
| Entire copied 1,536-byte engine | `247ad0ddd76963039ed01a2e14beb3499ee9097a8df86f62ad5751047835454e` |
| Packed camera DMA | `[0x340000A0, 0x341D2400)`, 1,909,600 bytes / 1,527,680 pixels |
| Early receiver extent | 15,804 bytes, unchanged |

The original prefix remains usable only before DMA. The receiver revokes old
copy authority at entry, refuses an enabled D-cache, copies and compares every
word, invalidates I-cache, and publishes fresh `ECP1` proof before any terminal
or camera path. A pre-arm copy failure can use the original prefix engine;
runtime failures use only the high-SRAM copy. The linked source engine has no
external call, indirect branch or address-sensitive dependency outside its
section. Independent review includes Cortex-M55 hardware-loop control flow.

Both diagnostic and production installations passed programmer readback and
an independent complete physical 64 KiB NOR readback. The following 4 KiB
remained unchanged. The existing early recovery instructions and literals are
preserved; only the two checked receiver CRC words changed inside the former
prefix extent, followed by 220 bytes of added zero padding. The normal image
contains no diagnostic-enable literal. No new cold-start latency claim is made.

## Deterministic post-frame test

The separate `flash-postframe-v3` image uses the real sensor/receiver and waits
for the complete validated frame plus sensor STOP. It then calls the normal
code-4 terminal before any SD operation, isolating error handling from the
unreliable SD connection. Read-only ST-LINK observations during display proved:

- One complete 1,909,600-byte frame, validated FRAME and STOP, and zero guard
  failures before error dispatch.
- The original prefix engine's first word had become image data, while all
  1,536 bytes of the persistent copy still matched the production engine.
- Nonzero RAW result `0x20E`, intended code 4, zero SD reads/writes, and
  `CFSR=0`, `HFSR=0`; no halt, reset or target-memory write in the observation.
- Twenty current pulses in five groups of four. Measured on intervals were
  95–100 ms; within-group dark intervals 405–410 ms; between-group dark
  intervals approximately 2,015 ms. Each is consistent with the requested
  100/400/2,000 ms schedule under the stated ±20 ms interval uncertainty.
- Approximately 405 ms after the last pulse, current reached an 8.059 mA
  plateau on the Joulescope-fed Nucleo branch.

First-attempt warm UART recovery after this shutdown reached the exact early
park with nine good pulses and zero bad pulses. The guarded flag reader then
observed `SBF=1`, `PDDS=1`, `STOPF=0`, without a further reset or power cycle.
Its `trial_entry_proven:false` limitation remains: the flags report Standby
since the relevant flag clear/POR; the reader does not independently prove the
complete entry history.

A second real-frame diagnostic verified the same intact copy and zero fault
registers, then requested UART recovery 2.123495 seconds after power-on,
during the nominal 16.4-second display; the actual BREAK stimulus began
2.548631 seconds after power-on. Recovery reached the exact early park
with three good pulses and zero bad pulses. This interrupted display is
intentional and is not counted as a completed five-set shutdown trial.

## Uninjected production test and final state

After installing the normal image, a cold cycle captured the full frame and
reproduced the original storage problem: two slot headers read, then `CMD17`
failed with error 14 / stage 5 / status `0x2` (`DCRCFAIL`). RAW result `0x324`
and `cleanup_error=10` remain explicit. No image sectors were written. The
reported deinitialized/unowned/media-idle fields do not erase the failed
operation or grant successful-save permission.

The persistent engine still matched exactly and `CFSR/HFSR` remained zero.
Twenty pulses in five groups of four were observed, followed by approximately
8.062 mA. On intervals were 80–100 ms, within-group dark intervals 405–410 ms,
and between-group dark intervals 2,015–2,020 ms, within the same conservative
±20 ms interval uncertainty. The short first observed interval remains in
the evidence; it is not silently replaced by the nominal value.

Warm UART recovery passed with ten good pulses and zero bad pulses, and the
guarded flag read again reported `SBF=1`, `PDDS=1`, `STOPF=0` with
`trial_entry_proven:false`. The Joulescope recording closed cleanly at
21:56:33.455049 UTC, restored its initial range 128 and left target power on.
The final flag read ended at 21:57:35.113112 UTC. Final target state is the
normal firmware's exact early UART park, **not the low-current plateau**; no
additional normal boot followed the flag read. CLI disconnect can resume that
verified branch-to-self park, so persistent halt is not asserted.

## Evidence limits and replay

The 5 ms bin minima and three-bin median filter infer LED transitions from
current steps. No optical or LED GPIO probe was attached. ST-LINK read-only
access occurred during display. Timing is consistency evidence with ±20 ms
interval uncertainty, not precision clock calibration or a new energy result.

Each complete recording contains 71 nonfinite startup current samples, so
whole-session validity remains false. The analyzed error windows have finite,
contiguous current and voltage samples, no dropped queue chunks and no logger
error. These scoped checks are not generalized to the entire recording.

No successful normal SD save is established for the changed wiring; no new
signal-integrity margin, retained-photo readback, arbitrary power-loss safety
or battery-side shutdown-current qualification is claimed. The diagnostic
specifically proves post-DMA engine lifetime, and the production trial proves
the real CMD17 error reaches that same working response.

`python -B archive.py verify` checks immutable snapshot hashes, firmware/source
identities, independent installation bytes, both complete waveform analyses,
full-frame/error records, UART parks and guarded power flags. Camera payloads
and private overwritten-prefix dumps are excluded. The prior faulty-image
[diagnosis](../2026-10-26-error-handler-overlap/README.md) and its old blink-test
archive remain unchanged.
