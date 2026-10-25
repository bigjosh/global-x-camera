# 27 ohm CLK resistor: observed signal follow-up

With the user-reported 27 ohm resistor inserted approximately midway along
CLK, the subsequent 25 MHz NEGEDGE/speed3 write has **zero observed 4/8/12 ns CLK
pulses** during its data transfer. The preceding phase-only write had thousands.
This is a digital-threshold observation, not an analog ringing measurement.

At both 0 ns and +4 ns sampling offsets, all 3,730 wire packets exactly match the
original pattern frame plus GXR2 metadata/trailer, and all 14,920 per-lane CRC16
checks pass. Every block has its first DAT0 CRC response `010` (accepted),
consistently three clocks after the data end. At -4 ns, 3,614 packets have all-four
CRC passes and 3,618 payloads match; that edge-sampling ambiguity remains part
of the report rather than being silently removed.

The separate 512-sector read trace contains every expected sector with valid
four-lane CRC and exact original-RAM bytes at 0/+4 ns. At -4 ns, 511 expected sectors
match; sector 477 is ambiguous at that earlier sampling point.

Independently of the analyzer decoding, full post-resistor software readbacks
of previously written slots 3 and 4 passed, each matching all 1,909,600 original
camera-RAM image bytes. These are the earlier default-phase and NEGEDGE
pattern writes respectively. The observed new resistor-equipped write's
later complete SD readback, no-probe trials and coldboot trials belong in
their own hardware records.

## Attribution limits

CMD/CH3 became constant LOW with no transitions after insertion of the resistor.
Therefore these two traces do not independently establish the command stream;
write/read mode and extent come from firmware proof and expected pattern data.
Effective CMD-probe loading may also have changed, so this is not a perfectly
isolated analog resistor experiment. The zero narrow-clock observations,
exact wire data and restored software reads support the damping approach;
they do not establish the specific electrical cause or production margins.

`post-resistor-signal-analysis.json` retains all offsets, exact selected CRC
statistics, source hashes and full-readback equality. It contains no instrument
or card identifiers, user paths, raw images or bulk waveforms.
