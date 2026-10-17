# JS110 output for autonomous recovery

`js110_session.py --recovery-output` adds optional OUT0 control to the existing
single-owner power session. This is an **active-high NMOS interface**, not a direct
push-pull connection to the MCU. The implementation has offline tests; wiring,
actual GPIO levels and autonomous recovery still require bench verification.
Without the flag, the helper does not read or write GPIO settings and rejects
recovery commands. Existing power-control requests retain their behavior.

## Connection and polarity

Use a suitable small logic-level NMOS as an open-drain pull-down:

- JS110 rear **OUT0** to the gate; approximately 100 kΩ from gate to source.
- Source and JS110 rear **GND** to target ground.
- Drain to the MCU recovery input, optionally through 1 kΩ to limit accidental
  contention if a test image mistakenly configures that pin as an output.
- The MCU enables its internal pull-up early, waits for it to settle, then samples
  the input. High continues normal boot; low enters the recovery wait loop.

OUT0 low releases recovery; OUT0 high asserts it. The gate pull-down also releases
the request when the JS110 output is unpowered or disconnected. Verify the exact
transistor pinout and its operation at 3.3 V before wiring it. The boot-guard
documentation selects the MCU pin separately.

The transistor prevents the JS110's driven-high output from supplying an unpowered
MCU pin. A direct connection through a resistor only limits that possible current;
it does not isolate the target. Do not connect the rear +5 V pin to MCU VDD.

JS110 GPIO is referenced to **USB ground**, unlike its isolated current-measurement
ports. It has an internally programmable I/O supply, not a target Vref input.
OUT0/OUT1 use a shared supply and the input thresholds also depend on that supply.
The guide specifies approximately 100 Ω output impedance and output-low voltage
at most 0.1 V at 100 µA. These are JS110 specifications; do not substitute JS220
topics or wiring. [JS110 User's Guide, revision 1.3, §§8.10 and 12](https://download.joulescope.com/docs/JoulescopeUsersGuide/JoulescopeUsersGuide_v1_3.pdf)

### Output levels and PE1 limits

The JS110's specified programmable logic supply spans 1.8 V to USB voltage
minus 0.2 V (about 4.8 V with a nominal 5 V USB supply). For this interface use
3.3 V. At a 100 µA load, the guide specifies output high at least Vcco minus
0.1 V and output low at most 0.1 V; these are comfortably separated at a 3.3 V
setting. Both output channels share that logic supply.

PE1 is a **TT, 3.3 V-tolerant** STM32 input on the VDD domain, not a 5 V-tolerant
input. At the bench's 3.3 V VDD, ordinary 0/3.3 V logic levels are compatible.
DS14791 Rev11 Table25 limits the operating input voltage relative to its I/O
supply (upper limit supply plus 0.3 V). Table22's -0.3 to 3.6 V absolute input
rating for the 3.3 V range is a stress limit, with a footnote requiring the main
supplies in their permitted ranges; it is not a guarantee of powered-off input
tolerance. A separately powered 3.3 V GPO must therefore not be assumed suitable
for direct connection throughout target power cycling. This is the reason for
the sink interface, rather than a mismatch between the powered logic levels.
[STM32N657 datasheet, Tables18, 22 and 25](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf)

## Opt-in and shared-supply guards

Start the existing helper with its normal mailbox paths and `--recovery-output`.
Do not open another driver client just to control OUT0. The session uses restore
mode, records both retained GPO values and the shared I/O voltage, and releases
OUT0 before reporting ready.

The starting shared I/O supply must be **3300 mV or off (0)**:

- At 3300 mV, the voltage is left unchanged. OUT1 and existing input use are
  preserved; this mode owns only OUT0.
- At 0, enabling 3300 mV affects both outputs and both input thresholds. All other
  rear GPIO signal pins must be disconnected before using this option. The helper
  additionally rejects a retained-high OUT1, either enabled GPI stream, or either
  nonzero current/voltage LSB route. These software guards cannot detect a wire.
  OUT0 is released before the shared supply is enabled, even if its retained value
  initially was high.
- Other voltages are rejected before GPIO changes. There is no automatic
  conversion from a voltage another instrument connection might require.

The helper never publishes a new OUT1 value. It checks that OUT1 remains equal to
its starting value and refuses to restore the shared voltage if OUT1 unexpectedly
changes. A GPIO configuration mismatch ends the session and records the error.

## Mailbox commands

Use a fresh request ID and wait for the matching response for every request:

```json
{"id":"recovery-on-1","state":"recovery","asserted":true}
```

```json
{"id":"recovery-off-1","state":"recovery","asserted":false}
```

`asserted` must be the JSON boolean `true` or `false`; numeric values, strings,
missing fields and null are rejected. These requests do not change the current
range or cycle power. The usual `query`, `off`, `auto`, `2A` and `stop` commands
remain available. Setting recovery must precede the separately requested power
cycle so the input is stable before the boot guard samples it.

Ready, successful command responses, queries and the final stop record include
`recovery_output` with both GPO values and the shared voltage. These are
**retained settings, not measurements of the physical pins**. An asserted flag
does not prove that the transistor or MCU input responded. Verify pin levels,
normal/recovery branch selection, debug access and power-rail discharge/restoration
with the external capture before calling the mechanism autonomous.

On stop, timeout, Ctrl-C or a handled error, the helper attempts to restore the
starting OUT0 value and any changed I/O voltage before restoring the original
current range. If the supply originally was off, it restores that supply first,
then restores a possibly high retained OUT0. Every changed setting is attempted
even if an earlier restoration reports an error. OUT1 is never overwritten.
Any failed restoration makes the final result unsuccessful. A killed process,
device disconnect or host failure can prevent restoration. The original state
may itself have OUT0 high; restoring it can leave recovery asserted for the next
boot, and the final response makes that explicit.

## Driver contract and verification

The pinned `pyjoulescope_driver` 2.5.4 source defines:

| Topic relative to the JS110 device | Meaning |
|---|---|
| `s/extio/voltage` | Shared I/O voltage in millivolts; 0 is off; default 3300 |
| `s/gpo/0/value` | OUT0 boolean; default 0 |
| `s/gpo/1/value` | OUT1 boolean; default 0 |

The driver exposes no per-output open-drain mode. Its restore-mode open synchronizes
external-I/O settings from the instrument. External-I/O USB messages carry the
shared settings together, so preserving the unowned output's retained value is
essential. [Pinned JS110 driver source](https://github.com/jetperch/joulescope_driver/blob/v2.5.4/src/devices/js110/js110_usb.c)

`tests/test_js110_recovery.py` exercises legacy isolation, mailbox validation,
power-independent assert/release, initial high-output ordering, shared-supply
rejection, partial-success USB failures, restoration failures, interrupts and
unexpected OUT1 changes. These tests use an in-memory fake device and never
import or operate an instrument driver.
