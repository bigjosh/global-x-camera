# SD protocol and performance review — 2026-10-26

Review and final lower-clock hardware verification completed October 26.
Start with the [review summary](REVIEW-SUMMARY.md) for changes, measurements
and remaining 50 MHz work. The chronological experiments below preserve
their original scope; the final installed profile and live handoff are in
[the firmware README](../../README.md) and [bench checkpoint](../../../../AGENTS.md).

The [final cold qualification](FINAL-QUALIFICATION.md) covers the installed
startup/no-tail firmware, complete saved-image comparisons and recovery.
The separate [final Standby wire verification](FINAL-STANDBY-WIRE.md) passed
all 3,730 packets and 14,920 lane CRCs, with complete wire-to-SD equality and
the final CMD12 busy interval measured. The original camera RAM was lost for
that Standby trial; cold awake slot27 separately passed original-RAM equality.

## Qualified 12.5 MHz phase baseline

Explicit four-bit 12.5 MHz, falling-edge host launch during both100 kHz identification and fast transfers; SELCLKRX=00 internal-feedback rising-edge reception unchanged. GPIO speed3, existing27-ohm midpoint CLK resistor, all six SD probes attached. No card erase.

One cold awake flash capture saved slot18 (LBA67140,3,730sectors). All3,730 write packets passed every lane CRC and received accepted status. Independent raw-edge reconstruction of the complete1,909,760-byte slot matched GXR2 +152zero metadata bytes + original1,909,600-byte camera frame + GXRE. Full subsequent SD readback also matched every original camera byte. Independent PNG decoding and visible patterned scene inspection passed. UART recovery passed first attempt before installation and after capture (nine good pulses, zero bad).

[Wire measurements](phase125-wire.json), [capture proof](phase125-capture.json), [readback](phase125-readback.json), [scene](phase125-scene.png), [historical byte-identity controls](phase125-build-identities.json), [prefix admission](phase125-recovery-admission.json).

127 valid identification commands and77 fast commands were observed. Host CMD changes cluster at CLK falling (median0ns, ±4ns acquisition/skew resolution); fast data transitions likewise cluster near falling. Clock period median80ns, quantized76–84ns at250MS/s. The receiver's sampling selection is established by configuration and successful readbacks, not directly visible as an internal latch edge. The decoder's known initial phantomCMD63 is an acquisition/startup artifact; all actual transactions decoded without CRC errors at sample offset0. Digital observations do not establish analog voltage/setup/hold margins or production/PVT reliability.

Private complete files: `tmp/bringup/sd125-negedge-20261026/`, including `cold01/signals.sal`, binary exports, `decoded/sd-analyzed.sal`, full camera/slot bytes and physical NOR readbacks. Independent64KiB NOR readback matched awake sector `c85907d0c29da1bfa6905734b65f7af3a73a73db70d1f2186065405a5aeb467f`; following4KiB unchanged. Awake proof is not a Standby or energy qualification.

### Separate 12.5 MHz Standby cycle

The matching Standby build subsequently saved slot19, LBA70870. Independent raw-edge reconstruction verified all3,730 packets,14,920 lane CRC16 values,3,730 accepted status tokens and every start/end bit. All1,909,760 wire bytes exactly match the complete subsequently retrieved SD slot, SHA256 `5a4805fd675182529c677c7b2de26c1bb068ab6344a20ce454fce964acbcb166`. GXR2,152zero metadata bytes and GXRE are present. PNG decoding matches the retrieved RAW samples, and visual inspection confirms a recognizable patterned scene. **Original camera RAM was lost in Standby**, so this is wire-to-SD equality, not another original-camera-RAM comparison.

| Measured SD interval | Time |
| --- | ---: |
| CMD0 start to first final READY response end | 562.414284 ms |
| CMD25 start to first final READY response end | 336.109944 ms |
| First data packet start to last packet end, including interpacket intervals | 333.899148 ms |
| Sum of decoded data-packet spans | 312.482992 ms |
| Sum of exposed per-block DAT0 busy intervals | 16.616684 ms |
| Final CMD12 DAT0 busy | 1.921900 ms |

These boundaries are relative to the saved logic capture, not power-good/reset. Packet spans include start/CRC/end sampling boundaries; exposed busy is not isolated card-internal programming time. The rows are overlapping/different boundaries and must not all be added together. This run has no total-cycle energy integration. CMD transitions again cluster on falling edges (median0ns), and payload clock periods have median80ns with76–84ns acquisition quantization. Only the known pre-CMD0 phantomCMD63 annotation is invalid; actual transactions pass.

The exact64KiB NOR readback matches Standby sector `4762bbe49e5d48bba5869892f327b8871fccaf8f543cde550ab7858252949945`, prefix `d5f17279640f5acd9642a28fa0df11bddf1825a2b9d06432908ef4a460204c60`; the following4KiB remains unchanged. Warm UART recovery reached the exact park with nine valid pulses and zero bad pulses. The standalone guarded PWR read observed SBF=1/PDDS=1/STOPF=0 without a new reset/power change, but explicitly reports `trial_entry_proven=false`; preserve that attribution limit. The cold-cycle low-current observation was4.892288V/8.192636mA, which is not an energy measurement.

[Wire/timing proof](phase125-standby-wire.json), [full readback](phase125-standby-readback.json), [NOR/recovery/Standby observation](phase125-standby.json), [retrieved scene](phase125-standby-scene.png). Private replay script: `tmp/bringup/sd125-negedge-20261026/check_standby_waveform.py`; source files are `cold-standby/binary/`, `decoded-standby/sd-all-events.csv` and `slot19/slot.bin`. This subsection records the completed test and does not declare the later live bench state.

## Review scope

Protocol/timing correctness, unnecessary work, ordering and overlap; goal is reliable50MHz after actual high-speed negotiation and exact clock generation. Existing150MHz/integer divider cannot generate50MHz: truncating150/(2×50) would incorrectly select75MHz. New profile must establish a100MHz kernel without changing CPU/camera/NOR clocks, then CMD6 check/switch High Speed before exceeding25MHz. Legacy binary identities and autonomous recovery must remain preserved. Findings and qualification will be appended as work proceeds.

## 50 MHz investigation — initial results, not qualified

The reviewed profile successfully negotiated native3.3V High Speed with CMD6 check/switch, used a100MHz kernel/CLKDIV1, and restored the original clock topology after each completed operation. The card reported200mA maximum current in its switch status. Final host launch uses the High Speed datasheet's post-rising phase; identification/intermediate25MHz retain falling launch. CPU/camera/NOR clocks remain unchanged.

| Trial | Observed result |
| --- | --- |
| Uniform GPIO speed3, one-sector read | Passed, identical to the prior12.5MHz reference |
| Uniform speed3, complete slot19 read | All1,909,760bytes identical to the prior12.5MHz reference |
| Uniform speed3, pattern capture/write slot20 | Completed, one CMD25, no reported write error; complete subsequent12.5MHz readback matched every original camera byte |
| Uniform speed3, slot20 sustained50MHz read | Failed DCRCFAIL during CMD18 after64 successful sectors in the failing512-sector request;1625 words received in the failing transfer |
| Same50MHz read repeated with waveform capture | Failed DCRCFAIL after64 sectors, this time4281 words; failure point moved |
| DS mixed slew: CLK speed1, CMD/DAT speed0 | Initial262,144-byte read matched exactly; subsequent full-image stress failed DCRCFAIL after320 successful sectors in the failing512-sector request |

All three read failures preserved their original error, aborted the data transaction, reached fresh card/controller readiness and restored IC5/mux ownership. Read-only SRAM/RCC snapshots confirmed cleanup; a failed read was never accepted as a successful image or used as a normal success admission. The independent12.5MHz read of slot20 confirms its saved data is intact. These results reject both tested slew profiles as reliable50MHz configurations at this stage.

Private evidence is under `tmp/bringup/sd50-reviewed-20261026/`: `read-slot19`, `pattern01`, `pattern125-readback`, `pattern01-read-failure`, `read-repeat-failure`, `mixed-read` and `mixed-stress-failure`. The installed NOR remains the verified12.5MHz Standby build above;50MHz flash candidates are offline only. No card erase occurred.

[Offline recovery admission](hs50-offline-recovery-admission.json) proves the two initial50MHz candidate prefix/sector pairs preserve all20 recovery literals,1,774 listing rows and the15,804-byte early load, changing only the two reviewed CRC words. Both strict admission functions and the8 recovery-park/14 readback tests passed. This is identity validation for recovery, **not authorization to install or a qualification of50MHz**; neither candidate was promoted.

### Independent saved-waveform comparison

[Raw-edge comparison](hs50-wire-comparison.json) independently reconstructs the saved250MS/s traces against the complete12.5MHz slot20 reference. [Failure snapshots](hs50-read-failures.json) retain the original hardware errors and separate cleanup proofs. Full frames and captures remain private; source hashes and relative replay paths are retained.

| Observation | Uniform speed3 repeat | CLK speed1 / CMD-DAT speed0 initial read |
| --- | ---: | ---: |
| Observed512-byte wire packets, including card overrun after requested count | 116 | 649 |
| Captured4ns high CLK intervals within those packets | 959 | 3,737 |
| Such intervals per1,000 observed packet clocks | 7.94 | 5.53 |
| Same comparison restricted to first64 requested packets | 569 / 8.54 per1,000 | 413 / 6.20 per1,000 |
| Median host CMD transition after previous rising CLK edge | 4ns | 4ns |
| Host commands reconstructed with matching CRC/argument at+12ns | 10/10 | 34/34 |

The active clock period has a20ns median with4ns acquisition quantization; clock pauses are counted separately and are not labeled defects. The measured reduction in short captured intervals does **not** establish that slew caused the CRC change or fixed the link. Both configurations subsequently failed a real MCU read. A logic trace cannot determine analog ringing, threshold excursions, setup/hold margin or the MCU's exact internal latch event.

No tested fixed data-sampling offset makes either complete trace CRC-clean. Even the first64 packets, which the MCU accepted in both trials, have analyzer discrepancies. At the best tested offset for that subset, only41/64 packets reconstruct with all four lane CRCs in each trace. Consequently analyzer CRC counts must not be reported as hardware read failures. The+12ns position reliably reconstructs these observed host commands, but is not a universal data sampling solution. Offline offsets do not modify the firmware's receive timing.

The repeat MCU failure after4,281 words lies within the34th block of its secondCMD18 (LBA75721). That block is byte-exact and all-lane CRC-correct when independently sampled at the external rising edge; the+12ns decoder instead reports errors. The following block shows a larger nibble displacement after the hardware failure may already have begun. It may include abort-side effects, so neither observation identifies the physical root cause. The first uniform-slew failure occurred at1,625words and the later mixed-slew stress failure at569words after320 completed sectors, further rejecting a fixed saved-data corruption explanation.

All three snapshots preserve error14/DCRCFAIL atCMD18 (`STA=0x9002`), then show `media_idle=1`, `initialized=0`, `controller_owned=0`, `cleanup_error=0`, clock-profile state5 and the restored SD mux. This is successful bounded cleanup of failed reads, not successful image retrieval. The archive scripts are `tmp/bringup/sd50-reviewed-20261026/analyze_repeat.py` and `archive_read_comparison.py`; neither accesses live instruments.

### Fixed-compensation follow-up failures

Two additional root-owned50MHz PIO-read trials also failed and are retained in the [failure snapshot archive](hs50-read-failures.json):

| Electrical profile | Completed sectors in the failing request | Words received in the failing CMD18 |
| --- | ---: | ---: |
| Uniform speed3 plus fixed VDDIO5 compensation | 0 | 6,009 |
| Mixed slew plus the same fixed compensation | 128 | 7,257 |

Both snapshots show the fixed compensation register changed from`0x78` to`0x287` with the required supply-valid and clock/reset prerequisites recorded. Both preserve error14/DCRCFAIL (`STA=0x9002`), `media_idle=1`, `initialized=0`, `controller_owned=0`, `cleanup_error=0`, clock-profile state5 and the restored SD mux. The original read failures remain failures despite clean recovery. These trials do not qualify either electrical profile or show that the previous saved image is corrupt; the separate12.5MHz full-slot comparison remains the saved-data integrity evidence. No50MHz flash candidate was promoted. Private sources are `comp-read-failure/snapshot.json` and `combined-read-failure/snapshot.json` under the same experiment directory.

### Receive-IDMA follow-up

The isolated50MHz/fixed-compensation IDMA READ of512 sectors fromLBA75624 also failed its firstCMD18 with DCRCFAIL (`STA=0x81002`). It preserved error14 and completed bounded abort, card/controller readiness, deinitialization and clock restoration. The retained `transfer_words=0` is an unavailable progress count on this IDMA failure path, **not evidence that zero bytes reached memory**. The [failure archive](hs50-read-failures.json) includes the original snapshot.

The [independent IDMA waveform reconstruction](hs50-idma-read-wire.json) finds339 complete externally observed packets before the abort. From the first packet to the last, CLK periods are16/20/24ns at250MS/s, with no intervals above100ns: the long CPU-fed receive pauses seen in the PIO traces are absent. There are still2,019 captured4ns high intervals within those packet windows, approximately5.72 per1,000 packet clocks. Removing the PIO pauses did not make this link reliable.

CMD18 begins at7.659251236s and abortCMD12 at7.666776300s in the saved capture. The last complete packet,339/LBA75962, ends at7.666762680s. All tested sampling offsets show a nibble displacement near its final bytes, beginning aroundbyte506, but this is only an external disruption location. No single fixed offset correctly reconstructs every earlier packet either, and the MCU's exact first failing sample was not recorded. The trace therefore cannot establish an analog cause or equate analyzer CRC errors with MCU errors. Private replay source: `idma-read-wire/binary/`; offline script: `analyze_idma_read.py`.

[Independent diagnostic admission](diagnostic-admission.json) checks the exact frozen50MHz IDMA READ build,50MHz tail-wait capture build and12.5MHz tail-wait fallback. READ/capture operations remain separate, format and opposite operations are rejected, and neither diagnostic permits flash/Standby admission. Nine host-admission/tail-helper tests passed independently. These software checks do not supersede the failed hardware read.

### Successful50MHz tail-wait capture, verified by12.5MHz readback

One RAM-awake scene capture with fixed compensation saved slot21, LBA78330. The validated FRAME initially lacked only its final sector because sensor STOP was pending. The bounded tail helper waited5.521150ms, normal publication then released the final sector, and the transport selected complete-buffer IDMA. No trailer, STOP or guard check was bypassed. The interval from the first-write marker before the SD call to returned payload completion was89.281515ms at the qualified400MHz CPU clock.

Full subsequent12.5MHz SD readback matched all1,909,600 original camera-RAM bytes, with GXR2,152zero metadata bytes and GXRE intact. Independent archive checks compared the actual source, retrieved frame and slot payload directly; all are identical. The source-frame SHA256 is`72a73248fd00a2116dd2cb082d51333e52bf55496097c5c1c1c80401c632e3a7`; full-slot SHA256 is`801a16435a4ee6fe97203ebe2a40ac4e151bfe423bac1309f6c698c953a5a654`. PNG decoding matches the retrieved RAW samples, and independent visual inspection shows the recognizable illuminated triangular lattice/panel and surrounding structure.

[Bounded outcome/timings](tail50-outcome.json), [capture/ownership proof](tail50-capture.json), [full readback proof](tail50-readback.json), [retrieved scene](tail50-scene.png). The earlier approximately205ms PIO result used a different pattern/scene and electrical configuration, so these measurements do not isolate the tail helper's speedup. No total-cycle energy or cold/Standby qualification was performed for this trial. This is a successful50MHz **write** with12.5MHz verification; the preceding failed50MHz reads remain unresolved and no50MHz flash build was promoted.
