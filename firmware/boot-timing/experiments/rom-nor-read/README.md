# Read NOR through the preserved ROM configuration

This RAM-only diagnostic reads 16 bytes (optionally 64) at NOR offset zero. It
does not invoke an external loader or reinitialize the board. The actual
October 17 register snapshot matched UM3234 Rev 5 section 3.4.5, Table 14:
**XSPI1 is routed to physical Port 2 in indirect-read mode**, using single-lane
`0x0B`, 24-bit address and eight dummy clocks. This differs from the installed
external loader's XSPI2 setup. No memory-mapped aperture is accessed.

Build locally with `python firmware/boot-timing/experiments/rom-nor-read/build.py`.
`--length 64` selects the longer bounded read. The build verifies the vendor
commit and rejects a modified CMSIS tree, then saves binary/ELF, disassembly,
symbols, stack usage, linker map and a manifest. No build command accesses
hardware. The initial 16-byte binary is 628 bytes with SHA-256
`87a65b2b20fbea48e6d9c549ad95060b57aa345b24abc7d934c8c9d7edde0ebd`.

The first hardware read succeeded: DONE, result 0, count 16, 51 polls, final
SR=2, thread-mode PC at `0x341A01F2`, and the expected `STM2` header prefix.
Logs are in `tmp/bringup/rom-nor-read16-20261017`. Its captured original DLR was
`0x67F` and AR was `0x240`; the earlier value read at offset `0x30` was reserved
space and was **not** DLR. This result verifies the small read, not yet a full
sector backup or any erase/program operation.

Root/bench operator sequence, only after review:

1. Use the working HOTPLUG AP1 connection, halted in secure privileged thread
   mode. Confirm D-cache is off and reserve `0x341A0000..0x341A0FFF` for this
   experiment. This is fresh executable RAM for the first attempt; when
   replacing its code later, first arrange instruction-cache coherency (the
   separately tested cache-prep helper, or a fresh boot). Download and verify
   `read.bin` at `0x341A0000`, without an external loader or boot header.
2. Set `PC=0x341A0001`, `XPSR=0x01000000`, then use **`-run`**, not an addressless
   `-g`. Entry masks interrupts, clears MSPLIM, and uses fresh stack top
   `0x341A1000`; it never returns to the interrupted firmware.
3. Reconnect/halt after completion. For the initial 16-byte build, the awake
   loop is `0x341A01F0/0x341A01F2`. Read 23 words at `0x341A0400` and the requested
   data bytes at `0x341A0500`. Require `magic=0x444F4E45`, result zero, full byte
   count, `IPSR=0`, and successful header comparison. The expected first 16
   bytes of the installed GPIO diagnostic's STM32 boot header are
   `53 54 4D 32 00 00 00 00 00 00 00 00 00 00 00 00`.

Before any XSPI write, the helper requires D-cache off, CONTROL/IPSR zero,
XSPI1/XSPIM clocks present, their resets clear, XSPIM_CR exactly 2, and this
exact controller setup:

| Register | Required value |
| --- | --- |
| CR | `0x10000001` |
| DCR1 | `0x001F0000` |
| DCR2 | `1` |
| CCR | `0x01002101` |
| TCR | `8` |
| IR | `0x0B` |

BUSY and FIFO level must also be zero. The only peripheral writes are FCR=3
(clear completion/error flags), DLR=length-1, and AR=0 (start addressed read).
**DLR is offset `0x40`; offset `0x30` is reserved.** Each data byte is read from
DR only when FIFO level is nonzero. Two polling phases share a one-million-
iteration budget. Success requires all bytes, TCF set, BUSY clear and FIFO
empty. There is no HAL tick, interrupt, BKPT, clock/reset change, cache change,
security/OTP operation, NOR mode command, write-enable, erase or program command.

The helper does not restore DLR or AR, clear the final completion flag, abort a
timeout, or restart a transfer. Such writes would obscure the final transaction
state. A timeout reports partial data and ends awake; the controller may still
be busy and must be inspected before another transaction. The finite polling
budget is not a calibrated wall-clock timeout and cannot recover a CPU bus fault
or a stalled peripheral register bus access. The observed clock/reset gates
reduce those risks; they do not make the helper a general-purpose loader.

Status fields, consecutive 32-bit words at `0x341A0400`:

| Word | Meaning |
| --- | --- |
| 0–5 | Magic, result, requested bytes, read count, total polls, last SR |
| 6–10 | CONTROL, IPSR, CPU CCR, original MSP, original MSPLIM |
| 11–13 | RCC_AHB5ENR, RCC_AHB5RSTR, XSPIM_CR |
| 14–17 | Initial CR, DCR1, DCR2, SR |
| 18–22 | Initial CCR, TCR, IR, DLR, AR |

Results: 0 success; 1 D-cache enabled; 2 incorrect CPU context; 3 missing clock;
4 controller reset; 5 mux mismatch; 6 controller configuration mismatch;
7 BUSY/FIFO not idle; 8 transfer error; 9 premature completion; 10 polling
timeout; 11 extra FIFO data. Magic `0x52554E4E` means started; only DONE indicates
the result was finalized. A D-cache refusal may leave RAM status invisible to
the debugger; directly check CPU CCR as a precondition.

Primary references: UM3234 Rev 5 section 3.4.5/Table 14; RM0486 Rev 4 section
28.4.10 (indirect-read trigger, finite DLR, FIFO/completion), and register layout
in `stm32n657xx.h` at vendor commit
`e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`.
