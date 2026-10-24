# Three v66c cold cycles

Compact records for [standby02](standby02/summary.json),
[standby03](standby03/summary.json) and [standby04](standby04/summary.json)
preserve the closed cycle recordings, phase digital edges/configuration, first
warm-UART recovery request, exact early-recovery park and fresh SBF read. All
three observed SBF set. No images, raw Joulescope sample streams, native Saleae
recordings or large analog captures are included.

The original strict pulse-width decoder failed and remains failed. The SBF
reader's original `trial_entry_proven=false` remains unchanged as well: SBF alone
does not identify which cycle set it. Each summary instead links the separate,
hash-bound hardware-owner attestation that the exact v66c image stayed installed,
no SWD operated during capture or the plateau, and warm recovery/SBF observation
followed that plateau without an intervening power-off. Source-order phase
interpretation and qualified energy endpoints are analyzed separately.

The cycle archive does not claim PNG readback success. Later file verification
is an independent addendum. Run `python verify_standby.py` from this directory to
check all 282 indexed records and their attestation/park/SBF bindings without
reading any raw stream or accessing hardware.
