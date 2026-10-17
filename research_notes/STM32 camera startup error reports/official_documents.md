# Official ST documentation: CSI D-PHY startup control errors

Research date: October 17, 2026. Read-only investigation; no hardware access, firmware changes, or outreach. Sources below are manufacturer documents. Forum statements are covered by the other researcher and should be distinguished from formal errata.

## Is this a documented STM32N6 silicon erratum or a formally benign startup event?

### Takeaway

No matching CSI/D-PHY erratum or formal benign-startup declaration was found in the current official documents inspected. That is a bounded negative result, not proof that ST has no internal knowledge of the condition.

### Cited Findings

- The current **ES0620 Rev 5, August 2026**, PDF has 38 pages. Its revision history dates Rev 5 to **August 7, 2026** and identifies addition of silicon revision X. Neither its complete searchable text nor its limitation summary contains a CSI or D-PHY entry. The DCMIPP/VENC desynchronization limitation is a different issue. Some search snippets still show Rev 3; those are stale relative to the opened PDF. — [ES0620 official PDF](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf), summary pp. 2–5, revision history p. 33.
- **AN6211 Rev 1, April 2025**, describes normal low-power/start-of-transmission/packet/end-of-transmission transitions and separates header ECC from payload CRC checking. Its CSI overview and packet discussion do not describe ECTRL, a startup control-error exception, or a recovery workaround. Full-text searches for startup and incorrect returned no hits. — [AN6211 official PDF](https://www.st.com/resource/en/application_note/an6211-introduction-to-digital-camera-interface-pixel-pipeline-for-stm32-mcus-stmicroelectronics.pdf), §2.6.4 pp. 12–13.
- **AN5967 Rev 6, September 2026**, is newer than the repository's Rev 5. Revision history dates it September 11. Camera hardware guidance includes CSI_REXT's 200-ohm 1% resistor and differential routing requirements, but the camera section contains no startup ECTRL exception or software workaround. The Rev 6 history identifies power and I/O updates rather than a CSI startup fix. — [AN5967 official PDF](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf), §13.5 pp. 35–36, Table 14, revision history p. 46.

### Inferences

- Good frames and clean observed payload flags remain relevant experimental evidence, but these documents alone do not justify suppressing the control-error history or declaring the condition harmless.

### Gaps

- No formal ST document recovered that explicitly says an ECTRLDL1F event during VD56G3 startup can be ignored.
- No official timing diagram recovered identifying the precise transmitter transition that causes our event.
- This search did not inspect private support material or the licensed complete MIPI specifications.

## What exactly does RM0486 require during receiver setup?

### Takeaway

The relevant explicit sequencing restriction applies to **lane-merger configuration**, not simply to when the host enables its PHY relative to sensor START. Whether our optimized timing satisfies it depends on the actual receiver clock activity during those register writes, which has not been measured.

### Cited Findings

- **RM0486 Rev 4, May 2026**, §40.9.15 p. 2061: ECTRLDL1F/0F are lane-sequence flags at bits 12/4, distinct from SOT/escape/LP-sync errors; §40.9.17 assigns write-one acknowledgment to FCR1. — [RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf).
- §40.6.2 p. 2033: configuring DL0MAP, DL1MAP and LANENB requires CSIEN=0 and inactive D-PHY_RX clocking. LLP steps 5–7 then enable interrupts, lanes and virtual-channel reception. — [RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf).
- ST's current preliminary reference-manual update index still identifies RM0486 Rev 4 (May 2026); its listed N6 updates concern other topics, rather than a startup control-error exception. — [ST reference-manual preliminary updates](https://community.st.com/stm32-mcus-60/stm32-mcu-reference-manuals-expected-preliminary-updates-128416).

### Inferences

- Command timing alone does not establish electrical-clock state or compliance.
- The original receiver-first smoke test also reported the same control-error class, so optimized overlap alone cannot explain the entire historical observation.
- Follow the separate ST forum clarification concerning CSI_PFCR.DLD rather than mechanically applying the contradictory RM wording. This document review does not recommend changing DLD.

### Gaps

- The public RM does not provide a specific ECTRL cause tree or a documented reset/clear sequence that repairs this startup event.
- RM PDF retrieval through the web tool failed on this pass; its exact passages were checked against the repository's preserved official Rev 4 PDF text and source record. The live ST update index independently confirms that revision remains referenced. No claim is made to have redownloaded the 98 MB PDF.

## What does the VD56G3 documentation say about transmitter startup?

### Takeaway

The sensor manual specifies command states and configuration timing, but it does not expose enough electrical detail to identify the lane transition responsible for the MCU flag.

### Cited Findings

- **UM2602 Rev 8, April 2024**, revision date April 17: §5 p. 7 requires sensor supplies and input clock before releasing XSHUTDOWN, then transition through READY_TO_BOOT and SW_STANDBY before streaming. — [UM2602 official PDF](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf).
- §16 pp. 41–42 places bitrate setup and output-interface configuration in SW_STANDBY. Continuous clock is the default; DPHYTX_CTRL changes from 0x1C to 0x0C to request non-continuous clock, with low-power clock state between frames. Lane mapping/polarity and lane count are output-interface configuration fields. — [UM2602 official PDF](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf).
- §9 pp. 11–12 lists the sensor's own output-interface errors, including CSI_LANE_DESYNC_ERROR. Those are sensor ERROR_CODE values, not the STM32 receiver's ECTRLDL1F flag. — [UM2602 official PDF](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf).

### Inferences

- Continuous versus non-continuous clock is a legitimate experiment knob, but the manual does not promise that it changes startup control errors. Our already-recorded experiment is stronger evidence about this particular board than speculation from the setting name.

### Gaps

- No exact LP-11/LP-01/LP-00 sequence and duration throughout START_STREAM was found in UM2602.
- No statement tying the VD56G3's lane mapping/polarity update to a temporary invalid receiver state was found.
- Direct HTTPS download attempts for UM2602, AN6211 and AN5967 timed out with certificate verification enabled. Their official PDF contents were successfully read using the web tool; no browser download or Save As dialog was initiated.
