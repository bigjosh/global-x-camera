# Hardware capture check for exposure-marker latency

October 17, 2026. This is an isolated diagnostic of the native v25 capture path. The root controller owns hardware execution. `build_timer_probe.py` verifies frozen source hashes and builds a separate receiver/prefix without editing the shared capture source or original firmware. The unexecuted TIM2 v29 candidate is superseded by **TIM5 v29b**: the ROM leaves TIM2's clock enabled, so reusing it would violate the probe's ownership guard.

## Circuit and configuration

The existing sensor STROBE reaches MCU PA0. DS14791's alternate-function table assigns PA0 AF2 to TIM5_CH1. RM0486 Rev4 §54.4.7 describes latching the counter into CCR1 at a capture edge. TIM5 is a 32-bit timer, and TI1SEL=0 selects its CH1 pin. CC1S=01 selects input before PA0 changes to AF2; CC1P=CC1NP=1 selects both edges. No output-compare/PWM mode, timer interrupt or DMA is enabled. All other timer channels remain disabled.

PA0's existing EXTI route, rising/falling triggers and mask remain configured; direct AFR/MODER updates preserve them. RM0486 §15.3.11 states that the digital input remains active in alternate-function mode. The timer configuration therefore adds an independent edge latch while retaining the existing EXTI callbacks and external PE0 markers. The implementation refuses a pre-existing TIM5 clock gate or nonzero CR1/SMCR/DIER/CCER, and never changes TIM2.

The STM32N6 timer clock rule differs from the common APB-doubling rule. RM0486 §14.10.5 defines `timg_ck = sys_bus_ck / 2^TIMPRE`. The observed CFGR2=0x00100000 has TIMPRE=0 and HPRE=1, giving timer 300 MHz while APB1 is 150 MHz. The probe requires this clock profile and a 400 MHz CPU, records the configuration, and brackets two counter reads with DWT timestamps to independently validate the 3:4 ratio. The HAL system-clock helper was already linked by the baseline's APB1-frequency read; this does not introduce a new floating-point maintenance requirement.

## Bounded record layout

The receiver manifest declares `timer_status_address=0x343F7000` and `timer_status_words=224`. This 896-byte region ends at 0x343F7380, above all existing records and outside the frame/code/stack/helper regions. It contains a 32-word header followed by at most sixteen 12-word records. No host scan or unbounded memory read is needed.

| Header words | Meaning |
| --- | --- |
| 0–3 | T5IC magic 0x54354943; initialization status (0 success); timer Hz; CPU Hz |
| 4–8 | RCC CFGR1, CFGR2, IC2CFGR, DIVENR, original APB1ENR1 |
| 9–12 | Original TIM5 CR1, SMCR, DIER, CCER |
| 13–18 | GPIOA MODER, AFRL; EXTI EXTICR1, RTSR1, FTSR1, IMR1 |
| 19–23 | TIM5 CCMR1, CCER, TISEL, PSC, ARR |
| 24–25 | Recorded edge count; dropped-record count |
| 26–28 | Initial DWT-before, CNT, DWT-after |
| 29–31 | Final DWT-before, CNT, DWT-after |

Each record stores event ID; CNT before PE0 logger; CNT after logger; SR before CCR1; captured CCR1; SR after CCR1; modulo-32-bit minimum and maximum marker lag in timer ticks; DWT at record time; GPIO input level; trace event count after logger; validity bits. Validity requires all four bits: CC1IF was set, no CC1OF in either status sample, pin level matches the edge, and CC1IF cleared after reading CCR1. Reading CCR1 clears CC1IF in input mode; the prior SR is essential evidence. Overcapture is recorded before acknowledging only CC1OF using its write-zero-to-clear semantics.

## Interpretation

The callback brackets the unchanged `event(50/51)` logger with TIM5 CNT reads. Subtracting the latched CCR1 from those two samples gives a measured interval containing the PE0 marker's delay from the timer edge. The added reads slightly perturb the instrumented path; no claim is made that they speed it up. The first timer capture must match the first event 50, and its following event 51 must precede the first frame-complete event.

`analyze_timer.py` validates fixed length, initialization and ownership, counts/no overflow, every record's flags and event index, clock ratio, edge ordering and pulse-width agreement with the external trace. Absolute counter conversion uses the independent, near-exposure event 26-to-29 DWT/Saleae interval, then the verified 3:4 timer/core ratio. It retains other independent interval rates and a conservative empirical frequency envelope. This avoids treating nominal 300/400 MHz as exact or assuming the measured average frequency remains constant throughout startup. Nominal and measured values are both retained. The envelope includes an explicit allowance of 10 µs logging displacement and one 0.16 µs sample at each endpoint; this allowance is an assumption, not a proved worst-case bound. The exposure pulse is not used to calibrate its own width.

The decoder rejects missing/overwritten captures and marker lags of at least 1 ms. Regressions verify that a plausible timestamp cannot pass when overcapture is flagged and that a non-nominal clock is calibrated from the independent markers. Output is created exclusively, preserving raw evidence.

This checks an **observed marker-delay bracket relative to the timer's synchronized input**. Sensor output, translator and timer input-synchronization delay are outside that bracket. It is not a universal worst-case interrupt-latency or direct optical-onset guarantee.

## Observed native RAW10 result

The [v29b evidence archive](evidence/2026-10-17-native-raw10-tim5-v29b/README.md) records one cold start with a discernible LED-panel image, independently inspected by the root bench controller. All four edge records passed validity flags and event association, with no overcapture or log overflow. The first rising edge's synchronized-input-to-PE0 bracket was **0.6743–3.9855 µs**; the largest upper endpoint across all four records was **4.1001 µs**. The first PE0 exposure marker was 23.732160 ms after NRST, placing the synchronized timer edge in the empirical interval **23.728175–23.731486 ms**. These intervals use the observed frequency envelope and the stated endpoint allowance.

The near-exposure interval measured CPU 396.715738 MHz and TIM5 297.536803 MHz. Independent non-strobe intervals showed different average rates across the run. Using the much longer event 3-to-40 interval as a constant clock incorrectly predicted a first pulse of 10,978.717 µs against the external 10,984.000 µs and failed the initial consistency check. The archived diagnostic note preserves this rejected assumption. Local calibration gives 10,983.945 µs, consistent with the external pulse; the empirical envelope also covers it. The observations establish nonstationary measured rates, without identifying their physical cause or establishing a universal instantaneous-frequency bound.

The measured logging delay is negligible compared with millisecond-scale startup optimization. NRST-relative corrected values retain the external trace's 0.16 µs sample spacing and uncalibrated absolute-time accuracy; their decimal precision is not an additional accuracy claim. This diagnostic adds timer reads to the capture callback, so it qualifies the instrumented path rather than providing an exact correction to every earlier run.

Primary references: [RM0486 Rev4](../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf), §§14.10.5, 15.3.11, 54.4.7 and timer status/CCER definitions; pinned STM32N657 CMSIS and GPIO alternate-function headers; STM32N657 DS14791 PA0 alternate-function table.
