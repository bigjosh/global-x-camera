# v60c awake and retained-frame SAVE phase evidence

This is an additional source-order analysis. It does not change the earlier
v61 record, the strict decoder, or any failed width result. The exact v60c
sector is `20444827100b1a33826c5b7e3362a396a0ce31f27f0c3db7fea12fb755320f7e`;
the module is `51c067de2859588fc87cf1249fdff4186b17a4e0ab85585c72fc9b5dc94379f5`.

The [cold run](v60-cycle-01/timing.md) has ten complete pulses, an independent
full NOR read, and a later successful automatic SAVE maintenance proof. Its
last checkpoint is the awake completion park, **not Standby or WFI**. Captured
RAW metadata and its SHA-256 bind the input without copying camera pixels.
The separate [automatic-image verification addendum](../automatic-save-v60/verification-addendum.json)
records the later full `IMG00061.PNG` pixel readback; the timing analyzer itself
does not perform that check.

Three subsequent RAM SAVE operations reused that retained input. Each recorded
six complete pulses with LOW marker boundaries while NRST and target 5 V
remained digitally HIGH throughout. The strict terminal reports have fresh
request nonces, successful file/card completion, caches disabled, and the exact
RAM park. Actual loaded module bytes and request/report readbacks are retained.
Host monotonic brackets put the SAVE command and successful report within each
manual Logic recording. This associates the operation with its recording; it
does not synchronize Saleae and Joulescope sample clocks.

| Record | Saved image | Inferred entry→event 9 edge interval (s) | Firmware COMPLETE (s) |
| --- | --- | ---: | ---: |
| [same-frame-01](same-frame-01/timing.md) | IMG00062.PNG | 2.113330 | 2.102061 |
| [same-frame-02](same-frame-02/timing.md) | IMG00063.PNG | 2.115049 | 2.104129 |
| [same-frame-03](same-frame-03/timing.md) | IMG00064.PNG | 2.109927 | 2.099228 |

The external intervals use Saleae rising edges; COMPLETE uses DWT cycles
divided by the firmware's nominal 400 MHz and different software endpoints.
Their approximately 11 ms difference is retained without calibration or an
invented offset. Event 9 precedes terminal publication. Do not substitute one
time base for the other or use this evidence to assign Joulescope energy to
individual phases.

All labels remain **inferred from source call order** and
`width_qualification=false`. The measured six-pulse widths were:

| Record | Widths in source-order sequence 4–9 (µs) |
| --- | --- |
| same-frame-01 | 2.53, 2.73, 3.07, 3.57, 4.06, 4.81 |
| same-frame-02 | 2.53, 2.72, 3.08, 3.56, 4.06, 4.81 |
| same-frame-03 | 2.51, 2.72, 3.07, 3.57, 4.08, 4.81 |

The nominal widths are 2.0 through 4.5 µs in 0.5 µs steps; several measured
widths are outside tolerance, and event 4 can look like event 5 by width. No
missing pulses are synthesized. The JSON keeps every original edge and width.
The inferred mount→PNG and commit→validation intervals encompass multiple
operations; they are not isolated compressor or card-programming costs.

Run `python test_ordered_v60.py` for offline rejection tests, or
`python ordered_v60.py same-frame-01` to reproduce one analysis/table. Run from
this directory. The latter rewrites only derived outputs, not the original
strict-width result. `archive_v60_phase.py` is an optional local acquisition
archive helper; it refuses existing destinations and copies only explicitly
listed compact metadata, firmware readback, and digital exports. No image,
analog stream, or full SAL capture is copied. `v60-index.json` binds this
addendum, leaving the original `index.json` and v61 files unchanged.
