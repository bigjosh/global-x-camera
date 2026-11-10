# A3/A4/A5 exposure knob smoke test

November7 local time (November8 UTC). The user confirmed A4 is the wiper
and the bench is reconnected. A RAM-only ADC helper runs at10samples/s:
A3/PA2 LOW, A5/PH2 HIGH, conditioned A4/PF3 ADC1 channel16, PC12 high impedance.

The first five host observations reported1190–1196 raw counts, A3=0/A5=1,
STATE4 and ERROR0. The later archived snapshot contains2119 conversions,
current1198 and observed1094–1225, with no ADC errors. Full-travel knob
movement had not yet been reported; this verifies conversion/readout, not
calibrated endpoints or voltage accuracy. The actual snapshot is in
`live-snapshot.json`; `result.json` records qualification limits.

UART recovery reached exact normal park0x3418078C. Its complete SRAM prefix
matched the October28 profile; the reviewed RAM bridge established400MHz,
expanded SRAM and disabled caches. The complete5460-byte v5 diagnostic
readback matched before execution. BinarySHA256:
`3491062f0e9f2215f53e08963a4528d53f1b622739192ff3a29c97753c8dd1ca`.

ST-LINK reported3.28V. The source identity was not independently established;
the open Joulescope app and its output were untouched. VDDIO4's PVM-ready
bit is affected by ES0620Rev5§2.2.29 and is not physical rail proof.
No camera/SD/NOR commands, explicit target reset or power switching occurred
after the bounded existing UART-recovery stimulus. Normal NOR was not changed.

At handoff the target remains powered and sampling; PD7HOLD is HIGH.
The visible Python console (PID10228 at launch) owns ST-LINK and records
`tmp/bringup/control-smoke-20261107/live-console/readings.jsonl`.
COM8 is closed/BREAK released. The user can turn the knob to inspect readings.
The finite36000-sample test lasts approximately one hour from launch, then
drives A5 LOW and parks awake with HOLD retained. Closing the console does
not itself stop the MCU. The host-source README documents the stop mailbox.
Reset/power loss removes the RAM test and restores normal FLASH boot.

`v5/`, `launch01/`, `smoke01/` and `host-source/` retain the frozen build,
debugger commands, readback checks and console source. The originally used
programmer path was absent; the exact ST2.23 portable bundle was restored
under the campaign, with official registry hash verification recorded in
`programmer-acquisition.json`. No global installation or PATH change.
