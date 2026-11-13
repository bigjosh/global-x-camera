# External HOLD reading and loss of the parked state

November 13, 2026. This addendum supersedes the earlier archive's live handoff,
not its recorded measurements. No firmware change was made.

The user reports approximately **0 V at both A3/CN4.4 and CN3.34** relative to
board ground. Their measurement time is not independently synchronized with
the debugger records. A known-rail meter check at CN5.4 remains pending.

At **16:57:22 UTC**, a read-only HOTPLUG operation again found the exact
7,160-byte November9 boot prefix, PC `0x3418078C`, PA2 output mode/push-pull/
no-pull, ODR bit2=1 and IDR bit2=1. GPIOA delay/retiming registers were zero.
The programmer reported 3.27 V target voltage.

At **17:03:05 UTC**, another read-only HOTPLUG operation failed to connect
(`Access port is not valid`) before reading any of its requested registers.
The intended RCC_AHB4ENR and PWR_WKUPEPR reads therefore produced **no data**.
There was no automatic retry, reset, halt, target write or power switch.

At **17:04:06 UTC**, a stats-only JS110 check found **4.9951 V / 3.1976 mA**.
This resembles the previous Standby plateau, but it is not a fresh PC or
Standby-flag proof. Range128 and statistics settings were preserved; the
driver closed cleanly. The exact recovery park can no longer be assumed.
The reason for the state change between successful and failed reads is unknown.

## Interpretation and next check

The official RM0486 sections15.3.1/15.3.10 describe GPIO_IDR as sampling the
physical I/O pin, including output mode. PA2 uses main VDD, and the reviewed
GPIO configuration shows no special retiming or analog mode that explains
HIGH internally with a simultaneous external 0 V. This does **not** establish
damage, an open SB6, or a wrong probe point: first re-establish one stable
operating state and correlate the external and internal measurements.

A finite RAM-only ADC1_INP13 probe is being prepared offline to independently
sample A3 through its divider/U8B/PA12 path. It must preserve all header outputs,
match secure ADC12 to PA12, and leave the external VREF+ supply configuration
intact. VREFINT17 supplies a conversion sanity check. A low ADC13 result alone
would not prove the header voltage because the buffer path itself could fail.
**This diagnostic has not been run.**

The board is left unchanged, with JS output enabled. Current PC and rail-level
state are unverified, COM8 is closed/BREAK released, and no bench helper remains.
Wait for the outstanding meter reference check before changing the measurement
state. No NOR/SD commands, firmware programming or GPIO writes occurred in this
follow-up. The original archive remains byte-for-byte preserved.

Primary references: [RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf),
[ST schematic, sheet10](../../../../../datasheets/boards/nucleo-n657x0-q/MB1940-N657X0Q-C02-schematic.pdf).
