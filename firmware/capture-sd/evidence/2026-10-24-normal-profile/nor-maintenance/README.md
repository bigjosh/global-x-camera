# NOR completion polling: failures and v2 hardware follow-up

The original programmer stopped twice with result 16 at the post-program WEL
check: sequence 241004 at `0x6200`, then a separately authorized repair,
sequence 241007, at `0x7500`. Both failures remain failures. Each was followed
by successful fresh INFO and a full read of the actual partial NOR contents.
Both reported 256-byte pages match the requested v62 bytes in those later reads.
This proves their readback contents, not why the completion check failed.

The local MB1940 schematic identifies U31 as **MX25UM51245GXDI00**. Its observed
RDID `C2 80 3A` agrees with Table 15 of Macronix MX25UM51245G PM2183 v1.6.
Section 9-1 recommends confirming WIP=0 before checking WEL=0; Figures 17–18
show another RDSR and polling while WEL remains set. The original helper used
the cached WIP-clear byte for its later WEL check. Its cleanup overwrites the
status byte, so the archived final status/security zero do not preserve the
triggering sample. [Manufacturer datasheet](https://www.macronix.com/Lists/Datasheet/Attachments/9241/MX25UM51245G,%201.8V,%20512Mb,%20v1.6.pdf).

The separately built v2 helper requires a fresh RDSR after a WIP-clear
observation, then both WIP/WEL clear before accepting completion. It retains
the bounded deadlines, controller transaction ordering, clock/cache/context
gates, failure cleanup, page verification and full final comparison. It never
uses WRDI to satisfy the completion check. Additional proof at `0x341B4300`
retains sampled completion states and the first failure before cleanup.
The original helper remains archived unchanged.

V2 INFO sequence **241011** passed. WRITE sequence **241012** then programmed
184 pages across 14 changed sectors from the exact second partial read to
**v62b**, a revised target image. The helper's final full NOR read was uploaded
from RAM and matched all 65,536 desired bytes. A separate read-only operation
confirmed that the following 4,096 bytes were unchanged. The live v2 helper was
also read back and matched the built binary at its exact terminal park.

The v2 proof records **198 completion checks and zero WIP-clear/WEL-pending
samples**. This is one successful hardware qualification. It neither reproduces
the earlier transient nor establishes its mechanism, and it is not a guarantee
against recurrence. No reset/power interruption during this maintenance sequence
is reported by the bench owner; these were explicit guarded repairs, not an
automatic retry loop.

| Artifact | SHA-256 |
|---|---|
| Original programmer | `2dd98e8facd32426b622cb4dc023f4efac5315a7f5d336379066bda43db06909` |
| V2 programmer, 3,320 bytes | `e69f0d0c3c49c2bad1ad5e7e8ff5907fcf3b251cb5b968629c18a9c57247f307` |
| Second exact partial state | `9a8c787b44b577fa460ea1103a712e6d8164ccd9f77a3ecb2328d37d0cad8238` |
| Final v62b 64 KiB region | `ae732240a491e4cba5e5ce408e43f56ee1ed99c33fe8008b2848c0ff6c98118d` |

`operations/` retains exact requests, commands, statuses, logs and relevant NOR
bytes; `helpers/` binds the source and binaries; `inputs/` retains both requested
images and the starting image. These are firmware bytes, not camera pixels or
SD file contents. Original request paths are historical provenance; portable
replay uses the archive-relative paths directly.

Run `python replay.py` here to verify file hashes, request CRCs, original failure
states, both partial-page comparisons, v2 diagnostics, exact live helper bytes,
full final readback and the following guard. This is offline evidence replay;
it does not operate or requalify hardware. Root owned the bench throughout;
archive assembly and replay were performed offline.
