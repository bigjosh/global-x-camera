# D3 HOLD capture/USB firmware — November 13

The offline qualification is recorded below, followed by the root-owned
installation and live smoke-test record. Frozen candidate manifests preserve
their original offline status; the hardware section identifies installation.

## Result and policy

- HOLD is Arduino **D3 / CN13.4 / PE9** (alternate CN15.31), main VDD.
  Secure GPIOE base is 0x56021000; only PE9 mode/pull/type/speed/output fields
  are changed by the HOLD helpers. A3/PA2 is retired as a latch output.
- Battery boot asserts HOLD in the 76-byte early hook at 0x34181DF0 before
  the original UART guard. Capture, saving, error display and recovery retain
  it; successful/error Standby floats it immediately before WFI. A refused or
  returning battery shutdown retains/reasserts it.
- The prior USB-off policy from commit `34a49be8` is restored on this branch
  and moved to PE9. Once VBUS selects USB (or is ambiguous), HOLD goes LOW
  before USB loading and remains LOW through service, faults, refused shutdown
  and an unexpected WFI return. USB Standby floats PE9 at WFI.
- The provisional early HIGH **before VBUS selection** remains, as does early
  recovery HIGH. This is not a no-pulse-on-USB-boot guarantee. The original
  ADC2/PA11 VBUS sampler is unchanged; capture-control forcing is rejected for
  the canonical D3 package.
- Capture HOLD contract schema 4 and USB shutdown schema 4 identify PE9. USB
  build policy schema 3 identifies PE9 OFF. Historical pin/schema records stay
  inspectable; the package rejects a PA2 capture / PE9 USB pairing.

## Frozen inputs and identities

The exact capture input is
[`hold-standby/staged`](../../../capture-raw/evidence/2026-11-13-d3-hold/hold-standby/staged).
The archive manifest uses durable capture/USB locations rather than the original
temporary build paths; executable bytes and source hashes are unchanged.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Combined prefix | 7160 | `bcd7fc5b439fc0b2df48ff668f62fe271d973df83121a96d9859a7d1757fd111` |
| NOR sector0 | 65536 | `1d5d4fd8aa04a9ed25e6a9608079601999d803f2b33b7cfff472c9bde7a9e6d9` |
| NOR sector1 | 65536 | `43f81739be9328adbe750e08e3846270f70b65956464d88519e5a262eca36bac` |
| USB executable | 34582 | `fcbb2b014edb42c444faab9728585237bd22d109ea4edc00a1856441e84aa026` |

The 76-byte early HOLD hook ends at 0x34181E3C, followed by four padding bytes.
The USB hook remains 440 bytes at 0x34181E40..0x34181FF8; no overlap. The selector
is 4468 bytes. Both NOR sectors remain 65536 bytes; the original capture payload
from sector0 offset 0x2000 is byte-identical to the reviewed D3 capture input.
Original early UART bytes and park 0x3418078C are unchanged.

## Validation

All **64 USB tests passed, no skips**, with the exact linked package. The
shutdown native model executes 34 guard/terminal cases and 4096 randomized
inherited GPIO states, totaling 41518 assertions. Successful USB teardown,
faults, bad prerequisites, bad clocks, pin failure, refusal and WFI return
never write PE9 HIGH; other controls and PE6 UART remain preserved. An
independent 42-byte Thumb oracle checks PE9 float/no-pull/WFI. Hardware Standby
entry and physical pin voltages are not implied by these models.

The selector compiler placed a literal pool between its final barriers and
application handoff. The executed path is DSB/ISB at 0x342002D0/2D4, unconditional
B.n at 0x342002D8 to 0x34200328, literal LDR r3, and BLX r3 at 0x3420032A to the exact
USB entry 0x34300381. A bounded raw-instruction audit follows only unconditional
branches and literal loads; it rejects stores, other calls, changed barrier,
changed entry and changed BLX. The old straight-line listing regex was replaced,
not loosened across arbitrary intervening instructions. Firmware bytes did not
change for this test correction.

[`results.json`](results.json), [`qualification.log`](qualification.log) and
[`validation/`](validation) preserve checks, source bindings and instruction
records. `SHA256SUMS` covers the frozen package, USB build, validation and result
files, excluding this expandable README and any later hardware subdirectory.

Re-run the linked suite from the repository root:

```powershell
$env:USB_BOOT_TEST_PACKAGE='firmware/usb-ptp/evidence/2026-11-13-d3-hold/package'
python -m unittest discover -s firmware/usb-ptp -p 'test_*.py' -v
```

## Hardware status

The normal D3 camera/PTP package is now installed. Both64KiB NOR sectors
were independently read back and match the listed identities; the following
4KiB is unchanged. The standalone all-A blinker has been replaced. Root
reviewed and admitted this exact package into the UART verifier; first
post-install recovery passed9valid/0bad pulses, with PC0x3418078C and the
complete7160-byte prefix matching.

D3/PE9 reads push-pull output HIGH with no pull at recovery. A normal powered
reset was then attempted; the first nonhalting read at about1second could not
connect (AP invalid). Therefore the expected missing-sensor error record,
blink sequence and physical HOLD release were **not observed** in that attempt.
A subsequent UART recovery passed9/0 and exactprefix again. Retained CPUCR
0x10201 means SBF1/PDDS1/STOPF0, but the test did not clear/bind prior flags,
so this is not proof of a fresh Standby entry. Sensor/knob reconnection was
not freshly confirmed. No successful image capture or USB transaction is
claimed by this smoke test.

The user confirmed ST-LINK and direct5V target power. No JS operation was used;
this was not a cold-power test or latch takeover test. The board is presently
parked with PE9HIGH for the requested external D3 voltage measurement.
[Hardware records](hardware/CURRENT-STATUS.json) preserve calls, readbacks,
recovery, incomplete cycle and the independent package review. No explicit
SD read/write/erase was issued by helpers; normal firmware may have accessed
SD if a sensor was reattached. Assembly/SVG changes remain deferred.
