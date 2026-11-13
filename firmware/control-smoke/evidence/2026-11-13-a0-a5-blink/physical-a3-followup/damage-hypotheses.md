# Possible A3 overstress mechanisms — not an established cause

The user asks how A3 could have been damaged. Electrical damage is still
unproven; an inaccessible connection failure can also explain the discrepancy.
No hardware action accompanied this review; the input/pull-up test still
awaits the user's direct5V/ST-LINK reconnection confirmation.

DS14791 Rev11 identifies PA2 as TT_a. Table22 gives3.6V absolute maximum in
the3.3V range; Table25's operating input limit tracks the relevant main supply
plus0.3V when the ADC switch is open. It is not a5V-tolerant contact, and a
fully charged1S LiPo also exceeds3.6V. Externally driving it while its supply
is off can violate the operating limit. Primary source:
https://www.st.com/resource/en/datasheet/stm32n657x0.pdf

Plausible events include accidental contact with5V/rawLiPo, output contention
or a temporary short while driven, and ESD/live-wiring transients. A Q2 pinout
mistake or gate insulation failure could create an unintended path. None has
been observed, and resistance measured after the event cannot rule out a
temporary earlier short.

The correct present latch connects A3 only to Q2's insulated gate and R2=100k
toGND, plus the board's roughly1.03M conditioning branch. HealthyQ2 has no DC
gate-to-drain path from5V/VBAT. Gate-to-drain coupling is capacitive, not a
normal DC feed; R1=100k makes an uncontrolled fast drain rise a weaker default
explanation without a waveform. A swapped gate/drain connection to the Q1
gate node has an R1-limited DC feed, not necessarily a stiff5V source.

A1k series gate resistor would limit current for some wiring faults and
transients without appreciable steady gate-voltage loss against R2=100k.
It would not make the GPIO5V-tolerant or guarantee powered-off protection.
Restoring it is a suggestion for bench robustness, not a new accepted wiring
decision or evidence that its omission caused this failure. Inspect the latch
before transferring it to another GPIO if a pin failure is confirmed.
