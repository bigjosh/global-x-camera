# ST shutdown sequencing question

Published November 7, 2026 in STM32 MCUs Products as **bigjosh**, tagged **STM32N6 series**. Status at publication: awaiting ST clarification, zero replies.

[Published topic](https://community.st.com/stm32-mcus-products-25/stm32n6-nucleo-power-off-pwr-on-at-1-63-v-vs-aux-before-main-requirement-169308)

The question asks ST to reconcile PDR-triggered PWR_ON deassertion with the newer AUX-before-main shutdown requirement and explain stock Nucleo compliance during sudden input removal. This is a documentation clarification request, not a measured stock-board violation.

## Exact posted title

STM32N6/Nucleo power-off: PWR_ON at 1.63 V vs AUX-before-main requirement

## Exact posted body

Hello ST team,

I am using the NUCLEO-N657X0-Q and trying to understand the intended behavior when its common 5 V input is disconnected while the MCU is running, without first entering Standby.

There appears to be a mismatch between the current shutdown requirements and the PWR_ON-controlled supply arrangement. Could you help reconcile the following?

1. AN5967 Rev 6 (September 2026), section 3.5.2, requires the auxiliary supply group to discharge below 0.6 V before the main supply group falls outside its operating range.
https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=9

2. AN6000 Rev 1 (November 2024), section 3.2, describes uncontrolled input-power removal. Main VDD/AON fall until a power-down-reset threshold is crossed; PWR_ON then becomes high impedance and its approximately 40 kohm internal pull-down takes it LOW, disabling the core/auxiliary regulators.
https://www.st.com/resource/en/application_note/an6000-how-to-build-the-discrete-power-supply-for-stm32n6-mcus-stmicroelectronics.pdf#page=9

3. DS14791 Rev 11, Tables 25 and 27, specifies a 3.0 V minimum for VDD in the 3.3 V range and a 1.71 V minimum for VDDA18AON. Both falling PDR thresholds are 1.58-1.67 V, typically 1.63 V. Therefore, PDR-triggered cutoff alone appears too late to guarantee that AUX is already below 0.6 V while the main supplies are still valid.
https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=140

On the stock MB1940-N657X0Q-C02 schematic, sheet 9:
- U33 (main 3.3 V / VDDIO) and U23 (1.8 V AON) have their enables tied to the incoming 5 V rail.
- U17 (core), U34 (auxiliary 3.3 V) and U26 (auxiliary 1.8 V) are enabled by PWR_ON.
- U26 is supplied from U34's output.
https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf#page=9

I understand that regulator dropout/UVLO and capacitor discharge can act before PDR. What I cannot see is how they guarantee the required ordering. I am not reporting a measured violation on a stock board; this is a question about the documented design requirements.

Could ST clarify:

1. Does AN5967 section 3.5.2 apply to sudden removal of the common input supply, or is there an exception for complete/uncontrolled shutdown? If there is an exception, what electrical limits apply?
2. How does the stock Nucleo meet the intended requirement during input removal? Is there an earlier shutdown mechanism, or specified regulator/discharge behavior that I am overlooking?
3. Which guidance should a new design follow: is the Nucleo-style PWR_ON arrangement sufficient, or is earlier input-failure detection plus main-supply hold-up required?

Related ST Community answers seem to distinguish these cases differently: the March 14, 2025 reply below accepts simultaneous shutdown, while the September 3, 2026 team response says sequencing is required to avoid inter-supply currents and an unstable shutdown state.
https://community.st.com/stm32-mcus-products-25/details-of-power-down-sequence-of-stm32n657x0h3q-148564
https://community.st.com/stm32-mcus-products-25/stm32n6-power-on-sequence-161758

I also checked ES0620 Rev 5 and did not find an erratum resolving this particular point. A clarification of how AN6000's uncontrolled shutdown relates to current AN5967 guidance would be very helpful.

Thank you.

## Publication evidence

The signed-in topic page showed the full title and body, author, category, tag and zero replies after submission. [Screenshot](published.jpg). No hardware or firmware changes accompanied publication.
