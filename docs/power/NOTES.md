# Power decisions and constraints

## 2026-10-13  Keep the battery prototype separate from mechanical energy harvesting

**Why:** the user selected four series CR2032 cells through LTC3621 while retaining a frame-advance mechanism winding/driving a spring as future work. The earlier harvesting calculation was an energy-envelope study, not a measured capture budget or a selected mechanism; a short shutter click and a deliberate winding stroke are different workloads.
**Rejected:** substituting an unqualified mechanical generator for the battery prototype; treating the study's 50 mJ assumption as achieved energy. Spring storage remains deferred, not rejected permanently.
**Evidence:** [D-03 and FD-02](../decisions/2026-10-13-project-baseline.md); [harvesting study](shutter-energy-harvesting.md); commit `cf9302c9`; [related-chat coverage](../notes-bootstrap-2026-10-24.md), mechanical-energy branch `01a132e1-f117-75c0-990c-b9b09b8e610c`.
**Provenance:** reconstructed from explicit user selection in review transcript message 020, the dated study, and the related October 13 spring discussion. Thin-capacitor candidates and assumed 20–150 mJ cycles were recommendations/models, not selected or measured hardware; candidate selection was delegated by the user on October 24.

## 2026-10-13  Budget RTC backup separately from the 100 nA main OFF target

**Why:** RTC backup bypasses the main regulator through one cell. The accepted 0.1 µA room-temperature target therefore applies to the complete main path, with the RTC accounted for separately at its tapped cell. LTC3621's 0.1 µA typical shutdown figure already consumes that whole target before external leakage; its 1 µA maximum is not a 100 nA guarantee.
**Rejected:** calling the regulator's typical figure an assembled-board limit; omitting RTC current from cell lifetime/imbalance; treating proposed regulator screening as qualified yield or a selected cutoff.
**Evidence:** [OFF-current budget](../../power.md#4-off-current-budget); [D-06](../decisions/2026-10-13-project-baseline.md); commit `cf9302c9`.
**Provenance:** reconstructed from explicit user target/scope approvals in review transcript messages 028–030 and the retained component study.

## 2026-10-13  Use button-to-RUN startup and GPIO HOLD with a minimum valid press

**Why:** the chosen simple prototype circuit lets the button-fed divider start LTC3621 and a diode-isolated GPIO sustain RUN after boot. The user accepts holding the button until takeover. Standby releases an ordinary HOLD GPIO; Stop retains I/O configuration and cannot perform that handoff. A held button can keep the regulator enabled while the MCU remains in Standby until release.
**Rejected:** assuming any short tap is guaranteed; automatic repeat captures while the button remains held; treating held-button consumption as the button-released 100 nA OFF state. The earlier discrete PMOS latch is comparison history, not the selected circuit.
**Evidence:** [RUN/HOLD operation and handoff](../../power.md#22-operation); [D-10, D-11 and D-16](../decisions/2026-10-13-project-baseline.md); commits `cf9302c9`, `853b0348`.
**Provenance:** reconstructed from explicit user proposals/clarifications in review transcript messages 038/040 and the approved shutdown definition. Final circuitry remains unqualified.

## 2026-10-13  Keep the held-button series capacitor distinct from a shutdown-delay capacitor

**Why:** a series capacitor could end a prolonged start assertion, but must reliably rearm and hold RUN through boot-to-HOLD takeover. A RUN-to-ground capacitor instead delays shutdown after HOLD releases. Their jobs and failure modes differ; neither supplies the camera independently.
**Rejected:** adding the held-button defense to the current prototype without pulse/rearm/bounce/leakage qualification; using the optional shunt delay as if it eliminated held-button current. Both values/topologies remain unselected.
**Evidence:** [FD-03 and capacitor distinction](../decisions/2026-10-13-project-baseline.md#future-directions-explicitly-retained); [power study](../../power.md); commit `cf9302c9`.
**Provenance:** reconstructed from the explicit deferral in review transcript messages 046–048 and its accompanying engineering analysis.

## 2026-10-13  GPIO release does not replace main and auxiliary rail sequencing

**Why:** N6 Standby turns off its internal SMPS and drives PWR_ON low, but the recovered shared 1.8 V net ties AON and auxiliary consumers together. External AUX rails still must fall below 0.6 V while the required main supplies remain valid. PWR_ON also asserts before firmware, so directly making it battery HOLD can engage battery power during USB boot.
**Rejected:** claiming an external sequencing IC is inherently mandatory; claiming internal SMPS shutdown or direct PWR_ON-to-RUN alone completes the external sequence and USB isolation. R_OFF discharges RUN, not the power rail.
**Evidence:** [sequencing and firmware handoff](../../power.md#stm32n6-sequencing-and-firmware-handoff); [recovered power tree](power-tree.md); [PWR-003](../review/power-review.md); commit `cf9302c9`.
**Provenance:** reconstructed from the corrected September analysis and October 13 consolidation. This is a circuit constraint, not proof that the final external sequencer exists.

## 2026-10-17  Use the CN8 source route to avoid ST-LINK power-switch interruptions

**Why:** disconnecting/reconnecting the CN9 load on protected 5V_STLK caused a persistent red PWR STATUS indication and source collapse. CN8 → CN9.3 → JS110 → CN9.2 kept the source alive while switching target power and supported repeated autonomous boots. CN15.8 is the same protected 5V_STLK source, not a bypass.
**Rejected:** retrying automated target cycling through CN9.1 as if it were an independent steady supply; treating the unexplained protection/reset behavior as an established MCU boot limit. The precise original trigger remains unresolved.
**Evidence:** [source routes and observations](nucleo-debug-isolation.md#board-source-using-the-second-usb-connector); [October 17 measurements](../../firmware/boot-timing/bench-results-2026-10-17.md); commits `ef783eda`, `169206da`, `7ca8ca8a`.
**Provenance:** reconstructed from user wiring confirmation and measured bench results, not inferred from the schematic alone.

## 2026-10-17  CN8-fed Joulescope results describe a board branch, not isolated battery energy

**Why:** CN8 retains a provider branch, VBUS sense divider and USB/CC signal paths outside the CN9/JS110 path. Individual CN12 rail shunts also omit other camera loads. Useful cycle timing and board-branch energy do not establish complete upstream battery energy or main-path OFF leakage.
**Rejected:** equating switched target-rail discharge with zero bypass current; adding input/output converter shunt readings as independent loads; claiming final battery efficiency from a downstream 5 V measurement. Independent 5 V input with CN8 absent remains a proposed isolation improvement.
**Evidence:** [CN8 bypass audit](nucleo-debug-isolation.md#cn8-bypass-audit--october-17); [measurement isolation goals](nucleo-debug-isolation.md#measurement-isolation-goals); commit `92d2c8fc`.
**Provenance:** reconstructed from the schematic audit and explicitly stated measurement limits. No new isolation test was performed during notes bootstrap.

## 2026-10-18  Retain the Nucleo regulator tree and feed it 5 V for the prototype

**Why:** direct 3.3 V injection is not a documented Nucleo input mode and does not power its complete main/AUX tree. Bypassing regulators requires separate main/AUX control and reverse-current analysis. The user selected LTC3621 at 5 V with unnecessary capture loads removed, accepting evaluation-board overhead to simplify bring-up; the confirmed adjustable DC1863A supports this setting.
**Rejected:** combining the unselected direct-3.3 V bypass study with the assembly guide; assuming the historical fixed LTC3621-3.3 part can be adjusted to 5 V. A compact-board rail architecture remains open.
**Evidence:** [selected power tree and alternatives](2026-10-14-power-tree-review.md); [assembly guide](../prototype/nucleo-assembly-guide.md); [conditional energy comparison](power-cost-comparison.md); commits `d6e28a9c`, `9fae7c66`.
**Provenance:** reconstructed from explicit final user selection and hardware identification. The modeling supported the tradeoff; it was not measured energy or proof of CR2032 pulse capability.

## 2026-10-18  Opening D2 separates the debugger supply but leaves signal and sense loads

**Why:** CN9 source selection does not open target 5 V → D2 → debugger regulator. The user removed D2 and R23, separating that main feed and the target power LED; debug/reset/UART and divider paths remain. The F723 FT inputs do not have the ordinary upper clamp diode model, yet voltage tolerance is not a powered-off leakage guarantee.
**Rejected:** CN9-open, debugger reset, a dark LED or a near-zero debugger rail as proof of full isolation; assuming every unpowered GPIO necessarily backfeeds through a VDD diode. Keep CN10 independently powered for development until remaining paths are separately qualified.
**Evidence:** [D2/R23 and powered-off-pin audit](nucleo-debug-isolation.md#d2-and-r23-removed-cn8-only-functional-operation--october-18); commits `da4d1a25`, `6c2b8c54`.
**Provenance:** reconstructed from user-reported removal and exact C02/F723 documentation review. Only D2/R23 removal was reported; other proposed component removals are not implied.

## 2026-10-18  Keep USB off the battery budget without assuming the camera can use only 1.8 V

**Why:** in the related power-tree chat the user explicitly said USB is not needed on battery. A future 1.8 V digital architecture can therefore retain USB-only 3.3 V, but it still needs the camera's 2.8 V analog rail and separate main/AUX sequencing. The present RTC backup switching and diode-to-RUN HOLD margin also need redesign at 1.8 V; the Nucleo core buck's input minimum prevents simply lowering its feed to 1.8 V.
**Rejected:** treating a lower-voltage research direction as performed Nucleo rework or a selected replacement power tree; claiming I/O voltage-squared savings as an equivalent whole-camera reduction. The 5 V prototype decision remains.
**Evidence:** [related-chat coverage](../notes-bootstrap-2026-10-24.md), “Consolidate project decisions - remove 5v”, `01a1481f-598f-7542-930d-381adef2786f`, direct user clarification October 18 at 22:35:51 UTC and its surrounding analysis; [1.8 V architecture assessment](1v8-memory-assessment.md); [custom-board candidate](2026-10-14-power-tree-review.md#compact-board-candidate-not-selected).
**Provenance:** reconstructed from the related chat retrieved during October 24 bootstrap. USB-on-battery scope is explicit user evidence; lower-voltage circuitry remains an assistant research recommendation, not an adopted modification.

## 2026-10-27  Use Arduino CN5.5 and CN5.6 for the Joulescope-fed target

**Why:** the user selected the Arduino power header as the canonical prototype power connection while explicitly retaining the JS110 in series. The regulated source feeds JS110 IN+, JS110 OUT+ feeds CN5.5/5V, and the common source/JS110 return connects to CN5.6/GND. This provides the requested header access while preserving the same target 5 V rail and downstream regulators. All CN9 shunts stay absent. The target-contact choice does not itself select a new upstream source: the existing CN8/CN9.3 bench source and separately configured LTC/external 5 V source remain distinct configurations.

**Rejected:** retaining CN9.2 as the current target attachment in assembly instructions, bypassing the Joulescope with a direct or parallel feed, using VIN for regulated 5 V, inferring that LTC has been connected or the physical lead move completed, or treating the new contacts as a cure for remaining debugger/CN8 bypass paths. When using LTC/external 5 V, disconnect the CN9.3 source lead and unplug CN8; the existing USB-fed bench option retains its documented measurement limits.

**Evidence:** direct user instruction on October27: "make CN5 pin 5 for 5V and CN5 pin 6 for GND the canonical power connection, keeping the joulescope in series." [Current connection table](nucleo-debug-isolation.md#canonical-target-power-connection--october-27); [assembly guide](../prototype/nucleo-assembly-guide.md#4-connect-ltc-power). ST MB1940 C02 manufacturing ODB++ maps CN5.5 and CN9.2/4/6 to net380/5V, CN5.6/7 to net358/GND, and CN5.8 to separate net10/VIN. [UM3417 Table16](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf) confirms the header functions. No firmware or instrument operation accompanied this documentation change; historical measured wiring records remain unchanged.

## 2026-10-28  Separate battery collapse from intrinsic camera power

**Why:** the user moved to four series CR2032 cells through DC1863A and explicitly placed JS110 between the cells and LTC. The supplied screenshot reaches about 280 mA and 2.73 V, outside the demo's specified input range for regulated 5 V. Approximate paired voltage/current readings suggest roughly 0.6–0.7 W during several active intervals, so rising current alone is not proof of rising useful load power. U24, the Ethernet PHY, remains fitted; only D2/R23 removals are confirmed. The camera adapter's LDOs and the newly selected main-LDO SD supply are further conversion costs.

**Rejected:** treating the 280 mA battery-side peak as MCU current; directly comparing it with old downstream 5 V current; asserting that the cells are permanently damaged; assigning an exact Nucleo overhead percentage from an aggregate collapsing-supply trace; reusing the old NAND model's roughly 40% custom-board saving as a measured SD result. Further rework and an energy reservoir remain proposals, not adopted hardware changes.

**Evidence:** [user screenshot](../../research_notes/Camera%20power/startup%204x2032%20via%20LTC.png), direct October28 clarification that no further power removals were made, and [analysis with rail topology, reference loads and primary sources](power-cost-comparison.md#october-28-battery-side-trace-and-remaining-overhead). The 5 V output and firmware execution were not measured. No instrument operation or firmware change occurred; current hardware state and USB-source isolation must be re-established before bench work.

## 2026-10-28  Establish board overhead on a stable direct 5 V baseline

**Why:** the user accepted the direct regulated 5 V setup and reports the connections made with a 2 A-capable bench supply. Measuring the unchanged target before component changes separates its demand from coin-cell collapse and LTC startup/losses. Existing PD12 markers and a reset input can align phases with JS power samples without first changing the capture firmware.

**Rejected:** treating a 2 A supply rating as measured proof of a stiff target rail; mixing upstream-LTC and target-5-V energy as one baseline; reusing Saleae pulse tolerances blindly for the JS110's slower digital sampling; assuming the JS GPIO shares the isolated measurement-terminal reference or requires JS220-style external Vref. GPIO wiring is proposed, not yet user-confirmed, and no new baseline has been recorded.

**Evidence:** direct user hookup confirmation and [baseline/marker plan](nucleo-debug-isolation.md#direct-5-v-baseline-and-proposed-synchronized-markers--october-28), the installed build's protocol-v2 manifest, and the linked JS110 manufacturer documentation. No instrument operation or firmware modification occurred during this setup review.

## 2026-10-28  Put the proposed JS marker wires on CN15

**Why:** the user prefers all JS digital connections on one convenient header. CN15.21/PD12 supplies the existing phase observations, CN15.33/PD0 provides an early firmware marker to inspect, and CN15.20 is ground. Target NRST is not on CN15, so this convenience trades direct reset-release timing for a firmware boot observation; PD12 still provides the needed cycle-phase alignment.

**Rejected:** inventing a CN15 equivalent of CN3.14/NRST or treating PD0 as reset release. The power wiring remains on CN5. Physical marker connection and waveform qualification remain pending; no firmware change was made.

**Evidence:** user request and [revised marker table](nucleo-debug-isolation.md#direct-5-v-baseline-and-proposed-synchronized-markers--october-28); ST C02 ODB++ maps the three CN15 pins to nets162/PD12,173/PD0,358/GND and contains no CN15 contact on target NRST/net235. Historical [boot probe mapping](../../firmware/boot-timing/bench-results-2026-10-16.md) independently records PD0 and GND contacts.

## 2026-10-28  Align Joulescope phase traces by native sample IDs and qualify startup separately

**Why:** the confirmed CN15 connections resolve all ten driven PD12 phase markers in three cold cycles, and IN1 follows three controlled PD0 pulses. However, analog channels start at different native sample IDs, the final packed digital chunk has an unspecified valid length, and undriven GPIOs chatter during startup/recovery park. The first 5 ms also contain unqualified analog extrema. Scoped later windows remain useful for comparing board overhead without inventing a precise startup-current or instruction-entry measurement.

**Rejected:** aligning raw files by array index or host callback timestamps; assigning every edge to firmware; treating PD0 as NRST; declaring a whole recording valid despite its 71 initial NaN current samples; promoting first-5-ms raw integrals or brief extrema as qualified whole-cycle energy/inrush. The corrected PD0 identity test does not erase its failed preliminary BSRR attempt or the strict IN0-silence failure while PD12 was undriven.

**Evidence:** [three-run baseline, wire tests and retained limitations](evidence/2026-10-28-direct5v-gpi/README.md), native sample/hash analysis and per-run records. The installed firmware was unchanged; no independent image readback or fresh SBF check accompanied these measurements. Final normal boot returned to approximately 8.568 mA at 4.993 V.

## 2026-10-28  Attribute power with matched phase controls and retain SD variability

**Why:** GPIO-aligned direct5V measurements place roughly two-thirds of cold
post5ms energy in SD transport, including the whole board's retained load.
Identical normal warm runs vary164–384ms in that interval, far larger than
small component changes. Matched post-STOP holds resolve0.791mA from sensor
reset and another0.841mA from receiver disable; deferring SD lowers concurrent
camera-period current25–32mA. These are useful incremental effects, not a
complete partition of intrinsic MCU power and Nucleo overhead. Ethernet
management did not acknowledge, leaving its saving unmeasured.

**Rejected:** subtracting unlike warm/cold totals, treating whole-board phase
energy as one component's power, attributing card write variability to an
ablation without repeats, or promoting an artificial200ms hold into normal
firmware. The sleep-path current drop remains externally observed because
live proof could not be read; its recovery constraint is owned by the
[RAW capture notes](../../firmware/capture-raw/NOTES.md).

**Evidence:** [aligned baseline, twelve successful RAM captures, three complete
image readbacks and final-state record](evidence/2026-10-28-aligned-ablation/README.md).
Normal flash remained unchanged; source/binary snapshots and failed controls
are retained with the measurement evidence.

## 2026-10-28  Do not dismiss the early transient as autoranging or certify its physical peak

**Why:** fixed10A and automatic-range controls both show the initial peak
around35µs on raw range0; automatic downshift occurs later at128.5µs. Their
first5ms charge agrees within about1.2%. Subsequent autoranging alone cannot
explain it, but a common switch-on/measurement response and the negative
transients remain unresolved. The raw event integrates to about3.7mJ,
compared with hundreds of millijoules in sustained capture/save.

**Rejected:** declaring the recorded approximately7.9A a calibrated physical
inrush, treating it as coin-cell current through LTC, or adding its raw energy
to a qualified full-cycle total. The source-side voltage does not establish
target rail droop; direct5V hard turn-on differs from LTC soft start.

**Evidence:** [fixed-range/automatic controls and SDK range interpretation](evidence/2026-10-28-aligned-ablation/README.md#initial-transient-fixed-range-versus-automatic-range).
Both raw traces, range streams, settings restoration and qualification limits
are retained. First5ms remain excluded from the qualified baseline windows.


## 2026-10-28  Measure Ethernet power-down before removing hardware; compare CPU choices per completed work

**Why:** with camera and SD physically disconnected, two matched LAN8742
normal/down/restored controls reduced board-input power by182.85mW on average
(36.76mA at5V). CPU-only400→50MHz saved13.31mW but doubled energy per completed
synthetic update; same-binary I-cache control reduced energy per update38.76%.
Unused SRAM RUN clock gating saved only1.59mW. The residual PHY-off board load
cannot be called intrinsic MCU power because required regulators, buses, memory
and other loads remain. A final missing-camera normal boot reached8.0766mA;
warm recovery then observedSBF1/PDDS1/STOPF0, with generic trial_entry_proven:false
retained and its cold-cycle history recorded separately.

**Rejected:** treating lower clock current as automatically lower photo energy;
adding separate control deltas as a measured combined configuration; counting
already removedD2/R23 or already disabledU14 again; removingEthernet immediately
when most of its awake cost can be addressed in firmware. Physical removal may
also eliminate residual and pre-firmware power, but that additional saving is
unmeasured. Defer regulator rework until main3.3V/auxiliary1.8V branch currents
are measured. These are recommendations for subsequent qualification, not an
installed production-firmware change or a measured custom-board floor.

**Evidence:** [isolated Nucleo report, proofs, waveform analysis and frozen builds](evidence/2026-10-28-isolated-nucleo/README.md).
Normal NOR unchanged; finalJSoutput disabled19:15:18UTC. The MDIO read-edge
constraint belongs to [RAW firmware notes](../../firmware/capture-raw/NOTES.md).

## 2026-10-30  Reject multi-second reservoir recharge as the route to CR2032 operation

**Why:** the user requires readiness for the next shot in less than one second,
rejecting the proposed whole-photo reservoir with roughly10–30s replenishment.
The independent50ms button-to-exposure target remains. The feasibility analysis
uses sustained1Hz short-exposure photography as a conservative working case;
the user has not separately specified burst length, temperature or usable-cell-life
qualification. A one-second exposure itself cannot fit within a sub-second
start-to-start interval. A small transient buffer is not rejected by this decision.

At1Hz,20/40/80mJ drawn from the battery per photo require1.67/3.33/6.67mA
through each series cell at12V, or2.22/4.44/8.89mA at9V. These energy figures
already include conversion losses. A custom-board goal near20–30mJ/photo is
therefore more useful than assuming the present200–270mJ measured5V workload
can be supported through a voltage change alone. It is a design target, not a
demonstrated result or a universal CR2032 current rating. Cell model, state of
charge and temperature still need qualification.

**Rejected:** a selected22–33mF reservoir/charger design; treating1.8V as every
device rail; treating an MCU clock-divider change or series/parallel cell
reconnection as an automatic whole-system energy saving; claiming that a
typical NAND programming calculation proves complete-photo energy or maximum
timing. No new power-tree, NAND, image-format or firmware choice is adopted.

**Evidence:** direct user requirement in this chat; [current measured cycles](../../firmware/capture-raw/evidence/2026-10-28-sensor-single-frame/README.md),
which exclude the first5ms and LTC losses. VD56G3 typical145mW sensor power
over the observed approximately25ms exposure/readout/tail gives only a few
millijoules; applying it for the entire approximately50ms startup gives about
8–11mJ upstream with assumed efficient supplies. These are models, not sensor
rail measurements. The sensor still needs1.15V core/1.8V IO/2.8V analog;
the N6 core remains approximately0.81/0.89V with separate main/AUX sequencing.
[Sensor tables13–14](https://www.st.com/resource/en/datasheet/vd56g3.pdf),
[N6 hardware guidance](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf).

Storage is a material research lever. For the current approximately1.91MB RAW
object in pre-erased pages, typical internal programming alone is approximately
20.2mJ/560ms for purchased Alliance AS5F14G04SND (933x2KiB,1.8V,20mA,600us),
8.74mJ/187ms for Macronix MX35UF4GE4AD (467x4KiB,1.8V,26mA,400us), and
5.25mJ/117ms for Winbond W35N04JW (467x4KiB,1.8V,25mA,250us). These exclude
bus loading, host/RAM, metadata, erase and conversion. Typical page times are
not maxima. Hardware quad/octal DMA, low-power waits while the array is busy,
sensor/CSI gating after readout and erasing onUSB are promising directions.
The new parts require interface, ECC, ten-year-retention/reuse and sourcing
qualification before selection; faster programming does not require claiming
undocumented cache-program support.
[Alliance Rev3.2](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.2_Jan2026-revised.pdf),
[Macronix Rev1.7](https://www.mxic.com.tw/Lists/Datasheet/Attachments/9233/MX35UF4GE4AD,%201.8V,%204Gb,%20v1.7.pdf),
[Winbond RevC](https://www.winbond.com/upload/technical-support/11749f34-ad3a-4639-8fcc-ea93e4322c94.pdf).
No hardware access, firmware change or new measurement accompanied this analysis.

## 2026-11-03  Preserve separate main and auxiliary rails in a LiPo regulator bypass

**Why:** the user is exploring LiPo plus 3.3 V LDO power. U33 already supplies main 3.3 V through an LDO; replacing only the auxiliary U34 buck's function may reduce rework. Schematic and ODB++ inspection now establish R102 as main output isolation, R115 as auxiliary output isolation, and R132 as the auxiliary buck's input disconnect. The two 3.3 V domains must retain their distinct startup/shutdown behavior. ST1S31 also limits EN to VIN, so disconnecting its input while PWR_ON remains connected is not a valid isolation scheme.

**Rejected:** interpreting the earlier tentative R132 identification as an output-isolation instruction; tying main and auxiliary 3.3 V together; removing R132/R115 alone while leaving an unpowered U34's enable driven; assuming one 3.3 V header powers the core/AON tree. The reversible candidate opens R115 only and leaves the old buck powered but unloaded while a PWR_ON-controlled LDO supplies AUX; its residual cost and replacement LDO ramp/discharge remain to qualify. No replacement regulator or battery architecture is selected, and no physical rework is performed.

**Evidence:** [updated circuit study and verified link/net table](2026-10-14-power-tree-review.md#november-3-single-cell-lipo-and-33-v-ldo-feasibility), MB1940 C02 sheet9/ODB++, ST1S31 Table2 and AN5967 section3.5. A LiPo/LDO supply cannot maintain regulated 3.3 V through the entire cell discharge range. The earlier approximate4V test starting point is not a measured cutoff; typical off-time arithmetic alone does not establish one.

## 2026-11-05  Account for the powered but unused camera regulator U42

**Why:** tracing the UM3417 power diagram's "others" block exposed a distinction between an unused supply path and an absent regulator. The MB1940 C02 BOM marks U42/LD1117S33TR fitted and SB31 not fitted. U42 input is directly on target 5 V; its output is local net388 with C155 and the open SB31. The actual camera feed is auxiliary VDD3V3 through SB10. U42 therefore remains a possible board-overhead load even when the camera is disconnected or the MCU enters Standby.

**Rejected:** reading the earlier "U42/SB31 path is not fitted" wording as proof that U42 consumes nothing; attributing all residual Standby current to the MCU; claiming a measured saving from removing U42. LD1117 Table 6 lists 5 mA typical / 10 mA maximum quiescent current under its stated conditions, but the actual contribution and delivered-board population still need physical qualification. No hardware operation or rework was performed.

**Evidence:** [corrected power comparison](power-cost-comparison.md), [ST C02 schematic sheet 11](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), C02 BOM rows U42/SB31 and ODB++ nets380/388 retained under `tmp/hardware-review/nucleo-modifications/`; [LD1117 Table 6](https://www.st.com/resource/en/datasheet/ld1117.pdf#page=12). Other omitted loads include LEDs, USB-C circuitry and exported header supplies; UM3417 does not enumerate exact membership of "others", so that grouping is a schematic interpretation.

## 2026-11-05  Remove unused U42 as a separate, measurable board-overhead reduction

**Why:** in response to the user's removal/location request, the schematic, C02 BOM and ODB++ establish that U42 has no functional downstream load with SB31 open. Removing the complete regulator preserves the existing SB10 auxiliary camera feed and eliminates U42's own input consumption. The verified underside location and removal instructions are now recorded.

**Rejected:** bridging the removed regulator's pads; removing SB10 or confusing U42 with a required main/AUX regulator; recording proposed rework as completed or assuming the typical5mA value is a measured saving. Physical removal remains user work; no bench state, firmware or measurement changed.

**Evidence:** [U42 locator and removal plan](../prototype/nucleo-assembly/README.md#november-5-unused-u42-removal-plan), direct bottom-assembly vector rectangle, pick/place BottomLayer X16.8686mm/Y29.0750mm, and net388 membership (U42.2/4, C155.2, SB31.1 only). Default SB10 fitted/SB31 absent verified in the C02 BOM.

## 2026-11-05  Preserve debug sensing while pursuing the remaining sleep loads

**Why:** the user confirms U42 removal worked and reports3.3mA after sleep. The remaining power-tree audit finds required low-bias main/AON regulators, already-disabled U14 and normally-off AUX/core supplies, rather than another unused U42-sized regulator. The SD carrier LED/card remain main-powered; the debugger's two dividers account for about0.496mA at nominal rails. Prioritize identifying the carrier LED before disrupting target-voltage sensing.

**Rejected:** removing R65/R73 as harmless passives while relying on ST-LINK recovery; changing canonical SD power back to AUX without power-off/backfeed qualification; interpreting nonmatched historic connected/disconnected currents as an isolated card measurement; treating a user-reported3.3mA plateau as independent proof of rail voltages or MCU state. U42 is now user-confirmed removed; no other new physical change, firmware installation or measurement was performed by the agent.

**Evidence:** direct user result in this chat; [remaining-load audit](power-cost-comparison.md#november-5-u42-removal-and-remaining-sleep-loads), C02 sheets8–13/BOM, installed October28 `peripherals.c` and `sd_deinit()` input/pull configuration. An ideal tenfold increase in both legs of each divider could save about0.446mA while preserving DC ratios, but ADC settling and leakage remain unqualified; this is not a selected component change.

## 2026-11-05  Exclude the already-removed SD power LED from further savings

**Why:** the user clarified that the SD breakout power LED was already removed. Historical observations of an illuminated LED no longer describe the prototype. The card itself remains supplied from main VDDIO under the canonical wiring.

**Rejected:** recommending the same LED removal again or assigning its unmeasured historical current to the remaining3.3mA. Its removal date and individual before/after delta are not known.

**Evidence:** direct user correction, "already removed it," immediately after the SD LED recommendation; [updated remaining-load review](power-cost-comparison.md#november-5-u42-removal-and-remaining-sleep-loads). No agent hardware action or fresh current measurement accompanied this update.

## 2026-11-05  Separate hard-switched input charging from firmware startup

**Why:** the user reports an approximately7A/200us startup spike and confirms direct regulated5V through JS110, not the battery/LTC path. C02 schematic/BOM inspection finds about274uF nominal principal direct5V input capacitance, dominated by fitted C14/220uF. Removing U42 leaves its C17/10uF input capacitor connected. MCU firmware cannot sequence capacitors already connected across its input before its first instruction. A controlled input ramp is therefore a distinct hardware option from firmware rail scheduling or reducing capacitance.

**Rejected:** forcing JS110 into a small current-measurement range as a precharge resistor/current limiter; the documented API supplies OFF/ON and shunt selection, not a programmable output ramp. Also reject counting unfitted C13/C81, or C21/C26 across shorted supply links, as ordinary direct input-to-ground bulk capacitors. A lower total capacitance reduces charging demand but does not guarantee a proportional lower instantaneous peak. No capacitor removal, load-switch installation or rail-sequencing change is selected here.

**Evidence:** C02 sheet9/sheet11 and BOM under `tmp/hardware-review/nucleo-modifications/`; [earlier fixed10A versus auto startup evidence](evidence/2026-10-28-aligned-ablation/README.md#initial-transient-fixed-range-versus-automatic-range); new campaign `tmp/bringup/inrush-20261105/`. Initial November5 stats-only API read independently measured3.307mA at4.995V, restored settings and left power unchanged; ST-LINK was absent and no reset/power change occurred at this point. JS110 [specification](https://docs.joulescope.com/en/products/js110/guide/specifications.html) and [driver implementation](https://github.com/jetperch/joulescope_driver/blob/main/src/devices/js110/js110_usb.c) distinguish range control from supply-ramp control. Actual capacitance under DC bias and target-side voltage remain unmeasured.

## 2026-11-05  Do not qualify direct LiPo feed from nominal LDO headroom alone

**Why:** the user asks whether500mAh LiPo directly into the5V distribution bus has adequate headroom through a cycle. U34's auxiliary3.3V ST1S31 buck is the unresolved path: Figure4 suggests loss of3.3V regulation around4.1V even atzero load, whereas its duty-cycle table suggests a more favorable conversion ratio. This ambiguity prevents promising full-to-halfSOC operation from a simple3.8−3.3V calculation. Actual lowerAUX voltage might still support the capture-only downstream rails, but that is a separate qualification.

**Rejected:** treating500mAh as an internal-resistance/current-rating specification; treating the95%/100% duty entries or typical94ns off time as a guaranteed Nucleo cutoff; claimingU34PG disablesU26 (U26EN is directlyPWR_ON); calling the historical5V trace aLiPo test. No battery/regulator/modification choice is made.

**Evidence:** [updated feasibility study](2026-10-14-power-tree-review.md#november-3-single-cell-lipo-and-33-v-ldo-feasibility); [ST1S31 Table4 andFigure4](https://www.st.com/resource/en/datasheet/st1s31.pdf#page=9), visually inspected from the local officialPDF; C02 sheet9; [LD39020 Table5](https://www.st.com/resource/en/datasheet/ld39020.pdf#page=6); [TPS62088](https://www.ti.com/lit/ds/symlink/tps62088.pdf). Regulated input sweep with downstream rail observation and image verification remains proposed, not performed.

## 2026-11-05  C14 removal shortens inrush but does not qualify lower cycle energy

**Why:** the user removed C14/220uF and requested repeated cold captures. Three fixed-10A JS recordings show6.480–6.489A sampled peaks and0.1836–0.1839mC in the first250us, versus the historical7.873A/0.6476mC reference. All three saved images passed full3730-sector readback and independent decoding. However, sustained active current is now about331mA and cycle energy1.03–1.04J, approximately250mA above the earlier comparable single-frame profile. The extra load begins before the receiver marker and disappears at shutdown; it remains unexplained. Full physical64KiB NOR matches the prior normal image. Final warm recovery current also varied from the earlier parks, so it is not an isolated MCU measurement.

**Rejected:** claiming a proportional peak reduction from nominal capacitance removal; treating a shorter input surge as a demonstrated whole-cycle energy improvement; attributing the extra current to C14 without a matched A/B; inferring downstream rail stability or original cold-camera-RAM equality from readable images. Historical U42/LED/firmware/wiring differences and startup instrument limits remain explicit. No other capacitor was removed and no resistor/MOSFET was installed by this work.

**Evidence:** [three-run report, complete image checks, full NOR identity and final OFF state](evidence/2026-11-05-c14-removed/README.md), archived proofs/hash inventory and local native traces. IN1 now carries the unique11-event PD12 phase protocol and IN0 the bounded PD0 exposure mirror; retain this inferred mapping instead of silently rewriting raw stream identities. Final JS output is intentionallyOFF; normal firmware unchanged, noSDerase orNORprogramming.

## 2026-11-05  Keep precharge control independent of successful MCU boot

**Why:** the user proposes a series resistor bypassed by a MOSFET after capacitor charging. This can limit inrush, but board load during the ramp creates voltage drop and can prevent the MCU from reaching the code that closes its own bypass. Abrupt bypass with residual voltage across the resistor can create a second surge. A controlled-slew high-side load switch is the preferred next prototype experiment, while component selection remains open. Nominal54uF,10ohm and5V give0.5A initially and2.49ms to99% only for an unloaded RC; they do not model all regulator/startup loads.

**Rejected:** relying on firmware to rescue a stalled precharge, treating resistor-parallel-MOSFET as a complete OFF switch, assuming slew control imposes a hard total-current ceiling, or selecting the illustrative TPS22918 as a production0.1uA solution (its typical shutdown current alone exceeds that target). Input ramp changes must preserve the required downstream core rise/rail sequence. No new hardware choice is locked.

**Evidence:** [proposal, calculations and limits](evidence/2026-11-05-c14-removed/README.md#resistor-precharge-versus-a-controlled-ramp); [TI inrush guidance](https://www.ti.com/lit/an/slva670a/slva670a.pdf), [TPS22918](https://www.ti.com/product/TPS22918), [ST AN6000](https://www.st.com/resource/en/application_note/an6000-how-to-build-the-discrete-power-supply-for-stm32n6-mcus-stmicroelectronics.pdf). Recorded from the user's proposal during the C14-removed tests.

## 2026-11-06  Exclude the suspected-short runs from the normal active power budget

**Why:** three unchanged normal cold cycles now measure 79.65–80.03 mA and 256.56–260.89 mJ from 5 ms after current onset through the low plateau, about 251 mA below the preceding abnormal runs. C14 remains removed; no NOR programming or power-optimization firmware change occurred. During this campaign the user reported that an inadvertent short might have been fixed. Recovery-only controls stayed near 75 mA and instrument setting changes did not reproduce the excess. Treat the short as the leading user-reported explanation, not an established fault location.

**Rejected:** assigning the earlier extra 250 mA to intrinsic MCU consumption, C14 removal or Ethernet alone; treating the lower energy as a new firmware optimization; continuing speculative power-tree changes after the abnormal load ceased reproducing. The earlier high-current evidence remains intact. New cycles have phase/commit/current proof, not independent image readback or final SBF/PC proof.

**Evidence:** [three cold cycles, measurement-setting controls, guarded clock/power snapshot and read-only PHY diagnostic](evidence/2026-11-06-active-current/README.md). All eleven markers and one exposure appeared each time. MDIO read IDs 0007/C131 and BMCR 3000 twice, unlike the earlier 0000; no causal component attribution follows. Final normal shutdown plateau is 3.311 mA at 4.99554 V, JS settings restored/closed. No new physical modification by the agent, explicit SD erase or NOR programming.

## 2026-11-06  Keep C79 because it is Ethernet termination capacitance, not a power load

**Why:** the C02 schematic and manufacturing records identify C79 as YAGEO CC1206KKX7RDBB102, 1 nF / 2 kV X7R, between the RJ45 cable-side common 75-ohm termination node and shield ground. It is not connected as a 5 V bulk reservoir and has no relevant DC supply current to remove.

**Rejected:** removing C79 to reduce active current or 5 V startup inrush, or confusing it with the PHY internal regulator's required output capacitor. Removal could alter Ethernet common-mode/EMC behavior without addressing the power problem. No removal is reported.

**Evidence:** [ST MB1940 C02 schematic, Ethernet sheet 7](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf); C02 BOM/ODB++ and pick-and-place records under `tmp/hardware-review/nucleo-modifications/`, visually inspected `ethernet-sheet7.png`; [current campaign record](evidence/2026-11-06-active-current/README.md#c79).

## 2026-11-06  Reduce unused input capacitance before active-regulator decoupling

**Why:** with C14 and U42 already removed, C17 remains a 10 µF direct-input capacitor with no remaining U42 load. C12 is another 10 µF candidate on disabled U14; retaining C28 leaves its 1 µF local bypass. These are the preferred first and second experiments for the user's proposed stiff LiPo source. Together they would reduce the principal nominal direct-input inventory from 54 to 34 µF, without assuming proportional peak reduction. No removal has been reported or tested.

**Rejected:** treating battery stiffness as a substitute for local MHz-current loops or regulator output stability; cutting all MCU/sensor/output decoupling; immediately reducing active U34 input capacitors; treating TPS62088's typical 4.7 µF input guidance as qualification of this board. Reducing C19/C23 from 20 to 10 µF remains a later layout/rail-tested option. Full unused-U14 input isolation (R32/R33/C26, with no CN12 feed) is more rework than the C12-only experiment and is deferred. LNK2 is not a parallel path into U14 VIN; it ties the positive measurement node to 5V.

**Evidence:** [candidate review and existing C17 locator](power-cost-comparison.md#november-6-remaining-input-capacitance-candidates-for-a-stiff-lipo), C02 schematic sheet9/sheet11/BOM and ODB++ pad nets; [TPS62088 section8.2.2.6](https://www.ti.com/lit/ds/symlink/tps62088.pdf#page=13), [ST1S31 section5.1](https://www.st.com/resource/en/datasheet/st1s31.pdf#page=16). Root inspected sheet9; subagent independently checked U14 input/LNK2 net membership. No instrument access, firmware change or physical rework in this review.

## 2026-11-06  C17 removal reduces startup charge but leaves a multiampere surge

**Why:** after the user removed C17/10 µF, three cold cycles on unchanged normal firmware showed median sampled peak 6.497→6.140 A, first-250-µs net charge 0.18540→0.14588 mC and time above 5 A 18→13.5 µs. Comparison uses the latest three LOW-current C17-fitted runs, with C14/U42 already removed. All three new slots (166–168) passed complete 3730-sector readback at 25 MHz, independent RAW10/PNG sample decoding and visual inspection. Sleep current remains 3.310 mA. This supersedes C17's untested status above; C12/C28 remain unchanged.

**Rejected:** claiming capacitance removal proportionally limits the peak; crediting C17 with the median 256.77→159.97 mJ cycle-energy reduction when SD transport alone shortened 383.68→164.86 ms; treating the three passes as LiPo, rail-stability or all-conditions qualification. Native startup extrema remain instrument observations, with source-side voltage only. Original cold camera RAM is lost in Standby and the slot has no payload checksum, so readable/independently decoded images do not establish equality to the original capture.

**Evidence:** [three-run comparison, full image proofs, source hashes and final handoff](evidence/2026-11-06-c17-removed/README.md). All eleven phase markers and one exposure envelope passed per run; exact UART recovery passed after each. Retained SBF1/PDDS1/STOPF0 was observed with `trial_entry_proven:false`. Normal NOR was not programmed; exact prefix reverified, no new complete NOR readback claimed. Final JS output intentionally OFF after fresh idle/recovery checks, with other settings restored and device closed. No SD erase/deletion or further physical modification.

## 2026-11-06  A series inductor alone is not a qualified inrush limiter

**Why:** the user proposed a series inductor in the 5 V feed. It limits current slew through V=L·di/dt and has low steady-state winding resistance, but its stored energy keeps charging the input capacitors after they reach the source voltage. An ideal unloaded, undamped LC step reaches 2·Vin regardless of L; increasing L lowers current peak while slowing the transient. Using 44 µF nominal direct-input inventory only as an illustrative model, Ipeak=5·sqrt(C/L) gives 3.32 A at 100 µH, 1.05 A at 1 mH, or 0.50 A at 4.4 mH. Each ideal case can reach 10 V. Effective capacitance, load startup, source impedance, existing parasitics and saturation make these examples unsuitable as board predictions or selected values.

**Rejected:** treating inductance as resistance that falls as current stabilizes; assuming a larger coil alone removes voltage overshoot; using saturation as safe current limiting; or installing a bare series coil on the DUT before qualifying damping/clamping and downstream voltage. A designed damped/protected input filter remains possible. The earlier controlled-ramp switch preference remains: a nominal 44 µF ramp from 0 to 5 V in 1 ms requires 220 mA of capacitor charging current, plus active board load, not a hard total-current ceiling. Exact switch choice/ramp and rail sequencing remain unqualified. This records engineering assessment, not a user-selected new modification.

**Evidence:** [Analog Devices AN88](https://www.analog.com/media/en/technical-documentation/application-notes/an88f.pdf) and [demo-board input damping guidance](https://www.analog.com/en/resources/technical-articles/how-not-to-damage-your-switching-regulator-demo-board.html); [Coilcraft saturation explanation](https://www.coilcraft.com/en-us/resources/application-notes/selecting-the-best-inductor-for-your-dc-dc-convert/); [TI controlled-rise-time explanation](https://www.ti.com/document-viewer/lit/html/SSZTBX2/GUID-2AF5E1CE-C09D-447F-ACB7-ED209C847E47); [nominal remaining capacitor inventory](power-cost-comparison.md#november-6-remaining-input-capacitance-candidates-for-a-stiff-lipo). Equations evaluated offline; no instrument operation, physical modification or firmware change. Prior C17 final OFF checkpoint remains unchanged.

## 2026-11-06  Onboard regulation does not protect the regulators from input overshoot

**Why:** the user clarified that a coil would precede the local regulators, which would regulate to their respective outputs. That is valid only within input and dynamic-response limits. C02 sheet9 and current manufacturer ratings show U17/TPS62088 (0.81/0.89 V core) operates up to 5.5 V with VIN absolute maximum 6 V; U33/U23 LD39020 (3.3 V main/1.8 V AON) operate up to 5.5 V with 7 V absolute maximum; U34/U14 ST1S31 (3.3 V AUX/disabled alternative 1.8 V) likewise operate up to 5.5 V with 7 V absolute maximum. U14 VIN remains connected despite its disabled state. A possible 10 V LC excursion therefore exceeds the input ratings themselves, irrespective of desired output voltage.

**Rejected:** using an absolute maximum as a regulated operating target or assuming a short VIN pulse is allowed because TPS62088 separately specifies a 10 ns SW-node transient rating. All five exposed regulator inputs need margin below the 5.5 V operating ceiling, and downstream rail response remains to be checked. This alone is not a complete board overvoltage qualification: R73/R74 still divides target5V directly into ST-LINK PB1/T_PWR_EXT, bypassing regulation. PB1 is an FT-capable pin, so do not assign a generic 3.3 V GPIO clamp limit without its actual mode/supply conditions.

**Evidence:** [TPS62088 RevF sections6.1/6.3](https://www.ti.com/lit/ds/symlink/tps62088.pdf#page=4); [LD39020 Rev6 tables2/5](https://www.st.com/resource/en/datasheet/ld39020.pdf#page=5); [ST1S31 Rev5 tables2/4](https://www.st.com/resource/en/datasheet/st1s31.pdf#page=5); [C02 schematic sheets9/13](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), locally inspected power-sheet9 and independently audited ODB nets. U42 removed, U10 feed isolated by D2 removal, U25 isolated through absent CN9 shunts, and U26 fed by AUX3.3 rather than direct5V. No hardware action or changed bench state.

## 2026-11-06  A clamped inductor can limit charging slew, but saturation is not a voltage-controlled bypass

**Why:** the user proposed a Zener clamp plus deliberately saturating inductor. A properly designed shunt clamp can bound an LC excursion with low steady-state loss (winding I²R plus clamp leakage), but the 5.0-to-5.5 V margin requires actual pulse-current clamping, temperature/tolerance and source-voltage checks. Zener nominal voltage at a stated test current is not its maximum surge clamp voltage. An ordinary unsaturated inductor already has only winding resistance at steady DC; saturation is unnecessary for that benefit and reverses as current falls.

**Rejected:** importing the resistor-capacitor intuition that charging current is already small when capacitor voltage approaches the source. For an ideal unloaded linear LC step, i(Vc)=sqrt[(C/L)(2VsVc−Vc²)]; at Vc=4.5 V on a 5 V source current is 99.5% of its peak, and at 5 V it peaks. Falling differential voltage reduces di/dt, not the existing current. Tuning saturation at this point responds to current/flux, not directly to capacitor voltage, and is tolerance-sensitive; it does not remove stored energy or provide a persistent bypass. A nonsaturating inductor with explicitly designed clamp/damping remains a possible experiment, not a selected board modification.

**Evidence:** independent offline analytic check; for illustrative zero-resistance, no-load 5 V / 44 µF / 4.4 mH with an ideal 5.3 V shunt clamp, clamp starts at 0.499 A, dissipates initially 2.65 W and takes 7.32 ms to reduce current to zero. Clamp energy is 9.68 mJ, including continuing source energy; it is not limited to the 0.548 mJ stored in the coil. Eclamp=Vclamp/(Vclamp−Vs)·Ecoil at clamp entry. These are not predictions for the loaded Nucleo, and residual LC ringing/damping still matters. [Nexperia BZX84 voltage/tolerance/differential-resistance specifications](https://assets.nexperia.com/documents/data-sheet/BZX84_SER.pdf), [Coilcraft saturation/current-loss definitions](https://www.coilcraft.com/en-us/resources/application-notes/getting-started-an-introduction-to-inductor-specif/). No component selected, no hardware action; target remains in the prior OFF checkpoint.

## 2026-11-06  Try a static series resistor before adding a bypass switch

**Why:** the user selects a passive-resistor experiment first, retaining an MCU-controlled bypass as a later option. Recommend 2.2 ohms on the present regulated 5 V supply, with 1 ohm as a fallback if startup fails. Nominal 5/R is 2.27 A; running drops are 0.286 V at 130 mA and 0.440 V at 200 mA. Replaying the three C17-removed current traces from 5 ms to plateau gives 6.03–6.47 mJ of resistor dissipation. This supersedes the earlier controlled-slew-switch preference as the next proposed experiment, not its electrical rationale. Exact available part and installation remain unconfirmed.

**Rejected:** treating projected resistor heat as an equal increase in battery/source energy (some replaces LDO loss, while buck input current changes); applying the unchanged measured startup waveform through R; assuming successful later operation proves startup headroom; or relying on firmware to rescue a supply that stalls before the bypass GPIO executes. The native traces contain a separate 1.311–1.312 A peak at about 1.49 ms, still an unqualified startup observation. A later parallel MOSFET must default off, have appropriate gate level shifting, and avoid a second surge when bypassing residual voltage. No bypass pin or firmware change is selected.

**Evidence:** [offline projection with source identities and sample windows](evidence/2026-11-06-series-resistor-estimate/projection.json), independently calculated from the three [C17-removed runs](evidence/2026-11-06-c17-removed/README.md). Nominal 44 uF gives an unloaded RC time to 99% of 0.446 ms and 0.55 mJ charging heat; these do not model regulator startup. Proposed hookup is JS OUT+ → resistor → CN5.5, with existing return unchanged; JS voltage is upstream, so actual downstream voltage needs separate observation. Choose a pulse-rated part, not solely by steady wattage ([Vishay pulse-rating guidance](https://www.vishay.com/en/resistors/resistor-pulse-selector/)); resistor/bypass is a standard topology ([Nexperia IAN50020](https://www.nexperia.com/applications/interactive-app-notes/IAN50020_Power_Switch_MOSFETs)). No instruments operated, physical change confirmed, or firmware installed; prior OFF checkpoint remains unchanged.

## 2026-11-06  Qualify downstream rail sequencing rather than only the input ramp

**Why:** the second native current peak is at 1.486–1.491 ms, while the first validated receiver-entry phase marker is at 23.652–23.882 ms, exposure mirror at 24.770–24.991 ms and SD initialization at 36.440–36.693 ms. Existing markers therefore cannot attribute this early pulse to a rail or device. C02 hardware starts main/AON LDOs directly from the input, then the MCU's PWR_ON enables core and AUX regulators. Their charging and downstream startup are plausible sources, not identified causes. U17's typical 250 us delay plus 1 ms ramp supplies timing context only.

**Rejected:** interpreting early undriven GPIO chatter as first code, assigning the pulse to image capture/host SD initialization, or assuming reset waits for the input to reach 5 V. U17/U34 power-good outputs do not gate NRST. A resistor must preserve actual downstream rise/tracking/headroom; a successful later photo alone does not establish those requirements. No resistor installation, new measurement or firmware change is confirmed; prior OFF checkpoint remains.

**Evidence:** [three-run marker extraction](evidence/2026-11-06-series-resistor-estimate/startup-marker-alignment.json); [C02 sheets3/9/12/13](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf); [TPS62088 section7.3.4](https://www.ti.com/lit/ds/symlink/tps62088.pdf). Current [DS14791 Rev11, Tables25–27, pp141–143](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=142) gives main/AON POR 1.62–1.71 V, core-ready 0.61–0.71 V, and minimum core-ready delay 180 us. VDD/AON/core rise/fall time per volt is 20–1500 us/V. To reach the nominal-mode minimum 0.782 V after earliest 0.61 V detection, conservatively require that segment in under180us (~0.956V/ms), with margin. This derivation supersedes AN6000 Rev1's older 200us/0.86V/ms assumption for qualification; do not treat it as a newly published ST limit or measured board slope. [AN5967 Rev6 sections3.5.1/3.5.3](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=8) additionally allows AON POR crossing at most250us after VDD's and requires AON no more than50mV aboveVDD when above0.6V. Proposed first scope alignment is board input CN5.5, PWR_ON TP19, core TP12 and NRST CN3.14; main TP13, AON TP15 and AUX TP5/TP16 remain follow-up rails. No probes were moved.

## 2026-11-06  The static 2.2-ohm resistor passes three cold capture cycles

**Why:** the user installed 2.2 ohms, reported reduced peaks and asked for confirmation. Three unchanged normal cold cycles reproduce initial peaks of 1.738–1.744 A and secondary peaks of 1.049–1.052 A, versus baseline medians6.140/1.311A. All eleven phase markers and one exposure appeared each time; saved slots174–176 passed all3730sectors at25MHz, independent RAW10/PNG sample decoding and root visual review. Exposure remains24.58–25.27ms and sleep3.309mA. This establishes a useful passive prototype result before considering a bypass MOSFET; no bypass hardware or firmware was added.

**Rejected:** attributing the median159.97→222.19mJ post5ms energy increase entirely to resistor loss. Longer SD activity dominates: about81% of the difference is explained arithmetically by extra phase duration at baseline power, while a closest-duration cycle used5.28% more energy. These are historical comparisons, not a randomized same-card resistor-removal A/B. Also reject claiming original sensor-RAM equality after Standby, payload-checksum protection, measured downstream voltage/ramp compliance, or LiPo operation from these passes.

**Evidence:** [three-run current/energy comparison, full-image proofs, visual review and final state](evidence/2026-11-06-series-resistor-tested/README.md). Source is regulated5V throughJS; resistor placement afterJS is inferred from the user's installation and prior instructions, not physically inspected. Native startup peaks remain instrument observations. Warm allocation173 was excluded from coldmetrics. Exact normal prefix reverified; noNORprogramming/fullNORreread orSDerase/deletion. Final exactUARTpark preceded intentionaloutputOFF at2026-11-06T17:03:19.096403UTC; otherinstrumentsettingsrestored, COM8closed/BREAKreleased, nohelperactive. The normalOctober28single-frame firmware and other hardware removals remain unchanged.

## 2026-11-06  Retain 2.2 ohms for the LiPo prototype and use a high-side MOSFET latch

**Why:** the user accepts the static 2.2-ohm resistor for now, announces a switch to a 500mAh LiPo, and asks which parts from the purchased Amazon kit suit momentary-button startup and GPIO power hold. The earlier shopping exchange identifies the VANXY 160-piece assortment, ASIN B0FD77Y9KZ, with AO3401 P-channel and AO3400 N-channel parts. Recommend AO3401 for the positive-supply switch and AO3400 for the GPIO-controlled gate pull-down. AOS specifies AO3401 resistance no greater than85mohm at VGS=-2.5V and25C; the control AO3400 also has a2.5V gate-drive specification. These are manufacturer reference specifications, not verification of the kit's actual vendor or delivered devices.

**Rejected:** bypassing the accepted resistor as part of this latch; using AO3400 alone as an unboosted high-side switch; driving a4.2V-source P-MOS gate directly from a3.3V MCU output; treating battery capacity as proof of discharge capability or board voltage headroom. The main P-MOS source goes to battery positive, drain toward the retained resistor/DUT, with a gate-source pull-up; the button and NMOS sink its gate to turn on. A held button keeps power on in this simple topology. GPIO selection and the delayed master cutoff needed for orderly AUX/core versus main/AON shutdown remain to implement and qualify. Single-PMOS reverse-feed isolation, off leakage, and LiPo operation across charge state are not established by the regulated5V resistor tests.

**Evidence:** direct user decision in this chat; November3 shopping recommendation in thread01a1901b-e53c-7f33-9c26-2cc22d2c08b4 (recorded2026-11-04T00:02:27Z); [kit listing](https://www.amazon.com/dp/B0FD77Y9KZ); [AOS AO3401 datasheet](https://www.aosmd.com/sites/default/files/res/datasheets/AO3401.pdf) and [AO3400 datasheet](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400.pdf). No wiring inspection, instrument action or firmware change accompanied this recommendation. The announced source change means the preceding bench5V checkpoint is historical until actual connections are checked.

## 2026-11-07  Reserve PD7 HOLD and delay cutoff at the NMOS gate

**Why:** the user requests a concrete latch diagram and convenient header. Choose PD7 on ArduinoD9/CN14.2, also CN15.19 besideGND20. C02 net167 is unloaded except MCU and these headers; the installed capture uses other GPIOD bits only. A diode-isolated1kohm GPIO feed charges the AO3400 gate's1uF/100kohm RC. The button now feeds that same RC from VBAT through its own1kohm, stretching startup as well as shutdown. This replaces the previously described direct button-to-PMOS-gate pull-down. Q1 retains100kohm gate-source bias and adds10nF gate-source capacitance to reduce hot-plug false turn-on. Existing2.2ohm remains in the main path.

**Rejected:** using occupied PD0/PD12, PE0, PE1, PE6 or PE11; allowing button voltage or stored capacitor charge into PD7; a large PMOS-gate capacitor as the sole shutdown delay, which also changes main-switch slew; calling the100ms RC time constant a guaranteed cutoff interval; treating the new drawing as installed HOLD firmware or LiPo qualification. The existing100ms UART BREAK may exhaust RC hold during reset: initial recovery requires the button held or bridged until autonomous behavior is qualified. These values are first-test selections, not rail-order proof.

**Evidence:** [canonical diagram, exact component connections, firmware contract and limitations](2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring); UM3417 Rev4 Tables18/20 and C02 ODB net167(U21-E12,CN14-2,CN15-19), DS14791 Rev11 PD7/mainVDD note2; official AOS/Vishay references linked there. Root visually inspected both MOSFET package drawings and the rendered wiring figure; independent offline reviews checked pin conflicts and RC behavior. No instruments operated or firmware changed.

## 2026-11-07  Q1 transfer curves do not predict camera current from gate voltage alone

**Why:** the requested AO3401 chart uses the manufacturer's typical 25/125°C curves at fixed VDS=-5V. The actual LiPo latch has a changing drain voltage, charging capacitors, regulators and a series resistor. Its fully-on current is load-dependent; a gate-to-ground axis translated for a3.7V source does not change the datasheet test conditions.

**Rejected:** treating the typical curve as a measured kit-part current limit, clipping it at Vbattery/2.2ohms to claim a board-current model, or assigning precise low-current thresholds from a source figure spanning20A. The resistor's1.68A at3.7V /1.91A at4.2V references are ideal initial-charging ceilings, not expected steady currents.

**Evidence:** [chart, digitized vector data and conditions](2026-10-14-power-tree-review.md#q1-current-versus-gate-voltage), AO3401 Rev6.1 Figure2. Source PDF SHA256 `a6abd2ad26b7305d45c71b3a7cbc6196410ddbc9124c4316a34b9aac2ca1b89a`; independent offline curve review and root visual inspection. No hardware or firmware changes.

## 2026-11-07  Open-drain mode does not qualify a direct battery connection to GPIO

**Why:** the user asks whether a GPIO can tolerate external voltage during power-down. STM32N657 GPIOs, including PD7, are TT rather than five-volt-tolerant. A charged4.2V LiPo exceeds their3.6V absolute input ceiling. Open-drain selection changes output behavior, not pad voltage ratings. Retain the external Q2 and diode isolation in the proposed latch.

**Rejected:** treating the generic3.6V unpowered maximum in AN4899 as a guarantee of negligible leakage; claiming every positive unpowered-pin voltage necessarily damages the MCU; or equating a still-powered backup domain with a fully unpowered chip.

**Evidence:** [DS14791 Rev11](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), Tables17/18/22/25 and section3.7; [AN4899 Rev4 section6.3](https://www.st.com/resource/en/application_note/an4899-stm32-microcontroller-gpio-hardware-settings-and-lowpower-consumption-stmicroelectronics.pdf#page=26). Independent offline review agreed. No hardware or firmware changes.

## 2026-11-07  Moving SW1 across Q2 permits removing R3, but D1 also preserves cutoff delay

**Why:** the user proposes SW1 across Q2 drain/source and removing D1/R3. This is a valid startup topology: the button pulls Q1 gate to ground without applying battery voltage to the Q2 gate or GPIO. R3 can be omitted. However, D1 also prevents GPIO LOW from discharging C1 through R4. Without it, the existing1kohm/100kohm/1uF values give approximately0.99ms rather than100ms nominal discharge time constant, before transistor switching effects. Recommend retaining D1 for the existing LOW-before-Standby contract.

**Rejected:** calling removal of both parts behavior-equivalent. Moving SW1 loses the C1 button-pulse stretch; the press must last until firmware establishes HOLD and charges C1. Hi-Z release could retain the longer decay while powered, but leaves a possible C1-to-unpowered-GPIO current path as VDD falls. Removing D1 therefore needs changed cutoff design and rail-sequence qualification. This records review of a proposed simplification, not a confirmed wiring change; the canonical drawing and firmware remain unchanged.

**Evidence:** independent circuit review and offline RC calculation, R4||R2=990.099ohms; [current latch values and firmware contract](2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring); [AN5967 Rev6 section3.5.2](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=9) requires auxiliary rails below0.6V before main supplies leave operating conditions. No bench action.

## 2026-11-07  PD7 has main-rail power but releases its output in Standby

**Why:** PD7 at CN15.19 / ArduinoD9(CN14.2) already uses main VDD, not switched AUX. RM0486 specifies ordinary I/O as high impedance without pulls in Standby. This supports a future alternative where entering Standby itself releases HOLD and starts C1 decay, rather than explicitly driving LOW first. The pad supply remains present during AUX shutdown.

**Rejected:** equating a powered pad with retained HIGH output, or claiming AUX shutdown alone unpowers PD7. The diode-removal concern occurs later, when Q1 cuts the main feed and residual C1 voltage may exceed the falling VDD. Standby-triggered release and cutoff timing remain untested; no wiring or firmware change is selected by this clarification.

**Evidence:** [DS14791 Rev11](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), PD7 Table18/p98 and supply note2/p112; [RM0486 Rev4 p383, I/O states in Standby](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf#page=383), checked against local extracted manual lines23090–23102. No bench operation.

## 2026-11-07  Prefer hardware PWR_ON for the proposed latch HOLD source

**Why:** the user proposes replacing the GPIO with PWR_ON while retaining delayed Q2 release. PWR_ON asserts after main/AON POR, before core startup and ROM execution, and deasserts on Standby entry. It can therefore establish HOLD without firmware GPIO setup and begin the external cutoff delay at the same event that disables AUX. Recommend SW1 across Q2 drain/source, omit R3, and feed Q2's gate from PWR_ON through R4 and forward D1; retain R2=100kohm/C1=1uF and Q1's existing network/2.2ohm path. For the first test, recommend R4=10kohm instead of1kohm to reduce added PWR_ON charging load to at most0.33mA at3.3V (ignoring diode drop). Ideal charging time constant is9.09ms; discharge through R2 remains100ms nominal, not a guaranteed cutoff time.

**Rejected:** attaching C1 directly to the regulator-enable net, or deleting D1: capacitor charge must not hold PWR_ON/AUX enables high or be drained through the LOW output. Do not assume general GPIO drive specifications prove this dedicated output's loaded startup behavior. Button duration, loaded PWR_ON voltage/edge, full main/AUX shutdown sequencing and reset/recovery remain to qualify. TP19 is the verified takeoff, not an Arduino/Morpho contact. A future independent USB target supply could assert PWR_ON and reconnect the battery unless source selection/inhibition is provided.

**Evidence:** [RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), local Rev4 p355 startup and p383 Standby; [AN6000 power-management sequence](https://www.st.com/content/st_com/en/technical-documents/an6000-how-to-build-the-discrete-power-supply-for-stm32n6-mcus-stmicroelectronics_asset/chunk-002-topic-an6000-powermanagement.html); C02 sheet9/ODB net66 maps TP19, U21-E2, U34EN and links R34/R85/R22(DNP), with no header. This is the preferred next circuit proposal, superseding PD7 as the recommended HOLD source, not a reported physical change. The existing drawing still depicts the earlier PD7 version; no hardware operation or firmware change occurred.

## 2026-11-07  Abrupt input removal does not provide a timed main-supply hold-up sequence

**Why:** the user asks how the current Nucleo shuts down when its 5V input is removed. C02 sheet9 ties main3.3 U33 and AON1.8 U23 enables directly to that input; core U17, AUX3.3 U34 and AUX1.8 U26 are enabled by PWR_ON. No independent input-fail supervisor or delayed main cutoff appears in this power circuit. AN6000 describes uncontrolled loss: input/output capacitors discharge, regulators lose headroom, then a main VDD or AON power-down reset makes PWR_ON high impedance with an internal approximately40kohm pull-down, disabling auxiliary/core regulators. DS14791 Rev11 gives both falling PDR thresholds as1.58–1.67V (1.63V typical). Individual regulator undervoltage cutoffs can act earlier, so this is a control mechanism, not a measured strict order of rail falls. U17 and the fitted U26 ordering code provide output discharge on disable; U34 has no documented explicit active-discharge function.

**Rejected:** interpreting a successful abrupt power cycle, PWR_ON enable wiring, or regulator power-good outputs as proof of compliant rail fall timing. AN5967 Rev6 requires AUX below0.6V before main supplies leave operating conditions; our modified board's actual falling waveforms are not measured. C14/C17 removals change stored charge without adding a sequencer. A normal completed cycle already enters Standby and disables AUX before input removal. The proposed PWR_ON/diode/RC latch deliberately retains healthy input/main power during AUX shutdown; it remains unbuilt and unqualified.

**Evidence:** root and independent offline visual inspection of C02 sheet9; [AN6000 uncontrolled-power-down description](https://www.st.com/content/st_com/en/technical-documents/an6000-how-to-build-the-discrete-power-supply-for-stm32n6-mcus-stmicroelectronics_asset/chunk-002-topic-an6000-powermanagement.html), [DS14791 Rev11 Table27](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=142), [AN5967 Rev6 section3.5.2](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=9). No bench actions, firmware changes or new waveform measurements.

## 2026-11-07  PDR-triggered cutoff does not explain compliance with the newer shutdown requirement

**Why:** the user correctly challenges the preceding uncontrolled-shutdown explanation: waiting until main VDD reaches approximately1.63V cannot itself guarantee AUX below0.6V while main remains within its3.3V operating range. DS14791 Rev11 Table25 sets that VDD range to3.0–3.6V; Table27's PDR is lower. AN6000 Rev1 (November2024) describes the late-PDR uncontrolled sequence, while AN5967's main/AUX sequencing section was added in Rev5 (August2026) and updated in Rev6 (September2026). The C02 board schematic is dated May2024. This establishes a documentation/design reconciliation question, not proof of a specific measured failure or permission to ignore the newer requirement.

**Rejected:** claiming PDR alone guarantees compliant shutdown, treating3.3V-mode VDD as fully valid down to1.63V, assuming a special exception for sudden input loss without ST confirmation, or assuming regulator UVLO/capacitor discharge will always rescue the ordering. The previous note describes a fallback mechanism only. Actual rail traces and an ST clarification are needed to explain arbitrary input removal; controlled Standby followed by a qualified delayed main cutoff remains the proposed design approach.

**Evidence:** [DS14791 Rev11 Tables25/27](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=140), [AN6000 Rev1 section3.2](https://www.st.com/resource/en/application_note/an6000-how-to-build-the-discrete-power-supply-for-stm32n6-mcus-stmicroelectronics.pdf#page=9), [AN5967 Rev6 section3.5.2 and revision history](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=9), independent offline review. No explicit uncontrolled-loss exception found in the reviewed sources. No instruments operated or firmware changed.

## 2026-11-07  ST forum guidance distinguishes direct shutdown historically but does not reconcile the current limit

**Why:** the requested forum/errata search found a material qualification to the previous search result. In the March14,2025 thread [Details of Power down sequence of STM32N657X0H3Q](https://community.st.com/stm32-mcus-products-25/details-of-power-down-sequence-of-stm32n657x0h3q-148564), ST employee RomainR explicitly accepted turning all supplies off at once as complete direct shutdown. His January28,2026 follow-up pointed to AN6000's uncontrolled sequence and promised improved AN5967 figures. A later [STM32N6 Power On sequence](https://community.st.com/stm32-mcus-products-25/stm32n6-power-on-sequence-161758) reply on September3,2026 from ST Technical Moderator mEALLEm, relaying the team's answer after internal ticket CDM0065534, says the power-down sequence must be followed; otherwise inter-supply currents can cause spikes and an unstable shutdown state. These are relevant ST statements with differing scope/date, not a clear modern resolution of PDR approximately1.63V versus main-valid/AUX-below0.6V.

**Rejected:** continuing to say no ST staff has allowed direct shutdown; treating the older allowance as an explicit exception in AN5967 Rev6; treating the later reply as a measured Nucleo defect; or declaring that nobody has raised the exact threshold mismatch. Public search and retrieved replies did not establish an answer to that exact question. The older thread has collapsed replies in its text view, so coverage is not exhaustive. No support message was posted and no internal ticket accessed.

**Evidence:** sources above checked November7,2026. Official [ES0620 Rev5, August2026](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf) lists no erratum resolving this shutdown-order/PWR_ON-threshold issue; reviewed summary, System entries and revision history. Section2.2.29 separately says PVM monitoring does not operate on VDDIO2/3/4/5, USB33 and VDDCORE, so those monitors are not an assumed firmware workaround. The related [June24,2026 Nucleo schematic-discrepancy reply](https://community.st.com/stm32-mcus-boards-and-hardware-tools-26/nucleo-n657-schematic-discrepancy-vs-an5967-regarding-vdda18pmu-vddsmps-165225) calls for active core discharge but does not resolve the late PDR trigger. No hardware or firmware change; controlled Standby plus qualified delayed main cutoff remains the proposal pending clearer ST guidance and rail measurements.

## 2026-11-07  Request ST clarification of PWR_ON versus the AUX shutdown requirement

**Why:** the user explicitly requested drafting and publishing an ST forum question, then confirmed login and publication. The question asks whether AN5967 Rev6 applies to abrupt common-input removal, how the stock Nucleo meets the requirement, and whether a new design needs earlier input-failure detection and main-supply hold-up. It cites the document revisions, schematic enable paths, PDR limits and differing historical ST replies.

**Rejected:** claiming a measured stock-board defect or treating the open question as permission to ignore sequencing. Publication does not resolve the electrical requirement. The preceding note's no-message-posted statement describes the earlier search boundary; a question is now published and awaiting clarification.

**Evidence:** [published ST Community topic](https://community.st.com/stm32-mcus-products-25/stm32n6-nucleo-power-off-pwr-on-at-1-63-v-vs-aux-before-main-requirement-169308), author bigjosh, STM32 MCUs Products, STM32N6 series tag; [exact text and publication screenshot](evidence/2026-11-07-st-shutdown-question/README.md). The resulting topic page showed the complete text and zero replies. No hardware or firmware changes.

## 2026-11-07  Keep prototype power and GPIO HOLD on Arduino headers

**Why:** the user explicitly chooses GPIO control to keep all power-latch board connections on Arduino headers for easier assembly. PD7 at Arduino D9/CN14.2 is the canonical HOLD contact; target input remains CN5.5 and common return CN5.6. Retain the diode-isolated RC off-delay so the external main switch can remain on during Standby entry and auxiliary shutdown.

**Rejected:** the intervening recommendation to use PWR_ON at TP19 as external HOLD, and CN15.19 as the latch assembly endpoint. PWR_ON retains its existing onboard regulator-control role. GPIO HOLD requires firmware takeover after boot; that implementation, button/recovery continuity and actual rail-shutdown timing remain to qualify. This pin decision does not select the separately discussed SW1 simplification or change the drawn component values.

**Evidence:** direct user instruction in this chat on November7; [updated canonical connection plan and diagram](2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring), using the previously checked PD7 header/net mapping. No firmware, instrument or physical board changes accompanied this documentation update.

## 2026-11-07  Put SW1 across Q2 and omit R3

**Why:** after the R3 explanation, the user explicitly selects the simpler button hookup. SW1 now connects Q2 drain/pin3 (also Q1 gate) directly to Q2 source/pin2/GND. It turns on Q1 without charging the Q2 gate capacitor. Omit R3 and the former VBAT-to-button-to-HOLD_RC branch. GPIO HOLD remains PD7 at Arduino D9/CN14.2; retain R4=1kohm, D1 with its band toward Q2 gate, R2=100kohm and C1=1uF, plus the existing Q1 network and 2.2-ohm input resistor.

**Rejected:** removing D1 with R3, or retaining the claim that C1 stretches the initial button pulse. The button must stay closed through boot and sufficient GPIO-driven C1 charging. D1 preserves the intended off-delay against a LOW or unpowered GPIO; 100ms is the nominal R2/C1 time constant, not a qualified cutoff time. A held button continues overriding master power-off.

**Evidence:** direct user instruction, updated [component table, operation and diagram](2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring), and independent circuit review. This selects the assembly plan; no physical rewiring, firmware installation or bench qualification was performed.

## 2026-11-08  Separate the proposed held-button trigger capacitor from shutdown hold-up

**Why:** the user proposes an SPDT trigger whose common terminal connects a
ground-referenced capacitor to GND when released and Q1's gate when pressed.
The discharged capacitor initially pulls the gate low; R1 subsequently charges
it toward VBAT unless firmware turns Q2 on. After Q2 releases, a continuously
held switch permits only a finite charging transient, followed by leakage.
However, releasing the switch disconnects that capacitor from Q1. It neither
stretches a too-short press after release nor preserves the previous C1/R2
shutdown delay in that button state.

**Rejected:** treating the new trigger capacitor as a replacement for the
independent Q2-gate C1/D1 off-delay; claiming a permanently held button forces
unlimited power after Q2 releases; or claiming this circuit independently
times out a firmware failure that keeps Q2 asserted. The marked-up drawing
appears to remove C1 and bypass D1 as well as omit C2; clarification is pending.
The recommendation is to retain C1/D1 until AUX/main shutdown timing is
qualified. C2's source-to-gate transient suppression is a separate function.
No new capacitor value, physical wiring or canonical diagram is selected.

**Evidence:** user SPDT proposal and annotated latch drawing, November8;
first-principles circuit review; [existing component roles](2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring);
[AN5967 Rev6 section3.5.2](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf#page=9)
requires AUX below0.6V before main supplies leave operating conditions.
For a held switch before Q2 takeover, the idealized gate drive magnitude is
VBAT*exp(-t/(R1*Ctrigger)); use the required load-current gate drive, not
VGS(th), to estimate useful startup margin. [AO3401](https://www.aosmd.com/sites/default/files/res/datasheets/AO3401.pdf)
specifies on-resistance at VGS=-2.5V. No instrument access or firmware change
occurred in this review. The normal camera FLASH still lacks installed PD7
HOLD; the live RAM knob diagnostic is a different program.

## 2026-11-08  Accept no separate Q2 shutdown delay for the SPDT prototype

**Why:** when asked about the marked removal of C1 and bypass of D1, the
user explicitly declined retaining that delay, citing the manufacturer's
reference board behavior. For this prototype, remove external C1 and D1;
PD7 drives Q2's gate through retained R4=1kohm, with R2=100kohm to ground.
The user also reports omitting external C2 because the battery will be
permanently soldered in. The SPDT trigger-capacitor direction is retained.

**Rejected:** blocking this experimental circuit choice on the previous
unqualified RC off-delay recommendation, or silently putting C1/D1 back in
the next diagram. This is acceptance of the prototype tradeoff, not evidence
that the AN5967 shutdown-order question has been resolved or that the
manufacturer's board establishes compliant rail timing. The prior 1uF/100kohm
off-delay is no longer part of the selected external circuit.

**Evidence:** direct user reply, "the reference PCB from the manufacturer
itself does not seem to abide this delay - we do not need to," after the
C1/D1 clarification. No hardware inspection, instrument action or firmware
change accompanied this decision. R1=100kohm with a new2.2uF trigger cap and
1kohm in the released/reset throw is a suggested first-test sizing, not a
measured takeover guarantee. At ideal3.7V, |VGS| reaches2.5V after about86ms;
the minimum held press still must outlast PD7 takeover because release
disconnects the trigger capacitor from Q1's gate.

## 2026-11-08  Make the capacitor SPDT latch the canonical prototype wiring

**Why:** the user requests the revised diagram and component connections after
explicitly accepting omission of C1/D1 and C2. Select C3=2.2uF X7R/10–16V
from switch common to GND; momentary break-before-make SW1 connects common
to R5=1kohm/GND when released and Q1 gate/Q2 drain when pressed. Keep
R1=100kohm gate-to-source, PD7/D9/CN14.2 through R4=1kohm to Q2 gate,
R2=100kohm gate-to-ground, and the existing2.2ohm main-path resistor.
All battery/latch current passes through the upstream Joulescope. Power and
return remain Arduino CN5.5/6. The current drawing and connection table now
replace the superseded normally-open button and Q2-gate RC circuit.

**Rejected:** silently retaining the previously recommended off-delay,
connecting the SPDT common to Q1 gate instead of C3, putting R5 in the
pressed path, or calling a held trigger a permanent programming bypass.
Releasing too early disconnects the startup capacitor; HOLD must already
be established. Held-button timeout starts only when Q2 releases, and
does not override firmware stuck holding Q2 on. The nominal220ms pulse
time constant and approximately11ms reset interval are component estimates,
not measured takeover/cutoff or rail-sequencing guarantees.

**Evidence:** direct user request on November8; [canonical diagram and table](2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring),
[SVG](lipo-latch-wiring.svg), [PNG](lipo-latch-wiring.png), generated by
`tools/build_lipo_latch_wiring.py` and visually inspected. No hardware,
instrument, installed-firmware or measured-timing change accompanied this
documentation update; the requested HOLD qualification is separate work.

## 2026-11-08  Omit R4 and retain gate damping as a measured follow-up

**Why:** after reviewing the optional gate and switch-reset resistors, the
user chooses to omit the gate resistor for simpler prototype assembly and
restore it if ringing becomes an issue. Connect PD7 / Arduino D9 / CN14.2
directly to Q2/AO3400 gate pin1, retaining R2=100kohm to ground. R4 is no
longer fitted. The reference to gate ringing identifies R4; R5=1kohm in the
SPDT's released/reset path remains selected, along with C3=2.2uF.

**Rejected:** retaining R4 as a mandatory latch component, silently removing
R5 as well, or treating a roughly50ms button press as proof that the earlier
GPIO-edge transient is harmless. Direct drive is an accepted prototype
tradeoff, not a measured gate-waveform qualification. If ringing, overshoot
or GPIO-drive problems appear, restore series damping starting with the
previous1kohm value and measure the result. Keep the existing low-speed
push-pull HOLD configuration and external R2 default-OFF path.

**Evidence:** direct November8 instruction to remove the gate resistor and
note adding it back if ringing becomes an issue; [updated canonical wiring](2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring)
and regenerated PNG/SVG. The [AO3400 datasheet](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400.pdf)
lists630pF typical input capacitance under its stated test conditions; the
former external1uF Q2 gate capacitor was already removed. No firmware,
instrument or physical-board operation accompanied this documentation
change. R1/C3 startup-window estimates are unchanged; frozen earlier
evidence retains its then-selected R4 circuit.

## 2026-11-08  Use USB-controlled reverse-oriented PMOS as the low-loss battery-isolation proposal

**Why:** the user proposes replacing the battery ORing diode with another kit
PMOS whose gate follows USB and has a ground pull-down. Another AO3401 is a
suitable prototype candidate: Q3 drain/pin3 faces the existing Q1 battery
output, source/pin2 faces the shared system input, and gate/pin1 connects to
protected USB5V before the retained USB Schottky, with100kohm to ground.
This orientation makes Q3's body diode point battery-to-system. Valid USB5V
turns Q3 off; absent USB lets the pull-down enable its low-resistance channel.
The existing SPDT/C3/R5 and Q2/PD7 control stay unchanged. SB12 pad1 is the
accessible top-side USB takeoff near CN8, on exactly the CN9.3/5V_USB_SNK net;
leave the fitted bridge intact and CN9 shunts absent.

**Rejected:** using Q3 in Q1's original source-to-battery orientation, tying its
gate to the combined output, or calling an always-on MOSFET a reverse-blocking
diode. This is USB-presence source selection, not closed-loop ideal-diode
control: unplug/plug transients, residual charge and actual kit parts remain
to qualify. The user's proposed R0 placement immediately after Q1 drain is
electrically valid and leaves the USB branch unresisted, but the premise that
inrush occurs only on battery power is rejected. The direct5V November6
measurements were6.140A without R0 versus1.743A with2.2ohms. Recommend retaining
common-path limiting initially, or separately qualifying/limiting USB startup
before bypassing it. Removing the battery diode does not remove R0's voltage
drop or qualify direct-LiPo regulator headroom. No canonical wiring promotion,
physical modification, firmware update or bench action occurs in this review.

**Evidence:** direct November8 questions; [Microchip AN1149 figures5-7](https://ww1.microchip.com/downloads/en/appnotes/01149a.pdf),
[AO3401 datasheet](https://www.aosmd.com/sites/default/files/res/datasheets/AO3401.pdf)
(85mohm maximum atVGS=-2.5V under its25C test conditions),
[measured resistor comparison](evidence/2026-11-06-series-resistor-tested/README.md),
and MB1940 C02 ODB net382 endpoints SB12.1/CN9.3. USB branch diode choice and
transition testing remain open; this circuit does not charge the LiPo.

## 2026-11-08  Restrict power consolidation to parts on hand; investigate reusing U6

**Why:** the user explicitly restricts the simpler consolidated power design
to parts already available, including components on the Nucleo. A new
dual-input regulator/evaluation board is therefore outside this prototype
scope. The fitted U6/TPS259535DSG is a useful consolidation candidate: as a
common master switch after USB/battery selection, it can combine enable/HOLD,
controlled startup slew and current limiting, potentially replacing external
latch Q1/Q2 and the 2.2-ohm resistor after qualification. Retain source
selection/isolation separately: one kit AO3401 in the previously reviewed
reverse orientation and a USB power diode. Removed board D2 is BAT20JFILM
and is a possible diode donor only if retained and intact. The SPDT capacitor
would need a positive enable pulse instead of the existing negative PMOS-gate
pulse; isolated PD7 HOLD and USB-present enable remain required.

**Rejected:** buying LTC3118/DC2045A for this constrained build; treating
U28/STMPS2151STR as an available fitted spare (it is DNF); or claiming U22/TCPP03
and its back-to-back consumer MOSFETs automatically provide ideal-diode
reverse blocking. TCPP03's consumer driver is VBUS-self-biased in the default
OFF/dead-battery state, with no specified reverse-current comparator. A
battery-fed system could sustain VBUS through an already-on consumer path
after unplugging; do not delete the USB diode on that assumption.

**Evidence:** MB1940 C02 sheet13 and ODB connectivity: U6 IN3/4 share raw
CN10 VBUS; EN2 directly shares debugger PB0; ILM7 has R7=3.9kohm to ground and
R6/R14 to debugger GPIOs; OUT5/QOD6 share5V_STLK, including an R8/R9 debugger
sense load. Repurposing therefore needs actual input/enable isolation and
sense/current-control rework, not just a jumper. Existing C18=10nF controls
slew; the [TI datasheet](https://www.ti.com/lit/ds/symlink/tps2595.pdf) specifies
3.3nF as a minimum, not maximum. TPS259535 operates from3.0V, has approximately
34-36mohm typical on-resistance, and lists40nA typical shutdown at VIN<=5V and
EN<0.5V without a maximum in that entry. This does not qualify whole-circuit
0.1uA: the upstream USB diode, trigger/control network and board paths add
leakage. It does not boost the LiPo or itself block reverse power; LiPo
headroom, handover transients, pulse timing, startup and shutdown still need
qualification. [TCPP03 tables7/12](https://www.st.com/resource/en/datasheet/tcpp03-m20.pdf)
and [BAT20J](https://www.st.com/resource/en/datasheet/bat20j.pdf) support the
isolation/donor audit. This is an offline proposal, not a canonical wiring
selection, physical modification or firmware/instrument operation.

## 2026-11-08  Try U6 consolidation in place rather than desoldering the WSON

**Why:** the user approves trying U6 and requests an SVG plus a comparison of
in-place rework versus removing the part. Recommend keeping U6 mounted:
the2x2mm WSON8 package has0.5mm-pitch pads and an exposed ground/thermal pad,
which are much harder to reconstruct with loose wires than to preserve on
the existing board. The [architecture SVG](u6-consolidated-power.svg) and
[preview](u6-consolidated-power.png) show the common master switch, retained
battery selector/USB diode and functional enable combining. They are not a
pin-level implementation of the trigger/HOLD/USB OR network or a trace-cut map.

**Rejected:** calling this jumper-only rework, recommending removal followed
by unsupported dead-bug wiring, cutting a guessed single input trace, or
operating hardware before the new physical arrangement is established. The
new input bypass must be connected to the isolated U6 input; leaving C25 on
its original USB net would not provide that bypass. The prior discrete latch
is superseded as the next experiment, not proven replaced on the bench.

**Evidence:** independent C02 ODB and sheet13 audit found U6 IN3/4 have two
rightward top connections and another pin4 connection to the VBUS_STLK pour,
with nearby vias into other layers. No removable input link exists. EN can
be contacted at R29.2 after isolating the debugger-side trace; retain R29.
OUT is C15.2/CN15.8/CN9.1; isolate R8's debugger sense load. R6/R14 isolate
debugger current-limit control; R7=3.9kohm and C18=10nF can remain as initial
settings. Exact cut locations require an enlarged layer rendering and
physical continuity verification; coordinate candidates are not published
as assembly instructions. ST-LINK's D1/CN10 supply and UART/SWD/reset routes
can remain intact. Package and functions are from the
[TI datasheet](https://www.ti.com/lit/ds/symlink/tps2595.pdf).
Existing C25=100nF/25V X7R can be reused: pad1 is GND, while its other terminal
must be removed from the old VBUS pad and reconnected to the isolated input
with a short loop. Bridging the original VBUS pad would undo isolation.
The diagram was generated by `tools/build_u6_power_proposal.py` and visually
inspected. No hardware, instrument or firmware operation occurred.

## 2026-11-08  Whole VBUS_STLK pour isolation moves the difficult cuts to CN10

**Why:** the user suggests keeping U6's input pour and isolating its other
connections. This is electrically possible. The complete raw debugger-USB
net has only these component endpoints: U6 IN3/4, CN10 A4/A9/B4/B9, D1
anode, U27 protection diode pad1, C58=100pF pad1, C25=100nF pad2, and the
unpopulated C57 pad2/U28 pin5 footprints. D1 is its only supply branch into
the debugger regulator. Retaining the pour could retain C25 directly.

**Rejected:** treating this net as the MCU USB input or target5V; leaving
D1 connected to a battery-fed pour, which would power the debugger while
U6 is off; or assuming a single connector-side trace cut isolates the whole
pour. CN10's four VBUS pads have multiple top escapes/vias into the internal
power layer. No single accessible upstream neck was found. Isolating all
connector VBUS routes plus rerouting a separate CN10-to-D1 debugger feed
appears harder than local U6 input isolation. Removing CN10 or depending on
a specially modified cable is not the preferred simplification. The EN,
current-limit and output-sense rework remains necessary with either approach.

**Evidence:** MB1940 C02 sheet13, ODB EDA net23 VBUS_STLK (CAD netlist389),
independent component-endpoint extraction and copper-layer review. The
endpoint record is `tmp/usb-power-review-20261108/vbus-stlk-endpoints.json`.
This is a layout-based recommendation, not a completed cut map or physical
continuity test; no hardware, firmware or instrument operation occurred.

## 2026-11-08  Return to the three-transistor discrete power plan

**Why:** after reviewing both local U6 input isolation and whole-pour isolation,
the user concludes there is little gain over discretes and asks to return to
that plan. Keep Q1/AO3401 battery OFF switching, Q2/AO3400 PD7 HOLD interface,
and reverse-oriented Q3/AO3401 USB-controlled battery selection, plus the USB
power Schottky. USB can directly power the merged rail without a separate
enable OR network. The existing SPDT trigger, 2.2-uF capacitor, 1-kohm reset
resistor and gate bias resistors remain; C1, C2, the old gate diode D1 and
R4 remain omitted. U6 reuse is deferred, not implemented.

**Rejected:** reducing Q1 and Q3 to one PMOS while claiming both complete
battery OFF and USB-to-battery blocking: either orientation leaves an
unwanted body-diode path. Common-gate pairing moves USB override into extra
control circuitry without a useful part saving. Direct battery-gate control
from unpowered PD7 is also rejected. Using the board's raw-VBUS divider
instead of Q3's pull-down would save a resistor but add a separate tap and
change unplug behavior; retain the simpler protected-USB takeoff. Do not
silently release HOLD during USB to save its battery-side bias current:
that would change the existing unplug/cleanup behavior and is outside this
hardware simplification.

**Evidence:** direct November 8 user decision; independent topology review;
[AO3401 datasheet](https://www.aosmd.com/sites/default/files/res/datasheets/AO3401.pdf)
and [Microchip AN1149](https://ww1.microchip.com/downloads/en/appnotes/01149a.pdf).
Recommend joining Q1 and Q3 drains directly and placing the existing 2.2-ohm
R0 after the merge, common to battery and USB. This is a proposed relocation,
not a new user-selected or measured wiring state: it limits both sources but
adds 0.22 V USB drop at 100 mA / 0.44 V at 200 mA, beyond the USB diode drop.
The [measured direct-5-V inrush](evidence/2026-11-06-series-resistor-tested/README.md)
supports retaining limiting on USB too. LiPo headroom, leakage and hot-plug
transients remain unqualified. The current power review supersedes the U6
direction and its diagram is marked deferred. No hardware, firmware or
instrument operation occurred.

## 2026-11-08  Put the 2.2-ohm resistor after the source merge in the complete wiring plan

**Why:** the user explicitly selects the common resistor placement and requests
a complete SVG including SPDT, HOLD, USB tap, values and pin numbers. Join Q1
and Q3 drains directly; Q3 source and USB diode cathode form MERGE. Route
MERGE through the existing pulse-rated2.2-ohm R0, then JS110, then CN5.5.
This gives both sources inrush limiting with one resistor and simpler MOSFET
assembly. The [canonical SVG](lipo-latch-wiring.svg), PNG and component table
now include the complete circuit rather than a battery-only latch plus a
separate USB proposal.

**Rejected:** the previous battery-only R0 location; the old drawing's
instruction to disconnect CN8; claiming the post-merge JS measures upstream
latch/gate-bias currents; and inventing numeric lug assignments for an
unspecified SPDT. The switch uses COM/NC/NO identified by continuity. The
common resistor's USB drop and direct-LiPo margin remain to qualify.

**Evidence:** direct user selection; independent pin/topology audit against
AO3401/AO3400 datasheets and MB1940 C02 ODB nets. USB takeoff remains SB12.1
(same net as CN9.3), with all CN9 shunts out and SB12 fitted. D_USB is shown
as removed board D2/BAT20JFILM only if retained/intact; donor footprint1=A,
2=K/band, while ST's datasheet labels the terminals A/K. Anode goes to USB,
cathode to MERGE. All three SOT-23 MOSFETs use1=G,2=S,3=D, with Q3 reversed
relative to Q1. SPDT/C3=2.2uF/R5=1kohm, R1/R2/R6=100kohm and direct
PD7/CN14.2-to-Q2 gate remain. The diagram generator is
`tools/build_lipo_usb_power_wiring.py`; the earlier generator entry point
delegates to it. SVG XML and rendered layout were checked. No instruments,
firmware installation or physical changes occurred. USB handover, leakage,
minimum press, cutoff and loaded supply margins remain unqualified.

## 2026-11-08  An upstream USB merge would require automatic latch enabling

**Why:** the user asks whether Q3 and D_USB can move together between the LiPo
and the existing VBAT node for easier assembly. Moving the complete selector
before Q1 would put Q1 in both source paths. With Q1 initially OFF, USB could
not start the MCU to assert HOLD; automatic USB operation would need an
additional USB-to-enable path or a shutter press.

**Rejected:** treating that complete upstream relocation as functionally
equivalent with the existing control circuit. Recommended alternative, not
yet selected: move only Q3 before Q1 and leave the USB diode feeding the load
merge after Q1. LiPo+ then goes to Q3 D3; Q3 S2 joins Q1 S2 and R1's high
end; Q1 D3 joins the USB diode cathode before common R0. Q3 gate remains on
protected USB before the diode, with R6 to ground. This keeps USB auto-on
and battery isolation without extra components.

**Evidence:** circuit analysis independently reviewed against the
[AO3401 body-diode orientation](https://www.aosmd.com/sites/default/files/res/datasheets/AO3401.pdf).
In the Q3-only alternative, Q1's body diode can raise the intermediate
common-source node from USB, so it must not be labelled or treated as raw
LiPo voltage. Q3 OFF blocks that node from feeding the cell; with HOLD
asserted, Q1's channel also supplies R1/Q2 bias from USB. Existing handover
and residual-charge qualifications still apply. No canonical SVG or wiring
selection changed, and no firmware or hardware operation occurred.

## 2026-11-08  Select upstream Q3 and USB joining after the battery resistor

**Why:** the user explicitly selects moving Q3 ahead of Q1 for easier wiring,
with D_USB feeding MERGE after R0. Canonical order is raw LiPo+ to Q3 D3;
Q3 S2 joins Q1 S2 and R1 high end at SOURCE_SW; Q1 D3 to2.2-ohm R0; R0
output and D_USB cathode join MERGE; MERGE to JS110 then CN5.5. Q3 gate
still senses protected USB/SB12.1 before D_USB, with R6=100kohm to ground.
The SPDT/C3/R5/Q2/PD7 circuit and other values are unchanged.

**Rejected:** retaining the earlier common-drain ordering or common-path
resistor after the user's latest explicit placement. This supersedes the
earlier same-day decision to place R0 after MERGE: R0 is now in the battery
branch, and USB-to-camera current bypasses its inrush limiting. This is a
selected prototype tradeoff, not evidence that USB startup is already safe
or limited. Keep the USB merge downstream of Q1 so USB can start the MCU
without a shutter press or extra enable circuit.

**Evidence:** direct user request and independent topology review. SOURCE_SW
can rise from USB through R0 and Q1's body diode/channel, so its name and
R1 connection explicitly differ from raw VBAT. Q3 OFF blocks the steady
path back to the cell. Small USB-fed R1/Q2 bias current can flow backwards
through R0; only the USB-to-camera current bypasses it. JS after MERGE
measures target current, not the upstream R1/trigger/Q2 or R6 branches.
The [canonical SVG](lipo-latch-wiring.svg), PNG, generator and current wiring
table were updated, with the SOURCE_SW and battery-only limiting labels.
All CN9 shunts remain out, SB12 stays fitted, and D2/R23 remain removed.
No physical change, firmware update or instrument operation occurred.
USB inrush/handover, direct-LiPo headroom and leakage remain to qualify.

## 2026-11-09  Manual trigger test confirms missing-sensor shutdown and load cutoff

**Why:** after the reviewed A3 HOLD firmware was installed and the user took
manual control, they reported that pressing the trigger worked, the expected
two-red-flash missing-sensor indication appeared, and the camera shut down
with zero indicated current at the end of the cycle. This is functional
confirmation of the assembled trigger/HOLD/cutoff chain on the error path,
beyond the preceding direct-5V GPIO and Standby smoke test.

**Rejected:** equating a zero instrument indication with mathematically zero
current or the specified 0.1 µA room-temperature target; treating this report
as a measured HOLD waveform, a held-button test, or successful capture/save
qualification with the sensor absent. Exact current boundary/resolution,
supply configuration and button release timing were not reported.

**Evidence:** direct November 9 user report following manual trigger testing;
the installed prefix remains
`852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084` from the
[preceding installation and instrumented smoke test](../../firmware/control-smoke/evidence/2026-11-09-a3-live/README.md).
No firmware change or agent-operated instrument measurement occurred during
this confirmation. The user retains bench control; the earlier automatic
Joulescope OFF setting must not be assumed current after manual operation.

## 2026-11-10  Use a manual source selector on the prototype and automatic MOSFET selection on the PCB

**Why:** to simplify physical wiring, the user removed Q3, the MOSFET that
disconnects the battery when USB is present. A separate SPDT power selector
now connects either USB power or the output of the battery's 2.2-ohm R0 to
the Nucleo 5V input. Q1/Q2 and the momentary capacitor/SPDT trigger remain;
Q1 source and R1 high end now connect directly to LiPo+. The PCB version
will use automatic MOSFET source control rather than a physical selector.

**Rejected:** leaving the old wired USB/battery merge in place after removing
Q3, treating USB attachment as automatic prototype source selection, or
removing the trigger/HOLD latch along with Q3. SW2 is the new power selector;
SW1 remains the momentary trigger. Use non-shorting/break-before-make source
selection so the throws do not join USB and battery; the installed switch's
exact part/contact timing was not reported. R0 still limits only the battery
branch. R6 is no longer needed for the omitted Q3, but its physical removal
and the previous D_USB diode's presence were not reported.

**Evidence:** direct November10 user hardware update; [current power wiring
and diagram](2026-10-14-power-tree-review.md#canonical-lipo-usb-and-a3-hold-wiring--november-10).
The user separately added the ASA pot; its owning decision is in
[prototype notes](../prototype/NOTES.md). This update changes documentation
and the drawing only, not firmware or the bench. The November9 manual latch
test predates this selector change; no new source-transfer or capture
qualification is claimed. USB tap remains the documented protected SB12.1
takeoff unless subsequently changed. Exact final PCB source-control circuit
and part qualification remain implementation work.

## 2026-11-11  Design the PCB for standard CR2032 cells at 50 F without further Nucleo power experiments

**Why:** in the PL-01 punch-list discussion the user set the battery inputs for
the custom PCB. The camera should work down to 50 F (10 C), with colder
operation a welcome bonus. The maximum rate is one shot per second. Cells are
standard, for example Energizer CR2032; the user chose CR2032 as the most
widely available primary cell that fits the 5 mm thickness, and remains open
to other suggestions, including a mechanical generator drive. CR2032 holders
go on this board spin, accepting that they may prove unusable. Moving to five
cells is acceptable if they physically fit. No charger. The user's reply
wrote "5xcr3032"; whether that meant CR2032 or the 30 mm CR3032 is not yet
confirmed.

**Rejected:** running further power experiments on the present Nucleo before
layout. The user judges the hacked Nucleo with an SD card too different in
power use from a custom board for more data to be worth taking. This
withdraws the four measurements proposed in the punch list on November 11
(SD card current, cell pulse resistance, baseline collapse resistance and
per-rail currents); it is not a finding that those quantities are known.
Also rejected: an on-board charger.

**Evidence:** direct user reply, November 11, in the PCB readiness review;
[punch-list item PL-01](../review/2026-11-10-pcb-readiness-punch-list.md).
The four- versus five-cell power ceilings, the 1.4x resistance factor
assumed for 50 F, the custom-board power figures and the 16.5 V input
rating recorded there are the reviewing assistant's model and inference,
not user decisions or measurements. Cell count, a LiPo connection alongside
the holders and CR2025 compatibility remain open. No bench operation,
firmware change or CAD change accompanied this entry.

## 2026-11-11  Five cells means CR2032; a LiPo may take the holder space; explore custom-board savings

**Why:** the user confirmed that "5xcr3032" in the earlier reply was a typo
for five CR2032. If the cells prove unusable, the CR2032 holders can be left
unfitted and that board area used for a LiPo instead. The user also states an
expectation that a custom board offers further power savings, naming a
specific low-power NAND, running everything except the sensor's 2.8 V rail
from a 1.8 V buck output, and slowing the MCU to match its input data
streams, and asked for ways to reduce peak current to be explored.

**Rejected:** reading the earlier reply as a request for 30 mm CR3032 cells;
fitting LiPo and coin cells side by side as a requirement. Not rejected or
selected: any particular power tree, NAND part or clocking scheme. The
exploration is an estimate to discuss, not a design decision.

**Evidence:** direct user reply, November 11;
[first peak-power exploration](custom-pcb-peak-power.md) and its
[calculation](../../tools/estimate_custom_pcb_peak_power.py). The
exploration's figures are the reviewing assistant's model from datasheet
typical values with marked assumptions; it found the 1.8 V main rail worth
little on power alone, and the sensor-core LDO, NAND in place of SD and MCU
sleep during page programming worth more. No bench operation, firmware
change or CAD change.

## 2026-11-11  The armed sensor is a sustained load, so long exposures set the coin-cell limit

**Why:** the user supplied the VD56G3 datasheet (DS12968 Rev 12, now stored).
Its Table 13 gives 97 mW typical in follower mode at 0 fps, 120 mW at 30 fps
and 145 mW at 60 fps; Table 14 gives maxima of 11 mA, 86 mA and 25 mA on the
1.8 V, 1.15 V and 2.8 V rails. A sensor that is ready to stream but reading
out no frame therefore draws about two-thirds of its full streaming power.
Exposure can be set up to one second, so the exposure itself is a sustained
load of roughly 0.15 W at the pack on an efficient board, not a brief burst.
On the review's source model that is 72-95% of what four standard CR2032
sustain at 50 F and 57-76% for five.

**Rejected:** treating the whole capture as a 22 ms burst that a small
reservoir can carry; assuming sensor power falls to its standby level while
integrating. Not established: that integration draws exactly the 0 fps
figure. The datasheet states the follower-mode figure, and its application to
a long exposure is the reviewing assistant's inference. The short-form
datasheet has no register detail, so whether a lower PLL or link rate reduces
the armed current is unknown.

**Evidence:** [VD56G3 datasheet](../../datasheets/camera/VD56G3_DS12968_datasheet.pdf),
Tables 13 and 14, Figures 23 and 24; [peak-power exploration](custom-pcb-peak-power.md)
and its [calculation](../../tools/estimate_custom_pcb_peak_power.py).
The pack-side figures are a model with marked assumptions, not measurements.
The user also noted that the ST promodule is expected to be required;
[owning note](../prototype/NOTES.md#2026-11-11--keep-the-st-promodule-as-the-camera-for-the-custom-pcb).
No bench operation, firmware change or CAD change.

## 2026-11-11  The longest exposure may be cut to 0.5 s, possibly by temperature

**Why:** the stored sensor datasheet shows that an armed sensor is a sustained
load, which makes long exposures the limiting case on coin cells. The user
answered that the maximum exposure time can be reduced to 0.5 s if necessary,
and that the restriction could depend on temperature, since temperature is
known from the RTC. The user's reply names an RV3032; the recovered design
carries an RV-3028-C8, so the RTC part is to be confirmed.

**Rejected:** treating one-second exposure on coin cells at 50 F as a fixed
requirement that the power source must meet regardless. D-39's exponential
curve to 1 s is not withdrawn; it may be shortened on coin cells when needed.
Not decided: the threshold, or whether the limit is sensed by temperature, by
loaded pack voltage, or both. A shorter exposure does not lower the sustained
power; it shortens how long the cells must hold it.

**Evidence:** direct user reply, November 11; [peak-power exploration](custom-pcb-peak-power.md);
[punch-list items PL-01 and PL-16](../review/2026-11-10-pcb-readiness-punch-list.md).
No hardware, firmware or CAD change.

## 2026-11-12  A HIGH HOLD pad does not prove the external latch has taken over

**Why:** a trigger-powered, sensor-disconnected boot reached the sensor READY
poll with PA2/A3 configured as output HIGH and its pad reading HIGH. Current
nevertheless collapsed before the documented 500 ms absent-sensor timeout,
preventing the expected error display. The external A3/Q2/Q1 path is the
leading suspect; the physical failure is still unlocated.

**Rejected:** changing the blink firmware based only on the observed brief
red LED; treating the MCU's output latch or pad reading as proof that Q2's
gate receives the voltage and clamps Q1's gate. A second UART-requested pulse
also ended early, but no recovery snapshot was obtained, so it is not proof
of a verified parked MCU dropping power.

**Evidence:** [November 12 trigger traces and RAM records](evidence/2026-11-12-trigger-dropout/README.md).
No firmware/NOR/SD writes, reset, halt or JS power switching. Physical HOLD
continuity and downstream gate/rail measurements remain pending.

## 2026-11-13  Direct 5 V operation supports investigating the external latch first

**Why:** the user bypassed the trigger circuit by feeding the board's 5 V pin
directly and reports that it now seems to work. Together with the earlier
HIGH HOLD pad and early current collapse, this supports investigating the
external trigger/HOLD connections before changing firmware.

**Rejected:** treating the brief red indication as sufficient evidence of a
blink-handler bug; claiming the exact failing wire or component is now
identified. The user did not report exact blink counts or measured waveforms
for this direct-power check.

**Evidence:** direct user report on November 13; [preceding instrumented
diagnostic](evidence/2026-11-12-trigger-dropout/README.md). The user is checking
the power-circuit connections and retains bench ownership. No instrument
access or firmware change was made for this update.

## 2026-11-13  Make D8 the canonical prototype HOLD connection after the user's check

**Why:** after the A3 output investigation and the intermediate D3 migration,
the user requested D8 instead, then reported that the loaded firmware works.
The assembly plan now connects **Arduino D8 / CN14 pin 1 / PD12** directly to
Q2 gate pin 1. CN15 pin 21 is the same net. The SPDT trigger, 2.2 uF starting
capacitor, R1/R2=100 kOhm, R5=1 kOhm, R0=2.2 Ohm and manual USB/battery
selector are unchanged. Exposure remains A0-A2 and ASA remains A4/A5/GND.

**Rejected:** keeping A3 or D3 in current wiring instructions, diagnosing why
A3 stopped driving from internal GPIO readings, or treating the user's D8
confirmation as evidence that D3 failed. PD12 cannot also emit phase pulses;
the firmware disables that physical marker while retaining RAM timing and the
independent PD0 exposure marker. USB-selected mode keeps HOLD LOW; the existing
provisional early assertion and early UART-recovery HIGH are not a guarantee
of a zero-pulse USB start. Automatic power selection remains a PCB direction.

**Evidence:** direct November 13 user instruction, "works! lets update the
schematic and assembly instructions to make D8 the canonical HOLD pin, then
commit and push"; [complete wiring](lipo-latch-wiring.svg),
[assembly guide](../prototype/nucleo-assembly-guide.md), and
[installed D8 package, complete programming readbacks and user confirmation](../../firmware/usb-ptp/evidence/2026-11-13-d8-hold/README.md).
The reload had build/layout and programming checks but no additional functional
test campaign, at the user's request. No new bench operation accompanies this
documentation update; exact latch timing and rail ordering are not newly measured.
