# Peripheral teardown candidate

This module runs only after a successful automatic capture → PNG → FAT32 save,
the final card-ready check, SDMMC2 deinitialization, and the save loader's return.
It does not enter a CPU low-power mode. `completion.c` owns that separate step.
The first qualification is an awake terminal loop after teardown, followed by
Sleep/Stop/Standby variants and a cold UART-recovery check. Offline tests do not
establish physical rail discharge, GPIO transition behavior or measured power.

`camera_peripherals_shutdown()` uses a caller-owned 256-byte `PLP1` proof at
`0x343F9D00`. The caller clears this proof once before first entry. It requires
the exact generated save-module CRC/length, successful `DONE` report, finished
filesystem snapshot, idle/deinitialized card snapshot, completed `FSD1`
capture-stop proof, disabled caches, privileged MSP Thread mode, masked
interrupts and no active lazy FP preservation. Existing CONTROL FPCA/SFPA
flags are retained; the function does not normalize the caller's FP context.

All live peripheral snapshots precede reset/clock removal. The sequence is:

1. Confirm all CSI virtual channels and DCMIPP pipes are inactive, I2C2 is
   idle, XSPI1 is idle in the known finite NOR-read configuration, SDMMC2 is
   already gated, and no other XSPI client owns the shared XSPIM.
2. Mask receiver interrupt sources, disable CSI, assert digital PHY reset,
   and clear CSI `PCR` to power down its analog PHY and all lanes.
3. Hold sensor `PO5 / NRST_CAM` LOW, then hold CSI/DCMIPP in RCC reset, remove
   their bus clocks and dedicated IC17/IC18 clocks. No subsequent CSI or
   DCMIPP access is permitted.
4. Disable I2C2 and make PB10/PB11 analog/no-pull, then hold/reset-gate I2C2.
5. Preload NOR PN1 chip-select HIGH before switching it to GPIO output,
   require HIGH GPIO input readback, disable XSPI1, hold PN6 clock and PN2 MOSI
   LOW, and make PN3 MISO analog.
   Hold/reset-gate XSPI1 and gate XSPIM. No NOR command is issued.
6. Verify the final RCC/GPIO state, retaining BSEC, SRAM/cache-memory clocks,
   IC11, CPU/PLL clocks, GPIO-bank supplies and all unrelated clock bits.
   Publish `PDON` last after a barrier.

No powered-down register bank is read on repeated calls or failure paths.
A completed repeated call only rechecks the retained storage proof and RCC/GPIO
state; a partial or failed attempt refuses retry. Failure leaves the board
powered and requires an explicit recovery decision. The module neither resets
the CPU nor switches off SD power.

NOR deep-power-down is deliberately deferred: the ROM reads NOR before reaching
the UART recovery guard. Sleep/Stop retain the deliberate pin states; Standby
resets ordinary GPIO configuration and loses the high-SRAM proofs. A return
from these terminal states must not use the old maintenance helper assumptions.

## Stock MB1940 C02 supply paths

The table follows the actual net names in the primary schematic. `VDDIO` and
`VDD3V3` are different 3.3 V rails. D2/R23 removal does not change these paths;
the user has reported no VDDIO-bank or camera-supply bridge rework.

| Consumer | Supply path | When PWR_ON falls for Standby |
| --- | --- | --- |
| Main MCU VDD, VDDIO2 | 5 V → U33 LD39020 → `VDDIO` | Remains powered |
| PC2/PC3/PC4/PE4 SD GPIO bank | `VDDIO` → stock SB23 → `VDDIO5` | Remains powered |
| SD breakout VCC, CN5 pin 4 | 5 V → U34 ST1S31 → `VDD3V3` | Regulator disabled |
| Camera connector VDD_CAM | `VDD3V3` → stock SB10 → CN6 | Regulator disabled |
| NOR U31 | `VDD3V3` → U26 LD56100 → `VDDA1V8` → SB21 → `VDD_OCTO2_M` | Regulator disabled |
| NOR GPIO bank VDDIO3 | `VDDA1V8` | Regulator disabled with NOR supply |
| MCU core | 5 V → U17 TPS62088 → `VDDCORE` | Regulator disabled |

The camera's alternate U42 supply is isolated by the DNF SB31 link in the stock
schematic. The SD bank therefore remains powered while the card supply falls;
this is **not** a powered SD card driving an unpowered VDDIO5 bank. Ordinary
Standby high-impedance/no-pull GPIO state prevents the MCU's former internal SD
pull-ups from sustaining the unpowered card. The same reasoning applies to
PO5 on the still-powered VDDIO2 bank when the camera supply falls. Do not enable
GPIO pull retention without a new supply/backfeed review. Actual voltage
decay and residual signal current remain bench qualifications.

Primary source: [ST MB1940 N657X0Q C02 schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf),
sheets 4 (MCU supplies/SB23), 5 (NOR/SB21), 9 (U17/U23/U26/U33/U34),
10 (CN5.4), and 11 (camera/SB10/SB31). The local source reviewed was
`tmp/hardware-review/nucleo-modifications/mb1940-schematic.pdf`;
rendered inspection pages are in `tmp/bringup/low-power-schematic/`.

The register sequencing is grounded in
[RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf)
§14.6.9 (unclocked peripheral-access hazard), §40.6.3 (CSI stop),
§40.9.2 (`PCR.NPWRDOWN`, zero means power down), §40.10.1 (`PRCR.PEN`), and
the pinned `HAL_DCMIPP_DeInit` implementation. BSEC clock preservation follows
[ES0620](https://www.st.com/resource/en/errata_sheet/es0620-stm32n647657xx-device-errata-stmicroelectronics.pdf)
§2.2.2. Power-mode policy and reset/wake restrictions belong to the separate
completion implementation.

## October 20 NOR chip-select handoff

The first late-loaded teardown image, v54d, completed capture and saved IMG36
before refusing its initial pin check with no teardown mutation. PN1 input
readback was LOW while configured as AF9, although XSPI was idle after two
CRC-verified finite NOR reads. The pin assignment is confirmed by schematic
sheet 5: PN1 connects through R110 to U31 C2/nCS, with R113 pulling it up to
the NOR supply; PN6 connects to U31 B2/SCLK. DS14791 Rev10 Table 18 and the
AF9 table (pp106 and 132) agree. PN1 and PN6 were not interchanged.

A bounded hardware experiment preloaded PN1's output latch HIGH and changed
only PN1 from AF9 to GPIO output. `GPION_IDR` changed from `0x8` to `0xA`,
confirming nCS HIGH; CLK/MOSI configuration stayed unchanged and no NOR
command was issued. The advanced GPIO retiming/delay registers were zero.
The reason for the earlier AF-mode input value remains unresolved.

The revised candidate removes only the initial AF-mode PN1-HIGH requirement.
It retains all storage, idle, mux and pin-mode checks, and requires PN1 HIGH
after GPIO takeover **before** disabling XSPI or changing CLK/MOSI. A pin
that stays LOW stops teardown at that point. Original evidence is under
`tmp/bringup/capture-sleep-20261020/v54d-pin-diagnosis/`,
`v54d-nor-retiming/`, and `v54d-ncs-gpio-finish/result.json`.

## Offline checks

`test_peripherals.py` executes the actual C control flow with modeled register
banks. Its 44 cases cover successful teardown with CONTROL 0/4/12, rejected
cache/privilege/lazy-FP context, incomplete or erroneous save/card/loader/FS
proof, missing/reset clock banks, active capture/I2C/NOR, shared XSPI ownership,
pin-state failure, AF-mode nCS LOW followed by successful GPIO takeover,
nCS stuck LOW after takeover, safe idempotency and refusal after a partial failure.
Every modeled CSI/DCMIPP/I2C/XSPI access requires a live clock and released
reset. BSEC, IC11 and unrelated clock bits must survive.

ARM compilation against the pinned STM32N657 CMSIS headers passes with
`-Os -mcpu=cortex-m55 -mcmse -mno-unaligned-access -Wall -Wextra -Werror`.
The initial candidate object contains 2,348 bytes of code and no static data.
These are implementation checks; the exact integrated image still needs
instrumented hardware qualification.
