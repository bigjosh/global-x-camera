# Diode recovery qualification — October 17, 2026

The PE1 recovery guard is installed and works on this board. With the JS110
GPIO supply at 3300 mV, OUT0 low selects early recovery and OUT0 high releases
PE1 for normal flash boot. The diode anode is on PE1/CN15.24; its cathode is on
OUT0. No jumper changes were needed for the completed guard tests.

| Test | Observation |
|---|---|
| Pull-up, OUT0 low | PE1 low |
| Pull-up, OUT0 high | PE1 high |
| Pull-down, either powered OUT0 level | PE1 low |
| GPIO supply off, retained OUT0 low, pull-up | PE1 stayed low: not a usable release setting |
| v34c normal cold boot | Complete recognizable image, matching integrity |
| v34c requested cold recovery | Exact early park, debugger accessible, both caches disabled |
| Flash update from early recovery | v34c → v34b → v34c; both full 64 KiB readbacks matched |
| Final normal cold boot | Valid image, PE1 high, first reported exposure-start event at 24.05456 ms after NRST |

The 40,000-cycle pull settling interval measured 40,002–40,004 cycles in these
tests (about 100 µs at the retained 400 MHz clock). No analog diode-drop,
noise-margin or leakage qualification is implied by the digital pin tests.
The exposure-event time uses the existing callback/marker correlation; this
recovery test did not independently requalify the sensor exposure timing method.

The final installed first-64-KiB image SHA-256 is
`14b6015e0c5705ce5bde655470977851e32cce01fa0164ccda163b892dca3222`.
After closing the owned power session, the GPIO supply was deliberately left at
3300 mV and OUT0 high; a subsequent MCU input read confirmed PE1 high. Power
remained on in auto range, and the temporary input-bit routing changes were
restored. Captured room images and large recordings stay local under
`tmp/bringup`; this directory contains compact engineering evidence only.

Read [the final qualification summary](guard-qualification/qualification-summary.json)
and [the operational instructions](../../recovery_gpio/README.md). The earlier
`independent-summary.json` and `followup-summary.json` are historical checkpoints:
their pending/blocked states are superseded by the final qualification. Source
provenance accompanies each evidence set.

Two useful findings are retained in the implementation:

- CubeProgrammer can resume the MCU when a connection closes. A halt-dependent
  operation must share the halt command's connection; the verified recovery
  branch-to-self remains safe if resumed.
- v34b entered recovery but retained ROM's instruction cache. v34c disables and
  invalidates I-cache only on the recovery branch; the host still rejects an
  unexpectedly enabled D-cache. The normal capture path skips this change.

All 58 boot-helper tests and 41 capture tests passed. The existing startup D-PHY
error remains visible in this unchanged v25 receiver; this work qualifies the
recovery mechanism, not a resolution of that separate camera-link issue.
