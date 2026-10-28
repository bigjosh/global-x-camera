# Solid red: SD CRC error exposes an overwritten error handler

October 26, 2026. The user removed the 27-ohm SD CLK resistor and reported
solid red on a capture cycle. Root inspected the running failure through
ST-LINK HOTPLUG before resetting. No reset, power switch, UART stimulus,
firmware download, target-memory write, NOR write or SD operation was issued.
An explicit halt was requested after the initial read-only snapshot confirmed
a HardFault. CLI disconnect may resume the same fault loop; continued halt is
not asserted. Commands and UTC timestamps are retained in each `calls.jsonl`.

## Confirmed sequence

1. At 25 MHz, the allocation scan successfully read two slot headers, then
   failed a `CMD17` single-block read. The SD record has `error=14`
   (`SD_ERR_DATA`), `error_stage=5` (READ), and `error_sta=transfer_sta=0x2`
   (`DCRCFAIL`). No image sectors were written in this cycle. RAW result is
   `0x324`, stage3, and the selected red code was correctly **4**.
2. The receiver calls the flash profile's error engine at `0x34181840`.
   Its entire interval `[0x34181840,0x34181D64)` lies inside the camera frame
   `[0x340000A0,0x341D2400)`. Image DMA had overwritten it. The first eight
   expected bytes `43 1E 08 2B 28 BF 08 20` instead read
   `14 13 DC 13 13 14 13 CE`.
3. At `0x34181846`, those live bytes decode as `LDMIA r6!, {r0,r1,r4}`.
   Retained `r6=0x002CE0EB` is unaligned. `CFSR=0x01000000` reports UNALIGNED;
   `HFSR=0x40000000` reports escalation to HardFault.
4. Current `PC=0x34301E2C` is the old HardFault handler's permanent loop,
   which turns red on. It never reaches the new blink/shutdown engine.

The exception core frame at `0x343AFF10` retains `r0=4`,
`LR=0x34302307` (return from the error dispatch's `BLX` at `0x34302304`),
and `PC=0x34181846`. Saved EXC_RETURN is `0xFFFFFFE9`; lazy/extended floating
point context is retained (`FPCCR=0xC000001D`, `FPCAR=0x343AFF30`). This is
not described as a basic-only exception frame. BFAR/MMFAR validity bits are
clear, so their stale values are not fault addresses. The receiver's first
15,628 immutable bytes match the installed build exactly.

## Required correction and qualification gap

The new flash error dispatch violated the existing
[no-prefix-code-after-DMA rule](../../../capture-timing/raw10-relocation.md).
Runtime error handling must execute from persistent, verified code outside
the entire frame/guard allocation. A prefix-only handler may remain for
failures before receiver handoff; post-arm calls cannot use it.

The earlier synthetic prefix test ran before frame DMA, and RAM tests linked
their own safe copy. Successful normal captures never invoked this path.
Those observations remain valid but did not qualify post-capture failure
handling. A corrected build needs a regression that invokes an error after
real frame DMA or an equivalent complete overwrite, checks five blink sets
and shutdown, and verifies UART recovery. No correction is installed yet.

## Limits and preserved state

Resistor removal preceded the error and the old 25 MHz qualification included
that resistor. This capture proves a data CRC failure, not the specific
electrical cause. No new waveform or analog measurement was obtained.
The retained card record has `initialized=0`, `controller_owned=0`,
`media_idle=1`, **and `cleanup_error=10`**; preserve the failed cleanup history
rather than treating the transaction as successful. Existing photos were not
reread or requalified. No current or energy measurement was performed.

Installed image remains the previously verified `flash-v2`, sector SHA256
`5ad1bc968606b17e513680bcdf6abf9c73ca3ccf24a236a37b8ecc89d4e9c661`.
It was not reflashed or reread from NOR in this task. Source/build artifacts
are frozen in the adjacent error-blinks archive under
`snapshots/initial/inputs/flash-v2/`.

`diagnosis.json` contains decoded proof and card fields. Binary snapshots,
register output and CLI logs retain the underlying evidence. The earlier
`stack/raw-card.bin` at `0x34308098` was an incorrect-address read and is
explicitly excluded; `card/raw-card.bin` at `0x34307F80` is the correct record.
Full live prefix/image bytes remain in private `tmp/bringup/solid-red-20261026/`;
only eight bytes needed to demonstrate the faulting instruction are archived.
`SHA256.json` covers the captured evidence and decoded result, not this prose.
