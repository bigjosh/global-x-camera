# Prototype hardware decisions and constraints

## 2026-10-13  Select the 73-degree VD56G3 module and defer custom VD5943 optics

**Why:** CAM-6G3-073CLR provides monochrome global-shutter capture with fitted 73° diagonal optics in a published 4.68 mm module. It avoids making custom optics a prerequisite for the functional prototype. The higher-resolution VD5943 remains a future direction, but stock modules are much taller and no qualified near-73°, under-5-mm fitted assembly was found.
**Rejected:** silently retaining the recovered CAM-5G0-079CLR selection, substituting the 84° VD56G3 module, or treating a compact lens catalog's optical TTL as complete module thickness/compatibility. The complete camera still needs a ≤5 mm stackup review.
**Evidence:** [camera/module and optics research](prototype-parts-and-camera-research.md); [D-02 and FD-01](../decisions/2026-10-13-project-baseline.md); commit `cf9302c9`.
**Provenance:** reconstructed from explicit user selection in review transcript message 020 and dated manufacturer research. No quantity-500 supplier allocation is established by small-stock observations.

## 2026-10-14  Build the first prototype by hand on Nucleo and defer factory selection

**Why:** the user chose to assemble the NUCLEO-N657X0-Q prototype personally before selecting a custom-board manufacturer. This keeps current bring-up independent of production BOM, stackup, sourcing and assembly decisions.
**Rejected:** promoting the earlier JLCPCB Standard recommendation or PCBWay fallback into an approved factory/order; requiring production PCB fabrication before a functional camera. Manufacturing selection is deferred until the custom-board design is ready to qualify.
**Evidence:** [D-35](../decisions/2026-10-13-project-baseline.md); [historical PCBA feasibility](../manufacturing/china-pcba-feasibility.md); commit `73fe5a31`.
**Provenance:** reconstructed from the explicit user instruction recorded with D-35. Prior manufacturing research establishes feasibility leads, not a purchase or supplier commitment.

## 2026-10-14  Defer photographic flash until ambient-light images justify it

**Why:** the user selected ambient light for the first prototype and retained photographic flash as future work. The earlier flash-specific battery/brightness discussion did not select a camera power replacement or a ready circuit; working distance, pulse energy, recharge, thickness and timing depend on actual image needs.
**Rejected:** including xenon/chemical/LED flash hardware or the separate AA-cell proposals in the current prototype BOM. Status LEDs are unaffected.
**Evidence:** [D-34 and FD-06](../decisions/2026-10-13-project-baseline.md); [earlier flash discussion](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/6a887bc5-aa48-83ea-bda2-31a0fa35fd91.md); commit `b45283b5`.
**Provenance:** reconstructed from explicit user deferral and the preserved related-project discussion; no unrecorded rejection of future flash is inferred.

## 2026-10-15  Start with manual exponential exposure and fixed unity gains

**Why:** the user selected a potentiometer sampled by the ADC before acquisition, with fixed analog/digital 1× gains and an exponential exposure range from the fastest supported setting to one second. Finer adjustment at the short end is intentional; the actual camera will determine the tuned curve.
**Rejected:** a linear exposure mapping or an implicit automatic-gain/exposure algorithm for this starting point. Exact potentiometer, ADC interface and calibrated mapping remain deferred to hardware testing; settling/configuration time belongs in the exposure-start budget.
**Evidence:** [D-36, D-38 and D-39](../decisions/2026-10-13-project-baseline.md); commits `b3ac8292`, `5cf7aae8`.
**Provenance:** reconstructed from explicit user choices on October 14–15; the note dates the final curve/gain selection. It does not claim the potentiometer is implemented in current fixed-exposure bench firmware.

## 2026-10-17  Choose the existing Alliance NAND over a smaller convenience board

**Why:** the user selected AS5F14G04SND-10LIN for the NAND path. Its 4 Gbit capacity is a closer fit to the ≥200-photo requirement; Flash 5 Click's fitted 1 Gbit W25N01GV is convenient for commands but cannot hold that many full-resolution photos. Choosing the existing Alliance avoids a later device port if a compatible carrier is available.
**Rejected:** treating the Click board as the same NAND or as sufficient final capacity; promoting historical Micron/Winbond/parallel recommendations into a new part selection. Exact production device and retention qualification remain open.
**Evidence:** [selection and alternatives](alliance-nand-wiring.md); [procurement context](prototype-parts-and-camera-research.md); commits `c0e316e7`, `dd97c945`.
**Provenance:** reconstructed from explicit user choice and exact fitted-part comparison. The later SD prototype does not retroactively qualify Alliance NAND operation.

## 2026-10-18  Prefer Arduino convenience over hardware quad for the deferred NAND assembly

**Why:** after considering hardware quad options, the user made the final choice to use the existing Alliance NAND on Arduino headers, allowing bit-banging. VDDIO4 can be isolated to 1.8 V; the separate CN16 hardware XSPI port is on stock 3.3 V VDDIO2 without a simple isolation link. Sharing the 1.8 V boot-NOR bus would add fine solder taps, loading and boot-recovery risk.
**Rejected:** describing Arduino quad GPIO as hardware QSPI/DMA; combining the old CN3/VDDIO5 map with VDDIO4 rework; unqualified VDDIO2 cuts or silent boot-bus sharing. The physical convenience knowingly trades off throughput.
**Evidence:** [final mapping and hardware alternatives](alliance-nand-wiring.md); [assembly guide](nucleo-assembly-guide.md); commits `921a4a6b`, `dc423503`, `d6e28a9c`.
**Provenance:** reconstructed from the final explicit choice superseding the earlier hardware-quad preference. October 19 confirmed the banks still at 3.3 V; this remains a deferred NAND plan, not performed rework.

## 2026-10-18  Repurpose Arduino AREF only after isolating it and the NAND bank

**Why:** the user preferred all NAND connections on Arduino headers, so CN14.8/AREF became the canonical 1.8 V VCC contact fed from CN3.10/VDDIO4. R125 must remain absent to isolate VREFP; SB24 and the 3.3 V pull-ups R88/R89 must be removed before feeding the bank at 1.8 V. PA3 remains a main-domain output and must use open-drain CS with a 1.8 V pull-up.
**Rejected:** a separate direct CN12.14-to-NAND lead as the canonical plan; applying 1.8 V without removing 3.3 V paths; driving CS push-pull high; attaching a 3.3 V shield to the converted bank.
**Evidence:** [canonical Arduino wiring](alliance-nand-wiring.md#selected-arduino-header-bit-bang-mapping); commit `aedefb74`.
**Provenance:** reconstructed from explicit user wiring preference and the reviewed board connections. This conditional NAND-only plan must not be applied to the active 3.3 V SD setup.

## 2026-10-18  Do not assume the Alliance page cache permits next-page loading during programming

**Why:** the exact AS5F14G04SND-10LIN review found load → execute → OIP-clear sequencing, no supported pipelined cache-program command, and no separate cache-ready status. Random-data loads belong to Internal Data Move, not an independently loadable second page. MCU preparation can overlap array programming, but the documented SPI loads remain serialized.
**Rejected:** using `max(transfer, program)` for this device merely because generic text mentions cache operations; probing undocumented load-during-busy behavior and treating one success as production support. Manufacturer exact-part confirmation would be required to reopen that assumption.
**Evidence:** [next-page preload audit](alliance-nand-wiring.md#estimated-time-and-energy-penalty); [faster-part comparison](../../reports/Faster%20camera%20storage%20alternatives.md); commit `6ebd4d5e`.
**Provenance:** reconstructed from the dated command/status/timing audit. Faster serial parts and genuine-cache parallel NAND were research alternatives, not replacements selected by the user.

## 2026-10-19  Use native one-bit SDMMC2 with the seven-pin breakout

**Why:** the passive SPI-labelled breakout exposes CLK/CMD/DAT0/DAT3 but not DAT1/DAT2. Native one-bit SDMMC2 uses those available contacts with hardware CRC/flow control/DMA support, while the reviewed CN3 route avoids the Arduino analog-divider/LED loads. The user chose to use the existing board without socket rework and maximize one-bit throughput.
**Rejected:** calling the four-data-line SD interface QSPI; expecting four-bit operation from missing contacts; substituting mechanical CD for DAT1/2; continuing the older Arduino SPI wiring. A later full-pin breakout can support a separately qualified four-bit change.
**Evidence:** [breakout limits and selected wiring](sd-breakout-benchmark.md); commits `777a4b96`, `0c9d601d`, `6224f912`.
**Provenance:** reconstructed from user hardware constraints, the final interface decision and subsequent read smoke test. The GPIO banks remained 3.3 V; no NAND voltage conversion is implied.

## 2026-10-19  Internal pulls are a bench convenience, not complete SD reset-time bias

**Why:** internal CMD/DAT0/DAT3 pulls can support the requested unchanged-breakout experiment, but MCU pulls disappear in reset and the card's own startup pull covers DAT3 only. Hidden DAT1/DAT2 contacts cannot be biased by those MCU pins. Native CS/DAT3 is an input with pull-up, not a driven SPI chip select.
**Rejected:** treating successful initialization as full electrical qualification; selecting four-bit/UHS 1.8 V mode on this wiring; assuming weak pull-ups generate high-speed transfer edges. Keep the interface at 3.3 V until a separate physical change is qualified.
**Evidence:** [supply, pull-ups and initialization](sd-breakout-benchmark.md#supply-pull-ups-and-initial-firmware-setup); commits `b49741cc`, `0c9d601d`.
**Provenance:** reconstructed from the accepted experimental convenience and documented carrier/reset limitations, not an additional hardware-change authorization.

## 2026-10-19  Evaluate SD cards for predictable write completion as well as throughput

**Why:** in the related card comparison the user made unpredictable write delay as important as write speed, with read speed unimportant, capacity above 1 GB sufficient, a simple STM32N6 interface, and a preference for 3.3 V. This makes completed-write latency under the actual image workload a selection criterion, not just advertised sequential bandwidth.
**Rejected:** selecting a card solely by read MB/s, capacity, an industrial label or a video-speed badge. Specific SanDisk/Kingston models and four-bit 50 MHz operation in the response were candidates, not user-approved purchases or qualified results; p90 alone does not bound rare stalls.
**Evidence:** [Compare SD Cards](https://chatgpt.com/c/6ad6749b-fed8-83ea-9d9f-433ae6ae2652), user turns October 19 at 19:51:58 and 20:22:49 UTC; [related-chat coverage](../notes-bootstrap-2026-10-24.md); [benchmark boundary](sd-breakout-benchmark.md#what-the-comparison-can-establish).
**Provenance:** reconstructed from the complete related chat retrieved during October 24 bootstrap. User selection criteria are explicit; proposed card models remain research.

## 2026-10-24  Give the gain slider the full analog range while retaining unity digital gain

**Why:** the user wants separate manual exposure and gain controls and explicitly approved 1×–8× analog gain for the second slider. This adds low-light adjustment without requiring longer exposure, while keeping the stored RAW samples free of an additional digital-gain multiplier. Higher analog gain trades highlight headroom for signal amplification; it does not collect more photons.
**Rejected:** retaining the October 15 fixed-1× analog policy, extending the slider through digital gain, or selecting an automatic gain/exposure loop. Digital gain stays 1×. Equal-stop slider mapping (approximately 1×, 2×, 4×, 8× at equal travel intervals) is the recommended firmware mapping, quantized to the sensor's 29 analog codes; endpoint calibration and exact ADC wiring remain to settle.
**Evidence:** the user's “Yes” to “Shall we use the full 1×–8× analog-gain range for the gain slider?” in this chat on 2026-10-24; [current policy D-50](../decisions/2026-10-13-project-baseline.md); [VD56G3 datasheet §3.4.4](https://www.st.com/resource/en/datasheet/vd56g3.pdf), analog gain = 32/(32−code), code 0…28. Check the configured analog ceiling and verify the applied gain during implementation; [UM2602](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf) documents the default 4× limit.
**Provenance:** recorded contemporaneously after explicit approval. This supersedes only the analog-gain part of the October 15 unity-gain note; the exposure-range requirement remains. No slider wiring or gain-control firmware has been installed or qualified.

## 2026-10-24  Use conditioned Arduino analog inputs and switch both control pots together

**Why:** the user approved two 10 kΩ linear sliders, their low ends at ground and high ends supplied by one 3.3 V GPIO during sampling, with wipers routed through the Nucleo's conditioned A0/A1 inputs. The board's dividers/buffers translate the header range to the MCU's 1.8 V ADC, avoiding a voltage-bank modification. Nominal pot current is 2 × 3.3 V / 10 kΩ = 0.66 mA while enabled.
**Rejected:** applying 3.3 V directly to an unconditioned MCU ADC input; keeping the pots continuously energized; or merely floating their shared supply after reading. Wait for the analog supply, drive HIGH, overlap settling/ADC setup with independent initialization, sample and latch both positions, drive LOW, then apply sensor parameters. Keep the shared drive LOW before analog-rail shutdown. Companion digital pins PF5/PC10 remain high impedance with pulls disabled.
**Evidence:** the user's “Yes” to the buffered Arduino-input proposal on 2026-10-24; [UM3417 analog input adaptation and connector map](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf); reviewed MB1940 C02 schematic sheet 10 (470 kΩ/560 kΩ dividers and TSZ122 buffers). A0/CN4.1 feeds PA8/ADC12_INP5; A1/CN4.2 feeds PA9/ADC12_INP10. [TSZ122 timing](https://www.st.com/resource/en/datasheet/tsz122.pdf) makes instantaneous sampling inappropriate; 100–200 µs is a provisional settling window to test, not a qualified system limit.
**Provenance:** recorded contemporaneously after approval. A0 is assigned to exposure and A1 to gain as the wiring convention. Exact shared-supply GPIO, settling/calibration implementation and physical wiring remain to qualify. Separate GPIO/ADC-reference rails are not inherently ratiometric; calibrate endpoints and test rail variation. Switching removes pot current, not the onboard buffers' own powered bias. No firmware or hardware was changed.

## 2026-10-24  Reserve Arduino D7 PE11 for the shared slider supply

**Why:** the user already has sliders and asked for the high-side connection. PE11 is available on Arduino D7/CN13 pin 8 and the same net at CN15 pin 23, on the board's main 3.3 V I/O supply. It provides a convenient common switched supply for the two 10 kOhm controls without disturbing native SD, camera, recovery or phase-marker wiring. Configure low-speed push-pull, LOW initially and after sampling; nominal combined pot current is 0.66 mA.
**Rejected:** using D2/PD0 or D4/PE0 as apparently spare Arduino pins: current capture code still uses both as diagnostic outputs. A permanently connected 3.3 V rail would defeat the selected switched-pot behavior.
**Evidence:** [UM3417 tables 16-20](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf); MB1940 C02 schematic sheets 3, 6 and 10 and ODB++ net 147 (only U21-E11, CN13-8 and CN15-23); DS14791 PE11 supply note (1); current `firmware/capture-raw/runtime.c` initialization of PD0/PE0 and `firmware/capture-timing/stage1_sensor.c` PE0 trace toggles. [Canonical control wiring](../hardware-firmware-interface.md#current-behavior-and-firmware-contract).
**Provenance:** selected contemporaneously in response to the user's wiring question. This resolves D-51's previously unassigned shared GPIO. Physical wiring, ADC/pot firmware and measured settling remain unqualified; no hardware or firmware was changed in this documentation step.

## 2026-10-24  Reserve the requested bulb region pending sensor capability qualification

**Why:** the user wants the upper 10% of exposure-slider travel to select B, integrating while the shutter button remains pressed and finishing on release. Preserve that UI request, but true single-frame bulb is not established for the VD56G3. The remaining travel would retain manual timed exposure if this mode is qualified.
**Rejected:** treating a frame-start trigger as an exposure gate; promising that STOP_STREAM ends the active integration and returns its partial exposure; or silently substituting stacked frames for the requested continuous exposure. Stacking is only an alternative to discuss because it changes noise, timing, memory, energy and the stored object representation.
**Evidence:** [UM2602 Rev 8](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf), sections 6, 13.5 and 14.7: streaming stop, frame-start synchronization, and programmed 16-bit integration duration in lines. No documented exposure-end input or command was found. Whether a live duration update can affect the integration already underway requires an experiment or ST confirmation; it must not be assumed.
**Provenance:** contemporary user request and documentation review; no sensor experiment or firmware change. Button sensing independently of regulator RUN, power hold through readout/save, long-exposure limits and fault/timeouts would also need implementation. Existing capture behavior is unchanged.
