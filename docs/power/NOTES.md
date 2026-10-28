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
