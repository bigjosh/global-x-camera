# CLK-only cold failure and warm control, October 27, 2026

**The unchanged normal firmware failed its first SD header read at25MHz.
The subsequent isolated warm PIO control failed with exactly the same512
received bytes. Reconnecting CMD alongside CLK made the same warm binary
read the sector correctly.** Earlier CLK-only warm passes are not currently
reproducible; cold versus warm operation alone does not explain the difference.

The user reported that normal power-up gave four red blinks with only CLK
probed, and completed with both CLK and CMD probed. This archive tests the
CLK-only failure configuration and the subsequent both-probe comparison.
The reported wiring is a direct CLK jumper with no series resistor,
Saleae CLK input and ground attached, initially with CMD disconnected.
This supersedes older resistor descriptions; physical geometry was not
independently inspected.

## Attempts and evidence strength

| Attempt | What happened | What is established |
|---|---|---|
| Cold01 | JS input4.8935V but essentially zero load after ON; observer skipped all debug access | No powered normal boot or error diagnosis |
| Cold02 | Powered current sequence; ST-LINK USB absent, first CLI returned no debug probe | Five groups of four current pulses, followed by8.215mA; no SRAM command attribution |
| Cold03 | Normal flash boot with fresh read-only SRAM observations during error display | CMD17 data CRC failure at inferred LBA0, zero writes; same four-pulse groups, followed by8.108mA |
| Warm PIO01 | Exact prior25MHz RAM READ binary; camera held reset; one LBA0 sector | CMD17 data CRC failure, same512 bytes as Cold03, zero writes |
| Both-probe warm PIO01 | User reconnected only CMD; identical frozen RAM binary | All512 bytes match the verified reference; zero errors/writes, successful final idle |
| Both-probe cold01 | Unchanged normal firmware; observer skipped access because current was already low | Sustained8.198mA signature after approximately0.56s; no SRAM, image readback or SBF verification |

There is **one normal cold failure with complete retained SRAM attribution**,
not a statistical reliability qualification. Cold02 adds current-pattern
evidence. Every whole current recording retains71 startup NaN samples and
whole-session validity remains false. Separately scoped post-ON intervals
are finite and contiguous; no dropped chunks or cleanup errors were recorded.

## Exact failure

Cold03 retained RAW result`0x324`, stage3, SD error14/stage5/CMD17/STA2
(DCRCFAIL), cleanup_error10, and scan_headers0. The unchanged allocator reads
one512-byte header at each LBA`i*3730` and increments the counter only after
a successful read. Thus its failing header is LBA0. This inference uses
the retained scan state; `last_argument` belongs to later cleanup and is
not treated as the failed command's argument.

FRAME completed22.849ms, sensor STOP58.798ms, and SD-ready95.999ms after
the runtime begin counter. Failure completion was97.324ms. These are400MHz
DWT intervals, not external power-to-event measurements. The frame and STOP
preceded the failed scan, so active camera transfer at that specific header
read is not established. CFSR/HFSR were zero and the1536-byte relocated
error engine matched its expected hash. Both RAW and card records report
zero written sectors.

The warm control used exact binary
`d594faa4207ff9fd5449a4c4c3f3e9cfafe0b755311221a300c1bef5c052c887`.
Immutable-code and final-proof checks matched, camera reset remained asserted,
GPIO speed3 and25MHz/four-bit/falling-launch settings were verified. It
retained RAW result1038, SD error14/stage5/CMD17/STA2, DCOUNT0,128 serviced
words and cleanup_error10, with no CPU fault. It is a failed operation,
despite later media_idle1/initialized0/controller_owned0; it is not an
ordinary successful-idle proof.

After the user reconnected CMD, the identical warm binary returned the
correct reference SHA256
`fa6a9fc6d2fdd48e921c7a3b2d794e78477934056895190cc78449c4fcb05598`,
with result/error/cleanup all zero and a fresh successful-idle check. This
one fail/pass comparison supports a setup-sensitive link; it does not
isolate probe capacitance, grounding, incidental wire movement or pad history.

## Retained-data model

Both cold and warm failed buffers have SHA256
`1b7fcc1c7901b579989afeaf7ab95b7afbf029cfa05c2d50ad299cbcae4802e2`.
They differ from the verified same-card LBA0 pattern in306 bytes, beginning
at byte71. All512 bytes exactly fit deleting eight four-bit symbols at
indices`143,149,303,309,623,629,954,960`, then appending four computed CRC
wire bytes`55 4A 5C AB`. This also exactly matches the earlier CLK1 slew
trial03 failure. It differs from the ten-symbol loss seen in the earlier
probe-free PIO/IDMA campaign.

The alignment is unique within the tested deletion-only model. It is
retained-data evidence, **not** an electrical root-cause proof or a recording
of wire transitions. It does not distinguish excess clocks at the card,
missed receive clocks at the MCU, reflections, or another shared timing
mechanism. Identical cold/warm failures also mean camera activity and cold
power-up are not necessary conditions for this observed failure.

## Observation, recovery and final state

The normal-cycle observer issued only HOTPLUG memory uploads. It made no
halt/reset, target write, UART stimulus, power command, SD/NOR operation,
or live SD-register read. Fresh current and time limits constrained it to
the blink interval; it preserved nonzero errors and did not wait for a
successful terminal marker. After retained evidence was saved, root used
the separately authorized UART recovery and guarded RAM READ workflow.
Those recovery/programming operations are fully recorded, rather than
being described as part of the read-only observer.

Recovery before the CMD comparison passed the exact installed early park`0x3418078C`, with nine
good UART pulses and zero bad. The last saved park recheck command completed
at17:34:12.425211UTC. That park was superseded by the successful both-probe
warm READ and then the final normal cold boot. CLI disconnect may resume
the branch-to-self park, so persistent debug halt was never assumed.

The final cold run reached a sustained below20mA mean-bin tail at approximately
0.556s after the host power-on event. Its34.355s tail averaged8.19815mA.
The recorded startup maximum was227.0mA among retained sample extrema and
188.3mA for a5ms mean bin. These timing boundaries have5ms bin uncertainty
plus approximate host/device time alignment; they are not exact shutdown
or energy measurements. The observer skipped debug access at1.566s because
current was already low. No stored image or SBF was checked.

**Final target remained powered after that both-probe normal cold run**, with
CMD, CLK and ground attached and no reported resistor. No UART recovery
followed it. The final current logger closed cleanly at17:37:41.024709UTC,
restored original stream settings/range128 and left power on. Root reported
no active bench helper. Final state is a current signature, not a retained
firmware-state or Standby proof.

No NOR programming or card erase occurred. Zero image-sector writes are
proven for the diagnosed CLK-only cold failure and both isolated RAM reads.
The final both-probe normal run may have saved an image; its result and
stored contents were not independently verified. Installed source identity
reuses the prior sealed error-handler-fix archive; there was no fresh
physical NOR readback in this phase.

## Reproduction

Run `python -B archive.py verify` and `python -B archive.py replay` from this
directory. These commands access only local files. They verify gzip and
original JSONL hashes, prior sealed source references, all four numeric
current summaries, both error pulse patterns, the final low-current signature,
the complete header alignment, warm/cold byte equality, both-probe warm
readback, diagnostic attribution and pre-comparison recovery records.
They do not rerun firmware, instruments or historical tests.

- `compression.json`: original and compressed byte lengths/SHA256 values;
  gzip is lossless, deterministic with mtime0.
- `attempts/`: unmodified observation bytes/CLI logs, and the complete warm
  READ operation including its failed status.
- `reports/`: saved summaries and models, including the earlier scope audit
  written before the warm control; this README describes the final result.
- `reference/` and `sealed-reference-bindings.json`: compact comparison
  data/provenance and exact existing installed/RAM build references.
- `host-source/`: observer, logger and offline replay inputs. The archived
  hardware helpers are inspection copies; do not launch them from here.
- `recovery/`: UART records and exact final park checks.

Current pulses infer the LED association; there was no optical/GPIO trace.
Pulse/gap intervals include the existing conservative±20ms bin/filter
uncertainty. Voltage is JS110 input voltage, not a target rail probe.
No energy, analog margin, general protocol compliance, or independent
Standby attribution is claimed.
