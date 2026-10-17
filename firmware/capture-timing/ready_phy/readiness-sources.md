# Sensor and receiver readiness: source findings

Research date: 2026-10-17. This note separates published behavior from proposed
bench qualification. It does not establish a production timing guarantee.
The experiment's 100 µs dwell means 40,000 DWT cycles at the nominal 400 MHz
clock. Use the external capture correlation for measured elapsed times; the
nominal cycle conversion and physical timing are not interchangeable.

## Which event means what?

| Observation | Published meaning | What it does not establish |
|---|---|---|
| START acknowledgement | The sensor clears the command register after executing the command. START is written to `0x0201`. | A specified delay to electrical LP-11, or an ordering relative to the externally observed STROBE edge. |
| `SYSTEM_FSM == 3` | Sensor firmware reports STREAMING at `0x0028`. | That software observed the earliest instant at which the data receiver could safely initialize. Polling adds latency. |
| STROBE edge | Sensor exposure indicator, with programmable offsets relative to integration. The bench uses zero offsets. | A specified D-PHY initialization-complete signal. |
| Both `STOPDLxF` bits | STM32 reports both data-lane PHY StopState outputs. | A documented STM32 initialization timer completion, especially while a lane is disabled. |
| ForceRx asserted | Receiver is forced into receive/wait-for-Stop mode. | A command to drive the sensor wires high, or proof that a reported Stop already includes `T_INIT`. |

The sensor descriptions are in [UM2602 Rev8](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf):
§5.5 p7, §8 p10, Table43 p51, Table45 p56, and §18.2/Figure17 p48.
GPIO functions are active in STREAMING (§18 p47). The manual does not give an
explicit START-ACK-to-LP-11 guarantee. The [VD56G3 datasheet, DS12968 Rev12](https://www.st.com/resource/en/datasheet/vd56g3.pdf),
Table7 p19, lists LOW reset states for the CSI clock/data pins, so initial LP-11
must not be assumed.

## What STM32 documents

[RM0486 Rev4](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf)
provides these relevant definitions:

- §40.6.2 p2033: configure the lane merger while CSI is disabled and the PHY is
  not supplying a clock; enable the selected lanes before starting the virtual
  channel. No additional software Stop dwell appears in this sequence.
- §40.9.2 p2041: `PCR.DL0EN/DL1EN` enable the data-lane modules; clearing them
  shuts the modules down.
- §40.9.15 pp2060–2061: `SR1.STOPDL0F` bit19 and `STOPDL1F` bit25 reflect
  `StopState_D_lane0/1`; combined mask `0x02080000`.
- §40.10.1 pp2066–2067: `PRCR.PEN` bit1 controls digital PHY reset.
- §40.10.2 pp2067–2068: `PMCR` offset `0x1004`, reset `0x00011003`;
  `FRXMDL0/1` bits0/1 select receive/wait-for-Stop. `FTXSMDL0` bit2 is a
  different operation, forcing transmit Stop.

The reviewed CSI section does not specify whether Stop includes `T_INIT`, nor
an STM32 timer setting for that qualification. The existing HAL clears all of
PMCR immediately after releasing PEN; it does not wait for Stop. Preserve
clock/reset access guards: a status read from an unclocked or reset CSI is not
a safe way to inspect readiness.

## Why ForceRx is promising, and what remains uncertain

[AMD PG202 v4.3, Example13](https://docs.amd.com/r/en-US/pg202-mipi-dphy/Example-13-RX-Data-Lane-Initialization-Using-forcerxmode)
shows ForceRx resetting lane initialization, actual transmitter LP-11 held for
`T_INIT`, Stop becoming asserted after initialization, and ForceRx then being
released. This is evidence against treating ForceRx as a synthetic Stop-output
control. It describes AMD's implementation, not STM32's.

[Intel/Altera PPI signal definitions](https://www.intel.com/content/www/us/en/docs/programmable/817561/25-1/d-phy-tx-ppi-interface-signals.html)
likewise describe waiting for Stop on the physical interconnect and releasing
ForceRx only after the required LP-11 interval. ForceRx and ForceTxStop are
mutually exclusive. Neither source licenses asserting a transmit-driving mode
against this camera.

Implementation details matter. [TI SPRUHL6A, §2.3.2.2 p70](https://www.ti.com.cn/cn/lit/ug/spruhl6a/spruhl6a.pdf)
explicitly puts D-PHY initialization outside its PHY. Stop reports line state,
and controller logic times the interval before releasing ForceRx. Figure21 p70
and `CSI2_TIMING` Table87 p180 describe that coordination. Thus a Stop bit need
not universally incorporate the initialization interval.

The [MIPI specification page](https://www.mipi.org/specifications/d-phy) requires
member access to the normative specification. No unofficial mirror was used
to turn the STM32 ambiguity into a claimed guarantee.

## Controlled experiments and acceptance evidence

The first STOP-dwell experiment keeps data enable after ACK and STREAMING,
changing only the extra continuous-Stop interval from 100 to 10 to 0 µs. Zero
still requires both Stop bits. The 100 µs control is byte-identical to v36.
This tests whether the inherited empirical delay is needed; it does not move
the data-enable boundary earlier or demonstrate a universal `T_INIT` value.

The ACK experiment enables data and arms after ACK plus observed Stop, then
performs the unchanged STREAMING verification. A passing result supports an
earlier usable boundary for the tested sensor and setup. ACK and STROBE can be
observed in either order; compare measured events rather than assuming one.

For an independent ForceRx trial, retain early lane enable and explicitly
prepare `PMCR=0x3` before PEN release in both matched variants. Record the
original value and the write readback; do not assume the documented reset value
already equals 3. The control retains HAL's final clear, while the treatment
keeps the two ForceRx bits asserted. Record initial Stop and each lane's first
post-PEN Stop observation; initially require 100 µs continuously in both-lane
Stop. Confirm both remain in Stop immediately before releasing force. Then
clear only the two ForceRx bits, verify the readback, and arm. Do
not add error clearing, interrupt masking, transmit forcing, or a PHY reset
to hide the transition being investigated.

The proposed state bound is **enabled receive lanes, valid clock/reset state,
observed both-lane Stop for the chosen interval, then verified ForceRx
release before arming**. Initial Stop-low followed by Stop-high while force
remains asserted supports a physical readiness interpretation. Immediate
Stop-high after early enable leaves that interpretation ambiguous. A second
control can move receiver initialization slightly while leaving START fixed:
compare whether the Stop transition tracks sensor START or receiver enable.
This remains empirical evidence until STM32 timing semantics are confirmed.

Proof initialization must precede the new PHY observations. In the current
two-stage program, sensor START already occurs in stage1, before receiver
entry. Therefore receiver proof initialization is **after START**, and must
not be described as before it. Preserve START timing and record its inherited
timestamp instead of moving it to accommodate diagnostic bookkeeping.

Every candidate must preserve the early recovery guard and qualify all of:

- Real cold rail discharge/restoration, exact installed firmware identity,
  bounded execution and no diagnostic overflow.
- Raw startup, capture and shutdown error history with unchanged interrupt
  enables; a zero final flag alone is insufficient.
- First physical STROBE associated with first VSYNC and the complete first
  frame, including native byte count, image content and memory guards.
- Current-run shutdown proof, isolating data reception before sensor STOP.
- START-return-to-STROBE unchanged within the measured comparison; receiver
  arming-to-first-VSYNC margin reported separately from reset-to-exposure.

Successful trials establish measured margin on this board. They do not by
themselves bound sensor revisions, temperature, supply variation or production
worst cases. Per-run results and exact image hashes belong in the evidence
archive, separate from these source interpretations.

## Measured interpretation from the October 17 trials

The completed minimum-exposure trials support **lane1-only ForceRx with the
40,000-cycle Stop dwell** as the preferred sequence. The receiver enables its
lane modules early, prepares `PMCR=3` before PEN, then releases lane0 immediately
with `PMCR=2`. Lane1 remains in receive/wait-for-Stop until both data lanes have
continuously reported Stop for the selected dwell. The code rechecks Stop,
clears the remaining force, verifies `PMCR=0`, and arms capture before doing
the ACK/STREAMING polls. Thus the gate controls release into normal reception;
it does **not** mean PCR lane enable itself waits until sensor initialization.

| Trial | Measured outcome |
|---|---|
| Matched early control, force cleared immediately | First frame captured, but the original lane1 state-sequence error remained. |
| Both lanes forced through the 40,000-cycle dwell | Both Stop flags and force-release proof passed, but no frame arrived. Clock-active remained absent while the sensor continued exposures. Zero reported errors did not mean successful reception. |
| Both lanes forced, no additional Stop dwell | Released while clock Stop was still asserted; clock-active subsequently appeared and the first frame was clean. Arming-to-first-VSYNC margin: 651.68 µs. |
| Lane1 alone forced through the 40,000-cycle dwell | Clock-active was observed while lane1 remained forced. The first frame was clean, with 548.16 µs margin in the first trial. |

The both-lane comparison supports a timing-window explanation: retaining force
through clock Stop exit can prevent clock acquisition, while releasing before
that transition works. It does not prove a particular undocumented internal
connection between FRXMDL0 and the clock receiver. Lane1-only forcing avoids
depending on a narrowly timed release of lane0 and preserves a dwell before
releasing the lane that produced the original error. The observed `ACTCLF=1`
before lane1 release corroborates clock acquisition; the firmware does not
implement an ACTCLF polling gate. Earlier clock-only/PCR3 captures did not show
ACTCLF even after STREAMING, so polling it before data enable is not supported
by the measured evidence.

The deliberate PEN-delay control also passed with a clean first frame:

| Observation, relative to START return | Two ordinary lane1 trials | PEN-shifted trial |
|---|---|---|
| Post-PEN observation | 3726.449 / 3718.895 µs | 3934.095 µs |
| First observed both-data Stop | 4931.105 / 4934.440 µs | 4935.301 µs |

These are externally calibrated times. Receiver startup moved by about
208–215 µs, while the observed Stop boundary moved by only 0.861–4.196 µs.
This supports a sensor-related state boundary near START + 4.93 ms on this
hardware, rather than a fixed interval after PEN. The shifted trial retained
548.00 µs arming margin and a 5364.48 µs START-to-STROBE interval; the first
ordinary lane1 trial measured 5360.64 µs. The added receiver delay therefore
did not add a corresponding delay to exposure.

The readiness evidence is the initially absent, subsequently observed Stop
state, its persistence through the dwell, verified force release, and the
clean first physical frame. It is not a formal `T_INIT` guarantee or a
production-wide 4.93 ms deadline. The sensor and receiver must still satisfy
the complete first-frame/error/shutdown checks above. Default-exposure repeats
and final bench-state qualification are recorded separately in the
[receiver-readiness evidence archive](../evidence/2026-10-17-receiver-ready/).
