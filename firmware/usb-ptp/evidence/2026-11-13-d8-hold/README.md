# D8 HOLD substitution — November 13

The user moved HOLD from D3 to **D8 / CN14.1 / PD12** and requested a simple
substitution/reload without another test campaign. USB selected-mode HOLD stays
LOW; early battery HOLD/UART behavior and final shutdown policy are unchanged.
The capture owner disables the former PD12 phase-marker output to avoid
pulsing the latch. RAM counters and the separate PD0 exposure marker remain.

This record initially covers the offline build and mandatory package layout,
source/hash and recovery-preservation checks only. **No new test campaign was
run.** Existing test pin/schema expectations were retargeted but not executed.
The earlier D3 qualification is historical and is not a D8 test claim.

USB policy schema 4 and USB shutdown schema 5 identify GPIOD12. Capture uses
HOLD contract schema 5. The secure GPIO base is 0x56020C00; only PD12 fields
are changed by USB HOLD release. It floats through the 42-byte final WFI group,
with no battery assertion on a USB shutdown refusal or unexpected return.

The build retains provisional early HOLD before VBUS selection and early
UART recovery HIGH. It does not promise a zero-pulse USB cold boot.

## Exact reload artifacts

`package/` contains the two 64 KiB NOR regions, their boot prefix and recovery
metadata. The USB hook is 444 bytes at 0x34181E40 and ends at 0x34181FFC, leaving
four bytes before 0x34182000. The prefix is 7164 bytes; do not reuse the D3
package's 7160-byte admission. The capture tail and original UART guard are
byte-identical to their reviewed inputs. `results.json` records mandatory checks.

| Artifact | SHA-256 |
|---|---|
| Prefix | `b1b032c7ae48e68a8942922b9a6a2d8e57983030a331b1d5b590c01ee3571c52` |
| Sector0 | `1a9278ab1733134a86e382af61b3a78627fe40d82e9e137dd33f2bfcf8de1197` |
| Sector1 | `ed6d416974bf0801f1b1daa6e29520db06fa3294bb33060a9dfbc48b761fbc38` |
| USB | `d2bbb76f789e01bb94f09892f291d602b5d7276b96124eb613d70f1bd7b87461` |

`SHA256SUMS` covers frozen build/package/result files, excluding this expandable
README and any later hardware records.

## Hardware status

Installed by the root campaign on November13. Both64KiB NOR regions were
programmed and their complete programmer readbacks match the listed images.
The existing D3 UART recovery was used solely to enter programming; the new
UART code is preserved, but no post-load recovery, capture, latch, shutdown
or power test was run, as requested. One normal powered reset activated the
new firmware; it was not a cold-power cycle. Direct5V/ST-LINK remain connected,
no JS operation occurred, COM8 is closed/BREAK released, and no helper remains.
The final runtime/rail state was not measured. See
[programming record](hardware/final-state.json). Schematic/assembly edits were
deferred at this programming checkpoint.

## Subsequent user confirmation and canonical wiring

On November 13 the user replied, "works!", and requested that D8 become the
canonical HOLD connection in the schematic and assembly instructions, followed
by commit and push. The [current diagram](../../../../docs/power/lipo-latch-wiring.svg)
and [assembly guide](../../../../docs/prototype/nucleo-assembly-guide.md) now use
**D8 / CN14 pin 1 / PD12** directly to Q2 gate pin 1; CN15 pin 21 is the same net.
A3 is retired from HOLD, and the intermediate D3 choice is superseded without
claiming that D3 failed.

This is the user's functional confirmation of the loaded firmware. No further
automated tests or hardware operations were performed for this documentation
update, and no numerical HOLD timing, USB-removal or rail-sequencing result is
inferred. The package, frozen build hashes and programming records are unchanged.
