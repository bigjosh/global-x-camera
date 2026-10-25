# Pre-resistor 25 MHz SD signal findings

The failed read traces show a **whole-bus advance**, not merely one erroneous
data lane. At the breakpoint, the observed four-lane sequence matches the
original pattern frame with one or three four-bit samples omitted. Every
remaining CRC word is shifted by the same amount and filled by end/idle ones.
This is consistent with extra clock recognition at the card, but the digital
recording cannot establish the analog cause.

| Capture | Source-slot sector | One feasible omitted-clock alignment | Omitted samples | CRC lanes failing |
|---|---:|---|---:|---|
| phase-read02 | 193 | [738] | 1 | all four |
| speed2-read01 | 2 | [500] | 1 | all four |
| speed1-read01 | 2 | [492, 498, 500] | 3 | all four |

These are complete packets before the explicit CMD12 abort. The analysis
preserves separate -4/0/+4 ns sample offsets; all four CRC checks fail at all
three offsets. `phase-read02` additionally has a successful earlier read of
the same data for direct comparison. The speed1 alignment can be ambiguous
inside repeated pattern runs; the table records one exact alignment.

The default-phase successful write capture contains many raw 4/8/12 ns CLK
pulses although a nominal 25 MHz clock has 20 ns half cycles. The NEGEDGE write
contains far fewer, but does not eliminate them. Exact counts and windows are
in `signal-analysis.json`. These extra observed crossings can corrupt a naive
logic-analyzer decode even when the card accepts the block. Both successful
and failed read captures lack the same narrow CLK pulses at the analyzer's
threshold in the observed transaction window. At the first failed read slip,
all four data lines show an 8 ns HIGH pulse, while no extra CLK edge is resolved.

The evidence motivates checking clock integrity, return path and damping.
It does **not** distinguish source ringing, coupling, ground movement, card
input behavior or analyzer observation effects. Moving the launch phase,
changing GPIO slew or adding probe capacitance also changes the experiment.

## Evidence and limits

`signal-analysis.json` contains source hashes, firmware hashes, exact per-lane
CRC comparisons and short digital edge snippets. Original images, instrument
identifiers, card identifiers, user paths and full recordings are excluded.
The raw recording hashes bind the report to the private full recordings.

The offline decoder leaves invalid packets visible. Extra read packets
interrupted by CMD12 are not complete-block CRC evidence. Simple narrow-pulse
filtering was explored only as an explicitly labeled counterfactual; it did
not uniformly recover all accepted write packets and does not replace any
firmware, card or image qualification. LP8 sampling resolution is 4 ns and
its analog bandwidth is insufficient to qualify a 25 MHz edge shape.

All captures in this report precede the user's addition of a 27 ohm series
resistor. Subsequent resistor tests require separate evidence.
