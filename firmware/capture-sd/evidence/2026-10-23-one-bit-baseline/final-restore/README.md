# Original v59 restored after the one-bit SD benchmark

The original v59 Standby firmware is restored. The programmer's full 64 KiB
readback and a separate read both match sector SHA-256
`7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63`.
The desired bytes are identical to the previously archived October 20 v59
artifact, not a new rebuild. The following 4 KiB also matches its pre-experiment
contents, SHA-256
`01cc465d3a7581d9d003b09e5db684eb7bec8e8512e12ce3565154c3aced816f`.

Fresh INFO sequence 231013 passed before the guarded write. Write sequence
231014 passed all existing current/desired CRC, completion, cleanup, and full
readback checks. Separate reads 231015 and 231016 verified the restored sector
and following guard region. The prior exact v60c image, original v59 bytes,
requests, statuses, readbacks, and compact debugger logs are retained here.
See [verified-restore.json](verified-restore.json).

After restoration, UART recovery reached the exact v59 early park at
`0x3418078C`, with nine good pulses, zero bad pulses, caches off, and idle XSPI.
The same exact prefix was checked again before the final normal cold cycle.
These checks are recovery observations before that final normal execution;
they do not imply the core was left at the early park.

The final normal cycle was left powered. The JS110 helper stopped cleanly at
**2026-10-24 00:08:47.684621 UTC** (October 23 locally), restoring its original
range setting 128. Its last source measurement was **4.892616 V and 8.067146 mA**.
COM8 was closed and BREAK released; Logic 2 remained the running API backend.
No instrument or target was operated while assembling or replaying this archive.

The low-current observation is consistent with the existing v59 completion
behavior, but **no SBF read or saved-file readback was performed for this final
normal cycle**. Those qualification fields remain false. The previously
completed benchmark image checks are separate, under
[same-frame](../same-frame/README.md). Remaining CN8/debugger paths are outside
the JS110 measurement boundary.

Replay all hashes and comparisons offline from this directory:

```powershell
python replay.py --replay .
```

The manifest binds compact JSON, debugger logs, register/status bytes, and NOR
firmware bytes. SAL captures, large waveform exports, and camera/SD image
payloads are excluded; [omitted-files.json](omitted-files.json) records their
paths and sizes without copying them. The original local source is
`tmp/bringup/sd-baseline-20261023`.
