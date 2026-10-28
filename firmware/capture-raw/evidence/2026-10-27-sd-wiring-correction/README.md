# SD CLK wiring correction, October 27, 2026

**The SD CLK connection was a direct jumper with no series resistor from
the beginning of the CLK-slew experiments onward.** The user clarified this
while the CLK-only probe control was in progress. This supersedes the bench
owner's inherited assumption that a 27-ohm resistor remained near the card.
It is a user-reported wiring correction, not an independent physical inspection.

The clarification covers:

- [CLK-only slew testing](../2026-10-27-clk-slew/README.md), including its
  preliminary and formal attempts.
- [Probe-free PIO/IDMA reads](../2026-10-27-pio-idma-read/README.md).
- [Both CLK and CMD probes attached](../2026-10-27-pio-idma-probe-control/README.md).
- The subsequent CLK-only probe control, whose new evidence records use
  the corrected direct-jumper condition from the outset.

References in the first three sealed archives to a resistor being present,
its value or position are incorrect for these tests. Their original text is
preserved; [scope and checksum bindings](scope.json) identify the records
this addendum corrects. Earlier experiments outside this stated interval
are not retrospectively assigned the same wiring.

According to the clarification, the same actual CLK connection was used
across these conditions. The measured bytes, CRC outcomes, GPIO settings,
exact executable identities and matched probe comparisons remain unchanged.
Any explanation that depends on a resistor being present must instead be
evaluated using the direct CLK jumper. This correction does not itself
establish reflections or another electrical cause.

The evidence worker changed no earlier archive and accessed no hardware.
The current bench record and owning SD notes are maintained separately by
the bench owner.
