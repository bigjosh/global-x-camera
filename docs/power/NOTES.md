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
