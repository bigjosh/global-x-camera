# Resume boundary

Leave the direct-powered target at exact UART park while the user measures
D3/CN13.4. Do not interpret internal IDR as external voltage proof.

After that measurement, confirm whether the sensor is currently connected.
The normal first read at1s could miss a completed capture. The absent-sensor
error path should instead remain awake for about11.4s of blinks after its
500ms READY timeout. Normal stage1 opens debug before sensor initialization.

If needed, a separately identified renderer test may enter installed prefix
error_signal_shutdown at0x34181841 withR0=2, only after fresh exact UARTpark,
400MHz clock/context/stack checks. Do not use the high-SRAM copied handler
before capture has populated it. This tests HOLD/error shutdown, not sensor
error classification. Preserve normal NOR and UART recovery. No such test
has run yet.

The user forked knob-label design to chat01a1d66c-ae5c-7390-ab14-81eca99749d5;
that chat has no instrument ownership and should not change firmware.
