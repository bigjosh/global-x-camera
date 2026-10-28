# Sensor auto-stop measurement plan

This is an offline plan, not a hardware result. Root owns the instruments.

## Decisive observations

Configure context 0 repeat count 1 and next context 4 before START, with
readback. Establish the initial global sensor FRAME_COUNTER at 0x0050. It is
a 16-bit unsigned status register; UM2602 Rev 8 section 15 specifies rollover
65535 to 1, so a generic modulo-65536 delta is not valid at rollover. A freshly
booted zero initial counter avoids that ambiguity.

After the first complete receiver frame, omit sensor STOP and poll the sensor
state until autonomous SW_STANDBY (FSM2), with finite bounds. Retain the first
observed state/time, global frame counter and all PA0 STROBE rising edges.
Repeat state/counter/STROBE checks after the SD operation has completed, without
adding a delay solely for the second observation. The observed interval bounds
what was checked; a stable count is not a lifetime guarantee.

The existing DCMIPP snapshot deliberately accepts one receiver frame. Therefore
receiver `frames==1` is image-completeness evidence, not sensor exposure count.
The existing PA0 EXTI handler counts all STROBE rises and stays enabled after
the first frame. Events 50/51 log rising/falling observations in the 200-entry
trace buffer. Extra sensor exposures can be visible here even when a second
image is not received by the snapshot.

Diagnostic-only PD0 mirroring of PA0 rising/falling callbacks gives an
independent external count through the already-connected JS IN1. It is an
IRQ-observed envelope, not a direct probe of the sensor pin. PD0 is HIGH during
earlier boot, so the mirror must explicitly establish LOW before PA0 IRQ is
enabled, and analysis must exclude startup chatter/HIGH. Match its pulses with
the retained AST/STROBE counts and first-exposure marker; do not classify any
unframed power-on pulse as an exposure.

## Timing and power

PD12 markers 1–10 retain the normal lifecycle. Diagnostic marker 11 is emitted
after the first host observation of autonomous FSM2, after frame marker3 and
before full commit marker8. Other SD markers may overlap this interval.
Marker11 measures an observation upper bound; I2C polling and service latency
separate it from the exact internal state transition.

The unchanged cold normal build has no STOP marker. It supports matched peak,
phase and total-energy controls, but does not independently expose the normal
FRAME-to-STOP interval. Use a fresh awake normal RAM proof's `frame_done` and
`camera_stop` versus the automatic-stop RAM proof for that comparison, retaining
nominal-DWT-clock and polling-resolution limits. Do not substitute the frame
IRQ for STOP in cold plots.

Current/energy are whole-board 5 V input. The first 5 ms and instantaneous
native analog extrema remain unqualified; use finite, contiguous windows and
1 ms/10 ms means on the retained 0.1 ms search grid. Sensor supplies remain
powered in software standby. SD slot count/initialization/write latency can
change total cycle energy independently of auto-stop.

## Outcomes

- One STROBE, one completed sensor frame, autonomous stable FSM2, no STOP
  command, and a full valid image supports true one-frame operation in this
  tested revision/profile.
- Two STROBEs or frame count 2 with otherwise valid data is an experimental
  result, not evidence for single-shot. It may reflect the manual's first-two-
  frames context0 rule; retain both counters and timestamps.
- No autonomous standby within the bound, missing/full-frame errors, counter
  disagreement or CSI shutdown errors are explicit failures to qualify.
  Preserve the failed state; do not silently insert STOP and call that success.
- Successful image readback proves saved bytes/format. Exact equality requires
  retained original RAM; after Standby only recovered-image validation is
  available. Source RAM loss must stay explicit.

## Sources

- UM2602 Rev8 sections 15 and 19: context management, FRAME_COUNTER0x0050,
  CONTEXT_REPEAT_COUNT0x048C and NEXT_CONTEXT0x048E.
- Installed normal generated `flash-candidate/capture.c`: PA0 callbacks392–403,
  first frame callback454–469, PA0 setup633–638, normal STOP poll706–718 and
  receiver/data disable plus explicit STOP791–802.
- Existing JS IN0/IN1 wiring: PD12/PD0 on CN15.21/33; GPIO ground CN15.20.
