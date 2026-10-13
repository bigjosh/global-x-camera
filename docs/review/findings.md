# Complete review findings register

> **Baseline and status:** this register records the September 5 recovered-circuit review. The October 12–13 [prototype decisions](../../spec.md) do not close these findings or imply schematic changes. Keep each finding open until the selected implementation is corrected and verified, or document why a redesign supersedes it. Camera-specific evidence must be reassessed for CAM-6G3-073CLR/VD56G3.

Reviewed 2026-09-05. **47 tracked findings/recommendations:** 5 blocker, 22 high, 17 medium, 3 low.

Severity is milestone-oriented: a manufacturing blocker may not affect electrical simulation. Confidence separates explicit conflicts/gaps from firmware/revision-dependent cases and measurement needs. These are not all proven failures. See the [main review](../DESIGN-REVIEW.md) for correction order and scope.

| ID | Severity | Confidence | Finding | Evidence and action |
|---|---|---|---|---|
| CAM-001 | blocker | confirmed | Rebuild J3 signal lands before PCB release | [camera-memory](camera-memory-review.md) |
| MCU-001 | blocker | confirmed | Boot NOR chip select is on the wrong ROM pin | [mcu](mcu-review.md) |
| MCU-002 | blocker | confirmed | Main and auxiliary MCU supplies cannot perform the mandatory sequence | [mcu](mcu-review.md) |
| PWR-001 | blocker | confirmed | Battery latch pull-down back-drives the MCU shutter input | [power](power-review.md) |
| PWR-004 | blocker | measurement | Four-CR2032 supply is unqualified for the stated system pulse power | [power](power-review.md) |
| MCU-003 | high | confirmed | NAND ready/busy is routed to FMC_NWAIT instead of FMC_RNB | [mcu](mcu-review.md) |
| MCU-004 | high | confirmed | RTC interrupt pull-up exceeds the receiving bank operating limit | [mcu](mcu-review.md) |
| MCU-005 | high | confirmed | NRST capacitor is ten times the specified maximum | [mcu](mcu-review.md) |
| PCB-004 | high | confirmed | Library load validation is not footprint manufacturing validation | [system](system-review.md) |
| PWR-002 | high | confirmed | PFET gate divider has no absolute-maximum margin at fresh-cell voltage | [power](power-review.md) |
| PWR-003 | high | confirmed | USB startup automatically reconnects the battery stack | [power](power-review.md) |
| PWR-005 | high | confirmed | Power magnetics and MLCC footprints are placeholders without production limits | [power](power-review.md) |
| PWR-006 | high | confirmed | MCU SMPS passive targets and local input bypass do not match the current reference requirements | [power](power-review.md) |
| CAM-002 | high | conditional | Sensor revision can make a 50 ms cold capture impossible | [camera-memory](camera-memory-review.md) |
| CAM-004 | high | conditional | Power-down must remove analog power before camera core and I/O | [camera-memory](camera-memory-review.md) |
| MCU-008 | high | conditional | Shutdown and bank setup need an N6-specific early firmware contract | [mcu](mcu-review.md) |
| MEM-001 | high | conditional | Use BCH4 or stronger and protect metadata outside the FMC BCH data path | [camera-memory](camera-memory-review.md) |
| MEM-002 | high | conditional | Power-fail recovery must respect partial-program and erase rules | [camera-memory](camera-memory-review.md) |
| PCB-001 | high | conditional | The four-layer target needs a real stackup and an escape trial | [system](system-review.md) |
| PCB-002 | high | conditional | High-speed and power routing rules are not yet implemented or verified | [system](system-review.md) |
| PCB-003 | high | conditional | The five-millimetre envelope and camera alignment are not closed | [system](system-review.md) |
| RTC-001 | high | conditional | Backup mode must be provisioned persistently; default is disabled | [system](system-review.md) |
| RTC-002 | high | conditional | The primary backup cell must never have trickle charging enabled | [system](system-review.md) |
| USB-001 | high | conditional | Attach/detach detection and USB power policy are incomplete | [system](system-review.md) |
| CAM-003 | high | measurement | Define exposure completion and first valid frame for the 50 ms requirement | [camera-memory](camera-memory-review.md) |
| MCU-006 | high | measurement | The 50 ms capture target needs a bounded cold-boot payload and measured startup budget | [mcu](mcu-review.md) |
| USB-002 | high | measurement | Directly connected capacitance and startup load need inrush control | [system](system-review.md) |
| PCB-005 | medium | confirmed | Debug keepout and assembly clearances need enforced rules | [system](system-review.md) |
| PWR-007 | medium | confirmed | The stated 8 V battery discharge endpoint is not enforced | [power](power-review.md) |
| SYS-001 | medium | confirmed | Add observability and a production recovery path before layout | [system](system-review.md) |
| ACC-001 | medium | conditional | Accelerometer cold startup consumes up to 20 ms before sampling | [system](system-review.md) |
| ACC-002 | medium | conditional | Keep MCU bus pins passive while the sensor rail is off | [system](system-review.md) |
| CAM-005 | medium | conditional | The 1.2 V camera core choice has limited tolerance margin | [camera-memory](camera-memory-review.md) |
| CAM-006 | medium | conditional | XSHUTDOWN pulldown is not proven against maximum input leakage | [camera-memory](camera-memory-review.md) |
| CAM-008 | medium | conditional | Use the exact 079CLR module envelope for mechanical release | [camera-memory](camera-memory-review.md) |
| MCU-007 | medium | conditional | The 0.81 V core label must not be treated as an 800 MHz operating point | [mcu](mcu-review.md) |
| MCU-010 | medium | conditional | Silicon revision and cold-reset recovery must be recorded before bring-up | [mcu](mcu-review.md) |
| MEM-003 | medium | conditional | Keep NAND scanning and erase work outside acquisition latency | [camera-memory](camera-memory-review.md) |
| MEM-004 | medium | conditional | NOR warm-reset state needs a recovery contract | [camera-memory](camera-memory-review.md) |
| SYS-002 | medium | conditional | Narrow the first prototype's performance and operating contract | [system](system-review.md) |
| CAM-007 | medium | measurement | 1 MHz camera I2C needs a capacitance and pull-up budget | [camera-memory](camera-memory-review.md) |
| MCU-009 | medium | measurement | The 40 MHz crystal network needs startup and load qualification | [mcu](mcu-review.md) |
| PWR-008 | medium | measurement | Ten-year shelf life is not established by the PFET off-state leakage limits | [power](power-review.md) |
| USB-003 | medium | measurement | Protection selection needs exact-vendor qualification and short return paths | [system](system-review.md) |
| MEM-005 | low | confirmed | AC remains supported; AD substitution changes the storage format | [camera-memory](camera-memory-review.md) |
| RTC-003 | low | confirmed | Resolve the optional pull-down and interrupt voltage before release | [system](system-review.md) |
| CAM-009 | low | conditional | Qualify the clear-filter optics for intended lighting | [camera-memory](camera-memory-review.md) |

The [JSON register](findings.json) contains detailed evidence, recommendations and the baseline hash. The finding identifiers remain stable across the linked reports. NAND PT was checked against its explicit low-or-floating allowance and is not an actionable defect.
