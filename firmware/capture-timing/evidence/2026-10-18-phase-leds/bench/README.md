# Programming and reset attempts, October 18

**The v44 image was programmed and its complete first 64 KiB read back correctly.
The user subsequently reported, “LEDs working great. I will continue with board
modifications now.”** That visual confirmation is retained separately from the
instrumented attempts below. No completed v44 image capture, measured CPU sleep,
true cold-start timing or successful GPIO-selected recovery was established by
these particular instrumented checks.

The offline build and its original qualification-pending records remain intact.
This directory is an additional bench checkpoint, not a reinterpretation of
failed logs as a passing capture test.

| Check | Evidence and result |
| --- | --- |
| Existing v41 preflight | `preflight-v41/capture-result.json`: one completed frame, matching image checksum/statistics, no recorded camera errors. This is v41 evidence. |
| Program v44 | `program-v44/write/verified.json` and `readback.bin`: all 65536 bytes matched sector SHA-256 `a325b36ed6d3f893ebe0d1153f476fd06fc51c648a1fe55aac15d353c959b4d8`. |
| First MCU reset | Exact v44 live prefix; terminal prefix error 17, sensor phase 2/result -3, zero frames. GPIOG ODR/IDR both `0x101`, consistent with red on and green/blue off. See `reset1/prefix-failure/result.json`. |
| Sensor reset preparation | Initial BSRR write command reported failure. Later independent PO5 ODR and IDR reads were both zero; that readback, rather than the failed command, supports the low-pin observation. |
| Second MCU reset | Hardware NRST after confirmed PO5 low; not a cold power cycle. Subsequent HOTPLUG AP1 read failed, so no LED proof buffer or CPU sleep state was obtained. |
| Additional reset/debug attempts | Documented AP0 `hwRstPulse` at 1 MHz connected and reported device/revision. Subsequent AP1 failed. A later AP0 read reported no debug probe; no cause is assigned. It would be inaccurate to say every ST-LINK operation failed. |
| Saleae capture | Two exported digital rows were all low; analog samples were near zero, with channel extrema from -44 mV to +14 mV. Probe/ground validity was unresolved. These records cannot establish that MCU rails were off. |
| User observation | The user's later visual confirmation supports their observation that the LEDs work. It does not supply captured frame integrity, exact timing, CPU sleep or recovery-park evidence. |

The user confirmed CN8 powered the board directly through a CN9 jumper and the
JS110 was not in the target-current path. Recovery-output retained settings
selected OUT0 low, but the observed PE1 input remained high; GPIO recovery was
therefore not demonstrated. The exact physical cause of that mismatch and the
AP1 failures is unknown. In particular, neither sleep nor a firmware defect is
established as the cause.

The owning bench agent requested restoration of the JS110 series supply route,
common ground and diode connection, but stopped further hardware work when the
user reported the LEDs working and resumed physical board modifications.

## Instruments and preserved records

The JS110 session closed cleanly at `2026-10-19T00:56:12.177760Z` (October 18
local time). Retained range returned to its starting value 128; recovery settings
were 3300 mV, OUT0 high and OUT1 low; no restoration errors were reported. These
are device settings, not independent voltage measurements. The final response
is preserved separately in `js110-final-response.json`. The earlier metadata
snapshot remains a bounded snapshot of the session while it was running.

The owning agent reported no remaining JS110 helper, Saleae capture helper or
CubeProgrammer process. Logic 2 was left open as the Saleae API backend. No
instrument was operated by this archiving task.

`attempt-source-index.json` hashes every copied compact log/status buffer and
records hashes for the excluded frame pixels, large analog CSV and Logic file.
`reset2-analog-summary.json` preserves the computed sample count and extrema.
JS110 metadata excludes the raw statistics stream; the final-response provenance
records that its statistics field was omitted. The phase LEDs' binary artifacts
and original manifests were not altered by this archive addition.
