# Dual-knob calibration — November 13

The live RAM diagnostic read both installed potentiometers while the user
positioned them at clockwise, mechanical center, and counterclockwise.
Each reported point uses eight stable host samples; the diagnostic itself
sampled at 10 Hz. Normal D8 camera/PTP FLASH was unchanged.

| Position, viewed at knob faces | Exposure A1 raw median | ASA A5 raw median |
|---|---:|---:|
| Clockwise stop | 3840 | 0 |
| Mechanical center | 2177 | 1780.5 |
| Counterclockwise stop | 1.5 | 3840 |

Exposure voltage increases clockwise; ASA voltage increases counterclockwise.
To make both physical controls increase counterclockwise, invert exposure
normalization and retain positive ASA normalization. A2/A4 reference readings
were 3840; A0 was near zero. The ADC full-scale value 4095 is not the observed
potentiometer endpoint. The center positions correspond to 43.32% and46.37%
of travel measured from clockwise. These three manually positioned points
support approximately linear taper, not a full angle/linearity calibration.
Do not force the hand-positioned center to 50% or claim calibrated ASA.

Exposure: A0/PF5 LOW, A1/PA9 ADC1 channel10 via its board buffer,
A2/PF6 HIGH. ASA: A4/PC12 HIGH, A5/PG15 ADC1 channel7 via its board buffer,
low end GND. D8/PD12 HOLD stays HIGH. Raw digital companions PC10/PH2
remain inputs without pulls. The helper preserves the proven ADC12 security
configuration and does not wait on the erratum-affected VDDIO4 power monitor.

Build schema6 is6200 bytes, SHA256
`f611404188a6f762b60f91e19e11ce595a2f4fd8420d3220eb4e1623b7366ddb`.
Thirteen focused offline tests passed. Full RAM readback matched before
execution; complete code identity was checked again before cooperative stop.
The five-channel sample batch took approximately1.761ms, measured cumulatively
from batch start. It is not five isolated per-channel timings.

At clean stop, state8/error0 and CFSR/HFSR0 were observed after3760 samples.
Separate GPIO register reads verified A2 and A4 LOW and D8 HIGH; the terminal
telemetry snapshot alone precedes excitation cleanup. UART recovery then
passed9 good/0 bad at exact park0x3418078C with the unchanged D8 prefix.

Final diagnostic handoff: target powered at the recovery park, direct5V and
ST-LINK attached, no active helper/monitor, COM8 closed/BREAK released. No
NOR/SD writes, JS switching, capture, or latch/shutdown qualification occurred.
The user subsequently confirmed the scene ready for capture integration;
that later campaign owns its own bench state and image evidence.

`position-*.json`, `calibration-summary.json`, `stop01/result.json` and
`park-after-knobs/result.json` are compact results. Their raw inputs, full
monitor and hardware call logs, build artifacts and tests are retained here.
SHA256SUMS pins every frozen file other than this README and the hash list.
