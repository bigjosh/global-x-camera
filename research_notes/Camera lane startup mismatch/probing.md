# Observing camera D-PHY startup on the present bench

Research checked October 17, 2026. Read-only investigation: no instruments opened, no target power or firmware changes, and no additional probes connected. The user has a Saleae Logic Pro 8, Rigol DS1054Z with standard passive probes, and Analog Discovery 3. They prefer the already connected LP8 and a software/state-machine investigation before adding probes.

## Can the Logic Pro 8 see the low-power lane states?

### Takeaway

Yes: its digital inputs can distinguish the nominal 0/1.2 V levels on both wires during LP operation. This would show the order and duration of the externally visible LP states, but cannot distinguish high-speed operation from a sustained LP-00 reading or prove the high-speed electrical link is compliant. Probe loading is a real concern even though the input has high DC resistance.

### Cited Findings

- The LP8 specifies 2 MΩ in parallel with 10 pF per input, selectable nominal thresholds of 0.6, 0.9 and 1.65 V, 100 MHz maximum digital bandwidth, and 5 MHz maximum analog bandwidth. Eight digital channels without analog capture support 100 MS/s over USB 3.0; up to four digital channels without analog support 500 MS/s. The datasheet contains one inconsistent 400 MS/s example, but its specification table and Saleae's separate support article agree on 500 MS/s. — [Saleae datasheet, pp.3–4](https://downloads.saleae.com/specs/logic_pro_8_data_sheet.pdf), [maximum-rate restrictions](https://www.saleae.com/support/troubleshooting/capture-and-recording-issues/maximum-sample-rate-not-selectable)
- The threshold choice applies globally, not per channel. The UI's 1.2 V family selects an approximately 0.6 V comparator threshold; 1.8 V selects 0.9 V and 3.3 V selects 1.65 V. Saleae says precise thresholds are uncalibrated and can vary by ±15%. — [Saleae supported voltages](https://www.saleae.com/support/specifications-hardware/electrical-characteristics/supported-voltages)
- Automation uses `LogicDeviceConfiguration(digital_threshold_volts=1.2)`, **not** `0.6`. It supports explicit digital channel lists, sample rates, trigger capture, and raw exports. The API parameter represents the supported family choices 1.2, 1.8, 3.3 despite its name. Use `Manager.connect` to the existing backend, not `launch`; closing a launched manager shuts down its app. — [Saleae Automation API](https://saleae.github.io/logic2-automation/automation.html)
- LP signaling uses two independent, nominally 1.2 V single-ended wires and four states, LP-00, LP-01, LP-10, LP-11. HS signaling uses a small differential swing on those same wires. — [Tektronix D-PHY application note](https://www.tek.com/en/documents/application-note/tekexpress-software-and-mipi-physical-layer-and-protocol-layer-testing-0)
- The device's grounds are common to USB/PC ground, and each digital input is single-ended. — [Saleae datasheet, p.4](https://downloads.saleae.com/specs/logic_pro_8_data_sheet.pdf)

### Inferences

- A useful later capture would enable only CH1/PD0, CH2/PE0 and prospective CH6/DL1P, CH7/DL1N at 500 MS/s with analog disabled, family 1.2, and no glitch filters. Disabling the other existing channels for this capture requires no removal of their physical wires. Alternatively, eight digital channels at 100 MS/s retain reset/rails with 10 ns sampling. Validate the actual USB connection/rate before recording.
- At 500 MS/s a 50 ns interval has about 25 samples; at 100 MS/s about five. The previous 6.25 MS/s setup has 160 ns spacing and can miss an entire such transition. These are sample-spacing calculations, not an assertion that every actual sensor state lasts 50 ns or a guaranteed interchannel skew bound.
- Reading the pair as P then N is essential. Reversing the displayed order exchanges LP-01 and LP-10 and could falsely suggest a wrong sequence. The current 1.65 V threshold would miss nominal 1.2 V LP highs completely.
- High-speed voltages normally remain below the 0.6 V threshold, so both digital inputs may read zero during HS traffic. A digital `00` interval alone therefore cannot establish whether the transmitter stayed in LP-00, started HS, or was unpowered. The LP8's 5 MHz analog path is not a substitute for a scope when investigating short analog transitions.
- At the 402 MHz alternating-pattern frequency of an 804 Mb/s link, an ideal 10 pF capacitance has approximately 40 Ω reactance. This is only a loading illustration: actual flying leads add distributed inductance, capacitance and reflections. It explains why 2 MΩ DC impedance does not make a direct LP8 clip innocuous on this lane.
- If probes are eventually attached, use a controlled comparison: reproduce the unprobed error/image result, attach one matched pair with the shortest practical connections, repeat, then remove the pair and repeat. A changed error or corrupted frame after attachment is measurement disturbance evidence, not necessarily the original defect. A low-capacitance buffer at the lane could isolate an analyzer, but would be additional hardware requiring its own validation.
- Keep local ground returns short, shared only with board GND. Never attach a ground clip to the N signal wire. The lower global threshold also changes where existing rail traces count as digital high, so do not compare their digital crossing timestamps with previous 1.65 V-threshold captures as if thresholds matched.

### Gaps

- No calibrated channel-to-channel timing/skew guarantee was located; a same-signal check on the intended two inputs would bound gross skew before interpreting nanosecond ordering. It does not calibrate different edge slew rates on the real pair.
- Mixed analog/digital combinations depend on channel count and USB bandwidth. The proposed settings deliberately use digital-only modes whose rates are documented.
- No new physical attachment is recommended until exact accessible pads and polarity are confirmed. No claim is made that 10 pF probing will preserve this particular link.

## What would the available scope add?

### Takeaway

The DS1054Z can add useful voltage-level and LP-transition evidence, particularly slow startup ramps or asymmetric P/N edges. Its 50 MHz bandwidth and ordinary passive probes cannot establish the 804 Mb/s high-speed eye or D-PHY electrical compliance, and those probes may also alter the link.

### Cited Findings

- Rigol specifies DS1054Z bandwidth as 50 MHz; acquisition is up to 1 GS/s on one analog channel, 500 MS/s with two, and 250 MS/s with three/four. Published standard-probe names differ across document revisions: PVP2150 in one official datasheet and PVP3150 in another. Thus “standard probes” does not establish an exact probe or its input capacitance. — [Rigol current datasheet](https://www.rigol.com/dam/global/downloads/brochures/en/data-sheet/oscilloscopes/DS1000Z_DataSheet_EN.pdf), [Rigol alternate official datasheet](https://supportint.rigol.com/Public/Uploads/uploadfile/files/ftp/DS/%E6%89%8B%E5%86%8C/DS1000Z/EN/DS1000Z_Datasheet_EN.pdf)
- D-PHY probing must accommodate terminated differential HS operation and unterminated single-ended LP operation. Tektronix recommends high-impedance probes supporting both measurement modes and places active buffers close to the tips to minimize loading. — [Tektronix D-PHY test/probing guidance](https://www.tek.com/en/datasheet/d-phy-transmitter-test-receiver-and-protocol-solutions)

### Inferences

- For LP debugging, use two simultaneous single-ended channels, one per wire relative to GND, optionally a third existing software timing marker. Record sufficient pretrigger to precede the error callback, since callback time is not the exact electrical-transition time.
- A differential-only measurement yields approximately zero for both LP-11 and LP-00 and loses the common-mode information needed for this question. P and N separately, plus derived P−N and (P+N)/2 if desired, are more informative.
- A 50 MHz instrument has an approximate 7 ns rise-time limit using the simple 0.35/BW estimate, so it can help with tens-of-nanoseconds LP intervals but cannot establish subnanosecond edge quality. Sample rate alone does not overcome its analog bandwidth.
- If using passive probes later, identify their model first, use compensated 10× mode and very short ground springs, and repeat the same disturbance comparison as for the LP8. A high-resistance 10× probe still has tip capacitance. Do not use a 1× probe or direct 50 Ω termination on the lane as an assumed equivalent.
- The Analog Discovery 3 adds no necessary capability for the first software investigation. Its particular probe/interface configuration was not researched here; merely owning another instrument does not justify more wiring.

### Gaps

- Actual passive-probe model, tip capacitance, accessories and usable access geometry are unconfirmed. No scope commands or connections were attempted.

## Where is the affected pair, and what should happen before probing?

### Takeaway

Track **STM32 physical data lane 1**, not sensor labels by number alone: the sensor names its two lanes DATA1 and DATA2, while the MCU names them D0 and D1. The receiver-side observation point would be most direct, but final physical pin instructions remain unverified.

### Cited Findings

- CAM-6G3-073CLR schematic Rev2 identifies sensor DATA2P/DATA2N at module J1 pins 22/24, DATA1P/DATA1N at pins 10/12, and clock P/N at 16/18. The module is connected through its 30-pin interface, not directly to the Nucleo's 22-pin FFC. — [ST module schematic](https://www.st.com/resource/en/schematic_pack/cam-6g3-073clr-schematic.pdf)
- P-board PCB4280D schematic Rev1.1 traces `MIPI0_D2_P/N` from J2 pins 22/24 to J1 pins 18/17. `MIPI0_D1_P/N` run from J2 pins 10/12 to J1 pins 21/20. The explicit net metadata in the PDF supports this mapping. Its TP2/TP3/TP4 labels are GPIO3/4/5; they are **not** MIPI lane test points. — [ST P-board schematic, sheet2](https://www.st.com/resource/en/schematic_pack/steval-cam-m0i-schematic.pdf)
- Nucleo MB1940 C02 camera sheet names `CSI_D1_P/N`, passing through U15's common-mode filter to `_CON` nets and CN6. Therefore a connector-side observation is on the far side of U15 from the MCU receiver. — [ST MB1940 C02 schematic, sheet11](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf)

### Inferences

- First use documented software controls and logging with existing wires: preserve the first error, snapshot the exposed PHY status at initialization/START, and compare receiver-enable timing relative to sensor start. A repeatable state-dependent error may be explained without adding capacitance to the link.
- Do not equate logical lane mapping in the packet receiver with the physical error flag. Confirm the physical lane and any polarity controls from the MCU register definition before attributing the flag to a sensor-side name.
- If software evidence remains ambiguous, observe the affected pair plus a marker before considering other lanes. Compare receiver-side with connector-side only if needed to investigate U15/cable-related distortion.

### Gaps

- The complete MB1940 PDF is ~24 MB and exceeded the web fetch limit. Direct HTTPS downloads timed out or were reset, with no valid local file saved. The indexed rendering contains visibly duplicated/incorrect CN6 pin assignments, so those assignments must **not** be used for wiring. The filter/net names are corroborated, but pin numbering and physical left/right orientation still need a visible schematic and the actual board.
- No easily accessible MIPI test pad is established from these schematics. Fine-pitch connector solder tails or filter pads are candidates for inspection, not an instruction to clip or solder there. FFC contact orientation and board revision must be confirmed before translating either endpoint's numbering to a physical attachment.
