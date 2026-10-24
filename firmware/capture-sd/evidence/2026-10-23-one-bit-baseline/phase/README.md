# Source-order phase timing — October 23, 2026

The strict width decoder **failed** on v61b cold cycle 01. The ten measured HIGH
widths were 0.74, 1.24, 1.74, 2.56, 2.73, 3.07, 3.58, 4.07, 4.87 and 5.34 µs.
Several exceed the original ±0.15 µs tolerance, and one would receive the wrong
event ID from width alone. The [original failed result](v61-cycle-01/strict-width-summary.json)
and [cycle result](v61-cycle-01/cycle-result.json) are preserved verbatim.
Neither the decoder nor its tolerance was changed.

The [separate timing table](v61-cycle-01/timing.md) assigns ordinal labels
**inferred from source call order**. It requires exactly ten complete pulses,
twenty strictly increasing edges, LOW beginning and ending states, matching
capture bounds, and one observed NRST-release and 5 V threshold edge before the
markers. The exact v61b sector was independently read back in full; its sources,
rebuild identity and checkpoint placement are verified against the frozen build.
A later warm recovery observed the exact prefix park and SBF=1. These facts
support the ordering inference; they do not turn pulse widths into qualified IDs.

With that explicit interpretation, the observed STROBE interrupt marker occurred
22.817 ms after NRST release, frame completion at 44.679 ms, SAVE entry at
501.784 ms, and the pre-WFI marker at 2.732168 s. The pre-WFI marker was
2.733800 s after the observed 5 V digital threshold crossing. These are same-capture
GPIO intervals, not analog power-good, exact exposure timing, or electrical
Standby entry. No synchronization to the separate Joulescope clock is inferred.

`ordered-analysis.json` keeps every measured rising/falling edge and pulse width,
all input hashes, and `width_qualification=false`. The SBF reader's original
`trial_entry_proven=false` is preserved: it reports historical Standby since the
last flag clear/POR; trial attribution additionally needs the reset/power history.
This analysis performs **no saved-PNG or original-frame verification** and leaves
`image_integrity_verified=false`. Later image qualification belongs in an addendum.

Only compact digital exports, metadata, the 64 KiB independent firmware readback,
and supporting logs are included. No analog sample stream, SAL capture, image or
SD dump is copied. `v61-cycle-01/inputs.json` records exact original paths and hashes.

Reproduce from the repository with the adjacent frozen build archive present:

```powershell
python ordered_edges.py v61-cycle-01
python test_ordered_edges.py
```

Run these commands from this `phase/` directory. Both are offline and access no
instrument or target. The first recreates the separate derived JSON and table;
it never writes the original strict-decoder result.
