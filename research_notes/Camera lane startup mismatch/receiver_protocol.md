# STM32N6 receiver and D-PHY protocol contract

Research date: October 17, 2026. Offline source investigation only; no instrument access or firmware modification. Local RM0486 Rev 4 (May 2026) was read directly; live official PDFs were checked for DS14791 Rev 11 (September 2026), AN5967 Rev 6 (September 2026), and AN6211 Rev 1 (April 2025).

## What does the flag establish, and what is the expected wire sequence?

### Takeaway

The flag establishes a control-state-sequence error at the receiver, not its exact offending transition. The most productive measurement is simultaneous observation of both conductors of data lane 1, with clock activity and the firmware error timestamp as context. Calling it definitely a low-speed-only event is premature.

### Cited Findings

- STM32N6 references CSI-2 v1.3 and D-PHY v1.2; the receiver supports two data lanes. RM0486 §40.9.15 identifies ECTRLDL1F as SR1 bit 12, distinct from SoT, escape-entry and LP-data synchronization errors. SR1 also exposes live clock/stop/HS-active states; FCR1 acknowledges sticky errors. — [RM0486, pp. 2015, 2060–2063](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), [DS14791 Rev 11, p. 51](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf).
- AMD's public PPI description gives an explicit ErrControl example: an escape/turnaround request returning to Stop without the intervening Bridge state. The interface error persists until another line-state change; this is generic PPI corroboration, not a list of all STM32 trigger conditions. — [AMD PG435 PPI signals, Dl<n>_errcontrol](https://docs.amd.com/r/en-US/pg435-mipi-rx-phy/PPI-Signals).
- Expected control states, written as `(Dp,Dn)`, are `11` Stop, `01` HS-request, `00` Bridge, and `10` LP-request. Normal data-burst entry is `11 → 01 → 00 → HS-0 → synchronization → data`. Clock entry precedes data entry. Crucially, the LP detector sees `00` during real HS traffic too. — [NXP AN13573 Rev 1.1, pp. 4–9](https://www.nxp.com/docs/en/application-note/AN13573.pdf).
- MIPI states explicitly that the full D-PHY specification is member-only; previous versions are also in the member library. Current public overview lists v3.6, which is not the version named by this STM32. No unofficial specification mirror was used as a normative source. — [MIPI D-PHY specification access](https://www.mipi.org/specifications/d-phy).

### Inferences

- A measured `11 → 10 → 11` startup excursion would be a concrete candidate matching the published control-error example. It has **not** been observed on our board.
- A logic-only `00` interval cannot prove that the transmitter remains in LP mode. A missed HS-request, genuine HS activity, an unpowered line, or a valid Bridge interval can all look low to LP-level thresholds. Scope evidence is needed to separate them.
- Our saved SR1 `0x76181000` contains ECTRL lane 1 and Stop on clock/both data lanes. That says where the link settled when sampled, not which edge caused the error. The callback timestamp is later than hardware detection by interrupt latency. — [Local measured event analysis](../../firmware/capture-timing/csi-startup-errors.md).

### Gaps

- RM0486 does not publish the internal lane-state machine or a complete transition-to-error truth table. Public material cannot identify the exact mismatch from the flag alone.
- No full licensed MIPI v1.2 text was available for a formal compliance analysis. Public manufacturer summaries support a diagnostic plan, not a compliance certificate.

## Which timing and configuration constraints can we check?

### Takeaway

Check actual lane state and PHY clock activity around initialization; sensor START timing alone does not establish either. The relevant LP transitions are tens of nanoseconds, despite “low power” terminology.

### Cited Findings

- RM0486 §40.6.2 requires lane-merger mapping/count changes with CSIEN=0 and D-PHY_RX not supplying a clock. HSFR is static while powered down; CCFR is derived from the PHY configuration clock. ACTCLF reports received HS clock activity. — [RM0486, pp. 2032–2033, 2060, 2068](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf).
- The pinned HAL writes LMCFGR before its later PHY reset/disable, enables error interrupts, programs the PHY and releases it. Its source comments and RM disagree on DLD polarity; existing ST clarification supports retaining the working HAL setting. — [ST HAL source](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/d88071ed0adc1991a5daed6f20ab311f80bb33b7/Src/stm32n6xx_hal_dcmipp.c), [ST DLD clarification](https://community.st.com/stm32-mcus-products-25/csi-pfcr-dld-bit-description-contradicts-hal-implementation-167440).
- Public D-PHY timing guidance gives TLPX ≥50 ns, THS-PREPARE 40+4UI to 85+6UI, and receiver THS-SETTLE 85+6UI to 145+10UI. At 804 Mbps, UI=1.24378 ns: preparation ≈44.98–92.46 ns; settling ≈92.46–157.44 ns. Generic LP voltages are high 1.1–1.3 V, VIH minimum 0.88 V, VIL maximum 0.55 V. These are not separately characterized STM32 electrical limits. — [NXP AN13573, pp. 5, 8–9](https://www.nxp.com/docs/en/application-note/AN13573.pdf).
- TI documents a 100 µs initialization interval for its CSI transmitter. That corroborates the scale of conventional D-PHY initialization but does not establish the STM32's exact internal qualification duration or a required new 100 µs software delay. — [TI DS90UB638-Q1 datasheet, §6.7 p. 15](https://www.ti.com/lit/ds/symlink/ds90ub638-q1.pdf).
- AN5967 requires 200 Ω ±1% at CSI_REXT and recommends 100 Ω differential routing. AN6211 illustrates separate camera transmitter, D-PHY receiver and host stages. Neither supplies a cure for the present flag. — [AN5967 Rev 6, §13.5](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf), [AN6211 Rev 1, §2.3.2](https://www.st.com/resource/en/application_note/an6211-introduction-to-digital-camera-interface-pixel-pipeline-for-stm32-mcus-stmicroelectronics.pdf).

### Inferences

- Distinguish four clocks: sensor input reference, STM32 PHY configuration clock, differential camera clock lane, and receiver-derived internal byte clock. The merger restriction concerns the D-PHY_RX delivery into the host, not a requirement to stop the MCU's configuration clock.
- In a genuinely reset PHY, the merger write may be valid even after the sensor received START. Instrument PRCR/PCR/CR and ACTCLF around the write before asserting a violation. A single ACTCLF=0 sample alone cannot exclude earlier activity.
- Existing 6.25 MS/s captures have 160 ns sample spacing, insufficient for a 50 ns LP-request. Faster acquisition is necessary; a high-resolution digital capture still does not qualify analog levels or distinguish HS from LP-00.
- In the selected run, receiver completion at 21.22256 ms precedes callback 22.97216 ms by ~1.750 ms. This argues against merely adding a blind 100 µs delay; it does not show how long valid LP-11 existed. — [Local results](../../firmware/capture-timing/optimization-results-2026-10-17.md).

### Gaps

- No dedicated STM32 CSI pad-threshold/timing table was found in current DS14791. Its 0.8925 V threshold belongs to **UCPD**, not CSI.
- No public N6-specific complete HSFR/internal test-register timing table or explicit T_INIT qualification behavior was recovered. Do not invent register writes or transplant another SoC's timing knobs.

## Which experiment would discriminate the mismatch without hiding errors?

### Takeaway

First collect raw error history and a physical waveform around the error; then vary only receiver release timing. Preserve the first frame and its integrity evidence for every comparison.

### Cited Findings

- Our original ST-based capture already reported the same error class with receiver-before-START sequencing; the optimized firmware localizes lane 1 before exposure. Correcting E2/E3, CCFR and clock mode did not remove it. Corrected HAL disables each error source after its first callback, so silence afterward is not evidence of no recurrence. — [Local CSI investigation](../../firmware/capture-timing/csi-startup-errors.md), [recorded experiments](../../firmware/capture-timing/experiments.md).
- The existing wrapper snapshots SR0/SR1/IER0/IER1 before invoking HAL. It can be extended without discarding this history. — [capture.c](../../firmware/capture-timing/capture.c).

### Inferences

The following are proposed tests, **not completed experiments or conclusions**:

| Candidate | Discriminating observation | What weakens it |
| --- | --- | --- |
| Transmitter emits a startup LP control excursion | Both lane-1 conductors show an invalid sequence tied consistently to START, before exposure | Valid well-timed states at MCU pins while raw flag asserts |
| Receiver wakes mid-transition or lacks qualified Stop | Moving PHY release changes occurrence; enabling after a measured stable Stop avoids it while still capturing frame one | Event remains fixed to transmitter action with receiver already stable |
| Polarity/mapping takes effect during transmitter startup | First excursion differs from later valid bursts or changes with a documented mapping sequence | Mapping already stable, no anomalous polarity on startup waveform |
| Merger configured while receiver supplies clock | ACTCLF/clock trace active at LMCFGR write; configuring while PHY held disabled resolves it | No delivered clock then, same flag persists with unequivocally static setup |
| Analog skew/ringing or probe loading | Unequal threshold crossings, droop, or count changes when probe is attached | Repeatable violation on unloaded equivalent point or clean low-capacitance analog capture |
| Persistent lane problem beyond startup | Additional raw flags during first image; CRC/ECC or packet losses correlate | Only bounded startup/stop events with clean frame transport |

Suggested diagnostic mechanics: add timestamped register snapshots at before/after LMCFGR, PHY release, sensor START and first IRQ; preserve instantaneous raw status before clear. In a separate bounded diagnostic mode, re-enable only recorded ECTRL sources after HAL acknowledges them, retain counters plus a small fixed ring buffer, and cap callbacks/time. On overflow, latch an explicit overflow flag and mask further interrupts to prevent a storm. Sample raw status again at first frame and stop. Do not treat count=1 under masking as success. A GPIO marker at IRQ entry gives the scope a trigger, but the pre-trigger window must cover the physical transition and ISR latency.

### Gaps

- The scope model, available probes, and physical connection access determine the measurement setup; this note does not authorize attaching a high-capacitance probe or changing the bench wiring.
- LP8 voltage threshold, loading and channel-rate constraints are covered by the separate instrumentation investigation.
