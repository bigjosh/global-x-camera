# Trigger power disappears before the missing-sensor error

November 12, 2026, America/New_York; recordings at 23:36 and 23:39 EST
(November 13 UTC). The user reports momentary red followed by all LEDs off,
with the camera sensor physically absent. Source is user-confirmed
**5 V PSU -> JS110 -> trigger circuit**; ST-LINK is connected. The physical
CN8 cable state was not supplied; the captured VBUS classifier selected
capture, not USB.

## Finding

The leading diagnosis is failure of the external power latch to take over.
The normal-trigger snapshot proves that firmware reached the sensor-ready
poll, selected capture mode, and drove PA2/A3 HOLD HIGH. No CPU fault was
recorded in that snapshot. Current then collapses before the documented
500 ms missing-sensor poll can time out and start its two-red-blink sequence.
The physical failing connection/component is **not yet identified**.

| Observation | Normal trigger (`trigger02`) |
|---|---|
| ST-LINK target reference during read | 3.28 V |
| Stage1 record | S1RN, result `0xFFFFFFFF`: running, not terminal error |
| Sensor record | SEN1, phase 0, result 0, 6036 read attempts; ISR `0x8011` |
| USB selector | phase 3, VBUS classification 0: returned to capture |
| PA2/A3 | output mode, no pull, ODR HIGH and pad IDR HIGH |
| CFSR / HFSR | both zero at snapshot |
| Current at 50-100 ms | 74.49 mA average |
| Falls below 50 / 20 / 10 / 1 mA | 427.32 / 451.62 / 461.82 / 502.81 ms |
| Source voltage | 4.994 V mean; minimum 100 us mean 4.834 V |

Times are relative to the first recorded current sample above 20 mA, not a
measured target power-good edge. The JS voltage is **upstream of the trigger**;
it does not measure target rail voltage. HOLD was read once during the pulse,
not continuously through its end. A later GPIO transition is not excluded
by the snapshot alone.

The exact previously installed November 9 source has a 200,000,000-cycle
sensor READY timeout at the checked 400 MHz clock: 500 ms. Phase 0 persists
while NACKs are tolerated; phase 2/result -3 and stage1 result 17 are published
only when that wait fails. The expected two-flash/five-set display then takes
11.4 seconds. See the frozen source under
[`stage1_sensor.c`](../../../../firmware/capture-raw/evidence/2026-11-09-a3-hold/hold-standby/staged/stage1_sensor.c)
and the [previous successful missing-camera test](../../../../firmware/control-smoke/evidence/2026-11-09-a3-live/README.md).
Today's full installed prefix/NOR was not reread, so the prior installed
identity is historical rather than a fresh byte-for-byte proof.

## UART-requested isolation attempt

`trigger03-uart` sent the established 1 Mbaud `0xC0` pulse train on COM8
before a second user trigger. **No BREAK/reset was asserted.** This run
dropped below 1 mA at 139.55 ms; all three bounded ST-LINK attempts timed out
without retrieving records. Consequently, **entry into UART recovery was
not proven** and this run cannot establish that a verified parked MCU lost
power. The two presses' mechanical hold durations were not measured, so their
different durations are not a controlled firmware comparison.

The normal trace's decay is compatible with the trigger capacitor no longer
being held down by Q2. R1=100 kohm and C3=2.2 uF imply a nominal 220 ms RC;
at 5 V, an illustrative gate-source displacement of 0.8 V is reached around
403 ms. This is only a circuit hypothesis, not a characterized MOSFET cutoff
threshold or proof of which wire is wrong. Releasing the SPDT trigger also
disconnects its capacitor from Q1's gate.

**Pending physical check:** with the 5 V supply off, verify A3/CN4.4 to Q2
gate/pin 1 and Q2 source/pin 2 to common ground. Then measure Q2 gate and Q1
gate if those connections pass. Firmware changes are deferred until that
boundary is understood.

## Evidence and terminal state

- `trace-100us.npz` in each run preserves current/voltage mean/min/max bins
  and nonfinite counts, derived from the native 2 MS/s stream. Columns and
  timing are recorded in each `result.json`; this is not a calibrated inrush
  peak or OFF-leakage qualification.
- Debugger logs, exact retrieved RAM/GPIO/fault bytes, command timestamps,
  UART open/close events and `measurements.json` are preserved here.
- Support scripts are their final campaign versions; the first normal run
  preceded adding the optional `park` prefix/core-read arguments.
- An earlier observation window saw no trigger event and stopped cleanly;
  its local record remains in `tmp/bringup/missing-sensor-20261112/trigger01`.

No firmware/NOR/SD writes, resets, debugger halt, or JS output switch occurred.
JS range remained 128; sampling controls were restored, JS was closed, and
COM8 was closed with BREAK released. At the final captured tail input current
was effectively zero; this does not prove every target rail is zero. The
user now owns the bench for the requested continuity check. Re-establish
the live source and wiring before more instrument operations. Other sessions'
existing PCB planning changes were preserved; no commit or push was made.
