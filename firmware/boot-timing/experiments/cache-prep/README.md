# RAM cache preparation experiment

This standalone diagnostic tests whether the instruction cache retained after
normal ROM boot explains an external-loader initialization fault. It is not a
boot image, boot-time optimization, or proof that the cache caused the fault.
The loader was observed replacing code at `0x34180400..0x341874a0`; the CPU had
`SCB_CCR=0x00020201` (instruction cache enabled, data cache disabled).

`python firmware/boot-timing/experiments/cache-prep/build.py` builds locally using
the existing pinned STM32 camera repository and GCC toolchain. Optional
`--toolchain`, `--vendor`, and `--out` select other paths. No command in this build
script connects to hardware. Outputs include the binary, ELF, disassembly,
symbols, linker map, and provenance/command/hash in `build.json`.

Code starts at `0x34190000`; its Thumb entry is `0x34190001`. It disables
interrupts, clears MSPLIM, and calls the pinned CMSIS `SCB_DisableICache()` only
when D-cache is already disabled. CMSIS issues the barriers, clears CCR.IC, and
invalidates the instruction cache. It leaves debug, clock, security, peripheral,
OTP, and flash registers untouched. It does not return or restore the original
CPU execution state. A power cycle restores the boot configuration. The compiled
148-byte version uses no stack and ends in an awake NOP/branch loop at
`cache_prep_ready`, `0x34190072`. It contains no BKPT, so disconnecting the
debugger does not deliberately trigger a debug exception.

Use only with an already working secure privileged HOTPLUG AP1 debug session,
halted at the diagnostic firmware's idle loop. The fresh code region and status
region must be free. Download and verify this binary at `0x34190000`, without a
boot header. Do not select an external loader for that RAM download. The local
CubeProgrammer 2.23 help documents `-coreReg PC=<value> XPSR=<value>` and `-run`
(Run core). After download and verification, use
`-coreReg PC=0x34190001 XPSR=0x01000000 -run` with the working HOTPLUG AP1
connection. Do **not** use `-g` without an explicit address: on the first bench
attempt it selected `0x08000000`, despite the prior PC write, causing a HardFault.
The bench operator owns execution sequencing. Reconnect and halt, confirm PC is
in the final awake loop, IPSR is zero, and the record below is valid before a
loader attempt. No hardware execution is performed by this directory's scripts.

Retry from a fresh cold boot if the core entered HardFault or the loader hung.
Verify the normal diagnostic markers, working HOTPLUG AP1 access, thread mode
(`IPSR=0`), and original CCR before running this helper again. Rewriting PC and
xPSR does not perform an architectural exception return or clear active
exception bookkeeping; do not count it as recovery to thread mode. The initial
BKPT-ending version did perform the cache change (`0x20201` to `0x201`) and clear
MSPLIM (`0x34180C00` to zero), but the attempt also involved HardFault execution.
Those results demonstrate the register changes, not clean loader recovery.

Revision 2 (awake loop), 148 bytes, has SHA-256
`bd34d1290a3e446aa3a01b99f2bc53707b12708eac92da1afabe6de50ea64dbf`.
The superseded revision 1 (BKPT) hash was
`aded87aca0306f208fbdaee0e5e0e7046eb07ddb6760a947c656265d1577a60f`.

Read five 32-bit words from `0x34190400`:

| Offset | Meaning | Expected for the observed board state |
| --- | --- | --- |
| `0x00` | Result magic | `0x43414348` means completed |
| `0x04` | Original CCR | `0x00020201` |
| `0x08` | Original MSPLIM | Recorded, not assumed |
| `0x0C` | New MSPLIM | `0` |
| `0x10` | Final CCR | `0x00000201` |

Other magic values are `0x50524550` (started), `0x4641494C` (IC bit failed to
clear), and `0x44434143` (D-cache enabled, operation refused). With D-cache
enabled, the RAM record itself is not guaranteed debugger-visible; inspect CCR
directly. Do not treat a missing or stale record as success. This is solely a
volatile cache-state diagnostic, not a general safe external-loader setup.

Primary implementation: ARM CMSIS `SCB_DisableICache()` in
`STM32Cube_FW_N6/Drivers/CMSIS/Include/m-profile/armv7m_cachel1.h`, lines 76–88,
in the vendor checkout pinned to `e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`.
The build includes that file rather than copying its implementation.
