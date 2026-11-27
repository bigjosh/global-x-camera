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

## 2026-11-13  Check both sides of SB6 when MCU HOLD and Arduino A3 disagree

**Why:** the user reports no external A3 HIGH despite continuity from A3 to
Q2's gate. Live rechecking found the complete boot/HOLD prefix unchanged and
PA2 output/pad HIGH in verified UART recovery. ST's schematic routes PA2
directly to CN3.34 but through SB6 to CN4.4/A3. Header-to-gate continuity does
not test that MCU-to-header connection. The official C02 BOM confirms SB6 is
factory fitted; its present physical condition remains unverified.

**Rejected:** concluding that firmware changed from the external trace alone;
calling an open SB6 proven; using PA12, the buffered ADC companion, as the
HOLD GPIO; or treating software pad readback as an external voltage measurement.
The requested direct-PA2 and A3 voltage readings remain pending.

**Evidence:** [November13 live prefix, recovery and GPIO comparison](../../firmware/control-smoke/evidence/2026-11-13-hold-recheck/README.md),
including official schematic/BOM/manual references. No firmware or board
wiring change; target left in recovery with HIGH HOLD for the user's meter.

## 2026-11-25  Custom-board dials: Alps RK10J11E0034, mounted face-down behind windows

**Why:** the user likes the present 16 mm hobby thumbwheels, but they have no datasheet. Asked for a similar part at DigiKey, a search by maker and by DigiKey category found one family still in production with a flat, edge-turned wheel: the Alps RK10J. The user chose RK10J11E0034 for both dials: single track, 10 kΩ linear (Alps taper 1B), 14 mm wheel, rated for DC use. The user then described the arrangement. The board's bare face is the user side. Both dials sit on the parts side with the wheel face against the board and are read through window holes sized to the labels. Each wheel stands about 2 mm above the top edge. The control group is on the top edge toward the right as seen from the user side, in the order ASA dial, shutter button, exposure dial, about 1 inch from the right edge. The button also stands about 2 mm proud, and a hole below it shows one reverse-mount RGB LED. The user will fold the legs by hand so the part mounts this way inside the 5 mm profile, and asked for a footprint with five lands for the terminals and two for the anchor lugs.
**Rejected:** keeping the hobby wheel; Panasonic EVU 16 mm wheels (obsolete at DigiKey); Bourns 3352 and TT 91 (9 mm trimmer wheels); Piher PT-10 and PT-15 with press-on wheels (a trimmer body under the wheel); the dual-track RK10J12 parts (audio taper, and Alps lists DC use as not applicable); a four-position switch for ASA, which the open-questions sweep had suggested. Not decided here: window diameter, dial spacing, how the anchor lugs are held, the button part and the LED part.
**Constraints read from Alps's drawing and model, nothing measured:** with 2 mm of wheel above the edge the knob centre is 5 mm below it, so a closed round window can be at most about 8 mm across, while the wheel's flat face would take a label of about 13 mm. Mounted face-down, the board is 1.9 mm from where the terminals leave the body and the terminals have 1.9 mm of free length, so they only just reach. The lugs are 1.8 mm long and would have to travel about 2.7 mm around the wheel's overhang, so they cannot reach the board. Board plus part is 3.4 mm thick.
**Evidence:** direct user replies, November 25, in the open-questions review; [Alps catalog and 3D model](../../datasheets/controls/Alps_RK10J_series_catalog.pdf) with their source records; Alps's product page read that day, supply status Standard; [preview drawing](../custom-pcb/control-cluster-preview.svg) from `tools/build_control_cluster_preview.py`, not yet confirmed by the user. DigiKey's listing could not be opened from the review environment and search snippets disagreed on stock (none, or about 1,900). No part in hand.

## 2026-11-25  Control group confirmed: centred in the right half, with a small hole showing the selected label

**Why:** shown a preview of the user side, the user confirmed the arrangement with two changes. The group moves right so that it is centred in the right half of the top edge. The windows are not label-sized: each is a small hole, about where the preview had its index arrows below the dial centre, only large enough to show the one selected label. The labels sit as close to the outer edge of the wheel as possible, so they can be large and well spaced. This replaces the label-sized windows of the earlier entry of this date, so the 8 mm limit on a closed window no longer matters.
**Rejected:** windows the size of the whole label; a group placed one inch from the right edge, which was the reviewer's reading of the first description. Not decided here: the hole diameter and radius (drawn as 2.8 mm at 5.2 mm from the knob centre, kept clear of the centre terminal's land), dial spacing (drawn as 24 mm), how the anchor lugs are held, the button part and the LED part.
**Evidence:** direct user reply, November 25; [preview drawing](../custom-pcb/control-cluster-preview.svg) regenerated by `tools/build_control_cluster_preview.py`. No part in hand.

## 2026-11-25  Control group geometry locked

**Why:** shown the regenerated preview, the user answered "yes this is perfect! lock it in." The drawn geometry is therefore the placement baseline, seen from the user side with the origin at the board's top-left corner: the group is centred at x = 64.2 mm, three quarters of the way along the top edge; the ASA dial's knob centre is at (52.2, 5.0) and the exposure dial's at (76.2, 5.0), 24 mm apart, so each 14 mm wheel stands 2 mm above the top edge; a 2.8 mm hole 5.2 mm below each knob centre shows the selected label; the shutter button is centred between the dials and also stands about 2 mm proud; the LED hole is below the button.
**Rejected:** nothing new. Still provisional, because they follow parts not yet chosen: the button's width and body, the LED hole's diameter and depth below the edge. Still open: how the dials' anchor lugs are held, and the label artwork for a 14 mm wheel with 270 degrees of travel.
**Evidence:** direct user reply, November 25; [preview](../custom-pcb/control-cluster-preview.svg) and [the recorded positions](../custom-pcb/control-cluster.json), both written by `tools/build_control_cluster_preview.py`.

## 2026-11-25  Dial mounting tabs fold outward and solder to their own pads

**Why:** told that the mounting tabs cannot reach the board when the dial is mounted face-down, the user marked the tabs on Alps's drawing and decided to fold them outward until they lie flat with the back of the pot, and asked for a rectangular pad for each to solder down to. The footprint now has two `MP` pads per dial. With the knob face on the board the back of the pot is 1.8 mm above it, and a folded tab ends about 6.7 mm from the knob centre, level with the knob's rim. Each pad therefore sits just outside the rim, 7.4 to 8.9 mm from the centre, and the tab needs a short wire or riser down to it; solder alone will not span 1.8 mm.
**Rejected:** pads under the tabs themselves, where the turning knob lies between tab and board; a single strap across both tabs, which the reviewer had suggested, in favour of the user's two pads. Consequences for the locked layout: 6.2 mm remains between the two dials' inner tab pads for the shutter switch body, and the exposure dial's outer pad ends about 0.4 mm from the board edge.
**Evidence:** direct user reply with a marked copy of Alps Drawing No. 1, November 25; [footprint](../../hardware/beta/GXB.pretty/ALPS_RK10J11E0034_FaceDown.kicad_mod) and [its notes](../../hardware/beta/README.md), written by `tools/build_dial_footprint.py`; tab and rim positions from Alps's 3D model. A draft: no part in hand.

## 2026-11-25  Dial footprint corrected after a second reading of Alps's model

**Why:** two independent checkers re-measured Alps's 3D model against the new footprint. They confirmed the pad positions, the mirroring and the clearances to the knob, and corrected four things. A folded tab is part of the back plate, so its underside is 1.5 mm above the board, not 1.8 mm, and its tip reaches about 6.97 mm from the knob centre, not 6.7 mm. The exposure dial's outer tab pad came within 0.12 mm of the board's rounded corner, so the tab pads now end at 8.6 mm. The terminal pads now start at 7.7 mm, outside the terminal strip's edge, because a folded terminal cannot sit inboard of it. And Alps's drawings disagree about which terminal is the wiper: the terminal figure for this part reads 1, dummy, 2, dummy, 3, while the leaders on its hole drawing and the reflow twin's land drawing point to 1, 2, dummy, dummy, 3.
**Rejected:** renaming the pads on the drawings alone. The pads keep the names from the part's own terminal figure, and the schematic is to tie both dummy pads to the wiper until a part has been metered.
**Still untested, no part in hand:** whether the terminals survive having the factory bend reversed next to the eyelet; whether they reach the pads once a label lifts the knob off the board; knob drag on the board.
**Evidence:** the two checkers' reports, November 25, both from measurements of `RK10J1_E.STEP` and Drawing No. 1; [footprint notes](../../hardware/beta/README.md). KiCad itself was not run on the file.

## 2026-11-26  Placement inputs for the beta board, and a first draft

**Why:** asked where the lens and card slot go, the user gave the placement brief, all as seen from the back. The lens is vertically centred, about a third of the board's width from the left edge, which leaves the right side under the control group as the handhold. The module sits in a cut-out so that its back is flush with the back of the board; the user plans to pot it in place and invited a neater mounting. The module's flex needs clearance to rise from the cut-out to its connector on the parts side. The SD slot is vertically centred on the left edge. The shutter switch should have long travel and a strong click, as far as an SPDT part that fits allows. A strip a few millimetres wide along the right edge is kept clear so the housing's front edge can be radiused like an old Nikon body. A keep-out centred on the bottom edge leaves room for a tripod socket. The layout should look composed, with symmetry, repeated patterns and alignment where they can be found, because the parts may be seen through a clear cast case.
**Proposed in the draft, not decided:** the SD slot, lens and cell on the horizontal centre line; the MCU, lens and regulator block on the lens's vertical axis; the cell landscape under the control group with its unfolded protection board at the lead end; four FETs in a row under the LED; charge pads and the ST-LINK connector along the bottom.
**Conflicts and unknowns the draft exposes:** the locked exposure dial reaches 2.4 mm from the right edge and its outer tab pad 0.8 mm, inside any keep-out of a few millimetres; a standard 1/4 inch tripod thread is 6.35 mm across, wider than the 5 mm camera, so the socket is a local bulge or a smaller thread; the module's flex has only about 3 mm of free length in which to climb about 2.2 mm from a head sunk flush with the back, and the direction it leaves the head fixes whether the frame is upright or on its side, so both need a module in hand.
**Evidence:** direct user reply, November 26; [draft](../custom-pcb/beta-placement-draft.svg) from `tools/build_beta_placement_preview.py`; module dimensions from the stored ST data brief. Nothing measured.

## 2026-11-26  Part searches for the beta: card socket, LED, debug connector, shutter switch

**Why:** four searches, each with a second checker, looked for the remaining user-facing parts. These are proposals; the user has not chosen.
- **Card socket:** Molex 503398-1892 (DigiKey WM11190CT-ND), push-push, 1.28 mm high, 13.1 x 14.05 mm, 10,000 cycles, detect switch to ground. From its drawing, which the checker opened: the card stands 2.8 mm past the socket front when locked, needs a 0.9 mm press to release and stands 6.2 mm out when ejected; the card's centre line is 0.83 mm off the body's centre. Alternate: Molex 104031-0811, push-pull, 1.42 mm, card 4.0 mm proud.
- **LED:** SunLED XZMDKCBDDG45S-9, a reverse-mount ("bottom entry") RGB, 3.2 x 2.8 mm, 1.9 mm high, six-figure DigiKey stock in snippets. Common anode rests on one listing snippet; pinout and hole diameter are unread. Alternate: Würth 156125M173000, 0.8 mm high.
- **Debug:** the STDC14 land pattern for a Samtec FTSH-107-01-L-DV-K header, which is 5.97 mm tall and so is soldered on development boards only, with BOOT0 and BOOT1 pads beside it; probe STLINK-V3MINIE, which ST states supports 1.65 to 3.6 V targets. No holes, nothing on the back. Alternate: Tag-Connect TC2070 pads, which need three 1 mm holes through the visible back and a cable DigiKey does not sell.
- **Shutter switch:** nothing found is SPDT, clicks, and fits the 6.2 mm between the dials' inner tab pads. The best is the Omron D2MQ-4L-105-1-L (DigiKey SW1396-ND): a true changeover snap-action microswitch with gold contacts for the microamp load, 8.2 x 6.5 mm and 2.7 mm thick laid flat, lever actuator, about 2 mm of pretravel, light force (about 40 gf on the silver-contact sibling). It needs about 8.5 mm along the edge.
**Rejected:** detector switches sold as "SPDT", which are centre-off with no normally-closed contact; right-angle click tactiles, all single-throw; the Panasonic ASQ sliding-contact switch (no click, too thick); the C&K K5V (far too large); reverse-mount status assumed for the Kingbright AAA3528L part.
**Evidence:** the searchers' and checkers' reports of November 26. The Molex, Hirose and GCT socket drawings were opened from public mirrors; everything else is distributor snippets. Stock figures are undated.

## 2026-11-26  Placement draft accepted as the direction; keep-outs and debug pads settled

**Why:** the user liked the first placement draft and answered its open points. The right-edge keep-out shrinks to accommodate the locked exposure dial: it now stops at the dial's rim, 2.4 mm from the edge, and the dial's flat outer tab pad is the one thing inside it. The tripod socket becomes part of the housing, so the board keeps nothing clear for it. The camera module's cut-out, flex path and flex direction stay pending until the user has a module in hand. The debug connection is header pads only: the STDC14 land pattern left bare, reached with a pogo fixture the user will make, with BOOT0 and BOOT1 pads beside it. The user will look at the proposed Omron D2MQ shutter switch and answer later.
**Rejected:** Tag-Connect, because its three holes would show on the back; a tripod keep-out on the board; moving the control group for the keep-out's sake.
**Still proposed, not decided:** the card socket (Molex 503398-1892), the LED (SunLED XZMDKCBDDG45S-9), and every block position outside the control group.
**Evidence:** direct user reply, November 26; [second draft](../custom-pcb/beta-placement-draft.svg) from `tools/build_beta_placement_preview.py`.

## 2026-11-26  Beta pin table drafted; three prototype pins move

**Why:** the pin table is the last input schematic capture needs. A researcher assigned every signal from ST's pin tables, the boot ROM manual and the prototype firmware, keeping the prototype's pin wherever it sits on a 1.8 V bank, and a second reader checked all rows. Three signals leave their prototype pins: the camera strobe goes from PA0 to PA5, because PA0 is a boot ROM UART pin that may be driven after any failed flash boot; XSHUTDOWN goes from PO5 to PF1, so the VDDIO2 bank stays unused as decided; the red LED goes from PG10, the ROM's boot-failed output, to PA7. The checker also found that 100 kilohm gate pull-downs are too weak against the datasheet's 5 microamp pin leakage: HOLD and the LED FETs get 10 to 22 kilohm and the 3.3 V enable 47 kilohm or less.
**Rejected:** keeping PA0, PO5 and PG10 for firmware's sake; a shared bus for the camera and the RTC, in favour of a second bus so that only the sensor is on the camera bus during start-up.
**Learned:** every reset returns HOLD to a floating input, so on the cell a reset drops power unless something else holds the latch; a force-on pad beside the debug pads is needed for programming.
**Evidence:** [pin table](../custom-pcb/beta-pin-table.md); the researcher's and checker's reports of November 26, citing DS14791 Rev 10 Tables 17 to 20 and UM3234 Tables 27 to 34. Nothing run on hardware; the user has not reviewed the table.

## 2026-11-26  Shutter switch: Omron D2MQ lever microswitch, terminals folded flat

**Why:** the user looked at the proposed Omron D2MQ-4L-105-1 and chose it: a true changeover snap-action switch with gold contacts, which the capacitor start circuit needs, with about 2 mm of lever travel. It lies flat on the parts side, 2.7 mm thick, lever toward the top edge, and the user will fold its three terminals flat onto rectangular pads so nothing passes through the board. Its 8.2 mm body does not fit the 6.8 mm between the dials' inner tab pads at the locked 24 mm spacing.
**Proposed, awaiting the user's answer:** move the ASA dial 2 mm left and the switch and LED hole 1 mm left, which leaves 0.3 mm each side of the body and keeps the exposure dial and the right-edge keep-out as they are; the LED hole moves down to about 12 mm below the edge to clear the terminal pads, so the FET row moves too. The alternative is to keep the 24 mm spacing and drop each dial's inner tab pad.
**Not yet known:** the terminal positions and which hand (-L or -R) to order; Omron's datasheet is not stored and its site cannot be reached from the review environment. Figures used are from distributor listings: body 8.2 x 6.5 x 2.7 mm, lever 6.3 mm, operating position 7.1 mm and free position 8.7 mm above the base, terminal spacings 2.5 and 4 mm, operating force about 0.39 N on the silver-contact sibling.
**Evidence:** direct user reply, November 26; [fit drawing](../custom-pcb/shutter-switch-fit.svg) from `tools/build_shutter_fit_preview.py`.

## 2026-11-26  Shutter switch: Omron's datasheet stored; hinge lever with straight terminals

**Why:** the user supplied Omron's D2MQ datasheet and named the hinge-lever model with straight terminals, D2MQ-4L-1, because the terminals come straight out of the case bottom and are easy to bend. The straight version replaces the question of -L or -R hands in the entry above.
**Corrects the entry above:** the operating position (7.1 ±0.5 mm) and free position (8.7 mm max) are measured from the mounting-hole centre line, which is 1.6 mm above the case bottom, not from the case bottom. The three terminals are at 2.5 mm pitch, centred, 0.8 x 0.6 mm and 3.4 mm long. With the lever resting 2.0 mm above the board edge the case bottom is 8.3 mm below the edge and the lever snaps about 0.4 mm above the edge; the proposed pads run to 11.0 mm and the LED hole centre moves to 12.6 mm below the edge.
**Open, raised with the user:** D2MQ-4L-1 has silver contacts with a minimum load of 5 VDC 50 mA; D2MQ-4L-105-1 is the same switch with gold contacts and a minimum of 5 VDC 5 mA. The start circuit switches far less than either, so the gold one is the nearer fit. The proposed 26 mm dial spacing is still awaiting the user's answer. A straight terminal leaves the case about 1 mm above the board when the switch lies flat, so each needs a small joggle down to its pad. The terminal order (datasheet: COM, NO, NC) is to be confirmed with a meter before the footprint is drawn.
**Evidence:** `datasheets/controls/Omron_D2MQ_datasheet.pdf` (user upload, November 26); [fit drawing](../custom-pcb/shutter-switch-fit.svg) and [full-board drawing with the proposed spacing](../custom-pcb/beta-placement-proposed-spacing.svg), both generated. No part in hand.

## 2026-11-26  Control group re-locked: dials 26 mm apart, gold-contact D2MQ between them

**Why:** the user confirmed the spacing the switch needs and the contact material ("26mm spacing and gold contacts. lock it in."). The part is Omron D2MQ-4L-105-1: hinge lever, straight terminals, gold contacts, minimum load 5 VDC 5 mA. In the back view the ASA dial centre is now at x = 50.2 mm, the switch at 63.2 and the exposure dial unchanged at 76.2, all 5.0 mm below the top edge for the dials. The switch is midway between the dials, so the group is still symmetric; it sits 1 mm left of the centre of the right half of the top edge. The switch case bottom is 8.3 mm below the edge, its pads end at 11.0 mm, and the LED hole centre is at 12.6 mm with two FETs each side.
**Rejected:** keeping the 24 mm spacing and dropping each dial's inner tab pad, which would leave each dial held by one tab and its terminals. The silver-contact D2MQ-4L-1 first named: its minimum load is 5 VDC 50 mA, far above what the start circuit switches.
**Removed:** `docs/custom-pcb/beta-placement-proposed-spacing.svg`, linked from the entry above. It showed the proposal; the placement draft now carries the same positions, and `tools/build_beta_placement_preview.py` no longer writes a second drawing.
**Evidence:** direct user reply, November 26; [control-cluster.json](../custom-pcb/control-cluster.json) and its preview, the [fit drawing](../custom-pcb/shutter-switch-fit.svg) and the [placement draft](../custom-pcb/beta-placement-draft.svg), regenerated. No part in hand; DigiKey stock of the straight-terminal gold part has not been checked on a live page.

## 2026-11-26  Dial wiring: outside terminals are the track ends, middle terminal is the wiper, dummies unconnected

**Why:** the user settled it: "two outside pins as top and bottom and middle pin as tap is flippable." The wiring is mirror-symmetric, so the face-down footprint works whichever way the terminal numbering runs; only the direction of rotation changes, and firmware sets that. Each dummy terminal keeps its own pad with no net.
**Rejected:** the earlier rule in the footprint notes, tying both dummy pads to the wiper until a part is metered. It assumed the dummies connect to nothing inside the part, which is not known. The user's first idea of the same day, shorting each outside pair of terminals and tapping the middle, which they withdrew: the opened part they photographed was not this one. That photo shows a two-gang element board (one shared end, two collectors, two far ends), the arrangement already recorded on November 7 for the uxcell duplex wheel; on such a part the shorted pairs would tie a live wiper to a track end.
**Still to check:** Alps's hole drawing hints at 1, 2, dummy, dummy, 3 instead of 1, dummy, 2, dummy, 3. Meter the first RK10J11E0034 before boards are ordered; the pads are separate, so a solder bridge to the neighbouring pad corrects it.
**Evidence:** direct user replies and photo, November 26; [footprint notes](../../hardware/beta/README.md). No Alps part has been metered or opened.

## 2026-11-26  Shutter switch footprint drafted and checked; dial wiper position is less certain than the terminal figure suggests

**Why (switch):** `tools/build_shutter_footprint.py` now holds the one definition of the D2MQ's geometry and lands, and the fit and placement drawings read it. A second reader re-measured Omron's drawings and agreed with every dimension, the contact order (pad 1 COM at the lever pivot, 2 NO, 3 NC, from the contact-form figure only) and the mirroring. Pads were widened from 1.4 to 1.6 mm after the check, to cover the terminals' 1.3 mm barbs by Omron's general tolerance.
**Learned (switch):** the free position is a maximum, so "2 mm proud" is the most the lever can stand. At the confirmed position the switch snaps 0.4 ±0.5 mm above the board edge and needs 0.3 mm more travel, so a worst-case part is pressed 0.4 mm below the edge. Moving the switch 0.5 mm toward the edge would avoid that. Deferred to the user: it changes the position confirmed today.
**Learned (dial):** Alps's dual-unit RK10J12 parts use the same outline drawing and a byte-identical 3D model, and their five terminals read shared end, wiper, wiper, far end, far end. The reflow single-unit twin RK10J11R0A0L is labelled 1, 2, dummy, dummy, 3, and the dummy leaders on the RK10J11E0034 hole drawing end on the third and fourth holes. Against that stand the part's own terminal figure and the digits over the holes: 1, dummy, 2, dummy, 3. The documents cannot settle which of the second or middle terminal is the wiper. The two outside terminals are the track ends in every figure. The wiring the user chose today is kept; the meter check before ordering is what decides, and the footprint notes give the procedure.
**Rejected:** tying the second and middle pads together now as insurance. It would work for a single wiper on either, but it presumes the unused one is isolated, and the user's rule is simpler to correct with a solder bridge once a part is metered.
**Evidence:** reports of the footprint builder, its checker and the Alps document reader, November 26 (stored catalogue pages 2 and 3; Alps product pages for RK10J11E0034, RK10J11R0A0L, RK10J12E0A0A and RK10J12R0A0B); three independent traces of the user's photo agreed on the two-gang layout of that other part. No Alps or Omron part has been metered; the footprint has not been loaded in KiCad.

## 2026-11-26  Shutter switch moved 0.5 mm toward the board edge

**Why:** the user chose it ("0.5 up please") after the footprint check showed that, 8.3 mm below the edge, a worst-case switch only finished its stroke 0.4 mm below the board edge. The case bottom is now 7.8 mm below the edge. The lever rests at most 2.5 mm above the edge, snaps 0.9 ±0.5 mm above it and, with Omron's 0.3 mm minimum overtravel, always finishes at least 0.1 mm above it. The pads run 7.9 to 10.5 mm below the edge and the LED hole centre is 12.1 mm below it.
**Constraint this adds:** the lever's fixed pivot hub now stands 0.4 mm beyond the board edge, and the lever rests up to 0.5 mm higher than the dial rims; the housing has to allow for both.
**Corrected in the drawings:** the four FETs beside the LED are now drawn standing on end at their real 2.4 x 2.9 mm outline, 0.5 mm below the LED centre. Drawn lying down at 2.9 x 1.6 mm they overlapped the corners of the dial bodies by 0.5 mm, in this and the earlier drawings. The fit script now checks the row against the switch pads and the dial bodies.
**Evidence:** direct user reply, November 26; `tools/build_shutter_footprint.py` and its checks; regenerated [fit drawing](../custom-pcb/shutter-switch-fit.svg), [control-cluster.json](../custom-pcb/control-cluster.json) and [placement draft](../custom-pcb/beta-placement-draft.svg). No part in hand.

## 2026-11-27  Dial and switch pin orders: build on the best guess, rework if wrong

**Why:** the user has neither part in hand and will not hold the board for meter checks ("go with best guess and we can always rework if issues"). The board is drawn with the dial wiper on the middle terminal and the switch as pad 1 COM (lever-pivot end), 2 NO, 3 NC.
**Basis for each guess:** dial: the part's own terminal figure and the digits over its hole drawing both give the middle terminal, and Alps drew a different figure for the reflow twin, which suggests the difference is deliberate; the stray dummy leader on the hole drawing looks like a leftover from the twin's drawing. That is the reviewer's reading, not a fact. Switch: two independent readings of Omron's contact-form figure agree.
**Rework if wrong:** dial: bridge the middle pad to the neighbouring dummy pad with solder (0.8 mm gap); the track ends are on the outside terminals in every Alps figure, so nothing else changes. Switch: a wrong order needs cuts and wires at the three pads, so keep the three nets as short, exposed surface traces near the pads.
**Deferred, not dropped:** the meter checks and the trial fold of a dial move from "before ordering" to the first parts to arrive.
**Evidence:** direct user reply, November 27; the entry of November 26 on the Alps documents.

