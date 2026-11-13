# Live HOLD code unchanged; separate PA2 from the Arduino header path

November 13, 2026, America/New_York. The user reports no A3 HIGH level in a
logic trace during a trigger-held cycle and good continuity from A3 to Q2's
gate. The user then confirms JS OUT is directly connected to the board's
5 V input. The external logic trace was not imported or independently viewed.

## Verified live

The complete **7,160-byte running boot prefix** matches the verified November9
A3 build byte-for-byte:
`852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084`.
This includes the early PA2 HOLD instructions, original UART guard, prefix
error engine and USB hook. The later NOR regions were not reread; this is not
a new full-flash comparison.

The established COM8 1 Mbaud recovery train plus ST-LINK BREAK/reset parked
the MCU at **0x3418078C**. The exact recovery verifier passed, with **9 valid
and 0 bad pulses**, and explicitly used debugger halt to verify context.
No firmware download, target-memory write, NOR/SD command or JS power switch
occurred. This differs from the earlier passive November12 observation,
which used neither reset nor halt.

Two consecutive GPIOA reads returned:

| Register/property | Value |
|---|---|
| MODER | `0xABFFEFDF`; PA2 mode 1, output |
| OTYPER | `0`; PA2 push-pull |
| OSPEEDR | `0x0C000000`; PA2 low speed |
| PUPDR | `0x64000000`; PA2 no pull |
| IDR | `0x8004`; PA2 input HIGH |
| ODR | `0x4`; PA2 output HIGH |

The pre-recovery JS snapshot was 4.991 V and 28.861 mA; it is not a measured
post-park current. The archived firmware inputs match the source text; two
raw file-hash differences are only CRLF/LF line endings. Current boot-HOLD,
shutdown and USB entry/shutdown sources match commit462f1918. No firmware
source was changed in this investigation.

## The PCB path still needs an external measurement

ST's schematic distinguishes these nodes:

```text
MCU PA2 ----+---- CN3 pin 34 (direct MCU-side tap)
           |
          SB6
           |
           +---- CN4 pin 4 / Arduino A3 ---- external Q2 gate
           |
           +---- resistor-divider/op-amp branch ---- PA12 ADC input
```

PA12 is a separate buffered analog companion, not the HOLD GPIO. GPIOA's
secure register base `0x56020000` is correct in ST's CMSIS header. SB6 pad1
is the MCU-side PA2/ARD_A3D net; pad2 is the header-side ARD_A3R net.

**SB6 is factory fitted**, not a deliberately open jumper in the documented
board. The official C02 BOM sheet `BOM`, row117 lists it among fitted
0-ohm SB0603 parts (YAGEO RC0603JR-070RL); the manufacturing placement also
marks it `SB_ON`. This verifies the previous stock-routing assumption, not
the present board's actual continuity or solder condition.

Sources: [ST schematic pages6 and10](../../../../datasheets/boards/nucleo-n657x0-q/MB1940-N657X0Q-C02-schematic.pdf),
[UM3417 Rev4 page34/Table20](../../../../datasheets/boards/nucleo-n657x0-q/UM3417-Nucleo-user-manual-Rev4.pdf),
[C02 BOM archive](../../../../datasheets/boards/nucleo-n657x0-q/MB1940-C02-bom.zip).

Good continuity from A3 to Q2 does **not** prove the PA2-to-SB6-to-A3 portion.
An open SB6/path, wrong header contact, probe/ground/threshold issue or other
physical mismatch remains possible; none is established. The earlier
inference of latch takeover failure is not a diagnosis of a specific part.

## Handoff

The MCU is intentionally left powered in the exact early UART recovery park,
with PA2 HIGH. The user is asked to measure **CN3 pin34** and **CN4 pin4/A3**
relative to **CN5 pin6/GND**; no trigger is needed. Results are pending.
COM8 is closed with BREAK released, no recorder/helper is active, and JS
range128/settings were preserved and its API closed. The user has bench
control for those measurements. A reset/power cycle leaves this park and
starts the normal installed program unless recovery is requested again.

`verified-park01/` preserves the exact prefix and guard records; `park-gpio/`
preserves both GPIO reads. `initial-read/` and `direct5v-read/` preserve the
unsuccessful pre-recovery attempts. `offline-comparison.json` records the
source comparison; `results.json` states scope and terminal state. No commit
or push was performed.
