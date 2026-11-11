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

## 2026-10-24  Defer bulb mode to future feature FD-07

**Why:** after reviewing the undocumented sensor capability, the user explicitly moved bulb mode to the future-features list. Retain the requested behavior: the upper 10% of the exposure slider selects B, exposure continues while the button is held, and release ends exposure before readout/save. It is not part of current prototype implementation.
**Rejected:** making bulb experiments a prerequisite for the current controls, reserving an inactive 10% band in the current timed-exposure mapping, or substituting frame accumulation without a separate decision. The current plan keeps the full slider range for manual timed exposure, from the fastest qualified duration to the existing 1 s target; endpoints still need hardware qualification.
**Evidence:** the user's October 24 instruction, "ok, lets add this to the list of future features," following the sensor-interface review above; [future direction FD-07](../decisions/2026-10-13-project-baseline.md#future-directions-explicitly-retained).
**Provenance:** recorded contemporaneously. Supersedes the earlier provisional reservation as current scope, preserving its desired future UI. Revisit actual sensor exposure-end control, long-exposure limits, button sensing, power hold through saving and energy before adoption. No firmware or hardware changed.

## 2026-10-24  Retain the SDMMC2 wiring when moving to a full-pin SD carrier

**Why:** the user selected Pzsmocn PZSSD001 (Amazon B08FB3GC34), which exposes D1 and D2 in addition to the signals already wired. Retaining CN3 CLK/CMD/D0/D3 and the existing supply/ground avoids moving established Nucleo connections; adding PC5/CN3.15 and PC0/CN3.17 prepares the native four-bit interface.
**Rejected:** calling the wider SD bus QSPI, using mechanical CD as data, or treating new wiring as an already negotiated/qualified four-bit link. Existing CS maps to D3, not CD. Installed v18 stays one-bit until the driver and card/controller width negotiation are changed and tested.
**Evidence:** [replacement wiring table and supplier pin diagram](sd-breakout-benchmark.md#october-24-replacement-pzsmocn-pzssd001-full-pin-breakout); existing MB1940 C02 CN3 mapping and DS14791 AF11 assignments cited there; `firmware/sd-storage/sd_card.c` configures only PC2/3/4 and keeps PE4 input/pull-up.
**Provenance:** recorded from the user's October 24 replacement-board selection and request for old-wire-to-new-pin instructions. Physical rewiring, delivered carrier bias network and four-bit throughput remain unverified; no firmware or instrument state was changed for this plan.

## 2026-10-27  Lock the prototype SD clock/ground pair and nearby power pins

**Why:** after reporting successful cycles without probes when CLK and ground were brought together, the user explicitly selected a twisted CLK/GND pair for the prototype. Moving SD ground to CN3.8 and VCC to CN3.5 allows tighter routing next to CLK at CN3.3. This is the canonical connection plan; CMD and all four data connections remain unchanged. Keep the pair short and closely coupled, with no series CLK resistor in this selected setup. Wire placement remains a known cause of link failures and must be preserved or requalified after handling.

**Rejected:** restoring the separated CLK/ground wiring or previous CN3.19/CN5.4 power endpoints as the current assembly plan; treating successful cycles as measured analog margin or complete image-readback qualification; assuming both 3.3 V supply contacts use the same regulator branch. CN3.5 is main VDDIO, while old CN5.4 is auxiliary VDD3V3. Account for the branch change in subsequent power comparisons; no voltage-bank conversion is selected.

**Evidence:** direct user instruction on October27 to lock in the twisted connections, explicitly reporting GND→CN3.8 and VCC→CN3.5. [Canonical wiring and diagram](sd-breakout-benchmark.md); [UM3417 Rev4 Table20](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf) lists CN3.3=PC2, CN3.5=VDDIO and CN3.8=GND. MB1940 C02 manufacturing ODB++ independently maps those contacts to PC2/net186, VDDIO/net11 and GND/net358. [Electrical interpretation and earlier uncertainty](../../firmware/sd-storage/NOTES.md#2026-10-27--treat-clockground-routing-as-an-experimental-variable). No agent bench operation, firmware change, new energy measurement or full-image readback accompanied this documentation change.

## 2026-11-07  Verify the supplied uxcell thumbwheel electrically before assigning physical pins

**Why:** the user identified the actual control as Amazon B07JLFC7FC, uxcell
50 kOhm 16 x 2 mm five-pin duplex thumbwheel, replacing the earlier assumed
10 kOhm slider hardware. The matching product listing identifies B503 and SKU
a18081800ux0125 but supplies no pinout. The search did not establish a
manufacturer datasheet tied to this SKU. A firsthand uxcell B503 teardown
draws a shared end (1), wipers (2/3), and opposite ends (5/4 respectively),
but does not qualify the user's delivered batch or physical viewing direction.

**Rejected:** presenting an ALPS RK14J lookalike datasheet or a generic B503
pin diagram as authoritative for this uxcell part; wiring by an assumed
left-to-right numbering. Confirm constant end-to-end resistance near 50 kOhm
and complementary variable wiper resistances with the unpowered part isolated.
Use one verified track for each independent knob; a duplex wheel moves both
tracks together. Revisit ADC settling/loading for 50 kOhm during control
bring-up rather than silently retaining a 10 kOhm qualification.

**Evidence:** user product photograph and [exact purchase link](https://www.amazon.com/dp/B07JLFC7FC);
[matching uxcell product listing](https://www.harfington.com/products/p-1100763);
[firsthand teardown and internal-track photograph](https://theblinkyledblog.blogspot.com/2016/04/uxcell-b503-b501-audio-duplex.html).
No meter measurements, control firmware, or new canonical pot pin assignment
were made in this lookup. Existing MCU-side A0/A1 and PE11 assignments remain
the proposed interface, not proof of this component's internal connections.

## 2026-11-07  Move the shared control supply to Arduino A5 PH2

**Why:** the user prefers the shared switched supply beside the A0/A1 wipers
for neater assembly. A5/CN4.6 connects to PH2 through fitted SB3 on the stock
C02 board. SB2 is open, isolating PH9/I2C SCL and its pull-up. PH2's VDDIO4
remains at 3.3 V in this SD prototype. Two separate 50 kOhm pot tracks draw
132 uA nominal together; the A0/A1/A5 470 kOhm + 560 kOhm conditioning
dividers add at most about 10 uA nominal. This is well below the 6.5 mA
load specified for low-speed GPIO output-high performance at 3.3 V.

**Rejected:** retaining the more distant PE11/D7 assignment solely because it
was selected earlier; driving PG15 (the buffered ADC companion) or PH9
instead of PH2; assuming the historical 1.8 V NAND-bank conversion happened.
Use PH2 low-speed push-pull, initially LOW, HIGH for settling/sampling,
then LOW before analog-rail shutdown. The high ends are supplied; the wipers
remain A0 and A1. D9/PD7 power HOLD is unchanged. If VDDIO4 is later converted
to 1.8 V, revisit the control range and calibration rather than retaining a
3.3 V assumption.

**Evidence:** [UM3417 Rev4 table 17 and default bridge footnote](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf#page=31);
saved MB1940 C02 schematic sheet 10 (SB3/SB2, A5 divider and U9B);
[DS14791 Rev11 table 66](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=172);
[current wiring](../hardware-firmware-interface.md#current-behavior-and-firmware-contract).
This supersedes the October 24 PE11/D7 supply choice. Component pin numbering
still needs the meter check recorded above. ADC firmware, settling and
accuracy remain unqualified; no firmware or bench operation accompanied this
wiring update, and the board remains disconnected for assembly.

## 2026-11-07  Group the exposure control on A3 A4 and A5

**Why:** the user wired the exposure thumbwheel to three adjacent Arduino
contacts: low end A3/CN4.4, wiper A4/CN4.5, high end A5/CN4.6, and confirmed
that A4 is the input to read. Stock C02 routing gives PA2 for the LOW drive,
PH2 for the switched HIGH drive, and buffered PF3/ADC1_INP16 for the wiper.
Keep A4's PC12 digital companion input/no-pull. Configure PA2 LOW before
enabling PH2 and retain it LOW during sampling; A3 is not a fixed ground pin.

**Rejected:** retaining A0/GND as the current exposure hookup, reading A3's
analog companion instead of the A4 wiper, or treating successful raw samples
as camera exposure integration. Gain's A1/CN4.2 wiper, CN5.6/GND return and
shared A5 high remain proposed, not newly confirmed. The earlier physical
thumbwheel pin-numbering caution and endpoint/settling qualification remain.

**Evidence:** direct user wiring statement and A4 clarification on November 7;
saved MB1940 C02 sheet 10 (SB6, SB5/SB4, SB3/SB2 and U9A) and DS14791
PF3/ADC1_INP16 mapping; [current wiring table](../hardware-firmware-interface.md#current-behavior-and-firmware-contract)
and [RAM-only diagnostic](../../firmware/control-smoke/README.md). The first
v5 diagnostic reads A4 at 10 Hz with raw values around 1190, PA2 LOW and PH2
HIGH, without reported errors. Full-travel validation is pending. No NOR
programming or integration into capture firmware accompanied this smoke test.
This supersedes only the exposure A0/GND plan in earlier notes; A5 remains
the selected shared supply and D9/PD7 power HOLD is unchanged.

## 2026-11-09  Exposure control now occupies A0 through A2, freeing A3

**Why:** while reviewing whether HOLD could move to A3, the user reports
that the exposure knob has physically moved to A0–A2. This supersedes the
previous A3–A5 exposure hookup and frees A3 from that knob connection.
Exact low/wiper/high roles within the new group were not restated; do not
invent them or assume the older proposed gain use of A1 remains available.

**Rejected:** reusing the old control-smoke program unchanged with the new
hookup, or claiming it already supports A3 HOLD. That diagnostic explicitly
drives PA2/A3 LOW. Installed USB HOLD remains PD7; an A3 migration needs
capture/USB/recovery/shutdown firmware updates before use.

**Evidence:** direct November9 user clarification; current
`firmware/control-smoke/control.c` drives `output(GPIOA,2,0)` and the current
manifest names A3-low/A4-wiper/A5-high. A3 is CN4.4/PA2 through fitted SB6
on MB1940 C02. Its R159=470kohm/R158=560kohm analog-conditioning branch
loads a3.3V HIGH by approximately3.2uA. This report records the knob move,
not a selected/installed HOLD relocation or a bench test.

## 2026-11-09  Reserve A3 for HOLD and confirm A0 A1 A2 exposure roles

**Why:** the user explicitly selects A3/CN4.4/PA2 for HOLD and confirms the
adjacent exposure contacts as A0 LOW, A1 wiper and A2 HIGH. Grouping the
control wiring on CN4 simplifies assembly. Stock C02 routing provides PF5
for A0 LOW, buffered PA9/ADC1 channel10 for the A1 wiper and PF6 for A2 HIGH;
A1's digital companion PC10 stays input/no-pull. PA2 is a main-VDD GPIO
through fitted SB6, so no PCB or voltage-bank conversion is needed.

**Rejected:** retaining D9/PD7 as the canonical HOLD endpoint; running the
old A3–A5 diagnostic, which deliberately drives PA2 LOW; or keeping the
earlier gain-on-A1 proposal when exposure now occupies A1. No gain replacement
is selected in this pin migration. The conditioned PA8/PA10/PA12 companions
remain analog/Hi-Z and are not the GPIO outputs to drive. A3's existing
470kohm/560kohm divider adds about3.2uA load at3.3V; it does not prevent
driving Q2, but it belongs in any future HOLD-current accounting.

**Evidence:** direct user selection and explicit A0 LOW/A1 wiper/A2 HIGH
confirmation; UM3417 Rev4 Table17, MB1940 C02 sheet10/SB6/U8B and DS14791
PA2 main-VDD supply note2. [Current interface](../hardware-firmware-interface.md)
and [canonical SVG](../power/lipo-latch-wiring.svg) use the new assignments.
The power topology is unchanged: Q3 before Q1; R0 in the battery branch;
D_USB joins after R0. New firmware changes are offline while the user has
the board disconnected for assembly. Package08 remains the last installed
PD7 image; new A3 takeover, recovery, ADC endpoints and latch cutoff require
hardware tests after reconnection. No instrument operation or installation
accompanied this documentation update.

## 2026-11-10  Put the ASA analog-gain knob on A4 A5 and ground

**Why:** the user installed an additional potentiometer for ASA control,
with its track between A4 and GND and its wiper on A5. It will set sensor
analog gain. This assigns the remaining nearby Arduino analog-header
contacts while preserving exposure on A0 LOW/A1 wiper/A2 HIGH and power
HOLD on A3. A4/CN4.5 uses PC12 for future switched excitation; A5/CN4.6
feeds the conditioned PG15/ADC1 channel7 input, with PH2 input/no-pull.

**Rejected:** leaving gain wiring unassigned or retaining gain on A1;
sharing exposure's A2 supply after the user's separate A4 connection;
driving A5/PH2 as in the historical exposure diagnostic; mapping ASA to
digital gain; or claiming the added wiring already changes sensor settings.
Keep the accepted 1×–8× analog range and unity digital gain. Exact ASA scale,
endpoint calibration, curve and settling remain implementation work.
Normal capture still uses fixed settings, and the current RAM diagnostic
tests only exposure. The older A3–A5 helper also lowers A3 HOLD and must
not be used with this wiring.

**Evidence:** direct November10 user hardware report; saved MB1940 C02
schematic sheet10 (A4 PC12/SB5, A5 PH2/SB3 and divider/U9B to PG15), default
SB4/SB2 open; historical [A5 endpoint manifest](../../firmware/control-smoke/evidence/2026-11-08-diagnosis/builds/v11-default-secure/manifest.json)
names ADC1_INP7/PG15. The current SD prototype retains 3.3V VDDIO4 for
PC12/PH2. PF3, A4's buffered ADC companion, stays analog/Hi-Z rather than
driving the header. Future firmware should drive PC12 LOW initially, HIGH
for settling/sampling, then LOW; never feed header-level3.3V directly into
an unconditioned ADC pin. [Current interface](../hardware-firmware-interface.md)
records both knobs. No firmware, instrument or hardware-test operation
accompanied this documentation update.

## 2026-11-10  Preserve revision-matched Nucleo source documents in Git

**Why:** the user asked to include the Nucleo schematic and relevant supporting
references in the pushed repository. The complete C02 schematic, BOM and
revision C manufacturing sources underpin connector, power-tree and component
location findings, but their originals were only in ignored temporary storage.
Archive those exact source bytes alongside UM3417 Rev 4, with source URLs and
SHA-256 records, so a fresh checkout can reproduce the reference review. The
external DC1863A manual accompanies the already tracked LTC3621 datasheet.

**Rejected:** leaving essential source documents only under `tmp/` or behind
external links; silently replacing the evidence-matched C02 source with a
newer board variant; treating generic manufacturing population as the fitted
C02 BOM; or describing the original schematic as our modified as-built board.

**Evidence:** [reference bundle and manifest](../../datasheets/boards/nucleo-n657x0-q/README.md);
[October 18 source hashes](nucleo-assembly/locations.json). The archived full
schematic and manufacturing ZIP match those historical hashes; all copied
vendor files have provenance records and verified content/archive integrity.
No firmware, hardware or instrument operation accompanies this publication.

## 2026-11-11  Keep the ST promodule as the camera for the custom PCB

**Why:** during the PCB readiness review the user noted "I think we have to
use the promodule". The custom PCB is therefore planned around the complete
CAM-6G3-073CLR module rather than a bare VD56G3 with separately sourced
optics. This fixes the module's 4.68 mm height, its 30-pin flex connector and
the need for the host board to supply all three sensor rails and the clock.

**Rejected:** planning this board spin around a bare sensor and custom lens to
recover thickness or power. The earlier VD5943/custom-optics direction stays a
future direction and is not reopened here. The user's wording is a working
constraint ("I think"), not a statement that no alternative can ever exist.

**Evidence:** direct user note, November 11, in the PCB readiness review;
[punch-list items PL-09 and PL-12](../review/2026-11-10-pcb-readiness-punch-list.md).
That the module carries no regulators is the repository's second-hand record
of ST's module documents, which are still not stored locally. No hardware,
firmware or CAD change.

## 2026-11-11  The RTC for the custom PCB is the RV-3032

**Why:** the user named the RV3032 as the source of temperature for a possible
exposure limit, and confirmed on request that the RV-3032 is the intended RTC.
The recovered design carries an RV-3028-C8, which that choice replaces for the
custom PCB.

**Rejected:** carrying the RV-3028-C8 forward by default from the recovered
schematic. Not decided: the backup supply arrangement, pins, or whether the
accelerometer is on this board spin.

**Evidence:** direct user replies, November 11, in the PCB readiness review;
[punch-list item PL-19](../review/2026-11-10-pcb-readiness-punch-list.md).
No RV-3032 datasheet is stored yet, so its backup current, temperature
accuracy and footprint are unverified here. No hardware, firmware or CAD
change.

## 2026-11-11  Include an orientation sensor, sized for four-way sensing, and cut it first

**Why:** the user decided to add the accelerometer to the custom PCB but to be
ready to cut it if other constraints require. The user noted that camera
orientation is only needed to within 90 degrees in the plane of the sensor,
which leaves many options beyond a three-axis accelerometer.

**Rejected:** leaving orientation off this spin by default; treating a full
accelerometer as a hard requirement. Not decided: the sensing part. The
recovered design's LIS2DW12 with its own load switch and I2C bus is one
candidate, not a selection.

**Evidence:** direct user note, November 11, in the PCB readiness review;
[punch-list item PL-19](../review/2026-11-10-pcb-readiness-punch-list.md);
earlier finding ACC-001 on the accelerometer's start-up time. No hardware,
firmware or CAD change.
