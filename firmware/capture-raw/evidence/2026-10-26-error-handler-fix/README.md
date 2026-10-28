# Persistent error handler: post-frame qualification

This archive records the fix for the [post-frame overwritten-handler fault](../2026-10-26-error-handler-overlap/README.md).
The failure diagnosis and the earlier blink tests remain separate historical
records. The fix passed real post-frame code-4 signaling, shutdown and UART
recovery. The installed production image then reproduced the existing SD CRC
failure and displayed the correct code instead of HardFaulting. See the
[qualification and remaining SD limitation](QUALIFICATION.md).
Do not infer current bench state from this historical archive.

The receiver copies and word-verifies the complete padded 1,536-byte engine
from `0x34181840` into reserved executable SRAM at `0x343C8000` before any
terminal or camera path. The source lies within the camera destination, but
all runtime error dispatch uses the persistent copy. Every boot revokes old
copy authority, refuses enabled D-cache, verifies each copied word, invalidates
I-cache and publishes a fresh `ECP1` observation. Prefix code remains available
only before camera DMA. The early receiver stays 15,804 bytes; the ROM prefix
grows from 6,500 to 6,720 bytes through zero padding.

| Offline candidate | Purpose | 64 KiB sector SHA256 |
| --- | --- | --- |
| `flash-normal-v2` | Normal four-bit 25 MHz capture and Standby | `232af9173262473021453f40ea944dfa4cafc2657443cd0b83ea9c8c8bb3b02c` |
| `flash-postframe-v3` | Real FRAME/STOP, then code 4 before any SD command | `7f21f21e8cf48f8a0cabc4bffb842b55e5960af136496133500e67f25b4ded08` |

Both use exactly the same copied engine, SHA256
`247ad0ddd76963039ed01a2e14beb3499ee9097a8df86f62ad5751047835454e`.
The static audit checks 441 instructions, 68 internal branches including the
Cortex-M55 hardware loop, 34 PC-relative loads and 25 literal words.
The destination is reserved outside the frame/guards, receiver/stack,
low-power helper and LINE snapshot ranges. Independent fresh objcopy/objdump
outputs match the build binaries/listings. Both recovery gates accept the two
exact new image pairs and reject seven modified or crossed pairs. Recorded
offline tests: 182 RAW capture tests, including 20 error-specific tests.

The diagnostic is an explicit separate flash profile. It waits for the real
validated frame and sensor STOP, then records proof at `0x343FD3C0` and invokes
the ordinary code-4 terminal. It does not depend on SD communication or write
an image. Its proof records and the copy record at `0x343FD380` are diagnostic
observations, not idle or maintenance authorization. The production candidate
contains no diagnostic enable literal.

Run `python -B archive.py verify` from this directory. This checks exact public
bytes, generated-source identities, independently regenerated binaries/listings,
the old/new prefix differences and the actual frozen engine dependency audit.
It does not rerun the historical compiler, tests, recovery scripts or bench
operations. A hash match cannot qualify a pending hardware test. Copied build
manifests preserve their creation-time `hardware_status: untested`.

`snapshots/offline` remains the immutable initial offline-only result, including
its then-pending checks. `snapshots/postframe` adds the completed diagnostic,
mid-display recovery and both installations. `snapshots/normal` adds the
uninjected production failure/shutdown/recovery and instrument closure.
The verifier replays both completed current analyses from losslessly compressed
JSONL; hashes bind the decompressed bytes to the original recordings. The
startup NaNs keep whole-session validity false while the finite error windows
are checked separately. Add later named snapshots instead of changing these
records. `python -B archive.py seal` verifies existing snapshots before
refreshing only the outer hash manifest.
ELF/object files, live session controls, superseded build candidates and all
camera/photo payloads are excluded. Local `* -text` preserves exact archived
bytes through Git.
